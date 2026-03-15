from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlmodel import Session, select

from app.models import Agent, Conversation, ConversationAgent
from app.services.context_packs import extract_context_pack_summaries
from app.services.planning_boundary import build_planning_boundary_projection
from app.services.runtime_authority import (
    apply_runtime_authority,
    build_runtime_authority_projection,
    derive_runtime_authority,
    extract_authority_profile_id,
)
from app.services.runtime_scope import resolve_run_scoped_nodes
from app.services.runtime_snapshot import (
    clean_list_of_text as _clean_list_of_text,
    clean_text as _snapshot_clean_text,
    created_sort_key as _created_sort_key,
    extract_runtime_team_snapshot,
    node_payload as _node_payload,
    normalize_runtime_source_key as _normalize_runtime_source_key,
    normalize_status as _normalize_status,
)
from app.services.skill_projections import extract_attached_skills, extract_runtime_agents_with_skills, extract_skill_usage_events
from app.services.skill_registry import build_skill_registry


EVIDENCE_NODE_TYPES = {"Decision", "Assumption", "Plan", "Observation", "ContextSummary", "Artifact", "Resource", "Message"}


def _jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def _clean_text(value: Any) -> str | None:
    clean = str(value or "").strip()
    return clean or None


def _first_present_value(mapping: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) is not None:
            return mapping.get(key)
    return None


def _runtime_status_from_counts(status_counts: dict[str, int]) -> str:
    if status_counts.get("running", 0) > 0:
        return "running"
    if status_counts.get("error", 0) > 0:
        return "error"
    if status_counts.get("queued", 0) > 0:
        return "queued"
    if sum(status_counts.values()) > 0:
        return "done"
    return "idle"


