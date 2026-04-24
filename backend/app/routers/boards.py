from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session, select

from app.db import engine
from app.models import Node
from app.services.learning_policy import (
    is_learning_excluded_payload,
    is_promotion_candidate_payload,
    is_raw_history_payload,
)
from app.services.raw_history_candidates import sync_candidates_for_raw_history
from app.services.candidate_promotion import approve_board_candidate
from app.tenant import require_thread_access, require_thread_write_access
from app.schemas import BoardCandidateApproveRequest, ThreadRawHistoryUpsertRequest
from app.services.graph import add_edge, get_last_node
from app.services.context_versions import snapshot_context_set
from app.models import ContextSet

router = APIRouter(prefix='/api/threads', tags=['board'])



def _jdump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)



def _jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or '')
    except Exception:
        return default



def _clean_text(value: Any) -> str:
    return str(value or '').strip()



def _first_context_set(session: Session, thread_id: str) -> ContextSet | None:
    return session.exec(
        select(ContextSet)
        .where(ContextSet.thread_id == thread_id)
        .order_by(ContextSet.created_at.asc(), ContextSet.id.asc())
        .limit(1)
    ).first()



def _activate_node_in_context_set(session: Session, *, context_set: ContextSet | None, node_id: str, resource_kind: str) -> None:
    if not context_set:
        return
    try:
        active_ids = json.loads(context_set.active_node_ids_json or '[]')
    except Exception:
        active_ids = []
    if node_id in active_ids:
        return
    active_ids.append(node_id)
    context_set.active_node_ids_json = _jdump(active_ids)
    snapshot_context_set(
        session,
        context_set,
        reason='add_resource',
        changed_node_ids=[node_id],
        meta={'node_type': 'Resource', 'resource_kind': resource_kind},
    )



def _collect_tags(payload: dict[str, Any]) -> list[str]:
    raw_tags = payload.get('tags')
    out: list[str] = []
    if isinstance(raw_tags, list):
        for value in raw_tags:
            clean = _clean_text(value)
            if clean and clean not in out:
                out.append(clean)
    return out[:8]



def _payload(node: Node) -> dict[str, Any]:
    raw = _jload(node.payload_json or '{}', {})
    return raw if isinstance(raw, dict) else {}



def _card(node: Node, payload: dict[str, Any], lane_id: str) -> dict[str, Any]:
    summary = _clean_text(payload.get('summary')) or _clean_text(node.text).splitlines()[0][:220]
    preview = _clean_text(node.text)[:2000]
    return {
        'id': node.id,
        'lane_id': lane_id,
        'title': _clean_text(payload.get('name') or payload.get('title')) or f'{lane_id}:{node.id[:8]}',
        'summary': summary or None,
        'preview_text': preview or None,
        'created_at': node.created_at.isoformat() if getattr(node, 'created_at', None) else None,
        'resource_kind': _clean_text(payload.get('resource_kind')) or None,
        'source': _clean_text(payload.get('source')) or None,
        'uri': _clean_text(payload.get('uri')) or None,
        'tags': _collect_tags(payload),
        'learning_excluded': is_learning_excluded_payload(payload),
        'promotion_blocked': bool(payload.get('promotion_blocked') is True),
        'shareability': _clean_text(payload.get('shareability')) or None,
        'privacy_class': _clean_text(payload.get('privacy_class')) or None,
        'history_stream_key': _clean_text(payload.get('history_stream_key')) or None,
        'candidate_key': _clean_text(payload.get('candidate_key')) or None,
        'candidate_kind': _clean_text(payload.get('candidate_kind')) or None,
        'promotion_status': _clean_text(payload.get('promotion_status')) or None,
        'review_status': _clean_text(payload.get('review_status')) or None,
        'derived_from_history_title': _clean_text(payload.get('derived_from_history_title')) or None,
        'promoted_node_id': _clean_text(payload.get('promoted_node_id')) or None,
        'promoted_resource_kind': _clean_text(payload.get('promoted_resource_kind')) or None,
        'published_to_library': bool(payload.get('published_to_library') is True),
        'stale': bool(payload.get('stale') is True),
        'improvement_job_id': _clean_text(payload.get('improvement_job_id') or payload.get('job_id')) or None,
        'improvement_target': _clean_text(payload.get('improvement_target')) or None,
        'target_runtime': _clean_text(payload.get('target_runtime')) or None,
        'phase': _clean_text(payload.get('phase')) or None,
        'status': _clean_text(payload.get('status')) or None,
        'last_patch_status': _clean_text(payload.get('last_patch_status')) or None,
        'last_test_status': _clean_text(payload.get('last_test_status')) or None,
        'last_canary_status': _clean_text(payload.get('last_canary_status')) or None,
        'last_promotion_status': _clean_text(payload.get('last_promotion_status')) or None,
        'last_llm_trace_status': _clean_text(payload.get('last_llm_trace_status')) or None,
        'latest_reports': payload.get('latest_reports') if isinstance(payload.get('latest_reports'), dict) else None,
        'report_counts': payload.get('report_counts') if isinstance(payload.get('report_counts'), dict) else None,
        'counts': {
            'line_count': len([line for line in preview.splitlines() if line.strip()]),
            'artifact_count': len(payload.get('extracted_artifacts') or []) if isinstance(payload.get('extracted_artifacts'), list) else 0,
        },
        'payload': payload,
    }



