from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, or_
from sqlmodel import Session, select

from app.models import RuntimeEvent, RuntimeRunProjection, utcnow

TRACE_SCHEMA = 'openharness.run_trace/v1'
SYNC_SCHEMA = 'openharness.run_sync/v1'


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


def _parse_datetime(value: Any) -> datetime:
    raw = _clean(value, 80)
    if not raw:
        return utcnow()
    try:
        parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return utcnow()


def _payload_digest(payload: dict[str, Any]) -> str:
    encoded = _dumps(payload).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()[:24]


def normalize_runtime_event(raw: dict[str, Any]) -> dict[str, Any]:
    row = _as_dict(raw)
    payload = _as_dict(row.get('payload'))
    event_id = _clean(row.get('event_id') or row.get('idempotency_key'), 200)
    event_type = _clean(row.get('event_type'), 120, True)
    run_id = _clean(row.get('run_id') or payload.get('run_id') or payload.get('runId'), 160)
    job_id = _clean(row.get('job_id') or payload.get('job_id') or payload.get('jobId'), 160)
    thread_id = _clean(row.get('thread_id') or payload.get('thread_id') or payload.get('threadId'), 160)
    if not event_id:
        raise HTTPException(400, 'event_id is required')
    if not event_type:
        raise HTTPException(400, 'event_type is required')
    schema_version = _clean(row.get('schema_version'), 80)
    sync_schema_version = _clean(row.get('sync_schema_version'), 80)
    if schema_version and schema_version != TRACE_SCHEMA:
        raise HTTPException(400, f'unsupported schema_version: {schema_version}')
    if sync_schema_version and sync_schema_version != SYNC_SCHEMA:
        raise HTTPException(400, f'unsupported sync_schema_version: {sync_schema_version}')
    return {
        **row,
        'schema_version': schema_version or TRACE_SCHEMA,
        'sync_schema_version': sync_schema_version or SYNC_SCHEMA,
        'event_id': event_id,
        'idempotency_key': _clean(row.get('idempotency_key') or event_id, 200),
        'event_type': event_type,
        'event_sequence': max(0, int(row.get('event_sequence') or 0)),
        'run_id': run_id,
        'job_id': job_id,
        'thread_id': thread_id,
        'source': _clean(row.get('source') or 'ddalggak', 80, True),
        'target': _clean(row.get('target') or 'goc', 80, True),
        'correlation_id': _clean(row.get('correlation_id') or run_id or job_id or event_id, 200),
        'causation_id': _clean(row.get('causation_id'), 200),
        'command_id': _clean(row.get('command_id') or payload.get('command_id'), 200),
        'aggregate_type': _clean(row.get('aggregate_type') or ('run' if run_id else 'job'), 80, True),
        'aggregate_id': _clean(row.get('aggregate_id') or run_id or job_id or event_id, 200),
        'aggregate_revision': max(0, int(row.get('aggregate_revision') or row.get('event_sequence') or 0)),
        'privacy_class': _clean(row.get('privacy_class') or 'internal_runtime', 80, True),
        'payload_digest': _clean(row.get('payload_digest') or _payload_digest(payload), 80, True),
        'occurred_at': _parse_datetime(row.get('occurred_at') or row.get('ts')),
        'payload': payload,
    }


def serialize_runtime_event(row: RuntimeEvent) -> dict[str, Any]:
    return {
        'id': row.id,
        'event_id': row.event_id,
        'idempotency_key': row.idempotency_key,
        'thread_id': row.thread_id,
        'run_id': row.run_id,
        'job_id': row.job_id,
        'event_sequence': row.event_sequence,
        'event_type': row.event_type,
        'source': row.source,
        'target': row.target,
        'correlation_id': row.correlation_id,
        'causation_id': row.causation_id,
        'command_id': row.command_id,
        'aggregate_type': row.aggregate_type,
        'aggregate_id': row.aggregate_id,
        'aggregate_revision': row.aggregate_revision,
        'privacy_class': row.privacy_class,
        'payload_digest': row.payload_digest,
        'payload': _loads(row.payload_json, {}),
        'occurred_at': row.occurred_at.isoformat() if row.occurred_at else None,
        'ingested_at': row.ingested_at.isoformat() if row.ingested_at else None,
    }


