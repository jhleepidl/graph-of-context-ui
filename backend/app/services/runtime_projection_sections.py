from __future__ import annotations

from typing import Any, Iterable

from app.services.runtime_projection_common import (
    EVIDENCE_NODE_TYPES,
    _boolish,
    _clean_list,
    _clean_text,
    _first_present_value,
    _friendly_runtime_label,
    _generic_runtime_label,
    _intish,
    _runtime_status_from_counts,
    _scalar_summary,
    _slot_indexes,
    _skill_packages_for_team_items,
    _step_activity_index,
    _step_activity_source_index,
    _preferred_step_source_key,
    _structured_summary,
    _structured_value,
    _team_view_labels_by_instance,
    aggregate_attached_skills,
    extract_authority_profile_id,
    _clean_list_of_text,
    _created_sort_key,
    _node_payload,
    _normalize_runtime_source_key,
    _normalize_status,
)


def build_team_view_projection(
    *,
    runtime_agents: list[dict[str, Any]],
    runtime_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    slot_by_id, slot_by_role_id = _slot_indexes(runtime_snapshot)
    scope_specs = list((runtime_snapshot or {}).get("scope_specs") or [])
    materialized_by_scope = {
        str(item.get("scope_id") or "").strip(): item
        for item in list((runtime_snapshot or {}).get("materialized_scopes") or [])
        if str(item.get("scope_id") or "").strip()
    }
    items: list[dict[str, Any]] = []

    for agent in runtime_agents:
        slot = slot_by_id.get(str(agent.get("slot_id") or "").strip()) or slot_by_role_id.get(str(agent.get("role_id") or "").strip())
        display_label = _friendly_runtime_label(
            display_label=(
                agent.get("display_label")
                or agent.get("name")
                or (slot or {}).get("display_label")
                or (slot or {}).get("displayLabel")
                or agent.get("role_label")
                or agent.get("runtime_instance_id")
                or agent.get("agent_id")
            ),
            role_id=agent.get("role_id") or (slot or {}).get("role_id") or (slot or {}).get("roleId"),
            slot=slot,
            selection_reason=agent.get("selection_reason") or (slot or {}).get("selection_reason") or (slot or {}).get("selectionReason"),
            synthesized=agent.get("synthesized"),
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
        runtime_instance_id = agent.get("runtime_instance_id") or agent.get("instance_id")
        slot_id = agent.get("slot_id") or (slot or {}).get("slot_id") or (slot or {}).get("slotId")
        scope_spec = next((entry for entry in scope_specs if str(entry.get("target_instance_id") or entry.get("targetInstanceId") or "").strip() == str(runtime_instance_id or "").strip()), None)
        if scope_spec is None and slot_id:
            scope_spec = next((entry for entry in scope_specs if str(entry.get("target_slot_id") or entry.get("targetSlotId") or "").strip() == str(slot_id).strip()), None)
        scope_materialized = materialized_by_scope.get(str((scope_spec or {}).get("scope_id") or "").strip(), {})
        items.append(
            {
                "runtime_instance_id": runtime_instance_id,
                "display_label": display_label,
                "slot_id": slot_id,
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
                "scope_id": (scope_spec or {}).get("scope_id") or (scope_spec or {}).get("scopeId"),
                "visibility_mode": (scope_spec or {}).get("visibility_mode") or (scope_spec or {}).get("visibilityMode"),
                "grant_labels": [key for key, value in dict((scope_spec or {}).get("memory_grants") or (scope_spec or {}).get("memoryGrants") or {}).items() if value is True],
                "scope_token_estimate": (scope_materialized or {}).get("token_estimate"),
                "runtime_status": agent.get("runtime_status"),
                "authority_profile_id": extract_authority_profile_id(agent),
            }
        )

    synthesized_count = sum(1 for item in items if bool(item.get("synthesized")))
    preset_count = sum(1 for item in items if str(item.get("preset_id") or "").strip())
    blueprint_summary = (runtime_snapshot or {}).get("blueprint_summary") if isinstance(runtime_snapshot, dict) else None
    return {
        "items": items,
        "count": len(items),
        "preset_count": preset_count,
        "synthesized_count": synthesized_count,
        "blueprint_summary": blueprint_summary if isinstance(blueprint_summary, dict) else None,
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
        "blueprint_summary": snapshot.get("blueprint_summary") if isinstance(snapshot.get("blueprint_summary"), dict) else None,
    }


def build_orchestration_projection(
    runtime_snapshot: dict[str, Any] | None,
    *,
    team_view: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = runtime_snapshot or {}
    labels_by_instance = _team_view_labels_by_instance(team_view)
    team_plan = snapshot.get("team_plan") or {}
    raw_supervisor_runtime = team_plan.get("supervisor_runtime") or {}
    supervisor_runtime = dict(raw_supervisor_runtime) if isinstance(raw_supervisor_runtime, dict) else {}
    execution_graph = snapshot.get("execution_graph") or {}
    raw_parallel_groups = list(execution_graph.get("parallel_groups") or [])
    sequential_after = dict(execution_graph.get("sequential_after") or {})
    raw_supervisor_edges = list(execution_graph.get("supervisor_edges") or [])
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
        else bool(interaction_mode or supervisor_runtime.get("instance_id") or raw_supervisor_edges)
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
        if raw_parallel_groups:
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

    parallel_groups: list[dict[str, Any]] = []
    for index, raw_group in enumerate(raw_parallel_groups):
        if not isinstance(raw_group, dict):
            continue
        member_instance_ids = _clean_list_of_text(raw_group.get("member_instance_ids"), limit=24)
        member_labels = _clean_list_of_text(raw_group.get("member_labels"), limit=24)
        if not member_labels:
            member_labels = [labels_by_instance.get(member_id) for member_id in member_instance_ids if labels_by_instance.get(member_id)]
        parallel_groups.append(
            {
                **raw_group,
                "group_id": raw_group.get("group_id") or raw_group.get("id") or f"group-{index + 1}",
                "member_instance_ids": member_instance_ids,
                "member_labels": member_labels,
                "label": _clean_text(
                    raw_group.get("label")
                    or raw_group.get("display_label")
                    or raw_group.get("displayLabel")
                    or raw_group.get("name")
                ),
            }
        )

    supervisor_edges: list[dict[str, Any]] = []
    for raw_edge in raw_supervisor_edges:
        if not isinstance(raw_edge, dict):
            continue
        from_id = _clean_text(
            raw_edge.get("from")
            or raw_edge.get("source")
            or raw_edge.get("supervisor_id")
            or raw_edge.get("supervisorId")
        )
        to_id = _clean_text(
            raw_edge.get("to")
            or raw_edge.get("target")
            or raw_edge.get("runtime_instance_id")
            or raw_edge.get("runtimeInstanceId")
        )
        from_label = labels_by_instance.get(from_id or "")
        to_label = labels_by_instance.get(to_id or "")
        edge_summary = None
        if from_id and to_id:
            edge_summary = f"{from_label or from_id} -> {to_label or to_id}"
        supervisor_edges.append(
            {
                **raw_edge,
                "from": from_id,
                "to": to_id,
                "from_label": from_label,
                "to_label": to_label,
                "edge_summary": edge_summary,
            }
        )

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
        termination = _structured_value(
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
                "termination_summary": _structured_summary(termination),
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


def build_checkpoints_projection(
    runtime_snapshot: dict[str, Any] | None,
    *,
    team_view: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = runtime_snapshot or {}
    labels_by_instance = _team_view_labels_by_instance(team_view)
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
        trigger_after_labels = [labels_by_instance.get(instance_id) for instance_id in trigger_after_instances if labels_by_instance.get(instance_id)]
        supervisor_decision = _structured_value(
            _first_present_value(raw, ("supervisor_decision", "supervisorDecision", "decision"))
        )
        completion_signal = _structured_value(
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
                "trigger_after_labels": trigger_after_labels,
                "supervisor_decision": supervisor_decision,
                "supervisor_decision_summary": _structured_summary(supervisor_decision),
                "completion_signal": completion_signal,
                "completion_signal_summary": _structured_summary(completion_signal),
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


