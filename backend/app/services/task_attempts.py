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
    raw_work_mode = payload.get('work_mode')
    work_mode = _as_dict(raw_work_mode)
    mode_source = raw_work_mode if isinstance(raw_work_mode, str) else None
    mode = _enum(mode_source or work_mode.get('work_mode') or work_mode.get('mode'), WORK_MODES, 'assisted_task')
    review = _enum(payload.get('review_policy') or work_mode.get('review_policy'), REVIEW_POLICIES, 'optional')
    if mode == 'quick_answer':
        review = _enum(review, REVIEW_POLICIES, 'none')
    if mode == 'research_campaign' and review == 'optional':
        review = 'stage_gate'
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
        'research': build_research_attempt_row(row, events=events or [] if include_events else None),
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



def _list_events_by_attempt(events: list[TaskAttemptEvent]) -> dict[str, list[TaskAttemptEvent]]:
    grouped: dict[str, list[TaskAttemptEvent]] = {}
    for event in events or []:
        grouped.setdefault(event.attempt_id, []).append(event)
    return grouped


def _status_decision(row: TaskAttempt) -> str:
    if row.status == 'promoted':
        return 'promote'
    if row.status in {'archived', 'superseded', 'failed'}:
        return 'reject'
    if row.run_mode in {'branch', 'parallel_branch'}:
        return 'branch_candidate'
    if row.run_mode == 'retry':
        return 'retry_candidate'
    return ''


def _latest_event_payload(events: list[TaskAttemptEvent], event_type: str) -> dict[str, Any]:
    for event in reversed(events or []):
        if event.event_type == event_type:
            return _jload(event.event_json, {})
    return {}


def _normalize_recipe_depth(row: TaskAttempt, recipe: dict[str, Any]) -> str:
    clean = _clean_text(recipe.get('depth') or recipe.get('work_depth') or recipe.get('mode'), 64).lower()
    if clean in {'ask', 'single', 'single_pass', 'quick_answer'}:
        return 'ask'
    if clean in {'team', 'team_review'}:
        return 'team'
    if clean in {'loop', 'bounded_loop', 'project_task', 'research_campaign', 'customize'}:
        return 'loop'
    if row.work_mode == 'quick_answer':
        return 'ask'
    if row.work_mode == 'team_review':
        return 'team'
    if row.work_mode in {'project_task', 'research_campaign', 'customize'}:
        return 'loop'
    if row.run_mode in {'retry', 'branch', 'parallel_branch'}:
        return 'loop'
    return 'team' if row.target_team != 'general' else 'ask'


def build_loop_recipe_snapshot(row: TaskAttempt) -> dict[str, Any]:
    candidate = _jload(row.candidate_snapshot_json, {})
    meta = _jload(row.meta_json, {})
    context_policy = _jload(row.context_policy_json, {})
    recipe = _as_dict(meta.get('loop_recipe') or candidate.get('loop_recipe') or candidate.get('recipe') or candidate.get('task_attempt_plan'))
    skills = recipe.get('skills') or candidate.get('skills') or candidate.get('skill_requirements') or []
    team_skeleton = (
        recipe.get('team_skeleton')
        or recipe.get('skeleton')
        or recipe.get('skeleton_motif')
        or candidate.get('skeleton_motif')
        or candidate.get('motif_id')
        or row.target_team
    )
    gates = recipe.get('gates') or recipe.get('approval_gates') or []
    if not gates and row.review_policy not in {'none', ''}:
        gates = [row.review_policy]
    return {
        'kind': 'loop_recipe_v1',
        'depth': _normalize_recipe_depth(row, recipe),
        'run_mode': row.run_mode,
        'work_mode': row.work_mode,
        'target_team': row.target_team,
        'team_skeleton': team_skeleton,
        'skills': _as_list(skills),
        'memory_policy': {
            'projection_profile': row.memory_projection_profile,
            'package_id': row.memory_package_id,
            'include_memory_package': bool(context_policy.get('include_memory_package')),
            'include_full_chat_tail': bool(context_policy.get('include_full_chat_tail')),
            'previous_result_policy': row.previous_result_policy,
        },
        'gates': _as_list(gates),
        'approval_policy': row.review_policy,
        'bounded_attempt_policy': _as_dict(meta.get('bounded_attempt_policy') or recipe.get('cycle_policy') or {}),
        'config_hash_inputs': {
            'attempt_id': row.attempt_id,
            'candidate_snapshot': candidate,
            'context_policy': context_policy,
        },
    }


