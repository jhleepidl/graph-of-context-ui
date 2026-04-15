from __future__ import annotations

import json
import re
from typing import Any, Iterable

from app.services.runtime_authority import extract_authority_profile_id
from app.services.runtime_snapshot import (
    clean_list_of_text as _clean_list_of_text,
    clean_text as _snapshot_clean_text,
    created_sort_key as _created_sort_key,
    node_payload as _node_payload,
    normalize_runtime_source_key as _normalize_runtime_source_key,
    normalize_status as _normalize_status,
)
from app.services.skill_projections import extract_attached_skills


EVIDENCE_NODE_TYPES = {"Decision", "Assumption", "Plan", "Observation", "ContextSummary", "Artifact", "Resource", "Message"}


def _jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def _clean_text(value: Any) -> str | None:
    clean = str(value or "").strip()
    return clean or None


def _clean_list(value: Any, *, limit: int = 24) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = []
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = _clean_text(item)
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
        if len(out) >= limit:
            break
    return out


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


def _structured_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        clean = value.strip()
        if not clean:
            return None
        if clean.startswith("{") or clean.startswith("["):
            parsed = _jload(clean, None)
            if parsed is not None:
                value = parsed
            else:
                return clean
        else:
            return clean
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return value


def _scalar_summary(value: Any) -> str | None:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return None


def _structured_summary(value: Any) -> str | None:
    normalized = _structured_value(value)
    scalar = _scalar_summary(normalized)
    if scalar is not None:
        return scalar

    if isinstance(normalized, list):
        parts: list[str] = []
        for item in normalized[:3]:
            item_summary = _structured_summary(item)
            if item_summary:
                parts.append(item_summary)
        if parts:
            return ", ".join(parts) + ("..." if len(normalized) > 3 else "")
        return f"{len(normalized)} items" if normalized else None

    if isinstance(normalized, dict):
        for key in ("summary", "label", "name", "title", "description", "message"):
            summary = _scalar_summary(normalized.get(key))
            if summary:
                return summary

        parts: list[str] = []
        for key in ("condition", "decision", "signal", "mode", "status", "type", "kind", "rule", "event", "action"):
            if key not in normalized:
                continue
            item_summary = _structured_summary(normalized.get(key))
            if item_summary:
                parts.append(f"{key}: {item_summary}")
            if len(parts) >= 3:
                break

        if parts:
            return " | ".join(parts)

        for key, raw in normalized.items():
            item_summary = _scalar_summary(raw)
            if item_summary is None and isinstance(raw, (dict, list, tuple)):
                item_summary = _structured_summary(raw)
            if item_summary:
                parts.append(f"{key}: {item_summary}")
            if len(parts) >= 3:
                break

        return " | ".join(parts) if parts else None

    return None


