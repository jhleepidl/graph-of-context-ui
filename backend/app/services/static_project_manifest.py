from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)(.+?)\s*$")

DEFAULT_PROJECT_MANIFEST_FILENAMES = ("CLAUDE.md", "AGENTS.md", "SKILL.md", "ROOM.md", "PROJECT.md")


def _clean(value: Any, max_len: int = 2000, lower: bool = False) -> str:
    text = re.sub(r"[ \t]+", " ", str(value or "").replace("\r\n", "\n").replace("\r", "\n")).strip()
    text = text[:max_len]
    return text.lower() if lower else text


def _slug(value: Any, fallback: str = "manifest") -> str:
    text = re.sub(r"[^a-z0-9가-힣._:-]+", "_", _clean(value or fallback, 160, True)).strip("_")
    return text or fallback


def _manifest_type(filename: str) -> str:
    base = Path(filename).name.lower()
    if base == "claude.md":
        return "claude_md"
    if base == "agents.md":
        return "agents_md"
    if base == "skill.md":
        return "skill_md"
    if base == "room.md":
        return "room_md"
    return "project_markdown"


def classify_heading(heading: str) -> str:
    h = _clean(heading, 180, True)
    if re.search(r"overview|summary|purpose|project|about|소개|개요|목적", h):
        return "overview"
    if re.search(r"architecture|structure|design|module|component|구조|아키텍처|설계", h):
        return "architecture"
    if re.search(r"command|script|build|test|run|deploy|실행|명령|테스트|빌드|배포", h):
        return "commands"
    if re.search(r"style|convention|guideline|coding|format|lint|규칙|컨벤션|스타일", h):
        return "conventions"
    if re.search(r"workflow|process|procedure|steps|작업|절차|프로세스", h):
        return "workflow"
    if re.search(r"do not|forbidden|avoid|never|주의|금지|하지 말", h):
        return "forbidden_actions"
    if re.search(r"review|checklist|verify|검토|확인|체크리스트", h):
        return "review_checklist"
    if re.search(r"tool|permission|api|external|도구|권한", h):
        return "tool_policy"
    if re.search(r"memory|context|state|history|맥락|컨텍스트|기억|메모리", h):
        return "memory_policy"
    if re.search(r"agent|skill|role|persona|에이전트|스킬|역할", h):
        return "agent_or_skill"
    return "other"