def build_memory_treatment_snapshot(row: TaskAttempt) -> dict[str, Any]:
    meta = _jload(row.meta_json, {})
    package = _jload(row.memory_package_json, {})
    context_policy = _jload(row.context_policy_json, {})
    explicit = _as_dict(meta.get('memory_treatment'))
    treatment_type = _clean_text(explicit.get('type') or explicit.get('treatment_type'), 96).lower()
    if not treatment_type:
        if package.get('ablation_of') or package.get('minus_object_id'):
            treatment_type = 'ablation'
        elif package.get('stale') is True or package.get('conflicting') is True or package.get('risk') in {'stale', 'conflicting', 'poison'}:
            treatment_type = 'stale_conflicting'
        elif context_policy.get('include_full_chat_tail') is True:
            treatment_type = 'full_chat_tail'
        elif package or context_policy.get('include_memory_package') is True:
            treatment_type = 'role_specific_package'
        else:
            treatment_type = 'control_no_memory'
    included = package.get('memory_object_ids') or package.get('included_memory_object_ids') or package.get('object_ids') or []
    excluded = package.get('excluded_memory_object_ids') or package.get('blocked_memory_object_ids') or []
    return {
        'kind': 'memory_treatment_v1',
        'type': treatment_type,
        'package_id': row.memory_package_id or package.get('package_id') or package.get('id'),
        'projection_profile': row.memory_projection_profile,
        'included_memory_object_ids': _as_list(included),
        'excluded_memory_object_ids': _as_list(excluded),
        'ablation_of': package.get('ablation_of') or package.get('minus_object_id') or explicit.get('ablation_of'),
        'risk_labels': _as_list(package.get('risk_labels') or explicit.get('risk_labels')),
        'read_only': _as_dict(package.get('permissions')).get('direct_write') is not True,
    }


def build_context_boundary_snapshot(row: TaskAttempt) -> dict[str, Any]:
    meta = _jload(row.meta_json, {})
    context_policy = _jload(row.context_policy_json, {})
    boundary = _as_dict(meta.get('context_boundary') or meta.get('context_firewall') or {})
    return {
        'kind': 'context_boundary_v1',
        'mode': _clean_text(boundary.get('mode') or context_policy.get('visibility_mode') or 'role_filtered', 64) or 'role_filtered',
        'role_id': _clean_text(boundary.get('role_id') or context_policy.get('role_id'), 128) or None,
        'allowed_memory_object_ids': _as_list(boundary.get('allowed_memory_object_ids') or boundary.get('allowed') or []),
        'blocked_memory_object_ids': _as_list(boundary.get('blocked_memory_object_ids') or boundary.get('blocked') or []),
        'policy_reasons': _as_list(boundary.get('policy_reasons') or []),
        'privacy_filter': boundary.get('privacy_filter') is not False,
        'stale_filter': boundary.get('stale_filter') is not False,
        'sufficiency_check': boundary.get('sufficiency_check') is not False,
        'context_policy': context_policy,
    }


