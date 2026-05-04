from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models import MemoryDemandEvent, Thread, utcnow


def _clean_text(value: Any, *, max_len: int = 500) -> str:
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


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    clean = _clean_text(value, max_len=80)
    return clean or None


def normalize_memory_demand_event(event: Any, *, run_id: str | None = None, source: str = 'ddalggak') -> dict[str, Any]:
    raw = _as_dict(event)
    reasons = raw.get('demand_reasons') or raw.get('demandReasons') or raw.get('reasons') or []
    sources = raw.get('sources') or raw.get('source_paths') or raw.get('sourcePaths') or []
    retrieval_mode = raw.get('retrieval_mode') or raw.get('retrievalMode') or raw.get('mode') or 'runtime_preflight'
    router_plan = _as_dict(raw.get('router_memory_plan') or raw.get('routerMemoryPlan') or raw.get('memory_routing') or raw.get('memoryRouting') or raw.get('memory_demand') or raw.get('memoryDemand'))
    source_types = raw.get('source_types') or raw.get('sourceTypes') or router_plan.get('source_types') or router_plan.get('sourceTypes') or []
    surface_ids = raw.get('surface_ids') or raw.get('surfaceIds') or router_plan.get('surface_ids') or router_plan.get('surfaceIds') or []
    classifier = raw.get('classifier') or router_plan.get('classifier') or router_plan.get('classifier_source') or router_plan.get('classifierSource')
    confidence_raw = raw.get('confidence') if raw.get('confidence') is not None else router_plan.get('confidence')
    try:
        confidence = max(0.0, min(1.0, float(confidence_raw))) if confidence_raw is not None else None
    except Exception:
        confidence = None
    matching = _as_dict(raw.get('matching') or raw.get('matching_summary') or raw.get('matchingSummary'))
    if not matching:
        matching = {
            'strategy': raw.get('strategy') or 'query_intent_plus_token_scoring',
            'semantic_note': raw.get('semantic_note') or raw.get('semanticNote') or '',
            'rule_based': bool(raw.get('rule_based')) if 'rule_based' in raw else None,
            'router_memory_plan': router_plan or None,
            'classifier': classifier or None,
            'confidence': confidence,
        }
    return {
        **raw,
        'query': _clean_text(raw.get('query') or raw.get('user_text') or raw.get('userText') or '', max_len=500),
        'reason': _clean_id(raw.get('reason') or 'context_preflight', max_len=100) or 'context_preflight',
        'demand_reasons': [_clean_text(v, max_len=120) for v in _as_list(reasons) if _clean_text(v, max_len=120)],
        'sources': [_clean_text(v, max_len=240) for v in _as_list(sources) if _clean_text(v, max_len=240)],
        'item_count': max(0, int(raw.get('item_count') or raw.get('itemCount') or 0)),
        'agent_id': _clean_id(raw.get('agent_id') or raw.get('agentId') or '', max_len=128) or None,
        'role_id': _clean_id(raw.get('role_id') or raw.get('roleId') or '', max_len=128) or None,
        'run_id': _clean_text(raw.get('run_id') or raw.get('runId') or run_id or '', max_len=128) or None,
        'retrieval_mode': _clean_id(retrieval_mode, max_len=100) or 'runtime_preflight',
        'classifier': _clean_id(classifier, max_len=100) or None,
        'confidence': confidence,
        'source_types': [_clean_id(v, max_len=80) for v in _as_list(source_types) if _clean_id(v, max_len=80)],
        'surface_ids': [_clean_id(v, max_len=120) for v in _as_list(surface_ids) if _clean_id(v, max_len=120)],
        'router_memory_plan': router_plan,
        'source': _clean_id(raw.get('source') or source or 'ddalggak', max_len=80) or 'ddalggak',
        'matching': matching,
    }


def summarize_memory_demand_event(row_or_event: Any) -> dict[str, Any]:
    if isinstance(row_or_event, MemoryDemandEvent):
        raw = _jload(row_or_event.event_json, {})
        reasons = _jload(row_or_event.demand_reasons_json, [])
        sources = _jload(row_or_event.sources_json, [])
        source_types = _jload(getattr(row_or_event, 'source_types_json', '[]'), [])
        surface_ids = _jload(getattr(row_or_event, 'surface_ids_json', '[]'), [])
        return {
            'id': row_or_event.id,
            'thread_id': row_or_event.thread_id,
            'run_id': row_or_event.run_id,
            'query': row_or_event.query,
            'reason': row_or_event.reason,
            'demand_reasons': reasons,
            'sources': sources,
            'item_count': row_or_event.item_count,
            'agent_id': row_or_event.agent_id,
            'role_id': row_or_event.role_id,
            'retrieval_mode': row_or_event.retrieval_mode,
            'classifier': getattr(row_or_event, 'classifier', None),
            'confidence': getattr(row_or_event, 'confidence', None),
            'source_types': source_types,
            'surface_ids': surface_ids,
            'router_memory_plan': _as_dict(raw.get('router_memory_plan')),
            'source': row_or_event.source,
            'matching': _as_dict(raw.get('matching')),
            'event': raw,
            'created_at': _iso(row_or_event.created_at),
        }
    event = normalize_memory_demand_event(row_or_event)
    return {
        'id': event.get('id'),
        'thread_id': event.get('thread_id'),
        'run_id': event.get('run_id'),
        'query': event.get('query'),
        'reason': event.get('reason'),
        'demand_reasons': event.get('demand_reasons') or [],
        'sources': event.get('sources') or [],
        'item_count': event.get('item_count') or 0,
        'agent_id': event.get('agent_id'),
        'role_id': event.get('role_id'),
        'retrieval_mode': event.get('retrieval_mode') or 'runtime_preflight',
        'classifier': event.get('classifier'),
        'confidence': event.get('confidence'),
        'source_types': event.get('source_types') or [],
        'surface_ids': event.get('surface_ids') or [],
        'router_memory_plan': _as_dict(event.get('router_memory_plan')),
        'source': event.get('source') or 'ddalggak',
        'matching': _as_dict(event.get('matching')),
        'event': event,
        'created_at': _iso(event.get('created_at')),
    }


