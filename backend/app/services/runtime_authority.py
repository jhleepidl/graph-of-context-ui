from __future__ import annotations

import json
from typing import Any, Iterable

from app.services.runtime_snapshot import (
    created_sort_key as _created_sort_key,
    has_non_empty_value as _has_non_empty_value,
    iter_payload_containers as _iter_payload_containers,
    node_payload as _node_payload,
)


# Canonical ddalggak -> GoC interoperability contract.
RUNTIME_AUTHORITY_FIELDS = (
    "mode",
    "plan_source",
    "context_source",
    "agent_catalog_source",
    "conversation_team_source",
    "skill_catalog_source",
    "degraded_mode",
    "fallback_reason",
)

CANONICAL_AUTHORITY_BLOCK_KEYS = (
    "runtime_authority",
    "runtimeAuthority",
)

LEGACY_AUTHORITY_BLOCK_KEYS = (
    "authority",
    "authority_state",
    "authorityState",
)

AUTHORITY_BLOCK_KEYS = CANONICAL_AUTHORITY_BLOCK_KEYS + LEGACY_AUTHORITY_BLOCK_KEYS

MODE_KEYS = (
    "mode",
    "runtime_mode",
    "runtimeMode",
    "authority_mode",
    "authorityMode",
    "control_mode",
    "controlMode",
    "goc_mode",
    "gocMode",
)
PLAN_SOURCE_KEYS = (
    "plan_source",
    "planSource",
    "planning_source",
    "planningSource",
    "planner_source",
    "plannerSource",
    "plan_authority",
    "planAuthority",
)
CONTEXT_SOURCE_KEYS = (
    "context_source",
    "contextSource",
    "context_authority",
    "contextAuthority",
    "compiled_context_source",
    "compiledContextSource",
)
AGENT_CATALOG_SOURCE_KEYS = (
    "agent_catalog_source",
    "agentCatalogSource",
    "agent_source",
    "agentSource",
    "agent_authority_source",
    "agentAuthoritySource",
)
CONVERSATION_TEAM_SOURCE_KEYS = (
    "conversation_team_source",
    "conversationTeamSource",
    "team_source",
    "teamSource",
    "team_authority_source",
    "teamAuthoritySource",
)
SKILL_CATALOG_SOURCE_KEYS = (
    "skill_catalog_source",
    "skillCatalogSource",
    "skills_source",
    "skillsSource",
    "skill_source",
    "skillSource",
)
DEGRADED_MODE_KEYS = (
    "degraded_mode",
    "degradedMode",
    "degraded",
    "fallback_mode",
    "fallbackMode",
    "authority_degraded",
    "authorityDegraded",
    "goc_fallback",
    "gocFallback",
    "local_fallback",
    "localFallback",
)
FALLBACK_REASON_KEYS = (
    "fallback_reason",
    "fallbackReason",
    "degraded_reason",
    "degradedReason",
    "degrade_reason",
    "degradeReason",
    "degraded_message",
    "degradedMessage",
    "degrade_message",
    "degradeMessage",
    "authority_fallback_reason",
    "authorityFallbackReason",
    "fallback_message",
    "fallbackMessage",
)

NESTED_FALLBACK_REASON_KEYS = (
    *FALLBACK_REASON_KEYS,
    "reason",
    "message",
)

AUTHORITY_HINT_KEYS = set(
    PLAN_SOURCE_KEYS
    + CONTEXT_SOURCE_KEYS
    + AGENT_CATALOG_SOURCE_KEYS
    + CONVERSATION_TEAM_SOURCE_KEYS
    + SKILL_CATALOG_SOURCE_KEYS
    + DEGRADED_MODE_KEYS
    + FALLBACK_REASON_KEYS
)


def _jload(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str):
        return None
    clean = raw.strip()
    if not clean or (not clean.startswith("{") and not clean.startswith("[")):
        return None
    try:
        return json.loads(clean)
    except Exception:
        return None


def _clean_text(value: Any) -> str | None:
    clean = str(value or "").strip()
    return clean or None