def build_outcome_snapshot(row: TaskAttempt) -> dict[str, Any]:
    result = _jload(row.result_json, {})
    evaluation = _as_dict(result.get('evaluation') or result.get('metrics') or result.get('outcome') or {})
    return {
        'kind': 'attempt_outcome_v1',
        'status': row.status,
        'success': evaluation.get('success', result.get('success')),
        'quality': evaluation.get('quality') or evaluation.get('quality_score'),
        'cost': evaluation.get('cost') or evaluation.get('cost_estimate'),
        'latency_ms': evaluation.get('latency_ms'),
        'token_cost': evaluation.get('token_cost') or evaluation.get('total_tokens'),
        'contradiction': bool(evaluation.get('contradiction', False)),
        'stale_context_failure': bool(evaluation.get('stale_context_failure', False)),
        'context_pollution': bool(evaluation.get('context_pollution', False)),
        'leakage_detected': bool(evaluation.get('leakage_detected', False)),
        'policy_violation': bool(evaluation.get('policy_violation', False)),
        'role_sufficiency': evaluation.get('role_sufficiency'),
        'raw': evaluation,
    }


def build_research_attempt_row(row: TaskAttempt, *, events: list[TaskAttemptEvent] | None = None) -> dict[str, Any]:
    event_list = events or []
    latest_decision = _latest_event_payload(event_list, 'user_decision_recorded')
    return {
        'kind': 'research_attempt_row_v1',
        'task_id': row.task_id,
        'attempt_id': row.attempt_id,
        'parent_attempt_id': row.parent_attempt_id,
        'run_id': row.run_id,
        'loop_recipe': build_loop_recipe_snapshot(row),
        'memory_treatment': build_memory_treatment_snapshot(row),
        'context_boundary': build_context_boundary_snapshot(row),
        'outcome': build_outcome_snapshot(row),
        'user_decision': latest_decision or ({'decision': _status_decision(row)} if _status_decision(row) else {}),
    }


def record_task_attempt_decision(session: Session, row: TaskAttempt, body: Any) -> TaskAttempt:
    payload = _as_dict(body)
    decision = _enum(payload.get('decision'), {'promote', 'reject', 'retry', 'branch', 'edit_memory', 'approve_checkpoint', 'exclude_previous_result', 'neutral', 'prefer'}, 'neutral')
    record = {
        'kind': 'user_decision_v1',
        'decision': decision,
        'preferred_attempt_id': _clean_text(payload.get('preferred_attempt_id') or (row.attempt_id if decision == 'promote' else ''), 128) or None,
        'rejected_attempt_id': _clean_text(payload.get('rejected_attempt_id') or (row.attempt_id if decision == 'reject' else ''), 128) or None,
        'compared_attempt_ids': _as_list(payload.get('compared_attempt_ids')),
        'reason_tags': _as_list(payload.get('reason_tags')),
        'ratings': _as_dict(payload.get('ratings')),
        'payload': _as_dict(payload.get('payload')),
    }
    summary = _clean_text(payload.get('summary') or f'user decision: {decision}', 512)
    if decision == 'promote':
        row.status = 'promoted'
        row.promoted_at = utcnow()
    elif decision == 'reject':
        row.status = 'archived'
        row.archived_at = utcnow()
    elif decision == 'exclude_previous_result':
        row.previous_result_policy = 'exclude'
        row.context_policy_json = _jdump(_normalize_context_policy(
            _jload(row.context_policy_json, {}),
            previous_result_policy=row.previous_result_policy,
            memory_projection_profile=row.memory_projection_profile,
            include_memory_package=bool(_jload(row.memory_package_json, {})),
        ))
    row.updated_at = utcnow()
    _event(session, row, 'user_decision_recorded', actor=_actor_from_payload(payload), summary=summary, payload=record)
    return row


def record_task_attempt_evaluation(session: Session, row: TaskAttempt, body: Any) -> TaskAttempt:
    payload = _as_dict(body)
    metrics = _as_dict(payload.get('metrics'))
    for key in ['quality', 'success', 'cost', 'latency_ms', 'token_cost', 'contradiction', 'stale_context_failure', 'context_pollution', 'leakage_detected', 'policy_violation', 'role_sufficiency', 'notes', 'evaluator']:
        if key in payload and payload.get(key) is not None:
            metrics[key] = payload.get(key)
    result = _jload(row.result_json, {})
    existing_eval = _as_dict(result.get('evaluation'))
    existing_eval.update(metrics)
    result['evaluation'] = existing_eval
    row.result_json = _jdump(result)
    row.updated_at = utcnow()
    _event(session, row, 'evaluation_recorded', actor=_actor_from_payload(payload), summary=_clean_text(payload.get('notes') or 'evaluation recorded', 512), payload={'kind': 'evaluation_v1', 'metrics': existing_eval})
    return row


