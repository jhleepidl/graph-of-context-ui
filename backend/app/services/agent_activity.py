from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models import AgentActivityEvent, Thread, utcnow


def _clean(value: Any = '', max_len: int = 2000) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text[:max_len]


def _loads(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or '')
    except Exception:
        return default


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value or '').strip()
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return utcnow()


def _event_kind(row: dict[str, Any], explicit: str = '') -> str:
    value = _clean(explicit or row.get('event_kind') or row.get('kind') or '', 80).lower()
    if value in {'activity', 'handoff', 'policy'}:
        return value
    if row.get('from_agent') or row.get('to_agent') or row.get('message_type'):
        return 'handoff'
    if row.get('workspace_write') or row.get('legacy_manual_fallback') or row.get('execution_mode') or row.get('runtimeExecutionPolicy'):
        return 'policy'
    return 'activity'


def _normalize(row: dict[str, Any], *, thread: Thread, run_id: str | None = None, event_kind: str = '', source: str = 'ddalggak') -> dict[str, Any]:
    raw = _as_dict(row)
    kind = _event_kind(raw, event_kind)
    runtime_policy = _as_dict(raw.get('runtime_execution_policy') or raw.get('runtimeExecutionPolicy') or raw.get('runtime_policy') or raw.get('runtimePolicy'))
    requirements = _as_dict(raw.get('requirements'))
    metadata = _as_dict(raw.get('metadata') or raw.get('payload'))
    payload = {**raw, 'metadata': metadata, 'requirements': requirements}
    clean_run_id = _clean(raw.get('run_id') or raw.get('runId') or run_id or '', 160) or None
    return {
        'thread_id': thread.id,
        'run_id': clean_run_id,
        'event_kind': kind,
        'event_type': _clean(raw.get('event') or raw.get('message_type') or raw.get('messageType') or raw.get('type') or f'agent_{kind}', 120),
        'agent_id': _clean(raw.get('agent_id') or raw.get('agentId') or '', 160) or None,
        'role_id': _clean(raw.get('role_id') or raw.get('roleId') or '', 160) or None,
        'from_agent': _clean(raw.get('from_agent') or raw.get('fromAgent') or '', 160) or None,
        'to_agent': _clean(raw.get('to_agent') or raw.get('toAgent') or '', 160) or None,
        'provider': _clean(raw.get('provider') or '', 120) or None,
        'model': _clean(raw.get('model') or '', 200) or None,
        'summary': _clean(raw.get('summary') or raw.get('message') or raw.get('decision') or '', 2000),
        'decision': _clean(raw.get('decision') or '', 200),
        'execution_mode': _clean(raw.get('execution_mode') or raw.get('executionMode') or runtime_policy.get('execution_mode') or runtime_policy.get('executionMode') or '', 120),
        'workspace_write': _clean(raw.get('workspace_write') or raw.get('workspaceWrite') or runtime_policy.get('workspace_write') or runtime_policy.get('workspaceWrite') or '', 120),
        'artifact_delivery': _clean(raw.get('artifact_delivery') or raw.get('artifactDelivery') or runtime_policy.get('artifact_delivery') or runtime_policy.get('artifactDelivery') or '', 120),
        'legacy_manual_fallback': _clean(raw.get('legacy_manual_fallback') or raw.get('legacyManualFallback') or runtime_policy.get('legacy_manual_fallback') or runtime_policy.get('legacyManualFallback') or '', 120),
        'source': _clean(raw.get('source') or source or 'ddalggak', 120),
        'source_event_id': _clean(raw.get('source_event_id') or raw.get('sourceEventId') or raw.get('id') or '', 200),
        'payload_json': _dumps(payload),
        'created_at': _parse_dt(raw.get('ts') or raw.get('created_at') or raw.get('createdAt')),
    }


def _to_dict(row: AgentActivityEvent) -> dict[str, Any]:
    return {
        'id': row.id,
        'thread_id': row.thread_id,
        'run_id': row.run_id,
        'event_kind': row.event_kind,
        'event_type': row.event_type,
        'agent_id': row.agent_id,
        'role_id': row.role_id,
        'from_agent': row.from_agent,
        'to_agent': row.to_agent,
        'provider': row.provider,
        'model': row.model,
        'summary': row.summary,
        'decision': row.decision,
        'execution_mode': row.execution_mode,
        'workspace_write': row.workspace_write,
        'artifact_delivery': row.artifact_delivery,
        'legacy_manual_fallback': row.legacy_manual_fallback,
        'source': row.source,
        'source_event_id': row.source_event_id,
        'payload': _loads(row.payload_json, {}),
        'created_at': row.created_at.isoformat(),
        'ingested_at': row.ingested_at.isoformat(),
    }


def summarize_agent_activity(rows: list[AgentActivityEvent]) -> dict[str, Any]:
    by_kind: dict[str, int] = {}
    by_policy: dict[str, int] = {}
    fallback_disabled = 0
    workspace_allowed = 0
    for row in rows:
        by_kind[row.event_kind] = by_kind.get(row.event_kind, 0) + 1
        if row.event_kind == 'policy':
            key = row.workspace_write or row.decision or 'policy'
            by_policy[key] = by_policy.get(key, 0) + 1
        if row.legacy_manual_fallback == 'disabled':
            fallback_disabled += 1
        if row.workspace_write == 'allowed_in_workspace':
            workspace_allowed += 1
    return {
        'event_count': len(rows),
        'by_kind': by_kind,
        'policy_decisions': by_policy,
        'workspace_write_allowed_count': workspace_allowed,
        'legacy_manual_fallback_disabled_count': fallback_disabled,
    }


def list_agent_activity(session: Session, thread: Thread, *, run_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    stmt = select(AgentActivityEvent).where(AgentActivityEvent.thread_id == thread.id)
    clean_run_id = _clean(run_id or '', 160)
    if clean_run_id:
        stmt = stmt.where(AgentActivityEvent.run_id == clean_run_id)
    rows = list(session.exec(stmt.order_by(AgentActivityEvent.created_at.desc()).limit(max(1, min(int(limit or 100), 500)))))
    return {'ok': True, 'thread_id': thread.id, 'run_id': clean_run_id or None, 'summary': summarize_agent_activity(rows), 'items': [_to_dict(row) for row in rows]}


def ingest_agent_activity(session: Session, thread: Thread, payload: dict[str, Any], *, source: str = 'ddalggak') -> dict[str, Any]:
    body = _as_dict(payload)
    run_id = _clean(body.get('run_id') or body.get('runId') or '', 160) or None
    rows: list[dict[str, Any]] = []
    for key, kind in [('events', ''), ('activity', 'activity'), ('activities', 'activity'), ('handoffs', 'handoff'), ('policy_resolutions', 'policy'), ('policyResolutions', 'policy'), ('execution_policy_resolutions', 'policy')]:
        for raw in _as_list(body.get(key)):
            rows.append(_normalize(_as_dict(raw), thread=thread, run_id=run_id, event_kind=kind, source=source))
    if not rows and body:
        rows.append(_normalize(body, thread=thread, run_id=run_id, source=source))

    saved = []
    for row in rows:
        event = AgentActivityEvent(**row)
        session.add(event)
        saved.append(event)
    session.commit()
    return {'ok': True, 'created': len(saved), 'summary': summarize_agent_activity(saved), 'items': [_to_dict(row) for row in saved]}
