from __future__ import annotations

import json
from typing import Any, Iterable

from app.services.runtime_snapshot import (
    clean_list_of_text as _runtime_clean_list_of_text,
    iter_payload_containers as _runtime_iter_payload_containers,
    node_payload as _runtime_node_payload,
)
from app.services.learning_policy import is_learning_excluded_node


SKILL_PACKAGE_KEYS = (
    "skill_packages",
    "skillPackages",
    "skill_registry",
    "skillRegistry",
    "available_skills",
    "availableSkills",
    "skill_catalog",
    "skillCatalog",
    "skill_package",
    "skillPackage",
)

DEFAULT_SKILL_REGISTRY: dict[str, dict[str, Any]] = {
    "skill.thread_team_reconciliation.v1": {
        "id": "skill.thread_team_reconciliation.v1",
        "slug": "skill.thread_team_reconciliation.v1",
        "name": "Thread Team Reconciliation",
        "version": "v1",
        "description": "Align runtime role assignments with thread team defaults and policy constraints.",
        "category": "team_orchestration",
        "capability_tags": ["team", "reconciliation", "runtime"],
        "compatible_roles": ["orchestrator", "planner"],
        "instructions_ref": None,
        "resource_refs": [],
        "utility_refs": [],
        "visibility": "internal",
        "status": "active",
    },
    "skill.claim_evidence_audit.v1": {
        "id": "skill.claim_evidence_audit.v1",
        "slug": "skill.claim_evidence_audit.v1",
        "name": "Claim Evidence Audit",
        "version": "v1",
        "description": "Audit claims against available evidence, provenance, and conflict signals.",
        "category": "verification",
        "capability_tags": ["evidence", "claims", "audit"],
        "compatible_roles": ["analyst", "reviewer", "critic"],
        "instructions_ref": None,
        "resource_refs": [],
        "utility_refs": [],
        "visibility": "internal",
        "status": "active",
    },
    "skill.context_selection_policy.v1": {
        "id": "skill.context_selection_policy.v1",
        "slug": "skill.context_selection_policy.v1",
        "name": "Context Selection Policy",
        "version": "v1",
        "description": "Choose and prioritize shared, role-specific, and skill-specific context items.",
        "category": "context_governance",
        "capability_tags": ["context", "selection", "policy"],
        "compatible_roles": ["orchestrator", "planner", "analyst"],
        "instructions_ref": None,
        "resource_refs": [],
        "utility_refs": [],
        "visibility": "internal",
        "status": "active",
    },
    "skill.telegram_briefing.v1": {
        "id": "skill.telegram_briefing.v1",
        "slug": "skill.telegram_briefing.v1",
        "name": "Telegram Briefing",
        "version": "v1",
        "description": "Produce concise Telegram-ready briefings from run outputs and evidence.",
        "category": "delivery",
        "capability_tags": ["telegram", "briefing", "summary"],
        "compatible_roles": ["writer", "reporter"],
        "instructions_ref": None,
        "resource_refs": [],
        "utility_refs": [],
        "visibility": "internal",
        "status": "active",
    },
    "skill.run_trace_debugging.v1": {
        "id": "skill.run_trace_debugging.v1",
        "slug": "skill.run_trace_debugging.v1",
        "name": "Run Trace Debugging",
        "version": "v1",
        "description": "Diagnose runtime traces, step transitions, and tool/result anomalies.",
        "category": "operations",
        "capability_tags": ["debugging", "trace", "runtime"],
        "compatible_roles": ["operator", "debugger", "orchestrator"],
        "instructions_ref": None,
        "resource_refs": [],
        "utility_refs": [],
        "visibility": "internal",
        "status": "active",
    },
    "skill.kr_equity_analysis.v1": {
        "id": "skill.kr_equity_analysis.v1",
        "slug": "skill.kr_equity_analysis.v1",
        "name": "KR Equity Analysis",
        "version": "v1",
        "description": "Analyze Korean equity context, claims, and evidence for decision support.",
        "category": "domain_finance",
        "capability_tags": ["kr_equity", "analysis", "finance"],
        "compatible_roles": ["analyst", "researcher"],
        "instructions_ref": None,
        "resource_refs": [],
        "utility_refs": [],
        "visibility": "internal",
        "status": "active",
    },
    "skill.kskill_korean_stock_search.v1": {
        "id": "skill.kskill_korean_stock_search.v1",
        "slug": "skill.kskill_korean_stock_search.v1",
        "name": "k-skill Korean Stock Search",
        "version": "v1",
        "description": "Template package for integrating k-skill Korean stock search through a proxy adapter.",
        "category": "domain_finance",
        "capability_tags": ["k-skill", "stock", "krx"],
        "compatible_roles": ["analyst", "researcher"],
        "execution_adapter": {"kind": "http_proxy", "endpoint_env": "KSKILL_PROXY_BASE_URL", "external_tool_requirements": ["proxy_http"]},
        "credential_requirements": [{"key": "KSKILL_PROXY_BASE_URL", "required": False, "provider": "k-skill-proxy"}],
        "trust_level": "reviewed",
        "side_effect_level": "read_only",
        "instructions_ref": None,
        "resource_refs": [],
        "utility_refs": [],
        "visibility": "internal",
        "status": "active",
    },
    "skill.kskill_srt_booking.v1": {
        "id": "skill.kskill_srt_booking.v1",
        "slug": "skill.kskill_srt_booking.v1",
        "name": "k-skill SRT Booking",
        "version": "v1",
        "description": "Template package for integrating k-skill SRT booking with explicit login bindings.",
        "category": "travel",
        "capability_tags": ["k-skill", "srt", "booking"],
        "compatible_roles": ["operator", "planner"],
        "execution_adapter": {"kind": "python_cli", "entrypoint": "python -m srt_booking", "runtime_capabilities_required": ["shell_exec"]},
        "credential_requirements": [{"key": "KSKILL_SRT_ID", "required": True, "provider": "srt"}, {"key": "KSKILL_SRT_PASSWORD", "required": True, "provider": "srt"}],
        "trust_level": "reviewed",
        "side_effect_level": "transactional",
        "instructions_ref": None,
        "resource_refs": [],
        "utility_refs": [],
        "visibility": "internal",
        "status": "active",
    },
}


