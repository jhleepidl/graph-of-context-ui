from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable


RUNTIME_MEMBER_ID_KEYS = ("agent_id", "runtime_instance_id", "instance_id", "id", "member_id")
RUNTIME_MEMBER_HINT_KEYS = (
    "role_label",
    "role",
    "role_id",
    "title",
    "name",
    "display_name",
    "display_label",
    "displayLabel",
    "label",
    "slot_id",
    "slotId",
    "preset_id",
    "presetId",
    "authority_profile_id",
    "authorityProfileId",
    "template_id",
    "agent_template_id",
    "provider",
    "llm_provider",
    "model",
    "model_name",
    "runtime_status",
    "status",
    "state",
    "capability_tags",
    "capabilities",
    "responsibilities",
    "responsibility",
    "ephemeral",
    "transient",
    "selection_reason",
    "selectionReason",
    "synthesized",
    "attached_skill_ids",
    "attachedSkillIds",
    "context_pack_id",
    "contextPackId",
)
RUNTIME_NESTED_BLOCK_KEYS = ("runtime", "meta", "result", "output", "state", "data")
TASK_INTERPRETATION_KEYS = ("task_interpretation", "taskInterpretation")
TEAM_PLAN_KEYS = ("team_plan", "teamPlan")
COLLABORATION_CELL_KEYS = ("collaboration_cells", "collaborationCells")
AUTHORITY_GRAPH_KEYS = ("authority_graph", "authorityGraph")
CHECKPOINT_KEYS = ("checkpoints",)
EXECUTION_GRAPH_KEYS = ("execution_graph", "executionGraph")
SELECTION_EXPLANATION_KEYS = ("selection_explanations", "selectionExplanations")
CONVERSATION_PREFERENCE_KEYS = ("conversation_preferences", "conversationPreferences")
TEAM_PLAN_V2_HINT_KEYS = (
    *TASK_INTERPRETATION_KEYS,
    *COLLABORATION_CELL_KEYS,
    *AUTHORITY_GRAPH_KEYS,
    *CHECKPOINT_KEYS,
    *EXECUTION_GRAPH_KEYS,
    *SELECTION_EXPLANATION_KEYS,
    *CONVERSATION_PREFERENCE_KEYS,
    "slots",
    "supervisor_runtime",
    "supervisorRuntime",
)


def jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def node_payload(node: Any | None) -> dict[str, Any]:
    if not node:
        return {}
    payload = jload(getattr(node, "payload_json", "{}"), {})
    if isinstance(payload, dict):
        return payload
    return {}


def created_sort_key(node: Any) -> tuple[str, str]:
    created_at = getattr(node, "created_at", None)
    if isinstance(created_at, datetime):
        return created_at.isoformat(), str(getattr(node, "id", ""))
    return str(created_at or ""), str(getattr(node, "id", ""))


def normalize_status(raw: Any) -> str:
    clean = str(raw or "").strip().lower()
    if not clean:
        return "unknown"
    if clean in {"queued", "pending", "waiting"}:
        return "queued"
    if clean in {"running", "in_progress", "active"}:
        return "running"
    if clean in {"done", "completed", "success", "ok"}:
        return "done"
    if clean in {"error", "failed", "failure", "blocked"}:
        return "error"
    return clean


def has_non_empty_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def clean_list_of_text(value: Any, *, limit: int = 16) -> list[str]:
    if isinstance(value, str):
        clean = value.strip()
        return [clean] if clean else []
    if not isinstance(value, (list, tuple, set)):
        return []
    out: list[str] = []
    for item in value:
        clean = str(item or "").strip()
        if not clean:
            continue
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def clean_text(value: Any) -> str | None:
    clean = str(value or "").strip()
    return clean or None


