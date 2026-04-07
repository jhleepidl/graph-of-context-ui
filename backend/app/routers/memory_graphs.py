from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException, Response
from sqlmodel import Session, select

from app.db import engine
from app.models import MemoryConflict, MemoryNode, MemoryProjection, MemorySurface, TeamSelectionEvent, Thread, utcnow
from app.schemas import (
    MemoryConflictResolveRequest,
    MemoryNodeCreateRequest,
    MemoryProjectionRequest,
    MemorySurfaceCreateRequest,
    TeamRecommendationRequest,
    TeamSelectionRecordRequest,
)
from app.services.memory_graph import (
    append_conflict_history,
    build_memory_projection,
    detect_memory_conflicts,
    normalize_conflict_resolution,
    normalize_memory_surfaces,
    summarize_memory_conflict,
    summarize_memory_conflicts,
    summarize_memory_projection,
)
from app.services.team_recommender import build_team_selection_dataset, recommend_team_blueprints, serialize_team_selection_dataset_jsonl
from app.tenant import require_thread_access, require_thread_write_access

router = APIRouter(prefix='/api', tags=['memory_graph'])


def _jdump(value):
    return json.dumps(value, ensure_ascii=False)


def _jload(raw, default):
    try:
        return json.loads(raw or '')
    except Exception:
        return default


def _active_conflict_node_ids(session: Session, thread_id: str) -> set[str]:
    rows = session.exec(
        select(MemoryConflict).where(
            MemoryConflict.thread_id == thread_id,
            MemoryConflict.status == 'pending',
        )
    ).all()
    node_ids: set[str] = set()
    for row in rows:
        if row.left_node_id:
            node_ids.add(row.left_node_id)
        if row.right_node_id:
            node_ids.add(row.right_node_id)
    return node_ids


def _invalidate_thread_projections(session: Session, thread_id: str) -> None:
    rows = session.exec(select(MemoryProjection).where(MemoryProjection.thread_id == thread_id)).all()
    for row in rows:
        session.delete(row)



@router.post('/threads/{thread_id}/memory/surfaces')
def create_memory_surface(thread_id: str, body: MemorySurfaceCreateRequest):
    with Session(engine) as session:
        thread = require_thread_write_access(session, thread_id)
        normalized_rows = normalize_memory_surfaces([body.model_dump() if hasattr(body, 'model_dump') else body.dict()])
        if not normalized_rows:
            raise HTTPException(400, 'invalid memory surface payload')
        payload = normalized_rows[0]
        row = session.exec(
            select(MemorySurface).where(
                MemorySurface.thread_id == thread.id,
                MemorySurface.surface_id == payload['surface_id'],
            )
        ).first()
        if row is None:
            row = MemorySurface(
                thread_id=thread.id,
                surface_id=payload['surface_id'],
            )
        row.title = payload['title']
        row.semantic_kind = payload['semantic_kind']
        row.visibility_scope = payload['visibility_scope']
        row.write_mode = payload['write_mode']
        row.policy_json = _jdump(payload.get('policy') or {})
        row.updated_at = utcnow()
        session.add(row)
        _invalidate_thread_projections(session, thread.id)
        session.commit()
        session.refresh(row)
        return {'surface': {'id': row.id, 'surface_id': row.surface_id, 'title': row.title, 'semantic_kind': row.semantic_kind, 'visibility_scope': row.visibility_scope, 'write_mode': row.write_mode}}


