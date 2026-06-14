from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import TaskAttempt, TaskAttemptEvent, Thread, utcnow

RUN_MODES = {'new', 'retry', 'branch', 'parallel_branch'}
STATUSES = {'draft', 'ready', 'launch_requested', 'running', 'completed', 'promoted', 'archived', 'superseded', 'failed'}
PREVIOUS_RESULT_POLICIES = {'include', 'exclude', 'summarize_only', 'optional'}
TARGET_TEAMS = {'coding', 'paper', 'presentation', 'review', 'general'}
WORK_MODES = {'quick_answer', 'assisted_task', 'team_review', 'project_task', 'research_campaign', 'customize'}
REVIEW_POLICIES = {'none', 'optional', 'required', 'stage_gate'}
MEMORY_PROFILES = {'coding', 'paper', 'presentation', 'review', 'general'}


def _jdump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def _jload(raw: str | None, default: Any) -> Any:
    try:
        parsed = json.loads(raw or '')
    except Exception:
        return default
    return parsed if parsed is not None else default


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, 'model_dump'):
        try:
            data = value.model_dump(exclude_none=True)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    if hasattr(value, 'dict'):
        try:
            data = value.dict(exclude_none=True)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_text(value: Any, max_len: int = 256) -> str:
    clean = str(value or '').strip()
    if not clean:
        return ''
    return clean[:max_len]


def _enum(value: Any, allowed: set[str], default: str) -> str:
    clean = _clean_text(value, 64).lower()
    return clean if clean in allowed else default


def _new_public_id(prefix: str) -> str:
    return f'{prefix}_{uuid4().hex[:16]}'


def _normalize_context_policy(value: Any, *, previous_result_policy: str, memory_projection_profile: str, include_memory_package: bool) -> dict[str, Any]:
    policy = _as_dict(value)
    normalized = {
        'include_original_user_request': policy.get('include_original_user_request') is not False,
        'include_user_feedback': bool(policy.get('include_user_feedback', True)),
        'include_previous_result': previous_result_policy == 'include' or policy.get('include_previous_result') is True,
        'include_previous_result_summary': previous_result_policy == 'summarize_only' or policy.get('include_previous_result_summary') is True,
        'include_full_chat_tail': bool(policy.get('include_full_chat_tail', False)),
        'include_memory_package': bool(include_memory_package or policy.get('include_memory_package', False)),
        'memory_package_mode': _clean_text(policy.get('memory_package_mode') or policy.get('memory_mode') or 'snapshot', 64) or 'snapshot',
        'memory_projection_profile': memory_projection_profile,
        'memory_scope': _clean_text(policy.get('memory_scope') or 'current_topic', 64) or 'current_topic',
    }
    for key, value in policy.items():
        if key not in normalized:
            normalized[key] = value
    if previous_result_policy == 'exclude':
        normalized['include_previous_result'] = False
        normalized['include_previous_result_summary'] = False
    return normalized


def _memory_projection_from_payload(payload: dict[str, Any]) -> str:
    memory = _as_dict(payload.get('memory_package') or payload.get('memory_import') or payload.get('memory'))
    return _enum(
        payload.get('memory_projection_profile')
        or memory.get('projection_profile')
        or memory.get('profile'),
        MEMORY_PROFILES,
        'general',
    )


def _work_mode_from_payload(payload: dict[str, Any]) -> tuple[str, str]:
    work_mode = _as_dict(payload.get('work_mode'))
    depth = _enum(payload.get('work_depth') or work_mode.get('work_depth') or work_mode.get('depth'), {'instant', 'team', 'loop'}, '')
    default_for_depth = {'instant': 'quick_answer', 'team': 'team_review', 'loop': 'project_task'}.get(depth, 'assisted_task')
    mode = _enum(payload.get('work_mode') or work_mode.get('work_mode') or work_mode.get('mode'), WORK_MODES, default_for_depth)
    review = _enum(payload.get('review_policy') or work_mode.get('review_policy'), REVIEW_POLICIES, 'optional')
    if mode == 'quick_answer':
        review = _enum(review, REVIEW_POLICIES, 'none')
    if mode == 'research_campaign' and review == 'optional':
        review = 'stage_gate'
    if depth == 'loop' and review == 'optional':
        review = 'required'
    return mode, review


