from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from app.models import ConversationTeamConfigRevision, Thread
from app.services.run_studio_audit_timeline import _clean_adaptive_expansion, _select_latest_team_strategy


def _jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or '')
    except Exception:
        return default


def _clean_text(value: Any, max_len: int = 256) -> str:
    return str(value or '').strip()[:max_len]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_float(value: Any) -> float | None:
    if value is None or value == '':
        return None
    try:
        return float(value)
    except Exception:
        return None


def _strategy_row(*, revision: ConversationTeamConfigRevision, payload: dict[str, Any]) -> dict[str, Any] | None:
    active_team = _as_dict(payload.get('active_team'))
    pending_team = _as_dict(payload.get('pending_team'))
    active_meta = _as_dict(active_team.get('planner_metadata') or active_team.get('plannerMetadata'))
    pending_meta = _as_dict(pending_team.get('planner_metadata') or pending_team.get('plannerMetadata'))
    active_strategy = _clean_adaptive_expansion(active_meta.get('adaptive_expansion') or active_meta.get('adaptiveExpansion') or {})
    pending_strategy = _clean_adaptive_expansion(pending_meta.get('adaptive_expansion') or pending_meta.get('adaptiveExpansion') or {})
    latest = _select_latest_team_strategy(pending_strategy, active_strategy)
    if not latest or not latest.get('recommendation'):
        return None
    source = _clean_text(latest.get('source'), 128) or ('pending_team' if latest == pending_strategy else 'active_team')
    source_team = pending_team if source.startswith('pending') else active_team
    augmentation = _as_dict(latest.get('augmentation'))
    role_separation = _as_dict(latest.get('role_separation'))
    quality = _as_dict(latest.get('quality'))
    rationale = [str(item).strip() for item in list(latest.get('rationale') or []) if str(item).strip()][:8]
    return {
        'revision_id': revision.id,
        'thread_id': revision.thread_id,
        'conversation_id': revision.conversation_id,
        'revision_kind': revision.revision_kind,
        'created_at': revision.created_at.isoformat() if revision.created_at else None,
        'status': _clean_text(payload.get('status'), 64) or None,
        'composition_mode': _clean_text(payload.get('composition_mode'), 64) or None,
        'proposal_mode': _clean_text(payload.get('proposal_mode'), 64) or None,
        'team_state': 'pending' if source.startswith('pending') else 'active',
        'team_name': _clean_text(source_team.get('team_name') or source_team.get('name'), 160) or None,
        'recommendation': _clean_text(latest.get('recommendation'), 64) or None,
        'source': source or None,
        'ts': _clean_text(latest.get('ts'), 128) or None,
        'augmentation_score': _safe_float(augmentation.get('score')),
        'role_separation_score': _safe_float(role_separation.get('score')),
        'independent_review_needed': role_separation.get('independent_review_needed') is True,
        'persistent_split_needed': role_separation.get('persistent_split_needed') is True,
        'auto_prepared_draft': latest.get('auto_prepared_draft') is True,
        'capability_gap_summary': _clean_text(latest.get('capability_gap_summary'), 256) or None,
        'rationale': rationale,
        'augmentation_reasons': [str(item).strip() for item in list(augmentation.get('reasons') or []) if str(item).strip()][:8],
        'role_separation_reasons': [str(item).strip() for item in list(role_separation.get('reasons') or []) if str(item).strip()][:8],
        'quality': {
            'quality_gap': _safe_float(quality.get('quality_gap')),
            'contradiction_pressure': _safe_float(quality.get('contradiction_pressure')),
            'followup_burden': _safe_float(quality.get('followup_burden')),
        },
    }



