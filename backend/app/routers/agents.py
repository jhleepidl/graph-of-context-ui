from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session, select

from app.auth import get_current_principal, get_current_user_id
from app.config import get_env
from app.db import engine
from app.models import Agent, AgentRevision, Conversation, ConversationAgent, Thread, User, utcnow
from app.schemas import (
    AgentArchiveRequest,
    AgentBootstrapDefaultsRequest,
    AgentCreateRequest,
    AgentForkRequest,
    AgentPatchRequest,
    ConversationAgentCreateRequest,
    ConversationAgentPatchRequest,
    ConversationAgentReorderRequest,
    ConversationEnsureRequest,
)
from app.services.agent_defaults import ensure_default_agents
from app.tenant import require_thread_access

router = APIRouter(prefix="/api", tags=["agents"])

AGENT_VISIBILITIES = {"private", "unlisted", "public"}
AGENT_LIST_SCOPES = {"my", "public", "installed"}


def _env_bool(key: str, default: bool) -> bool:
    raw = (get_env(key, "true" if default else "false") or "").strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def _enforce_conversation_owner_check() -> bool:
    principal = get_current_principal()
    if principal.role == "service":
        # Service requests often proxy multiple allowed telegram users in a group conversation.
        return False
    return _env_bool("GOC_ENFORCE_CONVERSATION_OWNER", False)


def _jdump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def _clean_visibility(value: str | None, default: str = "private") -> str:
    clean = str(value or "").strip().lower() or default
    if clean not in AGENT_VISIBILITIES:
        raise HTTPException(400, "visibility must be private|unlisted|public")
    return clean