def _merge_memory_package(existing: dict[str, Any], incoming: Any, projection_profile: str) -> dict[str, Any]:
    package = dict(existing or {})
    incoming_dict = _as_dict(incoming)
    if incoming_dict:
        package.update(incoming_dict)
    if projection_profile:
        package['projection_profile'] = projection_profile
    if package:
        package.setdefault('mode', 'snapshot')
        package.setdefault('permissions', {'read_only': True, 'allow_propose_update': True, 'direct_write': False})
    return package


def _actor_from_payload(payload: dict[str, Any], default: str = 'goc') -> str:
    return _clean_text(payload.get('actor') or payload.get('created_by') or default, 64) or default


def _event(session: Session, attempt: TaskAttempt, event_type: str, *, actor: str = 'goc', summary: str = '', payload: dict[str, Any] | None = None) -> TaskAttemptEvent:
    row = TaskAttemptEvent(
        thread_id=attempt.thread_id,
        task_id=attempt.task_id,
        attempt_id=attempt.attempt_id,
        event_type=event_type,
        actor=actor,
        summary=summary,
        event_json=_jdump(payload or {}),
    )
    session.add(row)
    return row


def serialize_task_attempt(row: TaskAttempt, *, include_events: bool = False, events: list[TaskAttemptEvent] | None = None) -> dict[str, Any]:
    value = {
        'id': row.id,
        'thread_id': row.thread_id,
        'task_id': row.task_id,
        'attempt_id': row.attempt_id,
        'parent_attempt_id': row.parent_attempt_id,
        'run_id': row.run_id,
        'run_mode': row.run_mode,
        'status': row.status,
        'target_team': row.target_team,
        'previous_result_policy': row.previous_result_policy,
        'work_mode': row.work_mode,
        'review_policy': row.review_policy,
        'memory_projection_profile': row.memory_projection_profile,
        'memory_package_id': row.memory_package_id,
        'task_text': row.task_text,
        'context_policy': _jload(row.context_policy_json, {}),
        'memory_package': _jload(row.memory_package_json, {}),
        'candidate_snapshot': _jload(row.candidate_snapshot_json, {}),
        'result': _jload(row.result_json, {}),
        'lineage': _jload(row.lineage_json, {}),
        'launch': _jload(row.launch_json, {}),
        'meta': _jload(row.meta_json, {}),
        'created_by': row.created_by,
        'promoted_at': row.promoted_at.isoformat() if row.promoted_at else None,
        'archived_at': row.archived_at.isoformat() if row.archived_at else None,
        'launched_at': row.launched_at.isoformat() if row.launched_at else None,
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
    }
    if include_events:
        value['events'] = [serialize_task_attempt_event(item) for item in events or []]
    return value


def serialize_task_attempt_event(row: TaskAttemptEvent) -> dict[str, Any]:
    return {
        'id': row.id,
        'thread_id': row.thread_id,
        'task_id': row.task_id,
        'attempt_id': row.attempt_id,
        'event_type': row.event_type,
        'actor': row.actor,
        'summary': row.summary,
        'event': _jload(row.event_json, {}),
        'created_at': row.created_at.isoformat() if row.created_at else None,
    }


def get_task_attempt(session: Session, attempt_id: str) -> TaskAttempt:
    clean = _clean_text(attempt_id, 128)
    if not clean:
        raise HTTPException(404, 'task attempt not found')
    row = session.exec(select(TaskAttempt).where(TaskAttempt.attempt_id == clean)).first()
    if not row:
        row = session.get(TaskAttempt, clean)
    if not row:
        raise HTTPException(404, 'task attempt not found')
    return row


def list_task_attempts(session: Session, *, thread_id: str, task_id: str | None = None, limit: int = 50) -> list[TaskAttempt]:
    stmt = select(TaskAttempt).where(TaskAttempt.thread_id == thread_id)
    clean_task_id = _clean_text(task_id, 128) if task_id else ''
    if clean_task_id:
        stmt = stmt.where(TaskAttempt.task_id == clean_task_id)
    stmt = stmt.order_by(TaskAttempt.created_at.desc()).limit(max(1, min(int(limit or 50), 200)))
    return list(session.exec(stmt).all())


