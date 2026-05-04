from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models import MemoryProjection, MemorySurface, MemoryTopologyEvent, MemoryTopologySnapshot, TeamSelectionEvent, Thread, utcnow

VALID_MEMORY_MODES = {'ephemeral', 'compact_single', 'structured_single', 'team_scoped', 'graph_snapshot'}


def _clean_text(value: Any, *, max_len: int = 240) -> str:
    out = str(value or '').strip()
    if len(out) > max_len:
        return out[: max_len - 1] + '…'
    return out


def _clean_id(value: Any, *, max_len: int = 128) -> str:
    out = _clean_text(value, max_len=max_len).lower().replace(' ', '_')
    return ''.join(ch for ch in out if ch.isalnum() or ch in {'_', '-', '.', ':'}).strip('_')


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _jload(raw: Any, default: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw or ''))
    except Exception:
        return default


def _jdump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except Exception:
        return default
    if out != out or out in {float('inf'), float('-inf')}:
        return default
    return out


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    clean = _clean_text(value, max_len=80)
    return clean or None


def _normalize_surface(row: Any) -> dict[str, Any] | None:
    if isinstance(row, MemorySurface):
        policy = _jload(row.policy_json, {})
        return {
            'id': row.surface_id,
            'surface_id': row.surface_id,
            'title': row.title or row.surface_id,
            'kind': row.semantic_kind or 'generic',
            'semantic_kind': row.semantic_kind or 'generic',
            'visibility_scope': row.visibility_scope or 'shared',
            'write_mode': row.write_mode or 'shared',
            'policy': policy,
            'readers': policy.get('readers') or policy.get('target_roles') or policy.get('target_agent_ids') or ['*'],
            'writers': policy.get('writers') or policy.get('writer_roles') or policy.get('target_roles') or ['runtime'],
            'steward': policy.get('steward') or policy.get('stewards') or policy.get('target_roles') or ['runtime'],
            'path': policy.get('path') or policy.get('file_name') or '',
        }
    source = _as_dict(row)
    sid = _clean_text(source.get('id') or source.get('surface_id') or source.get('surfaceId'), max_len=128)
    if not sid:
        return None
    policy = _as_dict(source.get('policy'))
    return {
        'id': sid,
        'surface_id': sid,
        'title': _clean_text(source.get('title') or sid, max_len=160) or sid,
        'kind': _clean_id(source.get('kind') or source.get('semantic_kind') or source.get('semanticKind') or 'generic', max_len=64) or 'generic',
        'semantic_kind': _clean_id(source.get('semantic_kind') or source.get('semanticKind') or source.get('kind') or 'generic', max_len=64) or 'generic',
        'visibility_scope': _clean_id(source.get('visibility_scope') or source.get('visibilityScope') or 'shared', max_len=64) or 'shared',
        'write_mode': _clean_id(source.get('write_mode') or source.get('writeMode') or source.get('write_policy') or 'shared', max_len=64) or 'shared',
        'policy': policy,
        'readers': _as_list(source.get('readers')) or _as_list(policy.get('readers')) or _as_list(policy.get('target_roles')) or ['*'],
        'writers': _as_list(source.get('writers')) or _as_list(policy.get('writers')) or _as_list(policy.get('target_roles')) or ['runtime'],
        'steward': _as_list(source.get('steward')) or _as_list(source.get('stewards')) or _as_list(policy.get('steward')) or _as_list(policy.get('stewards')) or ['runtime'],
        'path': _clean_text(source.get('path') or policy.get('path') or policy.get('file_name') or '', max_len=280),
        'lens': _clean_text(source.get('lens') or policy.get('lens') or '', max_len=280),
        'promotion_policy': _clean_text(source.get('promotion_policy') or source.get('promotionPolicy') or policy.get('promotion_policy') or '', max_len=280),
    }