def _variant_attempt_payload(row: TaskAttempt, *, variant_id: str, axis: str, label: str, overrides: dict[str, Any]) -> dict[str, Any]:
    base_meta = _jload(row.meta_json, {})
    meta = dict(base_meta)
    meta.setdefault('research_axis', {})
    meta['research_axis'] = {**_as_dict(meta.get('research_axis')), 'axis': axis, 'label': label, 'base_attempt_id': row.attempt_id}
    meta.update(_as_dict(overrides.pop('meta', {})))
    return {
        'thread_id': row.thread_id,
        'task_id': row.task_id,
        'parent_attempt_id': row.attempt_id,
        'attempt_id': f'{row.attempt_id}_{variant_id}',
        'run_mode': 'parallel_branch',
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
        'lineage': {**_jload(row.lineage_json, {}), 'base_attempt_id': row.attempt_id, 'variant_axis': axis, 'variant_label': label},
        'meta': meta,
        'created_by': 'goc-research-variant',
        **overrides,
    }


def _research_variants_for_attempt(row: TaskAttempt, axes: set[str]) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []
    if 'recipe' in axes:
        variants.extend([
            _variant_attempt_payload(row, variant_id='recipe_single', axis='recipe', label='single_pass', overrides={'work_mode': 'quick_answer', 'review_policy': 'none', 'target_team': 'general', 'meta': {'loop_recipe': {'depth': 'ask', 'team_skeleton': 'single_agent', 'gates': []}}}),
            _variant_attempt_payload(row, variant_id='recipe_team', axis='recipe', label='team_review', overrides={'work_mode': 'team_review', 'review_policy': 'optional', 'meta': {'loop_recipe': {'depth': 'team', 'team_skeleton': 'planner_producer_reviewer', 'gates': ['optional_review']}}}),
            _variant_attempt_payload(row, variant_id='recipe_loop', axis='recipe', label='bounded_loop', overrides={'work_mode': 'project_task', 'review_policy': 'stage_gate', 'meta': {'loop_recipe': {'depth': 'loop', 'team_skeleton': 'curator_producer_reviewer', 'gates': ['checkpoint']}}}),
        ])
    if 'memory' in axes:
        variants.extend([
            _variant_attempt_payload(row, variant_id='mem_control', axis='memory', label='control_no_memory', overrides={'memory_package_id': None, 'memory_package': {}, 'context_policy': {**_jload(row.context_policy_json, {}), 'include_memory_package': False, 'include_full_chat_tail': False}, 'meta': {'memory_treatment': {'type': 'control_no_memory'}}}),
            _variant_attempt_payload(row, variant_id='mem_full_tail', axis='memory', label='full_chat_tail', overrides={'context_policy': {**_jload(row.context_policy_json, {}), 'include_full_chat_tail': True, 'include_memory_package': False}, 'meta': {'memory_treatment': {'type': 'full_chat_tail'}}}),
            _variant_attempt_payload(row, variant_id='mem_role', axis='memory', label='role_specific_package', overrides={'context_policy': {**_jload(row.context_policy_json, {}), 'include_memory_package': True, 'include_full_chat_tail': False}, 'meta': {'memory_treatment': {'type': 'role_specific_package'}}}),
            _variant_attempt_payload(row, variant_id='mem_ablation', axis='memory', label='ablation_minus_one_object', overrides={'context_policy': {**_jload(row.context_policy_json, {}), 'include_memory_package': True}, 'memory_package': {**_jload(row.memory_package_json, {}), 'ablation_of': 'one_memory_object'}, 'meta': {'memory_treatment': {'type': 'ablation'}}}),
            _variant_attempt_payload(row, variant_id='mem_poison', axis='memory', label='stale_conflicting_package', overrides={'context_policy': {**_jload(row.context_policy_json, {}), 'include_memory_package': True}, 'memory_package': {**_jload(row.memory_package_json, {}), 'stale': True, 'conflicting': True, 'risk_labels': ['stale', 'conflicting']}, 'meta': {'memory_treatment': {'type': 'stale_conflicting'}}}),
        ])
    if 'context' in axes:
        variants.extend([
            _variant_attempt_payload(row, variant_id='ctx_full', axis='context', label='full_shared_memory', overrides={'context_policy': {**_jload(row.context_policy_json, {}), 'visibility_mode': 'full_shared'}, 'meta': {'context_boundary': {'mode': 'full_shared'}}}),
            _variant_attempt_payload(row, variant_id='ctx_role', axis='context', label='role_filtered', overrides={'context_policy': {**_jload(row.context_policy_json, {}), 'visibility_mode': 'role_filtered'}, 'meta': {'context_boundary': {'mode': 'role_filtered', 'privacy_filter': True, 'sufficiency_check': True}}}),
            _variant_attempt_payload(row, variant_id='ctx_least', axis='context', label='least_privilege', overrides={'context_policy': {**_jload(row.context_policy_json, {}), 'visibility_mode': 'least_privilege'}, 'meta': {'context_boundary': {'mode': 'least_privilege', 'privacy_filter': True, 'stale_filter': True, 'sufficiency_check': True}}}),
        ])
    return variants


