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
    build_memory_projection,
    detect_memory_conflicts,
    normalize_conflict_resolution,
    normalize_memory_surfaces,
    summarize_memory_conflict,
    summarize_memory_conflicts,
    summarize_memory_projection,
)
from app.services.team_recommender import build_team_selection_dataset, recommend_team_blueprints, serialize_team_selection_dataset_jsonl
from app.tenant import require_thread_access

router = APIRouter(prefix='/api', tags=['memory_graph'])


def _jdump(value):
    return json.dumps(value, ensure_ascii=False)


def _jload(raw, default):
    try:
        return json.loads(raw or '')
    except Exception:
        return default


@router.post('/threads/{thread_id}/memory/surfaces')
def create_memory_surface(thread_id: str, body: MemorySurfaceCreateRequest):
    with Session(engine) as session:
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, 'thread not found')
        require_thread_access(thread)
        normalized_rows = normalize_memory_surfaces([body.model_dump() if hasattr(body, 'model_dump') else body.dict()])
        if not normalized_rows:
            raise HTTPException(400, 'invalid memory surface payload')
        payload = normalized_rows[0]
        row = MemorySurface(
            thread_id=thread.id,
            surface_id=payload['surface_id'],
            title=payload['title'],
            semantic_kind=payload['semantic_kind'],
            visibility_scope=payload['visibility_scope'],
            write_mode=payload['write_mode'],
            policy_json=_jdump(payload.get('policy') or {}),
            updated_at=utcnow(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return {'surface': {'id': row.id, 'surface_id': row.surface_id, 'title': row.title, 'semantic_kind': row.semantic_kind, 'visibility_scope': row.visibility_scope, 'write_mode': row.write_mode}}


@router.post('/threads/{thread_id}/memory/nodes')
def create_memory_node(thread_id: str, body: MemoryNodeCreateRequest):
    with Session(engine) as session:
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, 'thread not found')
        require_thread_access(thread)
        row = MemoryNode(
            thread_id=thread.id,
            surface_id=str(body.surface_id).strip(),
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
            },
            existing_nodes=[
                {
                    'id': node.id,
                    'surface_id': node.surface_id,
                    'node_type': node.node_type,
                    'content': _jload(node.content_json, {}),
                    'provenance': _jload(node.provenance_json, {}),
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
        for spec in conflict_specs:
            conflict = MemoryConflict(
                thread_id=thread.id,
                surface_id=spec['surface_id'],
                left_node_id=spec['left_node_id'],
                right_node_id=spec['right_node_id'],
                status=spec['status'],
                reason=spec['reason'],
                resolution_json=_jdump({
                    'conflict_key': spec.get('conflict_key'),
                    'left_signature': spec.get('left_signature'),
                    'right_signature': spec.get('right_signature'),
                    'left_trust_tier': spec.get('left_trust_tier'),
                    'right_trust_tier': spec.get('right_trust_tier'),
                    'left_confidence': spec.get('left_confidence'),
                    'right_confidence': spec.get('right_confidence'),
                    'left_provenance_fingerprint': spec.get('left_provenance_fingerprint'),
                    'right_provenance_fingerprint': spec.get('right_provenance_fingerprint'),
                }),
                updated_at=utcnow(),
            )
            session.add(conflict)
            created_conflicts.append(conflict)
        if created_conflicts:
            row.status = 'conflicted'
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
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, 'thread not found')
        require_thread_access(thread)
        surfaces = session.exec(select(MemorySurface).where(MemorySurface.thread_id == thread.id)).all()
        nodes = session.exec(select(MemoryNode).where(MemoryNode.thread_id == thread.id)).all()
        projection = build_memory_projection(
            role_id=body.role_id,
            agent_id=body.agent_id,
            surfaces=[{'surface_id': row.surface_id, 'title': row.title, 'semantic_kind': row.semantic_kind, 'visibility_scope': row.visibility_scope, 'write_mode': row.write_mode, 'target_roles': _jload(row.policy_json, {}).get('target_roles', [])} for row in surfaces],
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
        )
        summary = summarize_memory_projection(projection)
        projection_meta = {
            **summary,
            'visible_surface_ids': projection.get('visible_surface_ids') or [],
            'blocked_surface_ids': projection.get('blocked_surface_ids') or [],
            'surface_reason_map': projection.get('surface_reason_map') or {},
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
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, 'thread not found')
        require_thread_access(thread)
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
                    detail['blocked_reason'] = surface_reason_map.get(node.surface_id) or 'surface_not_visible'
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
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, 'thread not found')
        require_thread_access(thread)
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
        thread = session.get(Thread, row.thread_id)
        if not thread:
            raise HTTPException(404, 'thread not found')
        require_thread_access(thread)
        resolution = normalize_conflict_resolution(body.model_dump() if hasattr(body, 'model_dump') else body.dict())
        row.status = resolution['status'] or 'resolved'
        current_resolution = _jload(row.resolution_json, {})
        current_resolution.update({k: v for k, v in resolution.items() if v not in (None, [], '')})
        row.resolution_json = _jdump(current_resolution)
        row.updated_at = utcnow()

        winner_id = resolution.get('winning_node_id')
        losing_ids = set(resolution.get('losing_node_ids') or [])
        if winner_id:
            winner = session.get(MemoryNode, winner_id)
            if winner:
                winner.status = 'published' if row.status in {'resolved', 'accepted', 'merged'} else winner.status
                winner.updated_at = utcnow()
        for node_id in losing_ids:
            node = session.get(MemoryNode, node_id)
            if not node:
                continue
            node.status = 'quarantined' if row.status == 'quarantined' else 'superseded'
            node.updated_at = utcnow()
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
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, 'thread not found')
        require_thread_access(thread)
        row = TeamSelectionEvent(
            thread_id=thread.id,
            run_id=(str(body.run_id).strip() if body.run_id else None),
            task_text=str(body.task_text or '').strip(),
            selected_blueprint_id=(str(body.selected_blueprint_id).strip() if body.selected_blueprint_id else None),
            recommendation_json=_jdump(body.recommendation or {}),
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
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, 'thread not found')
        require_thread_access(thread)
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