def normalize_memory_topology_payload(payload: Any) -> dict[str, Any]:
    raw = _as_dict(payload)
    mode = _clean_id(raw.get('mode') or raw.get('state') or 'compact_single', max_len=64)
    if mode not in VALID_MEMORY_MODES:
        mode = 'compact_single'
    stress = _as_dict(raw.get('stress'))
    stats = _as_dict(raw.get('stats'))
    maintenance = _as_dict(raw.get('maintenance'))
    surfaces = [_normalize_surface(item) for item in _as_list(raw.get('surfaces'))]
    surfaces = [item for item in surfaces if item]
    grants = _as_dict(raw.get('agent_grants') or raw.get('agentGrants'))
    normalized_grants: dict[str, dict[str, Any]] = {}
    for key, value in grants.items():
        row = _as_dict(value)
        grant_key = _clean_id(row.get('agent_id') or row.get('agentId') or key, max_len=128)
        if not grant_key:
            continue
        normalized_grants[grant_key] = {
            'agent_id': grant_key,
            'role': _clean_id(row.get('role') or row.get('role_id') or row.get('roleId') or '', max_len=80),
            'provider': _clean_id(row.get('provider') or '', max_len=80) or None,
            'read': [_clean_text(v, max_len=128) for v in _as_list(row.get('read')) if _clean_text(v, max_len=128)],
            'write': [_clean_text(v, max_len=128) for v in _as_list(row.get('write')) if _clean_text(v, max_len=128)],
            'lens': _clean_text(row.get('lens') or '', max_len=240),
            'write_mode': _clean_id(row.get('write_mode') or row.get('writeMode') or '', max_len=80) or None,
        }
    return {
        **raw,
        'version': int(raw.get('version') or 1),
        'mode': mode,
        'state': _clean_id(raw.get('state') or mode, max_len=80) or mode,
        'selection_reason': [_clean_text(v, max_len=160) for v in _as_list(raw.get('selection_reason') or raw.get('selectionReason')) if _clean_text(v, max_len=160)],
        'stress': {**stress, 'score': _float(stress.get('score'), 0.0), 'reasons': [_clean_text(v, max_len=160) for v in _as_list(stress.get('reasons')) if _clean_text(v, max_len=160)]},
        'stats': stats,
        'surfaces': surfaces,
        'agent_grants': normalized_grants,
        'maintenance': {**maintenance, 'idle_safe': bool(maintenance.get('idle_safe', True)), 'destructive_changes': bool(maintenance.get('destructive_changes', False)), 'actions': [_as_dict(item) for item in _as_list(maintenance.get('actions'))]},
    }


