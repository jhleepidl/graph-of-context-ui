from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body
from sqlmodel import Session

from app.db import engine
from app.services.room_usage import list_room_usage_events, record_room_usage_event
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
