from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models import ModelNodeRecord, ModelNodeUsageEvent, utcnow


def _clean(value: Any = '', max_len: int = 1000) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text[:max_len]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _loads(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or '')
    except Exception:
        return default


def _int(value: Any) -> int:
    try:
        n = int(float(value))
        return n if n >= 0 else 0
    except Exception:
        return 0


def _float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


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


def _node_id(node: dict[str, Any]) -> str:
    return _clean(node.get('node_id') or node.get('nodeId') or node.get('id') or ':'.join([str(node.get('provider') or ''), str(node.get('model') or node.get('model_id') or '')]).strip(':'), 300)


def _profile(node: dict[str, Any], snake: str, camel: str = '') -> dict[str, Any]:
    return _as_dict(node.get(snake) or node.get(camel or snake))


def _to_dict(row: ModelNodeRecord) -> dict[str, Any]:
    return {
        'id': row.id,
        'node_id': row.node_id,
        'provider': row.provider,
        'runtime': row.runtime,
        'model': row.model,
        'status': row.status,
        'cost_tier': row.cost_tier,
        'latency_tier': row.latency_tier,
        'quality_tier': row.quality_tier,
        'privacy_tier': row.privacy_tier,
        'data_boundary': row.data_boundary,
        'allow_private_context': row.allow_private_context,
        'context_tokens': row.context_tokens,
        'source': row.source,
        'node': _loads(row.node_json, {}),
        'last_seen_at': row.last_seen_at.isoformat(),
        'updated_at': row.updated_at.isoformat(),
    }


def upsert_model_nodes(session: Session, payload: dict[str, Any], *, source: str = 'ddalggak') -> dict[str, Any]:
    body = _as_dict(payload)
    nodes = _as_list(body.get('nodes') or body.get('items') or body.get('model_nodes') or body.get('modelNodes'))
    if not nodes and body:
        nodes = [body]
    saved: list[ModelNodeRecord] = []
    created = 0
    updated = 0
    for raw in nodes:
        node = _as_dict(raw)
        node_id = _node_id(node)
        if not node_id:
            continue
        cost = _profile(node, 'cost_profile', 'costProfile')
        latency = _profile(node, 'latency_profile', 'latencyProfile')
        quality = _profile(node, 'quality_profile', 'qualityProfile')
        privacy = _profile(node, 'privacy_profile', 'privacyProfile')
        limits = _profile(node, 'limits')
        existing = session.exec(select(ModelNodeRecord).where(ModelNodeRecord.node_id == node_id)).first()
        row = existing or ModelNodeRecord(node_id=node_id)
        if existing:
            updated += 1
        else:
            created += 1
        row.provider = _clean(node.get('provider') or '', 120)
        row.runtime = _clean(node.get('runtime') or node.get('kind') or '', 120)
        row.model = _clean(node.get('model') or node.get('model_id') or node.get('modelId') or '', 200)
        row.status = _clean(node.get('status') or 'available', 80)
        row.cost_tier = _clean(cost.get('tier') or 'unknown', 80)
        row.latency_tier = _clean(latency.get('tier') or 'unknown', 80)
        row.quality_tier = _clean(quality.get('tier') or 'standard', 80)
        row.privacy_tier = _clean(privacy.get('tier') or 'unknown', 100)
        row.data_boundary = _clean(privacy.get('data_boundary') or privacy.get('dataBoundary') or '', 160)
        row.allow_private_context = bool(privacy.get('allow_private_context') or privacy.get('allowPrivateContext') or node.get('trusted_context') or node.get('trustedContext'))
        row.context_tokens = _int(limits.get('context_tokens') or limits.get('contextTokens') or node.get('context_tokens') or node.get('contextTokens'))
        row.source = _clean(body.get('source') or node.get('source') or source or 'ddalggak', 120)
        row.node_json = _dumps(node)
        row.last_seen_at = _parse_dt(node.get('last_seen_at') or node.get('lastSeenAt') or body.get('discovered_at') or body.get('updated_at'))
        row.updated_at = utcnow()
        session.add(row)
        saved.append(row)
    session.commit()
    return {'ok': True, 'created': created, 'updated': updated, 'summary': summarize_model_nodes(saved), 'items': [_to_dict(row) for row in saved]}


def summarize_model_nodes(rows: list[ModelNodeRecord]) -> dict[str, Any]:
    by_provider: dict[str, int] = {}
    by_cost: dict[str, int] = {}
    trusted_private = 0
    for row in rows:
        by_provider[row.provider or 'unknown'] = by_provider.get(row.provider or 'unknown', 0) + 1
        by_cost[row.cost_tier or 'unknown'] = by_cost.get(row.cost_tier or 'unknown', 0) + 1
        if row.allow_private_context:
            trusted_private += 1
    return {'node_count': len(rows), 'by_provider': by_provider, 'by_cost_tier': by_cost, 'private_context_allowed_count': trusted_private}