def parse_jsonish(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return value
    clean = value.strip()
    if not clean:
        return None
    if clean.startswith("{") or clean.startswith("["):
        parsed = jload(clean, None)
        if parsed is not None:
            return parsed
    return value


def first_present(mapping: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) is not None:
            return mapping.get(key)
    return None


def normalize_record_list(
    value: Any,
    *,
    id_field: str = "id",
    hint_keys: Iterable[str] | None = None,
    value_field: str = "value",
    max_items: int = 32,
) -> list[dict[str, Any]]:
    raw = parse_jsonish(value)
    out: list[dict[str, Any]] = []
    hints = tuple(hint_keys or ())

    if isinstance(raw, list):
        for item in raw:
            if len(out) >= max_items:
                break
            if isinstance(item, dict):
                out.append(dict(item))
                continue
            clean = clean_text(item)
            if clean:
                out.append({id_field: clean})
        return out

    if isinstance(raw, tuple):
        return normalize_record_list(list(raw), id_field=id_field, hint_keys=hints, value_field=value_field, max_items=max_items)

    if isinstance(raw, dict):
        if not hints or any(has_non_empty_value(raw.get(key)) for key in hints):
            return [dict(raw)]

        for map_key, map_value in raw.items():
            if len(out) >= max_items:
                break
            if isinstance(map_value, dict):
                entry = dict(map_value)
                clean_key = clean_text(map_key)
                if clean_key and not has_non_empty_value(entry.get(id_field)):
                    entry[id_field] = clean_key
                out.append(entry)
                continue

            clean_key = clean_text(map_key)
            clean_value = clean_text(map_value)
            if clean_key and clean_value:
                out.append({id_field: clean_key, value_field: clean_value})
        return out

    clean = clean_text(raw)
    if clean:
        return [{id_field: clean}]
    return out


def normalize_mapping(value: Any) -> dict[str, Any] | None:
    raw = parse_jsonish(value)
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        clean = raw.strip()
        if clean:
            return {"summary": clean}
    return None


def normalize_task_interpretation(value: Any) -> dict[str, Any] | None:
    mapping = normalize_mapping(value)
    if mapping:
        return mapping
    items = clean_list_of_text(parse_jsonish(value), limit=12)
    if items:
        return {"items": items}
    return None


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

    task_interpretation = normalize_task_interpretation(first_present(raw, TASK_INTERPRETATION_KEYS))
    if task_interpretation:
        out["task_interpretation"] = task_interpretation

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
        supervisor_runtime = normalize_mapping(team_plan.get("supervisor_runtime") or team_plan.get("supervisorRuntime"))
        normalized_team_plan = dict(team_plan)
        normalized_team_plan["slots"] = normalized_slots
        normalized_team_plan["supervisor_runtime"] = supervisor_runtime
        out["team_plan"] = normalized_team_plan

    collaboration_cells = normalize_record_list(
        first_present(raw, COLLABORATION_CELL_KEYS)
        or ((out.get("team_plan") or {}).get("collaboration_cells"))
        or ((out.get("team_plan") or {}).get("collaborationCells")),
        id_field="cell_id",
        hint_keys=("cell_id", "id", "type", "kind", "mode", "name", "label"),
        max_items=32,
    )
    if collaboration_cells:
        out["collaboration_cells"] = collaboration_cells

    authority_graph = normalize_record_list(
        first_present(raw, AUTHORITY_GRAPH_KEYS)
        or ((out.get("team_plan") or {}).get("authority_graph"))
        or ((out.get("team_plan") or {}).get("authorityGraph")),
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
        ),
        max_items=64,
    )
    if authority_graph:
        out["authority_graph"] = authority_graph

    checkpoints = normalize_record_list(
        first_present(raw, CHECKPOINT_KEYS)
        or ((out.get("team_plan") or {}).get("checkpoints")),
        id_field="checkpoint_id",
        hint_keys=("checkpoint_id", "id", "kind", "type", "stage", "label", "title", "name"),
        max_items=48,
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

    conversation_preferences = normalize_mapping(first_present(raw, CONVERSATION_PREFERENCE_KEYS))
    if conversation_preferences:
        out["conversation_preferences"] = conversation_preferences

    return out


def has_runtime_snapshot_metadata(mapping: Any) -> bool:
    metadata = normalize_runtime_snapshot_metadata(mapping)
    return any(has_non_empty_value(value) for value in metadata.values())


def iter_payload_containers(payload: dict[str, Any], *, prefix: str = "", depth: int = 0, max_depth: int = 2):
    if not isinstance(payload, dict):
        return
    yield prefix, payload
    if depth >= max_depth:
        return
    for key in RUNTIME_NESTED_BLOCK_KEYS:
        nested = payload.get(key)
        if isinstance(nested, dict):
            next_prefix = f"{prefix}{key}."
            yield from iter_payload_containers(nested, prefix=next_prefix, depth=depth + 1, max_depth=max_depth)


def is_runtime_member_record(value: Any) -> bool:
    if not isinstance(value, dict):
        return False

    if any(has_non_empty_value(value.get(key)) for key in RUNTIME_MEMBER_ID_KEYS):
        return True

    hint_count = sum(1 for key in RUNTIME_MEMBER_HINT_KEYS if has_non_empty_value(value.get(key)))
    return hint_count >= 2


def extract_runtime_member_map(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    out: list[dict[str, Any]] = []
    for map_key, value in raw.items():
        if not is_runtime_member_record(value):
            continue
        member = dict(value)
        if not any(has_non_empty_value(member.get(key)) for key in RUNTIME_MEMBER_ID_KEYS):
            clean_key = str(map_key or "").strip()
            if clean_key:
                member["agent_id"] = clean_key
        out.append(member)
    return out


def extract_runtime_members(
    raw: Any,
    *,
    allow_string_ids: bool = False,
    allow_keyed_map: bool = False,
) -> list[dict[str, Any]]:
    if isinstance(raw, str):
        clean = raw.strip()
        if not clean:
            return []
        if clean.startswith("{") or clean.startswith("["):
            parsed = jload(clean, None)
            if parsed is not None:
                return extract_runtime_members(
                    parsed,
                    allow_string_ids=allow_string_ids,
                    allow_keyed_map=allow_keyed_map,
                )
        if allow_string_ids:
            return [{"agent_id": clean}]
        return []

    if isinstance(raw, list):
        out: list[dict[str, Any]] = []
        for item in raw:
            if is_runtime_member_record(item):
                out.append(item)
            elif allow_string_ids and isinstance(item, str) and item.strip():
                out.append({"agent_id": item.strip()})
        return out

    if isinstance(raw, dict):
        if is_runtime_member_record(raw):
            return [raw]
        if allow_keyed_map:
            return extract_runtime_member_map(raw)
    return []


def is_runtime_snapshot_shape(value: Any) -> bool:
    if not isinstance(value, dict):
        return False

    if any(
        key in value
        for key in (
            "runtime_team_snapshot",
            "runtimeTeamSnapshot",
            "runtime_agents",
            "runtimeAgents",
            "snapshot_id",
            "snapshot_at",
            "snapshot_version",
            "snapshot_source",
            "snapshot_kind",
        )
    ):
        return True

    for key in ("kind", "type", "source"):
        raw = str(value.get(key) or "").strip().lower()
        if raw and "snapshot" in raw and ("runtime" in raw or "team" in raw):
            return True
    return False


def team_plan_member_candidates(team_plan: Any, *, source_prefix: str) -> list[tuple[str, list[dict[str, Any]]]]:
    if isinstance(team_plan, str):
        parsed = jload(team_plan, None)
        if parsed is not None:
            team_plan = parsed

    if not isinstance(team_plan, dict):
        return []

    out: list[tuple[str, list[dict[str, Any]]]] = []
    runtime_agents = extract_runtime_members(team_plan.get("runtime_agents"), allow_string_ids=True, allow_keyed_map=True)
    if runtime_agents:
        out.append((f"{source_prefix}.runtime_agents", runtime_agents))

    for key in ("members", "agents"):
        members = extract_runtime_members(team_plan.get(key), allow_keyed_map=True)
        if members:
            out.append((f"{source_prefix}.{key}", members))

    role_members = extract_runtime_member_map(team_plan.get("roles"))
    if role_members:
        out.append((f"{source_prefix}.roles", role_members))

    return out


def runtime_member_candidates_from_container(
    container: dict[str, Any],
    *,
    source_prefix: str,
) -> list[tuple[str, list[dict[str, Any]]]]:
    out: list[tuple[str, list[dict[str, Any]]]] = []

    runtime_snapshot = container.get("runtime_team_snapshot")
    if runtime_snapshot is None:
        runtime_snapshot = container.get("runtimeTeamSnapshot")
    if isinstance(runtime_snapshot, str):
        parsed = jload(runtime_snapshot, None)
        if parsed is not None:
            runtime_snapshot = parsed

    if isinstance(runtime_snapshot, dict):
        snapshot_runtime_agents_value = runtime_snapshot.get("runtime_agents")
        if snapshot_runtime_agents_value is None:
            snapshot_runtime_agents_value = runtime_snapshot.get("runtimeAgents")
        canonical_runtime_agents = extract_runtime_members(
            snapshot_runtime_agents_value,
            allow_string_ids=True,
            allow_keyed_map=True,
        )
        if canonical_runtime_agents:
            out.append((f"{source_prefix}runtime_team_snapshot.runtime_agents", canonical_runtime_agents))

        out.extend(
            team_plan_member_candidates(
                runtime_snapshot.get("team_plan"),
                source_prefix=f"{source_prefix}runtime_team_snapshot.team_plan",
            )
        )

        for key in ("members", "agents"):
            members = extract_runtime_members(runtime_snapshot.get(key), allow_keyed_map=True)
            if members:
                out.append((f"{source_prefix}runtime_team_snapshot.{key}", members))

    elif runtime_snapshot is not None:
        members = extract_runtime_members(runtime_snapshot, allow_string_ids=True)
        if members:
            out.append((f"{source_prefix}runtime_team_snapshot", members))

    top_runtime_agents_value = container.get("runtime_agents")
    if top_runtime_agents_value is None:
        top_runtime_agents_value = container.get("runtimeAgents")
    top_runtime_agents = extract_runtime_members(
        top_runtime_agents_value,
        allow_string_ids=True,
        allow_keyed_map=True,
    )
    if top_runtime_agents:
        out.append((f"{source_prefix}runtime_agents", top_runtime_agents))

    if is_runtime_snapshot_shape(container):
        for key in ("members", "agents"):
            members = extract_runtime_members(container.get(key), allow_keyed_map=True)
            if members:
                out.append((f"{source_prefix}{key}", members))

    out.extend(
        team_plan_member_candidates(
            container.get("team_plan"),
            source_prefix=f"{source_prefix}team_plan",
        )
    )
    return out


def runtime_source_priority(source_key: str) -> int:
    clean = str(source_key or "")
    if clean.endswith("runtime_team_snapshot.team_plan.runtime_agents"):
        return 68
    if clean.endswith("runtime_team_snapshot.runtime_agents"):
        return 70
    if clean.endswith("runtime_team_snapshot.team_plan"):
        return 64
    if clean.endswith("runtime_agents"):
        return 60
    if ".runtime_team_snapshot." in clean:
        return 50
    if clean.endswith(".members") or clean.endswith(".agents"):
        return 40
    if clean.endswith("team_plan"):
        return 35
    if clean.endswith("task_interpretation"):
        return 34
    if clean.endswith("execution_graph"):
        return 33
    if clean.endswith("collaboration_cells"):
        return 32
    if clean.endswith("authority_graph"):
        return 31
    if clean.endswith("checkpoints"):
        return 30
    if ".team_plan." in clean:
        return 30
    if clean.endswith("runtime_team_snapshot"):
        return 20
    return 10


def normalize_runtime_source_key(source_key: Any) -> str:
    clean = str(source_key or "").strip()
    if not clean:
        return "runtime_snapshot"
    if clean.endswith("runtime_team_snapshot.team_plan.runtime_agents"):
        return "runtime_team_snapshot.team_plan.runtime_agents"
    if clean.endswith("runtime_team_snapshot.runtime_agents"):
        return "runtime_team_snapshot.runtime_agents"
    if clean.endswith("runtime_team_snapshot.team_plan"):
        return "runtime_team_snapshot.team_plan"
    if clean.endswith("runtime_agents"):
        return "runtime_agents"
    if "team_plan." in clean:
        return f"team_plan.{clean.split('team_plan.', 1)[1]}"
    if "runtime_team_snapshot." in clean:
        return f"runtime_team_snapshot.{clean.split('runtime_team_snapshot.', 1)[1]}"
    if clean.endswith("runtime_team_snapshot"):
        return "runtime_team_snapshot"
    if clean.endswith(".members"):
        return "members"
    if clean.endswith(".agents"):
        return "agents"
    return clean


def metadata_candidate_keys(container: dict[str, Any], *, source_prefix: str) -> list[str]:
    if not isinstance(container, dict):
        return []

    out: list[str] = []

    runtime_snapshot = container.get("runtime_team_snapshot")
    if runtime_snapshot is None:
        runtime_snapshot = container.get("runtimeTeamSnapshot")
    runtime_snapshot = parse_jsonish(runtime_snapshot)
    if isinstance(runtime_snapshot, dict) and has_runtime_snapshot_metadata(runtime_snapshot):
        out.append(f"{source_prefix}runtime_team_snapshot")

    team_plan = parse_jsonish(first_present(container, TEAM_PLAN_KEYS))
    if isinstance(team_plan, dict) and has_runtime_snapshot_metadata(team_plan):
        out.append(f"{source_prefix}team_plan")

    if has_runtime_snapshot_metadata(container):
        direct_key = source_prefix[:-1] if source_prefix.endswith(".") else source_prefix
        out.append(direct_key or "runtime_snapshot")

    deduped: list[str] = []
    seen: set[str] = set()
    for key in out:
        clean = str(key or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        deduped.append(clean)
    return deduped


def extract_runtime_snapshot_metadata_from_payload(
    payload: dict[str, Any],
    *,
    source_key: str | None = None,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    rows: list[tuple[int, str, dict[str, Any]]] = []
    for prefix, container in iter_payload_containers(payload):
        if not isinstance(container, dict):
            continue
        for candidate_key in metadata_candidate_keys(container, source_prefix=prefix):
            metadata = normalize_runtime_snapshot_metadata(container)
            if not metadata:
                continue
            score = runtime_source_priority(candidate_key)
            if source_key and candidate_key == source_key:
                score += 40
            elif source_key and candidate_key and str(source_key).endswith(candidate_key):
                score += 20
            rows.append((score, candidate_key, metadata))

        runtime_snapshot = parse_jsonish(container.get("runtime_team_snapshot") or container.get("runtimeTeamSnapshot"))
        if isinstance(runtime_snapshot, dict) and has_runtime_snapshot_metadata(runtime_snapshot):
            candidate_key = f"{prefix}runtime_team_snapshot"
            metadata = normalize_runtime_snapshot_metadata(runtime_snapshot)
            score = runtime_source_priority(candidate_key)
            if source_key and candidate_key == source_key:
                score += 40
            rows.append((score, candidate_key, metadata))

        team_plan = parse_jsonish(first_present(container, TEAM_PLAN_KEYS))
        if isinstance(team_plan, dict) and has_runtime_snapshot_metadata(team_plan):
            candidate_key = f"{prefix}team_plan"
            metadata = normalize_runtime_snapshot_metadata(team_plan)
            score = runtime_source_priority(candidate_key)
            if source_key and candidate_key == source_key:
                score += 40
            rows.append((score, candidate_key, metadata))

    if not rows:
        return {}

    rows.sort(key=lambda item: (int(item[0]), str(item[1])))
    out: dict[str, Any] = {}
    for _score, _candidate_key, metadata in rows:
        for key, value in metadata.items():
            if has_non_empty_value(value):
                out[key] = value
    return out


def extract_runtime_team_snapshot(
    nodes: Iterable[Any],
    *,
    include_node_types: set[str] | None = None,
) -> dict[str, Any] | None:
    # This stays focused on snapshot discovery; resolved_runtime handles scoped authority/projection assembly.
    allowed_types = include_node_types or {"Run", "Step"}
    candidates: list[dict[str, Any]] = []

    sorted_nodes = sorted(
        [node for node in nodes if str(getattr(node, "type", "")) in allowed_types],
        key=created_sort_key,
    )

    for node in sorted_nodes:
        payload = node_payload(node)
        source_candidates = runtime_member_candidates_from_container(payload, source_prefix="")

        for block_name in RUNTIME_NESTED_BLOCK_KEYS:
            block = payload.get(block_name)
            if isinstance(block, dict):
                source_candidates.extend(
                    runtime_member_candidates_from_container(
                        block,
                        source_prefix=f"{block_name}.",
                    )
                )

        for source_key, members in source_candidates:
            if not members:
                continue
            candidates.append(
                {
                    "node_id": getattr(node, "id", None),
                    "node_type": getattr(node, "type", None),
                    "created_at": getattr(node, "created_at", None),
                    "source_key": source_key,
                    "members": members,
                    "payload": payload,
                }
            )

        if not source_candidates:
            metadata_source_keys = metadata_candidate_keys(payload, source_prefix="")
            for block_name in RUNTIME_NESTED_BLOCK_KEYS:
                block = payload.get(block_name)
                if isinstance(block, dict):
                    metadata_source_keys.extend(metadata_candidate_keys(block, source_prefix=f"{block_name}."))

            for source_key in metadata_source_keys:
                candidates.append(
                    {
                        "node_id": getattr(node, "id", None),
                        "node_type": getattr(node, "type", None),
                        "created_at": getattr(node, "created_at", None),
                        "source_key": source_key,
                        "members": [],
                        "payload": payload,
                    }
                )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            str(item.get("created_at") or ""),
            runtime_source_priority(str(item.get("source_key") or "")),
            str(item.get("node_id") or ""),
        )
    )
    selected = dict(candidates[-1])
    payload = selected.pop("payload", None)
    metadata = extract_runtime_snapshot_metadata_from_payload(
        payload if isinstance(payload, dict) else {},
        source_key=str(selected.get("source_key") or ""),
    )
    selected.update(metadata)
    return selected


def extract_runtime_members_from_container(container: dict[str, Any]) -> list[dict[str, Any]]:
    members: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()

    for _source_key, batch in runtime_member_candidates_from_container(container, source_prefix=""):
        for member in batch:
            if not isinstance(member, dict):
                continue
            dedup_key = (
                str(member.get("runtime_instance_id") or member.get("instance_id") or ""),
                str(member.get("agent_id") or member.get("id") or member.get("agent") or ""),
            )
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)
            members.append(member)

    return members