SKILL_PACKAGE_FIELDS = (
    "id",
    "slug",
    "name",
    "version",
    "description",
    "category",
    "capability_tags",
    "compatible_roles",
    "instructions_ref",
    "resource_refs",
    "utility_refs",
    "required_tools",
    "trigger_terms",
    "execution_adapter",
    "credential_requirements",
    "install_recipe",
    "source_package",
    "trust_level",
    "side_effect_level",
    "visibility",
    "status",
)


def _jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def _node_payload(node: Any) -> dict[str, Any]:
    return _runtime_node_payload(node)


def _clean_text(value: Any) -> str | None:
    clean = str(value or "").strip()
    return clean or None


def _clean_list_of_text(value: Any, *, limit: int = 32) -> list[str]:
    return _runtime_clean_list_of_text(value, limit=limit)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_execution_adapter(value: Any) -> dict[str, Any]:
    row = _as_dict(value)
    kind = _clean_text(row.get("kind") or row.get("adapter") or row.get("type") or row.get("mode")) or "prompt_only"
    adapter = {
        "kind": kind,
        "transport": _clean_text(row.get("transport") or row.get("channel") or row.get("protocol")),
        "entrypoint": _clean_text(row.get("entrypoint") or row.get("command") or row.get("path") or row.get("endpoint")),
        "endpoint": _clean_text(row.get("endpoint") or row.get("url")),
        "endpoint_env": _clean_text(row.get("endpoint_env") or row.get("endpointEnv") or row.get("url_env") or row.get("urlEnv")),
        "working_directory": _clean_text(row.get("working_directory") or row.get("workingDirectory") or row.get("cwd")),
        "runtime_capabilities_required": _clean_list_of_text(row.get("runtime_capabilities_required") or row.get("runtimeCapabilitiesRequired") or row.get("required_runtime_capabilities")),
        "external_tool_requirements": _clean_list_of_text(row.get("external_tool_requirements") or row.get("externalToolRequirements") or row.get("required_external_tools")),
        "install_hint": _clean_text(row.get("install_hint") or row.get("installHint")),
    }
    return {key: value for key, value in adapter.items() if _has_non_empty(value)}


