from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException, Response
from sqlmodel import Session, select

from app.db import engine
from app.models import MemoryConflict, MemoryEdge, MemoryLifecycleEvent, MemoryNode, MemoryProjection, MemorySurface, TeamSelectionEvent, Thread, utcnow
from app.schemas import (
    MemoryConflictResolveRequest,
    MemoryEdgeCreateRequest,
    MemoryNodeCreateRequest,
    MemoryNodeTransitionRequest,
    MemoryProjectionRequest,
    MemorySurfaceCreateRequest,
    TeamRecommendationRequest,
    TeamSelectionRecordRequest,
)
from app.services.memory_graph import (
    append_conflict_history,
    build_memory_projection,
    detect_memory_conflicts,
    lifecycle_event_type_for_status,
    normalize_conflict_resolution,
    normalize_memory_edge,
    normalize_memory_surfaces,
    summarize_memory_conflict,
    summarize_memory_conflicts,
    summarize_memory_edge,
    summarize_memory_lifecycle_event,
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


def _extract_supporting_links(*payloads: dict | None) -> dict[str, list[str]]:
    claim_ids: list[str] = []
    evidence_ids: list[str] = []
    memory_ids: list[str] = []
    seen_claims: set[str] = set()
    seen_evidence: set[str] = set()
    seen_memory: set[str] = set()

    def _append_many(target: list[str], seen: set[str], values) -> None:
        for value in values or []:
            clean = str(value or '').strip()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            target.append(clean)

    for payload in payloads:
        data = payload if isinstance(payload, dict) else {}
        _append_many(claim_ids, seen_claims, data.get('supporting_claim_node_ids') or data.get('claim_node_ids'))
        _append_many(evidence_ids, seen_evidence, data.get('supporting_evidence_node_ids') or data.get('evidence_node_ids'))
        _append_many(memory_ids, seen_memory, data.get('supporting_memory_node_ids'))
    return {
        'supporting_claim_node_ids': claim_ids,
        'supporting_evidence_node_ids': evidence_ids,
        'supporting_memory_node_ids': memory_ids,
    }


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


def _record_memory_lifecycle_event(
    session: Session,
    *,
    thread_id: str,
    node: MemoryNode,
    event_type: str | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    actor: str | None = None,
    source: str | None = None,
    summary: str | None = None,
    metadata: dict | None = None,
    created_run_id: str | None = None,
):
    row = MemoryLifecycleEvent(
        thread_id=thread_id,
        node_id=node.id,
        surface_id=node.surface_id,
        event_type=event_type or lifecycle_event_type_for_status(to_status or node.status),
        from_status=(str(from_status).strip() if from_status else None),
        to_status=(str(to_status).strip() if to_status else (str(node.status).strip() if node.status else None)),
        actor=(str(actor).strip() if actor else None),
        source=(str(source).strip() if source else None),
        summary=str(summary or '').strip(),
        metadata_json=_jdump(metadata or {}),
        created_run_id=(str(created_run_id).strip() if created_run_id else (str(node.created_run_id).strip() if node.created_run_id else None)),
        created_at=utcnow(),
    )
    session.add(row)
    return row


def _upsert_memory_edge(
    session: Session,
    *,
    thread_id: str,
    edge_type: str,
    from_node: MemoryNode,
    to_node: MemoryNode,
    status: str = 'active',
    rationale: str | None = None,
    provenance: dict | None = None,
    created_run_id: str | None = None,
):
    row = session.exec(
        select(MemoryEdge).where(
            MemoryEdge.thread_id == thread_id,
            MemoryEdge.edge_type == edge_type,
            MemoryEdge.from_node_id == from_node.id,
            MemoryEdge.to_node_id == to_node.id,
        )
    ).first()
    if row is None:
        row = MemoryEdge(
            thread_id=thread_id,
            edge_type=edge_type,
            from_node_id=from_node.id,
            to_node_id=to_node.id,
        )
    row.from_surface_id = from_node.surface_id
    row.to_surface_id = to_node.surface_id
    row.status = str(status or 'active').strip() or 'active'
    row.rationale = str(rationale or '').strip()
    row.provenance_json = _jdump(provenance or {})
    row.created_run_id = str(created_run_id or from_node.created_run_id or to_node.created_run_id or '').strip() or None
    row.updated_at = utcnow()
    session.add(row)
    return row


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

        _record_memory_lifecycle_event(
            session,
            thread_id=thread.id,
            node=row,
            event_type=lifecycle_event_type_for_status(row.status),
            to_status=row.status,
            actor=row.owner_role_id or row.owner_agent_id or 'runtime',
            source='memory_node_create',
            summary=f"Node {row.id} created on surface {row.surface_id} as {row.status}",
            metadata={
                **_extract_supporting_links(body.provenance if isinstance(body.provenance, dict) else {}),
                'supporting_memory_node_ids': [row.id],
            },
            created_run_id=row.created_run_id,
        )

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
            for conflict in created_conflicts:
                left_node = session.get(MemoryNode, conflict.left_node_id)
                right_node = session.get(MemoryNode, conflict.right_node_id)
                if left_node and right_node:
                    contradiction_links = _extract_supporting_links(
                        _jload(left_node.provenance_json, {}),
                        _jload(right_node.provenance_json, {}),
                    )
                    contradiction = _upsert_memory_edge(
                        session,
                        thread_id=thread.id,
                        edge_type='contradicts',
                        from_node=left_node,
                        to_node=right_node,
                        rationale=conflict.reason or 'Detected conflicting memory nodes',
                        provenance={
                            'related_conflict_ids': [conflict.id],
                            **contradiction_links,
                            'supporting_memory_node_ids': [left_node.id, right_node.id],
                        },
                        created_run_id=row.created_run_id or left_node.created_run_id or right_node.created_run_id,
                    )
                    for target in (left_node, right_node):
                        previous_status = str(target.status or 'draft').strip() or 'draft'
                        if previous_status not in {'quarantined', 'superseded'}:
                            target.status = 'conflicted'
                            target.updated_at = utcnow()
                            _record_memory_lifecycle_event(
                                session,
                                thread_id=thread.id,
                                node=target,
                                event_type='node_conflicted',
                                from_status=previous_status,
                                to_status='conflicted',
                                actor='memory_conflict_detector',
                                source='memory_conflict_detector',
                                summary=f"Node {target.id} entered conflicted state",
                                metadata={
                                    'related_conflict_ids': [conflict.id],
                                    'related_edge_ids': [contradiction.id],
                                    **contradiction_links,
                                    'supporting_memory_node_ids': [left_node.id, right_node.id],
                                },
                                created_run_id=target.created_run_id or row.created_run_id,
                            )
                    if row.id in {left_node.id, right_node.id}:
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


@router.post('/threads/{thread_id}/memory/edges')
def create_memory_edge(thread_id: str, body: MemoryEdgeCreateRequest):
    with Session(engine) as session:
        thread = require_thread_write_access(session, thread_id)
        payload = normalize_memory_edge(body.model_dump() if hasattr(body, 'model_dump') else body.dict())
        from_node_id = str(payload.get('from_node_id') or '').strip()
        to_node_id = str(payload.get('to_node_id') or '').strip()
        if not from_node_id or not to_node_id:
            raise HTTPException(400, 'memory edge requires from_node_id and to_node_id')
        from_node = session.get(MemoryNode, from_node_id)
        to_node = session.get(MemoryNode, to_node_id)
        if not from_node or not to_node:
            raise HTTPException(400, 'memory edge references missing memory node')
        if from_node.thread_id != thread.id or to_node.thread_id != thread.id:
            raise HTTPException(400, 'memory edge nodes must belong to the thread')
        row = session.exec(
            select(MemoryEdge).where(
                MemoryEdge.thread_id == thread.id,
                MemoryEdge.edge_type == payload['edge_type'],
                MemoryEdge.from_node_id == from_node_id,
                MemoryEdge.to_node_id == to_node_id,
            )
        ).first()
        if row is None:
            row = MemoryEdge(
                thread_id=thread.id,
                edge_type=payload['edge_type'],
                from_node_id=from_node_id,
                to_node_id=to_node_id,
            )
        row.from_surface_id = from_node.surface_id
        row.to_surface_id = to_node.surface_id
        row.status = str(payload.get('status') or 'active').strip() or 'active'
        row.rationale = str(payload.get('rationale') or '').strip()
        row.provenance_json = _jdump(payload.get('provenance') or {})
        row.created_run_id = str(payload.get('created_run_id') or from_node.created_run_id or to_node.created_run_id or '').strip() or None
        row.updated_at = utcnow()
        session.add(row)
        _invalidate_thread_projections(session, thread.id)
        session.commit()
        session.refresh(row)
        node_lookup = {
            from_node.id: {
                'id': from_node.id,
                'node_type': from_node.node_type,
                'owner_role_id': from_node.owner_role_id,
                'content_json': _jload(from_node.content_json, {}),
                'provenance_json': _jload(from_node.provenance_json, {}),
            },
            to_node.id: {
                'id': to_node.id,
                'node_type': to_node.node_type,
                'owner_role_id': to_node.owner_role_id,
                'content_json': _jload(to_node.content_json, {}),
                'provenance_json': _jload(to_node.provenance_json, {}),
            },
        }
        return {'edge': summarize_memory_edge({
            'id': row.id,
            'edge_type': row.edge_type,
            'from_node_id': row.from_node_id,
            'to_node_id': row.to_node_id,
            'from_surface_id': row.from_surface_id,
            'to_surface_id': row.to_surface_id,
            'status': row.status,
            'rationale': row.rationale,
            'provenance_json': _jload(row.provenance_json, {}),
            'created_run_id': row.created_run_id,
            'created_at': row.created_at,
            'updated_at': row.updated_at,
        }, node_lookup=node_lookup)}


@router.get('/threads/{thread_id}/memory/edges')
def list_memory_edges(thread_id: str, run_id: str | None = None, node_id: str | None = None, limit: int = 40):
    clean_limit = max(1, min(int(limit or 40), 200))
    clean_run_id = str(run_id or '').strip() or None
    clean_node_id = str(node_id or '').strip() or None
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        statement = select(MemoryEdge).where(MemoryEdge.thread_id == thread.id)
        if clean_run_id:
            statement = statement.where(MemoryEdge.created_run_id == clean_run_id)
        rows = session.exec(statement.order_by(MemoryEdge.updated_at.desc()).limit(clean_limit)).all()
        if clean_node_id:
            rows = [row for row in rows if row.from_node_id == clean_node_id or row.to_node_id == clean_node_id]
        node_ids = {row.from_node_id for row in rows} | {row.to_node_id for row in rows}
        node_rows = session.exec(select(MemoryNode).where(MemoryNode.thread_id == thread.id)).all()
        node_lookup = {
            row.id: {
                'id': row.id,
                'node_type': row.node_type,
                'owner_role_id': row.owner_role_id,
                'content_json': _jload(row.content_json, {}),
                'provenance_json': _jload(row.provenance_json, {}),
            }
            for row in node_rows if row.id in node_ids
        }
        items = [summarize_memory_edge({
            'id': row.id,
            'edge_type': row.edge_type,
            'from_node_id': row.from_node_id,
            'to_node_id': row.to_node_id,
            'from_surface_id': row.from_surface_id,
            'to_surface_id': row.to_surface_id,
            'status': row.status,
            'rationale': row.rationale,
            'provenance_json': _jload(row.provenance_json, {}),
            'created_run_id': row.created_run_id,
            'created_at': row.created_at,
            'updated_at': row.updated_at,
        }, node_lookup=node_lookup) for row in rows]
        type_counts: dict[str, int] = {}
        for item in items:
            key = str(item.get('edge_type') or 'related_to')
            type_counts[key] = type_counts.get(key, 0) + 1
        return {'items': items, 'count': len(items), 'type_counts': type_counts}


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


@router.post('/threads/{thread_id}/memory/nodes/{node_id}/transition')
def transition_memory_node(thread_id: str, node_id: str, body: MemoryNodeTransitionRequest):
    with Session(engine) as session:
        thread = require_thread_write_access(session, thread_id)
        node = session.get(MemoryNode, node_id)
        if not node or node.thread_id != thread.id:
            raise HTTPException(404, 'memory node not found')
        to_status = str(body.to_status or '').strip()
        if not to_status:
            raise HTTPException(400, 'to_status is required')
        previous_status = str(node.status or 'draft').strip() or 'draft'
        node.status = to_status
        node.updated_at = utcnow()
        transition_payload = body.event_metadata if isinstance(body.event_metadata, dict) else {}
        transition_links = _extract_supporting_links(transition_payload, _jload(node.provenance_json, {}))
        related_edge_ids: list[str] = []
        published_from_id = str(body.published_from_node_id or '').strip()
        if published_from_id:
            source_node = session.get(MemoryNode, published_from_id)
            if not source_node or source_node.thread_id != thread.id:
                raise HTTPException(400, 'published_from_node_id must reference a memory node in the thread')
            published_edge = _upsert_memory_edge(
                session,
                thread_id=thread.id,
                edge_type='published_from',
                from_node=source_node,
                to_node=node,
                rationale=body.summary or f'Published node {node.id} from {source_node.id}',
                provenance={**transition_links, 'supporting_memory_node_ids': [source_node.id, node.id]},
                created_run_id=body.created_run_id or node.created_run_id or source_node.created_run_id,
            )
            related_edge_ids.append(published_edge.id)
        supersedes_ids = [str(item).strip() for item in (body.supersedes_node_ids or []) if str(item).strip()]
        for losing_id in supersedes_ids:
            losing_node = session.get(MemoryNode, losing_id)
            if not losing_node or losing_node.thread_id != thread.id:
                raise HTTPException(400, f'invalid supersedes node: {losing_id}')
            supersedes_edge = _upsert_memory_edge(
                session,
                thread_id=thread.id,
                edge_type='supersedes',
                from_node=node,
                to_node=losing_node,
                rationale=body.summary or f'Node {node.id} supersedes {losing_node.id}',
                provenance={**transition_links, 'supporting_memory_node_ids': [node.id, losing_node.id]},
                created_run_id=body.created_run_id or node.created_run_id or losing_node.created_run_id,
            )
            related_edge_ids.append(supersedes_edge.id)
        _record_memory_lifecycle_event(
            session,
            thread_id=thread.id,
            node=node,
            event_type=lifecycle_event_type_for_status(to_status),
            from_status=previous_status,
            to_status=to_status,
            actor=body.actor or node.owner_role_id or node.owner_agent_id or 'operator',
            source=body.source or 'memory_node_transition',
            summary=body.summary or f'Node {node.id} moved from {previous_status} to {to_status}',
            metadata={
                **transition_payload,
                **transition_links,
                'related_edge_ids': related_edge_ids,
                'supporting_memory_node_ids': [node.id, *supersedes_ids, *([published_from_id] if published_from_id else [])],
            },
            created_run_id=body.created_run_id or node.created_run_id,
        )
        _invalidate_thread_projections(session, thread.id)
        session.add(node)
        session.commit()
        session.refresh(node)
        return {'node': {'id': node.id, 'surface_id': node.surface_id, 'node_type': node.node_type, 'status': node.status}, 'related_edge_ids': related_edge_ids}


@router.get('/threads/{thread_id}/memory/lifecycle-events')
def list_memory_lifecycle_events(thread_id: str, run_id: str | None = None, node_id: str | None = None, limit: int = 50):
    clean_limit = max(1, min(int(limit or 50), 200))
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        statement = select(MemoryLifecycleEvent).where(MemoryLifecycleEvent.thread_id == thread.id)
        if run_id and str(run_id).strip():
            statement = statement.where(MemoryLifecycleEvent.created_run_id == str(run_id).strip())
        if node_id and str(node_id).strip():
            statement = statement.where(MemoryLifecycleEvent.node_id == str(node_id).strip())
        rows = session.exec(statement.order_by(MemoryLifecycleEvent.created_at.desc()).limit(clean_limit)).all()
        items = [summarize_memory_lifecycle_event({
            'id': row.id,
            'thread_id': row.thread_id,
            'node_id': row.node_id,
            'surface_id': row.surface_id,
            'event_type': row.event_type,
            'from_status': row.from_status,
            'to_status': row.to_status,
            'actor': row.actor,
            'source': row.source,
            'summary': row.summary,
            'metadata_json': _jload(row.metadata_json, {}),
            'created_run_id': row.created_run_id,
            'created_at': row.created_at.isoformat() if row.created_at else None,
        }) for row in rows]
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
        related_edge_ids: list[str] = []
        if winner:
            winner_previous_status = str(winner.status or 'draft').strip() or 'draft'
            if row.status in {'resolved', 'accepted', 'merged'}:
                winner.status = 'published'
            elif row.status == 'quarantined':
                winner.status = 'quarantined'
            winner.updated_at = utcnow()
            _record_memory_lifecycle_event(
                session,
                thread_id=thread.id,
                node=winner,
                event_type=lifecycle_event_type_for_status(winner.status),
                from_status=winner_previous_status,
                to_status=winner.status,
                actor=resolution.get('resolved_by') or 'operator',
                source=resolution.get('resolution_source') or 'operator_ui',
                summary=resolution.get('summary') or f'Conflict {row.id} selected node {winner.id}',
                metadata={
                    'related_conflict_ids': [row.id],
                    'rationale_codes': resolution.get('rationale_codes') or [],
                    'supporting_claim_node_ids': resolution.get('supporting_claim_node_ids') or [],
                    'supporting_evidence_node_ids': resolution.get('supporting_evidence_node_ids') or [],
                    'supporting_memory_node_ids': resolution.get('supporting_memory_node_ids') or [winner.id, *list(losing_ids)],
                },
                created_run_id=winner.created_run_id,
            )
        for node_id in losing_ids:
            node = session.get(MemoryNode, node_id)
            if not node:
                raise HTTPException(400, f'losing node not found: {node_id}')
            if node.thread_id != thread.id:
                raise HTTPException(400, 'losing node does not belong to the conflict thread')
            previous_status = str(node.status or 'draft').strip() or 'draft'
            node.status = 'quarantined' if row.status == 'quarantined' else 'superseded'
            node.updated_at = utcnow()
            _record_memory_lifecycle_event(
                session,
                thread_id=thread.id,
                node=node,
                event_type=lifecycle_event_type_for_status(node.status),
                from_status=previous_status,
                to_status=node.status,
                actor=resolution.get('resolved_by') or 'operator',
                source=resolution.get('resolution_source') or 'operator_ui',
                summary=resolution.get('summary') or f'Conflict {row.id} marked node {node.id} as {node.status}',
                metadata={
                    'related_conflict_ids': [row.id],
                    'winning_node_id': winner.id if winner else None,
                    'rationale_codes': resolution.get('rationale_codes') or [],
                    'supporting_claim_node_ids': resolution.get('supporting_claim_node_ids') or [],
                    'supporting_evidence_node_ids': resolution.get('supporting_evidence_node_ids') or [],
                    'supporting_memory_node_ids': resolution.get('supporting_memory_node_ids') or ([winner.id] if winner else []) + [node.id],
                },
                created_run_id=node.created_run_id,
            )
            if winner and row.status in {'resolved', 'accepted', 'merged'}:
                edge = _upsert_memory_edge(
                    session,
                    thread_id=thread.id,
                    edge_type='supersedes',
                    from_node=winner,
                    to_node=node,
                    rationale=resolution.get('summary') or f'Node {winner.id} supersedes {node.id}',
                    provenance={
                        'related_conflict_ids': [row.id],
                        'supporting_claim_node_ids': resolution.get('supporting_claim_node_ids') or [],
                        'evidence_node_ids': resolution.get('supporting_evidence_node_ids') or [],
                        'supporting_memory_node_ids': resolution.get('supporting_memory_node_ids') or [winner.id, node.id],
                    },
                    created_run_id=winner.created_run_id or node.created_run_id,
                )
                related_edge_ids.append(edge.id)
        if winner and related_edge_ids:
            _record_memory_lifecycle_event(
                session,
                thread_id=thread.id,
                node=winner,
                event_type='node_updated',
                from_status=winner.status,
                to_status=winner.status,
                actor=resolution.get('resolved_by') or 'operator',
                source='memory_conflict_resolution',
                summary=f'Conflict {row.id} generated supersession edges',
                metadata={
                    'related_conflict_ids': [row.id],
                    'related_edge_ids': related_edge_ids,
                    'supporting_claim_node_ids': resolution.get('supporting_claim_node_ids') or [],
                    'supporting_evidence_node_ids': resolution.get('supporting_evidence_node_ids') or [],
                    'supporting_memory_node_ids': [winner.id, *list(losing_ids)],
                },
                created_run_id=winner.created_run_id,
            )
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
