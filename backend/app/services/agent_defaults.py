from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from app.models import Agent, utcnow

SYSTEM_OWNER_USER_ID = "system"
SYSTEM_DEFAULT_SERVICE_ID = "public"

DEFAULT_SYSTEM_AGENTS: list[dict[str, Any]] = [
    {
        "system_key": "router",
        "name": "Router",
        "description": "Routes the task and orchestrates other agents.",
        "system_prompt": "Select the best specialist agent(s) and produce an execution plan.",
        "instruction": "Prefer minimal, deterministic plans and explicit handoff notes.",
        "tools": [],
        "model": "chatgpt:gpt-5",
    },
    {
        "system_key": "planner",
        "name": "Planner",
        "description": "Builds concrete step plans from user goals.",
        "system_prompt": "Turn goals into actionable steps with constraints and checkpoints.",
        "instruction": "Keep plans short, testable, and reversible.",
        "tools": [],
        "model": "chatgpt:gpt-5",
    },
    {
        "system_key": "researcher",
        "name": "Researcher",
        "description": "Finds references, compares options, and summarizes tradeoffs.",
        "system_prompt": "Gather evidence, compare alternatives, and cite assumptions clearly.",
        "instruction": "Avoid unsupported claims and include confidence notes.",
        "tools": ["search"],
        "model": "gemini:gemini",
    },
    {
        "system_key": "coder",
        "name": "Coder",
        "description": "Implements and validates code-level changes.",
        "system_prompt": "Write safe, maintainable code and verify behavior.",
        "instruction": "Prefer small diffs, tests, and explicit failure handling.",
        "tools": ["code", "shell"],
        "model": "codex:codex",
    },
]


def _jdump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def ensure_default_agents(session: Session) -> list[Agent]:
    existing = session.exec(
        select(Agent).where(Agent.is_system_default == True)  # noqa: E712
    ).all()
    by_key = {
        str(row.system_key or "").strip().lower(): row
        for row in existing
        if str(row.system_key or "").strip()
    }

    out: list[Agent] = []
    for spec in DEFAULT_SYSTEM_AGENTS:
        key = str(spec.get("system_key") or "").strip().lower()
        if not key:
            continue
        tools = spec.get("tools")
        tools_json = _jdump(tools if isinstance(tools, list) else [])
        current = by_key.get(key)
        if current:
            changed = False
            for field, value in (
                ("name", str(spec.get("name") or "").strip()),
                ("description", str(spec.get("description") or "").strip()),
                ("system_prompt", str(spec.get("system_prompt") or "").strip()),
                ("instruction", str(spec.get("instruction") or "").strip()),
                ("model", str(spec.get("model") or "").strip()),
            ):
                if getattr(current, field) != value:
                    setattr(current, field, value)
                    changed = True
            if current.tools_json != tools_json:
                current.tools_json = tools_json
                changed = True
            if current.visibility != "public":
                current.visibility = "public"
                changed = True
            if current.owner_user_id != SYSTEM_OWNER_USER_ID:
                current.owner_user_id = SYSTEM_OWNER_USER_ID
                changed = True
            if current.service_id != SYSTEM_DEFAULT_SERVICE_ID:
                current.service_id = SYSTEM_DEFAULT_SERVICE_ID
                changed = True
            if not current.is_system_default:
                current.is_system_default = True
                changed = True
            if current.is_archived:
                current.is_archived = False
                changed = True
            if changed:
                current.updated_at = utcnow()
                session.add(current)
            out.append(current)
            continue

        created = Agent(
            owner_user_id=SYSTEM_OWNER_USER_ID,
            service_id=SYSTEM_DEFAULT_SERVICE_ID,
            name=str(spec.get("name") or key).strip() or key,
            description=str(spec.get("description") or "").strip(),
            system_prompt=str(spec.get("system_prompt") or "").strip(),
            instruction=str(spec.get("instruction") or "").strip(),
            tools_json=tools_json,
            model=str(spec.get("model") or "").strip(),
            visibility="public",
            source_agent_id=None,
            system_key=key,
            is_system_default=True,
            is_archived=False,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(created)
        session.flush()
        out.append(created)

    return out