def _surface_counts(surfaces: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for surface in surfaces:
        kind = _clean_id(surface.get('kind') or surface.get('semantic_kind') or 'generic', max_len=64) or 'generic'
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def summarize_memory_topology(topology: dict[str, Any], *, source: str = 'snapshot', snapshot_id: str | None = None, run_id: str | None = None, created_at: str | None = None, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    row = normalize_memory_topology_payload(topology)
    surfaces = _as_list(row.get('surfaces'))
    grants = _as_dict(row.get('agent_grants'))
    maintenance = _as_dict(row.get('maintenance'))
    actions = _as_list(maintenance.get('actions'))
    stress = _as_dict(row.get('stress'))
    return {
        'schema_version': 'goc.memory_topology/v1',
        'source': source,
        'snapshot_id': snapshot_id,
        'run_id': run_id or _clean_text(row.get('run_id'), max_len=128) or None,
        'mode': row.get('mode') or 'compact_single',
        'state': row.get('state') or row.get('mode') or 'compact_single',
        'stress': stress,
        'stress_score': _float(stress.get('score'), 0.0),
        'selection_reason': _as_list(row.get('selection_reason')),
        'stats': _as_dict(row.get('stats')),
        'surfaces': surfaces,
        'surface_count': len(surfaces),
        'surface_kind_counts': _surface_counts(surfaces),
        'agent_grants': grants,
        'agent_grant_count': len(grants),
        'maintenance': maintenance,
        'maintenance_action_count': len(actions),
        'idle_safe': bool(maintenance.get('idle_safe', True)),
        'destructive_changes': bool(maintenance.get('destructive_changes', False)),
        'events': events or [],
        'event_count': len(events or []),
        'created_at': created_at or _iso(row.get('created_at')),
        'updated_at': _iso(row.get('updated_at')),
        'fallback': source.startswith('fallback'),
    }


def latest_memory_topology_snapshot(session: Session, *, thread_id: str, run_id: str | None = None) -> MemoryTopologySnapshot | None:
    statement = select(MemoryTopologySnapshot).where(MemoryTopologySnapshot.thread_id == thread_id)
    clean_run_id = _clean_text(run_id, max_len=128)
    if clean_run_id:
        scoped = session.exec(statement.where(MemoryTopologySnapshot.run_id == clean_run_id).order_by(MemoryTopologySnapshot.updated_at.desc(), MemoryTopologySnapshot.created_at.desc()).limit(1)).first()
        if scoped is not None:
            return scoped
    return session.exec(statement.order_by(MemoryTopologySnapshot.updated_at.desc(), MemoryTopologySnapshot.created_at.desc()).limit(1)).first()


def list_memory_topology_events(session: Session, *, thread_id: str, run_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    clean_limit = max(1, min(int(limit or 20), 100))
    statement = select(MemoryTopologyEvent).where(MemoryTopologyEvent.thread_id == thread_id)
    clean_run_id = _clean_text(run_id, max_len=128)
    if clean_run_id:
        statement = statement.where(MemoryTopologyEvent.run_id == clean_run_id)
    rows = session.exec(statement.order_by(MemoryTopologyEvent.created_at.desc()).limit(clean_limit)).all()
    return [{**_jload(row.event_json, {}), 'id': row.id, 'run_id': row.run_id, 'kind': row.kind, 'previous_mode': row.previous_mode, 'next_mode': row.next_mode, 'stress_score': row.stress_score, 'source': row.source, 'created_at': row.created_at.isoformat() if row.created_at else None} for row in rows]


def build_fallback_memory_topology(session: Session, *, thread: Thread, run_id: str | None = None) -> dict[str, Any]:
    clean_run_id = _clean_text(run_id, max_len=128) or None
    surfaces = [_normalize_surface(row) for row in session.exec(select(MemorySurface).where(MemorySurface.thread_id == thread.id)).all()]
    surfaces = [item for item in surfaces if item]
    projections_stmt = select(MemoryProjection).where(MemoryProjection.thread_id == thread.id)
    if clean_run_id:
        projections_stmt = projections_stmt.where(MemoryProjection.run_id == clean_run_id)
    projections = session.exec(projections_stmt.order_by(MemoryProjection.created_at.desc()).limit(20)).all()
    team_stmt = select(TeamSelectionEvent).where(TeamSelectionEvent.thread_id == thread.id)
    if clean_run_id:
        team_stmt = team_stmt.where(TeamSelectionEvent.run_id == clean_run_id)
    team_event = session.exec(team_stmt.order_by(TeamSelectionEvent.created_at.desc()).limit(1)).first()
    recommendation = _jload(team_event.recommendation_json, {}) if team_event else {}
    selected = _as_dict(recommendation.get('selected_candidate_snapshot'))
    candidate_team = _as_list(selected.get('agents') or selected.get('participants') or selected.get('members'))
    agent_count = len(candidate_team)
    if not agent_count:
        outcome = _jload(team_event.outcome_json, {}) if team_event else {}
        agent_count = int(outcome.get('agent_count') or outcome.get('member_count') or 0) if isinstance(outcome, dict) else 0
    role_ids: set[str] = set()
    agent_grants: dict[str, dict[str, Any]] = {}
    surface_lookup = {str(s.get('id') or s.get('surface_id')): s for s in surfaces}
    for projection in projections:
        summary = _jload(projection.summary_json, {})
        role = _clean_id(projection.role_id or projection.agent_id or 'agent', max_len=80) or 'agent'
        key = _clean_id(projection.agent_id or projection.role_id or role, max_len=128) or role
        if role:
            role_ids.add(role)
        read_surfaces = [sid for sid in _as_list(summary.get('visible_surface_ids')) if str(sid or '').strip()]
        if not read_surfaces and _jload(projection.visible_node_ids_json, []):
            read_surfaces = [str(s.get('id') or s.get('surface_id')) for s in surfaces if str(s.get('visibility_scope') or 'shared') == 'shared']
        writable: list[str] = []
        for sid, surface in surface_lookup.items():
            writers = {str(v).strip().lower() for v in _as_list(surface.get('writers'))}
            if '*' in writers or role in writers or not writers:
                writable.append(sid)
        agent_grants[key] = {'agent_id': key, 'role': role, 'read': read_surfaces, 'write': writable, 'lens': 'fallback projection from GoC memory projections', 'write_mode': 'contracted_or_runtime_append'}
    if agent_count > 1 and not role_ids:
        role_ids.add('team')
    stress_score = min(len(surfaces) * 0.45, 2.5) + min(len(projections) * 0.18, 1.5) + min(max(agent_count - 1, 0) * 0.8, 2.4) + min(len(role_ids) * 0.35, 1.8)
    if stress_score < 1.2 and not surfaces and agent_count <= 1:
        mode = 'ephemeral'
    elif stress_score < 3.0 and agent_count <= 1 and len(surfaces) <= 2:
        mode = 'compact_single'
    elif stress_score < 5.4 and agent_count <= 1:
        mode = 'structured_single'
    elif stress_score < 7.5:
        mode = 'team_scoped'
    else:
        mode = 'graph_snapshot'
    reasons: list[str] = []
    if surfaces:
        reasons.append('goc_memory_surfaces')
    if projections:
        reasons.append('goc_projection_history')
    if agent_count > 1:
        reasons.append('team_selection_event')
    return {'version': 1, 'mode': mode, 'state': mode, 'selection_reason': ['fallback_from_goc_memory_graph'], 'stress': {'score': round(stress_score, 2), 'reasons': reasons}, 'stats': {'surface_count': len(surfaces), 'projection_count': len(projections), 'team_agent_count': agent_count, 'role_count': len(role_ids)}, 'surfaces': surfaces, 'agent_grants': agent_grants, 'maintenance': {'generated_at': datetime.now(timezone.utc).isoformat(), 'idle_safe': True, 'destructive_changes': False, 'actions': [{'action': 'await_runtime_topology_snapshot', 'reason': 'No ddalggak memory_topology snapshot has been pushed yet', 'destructive': False, 'candidate_only': True}]}}


def build_run_studio_memory_topology(session: Session, *, thread: Thread, run_id: str | None = None, event_limit: int = 12) -> dict[str, Any]:
    snapshot = latest_memory_topology_snapshot(session, thread_id=thread.id, run_id=run_id)
    if snapshot is not None:
        events = list_memory_topology_events(session, thread_id=thread.id, run_id=snapshot.run_id or run_id, limit=event_limit)
        return summarize_memory_topology(_jload(snapshot.topology_json, {}), source=snapshot.source or 'ddalggak', snapshot_id=snapshot.id, run_id=snapshot.run_id, created_at=snapshot.created_at.isoformat() if snapshot.created_at else None, events=events)
    fallback = build_fallback_memory_topology(session, thread=thread, run_id=run_id)
    return summarize_memory_topology(fallback, source='fallback_goc_memory_graph', run_id=run_id, events=[])


def record_memory_topology_snapshot(session: Session, *, thread: Thread, topology: dict[str, Any], run_id: str | None = None, source: str = 'ddalggak', events: list[dict[str, Any]] | None = None) -> MemoryTopologySnapshot:
    normalized = normalize_memory_topology_payload(topology)
    row = MemoryTopologySnapshot(thread_id=thread.id, run_id=_clean_text(run_id or normalized.get('run_id'), max_len=128) or None, mode=normalized.get('mode') or 'compact_single', state=normalized.get('state') or normalized.get('mode') or 'compact_single', stress_score=_float(_as_dict(normalized.get('stress')).get('score'), 0.0), source=_clean_text(source or normalized.get('source') or 'ddalggak', max_len=80) or 'ddalggak', topology_json=_jdump(normalized), created_at=utcnow(), updated_at=utcnow())
    session.add(row)
    session.flush()
    for item in events or _as_list(normalized.get('events')):
        event = _as_dict(item)
        if not event:
            continue
        event_row = MemoryTopologyEvent(thread_id=thread.id, run_id=row.run_id, snapshot_id=row.id, kind=_clean_id(event.get('kind') or event.get('event_type') or 'memory_topology_event', max_len=80) or 'memory_topology_event', previous_mode=_clean_id(event.get('previous_mode') or event.get('from') or '', max_len=80) or None, next_mode=_clean_id(event.get('next_mode') or event.get('to') or normalized.get('mode'), max_len=80) or None, stress_score=_float(event.get('stress_score') or event.get('stress') or row.stress_score, row.stress_score), source=row.source, event_json=_jdump(event), created_at=utcnow())
        session.add(event_row)
    return row