def _lane_meta(lane_id: str) -> tuple[str, str]:
    mapping = {
        'raw_history': ('Raw history', 'Visible to users in GoC but excluded from learning/promotion.'),
        'promotion_candidates': ('Candidates', 'Structured artifacts that may be promoted after review/eval.'),
        'improvement_jobs': ('Improvement jobs', 'Self-improvement jobs created from Telegram/runtime control.'),
        'code_diffs': ('Code diffs & patch plans', 'Diff summaries and patch plans generated while iterating on forge runtimes.'),
        'code_snapshots': ('Code snapshots', 'Repository/workspace snapshots used to inspect current runtime code.'),
        'test_reports': ('Test reports', 'Automated test runs executed for improvement jobs.'),
        'canary_results': ('Canary results', 'Canary or restart validation results for forge/stable runtimes.'),
        'llm_traces': ('LLM traces', 'Redacted trace summaries for model calls captured during runtime or self-improvement jobs.'),
        'skill_packages': ('Skill packages', 'Installed or attached skill packages for this thread.'),
        'team_assets': ('Team assets', 'Thread-level team/agent blueprint resources.'),
        'other_resources': ('Other resources', 'Board-visible resources that do not fit another lane.'),
    }
    return mapping.get(lane_id, (lane_id.replace('_', ' ').title(), ''))



def _lane_order(lane_id: str) -> int:
    return {
        'raw_history': 0,
        'promotion_candidates': 1,
        'improvement_jobs': 2,
        'code_diffs': 3,
        'code_snapshots': 4,
        'test_reports': 5,
        'canary_results': 6,
        'llm_traces': 7,
        'skill_packages': 8,
        'team_assets': 9,
        'other_resources': 10,
    }.get(lane_id, 99)



def _pick_lane(payload: dict[str, Any]) -> str | None:
    kind = _clean_text(payload.get('resource_kind')).lower()
    if is_raw_history_payload(payload):
        return 'raw_history'
    if is_promotion_candidate_payload(payload):
        return 'promotion_candidates'
    if kind == 'improvement_job':
        return 'improvement_jobs'
    if kind in {'code_diff', 'repo_diff', 'patch_plan'}:
        return 'code_diffs'
    if kind in {'repo_snapshot', 'code_snapshot', 'module_index'}:
        return 'code_snapshots'
    if kind == 'test_report':
        return 'test_reports'
    if kind == 'canary_result':
        return 'canary_results'
    if kind == 'llm_trace_summary':
        return 'llm_traces'
    if kind == 'skill_package':
        return 'skill_packages'
    if kind in {'team_blueprint', 'agent_blueprint', 'team_manifest', 'harness_package'}:
        return 'team_assets'
    if payload.get('board_visible') is True:
        return 'other_resources'
    return None


@router.get('/{thread_id}/board')
def get_thread_board(
    thread_id: str,
    include_raw_history: bool = Query(default=True),
    include_other_resources: bool = Query(default=True),
    limit_per_lane: int = Query(default=24, ge=4, le=100),
):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        rows = session.exec(
            select(Node)
            .where(Node.thread_id == thread_id, Node.type == 'Resource')
            .order_by(Node.created_at.desc(), Node.id.desc())
        ).all()

        lanes: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            payload = _payload(row)
            lane_id = _pick_lane(payload)
            if not lane_id:
                continue
            if lane_id == 'raw_history' and not include_raw_history:
                continue
            if lane_id == 'other_resources' and not include_other_resources:
                continue
            lanes.setdefault(lane_id, [])
            if len(lanes[lane_id]) >= limit_per_lane:
                continue
            lanes[lane_id].append(_card(row, payload, lane_id))

        lane_items = []
        for lane_id in sorted(lanes.keys(), key=_lane_order):
            title, description = _lane_meta(lane_id)
            lane_items.append({
                'id': lane_id,
                'title': title,
                'description': description,
                'count': len(lanes[lane_id]),
                'cards': lanes[lane_id],
            })

        return {
            'ok': True,
            'thread_id': thread_id,
            'policy': {
                'raw_history_visible': True,
                'raw_history_learning_excluded': True,
                'promotion_requires_structured_artifacts': True,
                'candidate_learning_requires_review': True,
            },
            'lanes': lane_items,
            'counts': {lane['id']: lane['count'] for lane in lane_items},
        }


