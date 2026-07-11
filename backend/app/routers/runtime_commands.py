from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.auth import get_current_principal, require_service_key_principal
from app.db import engine
from app.services.runtime_commands import (
    acknowledge_runtime_command,
    create_runtime_command,
    get_runtime_command,
    list_runtime_commands,
    serialize_runtime_command,
)

router = APIRouter(prefix='/api/runtime/commands', tags=['runtime-commands'])


class RuntimeCommandCreateRequest(BaseModel):
    command_id: str = ''
    command_type: str
    thread_id: str = ''
    aggregate_type: str = 'room'
    aggregate_id: str = ''
    expected_revision: int = 0
    actor: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


class RuntimeCommandAckRequest(BaseModel):
    status: str = 'accepted'
    worker_id: str = ''
    result: dict[str, Any] = Field(default_factory=dict)
    error_message: str = ''


@router.post('')
def create_command(body: RuntimeCommandCreateRequest):
    principal = get_current_principal()
    request = body.model_dump()
    request['actor'] = {
        'type': principal.role,
        'id': principal.user_id or principal.service_id or principal.telegram_user_id or '',
    }
    with Session(engine) as session:
        row, created = create_runtime_command(session, request)
        session.commit()
        session.refresh(row)
        return {'created': created, 'command': serialize_runtime_command(row)}


@router.get('')
def list_commands(status: str = '', limit: int = 50):
    get_current_principal()
    statuses = [item.strip() for item in str(status or '').split(',') if item.strip()]
    with Session(engine) as session:
        rows = list_runtime_commands(session, statuses=statuses, limit=limit)
        return {'count': len(rows), 'items': [serialize_runtime_command(row) for row in rows]}


@router.get('/pending')
def list_pending_commands(limit: int = 50, worker_id: str = ''):
    require_service_key_principal()
    with Session(engine) as session:
        rows = list_runtime_commands(session, statuses=['queued'], limit=limit)
        return {
            'kind': 'runtime_command_queue_v1',
            'worker_id': worker_id,
            'count': len(rows),
            'items': [serialize_runtime_command(row) for row in rows],
        }


@router.get('/{command_id}')
def read_command(command_id: str):
    get_current_principal()
    with Session(engine) as session:
        return serialize_runtime_command(get_runtime_command(session, command_id))


@router.post('/{command_id}/ack')
def ack_command(command_id: str, body: RuntimeCommandAckRequest):
    require_service_key_principal()
    with Session(engine) as session:
        row = get_runtime_command(session, command_id)
        row = acknowledge_runtime_command(session, row, body.model_dump())
        session.commit()
        session.refresh(row)
        return {'command': serialize_runtime_command(row)}