def _split_sections(markdown: str) -> list[dict[str, Any]]:
    lines = str(markdown or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    raw_sections: list[dict[str, Any]] = []
    current = {"level": 1, "heading": "Preamble", "lines": []}
    in_fence = False
    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence
        match = None if in_fence else _HEADING_RE.match(line)
        if match:
            if "\n".join(current["lines"]).strip() or current["heading"] != "Preamble":
                raw_sections.append(current)
            current = {"level": len(match.group(1)), "heading": _clean(match.group(2), 180), "lines": []}
        else:
            current["lines"].append(line)
    if "\n".join(current["lines"]).strip() or current["heading"] != "Preamble":
        raw_sections.append(current)
    sections: list[dict[str, Any]] = []
    for idx, section in enumerate(raw_sections, start=1):
        bullets = []
        for line in section["lines"]:
            m = _BULLET_RE.match(line)
            if m:
                bullets.append(_clean(m.group(1), 300))
        sections.append({
            "section_id": f"section_{idx:02d}",
            "level": int(section["level"]),
            "heading": section["heading"],
            "category": classify_heading(section["heading"]),
            "text": _clean("\n".join(section["lines"]), 4000),
            "bullets": list(dict.fromkeys([b for b in bullets if b]))[:20],
        })
    return [s for s in sections if s["heading"] or s["text"]]


def _collect_policies(sections: list[dict[str, Any]]) -> dict[str, list[str]]:
    keys = ["overview", "architecture", "commands", "conventions", "workflow", "forbidden_actions", "review_checklist", "tool_policy", "memory_policy", "agent_or_skill", "other"]
    out: dict[str, list[str]] = {key: [] for key in keys}
    for section in sections:
        key = section.get("category") if section.get("category") in out else "other"
        lines = section.get("bullets") or ([section.get("text")] if section.get("text") else [])
        out[str(key)].extend([_clean(x, 300) for x in lines[:8] if _clean(x, 300)])
    return {key: list(dict.fromkeys(values))[:24] for key, values in out.items()}


def parse_project_manifest(filename: str, content: str, source: str = "manual_import") -> dict[str, Any]:
    sections = _split_sections(content)
    policies = _collect_policies(sections)
    policy_text = "\n".join([str(x) for values in policies.values() for x in values]).lower()
    domain = "code_review" if re.search(r"repo|code|test|build|lint|deploy|api|frontend|backend|python|node", policy_text) else ("research_paper" if re.search(r"paper|research|experiment|evaluation|latex|sigir|novelty", policy_text) else "general_workbench")
    agents = ["researcher", "reviewer", "synthesizer"]
    if domain == "code_review":
        agents = ["implementation_planner", "builder", "reviewer", "verifier"]
    if domain == "research_paper":
        agents = ["researcher", "novelty_critic", "evaluation_designer", "synthesizer"]
    object_types = ["project_overview", "workflow_rules", "constraints"]
    if policies.get("commands"):
        object_types.append("commands")
    if policies.get("architecture"):
        object_types.append("architecture_notes")
    if policies.get("review_checklist"):
        object_types.append("review_checklist")
    if policies.get("tool_policy"):
        object_types.append("tool_policy")
    return {
        "kind": "static_project_manifest_v1",
        "manifest_type": _manifest_type(filename),
        "source": source,
        "filename": Path(filename).name,
        "title": next((s["heading"] for s in sections if s.get("level") == 1 and s.get("heading") != "Preamble"), Path(filename).name),
        "domain_label": domain,
        "sections": sections,
        "policies": policies,
        "derived": {
            "agents": agents,
            "memory_object_types": list(dict.fromkeys(object_types)),
            "tags": [_manifest_type(filename), domain, "static_manifest", "project_guidance"],
        },
        "import_boundary": {
            "copies_private_memory": False,
            "copies_credentials": False,
            "raw_chat_history_imported": False,
            "user_approval_required_for_persistent_install": True,
        },
    }


def build_room_package_candidate(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "shared_room_package_v1",
        "schema_version": 1,
        "package_id": f"imported_{_slug(manifest.get('filename') or manifest.get('title'))}",
        "title": f"{manifest.get('title') or manifest.get('filename')} Room",
        "description": " ".join((manifest.get("policies") or {}).get("overview", [])[:2]) or f"Room package imported from {manifest.get('filename')}",
        "domain_label": manifest.get("domain_label") or "general_workbench",
        "agents": (manifest.get("derived") or {}).get("agents", []),
        "default_depth": "team" if manifest.get("domain_label") == "code_review" else "ask",
        "memory_schema": {
            "object_types": (manifest.get("derived") or {}).get("memory_object_types", []),
            "retention_policy": "room_local_by_default",
            "private_memory_export": "never_by_default",
        },
        "prompt_policy": {"static_manifest_context": "use_relevant_sections_only"},
        "context_policy": {
            "default_scope": "room_local_plus_static_manifest",
            "static_manifest_import": "allowed_as_non_private_project_guidance",
            "private_memory": "least_privilege",
        },
        "approval_policy": {"default": "ask_before_persistent_room_install"},
        "tags": (manifest.get("derived") or {}).get("tags", []),
        "safety_report": {"copies_private_memory": False, "credentials_copied": False, "raw_chat_history_imported": False},
    }


def build_static_manifest_context_block(manifest: dict[str, Any], max_sections: int = 6) -> str:
    preferred = {"overview", "architecture", "commands", "conventions", "workflow", "forbidden_actions", "review_checklist", "tool_policy", "memory_policy"}
    lines = [
        "<static_project_manifest>",
        f"filename: {manifest.get('filename', '')}",
        f"type: {manifest.get('manifest_type', '')}",
        "boundary: project guidance only; no private memory or credentials are imported",
    ]
    selected = [s for s in manifest.get("sections", []) if s.get("category") in preferred][:max_sections]
    for section in selected:
        body = "\n".join(f"- {x}" for x in section.get("bullets", [])) or section.get("text", "")
        lines.append(f"\n## {section.get('heading', '')}\n{body[:1800]}")
    lines.append("</static_project_manifest>")
    return "\n".join(lines)