def _event_status(event_type: str, payload: dict[str, Any], current: str) -> str:
    explicit = _clean(payload.get('status') or _as_dict(payload.get('result')).get('status'), 80, True)
    if explicit in {'failed', 'error', 'cancelled', 'canceled', 'completed', 'done', 'running'}:
        return 'cancelled' if explicit == 'canceled' else ('completed' if explicit == 'done' else explicit)
    if event_type in {'run.start', 'run.started'}:
        return 'running'
    if event_type in {'run.finish', 'run.completed'}:
        return 'completed'
    if event_type in {'run.failed'}:
        return 'failed'
    if event_type in {'run.cancelled', 'run.canceled'}:
        return 'cancelled'
    return current


def rebuild_run_projection(session: Session, run_id: str) -> RuntimeRunProjection | None:
    clean_run_id = _clean(run_id, 160)
    if not clean_run_id:
        return None
    events = list(session.exec(
        select(RuntimeEvent)
        .where(RuntimeEvent.run_id == clean_run_id)
        .order_by(RuntimeEvent.event_sequence.asc(), RuntimeEvent.occurred_at.asc(), RuntimeEvent.ingested_at.asc())
    ).all())
    if not events:
        return None
    status = 'unknown'
    started_at = None
    finished_at = None
    agent_ids: list[str] = []
    providers: list[str] = []
    command_ids: list[str] = []
    error_count = 0
    agent_event_count = 0
    for event in events:
        payload = _loads(event.payload_json, {})
        status = _event_status(event.event_type, payload, status)
        if event.event_type in {'run.start', 'run.started'} and started_at is None:
            started_at = event.occurred_at
        if event.event_type in {'run.finish', 'run.completed', 'run.failed', 'run.cancelled', 'run.canceled'}:
            finished_at = event.occurred_at
        if 'agent' in event.event_type:
            agent_event_count += 1
        if 'error' in event.event_type or event.event_type == 'run.failed':
            error_count += 1
        agent_id = _clean(payload.get('agent_id') or payload.get('agentId') or payload.get('agent'), 160)
        provider = _clean(payload.get('provider'), 80, True)
        if agent_id and agent_id not in agent_ids:
            agent_ids.append(agent_id)
        if provider and provider not in providers:
            providers.append(provider)
        if event.command_id and event.command_id not in command_ids:
            command_ids.append(event.command_id)
    last = events[-1]
    projection_payload = {
        'kind': 'runtime_run_projection_v1',
        'run_id': clean_run_id,
        'thread_id': next((event.thread_id for event in reversed(events) if event.thread_id), None),
        'job_id': next((event.job_id for event in reversed(events) if event.job_id), None),
        'status': status,
        'event_count': len(events),
        'last_sequence': max(event.event_sequence for event in events),
        'last_event_type': last.event_type,
        'agent_ids': agent_ids,
        'providers': providers,
        'command_ids': command_ids,
        'error_count': error_count,
        'started_at': started_at.isoformat() if started_at else None,
        'finished_at': finished_at.isoformat() if finished_at else None,
    }
    projection = session.exec(select(RuntimeRunProjection).where(RuntimeRunProjection.run_id == clean_run_id)).first()
    if projection is None:
        projection = RuntimeRunProjection(run_id=clean_run_id)
    projection.thread_id = projection_payload['thread_id']
    projection.job_id = projection_payload['job_id']
    projection.status = status
    projection.last_event_type = last.event_type
    projection.last_sequence = projection_payload['last_sequence']
    projection.event_count = len(events)
    projection.agent_event_count = agent_event_count
    projection.error_count = error_count
    projection.command_count = len(command_ids)
    projection.projection_json = _dumps(projection_payload)
    projection.started_at = started_at
    projection.finished_at = finished_at
    projection.updated_at = utcnow()
    session.add(projection)
    session.flush()
    return projection


