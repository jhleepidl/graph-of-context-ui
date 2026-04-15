from __future__ import annotations

from typing import Any

from app.services.runtime_snapshot_constants import (
    ACTION_SOURCE_KEYS,
    AUTHORITY_GRAPH_KEYS,
    CHECKPOINT_KEYS,
    COLLABORATION_CELL_KEYS,
    CONTEXT_RUNTIME_MODE_KEYS,
    CONVERSATION_PREFERENCE_KEYS,
    EXECUTION_FEEDBACK_KEYS,
    EXECUTION_GRAPH_KEYS,
    EXECUTION_INSIGHT_KEYS,
    MATERIALIZED_SCOPE_KEYS,
    SCOPE_SPEC_KEYS,
    SELECTION_EXPLANATION_KEYS,
    TASK_INTERPRETATION_KEYS,
    TEAM_PLAN_KEYS,
    TEAM_PLAN_V2_HINT_KEYS,
    VISIBILITY_GRAPH_KEYS,
)
from app.services.runtime_snapshot_value_helpers import (
    clean_list_of_text,
    clean_text,
    coerce_bool,
    coerce_int,
    first_present,
    has_non_empty_value,
    normalize_mapping,
    normalize_record_list,
    parse_jsonish,
    preserve_structured_value,
)

def normalize_task_interpretation(value: Any) -> dict[str, Any] | None:
    mapping = normalize_mapping(value)
    if mapping:
        return mapping
    items = clean_list_of_text(parse_jsonish(value), limit=12)
    if items:
        return {"items": items}
    return None

def normalize_supervisor_runtime(value: Any) -> dict[str, Any] | None:
    mapping = normalize_mapping(value)
    if not mapping:
        return None

    interaction_mode = clean_text(
        first_present(mapping, ("interaction_mode", "interactionMode", "mode", "kind", "strategy"))
    )
    instance_id = clean_text(
        first_present(mapping, ("instance_id", "runtime_instance_id", "runtimeInstanceId", "id"))
    )
    authority_profile_id = clean_text(
        first_present(mapping, ("authority_profile_id", "authorityProfileId"))
    )
    enabled = coerce_bool(first_present(mapping, ("enabled", "is_enabled", "isEnabled")))
    user_visible = coerce_bool(first_present(mapping, ("user_visible", "userVisible", "visible")))

    out = dict(mapping)
    if interaction_mode:
        out["interaction_mode"] = interaction_mode
        if not clean_text(out.get("mode")):
            out["mode"] = interaction_mode
    if instance_id:
        out["instance_id"] = instance_id
    if authority_profile_id:
        out["authority_profile_id"] = authority_profile_id
    if enabled is not None:
        out["enabled"] = enabled
    if user_visible is not None:
        out["user_visible"] = user_visible
    return out

def normalize_collaboration_cells(value: Any) -> list[dict[str, Any]]:
    items = normalize_record_list(
        value,
        id_field="cell_id",
        hint_keys=(
            "cell_id",
            "id",
            "pattern",
            "kind",
            "type",
            "mode",
            "name",
            "label",
            "topology",
            "max_rounds",
            "termination",
            "member_instance_ids",
            "memberInstanceIds",
            "report_back_to_instance_id",
            "reportBackToInstanceId",
        ),
        max_items=32,
    )

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        entry = dict(item)
        cell_id = clean_text(first_present(entry, ("cell_id", "id"))) or f"cell-{index + 1}"
        pattern = clean_text(first_present(entry, ("pattern", "kind", "type", "mode")))
        member_instance_ids = clean_list_of_text(
            first_present(
                entry,
                (
                    "member_instance_ids",
                    "memberInstanceIds",
                    "members",
                    "participants",
                    "runtime_instance_ids",
                    "runtimeInstanceIds",
                    "agents",
                ),
            ),
            limit=24,
        )
        topology = clean_text(first_present(entry, ("topology", "collaboration_topology", "topology_mode")))
        max_rounds = coerce_int(first_present(entry, ("max_rounds", "maxRounds", "rounds")))
        termination = preserve_structured_value(
            first_present(entry, ("termination", "termination_rule", "terminationRule", "stop_rule", "stopRule"))
        )
        report_back_to_instance_id = clean_text(
            first_present(
                entry,
                (
                    "report_back_to_instance_id",
                    "reportBackToInstanceId",
                    "report_to_instance_id",
                    "reportToInstanceId",
                ),
            )
        )

        entry["cell_id"] = cell_id
        if pattern:
            entry["pattern"] = pattern
            if not clean_text(entry.get("kind")):
                entry["kind"] = pattern
        if member_instance_ids:
            entry["member_instance_ids"] = member_instance_ids
        if topology:
            entry["topology"] = topology
        if max_rounds is not None:
            entry["max_rounds"] = max_rounds
        if has_non_empty_value(termination):
            entry["termination"] = termination
            if not has_non_empty_value(entry.get("termination_rule")):
                entry["termination_rule"] = termination
        if report_back_to_instance_id:
            entry["report_back_to_instance_id"] = report_back_to_instance_id

        normalized.append(entry)

    return normalized