@router.post('/{thread_id}/raw_history')
def upsert_thread_raw_history(thread_id: str, body: ThreadRawHistoryUpsertRequest):
    with Session(engine) as session:
        thread = require_thread_write_access(session, thread_id)
        context_set = _first_context_set(session, thread.id)

        stream_key = _clean_text(body.stream_key) or _clean_text(body.uri) or _clean_text(body.chat_id) or 'default'
        existing: Node | None = None
        if body.update_latest:
            candidates = session.exec(
                select(Node)
                .where(Node.thread_id == thread.id, Node.type == 'Resource')
                .order_by(Node.created_at.desc(), Node.id.desc())
            ).all()
            for row in candidates:
                payload = _payload(row)
                if not is_raw_history_payload(payload):
                    continue
                if _clean_text(payload.get('history_stream_key')) == stream_key:
                    existing = row
                    break

        payload = {
            'name': _clean_text(body.title) or 'Runtime history',
            'resource_kind': 'raw_history',
            'summary': _clean_text(body.summary) or None,
            'source': _clean_text(body.source) or 'ddalggak',
            'context_set_id': context_set.id if context_set else None,
            'uri': _clean_text(body.uri) or None,
            'chat_id': _clean_text(body.chat_id) or None,
            'job_id': _clean_text(body.job_id) or None,
            'run_id': _clean_text(body.run_id) or None,
            'session_id': _clean_text(body.session_id) or None,
            'history_stream_key': stream_key,
            'tag': 'RESOURCE',
            'privacy_class': 'raw_history',
            'shareability': 'private_only',
            'learning_excluded': True,
            'promotion_blocked': True,
            'reuse_mode': 'view_only',
            'history_visibility': 'board_only',
            'default_context_excluded': True,
            'board_visible': True,
            'tags': [_clean_text(tag) for tag in body.tags if _clean_text(tag)][:8],
            'provenance': body.provenance or {},
            'extracted_artifacts': list(body.extracted_artifacts or [])[:24],
        }

        if existing:
            current = _payload(existing)
            current.update({key: value for key, value in payload.items() if value is not None})
            existing.text = body.raw_text
            existing.payload_json = _jdump(current)
            session.add(existing)
            if body.auto_activate:
                _activate_node_in_context_set(session, context_set=context_set, node_id=existing.id, resource_kind='raw_history')
            extraction = sync_candidates_for_raw_history(session, thread=thread, raw_history_node=existing)
            session.commit()
            session.refresh(existing)
            return {'ok': True, 'updated': True, 'node': existing.model_dump(), 'derived_candidates': extraction}

        last = get_last_node(session, thread.id)
        node = Node(
            thread_id=thread.id,
            type='Resource',
            text=body.raw_text,
            payload_json=_jdump(payload),
        )
        session.add(node)
        session.flush()
        if last and last.id != node.id:
            session.add(add_edge(thread.id, last.id, node.id, 'NEXT'))
        if body.auto_activate:
            _activate_node_in_context_set(session, context_set=context_set, node_id=node.id, resource_kind='raw_history')
        extraction = sync_candidates_for_raw_history(session, thread=thread, raw_history_node=node)
        session.commit()
        session.refresh(node)
        return {'ok': True, 'updated': False, 'node': node.model_dump(), 'derived_candidates': extraction}


@router.post('/{thread_id}/board/candidates/{candidate_node_id}/approve')
def approve_thread_board_candidate(thread_id: str, candidate_node_id: str, body: BoardCandidateApproveRequest | None = None):
    with Session(engine) as session:
        thread = require_thread_write_access(session, thread_id)
        candidate_node = session.get(Node, candidate_node_id)
        if not candidate_node or candidate_node.thread_id != thread.id:
            raise HTTPException(404, 'candidate node not found in thread')
        outcome = approve_board_candidate(
            session,
            thread=thread,
            candidate_node=candidate_node,
            publish_to_library=bool(body.publish_to_library) if body else False,
        )
        session.commit()
        session.refresh(candidate_node)
        session.refresh(outcome['promoted_node'])
        return {
            'ok': True,
            'thread_id': thread.id,
            'candidate': candidate_node.model_dump(),
            'candidate_payload': outcome['candidate_payload'],
            'promoted_node': outcome['promoted_node'].model_dump(),
            'promoted_resource_kind': outcome['promoted_resource_kind'],
            'target_thread_id': outcome['target_thread_id'],
            'published_to_library': outcome['published_to_library'],
        }
