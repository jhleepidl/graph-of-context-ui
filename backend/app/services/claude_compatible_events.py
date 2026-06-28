from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.services.static_project_manifest import (
    build_room_package_candidate,
    build_static_manifest_context_block,
    parse_project_manifest,
)

_RAW_FORBIDDEN_KEYS = {
    "content", "text", "body", "message", "prompt", "response", "answer", "transcript",
    "raw", "raw_text", "raw_prompt", "raw_response", "file_content", "diff", "patch",
    "secret", "token", "api_key", "authorization", "password",
}


def _clean(value: Any = "", max_len: int = 500, lower: bool = False) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()[:max_len]
    return text.lower() if lower else text


def _slug(value: Any = "", fallback: str = "unknown") -> str:
    text = re.sub(r"[^a-z0-9가-힣._:-]+", "_", _clean(value or fallback, 160, True)).strip("_")
    return text or fallback


def _stable_hash(value: Any = "") -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:24]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def strip_raw_fields(value: Any) -> Any:
    if isinstance(value, list):
        return [strip_raw_fields(x) for x in value]
    if not isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    for key, raw in value.items():
        lower = str(key or "").lower()
        if lower in _RAW_FORBIDDEN_KEYS:
            continue
        if any(part in lower for part in ("secret", "token", "password", "authorization")):
            continue
        out[key] = strip_raw_fields(raw)
    return out


def _boolish(value: Any) -> bool:
    return bool(re.match(r"^(1|true|yes|on|accepted|accept|approved|approve)$", str(value or "").strip(), re.I))


def _infer_event_type(event_type: str = "", action: str = "", tool_name: str = "", outcome: dict[str, Any] | None = None) -> str:
    raw = _clean(event_type or action, 160, True)
    tool = _clean(tool_name, 120, True)
    signal = _clean(_as_dict(outcome).get("signal") or _as_dict(outcome).get("status"), 80, True)
    if "subagent" in raw or "agent" in raw or "subagent" in tool:
        return "subagent_used"
    if "skill" in raw or "skill" in tool:
        return "skill_used"
    if re.search(r"correction|reject|revise|retry|수정|거절", raw) or re.search(r"reject|retry|correction", signal):
        return "user_correction_or_rejection"
    if re.search(r"accept|approve|apply|done|complete|승인|적용|완료", raw) or re.search(r"accepted|approved|success", signal):
        return "user_acceptance_or_success"
    if "hook" in raw:
        return "hook_event"
    if re.search(r"manifest|claude\.md|agents\.md|skill\.md", raw):
        return "project_manifest_used"
    if "tool" in raw or "call" in raw or tool:
        return "tool_used"
    return "claude_compatible_usage"


def _infer_task_archetype(value: str = "", extra: dict[str, Any] | None = None) -> str:
    text = f"{value}\n{json.dumps(strip_raw_fields(extra or {}), ensure_ascii=False)}".lower()
    if re.search(r"code|repo|test|build|lint|bug|patch|implementation|frontend|backend|코드|버그|패치|테스트", text):
        return "code_review_or_implementation"
    if re.search(r"research|paper|experiment|dataset|evaluation|논문|실험|평가", text):
        return "research_or_evaluation"
    if re.search(r"strategy|competitor|customer|product|market|roadmap|전략|경쟁사|시장", text):
        return "enterprise_strategy"
    return "general_project_work"


def _infer_routing_depth(value: str = "", extra: dict[str, Any] | None = None) -> str:
    text = f"{value}\n{json.dumps(strip_raw_fields(extra or {}), ensure_ascii=False)}".lower()
    if re.search(r"loop|multi-step|long-running|background|autonomous|반복|장기", text):
        return "team_loop_task"
    if re.search(r"review|compare|analyze|tool|subagent|skill|검토|분석|비교", text):
        return "team_task"
    return "ask"


