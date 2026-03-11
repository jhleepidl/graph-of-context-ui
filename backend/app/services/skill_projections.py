from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable


RUNTIME_MEMBER_ID_KEYS = ("agent_id", "runtime_instance_id", "instance_id", "id", "member_id")
RUNTIME_MEMBER_HINT_KEYS = (
    "role_label",
    "role",
    "title",
    "name",
    "display_name",
    "label",
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
)
RUNTIME_NESTED_BLOCK_KEYS = ("runtime", "meta", "result", "output", "state", "data")

SKILL_ATTACHMENT_KEYS = (
    "attached_skills",
    "attachedSkills",
    "skills",
    "skill_ids",
    "skillIds",
    "enabled_skills",
    "enabledSkills",
)

SKILL_USAGE_EVENT_KEYS = (
    "skill_usage_events",
    "skillUsageEvents",
    "skill_events",
    "skillEvents",
    "skill_feedback",
    "skillFeedback",
    "skill_usage",
    "skillUsage",
)

ATTACHED_SKILL_FIELDS = (
    "skill_id",
    "skill_name",
    "load_level",
    "selected_by",
    "selection_reason",
    "status",
)


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


def _clean_list_of_text(value: Any, *, limit: int = 16) -> list[str]:
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


def _has_non_empty_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _iter_payload_containers(payload: dict[str, Any], *, prefix: str = "", depth: int = 0, max_depth: int = 2):
    if not isinstance(payload, dict):
        return
    yield prefix, payload
    if depth >= max_depth:
        return
    for key in RUNTIME_NESTED_BLOCK_KEYS:
        nested = payload.get(key)
        if isinstance(nested, dict):
            next_prefix = f"{prefix}{key}."
            yield from _iter_payload_containers(nested, prefix=next_prefix, depth=depth + 1, max_depth=max_depth)