def _pick(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key not in mapping:
            continue
        value = mapping.get(key)
        if _has_non_empty_value(value):
            return value
    return None


def _normalize_mode(value: Any) -> str | None:
    clean = str(value or "").strip().lower().replace("-", "_")
    if not clean:
        return None
    if clean in {"standalone", "local", "runtime", "ddalggak", "legacy"}:
        return "standalone"
    if clean in {"goc", "graph_of_context", "control_plane", "goc_enhanced"}:
        return "goc"
    return None


def _normalize_plan_source(value: Any) -> str | None:
    clean = str(value or "").strip().lower().replace("-", "_")
    if not clean:
        return None
    if clean in {"local_fallback", "fallback", "runtime_fallback", "fallback_local", "degraded_local"}:
        return "local_fallback"
    if clean in {"goc", "graph_of_context", "control_plane"}:
        return "goc"
    if clean in {"local", "runtime", "standalone", "planner_local"}:
        return "local"
    return None


def _normalize_local_goc_source(value: Any) -> str | None:
    clean = str(value or "").strip().lower().replace("-", "_")
    if not clean:
        return None
    if clean in {"goc", "graph_of_context", "control_plane"}:
        return "goc"
    if clean in {"local", "runtime", "standalone", "ddalggak", "legacy"}:
        return "local"
    return None


def _normalize_skill_source(value: Any) -> str | None:
    clean = str(value or "").strip().lower().replace("-", "_")
    if not clean:
        return None
    if clean in {"mixed", "hybrid", "both"}:
        return "mixed"
    if clean in {"goc", "graph_of_context", "control_plane"}:
        return "goc"
    if clean in {"local", "runtime", "standalone", "ddalggak"}:
        return "local"
    return None


def _coerce_bool(value: Any) -> bool | None:
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
    return None


def _extract_fallback_reason(value: Any) -> str | None:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, dict):
        reason = _pick(value, NESTED_FALLBACK_REASON_KEYS)
        return _clean_text(reason)
    return None


def default_runtime_authority() -> dict[str, Any]:
    return {
        "mode": "standalone",
        "plan_source": "local",
        "context_source": "local",
        "agent_catalog_source": "local",
        "conversation_team_source": "local",
        "skill_catalog_source": "local",
        "degraded_mode": False,
        "fallback_reason": None,
    }


def _extract_canonical_contract_from_mapping(mapping: dict[str, Any]) -> tuple[dict[str, Any], set[str]]:
    if not isinstance(mapping, dict):
        return {}, set()

    out: dict[str, Any] = {}
    explicit_fields: set[str] = set()

    if "mode" in mapping:
        mode = _normalize_mode(mapping.get("mode"))
        if mode:
            out["mode"] = mode
            explicit_fields.add("mode")

    if "plan_source" in mapping:
        plan_source = _normalize_plan_source(mapping.get("plan_source"))
        if plan_source:
            out["plan_source"] = plan_source
            explicit_fields.add("plan_source")

    if "context_source" in mapping:
        context_source = _normalize_local_goc_source(mapping.get("context_source"))
        if context_source:
            out["context_source"] = context_source
            explicit_fields.add("context_source")

    if "agent_catalog_source" in mapping:
        agent_catalog_source = _normalize_local_goc_source(mapping.get("agent_catalog_source"))
        if agent_catalog_source:
            out["agent_catalog_source"] = agent_catalog_source
            explicit_fields.add("agent_catalog_source")

    if "conversation_team_source" in mapping:
        conversation_team_source = _normalize_local_goc_source(mapping.get("conversation_team_source"))
        if conversation_team_source:
            out["conversation_team_source"] = conversation_team_source
            explicit_fields.add("conversation_team_source")

    if "skill_catalog_source" in mapping:
        skill_catalog_source = _normalize_skill_source(mapping.get("skill_catalog_source"))
        if skill_catalog_source:
            out["skill_catalog_source"] = skill_catalog_source
            explicit_fields.add("skill_catalog_source")

    if "degraded_mode" in mapping:
        degraded_mode = _coerce_bool(mapping.get("degraded_mode"))
        if degraded_mode is not None:
            out["degraded_mode"] = degraded_mode
            explicit_fields.add("degraded_mode")

    if "fallback_reason" in mapping:
        out["fallback_reason"] = _clean_text(mapping.get("fallback_reason"))
        explicit_fields.add("fallback_reason")

    return out, explicit_fields


