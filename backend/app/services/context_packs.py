from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable

from app.services.skill_projections import normalize_load_level


CONTEXT_PACK_KEYS = (
    "context_pack",
    "contextPack",
    "context_pack_summary",
    "contextPackSummary",
    "context_pack_summaries",
    "contextPackSummaries",
    "context_packs",
    "contextPacks",
)

NESTED_PAYLOAD_KEYS = ("runtime", "meta", "result", "output", "state", "data")


def _jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def _node_payload(node: Any) -> dict[str, Any]:
    payload = _jload(getattr(node, "payload_json", "{}"), {})
    if isinstance(payload, dict):
        return payload
    return {}


def _created_sort_key(node: Any) -> tuple[str, str]:
    created_at = getattr(node, "created_at", None)
    if isinstance(created_at, datetime):
        return created_at.isoformat(), str(getattr(node, "id", ""))
    return str(created_at or ""), str(getattr(node, "id", ""))


def _clean_text(value: Any) -> str | None:
    clean = str(value or "").strip()
    return clean or None


def _count_from_value(raw: Any) -> int:
    if raw is None:
        return 0
    if isinstance(raw, bool):
        return 1 if raw else 0
    if isinstance(raw, int):
        return max(0, int(raw))
    if isinstance(raw, float):
        return max(0, int(raw))
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return 0
        if stripped.isdigit():
            return int(stripped)
        return 1
    if isinstance(raw, (list, tuple, set, dict)):
        return len(raw)
    return 0


def _clean_list(value: Any, *, limit: int = 24) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value[:limit]
    if isinstance(value, tuple):
        return list(value)[:limit]
    if isinstance(value, set):
        return list(value)[:limit]
    return [value]


def _iter_payload_containers(payload: dict[str, Any], *, prefix: str = "", depth: int = 0, max_depth: int = 2):
    if not isinstance(payload, dict):
        return
    yield prefix, payload
    if depth >= max_depth:
        return
    for key in NESTED_PAYLOAD_KEYS:
        nested = payload.get(key)
        if isinstance(nested, dict):
            next_prefix = f"{prefix}{key}."
            yield from _iter_payload_containers(nested, prefix=next_prefix, depth=depth + 1, max_depth=max_depth)