def _step_activity_index(nodes: list[Any]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for step in sorted([node for node in nodes if str(getattr(node, "type", "")) == "Step"], key=_created_sort_key):
        payload = _node_payload(step)
        status = _normalize_status(payload.get("status"))
        keys = {
            str(payload.get("agent_id") or "").strip(),
            str(payload.get("agent") or "").strip(),
            str(payload.get("assignee") or "").strip(),
            str(payload.get("runtime_instance_id") or "").strip(),
            str(payload.get("instance_id") or "").strip(),
            str(payload.get("executor_id") or "").strip(),
            str(payload.get("template_id") or "").strip(),
        }
        keys = {key for key in keys if key}
        for key in keys:
            row = out.setdefault(key, {})
            row[status] = row.get(status, 0) + 1
    return out


def _step_activity_source_index(nodes: list[Any]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    field_names = (
        "agent_id",
        "agent",
        "assignee",
        "runtime_instance_id",
        "instance_id",
        "executor_id",
        "template_id",
    )
    for step in sorted([node for node in nodes if str(getattr(node, "type", "")) == "Step"], key=_created_sort_key):
        payload = _node_payload(step)
        for field_name in field_names:
            key = str(payload.get(field_name) or "").strip()
            if not key:
                continue
            row = out.setdefault(key, {})
            row[field_name] = row.get(field_name, 0) + 1
    return out


def _preferred_step_source_key(field_counts: dict[str, int] | None) -> str:
    if not field_counts:
        return "step_payload.agent_id"
    for field_name in (
        "agent_id",
        "agent",
        "assignee",
        "runtime_instance_id",
        "instance_id",
        "executor_id",
        "template_id",
    ):
        if int(field_counts.get(field_name, 0)) > 0:
            return f"step_payload.{field_name}"
    return "step_payload.agent_id"


def _skill_packages_for_team_items(
    *,
    team_items: list[dict[str, Any]],
    skill_registry: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    skill_ids: set[str] = set()
    for team_item in team_items:
        for attached in list(team_item.get("attached_skills") or []):
            skill_id = str(attached.get("skill_id") or "").strip()
            if skill_id:
                skill_ids.add(skill_id)
    return sorted(
        [skill_registry[skill_id] for skill_id in skill_ids if skill_id in skill_registry],
        key=lambda item: (str(item.get("name") or "").lower(), str(item.get("id") or "")),
    )


def aggregate_attached_skills(runtime_agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aggregated: dict[str, dict[str, Any]] = {}

    for agent in runtime_agents:
        for attached in list(agent.get("attached_skills") or []):
            skill_id = str(attached.get("skill_id") or "").strip()
            if not skill_id:
                continue

            current = aggregated.get(skill_id)
            if not current:
                aggregated[skill_id] = {
                    "skill_id": skill_id,
                    "skill_name": attached.get("skill_name"),
                    "load_level": attached.get("load_level") or "metadata_only",
                    "selected_by": attached.get("selected_by") or "runtime",
                    "selection_reason": attached.get("selection_reason"),
                    "status": attached.get("status") or "active",
                    "role_count": 1,
                }
                continue

            current["role_count"] = int(current.get("role_count") or 0) + 1
            if attached.get("skill_name"):
                current["skill_name"] = attached.get("skill_name")
            if attached.get("selection_reason"):
                current["selection_reason"] = attached.get("selection_reason")
            if attached.get("selected_by"):
                current["selected_by"] = attached.get("selected_by")
            if attached.get("status"):
                current["status"] = attached.get("status")

            current_level = str(current.get("load_level") or "")
            incoming_level = str(attached.get("load_level") or "")
            level_rank = {"metadata_only": 1, "instructions": 2, "resources": 3}
            if level_rank.get(incoming_level, 0) >= level_rank.get(current_level, 0):
                current["load_level"] = incoming_level or current_level

    return sorted(
        aggregated.values(),
        key=lambda item: (
            str(item.get("skill_name") or "").lower(),
            str(item.get("skill_id") or ""),
        ),
    )


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        clean = value.strip().lower()
        if clean in {"1", "true", "yes", "y", "on"}:
            return True
        if clean in {"0", "false", "no", "n", "off"}:
            return False
    return False


def _intish(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        clean = value.strip()
        if clean and clean.lstrip("-").isdigit():
            return int(clean)
    return None


def _slot_indexes(runtime_snapshot: dict[str, Any] | None) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    slots = list(((runtime_snapshot or {}).get("team_plan") or {}).get("slots") or [])
    slot_by_id: dict[str, dict[str, Any]] = {}
    slot_by_role_id: dict[str, dict[str, Any]] = {}
    for slot in slots:
        if not isinstance(slot, dict):
            continue
        slot_id = _snapshot_clean_text(slot.get("slot_id") or slot.get("slotId") or slot.get("id"))
        role_id = _snapshot_clean_text(slot.get("role_id") or slot.get("roleId"))
        if slot_id:
            slot_by_id[slot_id] = slot
        if role_id:
            slot_by_role_id[role_id] = slot
    return slot_by_id, slot_by_role_id


def build_team_view_projection(
    *,
    runtime_agents: list[dict[str, Any]],
    runtime_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    slot_by_id, slot_by_role_id = _slot_indexes(runtime_snapshot)
    items: list[dict[str, Any]] = []

    for agent in runtime_agents:
        slot = slot_by_id.get(str(agent.get("slot_id") or "").strip()) or slot_by_role_id.get(str(agent.get("role_id") or "").strip())
        display_label = _clean_text(
            agent.get("display_label")
            or agent.get("name")
            or (slot or {}).get("display_label")
            or (slot or {}).get("displayLabel")
            or agent.get("role_label")
            or agent.get("runtime_instance_id")
            or agent.get("agent_id")
        )
        selection_reason = _clean_text(
            agent.get("selection_reason")
            or (slot or {}).get("selection_reason")
            or (slot or {}).get("selectionReason")
            or (slot or {}).get("reason")
        )
        preset_id = _clean_text(agent.get("preset_id") or (slot or {}).get("preset_id") or (slot or {}).get("presetId"))
        attached_skill_ids = sorted(
            {
                str(skill_id).strip()
                for skill_id in list(agent.get("attached_skill_ids") or [])
                if str(skill_id).strip()
            }
            | {
                str(item.get("skill_id") or "").strip()
                for item in list(agent.get("attached_skills") or [])
                if str(item.get("skill_id") or "").strip()
            }
        )
        items.append(
            {
                "runtime_instance_id": agent.get("runtime_instance_id") or agent.get("instance_id"),
                "display_label": display_label,
                "slot_id": agent.get("slot_id") or (slot or {}).get("slot_id") or (slot or {}).get("slotId"),
                "slot_label": _clean_text(
                    (slot or {}).get("display_label")
                    or (slot or {}).get("displayLabel")
                    or (slot or {}).get("label")
                    or (slot or {}).get("name")
                ),
                "role_id": agent.get("role_id") or (slot or {}).get("role_id") or (slot or {}).get("roleId"),
                "role_label": agent.get("role_label") or (slot or {}).get("role_label") or (slot or {}).get("label"),
                "preset_id": preset_id,
                "synthesized": _boolish(agent.get("synthesized")),
                "selection_reason": selection_reason,
                "attached_skill_ids": attached_skill_ids,
                "context_pack_id": agent.get("context_pack_id"),
                "runtime_status": agent.get("runtime_status"),
                "authority_profile_id": extract_authority_profile_id(agent),
            }
        )

    synthesized_count = sum(1 for item in items if bool(item.get("synthesized")))
    preset_count = sum(1 for item in items if str(item.get("preset_id") or "").strip())
    return {
        "items": items,
        "count": len(items),
        "preset_count": preset_count,
        "synthesized_count": synthesized_count,
    }


def build_why_this_team_projection(
    *,
    team_view: dict[str, Any],
    runtime_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = runtime_snapshot or {}
    slot_reasons: list[dict[str, Any]] = []
    for slot in list(((snapshot.get("team_plan") or {}).get("slots") or [])):
        if not isinstance(slot, dict):
            continue
        reason = _clean_text(slot.get("selection_reason") or slot.get("selectionReason") or slot.get("reason"))
        if not reason:
            continue
        slot_reasons.append(
            {
                "slot_id": slot.get("slot_id") or slot.get("slotId") or slot.get("id"),
                "role_id": slot.get("role_id") or slot.get("roleId"),
                "display_label": slot.get("display_label") or slot.get("displayLabel") or slot.get("label") or slot.get("name"),
                "reason": reason,
            }
        )

    agent_reasons = [
        {
            "runtime_instance_id": item.get("runtime_instance_id"),
            "display_label": item.get("display_label"),
            "reason": item.get("selection_reason"),
        }
        for item in list(team_view.get("items") or [])
        if _clean_text(item.get("selection_reason"))
    ]
    explanations = list(snapshot.get("selection_explanations") or [])
    return {
        "selection_explanations": explanations,
        "slot_reasons": slot_reasons,
        "agent_reasons": agent_reasons,
        "conversation_preferences": snapshot.get("conversation_preferences"),
        "preset_count": int(team_view.get("preset_count") or 0),
        "synthesized_count": int(team_view.get("synthesized_count") or 0),
    }


def build_orchestration_projection(runtime_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    snapshot = runtime_snapshot or {}
    team_plan = snapshot.get("team_plan") or {}
    raw_supervisor_runtime = team_plan.get("supervisor_runtime") or {}
    supervisor_runtime = dict(raw_supervisor_runtime) if isinstance(raw_supervisor_runtime, dict) else {}
    execution_graph = snapshot.get("execution_graph") or {}
    parallel_groups = list(execution_graph.get("parallel_groups") or [])
    sequential_after = dict(execution_graph.get("sequential_after") or {})
    supervisor_edges = list(execution_graph.get("supervisor_edges") or [])
    interaction_mode = _clean_text(
        _first_present_value(
            supervisor_runtime,
            ("interaction_mode", "interactionMode", "mode", "kind", "strategy"),
        )
    )
    has_explicit_enabled = any(key in supervisor_runtime for key in ("enabled", "is_enabled", "isEnabled"))
    supervisor_enabled = (
        _boolish(_first_present_value(supervisor_runtime, ("enabled", "is_enabled", "isEnabled")))
        if has_explicit_enabled
        else bool(interaction_mode or supervisor_runtime.get("instance_id") or supervisor_edges)
    )
    instance_id = _clean_text(
        _first_present_value(
            supervisor_runtime,
            ("instance_id", "runtime_instance_id", "runtimeInstanceId", "id"),
        )
    )
    authority_profile_id = extract_authority_profile_id(supervisor_runtime)
    user_visible = None
    if any(key in supervisor_runtime for key in ("user_visible", "userVisible", "visible")):
        user_visible = _boolish(
            _first_present_value(supervisor_runtime, ("user_visible", "userVisible", "visible"))
        )

    normalized_supervisor_runtime = dict(supervisor_runtime)
    if interaction_mode:
        normalized_supervisor_runtime["interaction_mode"] = interaction_mode
        normalized_supervisor_runtime.setdefault("mode", interaction_mode)
    if instance_id:
        normalized_supervisor_runtime["instance_id"] = instance_id
    if authority_profile_id:
        normalized_supervisor_runtime["authority_profile_id"] = authority_profile_id
    normalized_supervisor_runtime["enabled"] = supervisor_enabled
    if user_visible is not None:
        normalized_supervisor_runtime["user_visible"] = user_visible

    mode = _clean_text(
        team_plan.get("mode")
        or execution_graph.get("mode")
        or interaction_mode
    )
    if not mode:
        if parallel_groups:
            mode = "parallel"
        elif sequential_after:
            mode = "sequential"
        else:
            mode = "runtime_managed"

    checkpoints = [item for item in list(snapshot.get("checkpoints") or []) if isinstance(item, dict)]
    checkpoint_status_counts: dict[str, int] = {}
    for checkpoint in checkpoints:
        status = _clean_text(checkpoint.get("status")) or "pending"
        checkpoint_status_counts[status] = checkpoint_status_counts.get(status, 0) + 1

    return {
        "mode": mode,
        "parallel_groups": parallel_groups,
        "sequential_after": sequential_after,
        "supervisor_runtime": normalized_supervisor_runtime,
        "supervisor_mode": interaction_mode,
        "supervisor_enabled": supervisor_enabled,
        "supervisor_edges": supervisor_edges,
        "checkpoint_count": len(checkpoints),
        "checkpoint_status_counts": checkpoint_status_counts,
        "parallel_group_count": len(parallel_groups),
        "sequential_dependency_count": len(sequential_after),
        "supervisor_edge_count": len(supervisor_edges),
    }


def build_collaboration_projection(
    *,
    runtime_snapshot: dict[str, Any] | None,
    team_view: dict[str, Any],
) -> dict[str, Any]:
    snapshot = runtime_snapshot or {}
    labels_by_instance = {
        str(item.get("runtime_instance_id") or ""): item.get("display_label")
        for item in list(team_view.get("items") or [])
        if isinstance(item, dict) and str(item.get("runtime_instance_id") or "").strip()
    }
    items: list[dict[str, Any]] = []
    counts: dict[str, int] = {}

    for raw in list(snapshot.get("collaboration_cells") or []):
        if not isinstance(raw, dict):
            continue
        kind = _clean_text(_first_present_value(raw, ("pattern", "kind", "type", "mode"))) or "collaboration"
        member_instance_ids = _clean_list_of_text(
            _first_present_value(
                raw,
                (
                    "member_instance_ids",
                    "memberInstanceIds",
                    "runtime_instance_ids",
                    "runtimeInstanceIds",
                    "members",
                    "participants",
                    "agents",
                ),
            ),
            limit=24,
        )
        member_labels = [
            labels_by_instance.get(member_id)
            for member_id in member_instance_ids
            if labels_by_instance.get(member_id)
        ]
        fallback_member_labels = _clean_list_of_text(
            _first_present_value(raw, ("member_labels", "memberLabels")),
            limit=24,
        )
        if not member_labels and fallback_member_labels:
            member_labels = fallback_member_labels
        report_back_to_instance_id = _clean_text(
            _first_present_value(
                raw,
                (
                    "report_back_to_instance_id",
                    "reportBackToInstanceId",
                    "report_to_instance_id",
                    "reportToInstanceId",
                ),
            )
        )
        termination = _clean_text(
            _first_present_value(raw, ("termination", "termination_rule", "terminationRule"))
        )
        items.append(
            {
                "cell_id": raw.get("cell_id") or raw.get("id"),
                "kind": kind,
                "pattern": kind,
                "display_label": raw.get("display_label") or raw.get("displayLabel") or raw.get("label") or raw.get("name"),
                "member_instance_ids": member_instance_ids,
                "member_labels": member_labels,
                "topology": _clean_text(raw.get("topology")),
                "max_rounds": _intish(_first_present_value(raw, ("max_rounds", "maxRounds", "rounds"))),
                "termination": termination,
                "termination_rule": termination,
                "report_back_to_instance_id": report_back_to_instance_id,
                "report_back_to_label": labels_by_instance.get(report_back_to_instance_id or ""),
                "decision_mode": _clean_text(raw.get("decision_mode") or raw.get("decisionMode")),
                "selection_reason": _clean_text(raw.get("selection_reason") or raw.get("selectionReason") or raw.get("reason")),
            }
        )
        counts[kind] = counts.get(kind, 0) + 1

    return {
        "items": items,
        "counts": counts,
        "count": len(items),
    }


def build_checkpoints_projection(runtime_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    snapshot = runtime_snapshot or {}
    items: list[dict[str, Any]] = []
    human_interrupts = 0
    approvals_required = 0
    blocking = 0

    for raw in list(snapshot.get("checkpoints") or []):
        if not isinstance(raw, dict):
            continue
        kind = _clean_text(raw.get("kind") or raw.get("type") or raw.get("mode")) or "checkpoint"
        needs_human = _boolish(
            _first_present_value(
                raw,
                (
                    "human_interrupt_allowed",
                    "humanInterruptAllowed",
                    "requires_human",
                    "requiresHuman",
                    "human_interrupt",
                    "humanInterrupt",
                ),
            )
        )
        approval = _boolish(
            _first_present_value(
                raw,
                ("approval_required", "approvalRequired", "requires_approval", "requiresApproval"),
            )
        )
        is_blocking = _boolish(raw.get("blocking") or raw.get("is_blocking") or raw.get("isBlocking"))
        trigger_after_instances = _clean_list_of_text(
            _first_present_value(raw, ("trigger_after_instances", "triggerAfterInstances", "after_instances", "afterInstances")),
            limit=24,
        )
        supervisor_decision = _clean_text(
            _first_present_value(raw, ("supervisor_decision", "supervisorDecision", "decision"))
        )
        completion_signal = _clean_text(
            _first_present_value(raw, ("completion_signal", "completionSignal", "completion"))
        )
        if needs_human:
            human_interrupts += 1
        if approval:
            approvals_required += 1
        if is_blocking:
            blocking += 1
        items.append(
            {
                "checkpoint_id": raw.get("checkpoint_id") or raw.get("id"),
                "kind": kind,
                "label": raw.get("label") or raw.get("title") or raw.get("name"),
                "stage": _clean_text(raw.get("stage")),
                "status": _clean_text(raw.get("status")) or "pending",
                "human_interrupt_allowed": needs_human,
                "requires_human": needs_human,
                "approval_required": approval,
                "requires_approval": approval,
                "blocking": is_blocking,
                "trigger_after_instances": trigger_after_instances,
                "supervisor_decision": supervisor_decision,
                "completion_signal": completion_signal,
                "selection_reason": _clean_text(raw.get("selection_reason") or raw.get("reason")),
            }
        )

    return {
        "items": items,
        "counts": {
            "total": len(items),
            "human_interrupts": human_interrupts,
            "approval_required": approvals_required,
            "blocking": blocking,
        },
    }


def build_skill_lineage_projection(
    *,
    runtime_agents: list[dict[str, Any]],
    context_packs: list[dict[str, Any]],
    usage_events: list[dict[str, Any]],
    nodes: Iterable[Any],
    edges: Iterable[Any],
) -> dict[str, Any]:
    role_skill_links: list[dict[str, Any]] = []
    for agent in runtime_agents:
        for attached in list(agent.get("attached_skills") or []):
            role_skill_links.append(
                {
                    "runtime_instance_id": agent.get("runtime_instance_id"),
                    "role_label": agent.get("role_label"),
                    "skill_id": attached.get("skill_id"),
                    "skill_name": attached.get("skill_name"),
                    "load_level": attached.get("load_level"),
                    "selected_by": attached.get("selected_by"),
                    "selection_reason": attached.get("selection_reason"),
                }
            )

    skill_context_links: list[dict[str, Any]] = []
    for pack in context_packs:
        for skill_item in list(pack.get("skill_items") or []):
            skill_context_links.append(
                {
                    "context_pack_id": pack.get("context_pack_id"),
                    "target_runtime_agent_instance_id": pack.get("target_runtime_agent_instance_id"),
                    "scope": pack.get("scope"),
                    "skill_id": skill_item.get("skill_id"),
                    "load_level": skill_item.get("load_level"),
                    "count": skill_item.get("count"),
                }
            )

    nodes_by_id = {str(getattr(node, "id", "")): node for node in nodes}
    outgoing: dict[str, list[Any]] = {}
    for edge in edges:
        src = str(getattr(edge, "from_id", "") or "")
        outgoing.setdefault(src, []).append(edge)

    skill_evidence_links: list[dict[str, Any]] = []
    for event in usage_events:
        skill_id = str(event.get("skill_id") or "").strip()
        event_node_id = str(event.get("node_id") or "").strip()
        if not skill_id or not event_node_id:
            continue

        for edge in outgoing.get(event_node_id, []):
            target_id = str(getattr(edge, "to_id", "") or "")
            target_node = nodes_by_id.get(target_id)
            if not target_node:
                continue
            target_type = str(getattr(target_node, "type", "") or "")
            if target_type not in EVIDENCE_NODE_TYPES:
                continue
            skill_evidence_links.append(
                {
                    "skill_id": skill_id,
                    "event_type": event.get("event_type"),
                    "from_node_id": event_node_id,
                    "to_node_id": target_id,
                    "to_node_type": target_type,
                    "edge_type": str(getattr(edge, "type", "") or ""),
                }
            )

    return {
        "role_skill_links": role_skill_links[:180],
        "skill_context_links": skill_context_links[:220],
        "skill_evidence_links": skill_evidence_links[:260],
        "counts": {
            "role_skill_links": len(role_skill_links),
            "skill_context_links": len(skill_context_links),
            "skill_evidence_links": len(skill_evidence_links),
        },
    }


@dataclass(slots=True)
class ResolvedRuntimeScope:
    requested_run_id: str | None
    run_id: str | None
    nodes: list[Any]
    scope: dict[str, Any]


@dataclass(slots=True)
class ResolvedConversationTeam:
    conversation_id: str | None
    snapshot_node_id: str | None
    snapshot_node_type: str | None
    snapshot_source_key: str | None
    snapshot_source_path: str | None
    items: list[dict[str, Any]]
    skill_packages: list[dict[str, Any]]
    active_count: int
    updated_at: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "snapshot_node_id": self.snapshot_node_id,
            "snapshot_node_type": self.snapshot_node_type,
            "snapshot_source_key": self.snapshot_source_key,
            "snapshot_source_path": self.snapshot_source_path,
            "items": list(self.items),
            "skill_packages": list(self.skill_packages),
            "active_count": self.active_count,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class ResolvedRunCapabilities:
    run_id: str | None
    runtime_agents: list[dict[str, Any]]
    attached_skills: list[dict[str, Any]]
    skill_packages: list[dict[str, Any]]
    context_packs: list[dict[str, Any]]
    skill_usage: list[dict[str, Any]]
    lineage: dict[str, Any]
    task_interpretation: dict[str, Any] | None
    team_view: dict[str, Any]
    why_this_team: dict[str, Any]
    orchestration: dict[str, Any]
    collaboration: dict[str, Any]
    authority_projection: dict[str, Any]
    checkpoints_projection: dict[str, Any]
    counts: dict[str, int]
    updated_at: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "runtime_agents": list(self.runtime_agents),
            "attached_skills": list(self.attached_skills),
            "skill_packages": list(self.skill_packages),
            "context_packs": list(self.context_packs),
            "skill_usage": list(self.skill_usage),
            "lineage": dict(self.lineage),
            "task_interpretation": dict(self.task_interpretation) if self.task_interpretation else None,
            "team_view": dict(self.team_view),
            "why_this_team": dict(self.why_this_team),
            "orchestration": dict(self.orchestration),
            "collaboration": dict(self.collaboration),
            "authority": dict(self.authority_projection),
            "checkpoints": dict(self.checkpoints_projection),
            "counts": dict(self.counts),
            "updated_at": self.updated_at,
        }

    def context_pack_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "items": list(self.context_packs),
            "count": len(self.context_packs),
            "updated_at": self.updated_at,
        }

    def skill_usage_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "items": list(self.skill_usage),
            "count": len(self.skill_usage),
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class ResolvedRuntimeProjection:
    scope: ResolvedRuntimeScope
    authority: dict[str, Any]
    planning_boundary: dict[str, Any]
    capabilities: ResolvedRunCapabilities | None = None
    conversation_team: ResolvedConversationTeam | None = None

    @property
    def run_id(self) -> str | None:
        return self.scope.run_id

    def apply_authority(self, payload: dict[str, Any]) -> dict[str, Any]:
        return apply_runtime_authority(payload, self.authority)

    def capability_payload(self) -> dict[str, Any]:
        payload = self.capabilities.as_payload() if self.capabilities else {
            "run_id": self.run_id,
            "runtime_agents": [],
            "attached_skills": [],
            "skill_packages": [],
            "context_packs": [],
            "skill_usage": [],
            "lineage": {
                "role_skill_links": [],
                "skill_context_links": [],
                "skill_evidence_links": [],
                "counts": {
                    "role_skill_links": 0,
                    "skill_context_links": 0,
                    "skill_evidence_links": 0,
                },
            },
            "task_interpretation": None,
            "team_view": {
                "items": [],
                "count": 0,
                "preset_count": 0,
                "synthesized_count": 0,
            },
            "why_this_team": {
                "selection_explanations": [],
                "slot_reasons": [],
                "agent_reasons": [],
                "conversation_preferences": None,
                "preset_count": 0,
                "synthesized_count": 0,
            },
            "orchestration": {
                "mode": "runtime_managed",
                "parallel_groups": [],
                "sequential_after": {},
                "supervisor_runtime": {},
                "supervisor_mode": None,
                "supervisor_edges": [],
                "parallel_group_count": 0,
                "sequential_dependency_count": 0,
                "supervisor_edge_count": 0,
            },
            "collaboration": {
                "items": [],
                "counts": {},
                "count": 0,
            },
            "authority": {
                "items": [],
                "graph": [],
                "count": 0,
                "graph_count": 0,
            },
            "checkpoints": {
                "items": [],
                "counts": {
                    "total": 0,
                    "human_interrupts": 0,
                    "approval_required": 0,
                    "blocking": 0,
                },
            },
            "counts": {
                "runtime_agents": 0,
                "attached_skills": 0,
                "skill_packages": 0,
                "context_packs": 0,
                "skill_usage": 0,
                "team_view": 0,
                "collaboration": 0,
                "authority": 0,
                "checkpoints": 0,
            },
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        payload = self.apply_authority(payload)
        payload["planning_boundary"] = dict(self.planning_boundary)
        return payload

    def context_pack_payload(self) -> dict[str, Any]:
        payload = self.capabilities.context_pack_payload() if self.capabilities else {
            "run_id": self.run_id,
            "items": [],
            "count": 0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        payload = self.apply_authority(payload)
        payload["planning_boundary"] = dict(self.planning_boundary)
        return payload

    def skill_usage_payload(self) -> dict[str, Any]:
        payload = self.capabilities.skill_usage_payload() if self.capabilities else {
            "run_id": self.run_id,
            "items": [],
            "count": 0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        payload = self.apply_authority(payload)
        payload["planning_boundary"] = dict(self.planning_boundary)
        return payload

    def conversation_team_payload(self) -> dict[str, Any]:
        payload = self.conversation_team.as_payload() if self.conversation_team else {
            "conversation_id": None,
            "snapshot_node_id": None,
            "snapshot_node_type": None,
            "snapshot_source_key": None,
            "snapshot_source_path": None,
            "items": [],
            "skill_packages": [],
            "active_count": 0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return self.apply_authority(payload)


def resolve_runtime_scope_state(
    *,
    nodes: Iterable[Any],
    edges: Iterable[Any],
    run_id: str | None = None,
) -> ResolvedRuntimeScope:
    nodes_list = list(nodes)
    edges_list = list(edges)
    scoped = resolve_run_scoped_nodes(nodes=nodes_list, edges=edges_list, run_id=run_id)
    return ResolvedRuntimeScope(
        requested_run_id=_clean_text(run_id),
        run_id=_clean_text(scoped.get("run_id")),
        nodes=list(scoped.get("nodes") or []),
        scope=dict(scoped.get("scope") or {}),
    )


def resolve_conversation_team(
    session: Session,
    *,
    thread_id: str,
    nodes: Iterable[Any],
) -> ResolvedConversationTeam:
    nodes_list = list(nodes)
    conversation = session.exec(
        select(Conversation)
        .where(Conversation.thread_id == thread_id)
        .limit(1)
    ).first()
    step_activity_by_agent = _step_activity_index(nodes_list)
    step_activity_sources_by_agent = _step_activity_source_index(nodes_list)
    skill_registry = build_skill_registry(nodes=nodes_list, include_defaults=True)

    runtime_snapshot = extract_runtime_team_snapshot(nodes_list)
    if runtime_snapshot and list(runtime_snapshot.get("members") or []):
        runtime_source_path = str(runtime_snapshot.get("source_key") or "")
        runtime_source_key = _normalize_runtime_source_key(runtime_source_path)
        runtime_items: list[dict[str, Any]] = []
        for raw_member in runtime_snapshot.get("members", []):
            if not isinstance(raw_member, dict):
                continue
            llm_block = raw_member.get("llm")
            llm_info = llm_block if isinstance(llm_block, dict) else {}
            runtime_instance_id = _clean_text(raw_member.get("runtime_instance_id") or raw_member.get("instance_id"))
            agent_id = _clean_text(raw_member.get("agent_id") or raw_member.get("id") or raw_member.get("agent"))
            template_id = _clean_text(
                raw_member.get("template_id")
                or raw_member.get("agent_template_id")
                or raw_member.get("template")
            )
            lookup_keys = [key for key in [runtime_instance_id, agent_id, template_id] if key]
            status_counts: dict[str, int] = {}
            for key in lookup_keys:
                source_counts = step_activity_by_agent.get(key, {})
                for status_key, count in source_counts.items():
                    status_counts[status_key] = status_counts.get(status_key, 0) + int(count)

            attached_skills = extract_attached_skills(raw_member, skill_lookup=skill_registry)
            context_pack_id = _clean_text(raw_member.get("context_pack_id") or raw_member.get("contextPackId"))
            if not context_pack_id:
                member_pack = raw_member.get("context_pack") or raw_member.get("contextPack")
                if isinstance(member_pack, dict):
                    context_pack_id = _clean_text(
                        member_pack.get("context_pack_id")
                        or member_pack.get("contextPackId")
                        or member_pack.get("id")
                    )

            runtime_items.append(
                {
                    "agent_id": agent_id or runtime_instance_id or template_id or "unknown-runtime-agent",
                    "runtime_instance_id": runtime_instance_id,
                    "instance_id": runtime_instance_id,
                    "name": _clean_text(
                        raw_member.get("name")
                        or raw_member.get("display_label")
                        or raw_member.get("displayLabel")
                        or raw_member.get("display_name")
                        or raw_member.get("label")
                        or agent_id
                        or runtime_instance_id
                    ),
                    "display_label": _clean_text(
                        raw_member.get("display_label")
                        or raw_member.get("displayLabel")
                        or raw_member.get("display_name")
                        or raw_member.get("label")
                        or raw_member.get("name")
                    ),
                    "slot_id": _clean_text(raw_member.get("slot_id") or raw_member.get("slotId")),
                    "role_id": _clean_text(raw_member.get("role_id") or raw_member.get("roleId")),
                    "role_label": _clean_text(raw_member.get("role_label") or raw_member.get("role") or raw_member.get("title")),
                    "template_id": template_id,
                    "preset_id": _clean_text(raw_member.get("preset_id") or raw_member.get("presetId")),
                    "authority_profile_id": extract_authority_profile_id(raw_member),
                    "provider": _clean_text(raw_member.get("provider") or raw_member.get("llm_provider") or llm_info.get("provider")),
                    "model": _clean_text(raw_member.get("model") or raw_member.get("model_name") or llm_info.get("model")),
                    "runtime_status": (
                        _normalize_status(raw_member.get("runtime_status") or raw_member.get("status") or raw_member.get("state"))
                        if (
                            raw_member.get("runtime_status") is not None
                            or raw_member.get("status") is not None
                            or raw_member.get("state") is not None
                        )
                        else _runtime_status_from_counts(status_counts)
                    ),
                    "status_counts": status_counts,
                    "source": "runtime_snapshot",
                    "source_key": runtime_source_key,
                    "source_path": runtime_source_path or None,
                    "snapshot_node_id": runtime_snapshot.get("node_id"),
                    "snapshot_node_type": runtime_snapshot.get("node_type"),
                    "enabled": bool(raw_member.get("enabled", True)),
                    "responsibilities": _clean_list_of_text(raw_member.get("responsibilities") or raw_member.get("responsibility")),
                    "capability_tags": _clean_list_of_text(raw_member.get("capability_tags") or raw_member.get("capabilities")),
                    "ephemeral": bool(raw_member.get("ephemeral") or raw_member.get("transient") or False),
                    "synthesized": _boolish(raw_member.get("synthesized")),
                    "selection_reason": _clean_text(raw_member.get("selection_reason") or raw_member.get("selectionReason")),
                    "attached_skills": attached_skills,
                    "attached_skill_ids": [
                        str(item.get("skill_id") or "").strip()
                        for item in attached_skills
                        if str(item.get("skill_id") or "").strip()
                    ],
                    "context_pack_id": context_pack_id,
                }
            )

        updated_at = datetime.now(timezone.utc).isoformat()
        return ResolvedConversationTeam(
            conversation_id=getattr(conversation, "id", None),
            snapshot_node_id=runtime_snapshot.get("node_id"),
            snapshot_node_type=runtime_snapshot.get("node_type"),
            snapshot_source_key=runtime_source_key,
            snapshot_source_path=runtime_source_path or None,
            items=runtime_items,
            skill_packages=_skill_packages_for_team_items(team_items=runtime_items, skill_registry=skill_registry),
            active_count=sum(1 for item in runtime_items if item["runtime_status"] in {"running", "queued"}),
            updated_at=updated_at,
        )

    if not conversation:
        inferred_items: list[dict[str, Any]] = []
        for agent_id in sorted(step_activity_by_agent.keys()):
            status_counts = step_activity_by_agent.get(agent_id, {})
            inferred_items.append(
                {
                    "agent_id": agent_id,
                    "name": agent_id,
                    "runtime_instance_id": None,
                    "role_label": None,
                    "template_id": None,
                    "provider": None,
                    "model": None,
                    "enabled": True,
                    "order_index": None,
                    "runtime_status": _runtime_status_from_counts(status_counts),
                    "status_counts": status_counts,
                    "responsibilities": [],
                    "capability_tags": [],
                    "ephemeral": False,
                    "source": "inferred_from_steps",
                    "source_key": _preferred_step_source_key(step_activity_sources_by_agent.get(agent_id)),
                    "attached_skills": [],
                    "context_pack_id": None,
                }
            )

        updated_at = datetime.now(timezone.utc).isoformat()
        return ResolvedConversationTeam(
            conversation_id=None,
            snapshot_node_id=None,
            snapshot_node_type=None,
            snapshot_source_key=None,
            snapshot_source_path=None,
            items=inferred_items,
            skill_packages=[],
            active_count=sum(1 for item in inferred_items if item["runtime_status"] in {"running", "queued"}),
            updated_at=updated_at,
        )

    memberships = session.exec(
        select(ConversationAgent)
        .where(ConversationAgent.conversation_id == conversation.id)
        .order_by(ConversationAgent.order_index.asc(), ConversationAgent.created_at.asc(), ConversationAgent.id.asc())
    ).all()
    agent_ids = [row.agent_id for row in memberships]
    agents = session.exec(select(Agent).where(Agent.id.in_(agent_ids))).all() if agent_ids else []
    agents_by_id = {agent.id: agent for agent in agents}

    items: list[dict[str, Any]] = []
    for membership in memberships:
        agent = agents_by_id.get(membership.agent_id)
        overrides = _jload(membership.overrides_json, {})
        if not isinstance(overrides, dict):
            overrides = {}

        status_counts = step_activity_by_agent.get(membership.agent_id, {})
        if not status_counts and agent:
            status_counts = step_activity_by_agent.get(agent.name, {})

        raw_responsibilities = overrides.get("responsibilities") or overrides.get("responsibility") or []
        responsibilities: list[str] = []
        if isinstance(raw_responsibilities, str):
            clean = raw_responsibilities.strip()
            if clean:
                responsibilities = [clean]
        elif isinstance(raw_responsibilities, list):
            responsibilities = [str(item).strip() for item in raw_responsibilities if str(item).strip()]

        capability_tags = _clean_list_of_text(overrides.get("capability_tags") or overrides.get("capabilities"))
        if not capability_tags and agent:
            capability_tags = _clean_list_of_text(_jload(getattr(agent, "tools_json", "[]"), []))

        items.append(
            {
                "membership_id": membership.id,
                "agent_id": membership.agent_id,
                "name": agent.name if agent else membership.agent_id,
                "runtime_instance_id": None,
                "role_label": _clean_text(
                    overrides.get("role_label")
                    or overrides.get("role")
                    or overrides.get("title")
                    or (agent.name if agent else None)
                ),
                "template_id": _clean_text(overrides.get("template_id") or overrides.get("agent_template_id")),
                "provider": _clean_text(overrides.get("provider") or overrides.get("llm_provider")),
                "enabled": bool(membership.enabled),
                "order_index": int(membership.order_index),
                "runtime_status": _runtime_status_from_counts(status_counts),
                "status_counts": status_counts,
                "responsibilities": responsibilities,
                "capability_tags": capability_tags,
                "ephemeral": bool(overrides.get("ephemeral") or False),
                "description": agent.description if agent else "",
                "model": agent.model if agent else "",
                "visibility": agent.visibility if agent else "",
                "source": "conversation_membership",
                "source_key": "conversation_agents",
                "attached_skills": extract_attached_skills(overrides, skill_lookup=skill_registry),
                "context_pack_id": _clean_text(overrides.get("context_pack_id") or overrides.get("contextPackId")),
            }
        )

    updated_at = datetime.now(timezone.utc).isoformat()
    return ResolvedConversationTeam(
        conversation_id=conversation.id,
        snapshot_node_id=None,
        snapshot_node_type=None,
        snapshot_source_key=None,
        snapshot_source_path=None,
        items=items,
        skill_packages=_skill_packages_for_team_items(team_items=items, skill_registry=skill_registry),
        active_count=sum(1 for item in items if item["runtime_status"] in {"running", "queued"}),
        updated_at=updated_at,
    )


def resolve_run_capabilities(
    *,
    nodes: Iterable[Any],
    edges: Iterable[Any],
    run_id: str | None = None,
    scope: ResolvedRuntimeScope | None = None,
) -> ResolvedRunCapabilities:
    nodes_list = list(nodes)
    edges_list = list(edges)
    scope_state = scope or resolve_runtime_scope_state(nodes=nodes_list, edges=edges_list, run_id=run_id)
    scoped_nodes = list(scope_state.nodes)

    registry = build_skill_registry(nodes=nodes_list, include_defaults=True)
    runtime_snapshot = extract_runtime_team_snapshot(scoped_nodes) or {}
    runtime_projection = extract_runtime_agents_with_skills(scoped_nodes, skill_lookup=registry)
    runtime_agents = list(runtime_projection.get("items") or [])
    context_packs = extract_context_pack_summaries(scoped_nodes)
    usage_events = extract_skill_usage_events(scoped_nodes, skill_lookup=registry)
    attached_skill_summaries = aggregate_attached_skills(runtime_agents)
    team_view = build_team_view_projection(runtime_agents=runtime_agents, runtime_snapshot=runtime_snapshot)
    why_this_team = build_why_this_team_projection(team_view=team_view, runtime_snapshot=runtime_snapshot)
    orchestration = build_orchestration_projection(runtime_snapshot)
    collaboration = build_collaboration_projection(runtime_snapshot=runtime_snapshot, team_view=team_view)
    authority_projection = build_runtime_authority_projection(
        runtime_agents=runtime_agents,
        authority_graph=list(runtime_snapshot.get("authority_graph") or []),
    )
    checkpoints_projection = build_checkpoints_projection(runtime_snapshot)

    referenced_skill_ids: set[str] = set()
    for item in attached_skill_summaries:
        skill_id = str(item.get("skill_id") or "").strip()
        if skill_id:
            referenced_skill_ids.add(skill_id)
    for event in usage_events:
        skill_id = str(event.get("skill_id") or "").strip()
        if skill_id:
            referenced_skill_ids.add(skill_id)
    for pack in context_packs:
        for skill_item in list(pack.get("skill_items") or []):
            skill_id = str(skill_item.get("skill_id") or "").strip()
            if skill_id:
                referenced_skill_ids.add(skill_id)

    # This remains a projection of observed/runtime-referenced packages, not execution authority.
    skill_packages = sorted(
        [registry[skill_id] for skill_id in referenced_skill_ids if skill_id in registry],
        key=lambda item: (str(item.get("name") or "").lower(), str(item.get("id") or "")),
    )

    lineage = build_skill_lineage_projection(
        runtime_agents=runtime_agents,
        context_packs=context_packs,
        usage_events=usage_events,
        nodes=scoped_nodes,
        edges=edges_list,
    )
    updated_at = datetime.now(timezone.utc).isoformat()
    return ResolvedRunCapabilities(
        run_id=scope_state.run_id,
        runtime_agents=runtime_agents,
        attached_skills=attached_skill_summaries,
        skill_packages=skill_packages,
        context_packs=context_packs,
        skill_usage=usage_events,
        lineage=lineage,
        task_interpretation=runtime_snapshot.get("task_interpretation"),
        team_view=team_view,
        why_this_team=why_this_team,
        orchestration=orchestration,
        collaboration=collaboration,
        authority_projection=authority_projection,
        checkpoints_projection=checkpoints_projection,
        counts={
            "runtime_agents": len(runtime_agents),
            "attached_skills": len(attached_skill_summaries),
            "skill_packages": len(skill_packages),
            "context_packs": len(context_packs),
            "skill_usage": len(usage_events),
            "team_view": int(team_view.get("count") or 0),
            "collaboration": int(collaboration.get("count") or 0),
            "authority": int(authority_projection.get("count") or 0),
            "checkpoints": int((checkpoints_projection.get("counts") or {}).get("total") or 0),
        },
        updated_at=updated_at,
    )


def resolve_runtime_projection(
    *,
    nodes: Iterable[Any],
    edges: Iterable[Any],
    run_id: str | None = None,
    session: Session | None = None,
    thread_id: str | None = None,
    team_nodes: Iterable[Any] | None = None,
    scope: ResolvedRuntimeScope | None = None,
    capabilities: ResolvedRunCapabilities | None = None,
    conversation_team: ResolvedConversationTeam | None = None,
    include_capabilities: bool = True,
    include_conversation_team: bool = False,
    context_source_default: str | None = None,
    plan_source_default: str | None = None,
    mode_default: str | None = None,
) -> ResolvedRuntimeProjection:
    nodes_list = list(nodes)
    edges_list = list(edges)
    scope_state = scope or resolve_runtime_scope_state(nodes=nodes_list, edges=edges_list, run_id=run_id)

    capability_state = capabilities
    if include_capabilities and capability_state is None:
        capability_state = resolve_run_capabilities(
            nodes=nodes_list,
            edges=edges_list,
            run_id=run_id,
            scope=scope_state,
        )

    team_state = conversation_team
    should_resolve_team = include_conversation_team or team_state is not None
    if should_resolve_team and team_state is None and session is not None and thread_id:
        team_state = resolve_conversation_team(
            session,
            thread_id=thread_id,
            nodes=list(team_nodes) if team_nodes is not None else nodes_list,
        )

    # All runtime-facing projections should consume the same normalized ddalggak -> GoC authority contract here.
    authority = derive_runtime_authority(
        nodes=scope_state.nodes,
        agent_team=team_state.as_payload() if team_state else None,
        skill_packages=capability_state.skill_packages if capability_state else [],
        runtime_agents=capability_state.runtime_agents if capability_state else [],
        usage_events=capability_state.skill_usage if capability_state else [],
        context_packs=capability_state.context_packs if capability_state else [],
        context_source_default=context_source_default,
        plan_source_default=plan_source_default,
        mode_default=mode_default,
    )
    planning_boundary = build_planning_boundary_projection(
        run_id=scope_state.run_id,
        runtime_authority=authority,
        runtime_snapshot=extract_runtime_team_snapshot(scope_state.nodes) or {},
        capabilities=capability_state.as_payload() if capability_state else None,
    )
    return ResolvedRuntimeProjection(
        scope=scope_state,
        authority=authority,
        planning_boundary=planning_boundary,
        capabilities=capability_state,
        conversation_team=team_state,
    )