def _extract_partial_from_mapping(
    mapping: dict[str, Any],
    *,
    allow_mode_without_hints: bool = False,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    has_hints = any(key in mapping for key in AUTHORITY_HINT_KEYS)

    mode_raw = _pick(mapping, MODE_KEYS)
    if mode_raw is not None and (allow_mode_without_hints or has_hints or _normalize_mode(mode_raw) is not None):
        mode = _normalize_mode(mode_raw)
        if mode:
            out["mode"] = mode

    plan_source = _normalize_plan_source(_pick(mapping, PLAN_SOURCE_KEYS))
    if plan_source:
        out["plan_source"] = plan_source

    context_source = _normalize_local_goc_source(_pick(mapping, CONTEXT_SOURCE_KEYS))
    if context_source:
        out["context_source"] = context_source

    agent_catalog_source = _normalize_local_goc_source(_pick(mapping, AGENT_CATALOG_SOURCE_KEYS))
    if agent_catalog_source:
        out["agent_catalog_source"] = agent_catalog_source

    conversation_team_source = _normalize_local_goc_source(_pick(mapping, CONVERSATION_TEAM_SOURCE_KEYS))
    if conversation_team_source:
        out["conversation_team_source"] = conversation_team_source

    skill_catalog_source = _normalize_skill_source(_pick(mapping, SKILL_CATALOG_SOURCE_KEYS))
    if skill_catalog_source:
        out["skill_catalog_source"] = skill_catalog_source

    degraded_raw = _pick(mapping, DEGRADED_MODE_KEYS)
    degraded = _coerce_bool(degraded_raw)
    if degraded is not None:
        out["degraded_mode"] = degraded

    fallback_reason = _clean_text(_pick(mapping, FALLBACK_REASON_KEYS))
    if not fallback_reason and "fallback" in mapping:
        fallback_reason = _extract_fallback_reason(mapping.get("fallback"))
    if not fallback_reason and "degraded" in mapping:
        fallback_reason = _extract_fallback_reason(mapping.get("degraded"))
    if fallback_reason:
        out["fallback_reason"] = fallback_reason

    return out


def _extract_runtime_authority_details_from_container(
    container: dict[str, Any],
) -> tuple[dict[str, Any], set[str], set[str]]:
    if not isinstance(container, dict):
        return {}, set(), set()

    merged: dict[str, Any] = {}
    explicit_fields: set[str] = set()
    canonical_fields: set[str] = set()

    for block_key in LEGACY_AUTHORITY_BLOCK_KEYS:
        if block_key not in container:
            continue
        block = _jload(container.get(block_key))
        if isinstance(block, dict):
            partial = _extract_partial_from_mapping(block, allow_mode_without_hints=True)
            if partial:
                merged.update(partial)
                explicit_fields.update(partial.keys())

    top_level_legacy = _extract_partial_from_mapping(container, allow_mode_without_hints=False)
    if top_level_legacy:
        merged.update(top_level_legacy)
        explicit_fields.update(top_level_legacy.keys())

    top_level_canonical, top_level_canonical_fields = _extract_canonical_contract_from_mapping(container)
    if top_level_canonical_fields:
        merged.update(top_level_canonical)
        explicit_fields.update(top_level_canonical_fields)
        canonical_fields.update(top_level_canonical_fields)

    for block_key in CANONICAL_AUTHORITY_BLOCK_KEYS:
        if block_key not in container:
            continue
        block = _jload(container.get(block_key))
        if not isinstance(block, dict):
            continue

        partial = _extract_partial_from_mapping(block, allow_mode_without_hints=True)
        if partial:
            merged.update(partial)
            explicit_fields.update(partial.keys())

        canonical_block, canonical_block_fields = _extract_canonical_contract_from_mapping(block)
        if canonical_block_fields:
            merged.update(canonical_block)
            explicit_fields.update(canonical_block_fields)
            canonical_fields.update(canonical_block_fields)

    return merged, explicit_fields, canonical_fields


def extract_runtime_authority_from_container(container: dict[str, Any]) -> dict[str, Any]:
    merged, _explicit_fields, _canonical_fields = _extract_runtime_authority_details_from_container(container)
    return merged


def _extract_runtime_authority_details_from_nodes(
    nodes: Iterable[Any],
    *,
    include_node_types: set[str] | None = None,
) -> tuple[dict[str, Any], set[str]]:
    allowed_types = include_node_types or {"Run", "Step"}
    legacy_values: dict[str, Any] = {}
    legacy_fields: set[str] = set()
    canonical_values: dict[str, Any] = {}
    canonical_fields: set[str] = set()

    sorted_nodes = sorted(
        [node for node in nodes if str(getattr(node, "type", "")) in allowed_types],
        key=_created_sort_key,
    )

    for node in sorted_nodes:
        payload = _node_payload(node)
        for _prefix, container in _iter_payload_containers(payload):
            partial, explicit_fields, container_canonical_fields = _extract_runtime_authority_details_from_container(container)
            if not explicit_fields:
                continue

            for field in explicit_fields:
                if field in container_canonical_fields:
                    canonical_values[field] = partial.get(field)
                    canonical_fields.add(field)
                    continue
                if field in canonical_fields:
                    continue
                legacy_values[field] = partial.get(field)
                legacy_fields.add(field)

    merged = dict(legacy_values)
    merged.update(canonical_values)
    return merged, legacy_fields | canonical_fields


def extract_runtime_authority_from_nodes(
    nodes: Iterable[Any],
    *,
    include_node_types: set[str] | None = None,
) -> dict[str, Any]:
    merged, _explicit_fields = _extract_runtime_authority_details_from_nodes(
        nodes,
        include_node_types=include_node_types,
    )
    return merged


def infer_conversation_team_source(agent_team: dict[str, Any] | None) -> str | None:
    if not isinstance(agent_team, dict):
        return None
    items = list(agent_team.get("items") or [])
    sources = {str(item.get("source") or "").strip().lower() for item in items if isinstance(item, dict)}
    if "conversation_membership" in sources:
        return "goc"
    if "runtime_snapshot" in sources or "inferred_from_steps" in sources:
        return "local"
    if _clean_text(agent_team.get("conversation_id")):
        return "goc"
    return None


def infer_agent_catalog_source(agent_team: dict[str, Any] | None) -> str | None:
    team_source = infer_conversation_team_source(agent_team)
    if team_source == "goc":
        return "goc"
    if team_source == "local":
        return "local"
    return None


def infer_skill_catalog_source(
    *,
    skill_packages: list[dict[str, Any]] | None,
    runtime_agents: list[dict[str, Any]] | None = None,
    usage_events: list[dict[str, Any]] | None = None,
    context_packs: list[dict[str, Any]] | None = None,
) -> str | None:
    packages = [pkg for pkg in (skill_packages or []) if isinstance(pkg, dict)]
    has_goc_catalog = any(str(pkg.get("source") or "").startswith("default_registry") for pkg in packages)
    has_runtime_catalog = any(
        not str(pkg.get("source") or "").startswith("default_registry")
        for pkg in packages
    )

    has_runtime_signals = False
    for agent in runtime_agents or []:
        if list(agent.get("attached_skills") or []):
            has_runtime_signals = True
            break
    if not has_runtime_signals and usage_events:
        has_runtime_signals = len(usage_events) > 0
    if not has_runtime_signals and context_packs:
        has_runtime_signals = any(list(pack.get("skill_items") or []) for pack in context_packs if isinstance(pack, dict))

    if has_runtime_catalog and has_goc_catalog:
        return "mixed"
    if has_runtime_signals and has_goc_catalog:
        return "mixed"
    if has_runtime_catalog:
        return "local"
    if has_goc_catalog:
        return "goc"
    return None


def derive_runtime_authority(
    *,
    nodes: Iterable[Any],
    agent_team: dict[str, Any] | None = None,
    skill_packages: list[dict[str, Any]] | None = None,
    runtime_agents: list[dict[str, Any]] | None = None,
    usage_events: list[dict[str, Any]] | None = None,
    context_packs: list[dict[str, Any]] | None = None,
    context_source_default: str | None = None,
    plan_source_default: str | None = None,
    mode_default: str | None = None,
) -> dict[str, Any]:
    explicit, explicit_fields = _extract_runtime_authority_details_from_nodes(nodes)
    authority = default_runtime_authority()
    authority.update(explicit)

    inferred_conversation_source = infer_conversation_team_source(agent_team)
    if inferred_conversation_source and "conversation_team_source" not in explicit_fields:
        authority["conversation_team_source"] = inferred_conversation_source

    inferred_agent_catalog_source = infer_agent_catalog_source(agent_team)
    if inferred_agent_catalog_source and "agent_catalog_source" not in explicit_fields:
        authority["agent_catalog_source"] = inferred_agent_catalog_source

    inferred_skill_source = infer_skill_catalog_source(
        skill_packages=skill_packages or [],
        runtime_agents=runtime_agents or [],
        usage_events=usage_events or [],
        context_packs=context_packs or [],
    )
    if inferred_skill_source and "skill_catalog_source" not in explicit_fields:
        authority["skill_catalog_source"] = inferred_skill_source

    if context_source_default and "context_source" not in explicit_fields:
        normalized_context_source = _normalize_local_goc_source(context_source_default)
        if normalized_context_source:
            authority["context_source"] = normalized_context_source

    if plan_source_default and "plan_source" not in explicit_fields:
        normalized_plan_source = _normalize_plan_source(plan_source_default)
        if normalized_plan_source:
            authority["plan_source"] = normalized_plan_source

    if "mode" not in explicit_fields:
        normalized_mode_default = _normalize_mode(mode_default) if mode_default else None
        if normalized_mode_default:
            authority["mode"] = normalized_mode_default
        else:
            source_modes = (
                authority.get("context_source"),
                authority.get("agent_catalog_source"),
                authority.get("conversation_team_source"),
            )
            authority["mode"] = "goc" if "goc" in source_modes or authority.get("plan_source") == "goc" else "standalone"

    degraded = bool(authority.get("degraded_mode"))
    if authority.get("plan_source") == "local_fallback":
        degraded = True
    fallback_reason = _clean_text(authority.get("fallback_reason"))
    if fallback_reason:
        degraded = True

    authority["degraded_mode"] = degraded
    authority["fallback_reason"] = fallback_reason if degraded else None

    # Ensure canonical schema shape and values.
    authority["mode"] = _normalize_mode(authority.get("mode")) or "standalone"
    authority["plan_source"] = _normalize_plan_source(authority.get("plan_source")) or "local"
    authority["context_source"] = _normalize_local_goc_source(authority.get("context_source")) or "local"
    authority["agent_catalog_source"] = _normalize_local_goc_source(authority.get("agent_catalog_source")) or "local"
    authority["conversation_team_source"] = _normalize_local_goc_source(authority.get("conversation_team_source")) or "local"
    authority["skill_catalog_source"] = _normalize_skill_source(authority.get("skill_catalog_source")) or "local"
    authority["degraded_mode"] = bool(authority.get("degraded_mode"))
    authority["fallback_reason"] = _clean_text(authority.get("fallback_reason")) if authority.get("degraded_mode") else None

    return {field: authority.get(field) for field in RUNTIME_AUTHORITY_FIELDS}


def apply_runtime_authority(
    payload: dict[str, Any],
    authority: dict[str, Any],
) -> dict[str, Any]:
    payload["runtime_authority"] = {field: authority.get(field) for field in RUNTIME_AUTHORITY_FIELDS}
    for field in RUNTIME_AUTHORITY_FIELDS:
        payload[field] = authority.get(field)
    return payload
