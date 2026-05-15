from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from app.models import AgentActivityEvent, ContextProjectionEvent, ContextSubstrateOperation, ContextSubstrateSnapshot, ContextWriteMetricEvent, HandoffDeltaEvent, ModelNodeUsageEvent, SemanticBoardCard, SemanticBoardLink, Thread


def _loads(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or '')
    except Exception:
        return default


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value else None


def _short(value: Any, limit: int = 240) -> str:
    text = ' '.join(str(value or '').split())
    return text if len(text) <= limit else text[: limit - 1] + '…'


def _activity_item(row: AgentActivityEvent) -> dict[str, Any]:
    payload = _loads(row.payload_json, {})
    reasons = payload.get('reasons') or payload.get('metadata', {}).get('reasons') or []
    return {
        'kind': row.event_kind,
        'type': row.event_type,
        'title': row.summary or row.decision or row.event_type,
        'summary': _short(row.summary or row.decision or row.event_type),
        'agent_id': row.agent_id,
        'role_id': row.role_id,
        'from_agent': row.from_agent,
        'to_agent': row.to_agent,
        'provider': row.provider,
        'model': row.model,
        'decision': row.decision,
        'reasons': reasons if isinstance(reasons, list) else [],
        'policy': {
            'execution_mode': row.execution_mode,
            'workspace_write': row.workspace_write,
            'artifact_delivery': row.artifact_delivery,
            'legacy_manual_fallback': row.legacy_manual_fallback,
        },
        'created_at': _iso(row.created_at),
        'source': row.source,
    }


def _card_item(row: SemanticBoardCard) -> dict[str, Any]:
    return {
        'kind': row.card_type,
        'id': row.card_id,
        'title': row.title,
        'status': row.status,
        'source': row.source,
        'reuse_score': row.reuse_score,
        'confidence': row.confidence,
        'tags': _loads(row.tags_json, []),
        'performance': _loads(row.performance_json, {}),
        'content': _loads(row.content_json, {}),
        'updated_at': _iso(row.updated_at),
    }


def _model_item(row: ModelNodeUsageEvent) -> dict[str, Any]:
    return {
        'kind': 'model_usage',
        'node_id': row.node_id,
        'provider': row.provider,
        'model': row.model,
        'agent_id': row.agent_id,
        'role_id': row.role_id,
        'task_kind': row.task_kind,
        'tokens': row.total_tokens,
        'prompt_tokens': row.prompt_tokens,
        'completion_tokens': row.completion_tokens,
        'latency_ms': row.latency_ms,
        'cost_estimate': row.cost_estimate,
        'created_at': _iso(row.created_at),
    }


