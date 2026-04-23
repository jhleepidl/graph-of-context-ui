from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session

from app.models import Thread

HARNESS_SPEC_SCHEMA_VERSION = "openharness.spec/v1"
ORCHESTRATION_ROLE_IDS = {"planner", "router", "system", "orchestrator", "supervisor", "operator"}
HARNESS_DELIVERY_MODES = {"compression_only", "compression_plus_appendix", "projection_only", "projection_preferred"}
DEFAULT_DELIVERY_MODE = "compression_plus_appendix"
DEFAULT_APPENDIX_CHAR_BUDGET_RATIO = 0.35
DEFAULT_BUDGET_TIER = "medium"
DEFAULT_RISK_LEVEL = "standard"
DEFAULT_HARNESS_NAME = "OpenHarness Default"
SUMMARY_ROLE_IDS = [
    "operator",
    "planner",
    "router",
    "system",
    "orchestrator",
    "supervisor",
    "verifier",
    "builder",
    "researcher",
    "analyst",
    "coder",
]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def _jdump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _clean_text(value: Any, *, max_len: int = 240) -> str | None:
    clean = str(value or "").strip()
    if not clean:
        return None
    return clean[: max_len - 3] + "..." if len(clean) > max_len else clean


def _clean_list_of_text(values: Any, *, max_items: int = 24, max_len: int = 64) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values if isinstance(values, list) else []:
        clean = _clean_text(value, max_len=max_len)
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
        if len(out) >= max_items:
            break
    return out


def _clean_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _clamp_ratio(value: Any, fallback: float = DEFAULT_APPENDIX_CHAR_BUDGET_RATIO) -> float:
    try:
        ratio = float(value)
    except Exception:
        ratio = fallback
    return max(0.0, min(ratio, 1.0))


def _normalize_delivery_mode(value: Any, fallback: str = "compression_plus_appendix") -> str:
    clean = _clean_text(value, max_len=64)
    normalized = (clean or fallback).lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in HARNESS_DELIVERY_MODES else fallback