@router.post('/threads/{thread_id}/memory/nodes')
def create_memory_node(thread_id: str, body: MemoryNodeCreateRequest):
    with Session(engine) as session:
        thread = require_thread_write_access(session, thread_id)
        surface_id = str(body.surface_id).strip()
        surface = session.exec(
            select(MemorySurface).where(
                MemorySurface.thread_id == thread.id,
                MemorySurface.surface_id == surface_id,
            )
        ).first()
        if surface is None:
            raise HTTPException(400, 'memory surface does not exist for thread')
        row = MemoryNode(
            thread_id=thread.id,
            surface_id=surface_id,
            node_type=str(body.node_type or 'note').strip() or 'note',
            owner_agent_id=(str(body.owner_agent_id).strip() if body.owner_agent_id else None),
            owner_role_id=(str(body.owner_role_id).strip() if body.owner_role_id else None),
            content_json=_jdump(body.content or {}),
            provenance_json=_jdump(body.provenance or {}),
            trust_tier=str(body.trust_tier or 'derived').strip() or 'derived',
            status=str(body.status or 'draft').strip() or 'draft',
            created_run_id=(str(body.created_run_id).strip() if body.created_run_id else None),
            updated_at=utcnow(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)

        existing_nodes = session.exec(
            select(MemoryNode).where(
                MemoryNode.thread_id == thread.id,
                MemoryNode.surface_id == row.surface_id,
            )
        ).all()
        existing_conflicts = session.exec(
            select(MemoryConflict).where(
                MemoryConflict.thread_id == thread.id,
                MemoryConflict.surface_id == row.surface_id,
            )
        ).all()
        conflict_specs = detect_memory_conflicts(
            new_node={
                'id': row.id,
                'surface_id': row.surface_id,
                'node_type': row.node_type,
                'content': _jload(row.content_json, {}),
                'provenance': _jload(row.provenance_json, {}),
                'trust_tier': row.trust_tier,
                'status': row.status,
            },
            existing_nodes=[
                {
                    'id': node.id,
                    'surface_id': node.surface_id,
                    'node_type': node.node_type,
                    'content': _jload(node.content_json, {}),
                    'provenance': _jload(node.provenance_json, {}),
                    'trust_tier': node.trust_tier,
                    'status': node.status,
                }
                for node in existing_nodes
            ],
            existing_conflicts=[
                {
                    'left_node_id': conflict.left_node_id,
                    'right_node_id': conflict.right_node_id,
                    'status': conflict.status,
                }
                for conflict in existing_conflicts
            ],
        )
        created_conflicts: list[MemoryConflict] = []
        conflicted_node_ids: set[str] = set()
        for spec in conflict_specs:
            left_node_id, right_node_id = sorted([spec['left_node_id'], spec['right_node_id']])
            existing_conflict = session.exec(
                select(MemoryConflict).where(
                    MemoryConflict.thread_id == thread.id,
                    MemoryConflict.surface_id == spec['surface_id'],
                    MemoryConflict.left_node_id == left_node_id,
                    MemoryConflict.right_node_id == right_node_id,
                )
            ).first()
            if existing_conflict is not None:
                continue
            resolution_payload = append_conflict_history({
                'conflict_key': spec.get('conflict_key'),
                'left_signature': spec.get('left_signature'),
                'right_signature': spec.get('right_signature'),
                'left_trust_tier': spec.get('left_trust_tier'),
                'right_trust_tier': spec.get('right_trust_tier'),
                'left_confidence': spec.get('left_confidence'),
                'right_confidence': spec.get('right_confidence'),
                'left_provenance_fingerprint': spec.get('left_provenance_fingerprint'),
                'right_provenance_fingerprint': spec.get('right_provenance_fingerprint'),
            }, {
                'event_type': 'conflict_detected',
                'status': spec.get('status') or 'pending',
                'summary': f"Detected conflict between {left_node_id} and {right_node_id}",
                'source': 'memory_conflict_detector',
                'supporting_memory_node_ids': [left_node_id, right_node_id],
            })
            conflict = MemoryConflict(
                thread_id=thread.id,
                surface_id=spec['surface_id'],
                left_node_id=left_node_id,
                right_node_id=right_node_id,
                status=spec['status'],
                reason=spec['reason'],
                resolution_json=_jdump(resolution_payload),
                updated_at=utcnow(),
            )
            session.add(conflict)
            created_conflicts.append(conflict)
            conflicted_node_ids.update({left_node_id, right_node_id})
        if created_conflicts:
            for conflicted_node_id in conflicted_node_ids:
                conflicted_node = session.get(MemoryNode, conflicted_node_id)
                if conflicted_node and conflicted_node.status not in {'quarantined', 'superseded'}:
                    conflicted_node.status = 'conflicted'
                    conflicted_node.updated_at = utcnow()
            row.status = 'conflicted'
        _invalidate_thread_projections(session, thread.id)
        session.commit()
        for conflict in created_conflicts:
            session.refresh(conflict)
        session.refresh(row)
        return {
            'node': {'id': row.id, 'surface_id': row.surface_id, 'node_type': row.node_type, 'status': row.status},
            'conflicts': [summarize_memory_conflict({'id': conflict.id, 'surface_id': conflict.surface_id, 'left_node_id': conflict.left_node_id, 'right_node_id': conflict.right_node_id, 'status': conflict.status, 'reason': conflict.reason, 'resolution_json': _jload(conflict.resolution_json, {})}) for conflict in created_conflicts],
        }


@router.post('/threads/{thread_id}/memory/project')
def project_memory(thread_id: str, body: MemoryProjectionRequest):
    with Session(engine) as session:
        thread = require_thread_write_access(session, thread_id)
        surfaces = session.exec(select(MemorySurface).where(MemorySurface.thread_id == thread.id)).all()
        nodes = session.exec(select(MemoryNode).where(MemoryNode.thread_id == thread.id)).all()
        unresolved_conflict_node_ids = _active_conflict_node_ids(session, thread.id)
        projection = build_memory_projection(
            role_id=body.role_id,
            agent_id=body.agent_id,
            surfaces=[{'surface_id': row.surface_id, 'title': row.title, 'semantic_kind': row.semantic_kind, 'visibility_scope': row.visibility_scope, 'write_mode': row.write_mode, 'policy': _jload(row.policy_json, {})} for row in surfaces],
            nodes=[{
                'id': row.id,
                'surface_id': row.surface_id,
                'node_type': row.node_type,
                'status': row.status,
                'trust_tier': row.trust_tier,
                'owner_agent_id': row.owner_agent_id,
                'owner_role_id': row.owner_role_id,
                'created_run_id': row.created_run_id,
                'content_json': _jload(row.content_json, {}),
                'provenance_json': _jload(row.provenance_json, {}),
            } for row in nodes],
            include_surface_ids=body.include_surface_ids or [],
            exclude_surface_ids=body.exclude_surface_ids or [],
            unresolved_conflict_node_ids=sorted(unresolved_conflict_node_ids),
        )
        summary = summarize_memory_projection(projection)
        projection_meta = {
            **summary,
            'visible_surface_ids': projection.get('visible_surface_ids') or [],
            'blocked_surface_ids': projection.get('blocked_surface_ids') or [],
            'surface_reason_map': projection.get('surface_reason_map') or {},
            'node_reason_map': projection.get('node_reason_map') or {},
        }
        saved = MemoryProjection(
            thread_id=thread.id,
            run_id=(str(body.run_id).strip() if body.run_id else None),
            agent_id=(str(body.agent_id).strip() if body.agent_id else None),
            role_id=(str(body.role_id).strip() if body.role_id else None),
            visible_node_ids_json=_jdump(projection['visible_node_ids']),
            blocked_node_ids_json=_jdump(projection['blocked_node_ids']),
            summary_json=_jdump(projection_meta),
        )
        session.add(saved)
        session.commit()
        session.refresh(saved)
        return {'projection_id': saved.id, 'projection': projection, 'summary': summary}


@router.get('/threads/{thread_id}/memory/projections')
def list_memory_projections(thread_id: str, run_id: str | None = None, limit: int = 12):
    clean_limit = max(1, min(int(limit or 12), 50))
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        statement = select(MemoryProjection).where(MemoryProjection.thread_id == thread.id)
        if run_id and str(run_id).strip():
            statement = statement.where(MemoryProjection.run_id == str(run_id).strip())
        rows = session.exec(statement.order_by(MemoryProjection.created_at.desc()).limit(clean_limit)).all()
        node_map = {row.id: row for row in session.exec(select(MemoryNode).where(MemoryNode.thread_id == thread.id)).all()}
        items = []
        for row in rows:
            summary = _jload(row.summary_json, {})
            visible_node_ids = _jload(row.visible_node_ids_json, [])
            blocked_node_ids = _jload(row.blocked_node_ids_json, [])
            surface_reason_map = summary.get('surface_reason_map') or {}
            node_reason_map = summary.get('node_reason_map') or {}
            def _node_detail(node_id: str, *, blocked: bool = False):
                node = node_map.get(node_id)
                if not node:
                    return {'node_id': node_id, 'blocked_reason': 'missing'} if blocked else {'node_id': node_id}
                content = _jload(node.content_json, {})
                provenance = _jload(node.provenance_json, {})
                preview = ''
                if isinstance(content, dict):
                    for key in ('claim', 'value', 'text', 'summary', 'decision', 'answer', 'note'):
                        value = str(content.get(key) or '').strip()
                        if value:
                            preview = value[:160]
                            break
                    if not preview:
                        preview = json.dumps(content, ensure_ascii=False, sort_keys=True)[:160]
                else:
                    preview = str(content or '')[:160]
                detail = {
                    'node_id': node.id,
                    'surface_id': node.surface_id,
                    'node_type': node.node_type,
                    'status': node.status,
                    'trust_tier': node.trust_tier,
                    'confidence': provenance.get('confidence') or provenance.get('confidence_score') or content.get('confidence') or content.get('confidence_score') or 0,
                    'owner_agent_id': node.owner_agent_id,
                    'owner_role_id': node.owner_role_id,
                    'created_run_id': node.created_run_id,
                    'content_preview': preview,
                    'provenance_fingerprint': (provenance.get('source_id') or provenance.get('document_id') or provenance.get('url') or provenance.get('entity') or provenance.get('topic')),
                }
                if blocked:
                    detail['blocked_reason'] = node_reason_map.get(node.id) or surface_reason_map.get(node.surface_id) or 'surface_not_visible'
                else:
                    detail['visibility_reason'] = node_reason_map.get(node.id) or 'visible'
                return detail
            items.append({
                'projection_id': row.id,
                'run_id': row.run_id,
                'agent_id': row.agent_id,
                'role_id': row.role_id,
                'summary': summary,
                'visible_surface_ids': summary.get('visible_surface_ids') or [],
                'blocked_surface_ids': summary.get('blocked_surface_ids') or [],
                'visible_node_ids': visible_node_ids,
                'blocked_node_ids': blocked_node_ids,
                'visible_nodes': [_node_detail(node_id) for node_id in visible_node_ids],
                'blocked_nodes': [_node_detail(node_id, blocked=True) for node_id in blocked_node_ids],
                'created_at': row.created_at.isoformat() if row.created_at else None,
            })
        return {'items': items, 'count': len(items)}


@router.get('/threads/{thread_id}/memory/conflicts')
def list_memory_conflicts(thread_id: str, status: str | None = None, surface_id: str | None = None, limit: int = 30):
    clean_limit = max(1, min(int(limit or 30), 100))
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        statement = select(MemoryConflict).where(MemoryConflict.thread_id == thread.id)
        if status and str(status).strip():
            statement = statement.where(MemoryConflict.status == str(status).strip())
        if surface_id and str(surface_id).strip():
            statement = statement.where(MemoryConflict.surface_id == str(surface_id).strip())
        rows = session.exec(statement.order_by(MemoryConflict.updated_at.desc()).limit(clean_limit)).all()
        summary = summarize_memory_conflicts([
            {
                'id': row.id,
                'surface_id': row.surface_id,
                'left_node_id': row.left_node_id,
                'right_node_id': row.right_node_id,
                'status': row.status,
                'reason': row.reason,
                'resolution_json': _jload(row.resolution_json, {}),
            }
            for row in rows
        ])
        return summary


@router.post('/memory/conflicts/{conflict_id}/resolve')
def resolve_memory_conflict(conflict_id: str, body: MemoryConflictResolveRequest):
    with Session(engine) as session:
        row = session.get(MemoryConflict, conflict_id)
        if not row:
            raise HTTPException(404, 'memory conflict not found')
        thread = require_thread_write_access(session, row.thread_id)
        resolution = normalize_conflict_resolution(body.model_dump() if hasattr(body, 'model_dump') else body.dict())
        previous_status = str(row.status or 'pending').strip() or 'pending'
        row.status = resolution['status'] or 'resolved'
        current_resolution = _jload(row.resolution_json, {})
        current_resolution.update({k: v for k, v in resolution.items() if v not in (None, [], '')})
        event_type = 'conflict_merged' if row.status == 'merged' else 'conflict_quarantined' if row.status == 'quarantined' else 'conflict_reopened' if row.status == 'pending' else 'conflict_resolved'
        current_resolution = append_conflict_history(current_resolution, {
            'event_type': event_type,
            'status': row.status,
            'previous_status': previous_status,
            'actor': resolution.get('resolved_by') or 'operator',
            'source': resolution.get('resolution_source') or 'operator_ui',
            'summary': resolution.get('summary') or f"Updated conflict {row.id} from {previous_status} to {row.status}",
            'merge_note': resolution.get('merge_note'),
            'winning_node_id': resolution.get('winning_node_id'),
            'losing_node_ids': resolution.get('losing_node_ids') or [],
            'rationale_codes': resolution.get('rationale_codes') or [],
            'supporting_claim_node_ids': resolution.get('supporting_claim_node_ids') or [],
            'supporting_evidence_node_ids': resolution.get('supporting_evidence_node_ids') or [],
            'supporting_memory_node_ids': resolution.get('supporting_memory_node_ids') or [],
        })
        row.resolution_json = _jdump(current_resolution)
        row.updated_at = utcnow()

        conflict_node_ids = {row.left_node_id, row.right_node_id}
        winner_id = resolution.get('winning_node_id')
        losing_ids = set(resolution.get('losing_node_ids') or [])
        mentioned_node_ids = {node_id for node_id in [winner_id, *list(losing_ids)] if node_id}
        if mentioned_node_ids and not mentioned_node_ids.issubset(conflict_node_ids):
            raise HTTPException(400, 'resolution references node ids outside the conflict pair')
        if winner_id and not losing_ids:
            losing_ids = conflict_node_ids - {winner_id}
        winner = session.get(MemoryNode, winner_id) if winner_id else None
        if winner is not None and winner.thread_id != thread.id:
            raise HTTPException(400, 'winning node does not belong to the conflict thread')
        if winner:
            if row.status in {'resolved', 'accepted', 'merged'}:
                winner.status = 'published'
            elif row.status == 'quarantined':
                winner.status = 'quarantined'
            winner.updated_at = utcnow()
        for node_id in losing_ids:
            node = session.get(MemoryNode, node_id)
            if not node:
                raise HTTPException(400, f'losing node not found: {node_id}')
            if node.thread_id != thread.id:
                raise HTTPException(400, 'losing node does not belong to the conflict thread')
            node.status = 'quarantined' if row.status == 'quarantined' else 'superseded'
            node.updated_at = utcnow()
        _invalidate_thread_projections(session, thread.id)
        session.add(row)
        session.commit()
        session.refresh(row)
        return {'conflict': summarize_memory_conflict({'id': row.id, 'surface_id': row.surface_id, 'left_node_id': row.left_node_id, 'right_node_id': row.right_node_id, 'status': row.status, 'reason': row.reason, 'resolution_json': _jload(row.resolution_json, {})})}


@router.post('/team/recommend')
def recommend_team(body: TeamRecommendationRequest):
    return recommend_team_blueprints(body.task_text, limit=max(1, min(int(body.limit or 3), 8)))


@router.post('/threads/{thread_id}/team-selection-events')
def record_team_selection(thread_id: str, body: TeamSelectionRecordRequest):
    with Session(engine) as session:
        thread = require_thread_write_access(session, thread_id)
        recommendation = _jload(_jdump(body.recommendation or {}), {})
        selected_blueprint_id = (str(body.selected_blueprint_id).strip() if body.selected_blueprint_id else None)
        if selected_blueprint_id and not recommendation.get('selected_candidate_snapshot'):
            candidates = [item for item in recommendation.get('candidates') or [] if isinstance(item, dict)]
            selected_candidate = next((item for item in candidates if str(item.get('template_id') or item.get('blueprint_id') or '').strip() == selected_blueprint_id), None)
            if selected_candidate:
                recommendation['selected_candidate_snapshot'] = selected_candidate
        row = TeamSelectionEvent(
            thread_id=thread.id,
            run_id=(str(body.run_id).strip() if body.run_id else None),
            task_text=str(body.task_text or '').strip(),
            selected_blueprint_id=selected_blueprint_id,
            recommendation_json=_jdump(recommendation),
            outcome_json=_jdump(body.outcome or {}),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return {'event_id': row.id, 'thread_id': row.thread_id, 'selected_blueprint_id': row.selected_blueprint_id}


@router.get('/threads/{thread_id}/team-selection-events/export')
def export_team_selection_dataset(thread_id: str, limit: int = 200, format: str | None = None):
    clean_limit = max(1, min(int(limit or 200), 1000))
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        rows = session.exec(
            select(TeamSelectionEvent)
            .where(TeamSelectionEvent.thread_id == thread.id)
            .order_by(TeamSelectionEvent.created_at.desc())
            .limit(clean_limit)
        ).all()
        events = [
            {
                'id': row.id,
                'thread_id': row.thread_id,
                'run_id': row.run_id,
                'task_text': row.task_text,
                'selected_blueprint_id': row.selected_blueprint_id,
                'recommendation': _jload(row.recommendation_json, {}),
                'outcome': _jload(row.outcome_json, {}),
                'created_at': row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
        dataset = build_team_selection_dataset(events)
        if str(format or '').strip().lower() == 'jsonl':
            return Response(serialize_team_selection_dataset_jsonl(events), media_type='application/x-ndjson')
        return dataset