def list_model_nodes(session: Session, *, provider: str | None = None, limit: int = 200) -> dict[str, Any]:
    stmt = select(ModelNodeRecord)
    clean_provider = _clean(provider or '', 120)
    if clean_provider:
        stmt = stmt.where(ModelNodeRecord.provider == clean_provider)
    rows = list(session.exec(stmt.order_by(ModelNodeRecord.updated_at.desc()).limit(max(1, min(int(limit or 200), 1000)))))
    return {'ok': True, 'summary': summarize_model_nodes(rows), 'items': [_to_dict(row) for row in rows]}


def _usage_to_dict(row: ModelNodeUsageEvent) -> dict[str, Any]:
    return {
        'id': row.id,
        'thread_id': row.thread_id,
        'run_id': row.run_id,
        'node_id': row.node_id,
        'provider': row.provider,
        'model': row.model,
        'agent_id': row.agent_id,
        'role_id': row.role_id,
        'task_kind': row.task_kind,
        'prompt_tokens': row.prompt_tokens,
        'completion_tokens': row.completion_tokens,
        'total_tokens': row.total_tokens,
        'latency_ms': row.latency_ms,
        'cost_estimate': row.cost_estimate,
        'event': _loads(row.event_json, {}),
        'created_at': row.created_at.isoformat(),
    }


def ingest_model_usage(session: Session, payload: dict[str, Any], *, thread_id: str | None = None, source: str = 'ddalggak') -> dict[str, Any]:
    body = _as_dict(payload)
    events = _as_list(body.get('events') or body.get('items') or body.get('usage'))
    if not events and body:
        events = [body]
    saved: list[ModelNodeUsageEvent] = []
    for raw in events:
        event = _as_dict(raw)
        usage = _as_dict(event.get('token_usage') or event.get('tokenUsage') or event.get('usage'))
        node = ModelNodeUsageEvent(
            thread_id=_clean(event.get('thread_id') or event.get('threadId') or thread_id or '', 160) or None,
            run_id=_clean(event.get('run_id') or event.get('runId') or '', 160) or None,
            node_id=_clean(event.get('node_id') or event.get('nodeId') or event.get('model_node_id') or '', 300),
            provider=_clean(event.get('provider') or '', 120),
            model=_clean(event.get('model') or '', 200),
            agent_id=_clean(event.get('agent_id') or event.get('agentId') or '', 160) or None,
            role_id=_clean(event.get('role_id') or event.get('roleId') or '', 160) or None,
            task_kind=_clean(event.get('task_kind') or event.get('taskKind') or event.get('role') or '', 160),
            prompt_tokens=_int(usage.get('prompt_tokens') or usage.get('promptTokens') or event.get('prompt_tokens')),
            completion_tokens=_int(usage.get('completion_tokens') or usage.get('completionTokens') or usage.get('output_tokens') or event.get('completion_tokens')),
            total_tokens=_int(usage.get('total_tokens') or usage.get('totalTokens') or event.get('total_tokens')),
            latency_ms=_int(event.get('latency_ms') or event.get('latencyMs')),
            cost_estimate=_float(event.get('cost_estimate') or event.get('costEstimate')),
            event_json=_dumps({**event, 'source': source}),
            created_at=_parse_dt(event.get('ts') or event.get('created_at') or event.get('createdAt')),
        )
        if not node.total_tokens:
            node.total_tokens = node.prompt_tokens + node.completion_tokens
        session.add(node)
        saved.append(node)
    session.commit()
    return {'ok': True, 'created': len(saved), 'summary': summarize_usage(saved), 'items': [_usage_to_dict(row) for row in saved]}


def summarize_usage(rows: list[ModelNodeUsageEvent]) -> dict[str, Any]:
    total_tokens = sum(int(row.total_tokens or 0) for row in rows)
    by_provider: dict[str, int] = {}
    for row in rows:
        by_provider[row.provider or 'unknown'] = by_provider.get(row.provider or 'unknown', 0) + int(row.total_tokens or 0)
    return {'event_count': len(rows), 'total_tokens': total_tokens, 'tokens_by_provider': by_provider}


def list_model_usage(session: Session, *, thread_id: str | None = None, run_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    stmt = select(ModelNodeUsageEvent)
    clean_thread = _clean(thread_id or '', 160)
    clean_run = _clean(run_id or '', 160)
    if clean_thread:
        stmt = stmt.where(ModelNodeUsageEvent.thread_id == clean_thread)
    if clean_run:
        stmt = stmt.where(ModelNodeUsageEvent.run_id == clean_run)
    rows = list(session.exec(stmt.order_by(ModelNodeUsageEvent.created_at.desc()).limit(max(1, min(int(limit or 100), 500)))))
    return {'ok': True, 'summary': summarize_usage(rows), 'items': [_usage_to_dict(row) for row in rows]}