def _normalize_role_delivery(raw: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in _clean_mapping(raw).items():
        role_id = _clean_text(key, max_len=64)
        if role_id:
            out[role_id.lower()] = _normalize_delivery_mode(value)
    return out


def default_harness_spec() -> dict[str, Any]:
    return {
        "schema_version": HARNESS_SPEC_SCHEMA_VERSION,
        "metadata": {
            "name": DEFAULT_HARNESS_NAME,
            "description": "Default visible/editable/shareable harness policy bundle.",
            "tags": ["default", "governed-memory", "runtime"],
            "visibility": "workspace",
            "updated_at": None,
        },
        "projection_policy": {
            "normalize_orchestration_roles_to_operator": True,
            "blocked_reason_detail": "standard",
            "projection_appendix_enabled_by_default": True,
        },
        "compression_policy": {
            "enabled": True,
            "default_budget_tier": DEFAULT_BUDGET_TIER,
            "default_risk_level": DEFAULT_RISK_LEVEL,
            "default_delivery_mode": DEFAULT_DELIVERY_MODE,
            "appendix_char_budget_ratio": DEFAULT_APPENDIX_CHAR_BUDGET_RATIO,
            "role_delivery": {
                "operator": "compression_plus_appendix",
                "planner": "compression_plus_appendix",
                "verifier": "compression_plus_appendix",
                "builder": "compression_only",
                "researcher": "compression_only",
                "analyst": "compression_only",
                "coder": "compression_only",
            },
        },
        "tool_policy": {"tool_rag_enabled": True, "tool_view_mode": "task_scoped"},
        "approval_policy": {"deny_feedback_mode": "structured_feedback", "default_escalation": "operator"},
        "audit_policy": {
            "timeline_enabled": True,
            "cross_reference_enabled": True,
            "show_lifecycle": True,
            "show_conflict_history": True,
        },
        "sharing": {"shareable": True, "exportable": True},
    }


def normalize_harness_spec(raw: Any) -> dict[str, Any]:
    base = default_harness_spec()
    incoming = _clean_mapping(raw)
    metadata = _clean_mapping(incoming.get("metadata"))
    base["metadata"] = {**base["metadata"], **{k: v for k, v in metadata.items() if v is not None}}
    base["metadata"]["name"] = _clean_text(base["metadata"].get("name"), max_len=120) or DEFAULT_HARNESS_NAME
    base["metadata"]["description"] = _clean_text(base["metadata"].get("description"), max_len=400) or "Harness policy bundle"
    base["metadata"]["visibility"] = _clean_text(base["metadata"].get("visibility"), max_len=64) or "workspace"
    base["metadata"]["tags"] = _clean_list_of_text(base["metadata"].get("tags"), max_items=16, max_len=48)
    base["metadata"]["updated_at"] = _clean_text(base["metadata"].get("updated_at"), max_len=64)

    projection = _clean_mapping(incoming.get("projection_policy"))
    base["projection_policy"] = {**base["projection_policy"], **{k: v for k, v in projection.items() if v is not None}}
    base["projection_policy"]["normalize_orchestration_roles_to_operator"] = bool(base["projection_policy"].get("normalize_orchestration_roles_to_operator") is not False)
    base["projection_policy"]["projection_appendix_enabled_by_default"] = bool(base["projection_policy"].get("projection_appendix_enabled_by_default") is not False)

    compression = _clean_mapping(incoming.get("compression_policy"))
    merged_compression = {**base["compression_policy"], **{k: v for k, v in compression.items() if k != "role_delivery" and v is not None}}
    merged_compression["enabled"] = bool(merged_compression.get("enabled") is not False)
    merged_compression["default_budget_tier"] = _clean_text(merged_compression.get("default_budget_tier"), max_len=32) or DEFAULT_BUDGET_TIER
    merged_compression["default_risk_level"] = _clean_text(merged_compression.get("default_risk_level"), max_len=32) or DEFAULT_RISK_LEVEL
    merged_compression["default_delivery_mode"] = _normalize_delivery_mode(merged_compression.get("default_delivery_mode"))
    merged_compression["appendix_char_budget_ratio"] = _clamp_ratio(merged_compression.get("appendix_char_budget_ratio"))
    merged_compression["role_delivery"] = {**_normalize_role_delivery(base["compression_policy"].get("role_delivery")), **_normalize_role_delivery(compression.get("role_delivery"))}
    base["compression_policy"] = merged_compression

    for section in ("tool_policy", "approval_policy", "audit_policy", "sharing"):
        incoming_section = _clean_mapping(incoming.get(section))
        base[section] = {**base[section], **{k: v for k, v in incoming_section.items() if v is not None}}
    base["tool_policy"]["tool_rag_enabled"] = bool(base["tool_policy"].get("tool_rag_enabled") is not False)
    for key in ("timeline_enabled", "cross_reference_enabled", "show_lifecycle", "show_conflict_history"):
        base["audit_policy"][key] = bool(base["audit_policy"].get(key) is not False)
    base["sharing"]["shareable"] = bool(base["sharing"].get("shareable") is not False)
    base["sharing"]["exportable"] = bool(base["sharing"].get("exportable") is not False)
    base["schema_version"] = HARNESS_SPEC_SCHEMA_VERSION
    return base


def harness_spec_hash(spec: Any) -> str:
    normalized = normalize_harness_spec(spec)
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(encoded.encode("utf-8")).hexdigest()[:16]


def _meta_payload(thread: Thread) -> dict[str, Any]:
    payload = _jload(thread.meta_json or "{}", {})
    return payload if isinstance(payload, dict) else {}


def get_thread_harness_spec(thread: Thread) -> dict[str, Any]:
    meta = _meta_payload(thread)
    return normalize_harness_spec(_clean_mapping(_clean_mapping(meta.get("openharness")).get("harness_spec")))


def resolve_harness_delivery_policy(spec: Any, *, role_id: str | None = None) -> dict[str, Any]:
    normalized = normalize_harness_spec(spec)
    compression = _clean_mapping(normalized.get("compression_policy"))
    projection = _clean_mapping(normalized.get("projection_policy"))
    role_delivery = _normalize_role_delivery(compression.get("role_delivery"))
    requested = (_clean_text(role_id, max_len=64) or "").lower()
    effective = "operator" if projection.get("normalize_orchestration_roles_to_operator") is not False and requested in ORCHESTRATION_ROLE_IDS else requested
    delivery_mode = _normalize_delivery_mode(role_delivery.get(effective) or role_delivery.get(requested) or compression.get("default_delivery_mode"))
    appendix_enabled = bool(projection.get("projection_appendix_enabled_by_default") is not False)
    if delivery_mode == "compression_only":
        appendix_enabled = False
    elif delivery_mode == "projection_only":
        appendix_enabled = True
    ratio = _clamp_ratio(compression.get("appendix_char_budget_ratio"))
    return {
        "requested_role_id": requested or None,
        "effective_role_id": effective or None,
        "delivery_mode": delivery_mode,
        "appendix_enabled": appendix_enabled,
        "appendix_char_budget_ratio": ratio,
        "budget_tier": _clean_text(compression.get("default_budget_tier"), max_len=32) or DEFAULT_BUDGET_TIER,
        "risk_level": _clean_text(compression.get("default_risk_level"), max_len=32) or DEFAULT_RISK_LEVEL,
    }


def _build_delivery_policy_summary(spec: Any) -> dict[str, Any]:
    normalized = normalize_harness_spec(spec)
    compression = _clean_mapping(normalized.get("compression_policy"))
    projection = _clean_mapping(normalized.get("projection_policy"))
    return {
        "default_delivery_mode": _normalize_delivery_mode(compression.get("default_delivery_mode")),
        "appendix_char_budget_ratio": _clamp_ratio(compression.get("appendix_char_budget_ratio")),
        "default_budget_tier": _clean_text(compression.get("default_budget_tier"), max_len=32) or DEFAULT_BUDGET_TIER,
        "default_risk_level": _clean_text(compression.get("default_risk_level"), max_len=32) or DEFAULT_RISK_LEVEL,
        "projection_appendix_enabled_by_default": bool(projection.get("projection_appendix_enabled_by_default") is not False),
        "normalize_orchestration_roles_to_operator": bool(projection.get("normalize_orchestration_roles_to_operator") is not False),
    }


def _build_resolved_role_delivery_summary(spec: Any) -> dict[str, dict[str, Any]]:
    normalized = normalize_harness_spec(spec)
    compression = _clean_mapping(normalized.get("compression_policy"))
    raw_role_delivery = _normalize_role_delivery(compression.get("role_delivery"))
    role_ids: list[str] = []
    for role_id in SUMMARY_ROLE_IDS + list(raw_role_delivery.keys()):
        clean_role_id = _clean_text(role_id, max_len=64)
        if not clean_role_id:
            continue
        lowered = clean_role_id.lower()
        if lowered in role_ids:
            continue
        role_ids.append(lowered)
    return {role_id: resolve_harness_delivery_policy(normalized, role_id=role_id) for role_id in role_ids}


def build_harness_summary(spec: Any) -> dict[str, Any]:
    normalized = normalize_harness_spec(spec)
    compression = _clean_mapping(normalized.get("compression_policy"))
    audit = _clean_mapping(normalized.get("audit_policy"))
    sharing = _clean_mapping(normalized.get("sharing"))
    metadata = _clean_mapping(normalized.get("metadata"))
    delivery_policy = _build_delivery_policy_summary(normalized)
    resolved_delivery = _build_resolved_role_delivery_summary(normalized)
    return {
        "schema_version": HARNESS_SPEC_SCHEMA_VERSION,
        "spec_hash": harness_spec_hash(normalized),
        "name": _clean_text(metadata.get("name"), max_len=120) or DEFAULT_HARNESS_NAME,
        "description": _clean_text(metadata.get("description"), max_len=400),
        "tags": _clean_list_of_text(metadata.get("tags"), max_items=16, max_len=48),
        "visibility": _clean_text(metadata.get("visibility"), max_len=64) or "workspace",
        "shareable": bool(sharing.get("shareable") is not False),
        "exportable": bool(sharing.get("exportable") is not False),
        "compression_enabled": bool(compression.get("enabled") is not False),
        "delivery_policy": delivery_policy,
        "role_delivery": _normalize_role_delivery(compression.get("role_delivery")),
        "resolved_role_delivery": resolved_delivery,
        "audit_flags": {
            "timeline_enabled": bool(audit.get("timeline_enabled") is not False),
            "cross_reference_enabled": bool(audit.get("cross_reference_enabled") is not False),
            "show_lifecycle": bool(audit.get("show_lifecycle") is not False),
            "show_conflict_history": bool(audit.get("show_conflict_history") is not False),
        },
        "updated_at": _clean_text(metadata.get("updated_at"), max_len=64),
    }

def save_thread_harness_spec(session: Session, thread: Thread, spec: Any) -> dict[str, Any]:
    normalized = normalize_harness_spec(spec)
    meta = _meta_payload(thread)
    openharness = _clean_mapping(meta.get("openharness"))
    openharness["harness_spec"] = normalized
    openharness["harness_spec_hash"] = harness_spec_hash(normalized)
    openharness["harness_spec_updated_at"] = _utc_iso()
    meta["openharness"] = openharness
    thread.meta_json = _jdump(meta)
    session.add(thread)
    session.commit()
    session.refresh(thread)
    return normalized