def build_decision_trace(session: Session, thread: Thread, *, run_id: str | None = None, limit: int = 80) -> dict[str, Any]:
    clean_run = (run_id or '').strip() or None
    bounded = max(1, min(int(limit or 80), 250))

    activity_stmt = select(AgentActivityEvent).where(AgentActivityEvent.thread_id == thread.id)
    usage_stmt = select(ModelNodeUsageEvent).where(ModelNodeUsageEvent.thread_id == thread.id)
    context_stmt = select(ContextSubstrateOperation).where(ContextSubstrateOperation.thread_id == thread.id)
    projection_stmt = select(ContextProjectionEvent).where(ContextProjectionEvent.thread_id == thread.id)
    write_stmt = select(ContextWriteMetricEvent).where(ContextWriteMetricEvent.thread_id == thread.id)
    handoff_delta_stmt = select(HandoffDeltaEvent).where(HandoffDeltaEvent.thread_id == thread.id)
    snapshot_stmt = select(ContextSubstrateSnapshot).where(ContextSubstrateSnapshot.thread_id == thread.id)
    card_stmt = select(SemanticBoardCard).where(SemanticBoardCard.thread_id == thread.id)
    link_stmt = select(SemanticBoardLink).where(SemanticBoardLink.thread_id == thread.id)
    if clean_run:
        activity_stmt = activity_stmt.where(AgentActivityEvent.run_id == clean_run)
        usage_stmt = usage_stmt.where(ModelNodeUsageEvent.run_id == clean_run)
        context_stmt = context_stmt.where(ContextSubstrateOperation.run_id == clean_run)
        projection_stmt = projection_stmt.where(ContextProjectionEvent.run_id == clean_run)
        write_stmt = write_stmt.where(ContextWriteMetricEvent.run_id == clean_run)
        handoff_delta_stmt = handoff_delta_stmt.where(HandoffDeltaEvent.run_id == clean_run)
        snapshot_stmt = snapshot_stmt.where(ContextSubstrateSnapshot.run_id == clean_run)
        card_stmt = card_stmt.where((SemanticBoardCard.run_id == clean_run) | (SemanticBoardCard.run_id.is_(None)))
        link_stmt = link_stmt.where((SemanticBoardLink.run_id == clean_run) | (SemanticBoardLink.run_id.is_(None)))

    activity_rows = list(session.exec(activity_stmt.order_by(AgentActivityEvent.created_at.desc()).limit(bounded)))
    usage_rows = list(session.exec(usage_stmt.order_by(ModelNodeUsageEvent.created_at.desc()).limit(bounded)))
    context_rows = list(session.exec(context_stmt.order_by(ContextSubstrateOperation.version.desc(), ContextSubstrateOperation.created_at.desc()).limit(bounded)))
    projection_rows = list(session.exec(projection_stmt.order_by(ContextProjectionEvent.created_at.desc()).limit(bounded)))
    write_rows = list(session.exec(write_stmt.order_by(ContextWriteMetricEvent.created_at.desc()).limit(bounded)))
    handoff_delta_rows = list(session.exec(handoff_delta_stmt.order_by(HandoffDeltaEvent.created_at.desc()).limit(bounded)))
    snapshot_rows = list(session.exec(snapshot_stmt.order_by(ContextSubstrateSnapshot.version.desc()).limit(8)))
    card_rows = list(session.exec(card_stmt.order_by(SemanticBoardCard.updated_at.desc()).limit(300)))
    link_rows = list(session.exec(link_stmt.order_by(SemanticBoardLink.updated_at.desc()).limit(500)))

    policies = [_activity_item(row) for row in activity_rows if row.event_kind == 'policy']
    handoffs = [_activity_item(row) for row in activity_rows if row.event_kind == 'handoff']
    activities = [_activity_item(row) for row in activity_rows if row.event_kind not in {'policy', 'handoff'}]
    skills = [_card_item(row) for row in card_rows if row.card_type == 'skill_card']
    rules = [_card_item(row) for row in card_rows if row.card_type == 'rule_card']
    memories = [_card_item(row) for row in card_rows if row.card_type in {'memory_card', 'evidence_card', 'review_card'}]
    models = [_model_item(row) for row in usage_rows]
    context_ops = [{
        'kind': 'context_operation',
        'operation_id': row.operation_id,
        'op': row.op,
        'version': row.version,
        'status': row.status,
        'lane': row.lane,
        'commit_mode': row.commit_mode,
        'actor': row.actor,
        'created_at': _iso(row.created_at),
    } for row in context_rows]
    context_snapshots = [{
        'kind': 'context_snapshot',
        'snapshot_id': row.snapshot_id,
        'version': row.version,
        'atom_count': row.atom_count,
        'link_count': row.link_count,
        'created_at': _iso(row.created_at),
    } for row in snapshot_rows]
    context_projections = [{
        'kind': 'context_projection',
        'projection_id': row.projection_id,
        'snapshot_id': row.snapshot_id,
        'role_id': row.role_id,
        'task_type': row.task_type,
        'model_node': row.model_node,
        'cache_hit': row.cache_hit,
        'compile_ms': row.compile_ms,
        'context_tokens': row.context_tokens,
        'selected_atom_count': row.selected_atom_count,
        'selected_link_count': row.selected_link_count,
        'handoff_count': row.handoff_count,
        'created_at': _iso(row.created_at),
    } for row in projection_rows]
    context_writes = [{
        'kind': 'context_write_metric',
        'event_id': row.event_id,
        'projection_id': row.projection_id,
        'snapshot_id': row.snapshot_id,
        'status': row.status,
        'batch_size': row.batch_size,
        'committed': row.committed,
        'proposals': row.proposals,
        'conflicts': row.conflicts,
        'operation_append_ms': row.operation_append_ms,
        'created_at': _iso(row.created_at),
    } for row in write_rows]
    handoff_deltas = [{
        'kind': 'handoff_delta',
        'handoff_id': row.handoff_id,
        'from_agent': row.from_agent,
        'to_agent': row.to_agent,
        'handoff_type': row.handoff_type,
        'snapshot_id': row.snapshot_id,
        'projection_id': row.projection_id,
        'delta_tokens': row.delta_tokens,
        'summary': _short(row.summary),
        'created_at': _iso(row.created_at),
    } for row in handoff_delta_rows]

    skill_links = [row for row in link_rows if row.link_type in {'uses', 'considered_skill', 'exports_rule', 'applies_to'}]
    link_explanations = [{
        'from': row.from_card_id,
        'to': row.to_card_id,
        'type': row.link_type,
        'weight': row.weight,
        'reason': row.reason,
        'status': row.status,
        'updated_at': _iso(row.updated_at),
    } for row in skill_links[:80]]

    attention: list[dict[str, Any]] = []
    latest_policy = policies[0] if policies else None
    if latest_policy and latest_policy.get('policy', {}).get('workspace_write') not in {'', 'allowed_in_workspace', None}:
        attention.append({'severity': 'warning', 'title': 'Workspace write may be blocked', 'detail': latest_policy.get('policy', {}).get('workspace_write')})
    if latest_policy and latest_policy.get('policy', {}).get('legacy_manual_fallback') not in {'', 'disabled', None}:
        attention.append({'severity': 'warning', 'title': 'Legacy manual fallback is not disabled', 'detail': latest_policy.get('policy', {}).get('legacy_manual_fallback')})
    low_reuse = [row for row in skills if row.get('reuse_score', 0) and row.get('reuse_score', 0) < 40]
    if low_reuse:
        attention.append({'severity': 'info', 'title': 'Some active skills have low reuse score', 'detail': ', '.join(row['id'] for row in low_reuse[:3])})

    return {
        'ok': True,
        'thread_id': thread.id,
        'run_id': clean_run,
        'summary': {
            'policy_count': len(policies),
            'activity_count': len(activities),
            'handoff_count': len(handoffs),
            'skill_count': len(skills),
            'rule_count': len(rules),
            'memory_count': len(memories),
            'model_usage_count': len(models),
            'context_operation_count': len(context_ops),
            'context_snapshot_count': len(context_snapshots),
            'context_projection_count': len(context_projections),
            'context_write_batch_count': len(context_writes),
            'handoff_delta_count': len(handoff_deltas),
            'attention_count': len(attention),
        },
        'attention': attention,
        'sections': {
            'why_execution_allowed': policies[:8],
            'why_agents_interacted': {'activity_handoffs': handoffs[:12], 'typed_deltas': handoff_deltas[:12]},
            'why_skills_rules_applied': {
                'skills': sorted(skills, key=lambda row: float(row.get('reuse_score') or 0), reverse=True)[:20],
                'rules': sorted(rules, key=lambda row: float(row.get('reuse_score') or 0), reverse=True)[:20],
                'links': link_explanations,
            },
            'why_models_used': models[:20],
            'why_memory_context_used': memories[:20],
            'why_context_projected': context_projections[:20],
            'why_context_changed': { 'operations': context_ops[:20], 'write_metrics': context_writes[:20], 'snapshots': context_snapshots[:8] },
            'recent_activity': activities[:20],
        },
    }