def generate_task_attempt_variants(session: Session, row: TaskAttempt, body: Any) -> dict[str, Any]:
    payload = _as_dict(body)
    axes_raw = {str(x).strip().lower() for x in _as_list(payload.get('axes')) if str(x).strip()}
    axes = axes_raw or set()
    if not axes:
        if payload.get('include_recipe_variants') is not False:
            axes.add('recipe')
        if payload.get('include_memory_treatments') is not False:
            axes.add('memory')
        if payload.get('include_context_boundaries') is not False:
            axes.add('context')
    axes = axes.intersection({'recipe', 'memory', 'context'}) or {'recipe', 'memory', 'context'}
    max_variants = max(1, min(int(payload.get('max_variants') or 12), 24))
    variants = _research_variants_for_attempt(row, axes)[:max_variants]
    created: list[TaskAttempt] = []
    if payload.get('create') is not False:
        thread = session.get(Thread, row.thread_id)
        if not thread:
            raise HTTPException(404, 'thread not found')
        for variant_payload in variants:
            existing = session.exec(select(TaskAttempt).where(TaskAttempt.thread_id == row.thread_id).where(TaskAttempt.attempt_id == variant_payload['attempt_id'])).first()
            if existing:
                created.append(existing)
                continue
            created.append(create_task_attempt(session, thread, variant_payload))
    _event(session, row, 'research_variants_generated', actor=_actor_from_payload(payload), summary=f'{len(variants)} research variants generated', payload={'axes': sorted(axes), 'variant_attempt_ids': [v.get('attempt_id') for v in variants]})
    return {
        'kind': 'task_attempt_variant_generation_v1',
        'base_attempt_id': row.attempt_id,
        'axes': sorted(axes),
        'count': len(variants),
        'variants': variants,
        'created_attempts': [serialize_task_attempt(item) for item in created],
    }