def _normalize_credential_requirements(value: Any) -> list[dict[str, Any]]:
    items = value if isinstance(value, list) else []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in items:
        if isinstance(raw, str):
            raw = {"key": raw}
        row = _as_dict(raw)
        key = (_clean_text(row.get("key") or row.get("credential_key") or row.get("credentialKey") or row.get("env")) or "").upper()
        if not key or key in seen:
            continue
        seen.add(key)
        entry = {
            "key": key,
            "kind": _clean_text(row.get("kind") or row.get("type")) or "api_key",
            "required": bool(row.get("required", True)),
            "delivery": _clean_text(row.get("delivery") or row.get("delivery_method") or row.get("deliveryMethod")) or "job_env",
            "scope": _clean_text(row.get("scope")),
            "provider": _clean_text(row.get("provider")),
            "env_fallback": _clean_text(row.get("env_fallback") or row.get("envFallback") or row.get("env")),
            "prompt": _clean_text(row.get("prompt") or row.get("description")),
        }
        out.append({key: value for key, value in entry.items() if _has_non_empty(value) or key == "required"})
    return out


def _normalize_install_recipe(value: Any) -> dict[str, Any]:
    row = _as_dict(value)
    recipe = {
        "setup_steps": _clean_list_of_text(row.get("setup_steps") or row.get("setupSteps"), limit=64),
        "python_packages": _clean_list_of_text(row.get("python_packages") or row.get("pythonPackages"), limit=32),
        "npm_packages": _clean_list_of_text(row.get("npm_packages") or row.get("npmPackages"), limit=32),
        "system_packages": _clean_list_of_text(row.get("system_packages") or row.get("systemPackages"), limit=32),
        "verify_commands": _clean_list_of_text(row.get("verify_commands") or row.get("verifyCommands"), limit=32),
    }
    return {key: value for key, value in recipe.items() if _has_non_empty(value)}


def _normalize_source_package(value: Any) -> dict[str, Any]:
    row = _as_dict(value)
    source = {
        "type": _clean_text(row.get("type") or row.get("source_type") or row.get("sourceType")) or "catalog",
        "repo_url": _clean_text(row.get("repo_url") or row.get("repoUrl") or row.get("repository")),
        "repo_path": _clean_text(row.get("repo_path") or row.get("repoPath") or row.get("path")),
        "homepage": _clean_text(row.get("homepage")),
        "license": _clean_text(row.get("license")),
    }
    return {key: value for key, value in source.items() if _has_non_empty(value)}


def _has_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _iter_payload_containers(payload: dict[str, Any], *, prefix: str = "", depth: int = 0, max_depth: int = 2):
    yield from _runtime_iter_payload_containers(payload, prefix=prefix, depth=depth, max_depth=max_depth)


def _guess_skill_name(skill_id: str) -> str:
    parts = [chunk for chunk in skill_id.split(".") if chunk]
    if not parts:
        return skill_id
    core = parts[-2] if len(parts) >= 2 and parts[-1].startswith("v") else parts[-1]
    return core.replace("_", " ").replace("-", " ").strip().title() or skill_id


def _guess_version(skill_id: str) -> str | None:
    parts = [chunk for chunk in skill_id.split(".") if chunk]
    if not parts:
        return None
    tail = parts[-1]
    if tail.startswith("v") and len(tail) > 1 and tail[1:].isdigit():
        return tail
    return None