def record_memory_demand_events(
    session: Session,
    *,
    thread: Thread,
    events: list[dict[str, Any]],
    run_id: str | None = None,
    source: str = 'ddalggak',
) -> list[MemoryDemandEvent]:
    rows: list[MemoryDemandEvent] = []
    for item in events or []:
        event = normalize_memory_demand_event(item, run_id=run_id, source=source)
        if not event.get('query') and not event.get('demand_reasons') and not event.get('sources'):
            continue
        row = MemoryDemandEvent(
            thread_id=thread.id,
            run_id=event.get('run_id') or (_clean_text(run_id, max_len=128) or None),
            query=event.get('query') or '',
            reason=event.get('reason') or 'context_preflight',
            demand_reasons_json=_jdump(event.get('demand_reasons') or []),
            sources_json=_jdump(event.get('sources') or []),
            item_count=int(event.get('item_count') or 0),
            agent_id=event.get('agent_id'),
            role_id=event.get('role_id'),
            retrieval_mode=event.get('retrieval_mode') or 'runtime_preflight',
            classifier=event.get('classifier'),
            confidence=event.get('confidence'),
            source_types_json=_jdump(event.get('source_types') or []),
            surface_ids_json=_jdump(event.get('surface_ids') or []),
            source=event.get('source') or source or 'ddalggak',
            event_json=_jdump(event),
            created_at=utcnow(),
        )
        session.add(row)
        rows.append(row)
    return rows


def list_memory_demand_events(session: Session, *, thread_id: str, run_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    clean_limit = max(1, min(int(limit or 20), 100))
    statement = select(MemoryDemandEvent).where(MemoryDemandEvent.thread_id == thread_id)
    clean_run_id = _clean_text(run_id, max_len=128)
    if clean_run_id:
        statement = statement.where(MemoryDemandEvent.run_id == clean_run_id)
    rows = session.exec(statement.order_by(MemoryDemandEvent.created_at.desc()).limit(clean_limit)).all()
    return [summarize_memory_demand_event(row) for row in rows]


def _count_by(items: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        values = item.get(key)
        if isinstance(values, list):
            iterable = values
        else:
            iterable = [values]
        for value in iterable:
            clean = _clean_id(value, max_len=120)
            if not clean:
                continue
            counts[clean] = counts.get(clean, 0) + 1
    return counts


def build_run_studio_memory_demand(session: Session, *, thread: Thread, run_id: str | None = None, limit: int = 16) -> dict[str, Any]:
    events = list_memory_demand_events(session, thread_id=thread.id, run_id=run_id, limit=limit)
    source_counts = _count_by(events, 'sources')
    reason_counts = _count_by(events, 'demand_reasons')
    retrieval_counts = _count_by(events, 'retrieval_mode')
    classifier_counts = _count_by(events, 'classifier')
    source_type_counts = _count_by(events, 'source_types')
    surface_counts = _count_by(events, 'surface_ids')
    agent_counts = _count_by(events, 'agent_id')
    return {
        'schema_version': 'goc.memory_demand/v1',
        'thread_id': thread.id,
        'run_id': _clean_text(run_id, max_len=128) or None,
        'event_count': len(events),
        'events': events,
        'reason_counts': reason_counts,
        'source_counts': source_counts,
        'retrieval_mode_counts': retrieval_counts,
        'classifier_counts': classifier_counts,
        'source_type_counts': source_type_counts,
        'surface_counts': surface_counts,
        'agent_counts': agent_counts,
        'latest_query': events[0]['query'] if events else None,
        'latest_at': events[0]['created_at'] if events else None,
        'preflight_semantics': {
            'goal': 'retrieve likely needed memory before agent execution',
            'runtime_contract': 'question-derived memory demand is injected before role/topology lens context is used',
            'matching_note': 'GoC records the runtime retrieval event; ddalggak may combine router LLM memory plans, intent classifiers, lexical expansion, token scoring, and prompt instructions. Exact surface matches are not required for the audit model.',
            'router_contract': 'The supervisor router may emit memory_routing or action.scope.memory_demand; the runtime uses that plan before role/topology lens fallback.',
        },
        'empty': len(events) == 0,
    }