def _build_preference_rows(rows: list[TaskAttempt], events_by_attempt: dict[str, list[TaskAttemptEvent]]) -> list[dict[str, Any]]:
    preferences: list[dict[str, Any]] = []
    by_task: dict[str, list[TaskAttempt]] = {}
    for row in rows:
        by_task.setdefault(row.task_id, []).append(row)
    for task_id, task_rows in by_task.items():
        promoted = [row for row in task_rows if row.status == 'promoted']
        for winner in promoted:
            for loser in task_rows:
                if loser.attempt_id == winner.attempt_id:
                    continue
                preferences.append({
                    'kind': 'recipe_preference_row_v1',
                    'task_id': task_id,
                    'winner_attempt_id': winner.attempt_id,
                    'loser_attempt_id': loser.attempt_id,
                    'label_source': 'promoted_status',
                    'winner_recipe': build_loop_recipe_snapshot(winner),
                    'loser_recipe': build_loop_recipe_snapshot(loser),
                })
        for row in task_rows:
            for event in events_by_attempt.get(row.attempt_id, []):
                if event.event_type != 'user_decision_recorded':
                    continue
                payload = _jload(event.event_json, {})
                winner = payload.get('preferred_attempt_id')
                loser = payload.get('rejected_attempt_id')
                if winner and loser and winner != loser:
                    preferences.append({
                        'kind': 'recipe_preference_row_v1',
                        'task_id': task_id,
                        'winner_attempt_id': winner,
                        'loser_attempt_id': loser,
                        'label_source': 'user_decision_event',
                        'reason_tags': payload.get('reason_tags') or [],
                    })
            if row.parent_attempt_id and row.run_mode in {'branch', 'retry', 'parallel_branch'} and row.status in {'promoted', 'completed'}:
                preferences.append({
                    'kind': 'recipe_preference_row_v1',
                    'task_id': task_id,
                    'winner_attempt_id': row.attempt_id,
                    'loser_attempt_id': row.parent_attempt_id,
                    'label_source': f'{row.run_mode}_outcome',
                    'winner_recipe': build_loop_recipe_snapshot(row),
                })
    return preferences


def export_research_dataset(session: Session, *, thread_id: str, task_id: str | None = None, include_events: bool = True) -> dict[str, Any]:
    rows = list_task_attempts(session, thread_id=thread_id, task_id=task_id, limit=200)
    events = list_task_attempt_events(session, thread_id=thread_id, task_id=task_id, limit=1000) if include_events else []
    events_by_attempt = _list_events_by_attempt(events)
    attempt_rows = [build_research_attempt_row(row, events=events_by_attempt.get(row.attempt_id, [])) for row in rows]
    preferences = _build_preference_rows(rows, events_by_attempt)
    memory_trials = []
    context_rows = []
    for row in rows:
        attempt = build_research_attempt_row(row, events=events_by_attempt.get(row.attempt_id, []))
        if attempt['memory_treatment'].get('type'):
            memory_trials.append({
                'kind': 'memory_trial_row_v1',
                'task_id': row.task_id,
                'attempt_id': row.attempt_id,
                'role_id': attempt['context_boundary'].get('role_id'),
                'memory_treatment': attempt['memory_treatment'],
                'outcome': attempt['outcome'],
            })
        context_rows.append({
            'kind': 'context_firewall_row_v1',
            'task_id': row.task_id,
            'attempt_id': row.attempt_id,
            'context_boundary': attempt['context_boundary'],
            'outcome': attempt['outcome'],
        })
    return {
        'kind': 'loop_research_dataset_v1',
        'thread_id': thread_id,
        'task_id': task_id,
        'counts': {
            'attempts': len(attempt_rows),
            'recipe_preferences': len(preferences),
            'memory_trials': len(memory_trials),
            'context_firewall_rows': len(context_rows),
            'events': len(events),
        },
        'attempts': attempt_rows,
        'recipe_preferences': preferences,
        'memory_trials': memory_trials,
        'context_firewall_rows': context_rows,
        'events': [serialize_task_attempt_event(event) for event in events] if include_events else [],
    }

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
    events = list_task_attempt_events(session, thread_id=thread_id, task_id=task_id, limit=1000)
    events_by_attempt = _list_events_by_attempt(events)
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
        'recipe_preferences': _build_preference_rows(rows, events_by_attempt),
        'research_attempts': [build_research_attempt_row(row, events=events_by_attempt.get(row.attempt_id, [])) for row in rows],
    }
