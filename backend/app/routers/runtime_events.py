from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.auth import get_current_principal, require_service_key_principal
from app.db import engine
from app.models import RuntimeRunProjection
from app.services.runtime_events import (
    ingest_runtime_events,
    list_runtime_events,
    serialize_run_projection,
    serialize_runtime_event,
)

router = APIRouter(prefix='/api/runtime', tags=['runtime-events'])


class RuntimeEventIngestRequest(BaseModel):
    events: list[dict[str, Any]] = Field(default_factory=list)


@router.post('/events/ingest')
def ingest_events(body: RuntimeEventIngestRequest):
    require_service_key_principal()
    if not body.events:
        raise HTTPException(400, 'events are required')
    if len(body.events) > 1000:
        raise HTTPException(400, 'at most 1000 events may be ingested at once')
    with Session(engine) as session:
        result = ingest_runtime_events(session, body.events)
        session.commit()
        return result


@router.get('/events')
def read_events(run_id: str = '', thread_id: str = '', limit: int = 200):
    get_current_principal()
    with Session(engine) as session:
        rows = list_runtime_events(session, run_id=run_id, thread_id=thread_id, limit=limit)
        return {
            'kind': 'runtime_event_list_v1',
            'count': len(rows),
            'items': [serialize_runtime_event(row) for row in rows],
        }


@router.get('/runs/{run_id}/projection')
def read_run_projection(run_id: str):
    get_current_principal()
    with Session(engine) as session:
        row = session.exec(select(RuntimeRunProjection).where(RuntimeRunProjection.run_id == str(run_id or '').strip())).first()
        if not row:
            raise HTTPException(404, 'runtime run projection not found')
        return serialize_run_projection(row)
