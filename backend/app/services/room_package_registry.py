from __future__ import annotations

import json
import re
from typing import Any

from app.services.room_components import build_room_components


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean(value: Any = "", max_len: int = 2000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:max_len]


def _id(value: Any = "", fallback: str = "room_package") -> str:
    text = _clean(value or fallback, 180).lower()
    clean = re.sub(r"[^a-z0-9가-힣._:-]+", "_", text).strip("_")
    return clean or fallback


def _loads(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def _unique(values: Any, *, limit: int = 64) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in _as_list(values):
        text = _clean(raw, 180)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


_PRIVATE_KEY_RE = re.compile(
    r"(credential|secret|token|password|api[_-]?key|provider[_-]?state|runtime[_-]?log|chat[_-]?history|transcript|raw[_-]?message|conversation[_-]?turn|private[_-]?memory|memory[_-]?content|artifact[_-]?content|upload[_-]?content)",
    re.I,
)


def _strip_private(value: Any, depth: int = 0) -> Any:
    if depth > 12:
        return None
    if isinstance(value, list):
        out = []
        for item in value:
            cleaned = _strip_private(item, depth + 1)
            if cleaned is not None:
                out.append(cleaned)
        return out
    if not isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    for key, raw in value.items():
        key_text = str(key)
        # Boolean safety metadata is safe to keep; it is not the private content itself.
        if key_text in {"copies_private_memory", "credentials_copied", "provider_state_copied", "private_files_copied"}:
            out[key] = raw
            continue
        if _PRIVATE_KEY_RE.search(key_text):
            continue
        cleaned = _strip_private(raw, depth + 1)
        if cleaned is not None:
            out[key] = cleaned
    return out


def sanitize_registry_room_package(raw: dict[str, Any]) -> dict[str, Any]:
    pkg = _strip_private(_as_dict(raw)) or {}
    package_id = _id(pkg.get("package_id") or pkg.get("packageId") or pkg.get("id") or pkg.get("title") or "shared_room_package")
    memory = _as_dict(pkg.get("memory_schema") or pkg.get("memorySchema"))
    context = _as_dict(pkg.get("context_policy") or pkg.get("contextPolicy"))
    approval = _as_dict(pkg.get("approval_policy") or pkg.get("approvalPolicy"))
    safety = _as_dict(pkg.get("safety_report") or pkg.get("safetyReport"))
    install = _as_dict(pkg.get("install_policy") or pkg.get("installPolicy"))
    return {
        **pkg,
        "kind": "shared_room_package_v1",
        "schema_version": pkg.get("schema_version") or pkg.get("schemaVersion") or 1,
        "package_id": package_id,
        "title": _clean(pkg.get("title") or pkg.get("name") or package_id, 160) or package_id,
        "description": _clean(pkg.get("description") or pkg.get("purpose") or "", 2000),
        "visibility": _id(pkg.get("visibility") or "private_review", "private_review"),
        "status": _id(pkg.get("status") or pkg.get("publish_state") or "candidate", "candidate"),
        "version": _clean(pkg.get("version") or "0.1.0", 40) or "0.1.0",
        "domain_label": _id(pkg.get("domain_label") or pkg.get("domainLabel") or pkg.get("domain") or "general_workbench", "general_workbench"),
        "agents": _unique(pkg.get("agents") or pkg.get("agent_roles") or pkg.get("agentRoles"), limit=32),
        "memory_schema": {
            **memory,
            "object_types": _unique(memory.get("object_types") or memory.get("objectTypes") or pkg.get("memory_object_types") or [], limit=96),
            "private_memory_export": "never_by_default",
            "copies_private_memory": False,
        },
        "context_policy": {
            **context,
            "shared_package_copies_private_memory": False,
            "private_memory": context.get("private_memory") or context.get("privateMemory") or "least_privilege",
            "cross_room_memory": context.get("cross_room_memory") or context.get("crossRoomMemory") or "ask_before_use",
        },
        "approval_policy": approval,
        "tags": _unique(pkg.get("tags") or [], limit=32),
        "safety_report": {
            **safety,
            "clone_safe": safety.get("clone_safe", True),
            "credentials_copied": safety.get("credentials_copied", False),
            "provider_state_copied": safety.get("provider_state_copied", False),
            "private_files_copied": safety.get("private_files_copied", False),
        },
        "install_policy": {
            **install,
            "private_memory": "fresh_on_install",
            "credentials": "never_copy",
            "user_must_approve_memory_import": True,
        },
    }


def _package_from_item(item: dict[str, Any]) -> dict[str, Any]:
    pkg = item.get("package") if isinstance(item.get("package"), dict) else item
    return sanitize_registry_room_package(_as_dict(pkg))


def _component_counts(pkg: dict[str, Any]) -> dict[str, int]:
    components = build_room_components(pkg)
    return {
        "agent_cards": len(_as_list(components.get("agents"))),
        "memory_schema_cards": len(_as_list(components.get("memory_schemas"))),
        "prompt_policy_cards": len(_as_list(components.get("prompt_policies"))),
        "context_policy_cards": len(_as_list(components.get("context_policies"))),
        "approval_policy_cards": len(_as_list(components.get("approval_policies"))),
        "evaluation_criteria_cards": len(_as_list(components.get("evaluation_criteria"))),
        "interaction_guide_cards": len(_as_list(components.get("interaction_guides"))),
    }


def _privacy_guardrail(pkg: dict[str, Any]) -> dict[str, Any]:
    safety = _as_dict(pkg.get("safety_report"))
    context = _as_dict(pkg.get("context_policy"))
    install = _as_dict(pkg.get("install_policy"))
    issues: list[str] = []
    if safety.get("copies_private_memory") is True:
        issues.append("package claims to copy private memory")
    if safety.get("credentials_copied") is True:
        issues.append("package claims to copy credentials")
    if context.get("shared_package_copies_private_memory") is True:
        issues.append("context policy copies private memory")
    if install.get("credentials") not in {None, "", "never_copy"}:
        issues.append("install policy may copy credentials")
    return {
        "clone_safe": not issues,
        "issues": issues,
        "private_memory_export": _as_dict(pkg.get("memory_schema")).get("private_memory_export") or "never_by_default",
        "credentials": install.get("credentials") or "never_copy",
        "source_room_private_memory": "never_read_by_imported_package",
    }


def build_room_package_registry_card(item: dict[str, Any]) -> dict[str, Any]:
    pkg = _package_from_item(item)
    components = _component_counts(pkg)
    guardrail = _privacy_guardrail(pkg)
    return {
        "kind": "room_package_registry_card_v1",
        "package_id": pkg.get("package_id") or item.get("package_id"),
        "title": pkg.get("title") or item.get("title") or "",
        "description": pkg.get("description") or item.get("description") or "",
        "domain_label": pkg.get("domain_label") or "general_workbench",
        "version": pkg.get("version") or "0.1.0",
        "visibility": pkg.get("visibility") or item.get("visibility") or "private_review",
        "status": pkg.get("status") or item.get("status") or "candidate",
        "source": item.get("source") or _as_dict(pkg.get("source")).get("kind") or "unknown",
        "lineage": _as_dict(pkg.get("lineage")),
        "tags": _unique(pkg.get("tags"), limit=24),
        "component_counts": components,
        "governance": {
            "approval_required_for_install": True,
            "approval_required_for_publish": True,
            "user_must_approve_memory_import": True,
            "private_memory_never_exported": guardrail.get("private_memory_export") == "never_by_default",
        },
        "privacy_guardrail": guardrail,
        "compatibility": {
            "exports": ["room_package_json", "claude_md", "agents_md", "skill_md", "claude_subagent_md"],
            "imports": ["shared_room_package_v1", "claude_md", "agents_md", "skill_md", "room_md", "project_md"],
            "runtime_targets": ["ddalggak", "goc", "claude_code_compatible"],
        },
        "updated_at": item.get("updated_at"),
        "created_at": item.get("created_at"),
    }


def build_room_package_registry(items: list[dict[str, Any]], *, query: str = "", limit: int = 100) -> dict[str, Any]:
    q = _clean(query, 200).lower()
    cards: list[dict[str, Any]] = []
    for item in items:
        card = build_room_package_registry_card(item)
        if q:
            haystack = " ".join([
                str(card.get("package_id") or ""),
                str(card.get("title") or ""),
                str(card.get("description") or ""),
                str(card.get("domain_label") or ""),
                " ".join(card.get("tags") or []),
            ]).lower()
            if q not in haystack:
                continue
        cards.append(card)
        if len(cards) >= max(1, min(int(limit or 100), 500)):
            break
    by_domain: dict[str, int] = {}
    by_status: dict[str, int] = {}
    clone_safe = 0
    for card in cards:
        by_domain[card["domain_label"]] = by_domain.get(card["domain_label"], 0) + 1
        by_status[card["status"]] = by_status.get(card["status"], 0) + 1
        if _as_dict(card.get("privacy_guardrail")).get("clone_safe"):
            clone_safe += 1
    return {
        "kind": "room_package_registry_v1",
        "ok": True,
        "query": q,
        "summary": {
            "package_count": len(cards),
            "by_domain": by_domain,
            "by_status": by_status,
            "clone_safe_count": clone_safe,
        },
        "items": cards,
    }


def _markdown_header(pkg: dict[str, Any], title: str = "AI Room Package") -> list[str]:
    return [
        f"# {title}: {pkg.get('title') or pkg.get('package_id')}",
        "",
        f"- Package ID: `{pkg.get('package_id')}`",
        f"- Domain: `{pkg.get('domain_label') or 'general_workbench'}`",
        f"- Version: `{pkg.get('version') or '0.1.0'}`",
        "",
        "## Purpose",
        "",
        _clean(pkg.get("description") or "Reusable AI Room guidance package.", 2000),
        "",
    ]


def build_room_package_export_preview(item: dict[str, Any], *, target_format: str = "claude_md") -> dict[str, Any]:
    pkg = _package_from_item(item)
    target = _id(target_format or "claude_md", "claude_md")
    components = build_room_components(pkg)
    agents = _unique(pkg.get("agents"), limit=48)
    mem = _as_dict(pkg.get("memory_schema"))
    context = _as_dict(pkg.get("context_policy"))
    approval = _as_dict(pkg.get("approval_policy"))
    lines = _markdown_header(pkg, "AI Room")
    if target == "room_package_json":
        body = json.dumps(pkg, ensure_ascii=False, indent=2)
    else:
        lines += [
            "## Room Router Policy",
            "",
            f"- Default depth: `{pkg.get('default_depth') or 'ask'}`",
            "- Simple turns should stay lightweight.",
            "- Escalate only when the turn requires structured memory, tools, review, or multi-step execution.",
            "",
            "## Agents / Components",
            "",
        ]
        lines += [f"- {agent}" for agent in agents] or ["- room_responder"]
        lines += [
            "",
            "## Memory Policy",
            "",
            f"- Object types: {', '.join(_unique(mem.get('object_types'), limit=24)) or 'none declared'}",
            "- Private room memory must not be exported with this package.",
            "- Memory writes are proposals unless explicitly approved.",
            "",
            "## Context Policy",
            "",
            f"- Private memory: `{context.get('private_memory') or 'least_privilege'}`",
            f"- Cross-room memory: `{context.get('cross_room_memory') or 'ask_before_use'}`",
            "",
            "## Approval Policy",
            "",
            f"- Install approval: `{approval.get('install') or 'required'}`",
            f"- Tool or side-effect approval: `{approval.get('external_side_effects') or 'approval_required'}`",
            "",
        ]
        if target == "skill_md":
            lines = [
                "---",
                f"name: {_id(pkg.get('title') or pkg.get('package_id'), 'room_skill')}",
                f"description: {_clean(pkg.get('description') or 'AI Room skill package', 500)}",
                "---",
                "",
                *lines,
            ]
        elif target == "claude_subagent_md":
            primary = agents[0] if agents else "room_responder"
            lines = [
                "---",
                f"name: {_id(primary, 'room_agent')}",
                f"description: {_clean(pkg.get('description') or 'Room-scoped specialist agent', 500)}",
                "tools: Read, Grep, Glob",
                "---",
                "",
                *lines,
            ]
        elif target == "agents_md":
            lines = ["# AGENTS.md", "", *lines]
        else:
            lines = ["# CLAUDE.md", "", *lines]
        body = "\n".join(lines).strip() + "\n"
    return {
        "kind": "room_package_export_preview_v1",
        "ok": True,
        "package_id": pkg.get("package_id"),
        "target_format": target,
        "content": body,
        "content_chars": len(body),
        "privacy": {
            "raw_private_memory_included": False,
            "credentials_included": False,
            "source_runtime_state_included": False,
        },
        "component_counts": _component_counts(pkg),
    }


def build_room_package_lifecycle_preview(item: dict[str, Any], *, action: str = "publish_review") -> dict[str, Any]:
    pkg = _package_from_item(item)
    act = _id(action or "publish_review", "publish_review")
    guardrail = _privacy_guardrail(pkg)
    next_status = {
        "publish_review": "pending_publish_review",
        "approve_publish": "published",
        "deprecate": "deprecated",
        "archive": "archived",
        "fork": "candidate",
    }.get(act, "pending_review")
    blockers: list[str] = []
    if act in {"publish_review", "approve_publish"} and not guardrail.get("clone_safe"):
        blockers.extend(guardrail.get("issues") or ["privacy guardrail failed"])
    if act in {"approve_publish"} and pkg.get("visibility") not in {"public", "unlisted"}:
        blockers.append("package visibility must be public or unlisted before publish approval")
    return {
        "kind": "room_package_lifecycle_preview_v1",
        "ok": not blockers,
        "package_id": pkg.get("package_id"),
        "action": act,
        "current_status": pkg.get("status") or item.get("status") or "candidate",
        "next_status": next_status,
        "requires_user_or_admin_approval": act in {"publish_review", "approve_publish", "archive", "deprecate"},
        "blockers": blockers,
        "privacy_guardrail": guardrail,
        "notes": [
            "Lifecycle preview does not mutate package state.",
            "Private memory is never exported or copied during publish/fork.",
            "GoC should record lineage and approval decisions when lifecycle actions are applied.",
        ],
    }