def _expand_skill_items(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    if isinstance(value, str):
        clean = value.strip()
        if clean:
            out.append({"skill_id": clean, "load_level": "metadata_only", "count": 1})
        return out

    if isinstance(value, list):
        for item in value:
            out.extend(_expand_skill_items(item))
        return out

    if isinstance(value, dict):
        if any(key in value for key in ("skill_id", "id", "slug", "load_level", "count")):
            out.append(dict(value))
            return out

        for map_key, map_value in value.items():
            if isinstance(map_value, dict):
                entry = dict(map_value)
                entry.setdefault("skill_id", str(map_key or "").strip())
                out.append(entry)
            elif isinstance(map_value, (int, float, str)):
                out.append(
                    {
                        "skill_id": str(map_key or "").strip(),
                        "count": _count_from_value(map_value),
                        "load_level": "metadata_only",
                    }
                )
        return out

    return out


def _normalize_skill_item(raw: Any) -> dict[str, Any] | None:
    if isinstance(raw, str):
        raw = {"skill_id": raw}
    if not isinstance(raw, dict):
        return None

    skill_id = _clean_text(raw.get("skill_id") or raw.get("id") or raw.get("slug") or raw.get("skill"))
    if not skill_id:
        return None

    count_raw = raw.get("count")
    if count_raw is None:
        count_raw = raw.get("items_count")
    if count_raw is None:
        count_raw = raw.get("item_count")

    return {
        "skill_id": skill_id,
        "load_level": normalize_load_level(raw.get("load_level") or raw.get("loadLevel") or raw.get("level")),
        "count": max(1, _count_from_value(count_raw)) if _count_from_value(count_raw) > 0 else 1,
    }


def _context_pack_entries_from_value(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        clean = value.strip()
        if not clean:
            return []
        if clean.startswith("{") or clean.startswith("["):
            parsed = _jload(clean, None)
            if parsed is not None:
                return _context_pack_entries_from_value(parsed)
        return [{"context_pack_id": clean}]

    if isinstance(value, list):
        out: list[dict[str, Any]] = []
        for item in value:
            out.extend(_context_pack_entries_from_value(item))
        return out

    if not isinstance(value, dict):
        return []

    if any(
        key in value
        for key in (
            "context_pack_id",
            "contextPackId",
            "id",
            "scope",
            "skill_items",
            "shared_items_count",
            "role_specific_items_count",
            "missing_items",
            "conflicts",
        )
    ):
        return [value]

    out: list[dict[str, Any]] = []
    for map_key, map_value in value.items():
        if isinstance(map_value, dict):
            entry = dict(map_value)
            entry.setdefault("context_pack_id", str(map_key or "").strip())
            out.append(entry)
        elif isinstance(map_value, list):
            out.extend(_context_pack_entries_from_value(map_value))
    return out


def normalize_context_pack_summary(
    raw: Any,
    *,
    target_runtime_agent_instance_id: str | None = None,
    source: str | None = None,
) -> dict[str, Any] | None:
    if isinstance(raw, str):
        raw = {"context_pack_id": raw}
    if not isinstance(raw, dict):
        return None

    context_pack_id = _clean_text(raw.get("context_pack_id") or raw.get("contextPackId") or raw.get("id"))
    scope = _clean_text(raw.get("scope") or raw.get("type") or raw.get("kind")) or "runtime"

    shared_count = raw.get("shared_items_count")
    if shared_count is None:
        shared_count = raw.get("shared_count")
    if shared_count is None:
        shared_count = raw.get("shared_context_count")
    if shared_count is None:
        shared_count = raw.get("shared_items")

    role_count = raw.get("role_specific_items_count")
    if role_count is None:
        role_count = raw.get("role_items_count")
    if role_count is None:
        role_count = raw.get("role_context_count")
    if role_count is None:
        role_count = raw.get("role_specific_items")
    if role_count is None:
        role_count = raw.get("role_items")

    raw_skill_items = (
        raw.get("skill_items")
        or raw.get("skillItems")
        or raw.get("skills")
        or raw.get("skill_context_items")
        or raw.get("skillContextItems")
    )

    skill_items: list[dict[str, Any]] = []
    for item in _expand_skill_items(raw_skill_items):
        normalized_item = _normalize_skill_item(item)
        if normalized_item:
            skill_items.append(normalized_item)

    target_runtime = _clean_text(
        raw.get("target_runtime_agent_instance_id")
        or raw.get("targetRuntimeAgentInstanceId")
        or raw.get("runtime_instance_id")
        or raw.get("instance_id")
        or target_runtime_agent_instance_id
    )

    missing_items = _clean_list(raw.get("missing_items") or raw.get("missing") or raw.get("missing_context"))
    conflicts = _clean_list(raw.get("conflicts") or raw.get("conflict_items") or raw.get("conflict"))

    out = {
        "context_pack_id": context_pack_id,
        "scope": scope,
        "target_runtime_agent_instance_id": target_runtime,
        "shared_items_count": _count_from_value(shared_count),
        "role_specific_items_count": _count_from_value(role_count),
        "skill_items": skill_items,
        "missing_items": missing_items,
        "conflicts": conflicts,
    }

    if source:
        out["source"] = source
    return out


def _merge_skill_items(base_items: list[dict[str, Any]], incoming_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for item in base_items + incoming_items:
        skill_id = _clean_text(item.get("skill_id"))
        if not skill_id:
            continue
        current = merged.get(skill_id)
        next_item = {
            "skill_id": skill_id,
            "load_level": normalize_load_level(item.get("load_level")),
            "count": max(1, _count_from_value(item.get("count"))),
        }
        if not current:
            merged[skill_id] = next_item
            continue

        current_rank = 0
        if str(current.get("load_level") or "") == "instructions":
            current_rank = 1
        elif str(current.get("load_level") or "") == "resources":
            current_rank = 2

        next_rank = 0
        if str(next_item.get("load_level") or "") == "instructions":
            next_rank = 1
        elif str(next_item.get("load_level") or "") == "resources":
            next_rank = 2

        if next_rank >= current_rank:
            current["load_level"] = next_item["load_level"]
        current["count"] = max(_count_from_value(current.get("count")), _count_from_value(next_item.get("count")))

    return sorted(merged.values(), key=lambda item: (str(item.get("skill_id") or ""),))


def _merge_context_pack_summary(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)

    for key in ("context_pack_id", "scope", "target_runtime_agent_instance_id", "source", "run_id", "node_id", "node_type"):
        value = incoming.get(key)
        if value is not None and str(value).strip():
            merged[key] = value

    merged["shared_items_count"] = max(
        _count_from_value(merged.get("shared_items_count")),
        _count_from_value(incoming.get("shared_items_count")),
    )
    merged["role_specific_items_count"] = max(
        _count_from_value(merged.get("role_specific_items_count")),
        _count_from_value(incoming.get("role_specific_items_count")),
    )

    merged["skill_items"] = _merge_skill_items(
        list(merged.get("skill_items") or []),
        list(incoming.get("skill_items") or []),
    )

    missing_items = [str(item) for item in list(merged.get("missing_items") or []) + list(incoming.get("missing_items") or []) if str(item).strip()]
    conflict_items = [str(item) for item in list(merged.get("conflicts") or []) + list(incoming.get("conflicts") or []) if str(item).strip()]
    merged["missing_items"] = sorted(set(missing_items))[:32]
    merged["conflicts"] = sorted(set(conflict_items))[:32]

    return merged


def _runtime_members_from_container(container: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    runtime_snapshot = container.get("runtime_team_snapshot")
    if runtime_snapshot is None:
        runtime_snapshot = container.get("runtimeTeamSnapshot")
    if isinstance(runtime_snapshot, str):
        parsed = _jload(runtime_snapshot, None)
        if parsed is not None:
            runtime_snapshot = parsed

    if isinstance(runtime_snapshot, dict):
        runtime_agents = runtime_snapshot.get("runtime_agents")
        if runtime_agents is None:
            runtime_agents = runtime_snapshot.get("runtimeAgents")
        if isinstance(runtime_agents, list):
            out.extend([item for item in runtime_agents if isinstance(item, dict)])
        elif isinstance(runtime_agents, dict):
            out.extend([item for item in runtime_agents.values() if isinstance(item, dict)])

    runtime_agents_top = container.get("runtime_agents")
    if runtime_agents_top is None:
        runtime_agents_top = container.get("runtimeAgents")
    if isinstance(runtime_agents_top, list):
        out.extend([item for item in runtime_agents_top if isinstance(item, dict)])
    elif isinstance(runtime_agents_top, dict):
        out.extend([item for item in runtime_agents_top.values() if isinstance(item, dict)])

    return out


def extract_context_pack_summaries(
    nodes: Iterable[Any],
    *,
    max_items: int = 160,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for node in sorted([item for item in nodes if str(getattr(item, "type", "")) in {"Run", "Step"}], key=_created_sort_key):
        node_payload = _node_payload(node)
        node_id = str(getattr(node, "id", "") or "")
        node_type = str(getattr(node, "type", "") or "")

        for prefix, container in _iter_payload_containers(node_payload):
            run_id = _clean_text(container.get("run_id") or node_payload.get("run_id"))
            for key in CONTEXT_PACK_KEYS:
                if key not in container:
                    continue
                raw_value = container.get(key)
                for raw_entry in _context_pack_entries_from_value(raw_value):
                    normalized = normalize_context_pack_summary(raw_entry, source=f"{prefix}{key}")
                    if not normalized:
                        continue
                    normalized["node_id"] = node_id
                    normalized["node_type"] = node_type
                    normalized["run_id"] = run_id
                    rows.append(normalized)

            for runtime_member in _runtime_members_from_container(container):
                runtime_instance_id = _clean_text(runtime_member.get("runtime_instance_id") or runtime_member.get("instance_id"))
                direct_context_pack_id = _clean_text(runtime_member.get("context_pack_id") or runtime_member.get("contextPackId"))
                if direct_context_pack_id:
                    summary = normalize_context_pack_summary(
                        {"context_pack_id": direct_context_pack_id},
                        target_runtime_agent_instance_id=runtime_instance_id,
                        source=f"{prefix}runtime_member.context_pack_id",
                    )
                    if summary:
                        summary["node_id"] = node_id
                        summary["node_type"] = node_type
                        summary["run_id"] = run_id
                        rows.append(summary)

                member_pack = runtime_member.get("context_pack") or runtime_member.get("contextPack")
                for raw_entry in _context_pack_entries_from_value(member_pack):
                    normalized = normalize_context_pack_summary(
                        raw_entry,
                        target_runtime_agent_instance_id=runtime_instance_id,
                        source=f"{prefix}runtime_member.context_pack",
                    )
                    if not normalized:
                        continue
                    normalized["node_id"] = node_id
                    normalized["node_type"] = node_type
                    normalized["run_id"] = run_id
                    rows.append(normalized)

                member_summary = runtime_member.get("context_pack_summary") or runtime_member.get("contextPackSummary")
                for raw_entry in _context_pack_entries_from_value(member_summary):
                    normalized = normalize_context_pack_summary(
                        raw_entry,
                        target_runtime_agent_instance_id=runtime_instance_id,
                        source=f"{prefix}runtime_member.context_pack_summary",
                    )
                    if not normalized:
                        continue
                    normalized["node_id"] = node_id
                    normalized["node_type"] = node_type
                    normalized["run_id"] = run_id
                    rows.append(normalized)

    merged_rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row.get("context_pack_id") or ""),
            str(row.get("target_runtime_agent_instance_id") or ""),
            str(row.get("scope") or "runtime"),
        )
        if key not in merged_rows:
            merged_rows[key] = row
            continue
        merged_rows[key] = _merge_context_pack_summary(merged_rows[key], row)

    ordered = sorted(
        merged_rows.values(),
        key=lambda item: (
            str(item.get("run_id") or ""),
            str(item.get("target_runtime_agent_instance_id") or ""),
            str(item.get("context_pack_id") or ""),
        ),
    )
    if len(ordered) > max_items:
        ordered = ordered[-max_items:]
    return ordered