def _parse_skill_package_map(value: dict[str, Any], *, source_key: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if any(key in value for key in ("id", "skill_id", "slug", "name", "version")):
        pkg = normalize_skill_package(value, source_key=source_key)
        if pkg:
            out.append(pkg)
        return out

    for map_key, map_value in value.items():
        if isinstance(map_value, dict):
            candidate = dict(map_value)
            candidate.setdefault("id", str(map_key or "").strip())
            pkg = normalize_skill_package(candidate, source_key=f"{source_key}.{map_key}")
            if pkg:
                out.append(pkg)
        elif isinstance(map_value, str):
            pkg = normalize_skill_package(
                {"id": str(map_key or "").strip(), "name": map_value.strip()},
                source_key=f"{source_key}.{map_key}",
            )
            if pkg:
                out.append(pkg)
    return out


def _collect_skill_packages_from_value(value: Any, *, source_key: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(value, str):
        clean = value.strip()
        if not clean:
            return out
        if clean.startswith("{") or clean.startswith("["):
            parsed = _jload(clean, None)
            if parsed is not None:
                return _collect_skill_packages_from_value(parsed, source_key=source_key)
        pkg = normalize_skill_package({"id": clean}, source_key=source_key)
        if pkg:
            out.append(pkg)
        return out

    if isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, (dict, str, list)):
                out.extend(_collect_skill_packages_from_value(item, source_key=f"{source_key}[{index}]"))
        return out

    if isinstance(value, dict):
        out.extend(_parse_skill_package_map(value, source_key=source_key))
    return out


def normalize_skill_package(raw: Any, *, source_key: str | None = None) -> dict[str, Any] | None:
    if isinstance(raw, str):
        raw = {"id": raw}
    if not isinstance(raw, dict):
        return None

    skill_id = _clean_text(raw.get("id") or raw.get("skill_id") or raw.get("skillId") or raw.get("slug"))
    if not skill_id:
        return None

    slug = _clean_text(raw.get("slug")) or skill_id
    name = _clean_text(raw.get("name") or raw.get("title")) or _guess_skill_name(skill_id)
    version = _clean_text(raw.get("version")) or _guess_version(skill_id)

    package = {
        "id": skill_id,
        "slug": slug,
        "name": name,
        "version": version,
        "description": _clean_text(raw.get("description") or raw.get("summary")),
        "category": _clean_text(raw.get("category") or raw.get("type")),
        "capability_tags": _clean_list_of_text(raw.get("capability_tags") or raw.get("capabilities") or raw.get("tags")),
        "compatible_roles": _clean_list_of_text(raw.get("compatible_roles") or raw.get("roles") or raw.get("role_labels")),
        "instructions_ref": _clean_text(raw.get("instructions_ref") or raw.get("instructions_uri") or raw.get("instruction_ref")),
        "resource_refs": _clean_list_of_text(raw.get("resource_refs") or raw.get("resources") or raw.get("resource_ids")),
        "utility_refs": _clean_list_of_text(raw.get("utility_refs") or raw.get("utilities") or raw.get("tool_refs")),
        "required_tools": _clean_list_of_text(raw.get("required_tools") or raw.get("requiredTools") or raw.get("tool_ids") or raw.get("toolIds")),
        "trigger_terms": _clean_list_of_text(raw.get("trigger_terms") or raw.get("triggerTerms")),
        "execution_adapter": _normalize_execution_adapter(raw.get("execution_adapter") or raw.get("executionAdapter")),
        "credential_requirements": _normalize_credential_requirements(raw.get("credential_requirements") or raw.get("credentialRequirements")),
        "install_recipe": _normalize_install_recipe(raw.get("install_recipe") or raw.get("installRecipe")),
        "source_package": _normalize_source_package(raw.get("source_package") or raw.get("sourcePackage")),
        "trust_level": _clean_text(raw.get("trust_level") or raw.get("trustLevel")) or "reviewed",
        "side_effect_level": _clean_text(raw.get("side_effect_level") or raw.get("sideEffectLevel")) or "none",
        "visibility": _clean_text(raw.get("visibility")) or "internal",
        "status": _clean_text(raw.get("status")) or "active",
    }

    if source_key:
        package["source"] = source_key
    return package


def merge_skill_packages(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)

    for field in SKILL_PACKAGE_FIELDS:
        value = incoming.get(field)
        if isinstance(value, list):
            current = merged.get(field) if isinstance(merged.get(field), list) else []
            seen = {str(item) for item in current}
            combined = list(current)
            for item in value:
                item_key = str(item)
                if item_key in seen:
                    continue
                seen.add(item_key)
                combined.append(item)
            merged[field] = combined
        elif _has_non_empty(value):
            merged[field] = value

    # Keep latest source information if available.
    if _has_non_empty(incoming.get("source")):
        merged["source"] = incoming.get("source")

    # Ensure minimum canonical values always exist.
    merged.setdefault("id", incoming.get("id") or base.get("id"))
    merged.setdefault("slug", merged.get("id"))
    if not _has_non_empty(merged.get("name")) and _has_non_empty(merged.get("id")):
        merged["name"] = _guess_skill_name(str(merged["id"]))

    merged.setdefault("capability_tags", [])
    merged.setdefault("compatible_roles", [])
    merged.setdefault("resource_refs", [])
    merged.setdefault("utility_refs", [])
    merged.setdefault("visibility", "internal")
    merged.setdefault("status", "active")

    return merged


def extract_skill_packages_from_nodes(nodes: Iterable[Any]) -> dict[str, dict[str, Any]]:
    packages: dict[str, dict[str, Any]] = {}
    for node in sorted(list(nodes), key=lambda item: (str(getattr(item, "created_at", "") or ""), str(getattr(item, "id", "") or ""))):
        payload = _node_payload(node)
        if str(payload.get("resource_kind") or "").strip() == "skill_package":
            direct_pkg = normalize_skill_package(payload.get("skill_package") or payload, source_key=f"resource:{getattr(node, 'id', '')}")
            if direct_pkg:
                skill_id = str(direct_pkg.get("id") or "").strip()
                if skill_id:
                    current = packages.get(skill_id)
                    packages[skill_id] = merge_skill_packages(current or {"id": skill_id}, direct_pkg)

        for prefix, container in _iter_payload_containers(payload):
            for key in SKILL_PACKAGE_KEYS:
                if key not in container:
                    continue
                raw_value = container.get(key)
                for pkg in _collect_skill_packages_from_value(raw_value, source_key=f"{prefix}{key}"):
                    skill_id = str(pkg.get("id") or "").strip()
                    if not skill_id:
                        continue
                    current = packages.get(skill_id)
                    packages[skill_id] = merge_skill_packages(current or {"id": skill_id}, pkg)
    return packages


def build_skill_registry(
    *,
    nodes: Iterable[Any] | None = None,
    include_defaults: bool = True,
) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}

    if include_defaults:
        for skill_id, package in DEFAULT_SKILL_REGISTRY.items():
            normalized = normalize_skill_package(package, source_key="default_registry")
            if normalized:
                registry[skill_id] = normalized

    if nodes is not None:
        discovered = extract_skill_packages_from_nodes(nodes)
        for skill_id, package in discovered.items():
            existing = registry.get(skill_id)
            registry[skill_id] = merge_skill_packages(existing or {"id": skill_id}, package)

    return registry


def list_skill_registry(
    *,
    nodes: Iterable[Any] | None = None,
    include_defaults: bool = True,
) -> list[dict[str, Any]]:
    registry = build_skill_registry(nodes=nodes, include_defaults=include_defaults)
    items = sorted(registry.values(), key=lambda item: (str(item.get("name") or "").lower(), str(item.get("id") or "")))
    return items


def get_skill_package(
    skill_id: str,
    *,
    nodes: Iterable[Any] | None = None,
    include_defaults: bool = True,
) -> dict[str, Any] | None:
    clean_skill_id = str(skill_id or "").strip()
    if not clean_skill_id:
        return None
    registry = build_skill_registry(nodes=nodes, include_defaults=include_defaults)
    package = registry.get(clean_skill_id)
    if package:
        return package

    # Last-resort minimal package for unseen runtime skills.
    fallback = normalize_skill_package({"id": clean_skill_id}, source_key="runtime_inferred")
    return fallback