def _title_case_identifier(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[._-]+", " ", text)).strip().title()


def _team_view_labels_by_instance(team_view: dict[str, Any] | None) -> dict[str, str]:
    return {
        str(item.get("runtime_instance_id") or ""): str(item.get("display_label") or "")
        for item in list((team_view or {}).get("items") or [])
        if isinstance(item, dict)
        and str(item.get("runtime_instance_id") or "").strip()
        and str(item.get("display_label") or "").strip()
    }


def _generic_runtime_label(label: Any, role_id: Any = None) -> bool:
    clean_label = _clean_text(label).lower()
    clean_role = (_clean_text(role_id) or '').lower()
    if not clean_label:
        return True
    if clean_role and clean_label in {clean_role, _clean_text(_title_case_identifier(clean_role)).lower()}:
        return True
    return False


def _friendly_runtime_label(*, display_label: Any = None, role_id: Any = None, slot: dict[str, Any] | None = None, selection_reason: Any = None, synthesized: Any = None) -> str | None:
    slot = slot or {}
    label = _clean_text(display_label)
    role = (_clean_text(role_id) or '').lower()
    slot_text = " ".join(
        filter(
            None,
            [
                _clean_text(slot.get("purpose") or slot.get("display_label") or slot.get("displayLabel") or slot.get("label")),
                _clean_text(selection_reason),
            ],
        )
    ).lower()
    if not _boolish(synthesized) and label:
        return label
    if label and not _generic_runtime_label(label, role):
        return label

    def has_any(*patterns: str) -> bool:
        return any(pattern in slot_text for pattern in patterns)

    if role == "researcher":
        if has_any("filing", "dart", "10-k", "10q", "공시"):
            return "DART Financial Researcher" if has_any("investment", "market", "equity", "stock") else "Filing Researcher"
        if has_any("news", "headline", "market"):
            return "Market News Researcher"
        if has_any("evidence", "citation", "claim", "validate"):
            return "Evidence Researcher"
        if has_any("investment", "equity", "stock", "portfolio"):
            return "Investment Researcher"
        return label or "Task Researcher"
    if role == "reviewer":
        if has_any("skeptical", "adversarial", "stress-test", "stress test", "claim", "citation", "evidence"):
            return "Skeptical Claim Reviewer"
        if has_any("regression", "test", "qa"):
            return "Regression Reviewer"
        if has_any("risk", "contradiction"):
            return "Risk Reviewer"
        if has_any("implementation", "code", "patch", "refactor"):
            return "Implementation Reviewer"
        return label or "Reviewer"
    if role == "builder":
        if has_any("notebook"):
            return "Notebook Builder"
        if has_any("patch", "refactor"):
            return "Patch Builder"
        return "Implementation Builder"
    if role == "synthesizer":
        if has_any("investment", "memo"):
            return "Investment Memo Synthesizer"
        if has_any("brief"):
            return "Briefing Synthesizer"
        if has_any("report", "final output", "assemble", "aggregation"):
            return "Report Synthesizer"
        return label or "Synthesizer"
    if role == "operator":
        return "Workflow Operator" if has_any("workflow", "runtime", "tool") else (label or "Operator")
    return label or _title_case_identifier(role) or None


def _configured_team_sections(team_config: dict[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
    payload = team_config if isinstance(team_config, dict) else {}
    sections: list[tuple[str, dict[str, Any]]] = []
    for state in ("active", "pending"):
        team = payload.get(f"{state}_team")
        if isinstance(team, dict) and team:
            sections.append((state, team))
    return sections


def _configured_scope_id(state: str, agent_id: str, index: int) -> str:
    clean_state = _clean_text(state) or "configured"
    clean_agent_id = _clean_text(agent_id) or f"agent_{index + 1}"
    return f"{clean_state}_scope_{re.sub(r'[^a-zA-Z0-9_]+', '_', clean_agent_id)}_{index + 1}"



def _configured_runtime_instance_id(state: str, agent_id: str, index: int) -> str:
    clean_state = _clean_text(state) or "configured"
    clean_agent_id = _clean_text(agent_id) or f"agent_{index + 1}"
    return f"{clean_state}_team_{re.sub(r'[^a-zA-Z0-9_]+', '_', clean_agent_id)}_{index + 1}"



def _build_configured_team_projection(
    *,
    team_config: dict[str, Any] | None,
    skill_registry: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    configured_items: list[dict[str, Any]] = []
    configured_scope_items: list[dict[str, Any]] = []

    for state, team in _configured_team_sections(team_config):
        team_name = _clean_text(team.get("team_name") or team.get("name"))
        composition_mode = _clean_text(team.get("composition_mode") or team.get("compositionMode"))
        proposal_mode = _clean_text(team.get("proposal_mode") or team.get("proposalMode"))
        shortcut_policy = team.get("shortcut_policy") or team.get("shortcutPolicy") or {}
        shortcut_enabled = None
        shortcut_max_recent_turns = None
        if isinstance(shortcut_policy, dict):
            if "enabled" in shortcut_policy:
                shortcut_enabled = _boolish(shortcut_policy.get("enabled"))
            shortcut_max_recent_turns = _intish(
                shortcut_policy.get("max_recent_turns") or shortcut_policy.get("maxRecentTurns")
            )

        interaction_spec = team.get("interaction_spec") or team.get("interactionSpec") or {}
        interaction_contracts = (
            interaction_spec.get("local_contracts")
            if isinstance(interaction_spec, dict)
            else {}
        )
        if not isinstance(interaction_contracts, dict):
            interaction_contracts = {}

        for index, raw_agent in enumerate(list(team.get("agents") or [])):
            if not isinstance(raw_agent, dict):
                continue
            agent_id = _clean_text(raw_agent.get("agent_id") or raw_agent.get("agentId") or raw_agent.get("id") or raw_agent.get("name"))
            if not agent_id:
                continue
            agent_name = _clean_text(raw_agent.get("name")) or agent_id
            role_id = _clean_text(raw_agent.get("role") or raw_agent.get("role_id") or raw_agent.get("roleId")) or "researcher"
            provider = _clean_text(raw_agent.get("provider"))
            model = _clean_text(raw_agent.get("model"))
            purpose = _clean_text(raw_agent.get("purpose") or raw_agent.get("why") or raw_agent.get("selection_reason") or raw_agent.get("selectionReason"))
            context_policy = raw_agent.get("context_policy") or raw_agent.get("contextPolicy") or {}
            if not isinstance(context_policy, dict):
                context_policy = {}
            reads = context_policy.get("reads") if isinstance(context_policy.get("reads"), dict) else {}
            writes = context_policy.get("writes") if isinstance(context_policy.get("writes"), dict) else {}
            read_grants = _clean_list(reads.get("grants"), limit=12)
            context_types = _clean_list(reads.get("context_types") or reads.get("contextTypes"), limit=12)
            publish_targets = _clean_list(writes.get("publish_targets") or writes.get("publishTargets"), limit=12)
            query_template = _clean_text(reads.get("query_template") or reads.get("queryTemplate"))
            attached_skills = extract_attached_skills(raw_agent, skill_lookup=skill_registry)
            runtime_instance_id = _configured_runtime_instance_id(state, agent_id, index)
            scope_id = _configured_scope_id(state, agent_id, index)
            local_contract = interaction_contracts.get(agent_name) if isinstance(interaction_contracts, dict) else None
            context_policy_summary = _structured_summary(context_policy)

            configured_items.append(
                {
                    "agent_id": agent_id,
                    "name": agent_name,
                    "runtime_instance_id": runtime_instance_id,
                    "display_label": _friendly_runtime_label(
                        display_label=agent_name,
                        role_id=role_id,
                        selection_reason=purpose,
                        synthesized=True,
                    )
                    or agent_name,
                    "role_label": _title_case_identifier(role_id) or role_id,
                    "role_id": role_id,
                    "template_id": _clean_text(raw_agent.get("template_id") or raw_agent.get("templateId")),
                    "provider": provider,
                    "model": model,
                    "enabled": raw_agent.get("enabled") is not False,
                    "order_index": index,
                    "runtime_status": "configured" if state == "pending" else "ready",
                    "status_counts": {},
                    "responsibilities": _clean_list(raw_agent.get("responsibilities") or purpose, limit=8),
                    "capability_tags": _clean_list(raw_agent.get("capability_tags") or raw_agent.get("capabilityTags"), limit=10),
                    "ephemeral": _boolish(raw_agent.get("ephemeral")),
                    "description": purpose,
                    "visibility": _clean_text(context_policy.get("base_mode") or context_policy.get("baseMode")) or "scoped_context",
                    "source": f"team_config_{state}",
                    "source_key": f"team_config.{state}_team",
                    "attached_skills": attached_skills,
                    "attached_skill_ids": [
                        str(item.get("skill_id") or "").strip()
                        for item in attached_skills
                        if str(item.get("skill_id") or "").strip()
                    ],
                    "context_pack_id": None,
                    "config_state": state,
                    "configured_only": True,
                    "team_name": team_name,
                    "composition_mode": composition_mode,
                    "proposal_mode": proposal_mode,
                    "purpose": purpose,
                    "selection_reason": purpose,
                    "context_policy": context_policy,
                    "context_policy_summary": context_policy_summary,
                    "grant_labels": read_grants,
                    "context_types": context_types,
                    "publish_targets": publish_targets,
                    "query_template": query_template,
                    "scope_id": scope_id,
                    "shortcut_eligible": shortcut_enabled,
                    "shortcut_max_recent_turns": shortcut_max_recent_turns,
                    "only_for_followups": _boolish(raw_agent.get("only_for_followups") or raw_agent.get("onlyForFollowups")),
                    "interaction_contract": local_contract if isinstance(local_contract, dict) else None,
                }
            )
            configured_scope_items.append(
                {
                    "scope_id": scope_id,
                    "runtime_instance_id": runtime_instance_id,
                    "slot_id": None,
                    "display_label": agent_name,
                    "visibility_mode": _clean_text(context_policy.get("base_mode") or context_policy.get("baseMode")) or "scoped_context",
                    "context_types": context_types,
                    "memory_grants": {grant: True for grant in read_grants},
                    "grant_labels": read_grants,
                    "selection_reason": purpose,
                    "context_set_id": None,
                    "token_estimate": _intish((context_policy.get("default_budget") or {}).get("soft_tokens")) if isinstance(context_policy.get("default_budget"), dict) else None,
                    "scope_version": None,
                    "active_node_ids": [],
                    "active_node_count": None,
                    "active_type_labels": [],
                    "visibility_rationale": _clean_text(context_policy.get("base_mode") or context_policy.get("baseMode")),
                    "compiler": "team_config_context_policy",
                    "selection_strategy": "team_config_context_policy",
                    "selection_summary": query_template or context_policy_summary,
                    "matched_query_terms": [],
                    "matched_context_types": context_types,
                    "seed_node_count": None,
                    "candidate_node_count": None,
                    "positive_candidate_count": None,
                    "rejected_positive_node_ids": [],
                    "selection_confidence": "configured",
                    "truncated": False,
                    "authoritative_scope": False,
                    "empty_scope": False,
                    "soft_budget_exceeded": False,
                    "configured_only": True,
                    "config_state": state,
                    "publish_targets": publish_targets,
                }
            )

    return configured_items, configured_scope_items


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