def list_task_attempt_events(session: Session, *, thread_id: str, task_id: str | None = None, attempt_id: str | None = None, limit: int = 200) -> list[TaskAttemptEvent]:
    stmt = select(TaskAttemptEvent).where(TaskAttemptEvent.thread_id == thread_id)
    if task_id:
        stmt = stmt.where(TaskAttemptEvent.task_id == _clean_text(task_id, 128))
    if attempt_id:
        stmt = stmt.where(TaskAttemptEvent.attempt_id == _clean_text(attempt_id, 128))
    stmt = stmt.order_by(TaskAttemptEvent.created_at.asc()).limit(max(1, min(int(limit or 200), 1000)))
    return list(session.exec(stmt).all())


def create_task_attempt(session: Session, thread: Thread, body: Any) -> TaskAttempt:
    payload = _as_dict(body)
    run_mode = _enum(payload.get('run_mode'), RUN_MODES, 'new')
    previous_result_policy = _enum(payload.get('previous_result_policy'), PREVIOUS_RESULT_POLICIES, 'optional')
    if run_mode in {'retry', 'branch', 'parallel_branch'} and previous_result_policy == 'optional':
        previous_result_policy = 'exclude'
    target_team = _enum(payload.get('target_team'), TARGET_TEAMS, 'general')
    memory_projection_profile = _memory_projection_from_payload(payload)
    memory_incoming = _as_dict(payload.get('memory_package') or payload.get('memory_import') or payload.get('memory'))
    memory_package_id = _clean_text(payload.get('memory_package_id') or memory_incoming.get('package_id') or memory_incoming.get('id'), 128) or None
    work_mode, review_policy = _work_mode_from_payload(payload)
    task_id = _clean_text(payload.get('task_id'), 128) or _new_public_id('task')
    attempt_id = _clean_text(payload.get('attempt_id'), 128) or _new_public_id('attempt')
    existing = session.exec(
        select(TaskAttempt).where(TaskAttempt.thread_id == thread.id).where(TaskAttempt.attempt_id == attempt_id)
    ).first()
    if existing:
        raise HTTPException(409, 'task attempt already exists')
    memory_package = _merge_memory_package({}, memory_incoming, memory_projection_profile)
    context_policy = _normalize_context_policy(
        payload.get('context_policy'),
        previous_result_policy=previous_result_policy,
        memory_projection_profile=memory_projection_profile,
        include_memory_package=bool(memory_package),
    )
    lineage = {
        'parent_attempt_id': _clean_text(payload.get('parent_attempt_id'), 128) or None,
        'source_run_id': _clean_text(payload.get('source_run_id') or payload.get('run_id'), 128) or None,
        'recommendation_event_id': _clean_text(payload.get('recommendation_event_id'), 128) or None,
        'selected_blueprint_id': _clean_text(payload.get('selected_blueprint_id'), 128) or None,
    }
    extra_lineage = _as_dict(payload.get('lineage'))
    if extra_lineage:
        lineage.update(extra_lineage)
    row = TaskAttempt(
        thread_id=thread.id,
        task_id=task_id,
        attempt_id=attempt_id,
        parent_attempt_id=lineage.get('parent_attempt_id'),
        run_id=_clean_text(payload.get('run_id'), 128) or None,
        run_mode=run_mode,
        status=_enum(payload.get('status'), STATUSES, 'draft'),
        target_team=target_team,
        previous_result_policy=previous_result_policy,
        work_mode=work_mode,
        review_policy=review_policy,
        memory_projection_profile=memory_projection_profile,
        memory_package_id=memory_package_id,
        task_text=_clean_text(payload.get('task_text') or payload.get('objective'), 4000),
        context_policy_json=_jdump(context_policy),
        memory_package_json=_jdump(memory_package),
        candidate_snapshot_json=_jdump(payload.get('candidate_snapshot') or payload.get('candidate') or {}),
        result_json=_jdump(payload.get('result') or {}),
        lineage_json=_jdump(lineage),
        launch_json=_jdump(payload.get('launch') or {}),
        meta_json=_jdump(payload.get('meta') or {}),
        created_by=_actor_from_payload(payload),
    )
    session.add(row)
    _event(session, row, 'created', actor=row.created_by, summary=f'{run_mode} attempt created', payload=serialize_task_attempt(row))
    return row


