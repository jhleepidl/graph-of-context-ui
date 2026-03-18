from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from app.models import Conversation, ConversationTeamConfig, ConversationTeamConfigRevision


def _jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def _jdump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _normalize_composition_mode(raw: Any, *, fallback: str = 'structured') -> str:
    value = str(raw or fallback).strip().lower() or fallback
    return value if value in {'structured', 'freeform'} else (fallback if fallback in {'structured', 'freeform'} else 'structured')


def _normalize_proposal_mode(raw: Any, *, fallback: str = 'suggest') -> str:
    value = str(raw or fallback).strip().lower() or fallback
    return value if value in {'suggest', 'create', 'refine', 'validate', 'apply'} else (fallback if fallback in {'suggest', 'create', 'refine', 'validate', 'apply'} else 'suggest')


def _normalize_team_config_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    status = str(raw.get('status') or 'none').strip().lower() or 'none'
    if status not in {'none', 'suggested', 'active', 'locked', 'editable'}:
        status = 'active' if raw.get('active_team') else ('suggested' if raw.get('pending_team') else 'none')
    active_team = raw.get('active_team') or raw.get('team_config') or {}
    pending_team = raw.get('pending_team') or {}
    if not isinstance(active_team, dict):
        active_team = {}
    if not isinstance(pending_team, dict):
        pending_team = {}
    composition_mode = _normalize_composition_mode(raw.get('composition_mode') or active_team.get('composition_mode') or pending_team.get('composition_mode') or 'structured')
    proposal_mode = _normalize_proposal_mode(raw.get('proposal_mode') or active_team.get('proposal_mode') or pending_team.get('proposal_mode') or ('create' if composition_mode == 'freeform' else 'suggest'))
    if status == 'none':
        active_team = {}
        pending_team = {}
    return {'status': status, 'composition_mode': composition_mode, 'proposal_mode': proposal_mode, 'active_team': active_team, 'pending_team': pending_team}


def _ensure_conversation(session: Session, *, thread_id: str) -> Conversation | None:
    return session.exec(select(Conversation).where(Conversation.thread_id == thread_id)).first()


def get_team_config_payload(session: Session, *, thread_id: str) -> dict[str, Any]:
    conversation = _ensure_conversation(session, thread_id=thread_id)
    if not conversation:
        return {
            "thread_id": thread_id,
            "conversation_id": "",
            "status": "none",
            "composition_mode": "structured",
            "proposal_mode": "suggest",
            "active_team": {},
            "pending_team": {},
            "updated_at": None,
        }
    row = session.exec(
        select(ConversationTeamConfig).where(ConversationTeamConfig.conversation_id == conversation.id)
    ).first()
    if not row:
        return {
            "thread_id": thread_id,
            "conversation_id": conversation.id,
            "status": "none",
            "composition_mode": "structured",
            "proposal_mode": "suggest",
            "active_team": {},
            "pending_team": {},
            "updated_at": None,
        }
    return {
        "thread_id": row.thread_id,
        "conversation_id": row.conversation_id,
        "status": row.status or "none",
        "composition_mode": _normalize_composition_mode((_jload(row.active_team_json, {}) or {}).get('composition_mode') or (_jload(row.pending_team_json, {}) or {}).get('composition_mode') or 'structured'),
        "proposal_mode": _normalize_proposal_mode((_jload(row.active_team_json, {}) or {}).get('proposal_mode') or (_jload(row.pending_team_json, {}) or {}).get('proposal_mode') or 'suggest'),
        "active_team": _jload(row.active_team_json, {}),
        "pending_team": _jload(row.pending_team_json, {}),
        "updated_at": row.updated_at,
    }


def save_team_config_payload(session: Session, *, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    conversation = _ensure_conversation(session, thread_id=thread_id)
    if not conversation:
        raise ValueError("conversation not found for thread")
    row = session.exec(
        select(ConversationTeamConfig).where(ConversationTeamConfig.conversation_id == conversation.id)
    ).first()
    if not row:
        row = ConversationTeamConfig(conversation_id=conversation.id, thread_id=thread_id)
    normalized = _normalize_team_config_payload(payload)
    row.status = normalized['status']
    row.active_team_json = _jdump(normalized['active_team'])
    row.pending_team_json = _jdump(normalized['pending_team'])
    session.add(row)
    session.flush()
    session.add(ConversationTeamConfigRevision(
        conversation_id=conversation.id,
        thread_id=thread_id,
        revision_kind="update",
        payload_json=_jdump({
            "status": row.status,
            "composition_mode": normalized['composition_mode'],
            "proposal_mode": normalized['proposal_mode'],
            "active_team": _jload(row.active_team_json, {}),
            "pending_team": _jload(row.pending_team_json, {}),
        }),
    ))
    session.commit()
    session.refresh(row)
    return {
        "thread_id": row.thread_id,
        "conversation_id": row.conversation_id,
        "status": row.status,
        "composition_mode": normalized['composition_mode'],
        "proposal_mode": normalized['proposal_mode'],
        "active_team": _jload(row.active_team_json, {}),
        "pending_team": _jload(row.pending_team_json, {}),
        "updated_at": row.updated_at,
    }
