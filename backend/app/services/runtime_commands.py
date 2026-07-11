from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import RuntimeCommand, RuntimeCommandEvent, utcnow

COMMAND_STATUSES = {'queued', 'accepted', 'applied', 'rejected', 'failed', 'cancelled'}
TERMINAL_STATUSES = {'applied', 'rejected', 'failed', 'cancelled'}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean(value: Any = '', max_len: int = 500, lower: bool = False) -> str:
    text = str(value or '').strip()[:max_len]
    return text.lower() if lower else text


def _loads(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(raw or '')
    except Exception:
        return fallback


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def serialize_runtime_command(row: RuntimeCommand) -> dict[str, Any]:
    return {
        'kind': 'runtime_command_v1',
        'command_id': row.command_id,
        'command_type': row.command_type,
        'thread_id': row.thread_id,
        'aggregate_type': row.aggregate_type,
        'aggregate_id': row.aggregate_id,
        'expected_revision': row.expected_revision,
        'status': row.status,
        'actor': {'type': row.actor_type, 'id': row.actor_id},
        'worker_id': row.worker_id,
        'payload': _loads(row.payload_json, {}),
        'result': _loads(row.result_json, {}),
        'error_message': row.error_message,
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'accepted_at': row.accepted_at.isoformat() if row.accepted_at else None,
        'completed_at': row.completed_at.isoformat() if row.completed_at else None,
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
    }


def _record_event(session: Session, row: RuntimeCommand, event_type: str, *, worker_id: str = '', data: dict[str, Any] | None = None) -> RuntimeCommandEvent:
    event = RuntimeCommandEvent(
        command_id=row.command_id,
        event_type=_clean(event_type, 80, True) or 'updated',
        status=row.status,
        worker_id=_clean(worker_id, 160),
        event_json=_dumps(data or {}),
    )
    session.add(event)
    return event


def create_runtime_command(session: Session, body: dict[str, Any]) -> tuple[RuntimeCommand, bool]:
    data = _as_dict(body)
    command_id = _clean(data.get('command_id') or f'cmd_{uuid4().hex}', 200)
    command_type = _clean(data.get('command_type'), 120, True)
    if not command_type:
        raise HTTPException(400, 'command_type is required')
    existing = session.exec(select(RuntimeCommand).where(RuntimeCommand.command_id == command_id)).first()
    if existing:
        return existing, False
    actor = _as_dict(data.get('actor'))
    row = RuntimeCommand(
        command_id=command_id,
        command_type=command_type,
        thread_id=_clean(data.get('thread_id'), 160) or None,
        aggregate_type=_clean(data.get('aggregate_type') or 'room', 80, True),
        aggregate_id=_clean(data.get('aggregate_id'), 200),
        expected_revision=max(0, int(data.get('expected_revision') or 0)),
        status='queued',
        actor_type=_clean(actor.get('type') or 'user', 80, True),
        actor_id=_clean(actor.get('id'), 160),
        payload_json=_dumps(_as_dict(data.get('payload'))),
    )
    session.add(row)
    session.flush()
    _record_event(session, row, 'created', data={'request': data})
    return row, True


def list_runtime_commands(session: Session, *, statuses: list[str] | None = None, limit: int = 50) -> list[RuntimeCommand]:
    stmt = select(RuntimeCommand)
    clean_statuses = [_clean(status, 40, True) for status in (statuses or []) if _clean(status, 40, True) in COMMAND_STATUSES]
    if clean_statuses:
        stmt = stmt.where(RuntimeCommand.status.in_(clean_statuses))
    stmt = stmt.order_by(RuntimeCommand.created_at.asc()).limit(max(1, min(int(limit or 50), 500)))
    return list(session.exec(stmt).all())


def get_runtime_command(session: Session, command_id: str) -> RuntimeCommand:
    clean_id = _clean(command_id, 200)
    row = session.exec(select(RuntimeCommand).where(RuntimeCommand.command_id == clean_id)).first()
    if not row:
        raise HTTPException(404, 'runtime command not found')
    return row


def acknowledge_runtime_command(session: Session, row: RuntimeCommand, body: dict[str, Any]) -> RuntimeCommand:
    data = _as_dict(body)
    status = _clean(data.get('status') or 'accepted', 40, True)
    if status not in COMMAND_STATUSES - {'queued'}:
        raise HTTPException(400, f'unsupported command status: {status}')
    if row.status in TERMINAL_STATUSES and row.status != status:
        raise HTTPException(409, f'command already terminal: {row.status}')
    worker_id = _clean(data.get('worker_id'), 160)
    if row.status == 'accepted' and row.worker_id and worker_id and row.worker_id != worker_id:
        raise HTTPException(409, f'command already claimed by worker: {row.worker_id}')
    if row.status in TERMINAL_STATUSES and row.worker_id and worker_id and row.worker_id != worker_id:
        raise HTTPException(409, f'command completed by another worker: {row.worker_id}')
    now = utcnow()
    if status == 'accepted' and row.accepted_at is None:
        row.accepted_at = now
    if status in TERMINAL_STATUSES:
        row.completed_at = now
    row.status = status
    row.worker_id = worker_id or row.worker_id
    row.result_json = _dumps(_as_dict(data.get('result')))
    row.error_message = _clean(data.get('error_message'), 4000)
    row.updated_at = now
    session.add(row)
    _record_event(session, row, f'command.{status}', worker_id=worker_id, data=data)
    return row
