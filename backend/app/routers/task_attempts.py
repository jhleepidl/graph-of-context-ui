from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from sqlmodel import Session

from app.db import engine
from app.schemas import (
    TaskAttemptArchiveRequest,
    TaskAttemptCreateRequest,
    TaskAttemptDecisionRequest,
    TaskAttemptEvaluationRequest,
    TaskAttemptLaunchRequest,
    TaskAttemptMemoryPackageRequest,
    TaskAttemptPromoteRequest,
    TaskAttemptUpdateRequest,
    TaskAttemptVariantRequest,
)
from app.services.task_attempts import (
    archive_task_attempt,
    attach_memory_package,
    compare_task_attempts,
    create_task_attempt,
    export_research_dataset,
    generate_task_attempt_variants,
    get_task_attempt,
    launch_task_attempt,
    list_task_attempt_events,
    list_task_attempts,
    promote_task_attempt,
    record_task_attempt_decision,
    record_task_attempt_evaluation,
    serialize_task_attempt,
    serialize_task_attempt_event,
    update_task_attempt,
)
from app.tenant import require_thread_access, require_thread_write_access

router = APIRouter(prefix='/api', tags=['task_attempts'])


def _ensure_attempt_read_access(session: Session, attempt_id: str):
    row = get_task_attempt(session, attempt_id)
    require_thread_access(session, row.thread_id)
    return row


def _ensure_attempt_write_access(session: Session, attempt_id: str):
    row = get_task_attempt(session, attempt_id)
    require_thread_write_access(session, row.thread_id)
    return row


@router.post('/task-attempts')
def create_attempt(body: TaskAttemptCreateRequest):
    with Session(engine) as session:
        thread = require_thread_write_access(session, body.thread_id)
        row = create_task_attempt(session, thread, body)
        session.commit()
        session.refresh(row)
        events = list_task_attempt_events(session, thread_id=row.thread_id, attempt_id=row.attempt_id)
        return {'ok': True, 'attempt': serialize_task_attempt(row, include_events=True, events=events)}


@router.get('/threads/{thread_id}/task-attempts')
def list_attempts(thread_id: str, task_id: str | None = None, limit: int = 50):
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        rows = list_task_attempts(session, thread_id=thread.id, task_id=task_id, limit=limit)
        return {
            'ok': True,
            'thread_id': thread.id,
            'task_id': task_id,
            'count': len(rows),
            'items': [serialize_task_attempt(row) for row in rows],
        }


@router.get('/threads/{thread_id}/task-attempts/compare')
def compare_attempts(thread_id: str, task_id: str):
    clean_task_id = str(task_id or '').strip()
    if not clean_task_id:
        raise HTTPException(400, 'task_id is required')
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        return compare_task_attempts(session, thread_id=thread.id, task_id=clean_task_id)



@router.get('/threads/{thread_id}/task-attempts/research-dataset')
def export_attempt_research_dataset(thread_id: str, task_id: str | None = None, include_events: bool = True, format: str | None = None):
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        dataset = export_research_dataset(session, thread_id=thread.id, task_id=task_id, include_events=include_events)
        if str(format or '').strip().lower() == 'jsonl':
            import json
            lines = []
            for section in ['attempts', 'recipe_preferences', 'memory_trials', 'context_firewall_rows', 'events']:
                for row in dataset.get(section, []):
                    lines.append(json.dumps({'section': section, **row}, ensure_ascii=False, sort_keys=True))
            return Response('\n'.join(lines) + ('\n' if lines else ''), media_type='application/x-ndjson')
        return {'ok': True, 'dataset': dataset}


@router.get('/task-attempts/{attempt_id}')
def read_attempt(attempt_id: str):
    with Session(engine) as session:
        row = _ensure_attempt_read_access(session, attempt_id)
        events = list_task_attempt_events(session, thread_id=row.thread_id, attempt_id=row.attempt_id)
        return {'ok': True, 'attempt': serialize_task_attempt(row, include_events=True, events=events)}


@router.patch('/task-attempts/{attempt_id}')
def update_attempt(attempt_id: str, body: TaskAttemptUpdateRequest):
    with Session(engine) as session:
        row = _ensure_attempt_write_access(session, attempt_id)
        row = update_task_attempt(session, row, body)
        session.add(row)
        session.commit()
        session.refresh(row)
        return {'ok': True, 'attempt': serialize_task_attempt(row)}


