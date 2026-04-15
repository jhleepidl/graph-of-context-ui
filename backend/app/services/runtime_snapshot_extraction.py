from __future__ import annotations

from typing import Any, Iterable

from app.services.runtime_snapshot_helpers import (
    ACTION_SOURCE_KEYS,
    RUNTIME_MEMBER_HINT_KEYS,
    RUNTIME_MEMBER_ID_KEYS,
    RUNTIME_NESTED_BLOCK_KEYS,
    TEAM_PLAN_KEYS,
    created_sort_key,
    first_present,
    has_non_empty_value,
    has_runtime_snapshot_metadata,
    jload,
    node_payload,
    normalize_runtime_snapshot_metadata,
    parse_jsonish,
)

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
    runtime_agents_value = team_plan.get("runtime_agents")
    if runtime_agents_value is None:
        runtime_agents_value = team_plan.get("runtimeAgents")
    runtime_agents = extract_runtime_members(runtime_agents_value, allow_string_ids=True, allow_keyed_map=True)
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