def serialize_run_projection(row: RuntimeRunProjection) -> dict[str, Any]:
    payload = _loads(row.projection_json, {})
    return {
        **payload,
        'id': row.id,
        'run_id': row.run_id,
        'thread_id': row.thread_id,
        'job_id': row.job_id,
        'status': row.status,
        'last_event_type': row.last_event_type,
        'last_sequence': row.last_sequence,
        'event_count': row.event_count,
        'agent_event_count': row.agent_event_count,
        'error_count': row.error_count,
        'command_count': row.command_count,
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
    }


def ingest_runtime_events(session: Session, events: list[dict[str, Any]]) -> dict[str, Any]:
    accepted: list[str] = []
    duplicates: list[str] = []
    affected_runs: list[str] = []
    for raw in events:
        event = normalize_runtime_event(raw)
        existing = session.exec(select(RuntimeEvent).where(RuntimeEvent.event_id == event['event_id'])).first()
        if existing:
            duplicates.append(event['event_id'])
            continue
        row = RuntimeEvent(
            event_id=event['event_id'],
            idempotency_key=event['idempotency_key'],
            thread_id=event['thread_id'] or None,
            run_id=event['run_id'] or None,
            job_id=event['job_id'] or None,
            event_sequence=event['event_sequence'],
            event_type=event['event_type'],
            source=event['source'],
            target=event['target'],
            correlation_id=event['correlation_id'],
            causation_id=event['causation_id'] or None,
            command_id=event['command_id'] or None,
            aggregate_type=event['aggregate_type'],
            aggregate_id=event['aggregate_id'],
            aggregate_revision=event['aggregate_revision'],
            privacy_class=event['privacy_class'],
            payload_digest=event['payload_digest'],
            payload_json=_dumps(event['payload']),
            event_json=_dumps({k: v for k, v in event.items() if k != 'occurred_at'}),
            occurred_at=event['occurred_at'],
        )
        session.add(row)
        session.flush()
        accepted.append(event['event_id'])
        if event['run_id'] and event['run_id'] not in affected_runs:
            affected_runs.append(event['run_id'])
    projections = []
    for run_id in affected_runs:
        projection = rebuild_run_projection(session, run_id)
        if projection:
            projections.append(serialize_run_projection(projection))
    return {
        'kind': 'runtime_event_ingest_result_v1',
        'accepted': len(accepted),
        'duplicates': len(duplicates),
        'accepted_event_ids': accepted,
        'duplicate_event_ids': duplicates,
        'projections': projections,
    }


def list_runtime_events(
    session: Session,
    *,
    run_id: str = '',
    thread_id: str = '',
    after_event_id: str = '',
    limit: int = 200,
) -> list[RuntimeEvent]:
    stmt = select(RuntimeEvent)
    if run_id:
        stmt = stmt.where(RuntimeEvent.run_id == _clean(run_id, 160))
    if thread_id:
        stmt = stmt.where(RuntimeEvent.thread_id == _clean(thread_id, 160))

    cursor_id = _clean(after_event_id, 200)
    cursor = None
    if cursor_id:
        cursor = session.exec(select(RuntimeEvent).where(RuntimeEvent.event_id == cursor_id)).first()
    if cursor is not None:
        stmt = stmt.where(or_(
            RuntimeEvent.ingested_at > cursor.ingested_at,
            and_(RuntimeEvent.ingested_at == cursor.ingested_at, RuntimeEvent.id > cursor.id),
        ))
        stmt = stmt.order_by(RuntimeEvent.ingested_at.asc(), RuntimeEvent.id.asc())
    else:
        stmt = stmt.order_by(RuntimeEvent.ingested_at.desc(), RuntimeEvent.id.desc())

    stmt = stmt.limit(max(1, min(int(limit or 200), 1000)))
    return list(session.exec(stmt).all())