@router.post('/task-attempts/{attempt_id}/memory-package')
def attach_attempt_memory_package(attempt_id: str, body: TaskAttemptMemoryPackageRequest):
    with Session(engine) as session:
        row = _ensure_attempt_write_access(session, attempt_id)
        row = attach_memory_package(session, row, body)
        session.add(row)
        session.commit()
        session.refresh(row)
        return {'ok': True, 'attempt': serialize_task_attempt(row)}



@router.post('/task-attempts/{attempt_id}/decision')
def record_attempt_decision(attempt_id: str, body: TaskAttemptDecisionRequest):
    with Session(engine) as session:
        row = _ensure_attempt_write_access(session, attempt_id)
        row = record_task_attempt_decision(session, row, body)
        session.add(row)
        session.commit()
        session.refresh(row)
        events = list_task_attempt_events(session, thread_id=row.thread_id, attempt_id=row.attempt_id)
        return {'ok': True, 'attempt': serialize_task_attempt(row, include_events=True, events=events), 'compare': compare_task_attempts(session, thread_id=row.thread_id, task_id=row.task_id)}


@router.post('/task-attempts/{attempt_id}/evaluation')
def record_attempt_evaluation(attempt_id: str, body: TaskAttemptEvaluationRequest):
    with Session(engine) as session:
        row = _ensure_attempt_write_access(session, attempt_id)
        row = record_task_attempt_evaluation(session, row, body)
        session.add(row)
        session.commit()
        session.refresh(row)
        events = list_task_attempt_events(session, thread_id=row.thread_id, attempt_id=row.attempt_id)
        return {'ok': True, 'attempt': serialize_task_attempt(row, include_events=True, events=events)}


@router.post('/task-attempts/{attempt_id}/variants')
def generate_attempt_variants(attempt_id: str, body: TaskAttemptVariantRequest | None = None):
    with Session(engine) as session:
        row = _ensure_attempt_write_access(session, attempt_id)
        result = generate_task_attempt_variants(session, row, body or TaskAttemptVariantRequest())
        session.commit()
        return {'ok': True, 'result': result, 'compare': compare_task_attempts(session, thread_id=row.thread_id, task_id=row.task_id)}


@router.post('/task-attempts/{attempt_id}/launch')
def launch_attempt(attempt_id: str, body: TaskAttemptLaunchRequest | None = None):
    with Session(engine) as session:
        row = _ensure_attempt_write_access(session, attempt_id)
        row = launch_task_attempt(session, row, body or TaskAttemptLaunchRequest())
        session.add(row)
        session.commit()
        session.refresh(row)
        return {'ok': True, 'attempt': serialize_task_attempt(row), 'launch_packet': serialize_task_attempt(row).get('launch', {}).get('packet')}


@router.post('/task-attempts/{attempt_id}/promote')
def promote_attempt(attempt_id: str, body: TaskAttemptPromoteRequest | None = None):
    with Session(engine) as session:
        row = _ensure_attempt_write_access(session, attempt_id)
        row = promote_task_attempt(session, row, body or TaskAttemptPromoteRequest())
        session.add(row)
        session.commit()
        session.refresh(row)
        return {'ok': True, 'attempt': serialize_task_attempt(row), 'compare': compare_task_attempts(session, thread_id=row.thread_id, task_id=row.task_id)}


@router.post('/task-attempts/{attempt_id}/archive')
def archive_attempt(attempt_id: str, body: TaskAttemptArchiveRequest | None = None):
    with Session(engine) as session:
        row = _ensure_attempt_write_access(session, attempt_id)
        row = archive_task_attempt(session, row, body or TaskAttemptArchiveRequest())
        session.add(row)
        session.commit()
        session.refresh(row)
        return {'ok': True, 'attempt': serialize_task_attempt(row)}


@router.get('/task-attempts/{attempt_id}/events')
def read_attempt_events(attempt_id: str):
    with Session(engine) as session:
        row = _ensure_attempt_read_access(session, attempt_id)
        events = list_task_attempt_events(session, thread_id=row.thread_id, attempt_id=row.attempt_id)
        return {'ok': True, 'attempt_id': row.attempt_id, 'count': len(events), 'items': [serialize_task_attempt_event(item) for item in events]}
