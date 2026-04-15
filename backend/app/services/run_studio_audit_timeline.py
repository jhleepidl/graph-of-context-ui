from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.models import Edge, MemoryConflict, MemoryEdge, MemoryLifecycleEvent, MemoryNode, Node, Thread
from app.services.memory_graph import summarize_memory_edge, summarize_memory_lifecycle_event


def build_run_studio_audit_timeline_impl(
    session: Session,
    *,
    thread: Thread,
    context_set_id: str | None = None,
    run_id: str | None = None,
    evidence: dict[str, Any] | None = None,
    memory_graph: dict[str, Any] | None = None,
    trace_scope: dict[str, Any] | None = None,
    cross_references: dict[str, Any] | None = None,
    projection_retrieval: dict[str, Any] | None = None,
    nodes: list[Node] | None = None,
    edges: list[Edge] | None = None,
    _build_run_bundle_cross_references=None,
    _clean_node_ids=None,
    _clean_text=None,
    _graph_or_load=None,
    _iso_or_none=None,
    _jload=None,
    _latest_team_selection_event=None,
    _node_payload=None,
    _push_timeline_event=None,
    _resolve_context_set=None,
    _scope_graph_for_run=None,
    _short_text=None,
    _team_selection_event_payload=None,
    _timeline_event_sort_key=None,
    build_run_studio_evidence=None,
    build_run_studio_memory_graph=None,
    build_run_studio_projection_retrieval=None,
    build_run_studio_trace_scope=None,
) -> dict[str, Any]:
    clean_run_id = str(run_id or '').strip() or None
    context_set = _resolve_context_set(session, thread_id=thread.id, context_set_id=context_set_id) if context_set_id is not None else None
    evidence_obj = evidence or build_run_studio_evidence(
        session,
        thread=thread,
        context_set_id=getattr(context_set, 'id', None),
        run_id=clean_run_id,
        nodes=nodes,
        edges=edges,
    )
    memory_obj = memory_graph or build_run_studio_memory_graph(session, thread=thread, run_id=clean_run_id)
    trace_obj = trace_scope or build_run_studio_trace_scope(
        session,
        thread=thread,
        run_id=clean_run_id,
        nodes=nodes,
        edges=edges,
    )
    cross_obj = cross_references or _build_run_bundle_cross_references(
        evidence=evidence_obj,
        memory_graph=memory_obj,
        trace_scope=trace_obj,
    )
    retrieval_obj = projection_retrieval or build_run_studio_projection_retrieval(
        session,
        thread=thread,
        run_id=clean_run_id,
        memory_graph=memory_obj,
        nodes=nodes,
        edges=edges,
    )

    nodes, edges = _graph_or_load(session, thread_id=thread.id, nodes=nodes, edges=edges)
    scoped_nodes, _ = _scope_graph_for_run(nodes=nodes, edges=edges, run_id=clean_run_id)
    node_by_id = {str(getattr(node, 'id', '') or ''): node for node in scoped_nodes if str(getattr(node, 'id', '') or '').strip()}
    memory_node_map = {row.id: row for row in session.exec(select(MemoryNode).where(MemoryNode.thread_id == thread.id)).all()}

    selection_event = _latest_team_selection_event(session, thread_id=thread.id, run_id=clean_run_id)
    selection_payload = _team_selection_event_payload(selection_event)

    claim_link_by_id = {
        str(item.get('claim_node_id') or '').strip(): item
        for item in (cross_obj.get('claim_links') or [])
        if str(item.get('claim_node_id') or '').strip()
    }
    memory_link_by_id = {
        str(item.get('memory_node_id') or '').strip(): item
        for item in (cross_obj.get('memory_links') or [])
        if str(item.get('memory_node_id') or '').strip()
    }
    conflict_link_by_id = {
        str(item.get('conflict_id') or '').strip(): item
        for item in (cross_obj.get('conflict_links') or [])
        if str(item.get('conflict_id') or '').strip()
    }
    edge_link_by_id = {
        str(item.get('edge_id') or '').strip(): item
        for item in (cross_obj.get('edge_links') or [])
        if str(item.get('edge_id') or '').strip()
    }

    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    if selection_event and selection_payload:
        alignment = str(selection_payload.get('recommendation_alignment') or '').strip() or None
        success = selection_payload.get('success') is True
        summary_parts: list[str] = []
        if selection_payload.get('selected_blueprint_id'):
            summary_parts.append(f"selected {selection_payload.get('selected_blueprint_id')}")
        if alignment:
            summary_parts.append(f"alignment {alignment}")
        if isinstance(selection_payload.get('top_recommended_candidate'), dict):
            top_candidate_id = str(selection_payload['top_recommended_candidate'].get('template_id') or selection_payload['top_recommended_candidate'].get('blueprint_id') or '').strip()
            if top_candidate_id:
                summary_parts.append(f"top recommendation {top_candidate_id}")
        _push_timeline_event(items, seen, {
            'event_id': f"selection:{selection_event.id}",
            'timestamp': _iso_or_none(selection_event.created_at),
            'category': 'selection',
            'title': 'Team selection recorded',
            'summary': '; '.join(summary_parts) or (_short_text(selection_event.task_text, 220) if selection_event.task_text else 'Team selection event stored for this run.'),
            'status': 'success' if success else 'failure',
            'run_id': clean_run_id or selection_event.run_id,
            'selection_event_id': selection_event.id,
            'primary_node_id': None,
            'related_node_ids': [],
            'trace_node_ids': [],
            'rationale_codes': [alignment] if alignment else [],
            'badges': [
                *([f"selected: {selection_payload.get('selected_blueprint_id')}"] if selection_payload.get('selected_blueprint_id') else []),
                *([f"alignment: {alignment}"] if alignment else []),
                f"success: {'yes' if success else 'no'}",
            ],
            'metadata': {
                'task_text': selection_payload.get('task_text'),
                'selected_blueprint_id': selection_payload.get('selected_blueprint_id'),
                'top_recommended_candidate': (selection_payload.get('top_recommended_candidate') or {}).get('template_id') if isinstance(selection_payload.get('top_recommended_candidate'), dict) else None,
                'recommendation_gap': selection_payload.get('recommendation_gap'),
                'artifact_quality': selection_payload.get('artifact_quality'),
            },
        })

    retrieval_summary = dict(retrieval_obj.get('summary') or {})
    retrieval_items = list(retrieval_obj.get('items') or [])
    retrieval_timestamp = (
        _iso_or_none(selection_event.created_at) if selection_event and selection_event.created_at else None
    )
    if not retrieval_timestamp and trace_obj.get('run_node_id') and trace_obj.get('run_node_id') in node_by_id:
        retrieval_timestamp = _iso_or_none(getattr(node_by_id[trace_obj.get('run_node_id')], 'created_at', None))
    if not retrieval_timestamp and (memory_obj.get('projections') or []):
        retrieval_timestamp = _iso_or_none((memory_obj.get('projections') or [])[0].get('created_at'))
    _push_timeline_event(items, seen, {
        'event_id': f"projection-retrieval:{clean_run_id or thread.id}:summary",
        'timestamp': retrieval_timestamp,
        'category': 'projection_retrieval',
        'title': 'Projection retrieval evaluated',
        'summary': _short_text(str(retrieval_summary.get('coverage_note') or 'Projection retrieval coverage was evaluated for the focused run.'), 240),
        'status': str(retrieval_summary.get('status') or 'partial'),
        'run_id': clean_run_id,
        'badges': [
            *([f"context: {retrieval_summary.get('context_source')}"] if retrieval_summary.get('context_source') else []),
            f"roles: {retrieval_obj.get('counts', {}).get('roles', 0)}",
            f"authoritative: {retrieval_obj.get('counts', {}).get('authoritative_roles', 0)}",
            *([f"planner/system: {retrieval_obj.get('counts', {}).get('planner_system_authoritative_roles', 0)}/{retrieval_obj.get('counts', {}).get('planner_system_roles', 0)}"] if retrieval_obj.get('counts', {}).get('planner_system_roles', 0) else []),
        ],
        'metadata': {
            'projection_authoritative': retrieval_summary.get('projection_authoritative'),
            'scope_first_ready': retrieval_summary.get('scope_first_ready'),
            'scope_projection_note': retrieval_summary.get('scope_projection_note'),
            'counts': retrieval_obj.get('counts') or {},
        },
    })
    for entry in retrieval_items:
        role_label = _clean_text(entry.get('display_label') or entry.get('role_id')) or 'runtime agent'
        _push_timeline_event(items, seen, {
            'event_id': f"projection-retrieval:{clean_run_id or thread.id}:{_clean_text(entry.get('runtime_instance_id')) or _clean_text(entry.get('role_id')) or role_label}",
            'timestamp': _iso_or_none(entry.get('projection_created_at')) or retrieval_timestamp,
            'category': 'projection_retrieval',
            'title': f"Retrieval coverage for {role_label}",
            'summary': _short_text(str(entry.get('selection_summary') or f"status={entry.get('status')} · visible={entry.get('visible_node_count', 0)} · blocked={entry.get('blocked_node_count', 0)}"), 240),
            'status': str(entry.get('status') or 'planned_only'),
            'run_id': clean_run_id,
            'related_node_ids': _clean_node_ids([entry.get('projection_id')]),
            'trace_node_ids': [],
            'badges': [
                *([f"role: {entry.get('role_id')}"] if entry.get('role_id') else []),
                f"visible: {entry.get('visible_node_count', 0)}",
                f"blocked: {entry.get('blocked_node_count', 0)}",
                *( ['authoritative'] if entry.get('projection_authoritative') else [] ),
                *( ['planner/system'] if any(token in str(entry.get('role_id') or '').lower() for token in ('planner', 'operator', 'system', 'supervisor', 'router')) else [] ),
            ],
            'metadata': {
                'scope_id': entry.get('scope_id'),
                'grant_labels': entry.get('grant_labels') or [],
                'active_node_count': entry.get('active_node_count'),
                'visible_surface_ids': entry.get('visible_surface_ids') or [],
                'blocked_surface_ids': entry.get('blocked_surface_ids') or [],
                'fallback_reason': entry.get('fallback_reason'),
            },
        })

    run_node_id = str(trace_obj.get('run_node_id') or '').strip() or None
    if run_node_id and run_node_id in node_by_id:
        run_node = node_by_id[run_node_id]
        run_payload = _node_payload(run_node)
        _push_timeline_event(items, seen, {
            'event_id': f"run:{run_node_id}",
            'timestamp': _iso_or_none(getattr(run_node, 'created_at', None)),
            'category': 'run',
            'title': str(run_payload.get('title') or run_payload.get('goal') or run_payload.get('task') or run_node.text or 'Run started').strip() or 'Run started',
            'summary': _short_text(str(run_payload.get('task') or run_payload.get('goal') or run_node.text or 'Runtime execution began for the focused run.'), 240),
            'status': str(run_payload.get('status') or '').strip() or None,
            'run_id': clean_run_id or run_node_id,
            'primary_node_id': run_node_id,
            'related_node_ids': [run_node_id],
            'trace_node_ids': [run_node_id],
            'badges': [
                *([f"status: {run_payload.get('status')}"] if run_payload.get('status') else []),
                *([f"goal: {_short_text(str(run_payload.get('goal') or ''), 72)}"] if run_payload.get('goal') else []),
            ],
            'metadata': {
                'selection_source': run_payload.get('selection_source'),
                'task': run_payload.get('task'),
                'goal': run_payload.get('goal'),
            },
        })

    for step_id in trace_obj.get('step_node_ids') or []:
        node = node_by_id.get(str(step_id))
        if not node:
            continue
        payload = _node_payload(node)
        status = str(payload.get('status') or '').strip() or None
        title = str(payload.get('title') or payload.get('goal') or node.text or step_id).strip() or step_id
        _push_timeline_event(items, seen, {
            'event_id': f"step:{node.id}",
            'timestamp': _iso_or_none(getattr(node, 'created_at', None)),
            'category': 'step',
            'title': title,
            'summary': _short_text(str(payload.get('goal') or payload.get('description') or node.text or ''), 220) or 'Step executed in the focused run.',
            'status': status,
            'run_id': clean_run_id,
            'primary_node_id': node.id,
            'related_node_ids': [node.id],
            'trace_node_ids': [node.id],
            'badges': [
                *([f"status: {status}"] if status else []),
                *([f"agent: {payload.get('agent_id')}"] if payload.get('agent_id') else []),
            ],
            'metadata': {
                'agent_id': payload.get('agent_id'),
                'role_id': payload.get('role_id'),
                'blocked_reason': payload.get('blocked_reason'),
                'error': payload.get('error') or payload.get('error_message'),
            },
        })

    for item in evidence_obj.get('items') or []:
        claim_node_id = str(item.get('claim_node_id') or '').strip()
        if not claim_node_id:
            continue
        claim_node = node_by_id.get(claim_node_id)
        claim_link = claim_link_by_id.get(claim_node_id) or {}
        evidence_nodes = [row for row in (item.get('evidence_nodes') or []) if isinstance(row, dict)]
        claim_text = str(item.get('claim_text') or (claim_node.text if claim_node else '') or '').strip()
        related_node_ids = _clean_node_ids([
            claim_node_id,
            *[row.get('id') for row in evidence_nodes],
            *(item.get('related_node_ids') or []),
            *(claim_link.get('related_memory_node_ids') or []),
        ])
        _push_timeline_event(items, seen, {
            'event_id': f"claim:{claim_node_id}",
            'timestamp': _iso_or_none(getattr(claim_node, 'created_at', None)),
            'category': 'evidence',
            'title': str(item.get('claim_node_type') or 'Claim').strip() or 'Claim',
            'summary': _short_text(claim_text, 240) or 'Claim or decision node recorded in the focused run.',
            'status': 'selected' if item.get('selected_in_context') else None,
            'run_id': clean_run_id,
            'claim_node_id': claim_node_id,
            'primary_node_id': claim_node_id,
            'related_node_ids': related_node_ids,
            'trace_node_ids': related_node_ids,
            'trace_anchor_related': bool(claim_link.get('trace_anchor_related')),
            'badges': [
                f"evidence: {len(evidence_nodes)}",
                *([f"memory links: {len(claim_link.get('related_memory_node_ids') or [])}"] if claim_link.get('related_memory_node_ids') else []),
                *([f"edges: {len(claim_link.get('related_memory_edge_ids') or [])}"] if claim_link.get('related_memory_edge_ids') else []),
                *([f"conflicts: {len(claim_link.get('related_conflict_ids') or [])}"] if claim_link.get('related_conflict_ids') else []),
                *([f"lifecycle: {len(claim_link.get('related_lifecycle_event_ids') or [])}"] if claim_link.get('related_lifecycle_event_ids') else []),
                *( ['anchor-related'] if claim_link.get('trace_anchor_related') else [] ),
            ],
            'metadata': {
                'provenance': item.get('provenance') or [],
                'uncertainty_notes': item.get('uncertainty_notes') or [],
                'evidence_node_ids': [row.get('id') for row in evidence_nodes if row.get('id')],
                'related_memory_edge_ids': claim_link.get('related_memory_edge_ids') or [],
                'related_lifecycle_event_ids': claim_link.get('related_lifecycle_event_ids') or [],
            },
        })

    for projection in memory_obj.get('projections') or []:
        projection_id = str(projection.get('projection_id') or '').strip()
        timestamp = _iso_or_none(projection.get('created_at'))
        role_id = str(projection.get('role_id') or projection.get('agent_id') or 'unknown').strip() or 'unknown'
        related_projection_nodes = _clean_node_ids([*(projection.get('visible_node_ids') or []), *(projection.get('blocked_node_ids') or [])])
        _push_timeline_event(items, seen, {
            'event_id': f"projection:{projection_id or role_id}:{timestamp or 'unknown'}",
            'timestamp': timestamp,
            'category': 'memory_projection',
            'title': f"Projection computed for {role_id}",
            'summary': f"visible nodes: {len(projection.get('visible_node_ids') or [])}; blocked nodes: {len(projection.get('blocked_node_ids') or [])}",
            'status': 'computed',
            'run_id': clean_run_id or projection.get('run_id'),
            'projection_id': projection_id or None,
            'primary_node_id': None,
            'related_node_ids': related_projection_nodes,
            'trace_node_ids': related_projection_nodes,
            'badges': [f"role: {role_id}", f"visible: {len(projection.get('visible_node_ids') or [])}", f"blocked: {len(projection.get('blocked_node_ids') or [])}"],
            'metadata': {
                'visible_surface_ids': projection.get('visible_surface_ids') or [],
                'blocked_surface_ids': projection.get('blocked_surface_ids') or [],
            },
        })

    memory_event_ids: set[str] = set()
    for projection in memory_obj.get('projections') or []:
        for node_entry in (projection.get('visible_nodes') or []) + (projection.get('blocked_nodes') or []):
            node_id = str(node_entry.get('node_id') or '').strip()
            if not node_id or node_id in memory_event_ids:
                continue
            memory_event_ids.add(node_id)
            memory_row = memory_node_map.get(node_id)
            memory_link = memory_link_by_id.get(node_id) or {}
            is_blocked = bool(node_entry.get('blocked_reason'))
            related_node_ids = _clean_node_ids([node_id, *(memory_link.get('related_claim_node_ids') or []), *(memory_link.get('related_conflict_ids') or [])])
            summary = str(node_entry.get('content_preview') or '').strip() or 'Memory node recorded for the focused run.'
            if is_blocked and node_entry.get('blocked_reason'):
                summary = f"{summary} Blocked because {node_entry.get('blocked_reason')}."
            _push_timeline_event(items, seen, {
                'event_id': f"memory:{node_id}",
                'timestamp': _iso_or_none(getattr(memory_row, 'created_at', None)),
                'category': 'memory',
                'title': str(node_entry.get('node_type') or 'Memory node').strip() or 'Memory node',
                'summary': _short_text(summary, 240),
                'status': str(node_entry.get('status') or '').strip() or ('blocked' if is_blocked else 'visible'),
                'run_id': clean_run_id or str(node_entry.get('created_run_id') or '').strip() or None,
                'memory_node_id': node_id,
                'primary_node_id': node_id,
                'related_node_ids': related_node_ids,
                'trace_node_ids': related_node_ids,
                'trace_anchor_related': bool(memory_link.get('trace_anchor_related')),
                'badges': [
                    *([f"surface: {node_entry.get('surface_id')}"] if node_entry.get('surface_id') else []),
                    *([f"trust: {node_entry.get('trust_tier')}"] if node_entry.get('trust_tier') else []),
                    *([f"claims: {len(memory_link.get('related_claim_node_ids') or [])}"] if memory_link.get('related_claim_node_ids') else []),
                    *([f"edges: {len(memory_link.get('related_edge_ids') or [])}"] if memory_link.get('related_edge_ids') else []),
                    *([f"conflicts: {len(memory_link.get('related_conflict_ids') or [])}"] if memory_link.get('related_conflict_ids') else []),
                    *( ['anchor-related'] if memory_link.get('trace_anchor_related') else [] ),
                ],
                'metadata': {
                    'surface_id': node_entry.get('surface_id'),
                    'visibility_reason': node_entry.get('visibility_reason'),
                    'blocked_reason': node_entry.get('blocked_reason'),
                    'owner_role_id': node_entry.get('owner_role_id'),
                    'owner_agent_id': node_entry.get('owner_agent_id'),
                    'confidence': node_entry.get('confidence'),
                    'provenance_fingerprint': node_entry.get('provenance_fingerprint'),
                    'related_edge_ids': memory_link.get('related_edge_ids') or [],
                },
            })

    edge_rows = session.exec(select(MemoryEdge).where(MemoryEdge.thread_id == thread.id).order_by(MemoryEdge.created_at.asc())).all()
    if clean_run_id:
        allowed_node_ids = {row.id for row in memory_node_map.values() if str(getattr(row, 'created_run_id', '') or '').strip() == clean_run_id}
        edge_rows = [
            row for row in edge_rows
            if row.from_node_id in allowed_node_ids or row.to_node_id in allowed_node_ids or str(getattr(row, 'created_run_id', '') or '').strip() == clean_run_id
        ]
    for row in edge_rows:
        edge_link = edge_link_by_id.get(row.id) or {}
        summary = summarize_memory_edge({
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
        }, node_lookup={
            node_id: {
                'id': node.id,
                'node_type': node.node_type,
                'owner_role_id': node.owner_role_id,
                'content_json': _jload(node.content_json, {}),
                'provenance_json': _jload(node.provenance_json, {}),
            }
            for node_id, node in memory_node_map.items()
        })
        related_node_ids = _clean_node_ids([
            row.from_node_id,
            row.to_node_id,
            *(summary.get('evidence_node_ids') or []),
            *(summary.get('supporting_claim_node_ids') or []),
            *(summary.get('supporting_memory_node_ids') or []),
        ])
        _push_timeline_event(items, seen, {
            'event_id': f"memory-edge:{row.id}",
            'timestamp': _iso_or_none(row.created_at),
            'category': 'memory_edge',
            'title': summary.get('edge_type_title') or 'Memory edge',
            'summary': _short_text(str(summary.get('rationale') or f"{summary.get('from_node_id')} → {summary.get('to_node_id')}"), 240),
            'status': str(summary.get('status') or 'active'),
            'run_id': clean_run_id or row.created_run_id,
            'primary_node_id': row.from_node_id,
            'related_node_ids': related_node_ids,
            'trace_node_ids': related_node_ids,
            'badges': [
                f"type: {summary.get('edge_type')}",
                *([f"from: {summary.get('from_node_id')}"] if summary.get('from_node_id') else []),
                *([f"to: {summary.get('to_node_id')}"] if summary.get('to_node_id') else []),
                *([f"claims: {len(edge_link.get('related_claim_node_ids') or [])}"] if edge_link.get('related_claim_node_ids') else []),
                *([f"conflicts: {len(edge_link.get('related_conflict_ids') or [])}"] if edge_link.get('related_conflict_ids') else []),
                *( ['anchor-related'] if edge_link.get('trace_anchor_related') else [] ),
            ],
            'trace_anchor_related': bool(edge_link.get('trace_anchor_related')),
            'metadata': {
                'edge_id': summary.get('id'),
                'edge_type': summary.get('edge_type'),
                'from_node_id': summary.get('from_node_id'),
                'to_node_id': summary.get('to_node_id'),
                'provenance_fingerprint': summary.get('provenance_fingerprint'),
                'supporting_claim_node_ids': summary.get('supporting_claim_node_ids') or [],
                'supporting_memory_node_ids': summary.get('supporting_memory_node_ids') or [],
                'evidence_node_ids': summary.get('evidence_node_ids') or [],
                'related_claim_node_ids': edge_link.get('related_claim_node_ids') or [],
                'related_conflict_ids': edge_link.get('related_conflict_ids') or [],
            },
        })

    lifecycle_rows = session.exec(select(MemoryLifecycleEvent).where(MemoryLifecycleEvent.thread_id == thread.id).order_by(MemoryLifecycleEvent.created_at.asc())).all()
    if clean_run_id:
        allowed_node_ids = {row.id for row in memory_node_map.values() if str(getattr(row, 'created_run_id', '') or '').strip() == clean_run_id}
        lifecycle_rows = [
            row for row in lifecycle_rows
            if row.node_id in allowed_node_ids or str(getattr(row, 'created_run_id', '') or '').strip() == clean_run_id
        ]
    for row in lifecycle_rows:
        summary = summarize_memory_lifecycle_event({
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
            'created_at': row.created_at,
        })
        metadata = summary.get('metadata') or {}
        related_node_ids = _clean_node_ids([summary.get('node_id'), *(summary.get('supporting_memory_node_ids') or [])])
        _push_timeline_event(items, seen, {
            'event_id': f"memory-lifecycle:{row.id}",
            'timestamp': _iso_or_none(row.created_at),
            'category': 'memory_lifecycle',
            'title': summary.get('event_title') or 'Memory lifecycle event',
            'summary': _short_text(str(summary.get('summary') or f"Node {summary.get('node_id')} transitioned to {summary.get('to_status') or summary.get('event_type')}"), 240),
            'status': str(summary.get('to_status') or summary.get('event_type') or ''),
            'run_id': clean_run_id or row.created_run_id,
            'primary_node_id': summary.get('node_id'),
            'related_node_ids': related_node_ids,
            'trace_node_ids': related_node_ids,
            'badges': [
                *([f"from: {summary.get('from_status')}"] if summary.get('from_status') else []),
                *([f"to: {summary.get('to_status')}"] if summary.get('to_status') else []),
                *([f"actor: {summary.get('actor')}"] if summary.get('actor') else []),
                *([f"edges: {len(summary.get('related_edge_ids') or [])}"] if summary.get('related_edge_ids') else []),
                *([f"conflicts: {len(summary.get('related_conflict_ids') or [])}"] if summary.get('related_conflict_ids') else []),
                *([f"claims: {len(summary.get('supporting_claim_node_ids') or [])}"] if summary.get('supporting_claim_node_ids') else []),
                *([f"evidence: {len(summary.get('supporting_evidence_node_ids') or [])}"] if summary.get('supporting_evidence_node_ids') else []),
            ],
            'metadata': {
                'node_id': summary.get('node_id'),
                'surface_id': summary.get('surface_id'),
                'event_type': summary.get('event_type'),
                'from_status': summary.get('from_status'),
                'to_status': summary.get('to_status'),
                'related_edge_ids': summary.get('related_edge_ids') or [],
                'related_conflict_ids': summary.get('related_conflict_ids') or [],
                'supporting_memory_node_ids': summary.get('supporting_memory_node_ids') or [],
                'supporting_claim_node_ids': summary.get('supporting_claim_node_ids') or [],
                'supporting_evidence_node_ids': summary.get('supporting_evidence_node_ids') or [],
                **({k: v for k, v in metadata.items() if k not in {'related_edge_ids', 'related_conflict_ids', 'supporting_memory_node_ids', 'supporting_claim_node_ids', 'supporting_evidence_node_ids'}}),
            },
        })

    conflict_rows = session.exec(select(MemoryConflict).where(MemoryConflict.thread_id == thread.id).order_by(MemoryConflict.created_at.asc())).all()
    if clean_run_id:
        allowed_node_ids = {row.id for row in memory_node_map.values() if str(getattr(row, 'created_run_id', '') or '').strip() == clean_run_id}
        conflict_rows = [row for row in conflict_rows if row.left_node_id in allowed_node_ids or row.right_node_id in allowed_node_ids]

    for row in conflict_rows:
        conflict_entry = conflict_link_by_id.get(row.id) or {}
        node_ids = _clean_node_ids([row.left_node_id, row.right_node_id, *(conflict_entry.get('related_claim_node_ids') or [])])
        _push_timeline_event(items, seen, {
            'event_id': f"conflict:{row.id}:detected",
            'timestamp': _iso_or_none(row.created_at),
            'category': 'conflict',
            'title': 'Memory conflict detected',
            'summary': _short_text(str(row.reason or conflict_entry.get('reason') or 'Conflicting memory nodes were detected.'), 240),
            'status': str(row.status or conflict_entry.get('status') or 'pending').strip() or 'pending',
            'run_id': clean_run_id,
            'conflict_id': row.id,
            'primary_node_id': row.left_node_id,
            'related_node_ids': node_ids,
            'trace_node_ids': node_ids,
            'trace_anchor_related': bool(conflict_entry.get('trace_anchor_related')),
            'badges': [
                *([f"reason: {row.reason}"] if row.reason else []),
                *([f"claims: {len(conflict_entry.get('related_claim_node_ids') or [])}"] if conflict_entry.get('related_claim_node_ids') else []),
                *([f"edges: {len(conflict_entry.get('related_edge_ids') or [])}"] if conflict_entry.get('related_edge_ids') else []),
                *( ['anchor-related'] if conflict_entry.get('trace_anchor_related') else [] ),
            ],
            'metadata': {'surface_id': row.surface_id, 'left_node_id': row.left_node_id, 'right_node_id': row.right_node_id, 'related_edge_ids': conflict_entry.get('related_edge_ids') or []},
        })
        history_items: list[tuple[str, dict[str, Any]]] = []
        for history_event in conflict_entry.get('history') or []:
            if isinstance(history_event, dict):
                history_items.append(('conflict', history_event))
        for merge_event in conflict_entry.get('merge_history') or []:
            if isinstance(merge_event, dict):
                history_items.append(('resolution', merge_event))
        for kind, event in history_items:
            event_type = str(event.get('event_type') or 'conflict_update').strip() or 'conflict_update'
            ts = _iso_or_none(event.get('created_at'))
            related_node_ids = _clean_node_ids([row.left_node_id, row.right_node_id, *(event.get('supporting_claim_node_ids') or []), *(event.get('supporting_evidence_node_ids') or []), *(event.get('supporting_memory_node_ids') or [])])
            _push_timeline_event(items, seen, {
                'event_id': f"conflict:{row.id}:{kind}:{event_type}:{ts or 'unknown'}",
                'timestamp': ts,
                'category': kind,
                'title': event_type.replace('_', ' ').title(),
                'summary': _short_text(str(event.get('summary') or event.get('merge_note') or conflict_entry.get('resolution_summary') or row.reason or 'Conflict state changed.'), 240),
                'status': str(event.get('status') or '').strip() or None,
                'run_id': clean_run_id,
                'conflict_id': row.id,
                'primary_node_id': str(event.get('winning_node_id') or row.left_node_id or '').strip() or None,
                'related_node_ids': related_node_ids,
                'trace_node_ids': related_node_ids,
                'trace_anchor_related': bool(conflict_entry.get('trace_anchor_related')),
                'rationale_codes': _clean_node_ids([*(event.get('rationale_codes') or []), *(conflict_entry.get('resolution_rationale_codes') or [])]),
                'badges': [
                    *([f"status: {event.get('status')}"] if event.get('status') else []),
                    *([f"actor: {event.get('actor')}"] if event.get('actor') else []),
                    *([f"winner: {event.get('winning_node_id')}"] if event.get('winning_node_id') else []),
                ],
                'metadata': {
                    'merge_note': event.get('merge_note'),
                    'source': event.get('source'),
                    'losing_node_ids': event.get('losing_node_ids') or [],
                    'supporting_claim_node_ids': event.get('supporting_claim_node_ids') or [],
                    'supporting_evidence_node_ids': event.get('supporting_evidence_node_ids') or [],
                    'supporting_memory_node_ids': event.get('supporting_memory_node_ids') or [],
                },
            })

    items.sort(key=_timeline_event_sort_key)
    counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for item in items:
        category = str(item.get('category') or 'other')
        counts[category] = counts.get(category, 0) + 1
        status = str(item.get('status') or '').strip() or None
        if status:
            status_counts[status] = status_counts.get(status, 0) + 1

    return {
        'run_id': clean_run_id,
        'scope': 'run' if clean_run_id else 'thread',
        'selection_event_id': selection_event.id if selection_event else None,
        'anchor_node_id': trace_obj.get('anchor_node_id'),
        'started_at': items[0].get('timestamp') if items else None,
        'ended_at': items[-1].get('timestamp') if items else None,
        'count': len(items),
        'category_counts': counts,
        'status_counts': status_counts,
        'items': items,
    }