def _short_payload_summary(value: Any, *, max_len: int = 240) -> str:
    if isinstance(value, str):
        compact = " ".join(value.split())
        return compact[:max_len] if len(compact) > max_len else compact

    if isinstance(value, dict):
        for key in (
            "summary",
            "reason",
            "selection_reason",
            "message",
            "result",
            "status",
            "note",
            "description",
        ):
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                compact = " ".join(raw.split())
                return compact[:max_len] if len(compact) > max_len else compact
        dumped = json.dumps(value, ensure_ascii=False)
        compact = " ".join(dumped.split())
        return compact[:max_len] if len(compact) > max_len else compact

    if isinstance(value, list):
        if not value:
            return ""
        joined = ", ".join(_short_payload_summary(item, max_len=max_len // 2) for item in value[:3])
        compact = " ".join(joined.split())
        return compact[:max_len] if len(compact) > max_len else compact

    return str(value or "").strip()[:max_len]


def normalize_load_level(raw: Any) -> str:
    clean = str(raw or "").strip().lower()
    if not clean:
        return "metadata_only"

    if clean in {"metadata", "meta", "metadata_only", "metadata-only", "id_only", "identifier_only"}:
        return "metadata_only"
    if clean in {"instruction", "instructions", "prompt", "prompt_only", "system_prompt"}:
        return "instructions"
    if clean in {"resource", "resources", "resource_full", "full", "complete", "all"}:
        return "resources"
    return clean


def _normalize_attached_skill(raw: Any, *, skill_lookup: dict[str, dict[str, Any]] | None = None) -> dict[str, Any] | None:
    if isinstance(raw, str):
        raw = {"skill_id": raw}
    if not isinstance(raw, dict):
        return None

    skill_id = _clean_text(raw.get("skill_id") or raw.get("id") or raw.get("slug") or raw.get("skill"))
    if not skill_id:
        return None

    package = (skill_lookup or {}).get(skill_id) if skill_lookup else None
    skill_name = _clean_text(raw.get("skill_name") or raw.get("name") or raw.get("title"))
    if not skill_name and package:
        skill_name = _clean_text(package.get("name"))

    return {
        "skill_id": skill_id,
        "skill_name": skill_name,
        "load_level": normalize_load_level(
            raw.get("load_level")
            or raw.get("loadLevel")
            or raw.get("level")
            or raw.get("context_load_level")
            or raw.get("scope")
        ),
        "selected_by": _clean_text(
            raw.get("selected_by")
            or raw.get("selectedBy")
            or raw.get("selector")
            or raw.get("selection_source")
        ) or "runtime",
        "selection_reason": _clean_text(raw.get("selection_reason") or raw.get("reason") or raw.get("why")),
        "status": _clean_text(raw.get("status")) or "active",
    }


def _skill_id_key(raw: Any) -> str:
    return str(raw or "").strip()


def _load_level_rank(level: str) -> int:
    clean = str(level or "").strip().lower()
    if clean == "resources":
        return 30
    if clean == "instructions":
        return 20
    if clean == "metadata_only":
        return 10
    return 0


def _merge_attached_skill(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for field in ATTACHED_SKILL_FIELDS:
        value = incoming.get(field)
        if not _has_non_empty_value(value):
            continue
        if field == "load_level":
            current_rank = _load_level_rank(str(merged.get(field) or ""))
            next_rank = _load_level_rank(str(value))
            if next_rank >= current_rank:
                merged[field] = value
            continue
        merged[field] = value
    return merged


def _expand_skill_entries(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    if isinstance(value, str):
        clean = value.strip()
        if clean:
            out.append({"skill_id": clean})
        return out

    if isinstance(value, list):
        for item in value:
            out.extend(_expand_skill_entries(item))
        return out

    if isinstance(value, dict):
        if any(key in value for key in ("skill_id", "id", "slug", "skill", "skill_name", "load_level")):
            out.append(dict(value))
            return out

        for map_key, map_value in value.items():
            if isinstance(map_value, dict):
                entry = dict(map_value)
                entry.setdefault("skill_id", str(map_key or "").strip())
                out.append(entry)
            elif isinstance(map_value, str):
                out.append({"skill_id": str(map_key or "").strip(), "status": map_value.strip()})
            elif map_value is True:
                out.append({"skill_id": str(map_key or "").strip()})
        return out

    return out


def _text_map(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key or "").strip()
        if not key:
            continue
        text = _clean_text(raw_value)
        if text:
            out[key] = text
    return out


def extract_attached_skills(
    runtime_member: dict[str, Any],
    *,
    skill_lookup: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(runtime_member, dict):
        return []

    raw_entries: list[dict[str, Any]] = []
    for key in SKILL_ATTACHMENT_KEYS:
        if key not in runtime_member:
            continue
        raw_entries.extend(_expand_skill_entries(runtime_member.get(key)))

    if not raw_entries:
        return []

    load_level_map = _text_map(runtime_member.get("skill_load_levels") or runtime_member.get("skillLoadLevels"))
    selection_reason_map = _text_map(runtime_member.get("skill_selection_reasons") or runtime_member.get("skillSelectionReasons"))
    selected_by_map = _text_map(runtime_member.get("skill_selected_by") or runtime_member.get("skillSelectedBy"))

    items: dict[str, dict[str, Any]] = {}
    for raw in raw_entries:
        normalized = _normalize_attached_skill(raw, skill_lookup=skill_lookup)
        if not normalized:
            continue
        skill_id = _skill_id_key(normalized.get("skill_id"))
        if not skill_id:
            continue

        if skill_id in load_level_map and not _has_non_empty_value(raw.get("load_level")):
            normalized["load_level"] = normalize_load_level(load_level_map[skill_id])
        if skill_id in selection_reason_map and not _has_non_empty_value(raw.get("selection_reason")):
            normalized["selection_reason"] = selection_reason_map[skill_id]
        if skill_id in selected_by_map and not _has_non_empty_value(raw.get("selected_by")):
            normalized["selected_by"] = selected_by_map[skill_id]

        current = items.get(skill_id)
        items[skill_id] = _merge_attached_skill(current or {"skill_id": skill_id}, normalized)

    ordered = sorted(items.values(), key=lambda item: (str(item.get("skill_name") or "").lower(), str(item.get("skill_id") or "")))
    return ordered


def _is_runtime_member_record(value: Any) -> bool:
    if not isinstance(value, dict):
        return False

    if any(_has_non_empty_value(value.get(key)) for key in RUNTIME_MEMBER_ID_KEYS):
        return True

    hint_count = sum(1 for key in RUNTIME_MEMBER_HINT_KEYS if _has_non_empty_value(value.get(key)))
    return hint_count >= 2


def _extract_runtime_member_map(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, dict):
        return []
    out: list[dict[str, Any]] = []
    for map_key, value in raw.items():
        if not _is_runtime_member_record(value):
            continue
        member = dict(value)
        if not any(_has_non_empty_value(member.get(key)) for key in RUNTIME_MEMBER_ID_KEYS):
            clean_key = str(map_key or "").strip()
            if clean_key:
                member["agent_id"] = clean_key
        out.append(member)
    return out


def _extract_runtime_members(
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
            parsed = _jload(clean, None)
            if parsed is not None:
                return _extract_runtime_members(
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
            if _is_runtime_member_record(item):
                out.append(item)
            elif allow_string_ids and isinstance(item, str) and item.strip():
                out.append({"agent_id": item.strip()})
        return out

    if isinstance(raw, dict):
        if _is_runtime_member_record(raw):
            return [raw]
        if allow_keyed_map:
            return _extract_runtime_member_map(raw)
    return []


def _is_runtime_snapshot_shape(value: Any) -> bool:
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


def _team_plan_member_candidates(team_plan: Any, *, source_prefix: str) -> list[tuple[str, list[dict[str, Any]]]]:
    if isinstance(team_plan, str):
        parsed = _jload(team_plan, None)
        if parsed is not None:
            team_plan = parsed

    if not isinstance(team_plan, dict):
        return []

    out: list[tuple[str, list[dict[str, Any]]]] = []
    runtime_agents = _extract_runtime_members(team_plan.get("runtime_agents"), allow_string_ids=True, allow_keyed_map=True)
    if runtime_agents:
        out.append((f"{source_prefix}.runtime_agents", runtime_agents))

    for key in ("members", "agents"):
        members = _extract_runtime_members(team_plan.get(key), allow_keyed_map=True)
        if members:
            out.append((f"{source_prefix}.{key}", members))

    role_members = _extract_runtime_member_map(team_plan.get("roles"))
    if role_members:
        out.append((f"{source_prefix}.roles", role_members))

    return out


def _runtime_member_candidates_from_container(
    container: dict[str, Any],
    *,
    source_prefix: str,
) -> list[tuple[str, list[dict[str, Any]]]]:
    out: list[tuple[str, list[dict[str, Any]]]] = []

    runtime_snapshot = container.get("runtime_team_snapshot")
    if runtime_snapshot is None:
        runtime_snapshot = container.get("runtimeTeamSnapshot")
    if isinstance(runtime_snapshot, str):
        parsed = _jload(runtime_snapshot, None)
        if parsed is not None:
            runtime_snapshot = parsed

    if isinstance(runtime_snapshot, dict):
        snapshot_runtime_agents_value = runtime_snapshot.get("runtime_agents")
        if snapshot_runtime_agents_value is None:
            snapshot_runtime_agents_value = runtime_snapshot.get("runtimeAgents")
        canonical_runtime_agents = _extract_runtime_members(
            snapshot_runtime_agents_value,
            allow_string_ids=True,
            allow_keyed_map=True,
        )
        if canonical_runtime_agents:
            out.append((f"{source_prefix}runtime_team_snapshot.runtime_agents", canonical_runtime_agents))

        out.extend(
            _team_plan_member_candidates(
                runtime_snapshot.get("team_plan"),
                source_prefix=f"{source_prefix}runtime_team_snapshot.team_plan",
            )
        )

        for key in ("members", "agents"):
            members = _extract_runtime_members(runtime_snapshot.get(key), allow_keyed_map=True)
            if members:
                out.append((f"{source_prefix}runtime_team_snapshot.{key}", members))

    elif runtime_snapshot is not None:
        members = _extract_runtime_members(runtime_snapshot, allow_string_ids=True)
        if members:
            out.append((f"{source_prefix}runtime_team_snapshot", members))

    top_runtime_agents_value = container.get("runtime_agents")
    if top_runtime_agents_value is None:
        top_runtime_agents_value = container.get("runtimeAgents")
    top_runtime_agents = _extract_runtime_members(
        top_runtime_agents_value,
        allow_string_ids=True,
        allow_keyed_map=True,
    )
    if top_runtime_agents:
        out.append((f"{source_prefix}runtime_agents", top_runtime_agents))

    if _is_runtime_snapshot_shape(container):
        for key in ("members", "agents"):
            members = _extract_runtime_members(container.get(key), allow_keyed_map=True)
            if members:
                out.append((f"{source_prefix}{key}", members))

    out.extend(
        _team_plan_member_candidates(
            container.get("team_plan"),
            source_prefix=f"{source_prefix}team_plan",
        )
    )
    return out


def _runtime_source_priority(source_key: str) -> int:
    clean = str(source_key or "")
    if clean.endswith("runtime_team_snapshot.runtime_agents"):
        return 70
    if clean.endswith("runtime_team_snapshot.team_plan.runtime_agents"):
        return 65
    if clean.endswith("runtime_agents"):
        return 60
    if ".runtime_team_snapshot." in clean:
        return 50
    if clean.endswith(".members") or clean.endswith(".agents"):
        return 40
    if ".team_plan." in clean:
        return 30
    if clean.endswith("runtime_team_snapshot"):
        return 20
    return 10


def _normalize_runtime_source_key(source_key: Any) -> str:
    clean = str(source_key or "").strip()
    if not clean:
        return "runtime_snapshot"
    if clean.endswith("runtime_team_snapshot.runtime_agents"):
        return "runtime_team_snapshot.runtime_agents"
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


def extract_runtime_snapshot_with_members(nodes: Iterable[Any]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    sorted_nodes = sorted([node for node in nodes if str(getattr(node, "type", "")) in {"Run", "Step"}], key=_created_sort_key)
    for node in sorted_nodes:
        payload = _node_payload(node)
        source_candidates = _runtime_member_candidates_from_container(payload, source_prefix="")
        for block_name in RUNTIME_NESTED_BLOCK_KEYS:
            block = payload.get(block_name)
            if isinstance(block, dict):
                source_candidates.extend(
                    _runtime_member_candidates_from_container(
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
                }
            )

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            str(item.get("created_at") or ""),
            _runtime_source_priority(str(item.get("source_key") or "")),
            str(item.get("node_id") or ""),
        )
    )
    return candidates[-1]


def _normalize_status(raw: Any) -> str:
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


def extract_runtime_agents_with_skills(
    nodes: Iterable[Any],
    *,
    skill_lookup: dict[str, dict[str, Any]] | None = None,
    source: str = "runtime_snapshot",
) -> dict[str, Any]:
    snapshot = extract_runtime_snapshot_with_members(nodes)
    if not snapshot:
        return {
            "snapshot_node_id": None,
            "snapshot_node_type": None,
            "snapshot_source_key": None,
            "snapshot_source_path": None,
            "items": [],
        }

    runtime_source_path = str(snapshot.get("source_key") or "")
    runtime_source_key = _normalize_runtime_source_key(runtime_source_path)

    items: list[dict[str, Any]] = []
    for raw_member in snapshot.get("members", []):
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

        attached_skills = extract_attached_skills(raw_member, skill_lookup=skill_lookup)

        context_pack_id = _clean_text(raw_member.get("context_pack_id") or raw_member.get("contextPackId"))
        if not context_pack_id:
            context_pack = raw_member.get("context_pack") or raw_member.get("contextPack")
            if isinstance(context_pack, dict):
                context_pack_id = _clean_text(
                    context_pack.get("context_pack_id")
                    or context_pack.get("contextPackId")
                    or context_pack.get("id")
                )

        items.append(
            {
                "runtime_instance_id": runtime_instance_id,
                "agent_id": agent_id or runtime_instance_id or template_id or "unknown-runtime-agent",
                "role_label": _clean_text(raw_member.get("role_label") or raw_member.get("role") or raw_member.get("title")),
                "name": _clean_text(raw_member.get("name") or raw_member.get("display_name") or raw_member.get("label")),
                "template_id": template_id,
                "provider": _clean_text(raw_member.get("provider") or raw_member.get("llm_provider") or llm_info.get("provider")),
                "model": _clean_text(raw_member.get("model") or raw_member.get("model_name") or llm_info.get("model")),
                "runtime_status": _normalize_status(raw_member.get("runtime_status") or raw_member.get("status") or raw_member.get("state")),
                "attached_skills": attached_skills,
                "context_pack_id": context_pack_id,
                "source": source,
                "source_key": runtime_source_key,
                "source_path": runtime_source_path or None,
                "snapshot_node_id": snapshot.get("node_id"),
                "snapshot_node_type": snapshot.get("node_type"),
                "enabled": bool(raw_member.get("enabled", True)),
            }
        )

    return {
        "snapshot_node_id": snapshot.get("node_id"),
        "snapshot_node_type": snapshot.get("node_type"),
        "snapshot_source_key": runtime_source_key,
        "snapshot_source_path": runtime_source_path or None,
        "items": items,
    }


def _normalize_skill_usage_event(
    raw: Any,
    *,
    fallback_skill_id: str | None = None,
    fallback_timestamp: str | None = None,
    fallback_event_type: str | None = None,
    skill_lookup: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if isinstance(raw, str):
        skill_id = _clean_text(raw) or fallback_skill_id
        if not skill_id:
            return None
        package = (skill_lookup or {}).get(skill_id) if skill_lookup else None
        return {
            "skill_id": skill_id,
            "skill_name": _clean_text(package.get("name")) if package else None,
            "event_type": fallback_event_type or "used",
            "timestamp": fallback_timestamp,
            "payload_summary": "",
        }

    if not isinstance(raw, dict):
        return None

    skill_id = _clean_text(raw.get("skill_id") or raw.get("id") or raw.get("skill") or raw.get("slug")) or fallback_skill_id
    if not skill_id:
        return None

    package = (skill_lookup or {}).get(skill_id) if skill_lookup else None

    return {
        "skill_id": skill_id,
        "skill_name": _clean_text(raw.get("skill_name") or raw.get("name") or raw.get("title")) or (
            _clean_text(package.get("name")) if package else None
        ),
        "event_type": _clean_text(raw.get("event_type") or raw.get("type") or raw.get("action") or raw.get("status")) or (fallback_event_type or "used"),
        "timestamp": _clean_text(raw.get("timestamp") or raw.get("ts") or raw.get("time") or raw.get("created_at")) or fallback_timestamp,
        "payload_summary": _short_payload_summary(
            raw.get("payload_summary")
            or raw.get("summary")
            or raw.get("message")
            or raw.get("reason")
            or raw.get("result")
            or raw
        ),
        "runtime_instance_id": _clean_text(raw.get("runtime_instance_id") or raw.get("instance_id")),
        "selection_reason": _clean_text(raw.get("selection_reason") or raw.get("reason")),
        "load_level": normalize_load_level(raw.get("load_level") or raw.get("loadLevel") or raw.get("level")),
    }


def _expand_usage_events_value(value: Any) -> list[Any]:
    if isinstance(value, str):
        clean = value.strip()
        if not clean:
            return []
        if clean.startswith("{") or clean.startswith("["):
            parsed = _jload(clean, None)
            if parsed is not None:
                return _expand_usage_events_value(parsed)
        return [clean]

    if isinstance(value, list):
        out: list[Any] = []
        for item in value:
            out.extend(_expand_usage_events_value(item))
        return out

    if isinstance(value, dict):
        # map form: skill_id -> event payload
        if any(key in value for key in ("skill_id", "id", "skill", "event_type", "type")):
            return [value]

        out: list[Any] = []
        for map_key, map_value in value.items():
            if isinstance(map_value, dict):
                entry = dict(map_value)
                entry.setdefault("skill_id", str(map_key or "").strip())
                out.append(entry)
            elif isinstance(map_value, list):
                for item in map_value:
                    if isinstance(item, dict):
                        entry = dict(item)
                        entry.setdefault("skill_id", str(map_key or "").strip())
                        out.append(entry)
                    elif isinstance(item, str):
                        out.append({"skill_id": str(map_key or "").strip(), "event_type": item.strip()})
            elif isinstance(map_value, str):
                out.append({"skill_id": str(map_key or "").strip(), "event_type": map_value.strip()})
        return out

    return []


def extract_skill_usage_events(
    nodes: Iterable[Any],
    *,
    skill_lookup: dict[str, dict[str, Any]] | None = None,
    max_items: int = 240,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for node in sorted([item for item in nodes if str(getattr(item, "type", "")) in {"Run", "Step"}], key=_created_sort_key):
        node_payload = _node_payload(node)
        fallback_timestamp = _clean_text(getattr(node, "created_at", None))

        for prefix, container in _iter_payload_containers(node_payload):
            for key in SKILL_USAGE_EVENT_KEYS:
                if key not in container:
                    continue
                raw_value = container.get(key)
                raw_events = _expand_usage_events_value(raw_value)
                for raw_event in raw_events:
                    normalized = _normalize_skill_usage_event(
                        raw_event,
                        fallback_timestamp=fallback_timestamp,
                        fallback_event_type="used",
                        skill_lookup=skill_lookup,
                    )
                    if not normalized:
                        continue
                    normalized["source"] = f"{prefix}{key}"
                    normalized["node_id"] = str(getattr(node, "id", "") or "")
                    normalized["node_type"] = str(getattr(node, "type", "") or "")
                    normalized["run_id"] = _clean_text(container.get("run_id") or node_payload.get("run_id"))
                    events.append(normalized)

            # direct shape fallback
            direct_skill_id = _clean_text(container.get("skill_id") or container.get("skill") or container.get("selected_skill_id"))
            direct_event_type = _clean_text(container.get("event_type") or container.get("skill_event_type"))
            if direct_skill_id and direct_event_type:
                normalized = _normalize_skill_usage_event(
                    {
                        "skill_id": direct_skill_id,
                        "event_type": direct_event_type,
                        "timestamp": container.get("timestamp") or container.get("ts"),
                        "payload_summary": container.get("summary") or container.get("reason") or container.get("result"),
                        "load_level": container.get("load_level") or container.get("skill_load_level"),
                        "selection_reason": container.get("selection_reason"),
                        "runtime_instance_id": container.get("runtime_instance_id"),
                    },
                    fallback_timestamp=fallback_timestamp,
                    skill_lookup=skill_lookup,
                )
                if normalized:
                    normalized["source"] = f"{prefix}direct_skill_event"
                    normalized["node_id"] = str(getattr(node, "id", "") or "")
                    normalized["node_type"] = str(getattr(node, "type", "") or "")
                    normalized["run_id"] = _clean_text(container.get("run_id") or node_payload.get("run_id"))
                    events.append(normalized)

    deduped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for event in events:
        key = (
            str(event.get("skill_id") or ""),
            str(event.get("event_type") or ""),
            str(event.get("timestamp") or ""),
            str(event.get("node_id") or ""),
        )
        if key not in deduped:
            deduped[key] = event
            continue

        existing = deduped[key]
        # Keep richer payload_summary/selection details when duplicates collide.
        if len(str(event.get("payload_summary") or "")) > len(str(existing.get("payload_summary") or "")):
            existing["payload_summary"] = event.get("payload_summary")
        if _has_non_empty_value(event.get("selection_reason")):
            existing["selection_reason"] = event.get("selection_reason")
        if _has_non_empty_value(event.get("runtime_instance_id")):
            existing["runtime_instance_id"] = event.get("runtime_instance_id")
        if _has_non_empty_value(event.get("load_level")):
            existing["load_level"] = event.get("load_level")

    ordered = sorted(
        deduped.values(),
        key=lambda item: (
            str(item.get("timestamp") or ""),
            str(item.get("node_id") or ""),
            str(item.get("skill_id") or ""),
        ),
    )
    if len(ordered) > max_items:
        ordered = ordered[-max_items:]
    return ordered