def update_task_attempt(session: Session, row: TaskAttempt, body: Any) -> TaskAttempt:
    payload = _as_dict(body)
    if 'run_mode' in payload:
        row.run_mode = _enum(payload.get('run_mode'), RUN_MODES, row.run_mode)
    if 'status' in payload:
        row.status = _enum(payload.get('status'), STATUSES, row.status)
    if 'target_team' in payload:
        row.target_team = _enum(payload.get('target_team'), TARGET_TEAMS, row.target_team)
    if 'previous_result_policy' in payload:
        row.previous_result_policy = _enum(payload.get('previous_result_policy'), PREVIOUS_RESULT_POLICIES, row.previous_result_policy)
    if 'work_mode' in payload or isinstance(payload.get('work_mode'), dict) or 'review_policy' in payload:
        row.work_mode, row.review_policy = _work_mode_from_payload({**payload, 'work_mode': payload.get('work_mode', row.work_mode), 'review_policy': payload.get('review_policy', row.review_policy)})
    if 'memory_projection_profile' in payload:
        row.memory_projection_profile = _enum(payload.get('memory_projection_profile'), MEMORY_PROFILES, row.memory_projection_profile)
    if 'memory_package_id' in payload:
        row.memory_package_id = _clean_text(payload.get('memory_package_id'), 128) or None
    if 'task_text' in payload:
        row.task_text = _clean_text(payload.get('task_text'), 4000)
    if 'run_id' in payload:
        row.run_id = _clean_text(payload.get('run_id'), 128) or None
    if 'context_policy' in payload:
        row.context_policy_json = _jdump(_normalize_context_policy(
            payload.get('context_policy'),
            previous_result_policy=row.previous_result_policy,
            memory_projection_profile=row.memory_projection_profile,
            include_memory_package=bool(_jload(row.memory_package_json, {})),
        ))
    if 'candidate_snapshot' in payload or 'candidate' in payload:
        row.candidate_snapshot_json = _jdump(payload.get('candidate_snapshot') or payload.get('candidate') or {})
    if 'result' in payload:
        row.result_json = _jdump(payload.get('result') or {})
    if 'meta' in payload:
        meta = _jload(row.meta_json, {})
        meta.update(_as_dict(payload.get('meta')))
        row.meta_json = _jdump(meta)
    row.updated_at = utcnow()
    _event(session, row, 'updated', actor=_actor_from_payload(payload), summary='task attempt updated', payload=payload)
    return row


def attach_memory_package(session: Session, row: TaskAttempt, body: Any) -> TaskAttempt:
    payload = _as_dict(body)
    projection_profile = _enum(
        payload.get('memory_projection_profile') or payload.get('projection_profile') or row.memory_projection_profile,
        MEMORY_PROFILES,
        row.memory_projection_profile or 'general',
    )
    package_id = _clean_text(payload.get('memory_package_id') or payload.get('package_id'), 128) or row.memory_package_id
    incoming = payload.get('memory_package') or payload.get('package') or payload
    memory_package = _merge_memory_package(_jload(row.memory_package_json, {}), incoming, projection_profile)
    if package_id:
        memory_package['package_id'] = package_id
    row.memory_projection_profile = projection_profile
    row.memory_package_id = package_id
    row.memory_package_json = _jdump(memory_package)
    row.context_policy_json = _jdump(_normalize_context_policy(
        _jload(row.context_policy_json, {}),
        previous_result_policy=row.previous_result_policy,
        memory_projection_profile=projection_profile,
        include_memory_package=True,
    ))
    row.updated_at = utcnow()
    _event(session, row, 'memory_package_attached', actor=_actor_from_payload(payload), summary=f'memory profile {projection_profile} attached', payload=memory_package)
    return row


