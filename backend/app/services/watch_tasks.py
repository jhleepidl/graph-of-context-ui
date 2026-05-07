from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models import Thread, WatchTask, WatchIteration, new_id, utcnow


def _jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or '')
    except Exception:
        return default


def _jdump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _clean(value: Any, max_len: int = 1000) -> str:
    text = str(value or '').strip()
    return text[:max_len]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    raw = str(value or '').strip()
    if raw:
        try:
            return datetime.fromisoformat(raw.replace('Z', '+00:00'))
        except Exception:
            pass
    return utcnow()


def _task_to_dict(task: WatchTask | None, iterations: list[WatchIteration] | None = None) -> dict[str, Any] | None:
    if not task:
        return None
    rows = iterations or []
    return {
        'id': task.id,
        'thread_id': task.thread_id,
        'run_id': task.run_id,
        'contract_id': task.contract_id,
        'workflow_kind': task.workflow_kind,
        'status': task.status,
        'goal': task.goal,
        'current_iteration': task.current_iteration,
        'min_iterations': task.min_iterations,
        'max_iterations': task.max_iterations,
        'required_passes': _jload(task.required_passes_json, []),
        'approval_boundary': task.approval_boundary,
        'stop_conditions': _jload(task.stop_conditions_json, []),
        'contract': _jload(task.contract_json, {}),
        'created_at': task.created_at.isoformat(),
        'updated_at': task.updated_at.isoformat(),
        'iterations': [_iteration_to_dict(row) for row in rows],
    }


def _iteration_to_dict(row: WatchIteration) -> dict[str, Any]:
    return {
        'id': row.id,
        'thread_id': row.thread_id,
        'task_id': row.task_id,
        'run_id': row.run_id,
        'iteration': row.iteration,
        'status': row.status,
        'event': row.event,
        'summary': row.summary,
        'stop_reason': row.stop_reason,
        'payload': _jload(row.payload_json, {}),
        'created_at': row.created_at.isoformat(),
        'updated_at': row.updated_at.isoformat(),
    }


def list_thread_watch_tasks(session: Session, thread: Thread, limit: int = 20) -> dict[str, Any]:
    tasks = list(session.exec(
        select(WatchTask)
        .where(WatchTask.thread_id == thread.id)
        .order_by(WatchTask.updated_at.desc())
        .limit(max(1, min(int(limit or 20), 100)))
    ))
    if not tasks:
        return {'ok': True, 'thread_id': thread.id, 'tasks': [], 'active_task': None}
    task_ids = [row.id for row in tasks]
    iterations = list(session.exec(
        select(WatchIteration)
        .where(WatchIteration.task_id.in_(task_ids))
        .order_by(WatchIteration.created_at.asc())
    ))
    by_task: dict[str, list[WatchIteration]] = {}
    for row in iterations:
        by_task.setdefault(row.task_id, []).append(row)
    active = next((row for row in tasks if row.status in {'active', 'running', 'next_iteration_ready', 'paused', 'awaiting_approval'}), tasks[0])
    return {
        'ok': True,
        'thread_id': thread.id,
        'tasks': [_task_to_dict(row, by_task.get(row.id, [])) for row in tasks],
        'active_task': _task_to_dict(active, by_task.get(active.id, [])),
    }


