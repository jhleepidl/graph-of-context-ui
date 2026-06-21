from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from sqlmodel import Session

from app.db import engine
from app.services.room_usage import get_room_learning_snapshot, list_room_usage_events, record_room_usage_event
from app.services.room_evolution import public_room_evolution_export
from app.tenant import require_thread_access, require_thread_write_access

router = APIRouter(prefix='/api', tags=['room-usage'])


@router.get('/threads/{thread_id}/room-usage-events')
def get_thread_room_usage_events(thread_id: str, limit: int = 200):
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        return list_room_usage_events(session, thread, limit=limit)


@router.post('/threads/{thread_id}/room-usage-events')
def post_thread_room_usage_event(thread_id: str, body: dict[str, Any] = Body(default_factory=dict)):
    with Session(engine) as session:
        thread = require_thread_write_access(session, thread_id)
        return record_room_usage_event(session, thread, body or {})



@router.get('/threads/{thread_id}/room-learning')
def get_thread_room_learning(thread_id: str, limit: int = 200):
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        return get_room_learning_snapshot(session, thread, limit=limit)


@router.get('/threads/{thread_id}/room-evolution')
def get_thread_room_evolution(thread_id: str, limit: int = 200):
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        learning = get_room_learning_snapshot(session, thread, limit=limit)
        snapshot = ((learning.get('snapshot') or {}).get('room_evolution') or {})
        return {'ok': True, 'thread_id': thread.id, 'snapshot': snapshot}


@router.get('/threads/{thread_id}/room-evolution/public-export')
def get_thread_room_evolution_public_export(thread_id: str, limit: int = 200):
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        learning = get_room_learning_snapshot(session, thread, limit=limit)
        snapshot = ((learning.get('snapshot') or {}).get('room_evolution') or {})
        return {'ok': True, 'thread_id': thread.id, 'export': public_room_evolution_export(snapshot)}