def normalize_authority_graph_entries(value: Any) -> list[dict[str, Any]]:
    items = normalize_record_list(
        value,
        id_field="authority_id",
        hint_keys=(
            "authority_id",
            "id",
            "instance_id",
            "runtime_instance_id",
            "authority_profile_id",
            "authorityProfileId",
            "subject_id",
            "source",
            "target",
            "denied_actions",
            "deniedActions",
            "allowed_actions",
            "allowedActions",
            "approval_required_for",
            "approvalRequiredFor",
            "tool_allowlist",
            "toolAllowlist",
        ),
        max_items=64,
    )

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        entry = dict(item)
        authority_id = clean_text(first_present(entry, ("authority_id", "id"))) or f"authority-{index + 1}"
        runtime_instance_id = clean_text(
            first_present(
                entry,
                (
                    "runtime_instance_id",
                    "instance_id",
                    "subject_instance_id",
                    "subjectInstanceId",
                    "subject_id",
                    "subjectId",
                ),
            )
        )
        authority_profile_id = clean_text(first_present(entry, ("authority_profile_id", "authorityProfileId")))
        allowed_actions = clean_list_of_text(
            first_present(entry, ("allowed_actions", "allowedActions", "permissions", "grants")),
            limit=24,
        )
        denied_actions = clean_list_of_text(
            first_present(
                entry,
                (
                    "denied_actions",
                    "deniedActions",
                    "restricted_actions",
                    "restrictedActions",
                    "restrictions",
                    "denies",
                    "blocked_actions",
                    "blockedActions",
                ),
            ),
            limit=24,
        )
        approval_required_for = clean_list_of_text(
            first_present(entry, ("approval_required_for", "approvalRequiredFor", "approval_actions", "approvalActions")),
            limit=24,
        )
        tool_allowlist = clean_list_of_text(
            first_present(entry, ("tool_allowlist", "toolAllowlist", "allowed_tools", "allowedTools")),
            limit=24,
        )

        entry["authority_id"] = authority_id
        if runtime_instance_id:
            entry["runtime_instance_id"] = runtime_instance_id
        if authority_profile_id:
            entry["authority_profile_id"] = authority_profile_id
        if allowed_actions:
            entry["allowed_actions"] = allowed_actions
        if denied_actions:
            entry["denied_actions"] = denied_actions
            if "restricted_actions" not in entry:
                entry["restricted_actions"] = denied_actions
        if approval_required_for:
            entry["approval_required_for"] = approval_required_for
        if tool_allowlist:
            entry["tool_allowlist"] = tool_allowlist
        normalized.append(entry)

    return normalized