def build_claude_compatible_room_event(body: dict[str, Any]) -> dict[str, Any]:
    meta = strip_raw_fields(_as_dict(body.get("metadata")))
    outcome = strip_raw_fields(_as_dict(body.get("outcome")))
    action = _clean(body.get("action") or body.get("event_type") or body.get("tool_name"), 300)
    archetype = _clean(body.get("task_archetype"), 120) or _infer_task_archetype(action, meta)
    depth = _clean(body.get("routing_depth"), 80) or _infer_routing_depth(action, meta)
    event_type = _infer_event_type(body.get("event_type") or "", body.get("action") or "", body.get("tool_name") or "", outcome)
    signal = _clean(outcome.get("signal") or outcome.get("status"), 120)
    return {
        "kind": "claude_compatible_room_event_v1",
        "ts": _clean(body.get("ts"), 80) or None,
        "source": _slug(body.get("source") or "claude_code", "claude_code"),
        "ids": {
            "project_root_hash": _stable_hash(body.get("project_root") or body.get("project_id") or body.get("room_id") or "project"),
            "project_id_hash": _stable_hash(body.get("project_id") or body.get("project_root") or body.get("room_id") or "project"),
            "room_id_hash": _stable_hash(body.get("room_id") or body.get("project_id") or body.get("project_root") or "room"),
            "user_id_hash": _stable_hash(body.get("user_id") or "user"),
            "session_id_hash": _stable_hash(body.get("session_id") or "session"),
        },
        "event_type": event_type,
        "task_archetype": archetype,
        "routing": {
            "depth": depth,
            "execution_shape": "single_agent" if depth == "ask" else ("bounded_team" if depth == "team_task" else "bounded_loop_team"),
        },
        "claude_artifact": {
            "manifest_type": _slug(body.get("manifest_type") or "", ""),
            "manifest_filename": _clean(body.get("manifest_filename") or body.get("manifest_file"), 160),
            "tool_name": _clean(body.get("tool_name"), 120),
            "subagent_name": _clean(body.get("subagent_name"), 120),
            "skill_name": _clean(body.get("skill_name"), 120),
        },
        "outcome": {
            "signal": signal,
            "accepted": bool(body.get("accepted") is True or _boolish(signal)),
            "user_corrected": bool(body.get("user_corrected") is True or re.search(r"correction|reject|retry", signal, re.I)),
        },
        "metadata": meta,
        "privacy": {
            "raw_text_included": False,
            "raw_project_files_included": False,
            "credentials_included": False,
            "ids_are_hashed": True,
            "suitable_for_goc_room_usage_collection": True,
        },
    }


def claude_event_to_room_usage_event(event: dict[str, Any]) -> dict[str, Any]:
    artifact = _as_dict(event.get("claude_artifact"))
    return {
        "kind": "room_usage_event_v1",
        "ts": event.get("ts"),
        "chat_id": _as_dict(event.get("ids")).get("room_id_hash", ""),
        "user_id": _as_dict(event.get("ids")).get("user_id_hash", ""),
        "event_type": event.get("event_type") or "claude_compatible_usage",
        "command": event.get("source") or "claude_compatible_surface",
        "goal": "",
        "room": {
            "name": "Claude-compatible Room",
            "domain_label": event.get("task_archetype") or "general_project_work",
            "default_depth": _as_dict(event.get("routing")).get("depth") or "ask",
            "default_agents": [x for x in [artifact.get("subagent_name"), artifact.get("skill_name")] if x],
            "memory_object_types": ["static_manifest_usage", "component_usage", "outcome_signal"],
            "package_id": f"claude_{artifact.get('manifest_type')}" if artifact.get("manifest_type") else "claude_compatible_room",
        },
        "recommendation": {
            "recommended": _as_dict(event.get("routing")).get("depth") or "ask",
            "action": "consider_promote_component" if _as_dict(event.get("outcome")).get("accepted") else ("review_component_or_schema" if _as_dict(event.get("outcome")).get("user_corrected") else "collect_more_usage"),
        },
        "signal_pack": {
            "task_archetype": event.get("task_archetype") or "general_project_work",
            "claude_compatible_source": event.get("source") or "claude_code",
            "artifact_type": artifact.get("manifest_type") or artifact.get("tool_name") or "",
            "accepted": _as_dict(event.get("outcome")).get("accepted") is True,
            "user_corrected": _as_dict(event.get("outcome")).get("user_corrected") is True,
            "raw_text_included": False,
        },
        "evolution": {
            "formation_mode": "imported_from_claude_compatible_usage_signal",
            "ai_role": "adapter_collector_not_authoritative_memory",
            "auto_apply": False,
            "schema_is_dynamic": True,
            "private_content_export": "never_by_default",
        },
        "extra": {"claude_compatible_event": event},
    }


def validate_claude_compatible_room_event(event: dict[str, Any]) -> tuple[bool, str]:
    encoded = json.dumps(event or {}, ensure_ascii=False)
    for key in _RAW_FORBIDDEN_KEYS:
        if f'"{key}"' in encoded:
            return False, f"forbidden_key:{key}"
    privacy = _as_dict(event.get("privacy"))
    if privacy.get("raw_text_included") is True or privacy.get("credentials_included") is True or privacy.get("raw_project_files_included") is True:
        return False, "privacy_boundary_violation"
    return True, "ok"


def import_claude_compatible_manifest_preview(filename: str, content: str, source: str = "claude_compatible_api") -> dict[str, Any]:
    manifest = parse_project_manifest(filename, content, source=source)
    return {
        "kind": "claude_compatible_manifest_import_preview_v1",
        "manifest": manifest,
        "room_package_candidate": build_room_package_candidate(manifest),
        "static_context_block": build_static_manifest_context_block(manifest),
        "collection_policy": {
            "stores_raw_files_by_default": False,
            "persistent_install_requires_user_approval": True,
            "private_memory_export": "never_by_default",
        },
    }