def build_launch_packet(row: TaskAttempt, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    overrides = overrides or {}
    return {
        'kind': 'task_attempt_launch_request_v1',
        'thread_id': row.thread_id,
        'task_id': row.task_id,
        'attempt_id': row.attempt_id,
        'parent_attempt_id': row.parent_attempt_id,
        'run_mode': row.run_mode,
        'target_team': row.target_team,
        'previous_result_policy': row.previous_result_policy,
        'work_mode': row.work_mode,
        'review_policy': row.review_policy,
        'memory_projection_profile': row.memory_projection_profile,
        'memory_package_id': row.memory_package_id,
        'task_text': row.task_text,
        'context_policy': _jload(row.context_policy_json, {}),
        'memory_package': _jload(row.memory_package_json, {}),
        'candidate_snapshot': _jload(row.candidate_snapshot_json, {}),
        'lineage': _jload(row.lineage_json, {}),
        'runtime_bridge': {
            'execute': False,
            'note': 'GoC records a bounded launch request; the ddalggak runtime bridge may consume this packet.',
        },
        'overrides': overrides,
    }


def launch_task_attempt(session: Session, row: TaskAttempt, body: Any) -> TaskAttempt:
    payload = _as_dict(body)
    overrides = _as_dict(payload.get('overrides'))
    packet = build_launch_packet(row, overrides)
    row.status = 'launch_requested'
    row.launched_at = utcnow()
    row.updated_at = row.launched_at
    row.launch_json = _jdump({
        'requested_at': row.launched_at.isoformat(),
        'actor': _actor_from_payload(payload),
        'packet': packet,
    })
    _event(session, row, 'launch_requested', actor=_actor_from_payload(payload), summary='launch requested from GoC', payload=packet)
    return row


def promote_task_attempt(session: Session, row: TaskAttempt, body: Any) -> TaskAttempt:
    payload = _as_dict(body)
    result = _as_dict(payload.get('result'))
    if result:
        existing_result = _jload(row.result_json, {})
        existing_result.update(result)
        row.result_json = _jdump(existing_result)
    row.status = 'promoted'
    row.promoted_at = utcnow()
    row.updated_at = row.promoted_at
    _event(session, row, 'promoted', actor=_actor_from_payload(payload), summary=_clean_text(payload.get('summary') or 'attempt promoted', 512), payload=payload)
    if payload.get('supersede_siblings') is True or payload.get('archive_siblings') is True:
        siblings = session.exec(
            select(TaskAttempt)
            .where(TaskAttempt.thread_id == row.thread_id)
            .where(TaskAttempt.task_id == row.task_id)
            .where(TaskAttempt.attempt_id != row.attempt_id)
            .where(TaskAttempt.status != 'archived')
            .where(TaskAttempt.status != 'promoted')
        ).all()
        for sibling in siblings:
            sibling.status = 'archived' if payload.get('archive_siblings') is True else 'superseded'
            sibling.updated_at = utcnow()
            if sibling.status == 'archived':
                sibling.archived_at = sibling.updated_at
            _event(session, sibling, sibling.status, actor=_actor_from_payload(payload), summary=f'sibling {sibling.status} by promotion of {row.attempt_id}', payload={'promoted_attempt_id': row.attempt_id})
    return row


def archive_task_attempt(session: Session, row: TaskAttempt, body: Any) -> TaskAttempt:
    payload = _as_dict(body)
    row.status = 'archived'
    row.archived_at = utcnow()
    row.updated_at = row.archived_at
    _event(session, row, 'archived', actor=_actor_from_payload(payload), summary=_clean_text(payload.get('reason') or 'attempt archived', 512), payload=payload)
    return row


def compare_task_attempts(session: Session, *, thread_id: str, task_id: str) -> dict[str, Any]:
    rows = list_task_attempts(session, thread_id=thread_id, task_id=task_id, limit=200)
    by_status: dict[str, int] = {}
    by_target_team: dict[str, int] = {}
    by_run_mode: dict[str, int] = {}
    promoted = None
    for row in rows:
        by_status[row.status] = by_status.get(row.status, 0) + 1
        by_target_team[row.target_team] = by_target_team.get(row.target_team, 0) + 1
        by_run_mode[row.run_mode] = by_run_mode.get(row.run_mode, 0) + 1
        if row.status == 'promoted' and promoted is None:
            promoted = row.attempt_id
    return {
        'kind': 'task_attempt_compare_v1',
        'thread_id': thread_id,
        'task_id': task_id,
        'count': len(rows),
        'promoted_attempt_id': promoted,
        'status_counts': by_status,
        'target_team_counts': by_target_team,
        'run_mode_counts': by_run_mode,
        'attempts': [serialize_task_attempt(row) for row in rows],
    }
