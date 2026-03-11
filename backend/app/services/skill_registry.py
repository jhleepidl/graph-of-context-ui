from __future__ import annotations

import json
from typing import Any, Iterable


SKILL_PACKAGE_KEYS = (
    "skill_packages",
    "skillPackages",
    "skill_registry",
    "skillRegistry",
    "available_skills",
    "availableSkills",
    "skill_catalog",
    "skillCatalog",
)

NESTED_PAYLOAD_KEYS = ("runtime", "meta", "result", "output", "state", "data")

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
    "visibility",
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


def _clean_text(value: Any) -> str | None:
    clean = str(value or "").strip()
    return clean or None


def _clean_list_of_text(value: Any, *, limit: int = 32) -> list[str]:
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


def _has_non_empty(value: Any) -> bool:
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
    for key in NESTED_PAYLOAD_KEYS:
        nested = payload.get(key)
        if isinstance(nested, dict):
            next_prefix = f"{prefix}{key}."
            yield from _iter_payload_containers(nested, prefix=next_prefix, depth=depth + 1, max_depth=max_depth)


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