def _normalize_tools(raw: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in raw or []:
        clean = str(item or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
    return out


def _current_service_id() -> str:
    principal = get_current_principal()
    service_id = str(principal.service_id or "").strip()
    if principal.role != "admin" and not service_id:
        raise HTTPException(401, "service scope is missing")
    return service_id or "default"


def _is_owner(agent: Agent, user_id: str | None, *, is_admin: bool) -> bool:
    if is_admin:
        return True
    clean_user = str(user_id or "").strip()
    return bool(clean_user and clean_user == str(agent.owner_user_id or "").strip())


def _can_read_agent(agent: Agent, *, user_id: str | None, service_id: str | None, is_admin: bool) -> bool:
    if is_admin:
        return True
    if _is_owner(agent, user_id, is_admin=False):
        return True
    visibility = _clean_visibility(agent.visibility, "private")
    if visibility in {"public", "unlisted"}:
        return True
    return False


def _can_write_agent(agent: Agent, *, user_id: str | None, is_admin: bool) -> bool:
    return _is_owner(agent, user_id, is_admin=is_admin)


def _owner_display_name(owner_user: User | None) -> str | None:
    if not owner_user:
        return None
    first_name = str(owner_user.first_name or "").strip()
    last_name = str(owner_user.last_name or "").strip()
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    if full_name:
        return full_name
    username = str(owner_user.username or "").strip()
    if username:
        return username
    return None


def _owner_users_by_id(session: Session, agents: list[Agent], *, is_admin: bool) -> dict[str, User]:
    if not is_admin:
        return {}
    owner_ids = {
        str(row.owner_user_id or "").strip()
        for row in agents
        if str(row.owner_user_id or "").strip()
    }
    if not owner_ids:
        return {}
    rows = session.exec(select(User).where(User.id.in_(sorted(owner_ids)))).all()
    return {str(row.id): row for row in rows}


def _agent_payload(
    agent: Agent,
    *,
    current_user_id: str | None,
    is_admin: bool,
    owner_user: User | None = None,
) -> dict[str, Any]:
    tools = _jload(agent.tools_json, [])
    if not isinstance(tools, list):
        tools = []
    owner_user_id = str(agent.owner_user_id or "").strip() or None
    exposed_owner_user_id = owner_user_id if is_admin else None
    owner_block: dict[str, Any] | None = None
    if is_admin:
        telegram_user_id = str(owner_user.telegram_user_id or "").strip() if owner_user else ""
        username = str(owner_user.username or "").strip() if owner_user else ""
        owner_block = {
            "user_id": owner_user_id,
            "telegram_user_id": telegram_user_id or None,
            "username": username or None,
            "display_name": _owner_display_name(owner_user),
        }
    return {
        "id": agent.id,
        "owner_user_id": exposed_owner_user_id,
        "service_id": agent.service_id,
        "name": agent.name,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "instruction": agent.instruction,
        "tools": [str(item) for item in tools if str(item or "").strip()],
        "model": agent.model,
        "visibility": _clean_visibility(agent.visibility, "private"),
        "source_agent_id": agent.source_agent_id,
        "system_key": agent.system_key,
        "is_system_default": bool(agent.is_system_default),
        "is_archived": bool(agent.is_archived),
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
        "can_write": _can_write_agent(agent, user_id=current_user_id, is_admin=is_admin),
        "owner": owner_block,
    }


def _serialize_agents(
    session: Session,
    agents: list[Agent],
    *,
    current_user_id: str | None,
    is_admin: bool,
) -> list[dict[str, Any]]:
    owners_by_id = _owner_users_by_id(session, agents, is_admin=is_admin)
    return [
        _agent_payload(
            row,
            current_user_id=current_user_id,
            is_admin=is_admin,
            owner_user=owners_by_id.get(str(row.owner_user_id or "").strip()),
        )
        for row in agents
    ]


def _serialize_agent(
    session: Session,
    agent: Agent,
    *,
    current_user_id: str | None,
    is_admin: bool,
) -> dict[str, Any]:
    owners_by_id = _owner_users_by_id(session, [agent], is_admin=is_admin)
    return _agent_payload(
        agent,
        current_user_id=current_user_id,
        is_admin=is_admin,
        owner_user=owners_by_id.get(str(agent.owner_user_id or "").strip()),
    )


def _append_agent_revision(
    session: Session,
    agent: Agent,
    *,
    actor_user_id: str | None,
    reason: str,
) -> AgentRevision:
    current = session.exec(
        select(AgentRevision)
        .where(AgentRevision.agent_id == agent.id)
        .order_by(AgentRevision.revision.desc())
        .limit(1)
    ).first()
    next_revision = int(current.revision if current else 0) + 1
    snapshot = {
        "id": agent.id,
        "owner_user_id": agent.owner_user_id,
        "service_id": agent.service_id,
        "name": agent.name,
        "description": agent.description,
        "system_prompt": agent.system_prompt,
        "instruction": agent.instruction,
        "tools_json": agent.tools_json,
        "model": agent.model,
        "visibility": agent.visibility,
        "source_agent_id": agent.source_agent_id,
        "system_key": agent.system_key,
        "is_system_default": bool(agent.is_system_default),
        "is_archived": bool(agent.is_archived),
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
        "reason": reason,
    }
    revision = AgentRevision(
        agent_id=agent.id,
        revision=next_revision,
        snapshot_json=_jdump(snapshot),
        created_by_user_id=(actor_user_id or "").strip() or None,
        created_at=utcnow(),
    )
    session.add(revision)
    return revision


def _get_agent_or_404(session: Session, agent_id: str) -> Agent:
    row = session.get(Agent, agent_id)
    if not row:
        raise HTTPException(404, "agent not found")
    return row


def _agent_lineage_key(agent: Agent) -> str:
    source_agent_id = str(agent.source_agent_id or "").strip()
    return source_agent_id or str(agent.id)


def _ensure_conversation(
    session: Session,
    *,
    thread_id: str,
    owner_user_id: str,
    service_id: str,
    is_admin: bool,
) -> tuple[Thread, Conversation]:
    thread = require_thread_access(session, thread_id)
    conversation = session.exec(
        select(Conversation)
        .where(Conversation.thread_id == thread_id)
        .limit(1)
    ).first()
    if conversation:
        if _enforce_conversation_owner_check() and not is_admin and conversation.owner_user_id != owner_user_id:
            raise HTTPException(403, "conversation owner mismatch")
        return thread, conversation

    created = Conversation(
        thread_id=thread_id,
        owner_user_id=owner_user_id,
        service_id=service_id,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    session.add(created)
    session.flush()
    return thread, created


def _require_conversation(
    session: Session,
    *,
    thread_id: str,
    owner_user_id: str,
    is_admin: bool,
) -> tuple[Thread, Conversation]:
    thread = require_thread_access(session, thread_id)
    conversation = session.exec(
        select(Conversation)
        .where(Conversation.thread_id == thread_id)
        .limit(1)
    ).first()
    if not conversation:
        raise HTTPException(404, "conversation not found")
    if _enforce_conversation_owner_check() and not is_admin and conversation.owner_user_id != owner_user_id:
        raise HTTPException(403, "conversation owner mismatch")
    return thread, conversation


def _conversation_memberships(session: Session, conversation_id: str) -> list[ConversationAgent]:
    return session.exec(
        select(ConversationAgent)
        .where(ConversationAgent.conversation_id == conversation_id)
        .order_by(ConversationAgent.order_index.asc(), ConversationAgent.created_at.asc(), ConversationAgent.id.asc())
    ).all()


def _conversation_payload(
    conversation: Conversation,
    *,
    memberships: list[ConversationAgent],
    agents_by_id: dict[str, Agent],
    current_user_id: str | None,
    is_admin: bool,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for membership in memberships:
        agent = agents_by_id.get(membership.agent_id)
        if not agent:
            continue
        items.append({
            "id": membership.id,
            "conversation_id": membership.conversation_id,
            "agent_id": membership.agent_id,
            "enabled": bool(membership.enabled),
            "order_index": int(membership.order_index),
            "overrides_json": _jload(membership.overrides_json, {}),
            "created_at": membership.created_at,
            "updated_at": membership.updated_at,
            "agent": _agent_payload(agent, current_user_id=current_user_id, is_admin=is_admin),
        })
    return {
        "id": conversation.id,
        "thread_id": conversation.thread_id,
        "owner_user_id": conversation.owner_user_id,
        "service_id": conversation.service_id,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "agents": items,
    }


def _install_default_private_agents(
    session: Session,
    *,
    owner_user_id: str,
    actor_user_id: str | None,
    service_id: str,
) -> list[Agent]:
    installed_items: list[Agent] = []
    defaults = ensure_default_agents(session)
    for default_agent in defaults:
        existing = session.exec(
            select(Agent)
            .where(Agent.owner_user_id == owner_user_id)
            .where(Agent.source_agent_id == default_agent.id)
            .where(Agent.is_archived == False)  # noqa: E712
            .order_by(Agent.updated_at.desc(), Agent.id.desc())
            .limit(1)
        ).first()
        if existing:
            installed_items.append(existing)
            continue

        now = utcnow()
        created = Agent(
            owner_user_id=owner_user_id,
            service_id=service_id,
            name=default_agent.name,
            description=default_agent.description,
            system_prompt=default_agent.system_prompt,
            instruction=default_agent.instruction,
            tools_json=default_agent.tools_json,
            model=default_agent.model,
            visibility="private",
            source_agent_id=default_agent.id,
            system_key=None,
            is_system_default=False,
            is_archived=False,
            created_at=now,
            updated_at=now,
        )
        session.add(created)
        session.flush()
        _append_agent_revision(
            session,
            created,
            actor_user_id=actor_user_id,
            reason=f"bootstrap_default:{default_agent.id}",
        )
        installed_items.append(created)
    return installed_items


def _add_missing_conversation_memberships(
    session: Session,
    *,
    conversation: Conversation,
    agents: list[Agent],
    only_if_empty: bool,
) -> bool:
    existing_members = {
        row.agent_id: row
        for row in _conversation_memberships(session, conversation.id)
    }
    if only_if_empty and existing_members:
        return False

    now = utcnow()
    next_order = len(existing_members)
    changed = False
    for item in agents:
        if item.id in existing_members:
            continue
        membership = ConversationAgent(
            conversation_id=conversation.id,
            agent_id=item.id,
            enabled=True,
            order_index=next_order,
            overrides_json=_jdump({}),
            created_at=now,
            updated_at=now,
        )
        session.add(membership)
        next_order += 1
        changed = True

    if changed:
        conversation.updated_at = now
        session.add(conversation)
    return changed


@router.get("/agents")
def list_agents(
    scope: str = Query(default="my"),
    include_archived: bool = Query(default=False),
):
    clean_scope = str(scope or "my").strip().lower()
    if clean_scope not in AGENT_LIST_SCOPES:
        raise HTTPException(400, "scope must be my|public|installed")
    principal = get_current_principal()
    is_admin = principal.role == "admin"
    current_user_id = get_current_user_id(required=not is_admin)
    current_service_id = _current_service_id()

    with Session(engine) as session:
        query = select(Agent).order_by(Agent.updated_at.desc(), Agent.created_at.desc(), Agent.id.desc())
        if not include_archived:
            query = query.where(Agent.is_archived == False)  # noqa: E712

        if clean_scope == "public":
            query = query.where(Agent.visibility == "public")
        elif clean_scope == "installed":
            if not current_user_id:
                raise HTTPException(401, "telegram user identity required")
            query = query.where(Agent.owner_user_id == current_user_id).where(Agent.source_agent_id.is_not(None))
        elif not is_admin:
            query = query.where(Agent.owner_user_id == current_user_id)

        rows = session.exec(query).all()
        visible_rows = [
            row
            for row in rows
            if _can_read_agent(
                row,
                user_id=current_user_id,
                service_id=current_service_id,
                is_admin=is_admin,
            )
        ]
        out = _serialize_agents(
            session,
            visible_rows,
            current_user_id=current_user_id,
            is_admin=is_admin,
        )
        return {"ok": True, "items": out}


@router.post("/agents")
def create_agent(body: AgentCreateRequest):
    principal = get_current_principal()
    is_admin = principal.role == "admin"
    owner_user_id = get_current_user_id(required=not is_admin)
    service_id = _current_service_id()
    clean_name = (body.name or "").strip()
    if not clean_name:
        raise HTTPException(400, "name is required")

    now = utcnow()
    with Session(engine) as session:
        created = Agent(
            owner_user_id=owner_user_id or "admin",
            service_id=service_id,
            name=clean_name,
            description=(body.description or "").strip(),
            system_prompt=(body.system_prompt or "").strip(),
            instruction=(body.instruction or "").strip(),
            tools_json=_jdump(_normalize_tools(body.tools)),
            model=(body.model or "").strip(),
            visibility=_clean_visibility(body.visibility),
            source_agent_id=None,
            system_key=None,
            is_system_default=False,
            is_archived=False,
            created_at=now,
            updated_at=now,
        )
        session.add(created)
        session.flush()
        _append_agent_revision(
            session,
            created,
            actor_user_id=owner_user_id,
            reason="create",
        )
        session.commit()
        session.refresh(created)
        return {
            "ok": True,
            "agent": _serialize_agent(
                session,
                created,
                current_user_id=owner_user_id,
                is_admin=is_admin,
            ),
        }


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str):
    principal = get_current_principal()
    is_admin = principal.role == "admin"
    current_user_id = get_current_user_id(required=not is_admin)
    service_id = _current_service_id()
    with Session(engine) as session:
        row = _get_agent_or_404(session, agent_id)
        if not _can_read_agent(row, user_id=current_user_id, service_id=service_id, is_admin=is_admin):
            raise HTTPException(404, "agent not found")
        return {
            "ok": True,
            "agent": _serialize_agent(
                session,
                row,
                current_user_id=current_user_id,
                is_admin=is_admin,
            ),
        }


@router.patch("/agents/{agent_id}")
def patch_agent(agent_id: str, body: AgentPatchRequest):
    principal = get_current_principal()
    is_admin = principal.role == "admin"
    current_user_id = get_current_user_id(required=not is_admin)
    with Session(engine) as session:
        row = _get_agent_or_404(session, agent_id)
        if not _can_write_agent(row, user_id=current_user_id, is_admin=is_admin):
            raise HTTPException(403, "agent write access denied")

        changed = False
        if body.name is not None:
            clean = body.name.strip()
            if not clean:
                raise HTTPException(400, "name must not be empty")
            if row.name != clean:
                row.name = clean
                changed = True
        if body.description is not None:
            clean = body.description.strip()
            if row.description != clean:
                row.description = clean
                changed = True
        if body.system_prompt is not None:
            clean = body.system_prompt.strip()
            if row.system_prompt != clean:
                row.system_prompt = clean
                changed = True
        if body.instruction is not None:
            clean = body.instruction.strip()
            if row.instruction != clean:
                row.instruction = clean
                changed = True
        if body.tools is not None:
            clean = _jdump(_normalize_tools(body.tools))
            if row.tools_json != clean:
                row.tools_json = clean
                changed = True
        if body.model is not None:
            clean = body.model.strip()
            if row.model != clean:
                row.model = clean
                changed = True
        if body.visibility is not None:
            clean_visibility = _clean_visibility(body.visibility)
            if row.visibility != clean_visibility:
                row.visibility = clean_visibility
                changed = True

        if changed:
            row.updated_at = utcnow()
            session.add(row)
            _append_agent_revision(
                session,
                row,
                actor_user_id=current_user_id,
                reason="update",
            )
            session.commit()
            session.refresh(row)
        return {
            "ok": True,
            "agent": _serialize_agent(
                session,
                row,
                current_user_id=current_user_id,
                is_admin=is_admin,
            ),
        }


@router.post("/agents/{agent_id}/fork")
def fork_agent(agent_id: str, body: AgentForkRequest):
    principal = get_current_principal()
    is_admin = principal.role == "admin"
    current_user_id = get_current_user_id(required=not is_admin)
    service_id = _current_service_id()

    with Session(engine) as session:
        source = _get_agent_or_404(session, agent_id)
        if not _can_read_agent(source, user_id=current_user_id, service_id=service_id, is_admin=is_admin):
            raise HTTPException(404, "agent not found")

        now = utcnow()
        created = Agent(
            owner_user_id=current_user_id or "admin",
            service_id=service_id,
            name=(body.name or "").strip() or f"{source.name} (fork)",
            description=(body.description if body.description is not None else source.description).strip(),
            system_prompt=(body.system_prompt if body.system_prompt is not None else source.system_prompt).strip(),
            instruction=(body.instruction if body.instruction is not None else source.instruction).strip(),
            tools_json=_jdump(_normalize_tools(body.tools if body.tools is not None else _jload(source.tools_json, []))),
            model=(body.model if body.model is not None else source.model).strip(),
            visibility=_clean_visibility(body.visibility, default="private"),
            source_agent_id=source.id,
            system_key=None,
            is_system_default=False,
            is_archived=False,
            created_at=now,
            updated_at=now,
        )
        session.add(created)
        session.flush()
        _append_agent_revision(
            session,
            created,
            actor_user_id=current_user_id,
            reason=f"fork:{source.id}",
        )
        session.commit()
        session.refresh(created)
        return {
            "ok": True,
            "agent": _serialize_agent(
                session,
                created,
                current_user_id=current_user_id,
                is_admin=is_admin,
            ),
        }


@router.post("/agents/{agent_id}/publish")
def publish_agent(agent_id: str):
    principal = get_current_principal()
    is_admin = principal.role == "admin"
    current_user_id = get_current_user_id(required=not is_admin)
    with Session(engine) as session:
        row = _get_agent_or_404(session, agent_id)
        if not _can_write_agent(row, user_id=current_user_id, is_admin=is_admin):
            raise HTTPException(403, "agent write access denied")
        row.visibility = "public"
        row.updated_at = utcnow()
        session.add(row)
        _append_agent_revision(
            session,
            row,
            actor_user_id=current_user_id,
            reason="publish",
        )
        session.commit()
        session.refresh(row)
        return {
            "ok": True,
            "agent": _serialize_agent(
                session,
                row,
                current_user_id=current_user_id,
                is_admin=is_admin,
            ),
        }


@router.post("/agents/{agent_id}/unpublish")
def unpublish_agent(agent_id: str):
    principal = get_current_principal()
    is_admin = principal.role == "admin"
    current_user_id = get_current_user_id(required=not is_admin)
    with Session(engine) as session:
        row = _get_agent_or_404(session, agent_id)
        if not _can_write_agent(row, user_id=current_user_id, is_admin=is_admin):
            raise HTTPException(403, "agent write access denied")
        row.visibility = "private"
        row.updated_at = utcnow()
        session.add(row)
        _append_agent_revision(
            session,
            row,
            actor_user_id=current_user_id,
            reason="unpublish",
        )
        session.commit()
        session.refresh(row)
        return {
            "ok": True,
            "agent": _serialize_agent(
                session,
                row,
                current_user_id=current_user_id,
                is_admin=is_admin,
            ),
        }


@router.post("/agents/{agent_id}/archive")
def archive_agent(agent_id: str, body: AgentArchiveRequest):
    principal = get_current_principal()
    is_admin = principal.role == "admin"
    current_user_id = get_current_user_id(required=not is_admin)
    with Session(engine) as session:
        row = _get_agent_or_404(session, agent_id)
        if not _can_write_agent(row, user_id=current_user_id, is_admin=is_admin):
            raise HTTPException(403, "agent write access denied")
        next_archived = bool(body.archived)
        row.is_archived = next_archived
        row.updated_at = utcnow()
        session.add(row)
        _append_agent_revision(
            session,
            row,
            actor_user_id=current_user_id,
            reason="archive" if next_archived else "unarchive",
        )
        session.commit()
        session.refresh(row)
        return {
            "ok": True,
            "agent": _serialize_agent(
                session,
                row,
                current_user_id=current_user_id,
                is_admin=is_admin,
            ),
        }


@router.get("/agents/defaults")
def list_default_agents():
    principal = get_current_principal()
    is_admin = principal.role == "admin"
    current_user_id = get_current_user_id(required=not is_admin)
    with Session(engine) as session:
        ensure_default_agents(session)
        session.commit()
        rows = session.exec(
            select(Agent)
            .where(Agent.is_system_default == True)  # noqa: E712
            .where(Agent.is_archived == False)  # noqa: E712
            .order_by(Agent.system_key.asc(), Agent.name.asc(), Agent.id.asc())
        ).all()
        return {
            "ok": True,
            "items": _serialize_agents(
                session,
                rows,
                current_user_id=current_user_id,
                is_admin=is_admin,
            ),
        }


@router.post("/agents/bootstrap_defaults")
def bootstrap_default_agents(body: AgentBootstrapDefaultsRequest):
    principal = get_current_principal()
    is_admin = principal.role == "admin"
    current_user_id = get_current_user_id(required=not is_admin)
    service_id = _current_service_id()
    thread_id = (body.thread_id or "").strip() or None

    if not current_user_id and not is_admin:
        raise HTTPException(401, "telegram user identity required")

    with Session(engine) as session:
        installed_items = _install_default_private_agents(
            session,
            owner_user_id=current_user_id or "admin",
            actor_user_id=current_user_id,
            service_id=service_id,
        )

        conversation: Conversation | None = None
        if body.add_to_conversation and thread_id:
            _, conversation = _ensure_conversation(
                session,
                thread_id=thread_id,
                owner_user_id=current_user_id or "admin",
                service_id=service_id,
                is_admin=is_admin,
            )
            _add_missing_conversation_memberships(
                session,
                conversation=conversation,
                agents=installed_items,
                only_if_empty=False,
            )

        session.commit()
        if conversation:
            session.refresh(conversation)
        for item in installed_items:
            session.refresh(item)

        response: dict[str, Any] = {
            "ok": True,
            "installed": _serialize_agents(
                session,
                installed_items,
                current_user_id=current_user_id,
                is_admin=is_admin,
            ),
            "installed_count": len(installed_items),
        }
        if conversation:
            memberships = _conversation_memberships(session, conversation.id)
            agent_ids = [row.agent_id for row in memberships]
            agents_map = {
                row.id: row
                for row in session.exec(select(Agent).where(Agent.id.in_(agent_ids))).all()
            } if agent_ids else {}
            response["conversation"] = _conversation_payload(
                conversation,
                memberships=memberships,
                agents_by_id=agents_map,
                current_user_id=current_user_id,
                is_admin=is_admin,
            )
        return response


@router.post("/conversations/ensure")
def ensure_conversation(body: ConversationEnsureRequest):
    thread_id = (body.thread_id or "").strip()
    if not thread_id:
        raise HTTPException(400, "thread_id is required")

    principal = get_current_principal()
    is_admin = principal.role == "admin"
    current_user_id = get_current_user_id(required=not is_admin)
    service_id = _current_service_id()

    with Session(engine) as session:
        _, conversation = _ensure_conversation(
            session,
            thread_id=thread_id,
            owner_user_id=current_user_id or "admin",
            service_id=service_id,
            is_admin=is_admin,
        )
        if body.bootstrap_defaults:
            installed_items = _install_default_private_agents(
                session,
                owner_user_id=current_user_id or "admin",
                actor_user_id=current_user_id,
                service_id=service_id,
            )
            _add_missing_conversation_memberships(
                session,
                conversation=conversation,
                agents=installed_items,
                only_if_empty=True,
            )
        conversation.updated_at = utcnow()
        session.add(conversation)
        session.commit()
        session.refresh(conversation)

        memberships = _conversation_memberships(session, conversation.id)
        agent_ids = [row.agent_id for row in memberships]
        agents = session.exec(select(Agent).where(Agent.id.in_(agent_ids))).all() if agent_ids else []
        return {
            "ok": True,
            "conversation": _conversation_payload(
                conversation,
                memberships=memberships,
                agents_by_id={row.id: row for row in agents},
                current_user_id=current_user_id,
                is_admin=is_admin,
            ),
        }


@router.get("/conversations/{thread_id}/agents")
def list_conversation_agents(thread_id: str):
    clean_thread_id = (thread_id or "").strip()
    if not clean_thread_id:
        raise HTTPException(400, "thread_id is required")
    principal = get_current_principal()
    is_admin = principal.role == "admin"
    current_user_id = get_current_user_id(required=not is_admin)

    with Session(engine) as session:
        _, conversation = _require_conversation(
            session,
            thread_id=clean_thread_id,
            owner_user_id=current_user_id or "admin",
            is_admin=is_admin,
        )
        memberships = _conversation_memberships(session, conversation.id)
        agent_ids = [row.agent_id for row in memberships]
        agents = session.exec(select(Agent).where(Agent.id.in_(agent_ids))).all() if agent_ids else []
        return {
            "ok": True,
            "conversation": _conversation_payload(
                conversation,
                memberships=memberships,
                agents_by_id={row.id: row for row in agents},
                current_user_id=current_user_id,
                is_admin=is_admin,
            ),
        }


@router.post("/conversations/{thread_id}/agents")
def add_conversation_agent(thread_id: str, body: ConversationAgentCreateRequest):
    clean_thread_id = (thread_id or "").strip()
    agent_id = (body.agent_id or "").strip()
    if not clean_thread_id:
        raise HTTPException(400, "thread_id is required")
    if not agent_id:
        raise HTTPException(400, "agent_id is required")

    principal = get_current_principal()
    is_admin = principal.role == "admin"
    current_user_id = get_current_user_id(required=not is_admin)
    service_id = _current_service_id()

    with Session(engine) as session:
        _, conversation = _ensure_conversation(
            session,
            thread_id=clean_thread_id,
            owner_user_id=current_user_id or "admin",
            service_id=service_id,
            is_admin=is_admin,
        )
        agent = _get_agent_or_404(session, agent_id)
        if agent.is_archived:
            raise HTTPException(400, "archived agent cannot be added")
        if not _can_read_agent(agent, user_id=current_user_id, service_id=service_id, is_admin=is_admin):
            raise HTTPException(404, "agent not found")

        memberships = _conversation_memberships(session, conversation.id)
        existing = next((row for row in memberships if row.agent_id == agent_id), None)
        if not existing:
            target_lineage_key = _agent_lineage_key(agent)
            member_agent_ids = [row.agent_id for row in memberships]
            member_agents = session.exec(
                select(Agent).where(Agent.id.in_(member_agent_ids))
            ).all() if member_agent_ids else []
            member_agents_by_id = {row.id: row for row in member_agents}
            for membership in memberships:
                member_agent = member_agents_by_id.get(membership.agent_id)
                if not member_agent:
                    continue
                if _agent_lineage_key(member_agent) == target_lineage_key:
                    existing = membership
                    break

        now = utcnow()
        if existing:
            existing.enabled = bool(body.enabled)
            if body.order_index is not None:
                existing.order_index = int(body.order_index)
            if body.overrides_json is not None:
                existing.overrides_json = _jdump(body.overrides_json)
            existing.updated_at = now
            session.add(existing)
        else:
            next_order = int(max((row.order_index for row in memberships), default=-1)) + 1
            row = ConversationAgent(
                conversation_id=conversation.id,
                agent_id=agent_id,
                enabled=bool(body.enabled),
                order_index=int(body.order_index) if body.order_index is not None else next_order,
                overrides_json=_jdump(body.overrides_json if body.overrides_json is not None else {}),
                created_at=now,
                updated_at=now,
            )
            session.add(row)

        conversation.updated_at = now
        session.add(conversation)
        session.commit()
        session.refresh(conversation)
        memberships = _conversation_memberships(session, conversation.id)
        agent_ids = [row.agent_id for row in memberships]
        agents = session.exec(select(Agent).where(Agent.id.in_(agent_ids))).all() if agent_ids else []
        return {
            "ok": True,
            "conversation": _conversation_payload(
                conversation,
                memberships=memberships,
                agents_by_id={row.id: row for row in agents},
                current_user_id=current_user_id,
                is_admin=is_admin,
            ),
        }


@router.post("/conversations/{thread_id}/agents/reorder")
def reorder_conversation_agents(thread_id: str, body: ConversationAgentReorderRequest):
    clean_thread_id = (thread_id or "").strip()
    if not clean_thread_id:
        raise HTTPException(400, "thread_id is required")
    principal = get_current_principal()
    is_admin = principal.role == "admin"
    current_user_id = get_current_user_id(required=not is_admin)
    clean_agent_ids = [str(row or "").strip() for row in body.agent_ids if str(row or "").strip()]
    if len(clean_agent_ids) != len(set(clean_agent_ids)):
        raise HTTPException(400, "agent_ids must not contain duplicates")

    with Session(engine) as session:
        _, conversation = _require_conversation(
            session,
            thread_id=clean_thread_id,
            owner_user_id=current_user_id or "admin",
            is_admin=is_admin,
        )
        memberships = _conversation_memberships(session, conversation.id)
        if not memberships:
            return {"ok": True, "conversation": _conversation_payload(
                conversation,
                memberships=[],
                agents_by_id={},
                current_user_id=current_user_id,
                is_admin=is_admin,
            )}

        by_agent_id = {row.agent_id: row for row in memberships}
        current_ids = set(by_agent_id.keys())
        requested_ids = set(clean_agent_ids)
        if current_ids != requested_ids:
            raise HTTPException(400, "agent_ids must match current conversation members")

        now = utcnow()
        for idx, agent_id in enumerate(clean_agent_ids):
            row = by_agent_id[agent_id]
            row.order_index = idx
            row.updated_at = now
            session.add(row)
        conversation.updated_at = now
        session.add(conversation)
        session.commit()
        session.refresh(conversation)

        refreshed = _conversation_memberships(session, conversation.id)
        agent_ids = [row.agent_id for row in refreshed]
        agents = session.exec(select(Agent).where(Agent.id.in_(agent_ids))).all() if agent_ids else []
        return {
            "ok": True,
            "conversation": _conversation_payload(
                conversation,
                memberships=refreshed,
                agents_by_id={row.id: row for row in agents},
                current_user_id=current_user_id,
                is_admin=is_admin,
            ),
        }


@router.patch("/conversations/{thread_id}/agents/{agent_id}")
def patch_conversation_agent(thread_id: str, agent_id: str, body: ConversationAgentPatchRequest):
    clean_thread_id = (thread_id or "").strip()
    clean_agent_id = (agent_id or "").strip()
    if not clean_thread_id or not clean_agent_id:
        raise HTTPException(400, "thread_id and agent_id are required")
    principal = get_current_principal()
    is_admin = principal.role == "admin"
    current_user_id = get_current_user_id(required=not is_admin)

    with Session(engine) as session:
        _, conversation = _require_conversation(
            session,
            thread_id=clean_thread_id,
            owner_user_id=current_user_id or "admin",
            is_admin=is_admin,
        )
        membership = session.exec(
            select(ConversationAgent)
            .where(ConversationAgent.conversation_id == conversation.id)
            .where(ConversationAgent.agent_id == clean_agent_id)
            .limit(1)
        ).first()
        if not membership:
            raise HTTPException(404, "conversation agent not found")

        if body.enabled is not None:
            membership.enabled = bool(body.enabled)
        if body.order_index is not None:
            membership.order_index = int(body.order_index)
        if body.overrides_json is not None:
            membership.overrides_json = _jdump(body.overrides_json)
        membership.updated_at = utcnow()
        session.add(membership)
        conversation.updated_at = utcnow()
        session.add(conversation)
        session.commit()
        session.refresh(conversation)

        memberships = _conversation_memberships(session, conversation.id)
        agent_ids = [row.agent_id for row in memberships]
        agents = session.exec(select(Agent).where(Agent.id.in_(agent_ids))).all() if agent_ids else []
        return {
            "ok": True,
            "conversation": _conversation_payload(
                conversation,
                memberships=memberships,
                agents_by_id={row.id: row for row in agents},
                current_user_id=current_user_id,
                is_admin=is_admin,
            ),
        }


@router.delete("/conversations/{thread_id}/agents/{agent_id}")
def delete_conversation_agent(thread_id: str, agent_id: str):
    clean_thread_id = (thread_id or "").strip()
    clean_agent_id = (agent_id or "").strip()
    if not clean_thread_id or not clean_agent_id:
        raise HTTPException(400, "thread_id and agent_id are required")
    principal = get_current_principal()
    is_admin = principal.role == "admin"
    current_user_id = get_current_user_id(required=not is_admin)

    with Session(engine) as session:
        _, conversation = _require_conversation(
            session,
            thread_id=clean_thread_id,
            owner_user_id=current_user_id or "admin",
            is_admin=is_admin,
        )
        membership = session.exec(
            select(ConversationAgent)
            .where(ConversationAgent.conversation_id == conversation.id)
            .where(ConversationAgent.agent_id == clean_agent_id)
            .limit(1)
        ).first()
        if membership:
            session.delete(membership)
        conversation.updated_at = utcnow()
        session.add(conversation)
        session.commit()
        session.refresh(conversation)

        memberships = _conversation_memberships(session, conversation.id)
        agent_ids = [row.agent_id for row in memberships]
        agents = session.exec(select(Agent).where(Agent.id.in_(agent_ids))).all() if agent_ids else []
        return {
            "ok": True,
            "conversation": _conversation_payload(
                conversation,
                memberships=memberships,
                agents_by_id={row.id: row for row in agents},
                current_user_id=current_user_id,
                is_admin=is_admin,
            ),
        }