def build_team_strategy_dataset(session: Session, *, thread: Thread, limit: int = 200) -> dict[str, Any]:
    clean_limit = max(1, min(int(limit or 200), 1000))
    revisions = session.exec(
        select(ConversationTeamConfigRevision)
        .where(ConversationTeamConfigRevision.thread_id == thread.id)
        .order_by(ConversationTeamConfigRevision.created_at.desc())
        .limit(clean_limit)
    ).all()
    rows: list[dict[str, Any]] = []
    recommendation_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    capability_gap_counts: dict[str, int] = {}
    rationale_counts: dict[str, int] = {}
    augment_only_count = 0
    expand_team_count = 0
    auto_prepared_draft_count = 0
    independent_review_count = 0
    persistent_split_count = 0
    augmentation_score_sum = 0.0
    augmentation_score_count = 0
    role_separation_score_sum = 0.0
    role_separation_score_count = 0

    for revision in revisions:
        payload = _as_dict(_jload(revision.payload_json, {}))
        row = _strategy_row(revision=revision, payload=payload)
        if not row:
            continue
        rows.append(row)
        recommendation = _clean_text(row.get('recommendation'), 64) or 'unknown'
        source = _clean_text(row.get('source'), 128) or 'unknown'
        recommendation_counts[recommendation] = recommendation_counts.get(recommendation, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1
        if recommendation == 'augment_context':
            augment_only_count += 1
        if recommendation == 'expand_team':
            expand_team_count += 1
        if row.get('auto_prepared_draft') is True:
            auto_prepared_draft_count += 1
        if row.get('independent_review_needed') is True:
            independent_review_count += 1
        if row.get('persistent_split_needed') is True:
            persistent_split_count += 1
        gap = _clean_text(row.get('capability_gap_summary'), 256)
        if gap:
            capability_gap_counts[gap] = capability_gap_counts.get(gap, 0) + 1
        for reason in list(row.get('rationale') or []):
            clean_reason = _clean_text(reason, 128)
            if not clean_reason:
                continue
            rationale_counts[clean_reason] = rationale_counts.get(clean_reason, 0) + 1
        augmentation_score = _safe_float(row.get('augmentation_score'))
        if augmentation_score is not None:
            augmentation_score_sum += augmentation_score
            augmentation_score_count += 1
        role_separation_score = _safe_float(row.get('role_separation_score'))
        if role_separation_score is not None:
            role_separation_score_sum += role_separation_score
            role_separation_score_count += 1

    total = len(rows)
    latest = rows[0] if rows else None
    top_capability_gaps = [
        {'value': key, 'count': count}
        for key, count in sorted(capability_gap_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    ]
    top_rationales = [
        {'value': key, 'count': count}
        for key, count in sorted(rationale_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]
    return {
        'kind': 'team_strategy_dataset_v1',
        'schema_version': 1,
        'thread_id': thread.id,
        'count': total,
        'recommendation_counts': recommendation_counts,
        'source_counts': source_counts,
        'summary': {
            'augment_only_count': augment_only_count,
            'expand_team_count': expand_team_count,
            'augment_only_rate': (float(augment_only_count) / float(total) if total else 0.0),
            'expand_team_rate': (float(expand_team_count) / float(total) if total else 0.0),
            'auto_prepared_draft_count': auto_prepared_draft_count,
            'independent_review_count': independent_review_count,
            'persistent_split_count': persistent_split_count,
            'average_augmentation_score': (augmentation_score_sum / augmentation_score_count if augmentation_score_count else None),
            'average_role_separation_score': (role_separation_score_sum / role_separation_score_count if role_separation_score_count else None),
            'top_capability_gaps': top_capability_gaps,
            'top_rationales': top_rationales,
            'latest_recommendation': latest.get('recommendation') if latest else None,
            'latest_source': latest.get('source') if latest else None,
            'latest_ts': latest.get('ts') if latest else None,
        },
        'rows': rows,
    }



def serialize_team_strategy_dataset_jsonl(rows: list[dict[str, Any]] | dict[str, Any]) -> str:
    dataset = rows if isinstance(rows, dict) else {'rows': rows}
    return '\n'.join(json.dumps(row, ensure_ascii=False) for row in list(dataset.get('rows') or []))