def normalize_checkpoints(value: Any) -> list[dict[str, Any]]:
    items = normalize_record_list(
        value,
        id_field="checkpoint_id",
        hint_keys=(
            "checkpoint_id",
            "id",
            "kind",
            "type",
            "mode",
            "stage",
            "label",
            "title",
            "name",
            "human_interrupt_allowed",
            "humanInterruptAllowed",
            "approval_required",
            "approvalRequired",
            "trigger_after_instances",
            "triggerAfterInstances",
            "supervisor_decision",
            "supervisorDecision",
            "completion_signal",
            "completionSignal",
        ),
        max_items=48,
    )

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        entry = dict(item)
        checkpoint_id = clean_text(first_present(entry, ("checkpoint_id", "id"))) or f"checkpoint-{index + 1}"
        kind = clean_text(first_present(entry, ("kind", "type", "mode")))
        label = clean_text(first_present(entry, ("label", "title", "name")))
        status = clean_text(first_present(entry, ("status", "checkpoint_status", "checkpointStatus")))
        human_interrupt_allowed = coerce_bool(
            first_present(
                entry,
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
        approval_required = coerce_bool(
            first_present(entry, ("approval_required", "approvalRequired", "requires_approval", "requiresApproval"))
        )
        trigger_after_instances = clean_list_of_text(
            first_present(entry, ("trigger_after_instances", "triggerAfterInstances", "after_instances", "afterInstances")),
            limit=24,
        )
        supervisor_decision = preserve_structured_value(
            first_present(entry, ("supervisor_decision", "supervisorDecision", "decision"))
        )
        completion_signal = preserve_structured_value(
            first_present(entry, ("completion_signal", "completionSignal", "completion"))
        )
        blocking = coerce_bool(first_present(entry, ("blocking", "is_blocking", "isBlocking")))

        entry["checkpoint_id"] = checkpoint_id
        if kind:
            entry["kind"] = kind
        if label:
            entry["label"] = label
        if status:
            entry["status"] = status
        if human_interrupt_allowed is not None:
            entry["human_interrupt_allowed"] = human_interrupt_allowed
            if "requires_human" not in entry:
                entry["requires_human"] = human_interrupt_allowed
        if approval_required is not None:
            entry["approval_required"] = approval_required
            if "requires_approval" not in entry:
                entry["requires_approval"] = approval_required
        if trigger_after_instances:
            entry["trigger_after_instances"] = trigger_after_instances
        if has_non_empty_value(supervisor_decision):
            entry["supervisor_decision"] = supervisor_decision
        if has_non_empty_value(completion_signal):
            entry["completion_signal"] = completion_signal
        if blocking is not None:
            entry["blocking"] = blocking
        normalized.append(entry)

    return normalized

def normalize_parallel_groups(value: Any) -> list[dict[str, Any]]:
    raw = parse_jsonish(value)
    out: list[dict[str, Any]] = []

    if isinstance(raw, list):
        for index, item in enumerate(raw):
            group_id = f"group-{index + 1}"
            if isinstance(item, dict):
                entry = dict(item)
                member_ids = clean_list_of_text(
                    entry.get("member_instance_ids")
                    or entry.get("members")
                    or entry.get("runtime_instance_ids")
                    or entry.get("agents")
                    or entry.get("items"),
                    limit=24,
                )
                if member_ids and not entry.get("member_instance_ids"):
                    entry["member_instance_ids"] = member_ids
                entry.setdefault("group_id", clean_text(entry.get("group_id") or entry.get("id")) or group_id)
                out.append(entry)
                continue
            if isinstance(item, (list, tuple, set)):
                member_ids = clean_list_of_text(item, limit=24)
                if member_ids:
                    out.append({"group_id": group_id, "member_instance_ids": member_ids})
                continue
            clean = clean_text(item)
            if clean:
                out.append({"group_id": group_id, "member_instance_ids": [clean]})
        return out

    if isinstance(raw, dict):
        for index, (map_key, map_value) in enumerate(raw.items()):
            if index >= 24:
                break
            entry = {"group_id": clean_text(map_key) or f"group-{index + 1}"}
            member_ids = clean_list_of_text(map_value, limit=24)
            if member_ids:
                entry["member_instance_ids"] = member_ids
            elif isinstance(map_value, dict):
                entry.update(dict(map_value))
            out.append(entry)
        return out

    return out

def normalize_sequential_after(value: Any) -> dict[str, list[str]]:
    raw = parse_jsonish(value)
    out: dict[str, list[str]] = {}

    if isinstance(raw, dict):
        for map_key, map_value in raw.items():
            clean_key = clean_text(map_key)
            if not clean_key:
                continue
            after_ids = clean_list_of_text(map_value, limit=24)
            if after_ids:
                out[clean_key] = after_ids
        return out

    for entry in normalize_record_list(
        raw,
        id_field="runtime_instance_id",
        hint_keys=("runtime_instance_id", "instance_id", "id", "slot_id", "slotId"),
        max_items=32,
    ):
        runtime_instance_id = clean_text(
            entry.get("runtime_instance_id")
            or entry.get("instance_id")
            or entry.get("id")
            or entry.get("slot_id")
            or entry.get("slotId")
        )
        if not runtime_instance_id:
            continue
        after_ids = clean_list_of_text(
            entry.get("sequential_after")
            or entry.get("after")
            or entry.get("after_ids")
            or entry.get("depends_on")
            or entry.get("dependsOn"),
            limit=24,
        )
        if after_ids:
            out[runtime_instance_id] = after_ids
    return out

def normalize_memory_map_summary(value: Any) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    out: list[dict[str, Any]] = []
    for raw in rows:
        row = normalize_mapping(raw)
        if not row:
            continue
        surface_id = clean_text(row.get("surface_id") or row.get("surfaceId") or row.get("file_name") or row.get("fileName"))
        if not surface_id:
            continue
        target_roles = clean_list_of_text(row.get("target_roles") or row.get("targetRoles"), limit=8)
        semantic_slots = clean_list_of_text(row.get("semantic_slots") or row.get("semanticSlots"), limit=8)
        out.append({
            "surface_id": surface_id,
            "file_name": clean_text(row.get("file_name") or row.get("fileName")) or None,
            "load_policy": clean_text(row.get("load_policy") or row.get("loadPolicy")) or None,
            "write_policy": clean_text(row.get("write_policy") or row.get("writePolicy")) or None,
            "target_roles": target_roles,
            "semantic_slots": semantic_slots,
        })
        if len(out) >= 12:
            break
    return out

def normalize_memory_acl_summary(value: Any) -> list[dict[str, Any]]:
    rows = value if isinstance(value, list) else []
    out: list[dict[str, Any]] = []
    for raw in rows:
        row = normalize_mapping(raw)
        if not row:
            continue
        role_id = clean_text(row.get("role_id") or row.get("roleId"))
        if not role_id:
            continue
        out.append({
            "role_id": role_id,
            "read_scope_mode": clean_text(row.get("read_scope_mode") or row.get("readScopeMode")) or None,
            "write_scope_mode": clean_text(row.get("write_scope_mode") or row.get("writeScopeMode")) or None,
            "publish_scope_mode": clean_text(row.get("publish_scope_mode") or row.get("publishScopeMode")) or None,
            "read_surface_ids": clean_list_of_text(row.get("read_surface_ids") or row.get("readSurfaceIds")),
            "write_surface_ids": clean_list_of_text(row.get("write_surface_ids") or row.get("writeSurfaceIds")),
            "publish_surface_ids": clean_list_of_text(row.get("publish_surface_ids") or row.get("publishSurfaceIds")),
            "can_publish_final_answer": coerce_bool(row.get("can_publish_final_answer") if "can_publish_final_answer" in row else row.get("canPublishFinalAnswer")),
            "can_publish_artifact_index": coerce_bool(row.get("can_publish_artifact_index") if "can_publish_artifact_index" in row else row.get("canPublishArtifactIndex")),
        })
        if len(out) >= 8:
            break
    return out

def normalize_blueprint_summary(value: Any) -> dict[str, Any] | None:
    row = normalize_mapping(value)
    if not row:
        return None
    memory_map = normalize_memory_map_summary(row.get("memory_map") or row.get("memoryMap"))
    memory_acl_summary = normalize_memory_acl_summary(row.get("memory_acl_summary") or row.get("memoryAclSummary"))
    runtime_bound_raw = row.get("runtime_bound") if "runtime_bound" in row else row.get("runtimeBound")
    out = {
        "source": clean_text(row.get("source")) or None,
        "blueprint_id": clean_text(row.get("blueprint_id") or row.get("blueprintId")) or None,
        "title": clean_text(row.get("title")) or None,
        "task_archetype": clean_text(row.get("task_archetype") or row.get("taskArchetype")) or None,
        "description": clean_text(row.get("description")) or None,
        "topology_pattern": clean_text(row.get("topology_pattern") or row.get("topologyPattern")) or None,
        "execution_pattern": clean_text(row.get("execution_pattern") or row.get("executionPattern")) or None,
        "capability_status": clean_text(row.get("capability_status") or row.get("capabilityStatus")) or None,
        "runtime_bound": coerce_bool(runtime_bound_raw),
        "admission_status": clean_text(row.get("admission_status") or row.get("admissionStatus")) or None,
        "admission_decision": clean_text(row.get("admission_decision") or row.get("admissionDecision")) or None,
        "blocking_reason_codes": clean_list_of_text(row.get("blocking_reason_codes") or row.get("blockingReasonCodes")),
        "degrade_reason_codes": clean_list_of_text(row.get("degrade_reason_codes") or row.get("degradeReasonCodes")),
        "required_tool_count": int(row.get("required_tool_count") or row.get("requiredToolCount") or 0) or None,
        "optional_tool_count": int(row.get("optional_tool_count") or row.get("optionalToolCount") or 0) or None,
        "missing_required_tool_count": int(row.get("missing_required_tool_count") or row.get("missingRequiredToolCount") or 0) or None,
        "missing_optional_tool_count": int(row.get("missing_optional_tool_count") or row.get("missingOptionalToolCount") or 0) or None,
        "missing_required_tools": clean_list_of_text(row.get("missing_required_tools") or row.get("missingRequiredTools")),
        "missing_optional_tools": clean_list_of_text(row.get("missing_optional_tools") or row.get("missingOptionalTools")),
        "memory_surface_count": int(row.get("memory_surface_count") or row.get("memorySurfaceCount") or len(memory_map) or 0),
        "memory_map": memory_map,
        "memory_acl_summary": memory_acl_summary,
    }
    return {key: value for key, value in out.items() if value not in (None, [], {}, "")} or None

def normalize_execution_insights(value: Any) -> dict[str, Any] | None:
    raw = normalize_mapping(value)
    if not raw:
        return None

    selection_raw = normalize_mapping(raw.get("selection"))
    execution_raw = normalize_mapping(raw.get("execution"))
    selection = {
        "selected": clean_list_of_text(selection_raw.get("selected"), limit=12),
        "suppressed": clean_list_of_text(selection_raw.get("suppressed"), limit=12),
        "planner_facts": clean_list_of_text(selection_raw.get("planner_facts") or selection_raw.get("plannerFacts"), limit=12),
    }
    execution = {
        "planned_agent_count": int(execution_raw.get("planned_agent_count") or execution_raw.get("plannedAgentCount") or 0) or 0,
        "observed_agent_count": int(execution_raw.get("observed_agent_count") or execution_raw.get("observedAgentCount") or 0) or 0,
        "participation_pct": float(execution_raw.get("participation_pct") or execution_raw.get("participationPct") or 0) or 0,
        "planned_agents": clean_list_of_text(execution_raw.get("planned_agents") or execution_raw.get("plannedAgents"), limit=12),
        "observed_agents": clean_list_of_text(execution_raw.get("observed_agents") or execution_raw.get("observedAgents"), limit=12),
        "missing_agents": clean_list_of_text(execution_raw.get("missing_agents") or execution_raw.get("missingAgents"), limit=12),
        "extra_agents": clean_list_of_text(execution_raw.get("extra_agents") or execution_raw.get("extraAgents"), limit=12),
        "participation_by_role": clean_list_of_text(execution_raw.get("participation_by_role") or execution_raw.get("participationByRole"), limit=12),
    }
    out = {
        "execution_pattern": clean_text(raw.get("execution_pattern") or raw.get("executionPattern")) or None,
        "selection": {key: value for key, value in selection.items() if value},
        "execution": {key: value for key, value in execution.items() if value not in (None, [], {}, "")},
    }
    if not out["selection"]:
        out.pop("selection", None)
    if not out["execution"]:
        out.pop("execution", None)
    return {key: value for key, value in out.items() if value not in (None, [], {}, "")} or None

def normalize_execution_feedback(value: Any) -> dict[str, Any] | None:
    raw = normalize_mapping(value)
    if not raw:
        return None

    patterns = []
    for entry in list(raw.get("patterns") or []):
        row = normalize_mapping(entry)
        if not row:
            continue
        patterns.append({
            "execution_pattern": clean_text(row.get("execution_pattern") or row.get("executionPattern")) or None,
            "run_count": int(row.get("run_count") or row.get("runCount") or 0) or 0,
            "avg_participation_pct": float(row.get("avg_participation_pct") or row.get("avgParticipationPct") or 0) or 0,
            "avg_planned_agents": float(row.get("avg_planned_agents") or row.get("avgPlannedAgents") or 0) or 0,
            "avg_observed_agents": float(row.get("avg_observed_agents") or row.get("avgObservedAgents") or 0) or 0,
            "avg_missing_agents": float(row.get("avg_missing_agents") or row.get("avgMissingAgents") or 0) or 0,
            "completion_rate_pct": float(row.get("completion_rate_pct") or row.get("completionRatePct") or 0) or 0,
            "recommendation": clean_text(row.get("recommendation")) or None,
            "reason": (clean_text(row.get("reason")) or "")[:240] or None,
        })
    overlays = []
    for entry in list(raw.get("overlays") or []):
        row = normalize_mapping(entry)
        if not row:
            continue
        overlays.append({
            "overlay_id": clean_text(row.get("overlay_id") or row.get("overlayId")) or None,
            "title": clean_text(row.get("title")) or None,
            "run_count": int(row.get("run_count") or row.get("runCount") or 0) or 0,
            "prompt_count": int(row.get("prompt_count") or row.get("promptCount") or 0) or 0,
            "avg_participation_pct": float(row.get("avg_participation_pct") or row.get("avgParticipationPct") or 0) or 0,
            "avg_overlay_tokens": float(row.get("avg_overlay_tokens") or row.get("avgOverlayTokens") or 0) or 0,
            "avg_overlay_share_pct": float(row.get("avg_overlay_share_pct") or row.get("avgOverlaySharePct") or 0) or 0,
            "recommendation": clean_text(row.get("recommendation")) or None,
            "reason": (clean_text(row.get("reason")) or "")[:240] or None,
        })

    def _compact_feedback_entries(items: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for entry in list(items or []):
            row = normalize_mapping(entry)
            if not row:
                continue
            out.append({
                "execution_pattern": clean_text(row.get("execution_pattern") or row.get("executionPattern")) or None,
                "overlay_id": clean_text(row.get("overlay_id") or row.get("overlayId")) or None,
                "title": clean_text(row.get("title")) or None,
                "run_count": int(row.get("run_count") or row.get("runCount") or 0) or 0,
                "avg_participation_pct": float(row.get("avg_participation_pct") or row.get("avgParticipationPct") or 0) or 0,
                "completion_rate_pct": float(row.get("completion_rate_pct") or row.get("completionRatePct") or 0) or 0,
                "avg_overlay_tokens": float(row.get("avg_overlay_tokens") or row.get("avgOverlayTokens") or 0) or 0,
                "avg_overlay_share_pct": float(row.get("avg_overlay_share_pct") or row.get("avgOverlaySharePct") or 0) or 0,
                "recommendation": clean_text(row.get("recommendation")) or None,
                "reason": (clean_text(row.get("reason")) or "")[:240] or None,
            })
        return out[:8]

    out = {
        "updated_at": clean_text(raw.get("updated_at") or raw.get("updatedAt")) or None,
        "run_count": int(raw.get("run_count") or raw.get("runCount") or 0) or 0,
        "patterns": patterns[:8],
        "overlays": overlays[:8],
        "recommended_patterns": _compact_feedback_entries(raw.get("recommended_patterns") or raw.get("recommendedPatterns") or []),
        "discouraged_patterns": _compact_feedback_entries(raw.get("discouraged_patterns") or raw.get("discouragedPatterns") or []),
        "recommended_overlays": _compact_feedback_entries(raw.get("recommended_overlays") or raw.get("recommendedOverlays") or []),
        "discouraged_overlays": _compact_feedback_entries(raw.get("discouraged_overlays") or raw.get("discouragedOverlays") or []),
    }
    return {key: value for key, value in out.items() if value not in (None, [], {}, "")} or None

def normalize_execution_graph(value: Any) -> dict[str, Any] | None:
    raw = normalize_mapping(value)
    if not raw:
        return None

    parallel_groups = normalize_parallel_groups(raw.get("parallel_groups") or raw.get("parallelGroups"))
    sequential_after = normalize_sequential_after(raw.get("sequential_after") or raw.get("sequentialAfter"))
    supervisor_edges = normalize_record_list(
        raw.get("supervisor_edges") or raw.get("supervisorEdges"),
        id_field="edge_id",
        hint_keys=("edge_id", "id", "from", "to", "source", "target", "supervisor_id", "runtime_instance_id"),
        max_items=32,
    )

    out = dict(raw)
    out["parallel_groups"] = parallel_groups
    out["sequential_after"] = sequential_after
    out["supervisor_edges"] = supervisor_edges
    return out

def team_plan_v2_hints(mapping: dict[str, Any]) -> bool:
    if not isinstance(mapping, dict):
        return False
    return any(has_non_empty_value(mapping.get(key)) for key in TEAM_PLAN_V2_HINT_KEYS)

def normalize_runtime_snapshot_metadata(mapping: Any) -> dict[str, Any]:
    raw = parse_jsonish(mapping)
    if not isinstance(raw, dict):
        return {}

    out: dict[str, Any] = {}

    action_source = clean_text(first_present(raw, ACTION_SOURCE_KEYS))
    if action_source:
        out["action_source"] = action_source

    task_interpretation = normalize_task_interpretation(first_present(raw, TASK_INTERPRETATION_KEYS))
    if task_interpretation:
        out["task_interpretation"] = task_interpretation

    blueprint_summary = normalize_blueprint_summary(first_present(raw, ("blueprint_summary", "blueprintSummary")))
    if blueprint_summary:
        out["blueprint_summary"] = blueprint_summary

    raw_team_plan = parse_jsonish(first_present(raw, TEAM_PLAN_KEYS))
    team_plan: dict[str, Any] | None = None
    if isinstance(raw_team_plan, dict) and team_plan_v2_hints(raw_team_plan):
        team_plan = dict(raw_team_plan)
    elif raw_team_plan is None and team_plan_v2_hints(raw):
        team_plan = dict(raw)

    if team_plan:
        normalized_slots = normalize_record_list(
            team_plan.get("slots") or team_plan.get("capability_slots") or team_plan.get("capabilitySlots"),
            id_field="slot_id",
            hint_keys=("slot_id", "slotId", "role_id", "roleId", "display_label", "displayLabel", "name", "label"),
            max_items=32,
        )
        supervisor_runtime = normalize_supervisor_runtime(team_plan.get("supervisor_runtime") or team_plan.get("supervisorRuntime"))
        normalized_scope_specs = normalize_record_list(
            first_present(team_plan, SCOPE_SPEC_KEYS),
            id_field="scope_id",
            hint_keys=("scope_id", "scopeId", "target_slot_id", "targetSlotId", "target_instance_id", "targetInstanceId", "role_id", "roleId", "visibility_mode", "visibilityMode"),
            max_items=48,
        )
        normalized_materialized_scopes = normalize_record_list(
            first_present(team_plan, MATERIALIZED_SCOPE_KEYS),
            id_field="scope_id",
            hint_keys=("scope_id", "scopeId", "context_set_id", "contextSetId", "token_estimate", "scope_version", "scopeVersion"),
            max_items=48,
        )
        normalized_visibility_graph = normalize_record_list(
            first_present(team_plan, VISIBILITY_GRAPH_KEYS),
            id_field="edge_id",
            hint_keys=("from_scope_id", "fromScopeId", "to_scope_id", "toScopeId", "relation"),
            max_items=64,
        )
        context_runtime_mode = clean_text(first_present(team_plan, CONTEXT_RUNTIME_MODE_KEYS))
        normalized_team_plan = dict(team_plan)
        normalized_team_plan["slots"] = normalized_slots
        normalized_blueprint_summary = normalize_blueprint_summary(team_plan.get("blueprint_summary") or team_plan.get("blueprintSummary"))
        if normalized_blueprint_summary:
            normalized_team_plan["blueprint_summary"] = normalized_blueprint_summary
            out.setdefault("blueprint_summary", normalized_blueprint_summary)
        normalized_team_plan["supervisor_runtime"] = supervisor_runtime
        if normalized_scope_specs:
            normalized_team_plan["scope_specs"] = normalized_scope_specs
        if normalized_materialized_scopes:
            normalized_team_plan["materialized_scopes"] = normalized_materialized_scopes
        if normalized_visibility_graph:
            normalized_team_plan["visibility_graph"] = normalized_visibility_graph
        if context_runtime_mode:
            normalized_team_plan["context_runtime_mode"] = context_runtime_mode
        out["team_plan"] = normalized_team_plan

    collaboration_cells = normalize_collaboration_cells(
        first_present(raw, COLLABORATION_CELL_KEYS)
        or ((out.get("team_plan") or {}).get("collaboration_cells"))
        or ((out.get("team_plan") or {}).get("collaborationCells")),
    )
    if collaboration_cells:
        out["collaboration_cells"] = collaboration_cells

    authority_graph = normalize_authority_graph_entries(
        first_present(raw, AUTHORITY_GRAPH_KEYS)
        or ((out.get("team_plan") or {}).get("authority_graph"))
        or ((out.get("team_plan") or {}).get("authorityGraph")),
    )
    if authority_graph:
        out["authority_graph"] = authority_graph

    checkpoints = normalize_checkpoints(
        first_present(raw, CHECKPOINT_KEYS)
        or ((out.get("team_plan") or {}).get("checkpoints")),
    )
    if checkpoints:
        out["checkpoints"] = checkpoints

    execution_graph = normalize_execution_graph(
        first_present(raw, EXECUTION_GRAPH_KEYS)
        or ((out.get("team_plan") or {}).get("execution_graph"))
        or ((out.get("team_plan") or {}).get("executionGraph"))
    )
    if execution_graph:
        out["execution_graph"] = execution_graph

    selection_explanations = normalize_record_list(
        first_present(raw, SELECTION_EXPLANATION_KEYS)
        or ((out.get("team_plan") or {}).get("selection_explanations"))
        or ((out.get("team_plan") or {}).get("selectionExplanations")),
        id_field="explanation_id",
        hint_keys=("explanation_id", "id", "slot_id", "slotId", "role_id", "roleId", "instance_id", "kind", "type"),
        value_field="text",
        max_items=48,
    )
    if selection_explanations:
        out["selection_explanations"] = selection_explanations

    execution_insights = normalize_execution_insights(first_present(raw, EXECUTION_INSIGHT_KEYS))
    if execution_insights:
        out["execution_insights"] = execution_insights

    execution_feedback = normalize_execution_feedback(first_present(raw, EXECUTION_FEEDBACK_KEYS))
    if execution_feedback:
        out["execution_feedback"] = execution_feedback

    scope_specs = normalize_record_list(
        first_present(raw, SCOPE_SPEC_KEYS)
        or ((out.get("team_plan") or {}).get("scope_specs"))
        or ((out.get("team_plan") or {}).get("scopeSpecs")),
        id_field="scope_id",
        hint_keys=("scope_id", "scopeId", "target_slot_id", "targetSlotId", "target_instance_id", "targetInstanceId", "role_id", "roleId", "visibility_mode", "visibilityMode"),
        max_items=48,
    )
    if scope_specs:
        out["scope_specs"] = scope_specs

    materialized_scopes = normalize_record_list(
        first_present(raw, MATERIALIZED_SCOPE_KEYS)
        or ((out.get("team_plan") or {}).get("materialized_scopes"))
        or ((out.get("team_plan") or {}).get("materializedScopes")),
        id_field="scope_id",
        hint_keys=("scope_id", "scopeId", "context_set_id", "contextSetId", "token_estimate", "scope_version", "scopeVersion"),
        max_items=48,
    )
    if materialized_scopes:
        out["materialized_scopes"] = materialized_scopes

    visibility_graph = normalize_record_list(
        first_present(raw, VISIBILITY_GRAPH_KEYS)
        or ((out.get("team_plan") or {}).get("visibility_graph"))
        or ((out.get("team_plan") or {}).get("visibilityGraph")),
        id_field="edge_id",
        hint_keys=("from_scope_id", "fromScopeId", "to_scope_id", "toScopeId", "relation"),
        max_items=64,
    )
    if visibility_graph:
        out["visibility_graph"] = visibility_graph

    context_runtime_mode = clean_text(
        first_present(raw, CONTEXT_RUNTIME_MODE_KEYS)
        or ((out.get("team_plan") or {}).get("context_runtime_mode"))
        or ((out.get("team_plan") or {}).get("contextRuntimeMode"))
    )
    if context_runtime_mode:
        out["context_runtime_mode"] = context_runtime_mode

    conversation_preferences = normalize_mapping(first_present(raw, CONVERSATION_PREFERENCE_KEYS))
    if conversation_preferences:
        out["conversation_preferences"] = conversation_preferences

    return out

def has_runtime_snapshot_metadata(mapping: Any) -> bool:
    metadata = normalize_runtime_snapshot_metadata(mapping)
    return any(has_non_empty_value(value) for value in metadata.values())