def upsert_thread_watch_task(session: Session, thread: Thread, payload: dict[str, Any], source: str = 'ddalggak') -> dict[str, Any]:
    body = _as_dict(payload)
    contract = _as_dict(body.get('contract') or body.get('watch_task_contract') or body)
    contract_id = _clean(contract.get('contract_id') or body.get('contract_id') or f'watch_{thread.id}', 160)
    run_id = _clean(body.get('run_id') or body.get('runId') or contract.get('job_id') or contract.get('run_id'), 160)
    existing = session.exec(
        select(WatchTask).where(WatchTask.thread_id == thread.id, WatchTask.contract_id == contract_id)
    ).first()
    task = existing or WatchTask(thread_id=thread.id, contract_id=contract_id)
    task.run_id = run_id or task.run_id
    task.workflow_kind = _clean(contract.get('workflow_kind') or contract.get('workflowKind') or 'bounded_continuous_loop', 120)
    task.status = _clean(contract.get('status') or body.get('status') or task.status or 'active', 80)
    task.goal = _clean(contract.get('goal') or body.get('goal') or task.goal, 2000)
    task.current_iteration = int(contract.get('current_iteration') or body.get('current_iteration') or task.current_iteration or 0)
    task.min_iterations = int(contract.get('min_iterations') or body.get('min_iterations') or task.min_iterations or 1)
    task.max_iterations = int(contract.get('max_iterations') or body.get('max_iterations') or task.max_iterations or 1)
    task.required_passes_json = _jdump(_as_list(contract.get('required_passes') or body.get('required_passes')))
    task.approval_boundary = bool(contract.get('approval_boundary') or body.get('approval_boundary'))
    task.stop_conditions_json = _jdump(_as_list(contract.get('stop_conditions') or body.get('stop_conditions')))
    task.contract_json = _jdump({'source': source, **contract})
    task.updated_at = utcnow()
    session.add(task)
    session.commit()
    session.refresh(task)
    for raw in _as_list(body.get('iterations')):
        upsert_watch_iteration(session, thread, task, _as_dict(raw), commit=False)
    session.commit()
    return {'ok': True, 'task': _task_to_dict(task, list(session.exec(select(WatchIteration).where(WatchIteration.task_id == task.id).order_by(WatchIteration.created_at.asc()))))}


def upsert_watch_iteration(session: Session, thread: Thread, task: WatchTask, payload: dict[str, Any], commit: bool = True) -> WatchIteration:
    iteration_no = int(payload.get('iteration') or payload.get('iteration_number') or 0)
    event = _clean(payload.get('event') or 'watch_iteration_event', 120)
    created_at = _parse_dt(payload.get('ts') or payload.get('created_at'))
    existing = None
    if iteration_no > 0 and event:
        existing = session.exec(
            select(WatchIteration).where(
                WatchIteration.thread_id == thread.id,
                WatchIteration.task_id == task.id,
                WatchIteration.iteration == iteration_no,
                WatchIteration.event == event,
            )
        ).first()
    row = existing or WatchIteration(thread_id=thread.id, task_id=task.id)
    row.run_id = task.run_id
    row.iteration = iteration_no
    row.event = event
    row.status = _clean(payload.get('status') or row.status or 'recorded', 80)
    row.summary = _clean(payload.get('summary') or payload.get('route_reason') or '', 1000)
    row.stop_reason = _clean(payload.get('stop_reason') or '', 160)
    row.payload_json = _jdump(payload)
    row.created_at = existing.created_at if existing else created_at
    row.updated_at = utcnow()
    session.add(row)
    if commit:
        session.commit()
        session.refresh(row)
    return row


def apply_watch_task_action(session: Session, thread: Thread, task_id: str, action: str, reason: str = '', actor: str = 'goc') -> dict[str, Any]:
    task = session.get(WatchTask, task_id)
    if not task or task.thread_id != thread.id:
        raise ValueError('watch task not found')
    clean_action = _clean(action, 80).lower()
    mapping = {
        'pause': 'paused',
        'resume': 'active',
        'stop': 'stopped',
        'complete': 'completed',
    }
    if clean_action not in mapping:
        raise ValueError('invalid watch task action')
    task.status = mapping[clean_action]
    task.updated_at = utcnow()
    session.add(task)
    event = WatchIteration(
        thread_id=thread.id,
        task_id=task.id,
        run_id=task.run_id,
        iteration=task.current_iteration,
        event=f'watch_{task.status}',
        status=task.status,
        summary=_clean(reason, 1000),
        payload_json=_jdump({'action': clean_action, 'reason': reason, 'actor': actor}),
    )
    session.add(event)
    session.commit()
    session.refresh(task)
    return {'ok': True, 'task': _task_to_dict(task, list(session.exec(select(WatchIteration).where(WatchIteration.task_id == task.id).order_by(WatchIteration.created_at.asc()))))}
