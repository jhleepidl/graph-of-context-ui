from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.models import Edge, MemoryConflict, MemoryEdge, MemoryLifecycleEvent, MemoryNode, Node, Thread
from app.services.memory_graph import summarize_memory_edge, summarize_memory_lifecycle_event
from app.services.conversation_team_config import get_team_config_payload


def _clean_adaptive_expansion(value: Any) -> dict[str, Any]:
    row = value if isinstance(value, dict) else {}
    augmentation = row.get('augmentation') if isinstance(row.get('augmentation'), dict) else {}
    role_separation = row.get('role_separation') if isinstance(row.get('role_separation'), dict) else {}
    quality = row.get('quality') if isinstance(row.get('quality'), dict) else {}
    rationale = [str(item).strip() for item in list(row.get('rationale') or []) if str(item).strip()][:6]
    return {
        'recommendation': str(row.get('recommendation') or '').strip().lower() or None,
        'rationale': rationale,
        'augmentation': {
            'score': augmentation.get('score'),
            'reasons': [str(item).strip() for item in list(augmentation.get('reasons') or []) if str(item).strip()][:6],
        },
        'role_separation': {
            'score': role_separation.get('score'),
            'reasons': [str(item).strip() for item in list(role_separation.get('reasons') or []) if str(item).strip()][:6],
            'independent_review_needed': role_separation.get('independent_review_needed') is True,
            'persistent_split_needed': role_separation.get('persistent_split_needed') is True,
        },
        'quality': quality if isinstance(quality, dict) else {},
        'capability_gap_summary': str(row.get('capability_gap_summary') or '').strip() or None,
        'auto_prepared_draft': row.get('auto_prepared_draft') is True,
        'source': str(row.get('source') or '').strip() or None,
        'ts': str(row.get('ts') or '').strip() or None,
    }


def _select_latest_team_strategy(*strategies: dict[str, Any]) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    latest_ts = ''
    for strategy in strategies:
        if not isinstance(strategy, dict):
            continue
        clean = _clean_adaptive_expansion(strategy)
        if not clean.get('recommendation'):
            continue
        ts = str(clean.get('ts') or '')
        if latest is None or ts >= latest_ts:
            latest = clean
            latest_ts = ts
    return latest


def _clean_execution_lane(value: Any) -> str | None:
    lane = str(value or '').strip().lower()
    return lane if lane in {'fast', 'work', 'deep'} else None


def _extract_execution_lane(*sources: Any) -> str | None:
    for source in sources:
        if isinstance(source, dict):
            direct = _clean_execution_lane(
                source.get('execution_lane')
                or source.get('executionLane')
                or source.get('chat_lane')
                or source.get('chatLane')
                or source.get('route_lane')
                or source.get('routeLane')
                or source.get('response_lane')
                or source.get('responseLane')
                or source.get('lane')
            )
            if direct:
                return direct
            nested = _extract_execution_lane(
                source.get('route_plan'),
                source.get('routePlan'),
                source.get('supervisor_route'),
                source.get('supervisorRoute'),
                source.get('routing'),
                source.get('routing_metadata'),
                source.get('routingMetadata'),
            )
            if nested:
                return nested
    return None


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
    _extract_runtime_team_snapshot=None,
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
    runtime_snapshot = _extract_runtime_team_snapshot(scoped_nodes) if _extract_runtime_team_snapshot else {}
    runtime_snapshot = runtime_snapshot if isinstance(runtime_snapshot, dict) else {}
    team_plan = runtime_snapshot.get('team_plan') or {}
    team_plan = team_plan if isinstance(team_plan, dict) else {}
    planner_metadata = team_plan.get('planner_metadata') or team_plan.get('plannerMetadata') or {}
    planner_metadata = planner_metadata if isinstance(planner_metadata, dict) else {}
    selected_motif_ids = [str(item).strip() for item in (planner_metadata.get('selected_motif_ids') or planner_metadata.get('selectedMotifIds') or []) if str(item).strip()]
    team_synthesis_mode = str(planner_metadata.get('team_synthesis_mode') or planner_metadata.get('teamSynthesisMode') or '').strip() or None
    motif_feedback_run_count = planner_metadata.get('motif_feedback_run_count') or planner_metadata.get('motifFeedbackRunCount')
    motif_channel = str(planner_metadata.get('motif_channel') or planner_metadata.get('motifChannel') or '').strip() or None
    execution_mode = str(planner_metadata.get('execution_mode') or planner_metadata.get('executionMode') or '').strip() or None
    execution_mode_reasons = [str(item).strip() for item in (planner_metadata.get('execution_mode_reasons') or planner_metadata.get('executionModeReasons') or []) if str(item).strip()]
    execution_mode_signals = planner_metadata.get('execution_mode_signals') or planner_metadata.get('executionModeSignals') or {}
    execution_mode_signals = execution_mode_signals if isinstance(execution_mode_signals, dict) else {}
    execution_quality_signals = planner_metadata.get('execution_quality_signals') or planner_metadata.get('executionQualitySignals') or {}
    execution_quality_signals = execution_quality_signals if isinstance(execution_quality_signals, dict) else {}
    execution_lane = _extract_execution_lane(planner_metadata, execution_mode_signals, execution_quality_signals)
    execution_mode_history_tail = planner_metadata.get('execution_mode_history_tail') or planner_metadata.get('executionModeHistoryTail') or []
    execution_mode_history_tail = execution_mode_history_tail if isinstance(execution_mode_history_tail, list) else []
    task_type = str(planner_metadata.get('task_type') or planner_metadata.get('taskType') or '').strip() or None
    deliverable_type = str(planner_metadata.get('deliverable_type') or planner_metadata.get('deliverableType') or '').strip() or None
    task_family_key = str(planner_metadata.get('task_family_key') or planner_metadata.get('taskFamilyKey') or '').strip() or None
    task_family_mode_hint = planner_metadata.get('task_family_mode_hint') or planner_metadata.get('taskFamilyModeHint') or {}
    task_family_mode_hint = task_family_mode_hint if isinstance(task_family_mode_hint, dict) else {}
    runtime_strategy = _clean_adaptive_expansion(planner_metadata.get('adaptive_expansion') or planner_metadata.get('adaptiveExpansion') or {})
    team_config_payload = get_team_config_payload(session, thread_id=thread.id)
    active_team = team_config_payload.get('active_team') if isinstance(team_config_payload.get('active_team'), dict) else {}
    pending_team = team_config_payload.get('pending_team') if isinstance(team_config_payload.get('pending_team'), dict) else {}
    active_strategy = _clean_adaptive_expansion((active_team.get('planner_metadata') or active_team.get('plannerMetadata') or {}).get('adaptive_expansion') or ((active_team.get('planner_metadata') or active_team.get('plannerMetadata') or {}).get('adaptiveExpansion')) or {})
    pending_strategy = _clean_adaptive_expansion((pending_team.get('planner_metadata') or pending_team.get('plannerMetadata') or {}).get('adaptive_expansion') or ((pending_team.get('planner_metadata') or pending_team.get('plannerMetadata') or {}).get('adaptiveExpansion')) or {})
    latest_team_strategy = _select_latest_team_strategy(pending_strategy, runtime_strategy, active_strategy)

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

    if selected_motif_ids or team_synthesis_mode:
        motif_summary = []
        if team_synthesis_mode:
            motif_summary.append(f"mode {team_synthesis_mode}")
        if execution_mode:
            motif_summary.append(f"execution {execution_mode}")
        if selected_motif_ids:
            motif_summary.append(f"motifs {', '.join(selected_motif_ids[:4])}")
        if motif_feedback_run_count not in (None, ''):
            motif_summary.append(f"feedback runs {motif_feedback_run_count}")
        _push_timeline_event(items, seen, {
            'event_id': f"planner-motif:{clean_run_id or thread.id}",
            'timestamp': _iso_or_none(selection_event.created_at) if selection_event and selection_event.created_at else None,
            'category': 'planning_motif',
            'title': 'Planner motif selection',
            'summary': '; '.join(motif_summary) or 'Planner motifs were selected for this run.',
            'status': team_synthesis_mode or None,
            'run_id': clean_run_id,
            'badges': [
                *([f"mode: {team_synthesis_mode}"] if team_synthesis_mode else []),
                *([f"execution: {execution_mode}"] if execution_mode else []),
                *([f"lane: {execution_lane}"] if execution_lane else []),
                *([f"channel: {motif_channel}"] if motif_channel else []),
                *([f"motifs: {len(selected_motif_ids)}"] if selected_motif_ids else []),
                *([f"quality: {execution_quality_signals.get('quality_health_score')}"] if execution_quality_signals.get('quality_health_score') not in (None, '') else []),
                *([f"task-family: {task_family_key}"] if task_family_key else []),
            ],
            'metadata': {
                'selected_motif_ids': selected_motif_ids,
                'team_synthesis_mode': team_synthesis_mode,
                'motif_feedback_run_count': motif_feedback_run_count,
                'motif_channel': motif_channel,
                'execution_mode': execution_mode,
                'execution_lane': execution_lane,
                'execution_mode_reasons': execution_mode_reasons,
                'execution_mode_signals': execution_mode_signals,
                'execution_quality_signals': execution_quality_signals,
                'execution_mode_history_tail': execution_mode_history_tail,
                'task_type': task_type,
                'deliverable_type': deliverable_type,
                'task_family_key': task_family_key,
                'task_family_mode_hint': task_family_mode_hint,
                'selection_explanations': runtime_snapshot.get('selection_explanations') or [],
            },
        })

    if latest_team_strategy:
        recommendation = str(latest_team_strategy.get('recommendation') or '').strip().lower()
        augmentation_meta = latest_team_strategy.get('augmentation') if isinstance(latest_team_strategy.get('augmentation'), dict) else {}
        role_separation_meta = latest_team_strategy.get('role_separation') if isinstance(latest_team_strategy.get('role_separation'), dict) else {}
        strategy_source = str(latest_team_strategy.get('source') or '').strip() or ('pending_team' if pending_strategy.get('recommendation') else ('runtime' if runtime_strategy.get('recommendation') else 'active_team'))
        strategy_team_name = str((pending_team if strategy_source.startswith('pending') else active_team).get('team_name') or '').strip() or None
        strategy_summary_parts = []
        if recommendation == 'augment_context':
            strategy_summary_parts.append('Preferred memory / skill / context augmentation before splitting roles.')
        elif recommendation == 'expand_team':
            strategy_summary_parts.append('Role separation value is high enough to justify a pending or active team expansion.')
        elif recommendation:
            strategy_summary_parts.append(f'Recommended {recommendation} for the latest run state.')
        capability_gap_summary = str(latest_team_strategy.get('capability_gap_summary') or '').strip()
        if capability_gap_summary:
            strategy_summary_parts.append(f'gaps {capability_gap_summary}')
        if latest_team_strategy.get('auto_prepared_draft') is True:
            strategy_summary_parts.append('pending draft prepared')
        strategy_timestamp = str(latest_team_strategy.get('ts') or '').strip()
        if not strategy_timestamp and selection_event and selection_event.created_at:
            strategy_timestamp = _iso_or_none(selection_event.created_at)
        _push_timeline_event(items, seen, {
            'event_id': f"team-strategy:{clean_run_id or thread.id}",
            'timestamp': strategy_timestamp,
            'category': 'team_strategy',
            'title': 'Adaptive team strategy assessed',
            'summary': ' · '.join(strategy_summary_parts) or 'Adaptive team strategy was assessed for this run.',
            'status': recommendation or None,
            'run_id': clean_run_id,
            'badges': [
                *([f"recommendation: {recommendation}"] if recommendation else []),
                *([f"augmentation: {augmentation_meta.get('score')}"] if augmentation_meta.get('score') not in (None, '') else []),
                *([f"role separation: {role_separation_meta.get('score')}"] if role_separation_meta.get('score') not in (None, '') else []),
                *([f"source: {strategy_source}"] if strategy_source else []),
                *([f"lane: {execution_lane}"] if execution_lane else []),
                *(['independent review'] if role_separation_meta.get('independent_review_needed') is True else []),
                *(['persistent split'] if role_separation_meta.get('persistent_split_needed') is True else []),
                *(['pending draft'] if latest_team_strategy.get('auto_prepared_draft') is True else []),
            ],
            'metadata': {
                'recommendation': recommendation,
                'rationale': latest_team_strategy.get('rationale') or [],
                'augmentation': augmentation_meta,
                'role_separation': role_separation_meta,
                'quality': latest_team_strategy.get('quality') or {},
                'capability_gap_summary': capability_gap_summary or None,
                'source': strategy_source,
                'execution_lane': execution_lane,
                'team_name': strategy_team_name,
                'team_state_status': team_config_payload.get('status'),
                'active_team_name': active_team.get('team_name'),
                'pending_team_name': pending_team.get('team_name'),
                'auto_prepared_draft': latest_team_strategy.get('auto_prepared_draft') is True,
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


    participant_nodes = [
        node for node in node_by_id.values()
        if str(getattr(node, 'type', '') or '').strip() in {'ParticipantSignal', 'ParticipantDigest', 'ChannelVerifierDecision', 'ChannelPromotionApplied'}
    ]
    participant_nodes.sort(key=_created_sort_key)
    for node in participant_nodes:
        payload = _node_payload(node)
        payload_run_id = str(payload.get('run_id') or '').strip()
        if clean_run_id and payload_run_id and payload_run_id != clean_run_id:
            continue
        node_type = str(getattr(node, 'type', '') or '').strip()
        if node_type == 'ParticipantSignal':
            participant = payload.get('participant') or {}
            contribution = payload.get('contribution') or {}
            decision = payload.get('decision') or {}
            participant_label = _clean_text(participant.get('label') or participant.get('participant_id')) or 'participant'
            contribution_kind = _clean_text(contribution.get('kind'), max_len=64) or 'signal'
            confidence = contribution.get('confidence')
            try:
                confidence_label = f"{round(float(confidence) * 100):.0f}%"
            except Exception:
                confidence_label = None
            title = f"Participant signal from {participant_label}"
            summary = _short_text(str(contribution.get('summary') or contribution.get('content') or decision.get('digest') or decision.get('action') or 'Participant contributed an internal signal.'), 240)
            _push_timeline_event(items, seen, {
                'event_id': f"participant-signal:{node.id}",
                'timestamp': _iso_or_none(getattr(node, 'created_at', None)),
                'category': 'participant_signal',
                'title': title,
                'summary': summary,
                'status': str(decision.get('action') or contribution.get('visibility_default') or '').strip() or None,
                'run_id': clean_run_id or payload_run_id or None,
                'primary_node_id': node.id,
                'related_node_ids': [node.id],
                'trace_node_ids': [node.id],
                'badges': [
                    *([f"participant: {participant_label}"] if participant_label else []),
                    *([f"kind: {contribution_kind}"] if contribution_kind else []),
                    *([f"confidence: {confidence_label}"] if confidence_label else []),
                    *([f"surface: {decision.get('action')}"] if decision.get('action') else []),
                ],
                'metadata': {
                    'participant_id': participant.get('participant_id'),
                    'participant_type': participant.get('participant_type'),
                    'channel_mode': participant.get('channel_mode'),
                    'kind': contribution.get('kind'),
                    'confidence': contribution.get('confidence'),
                    'surface_mode': decision.get('surface_mode'),
                    'should_fold': decision.get('should_fold'),
                    'should_surface': decision.get('should_surface'),
                    'digest': decision.get('digest'),
                    'references': contribution.get('references') or [],
                },
            })
            continue
        if node_type == 'ChannelVerifierDecision':
            motif = payload.get('motif') or {}
            participant_policy = payload.get('participant_policy') or {}
            overall = str(payload.get('overall_recommendation') or '').strip() or None
            title = 'Experiment channel verifier'
            summary = _short_text(str(
                motif.get('rationale')
                or participant_policy.get('rationale')
                or payload.get('goal_excerpt')
                or 'Verified active motif and participant policy channels for this run.'
            ), 240)
            _push_timeline_event(items, seen, {
                'event_id': f"channel-verifier:{node.id}",
                'timestamp': _iso_or_none(getattr(node, 'created_at', None)),
                'category': 'channel_verifier',
                'title': title,
                'summary': summary,
                'status': overall,
                'run_id': clean_run_id or payload_run_id or None,
                'primary_node_id': node.id,
                'related_node_ids': [node.id],
                'trace_node_ids': [node.id],
                'badges': [
                    *([f"overall: {overall}"] if overall else []),
                    *([f"motif: {motif.get('channel')} → {motif.get('next_channel')}"] if motif.get('channel') else []),
                    *([f"participant: {participant_policy.get('channel')} → {participant_policy.get('next_channel')}"] if participant_policy.get('channel') else []),
                ],
                'metadata': {
                    'motif': motif,
                    'participant_policy': participant_policy,
                    'participation_pct': payload.get('participation_pct'),
                    'score': payload.get('score'),
                    'execution_pattern': payload.get('execution_pattern'),
                    'goal_excerpt': payload.get('goal_excerpt'),
                },
            })
            continue

        if node_type == 'ChannelPromotionApplied':
            motif = payload.get('motif') or {}
            participant_policy = payload.get('participant_policy') or {}
            overall = str(payload.get('overall_recommendation') or '').strip() or None
            title = 'Channel promotion applied'
            summary = _short_text(str(
                motif.get('rationale')
                or participant_policy.get('rationale')
                or payload.get('goal_excerpt')
                or 'Applied stable/candidate promotion summary for this run.'
            ), 240)
            _push_timeline_event(items, seen, {
                'event_id': f"channel-promotion:{node.id}",
                'timestamp': _iso_or_none(getattr(node, 'created_at', None)),
                'category': 'channel_promotion',
                'title': title,
                'summary': summary,
                'status': overall,
                'run_id': clean_run_id or payload_run_id or None,
                'primary_node_id': node.id,
                'related_node_ids': [node.id],
                'trace_node_ids': [node.id],
                'badges': [
                    *([f"overall: {overall}"] if overall else []),
                    *([f"promoted motifs: {len(list((motif.get('promoted_motif_ids') or [])))}"] if motif.get('promoted_motif_ids') else []),
                    *([f"rolled back motifs: {len(list((motif.get('rolled_back_motif_ids') or [])))}"] if motif.get('rolled_back_motif_ids') else []),
                    *(['participant snapshot: applied'] if (participant_policy.get('snapshot') or {}) else []),
                ],
                'metadata': {
                    'motif': motif,
                    'participant_policy': participant_policy,
                    'goal_excerpt': payload.get('goal_excerpt'),
                },
            })
            continue
        participant_labels = [str(item).strip() for item in (payload.get('participant_labels') or []) if str(item).strip()]
        kind_counts = payload.get('kind_counts') or {}
        _push_timeline_event(items, seen, {
            'event_id': f"participant-digest:{node.id}",
            'timestamp': _iso_or_none(getattr(node, 'created_at', None)),
            'category': 'participant_digest',
            'title': 'Folded participant digest applied',
            'summary': _short_text(str(payload.get('digest_block') or payload.get('prompt_block') or f"Folded {payload.get('item_count') or 0} participant signals into the final reply flow."), 240),
            'status': str(payload.get('mode') or '').strip() or None,
            'run_id': clean_run_id or payload_run_id or None,
            'primary_node_id': node.id,
            'related_node_ids': [node.id],
            'trace_node_ids': [node.id],
            'badges': [
                f"items: {int(payload.get('item_count') or 0)}",
                *([f"mode: {payload.get('mode')}"] if payload.get('mode') else []),
                *([f"participants: {', '.join(participant_labels[:3])}"] if participant_labels else []),
            ],
            'metadata': {
                'turn_id': payload.get('turn_id'),
                'participant_labels': participant_labels,
                'participant_ids': payload.get('participant_ids') or [],
                'contribution_ids': payload.get('contribution_ids') or [],
                'kinds': payload.get('kinds') or [],
                'kind_counts': kind_counts,
                'digest_block': payload.get('digest_block'),
                'signature': payload.get('signature'),
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

    participant_signal_events = [item for item in items if str(item.get('category') or '') == 'participant_signal']
    participant_digest_events = [item for item in items if str(item.get('category') or '') == 'participant_digest']
    channel_verifier_events = [item for item in items if str(item.get('category') or '') == 'channel_verifier']
    channel_promotion_events = [item for item in items if str(item.get('category') or '') == 'channel_promotion']
    participant_kind_counts: dict[str, int] = {}
    participant_labels: list[str] = []
    seen_participant_labels: set[str] = set()
    for event in participant_signal_events:
        metadata = event.get('metadata') or {}
        kind = str(metadata.get('kind') or '').strip()
        if kind:
            participant_kind_counts[kind] = participant_kind_counts.get(kind, 0) + 1
        label = str(metadata.get('participant_id') or '').strip()
        if label and label not in seen_participant_labels:
            seen_participant_labels.add(label)
            participant_labels.append(label)
    for event in participant_digest_events:
        metadata = event.get('metadata') or {}
        for kind, count in dict(metadata.get('kind_counts') or {}).items():
            clean_kind = str(kind or '').strip()
            if not clean_kind:
                continue
            participant_kind_counts[clean_kind] = participant_kind_counts.get(clean_kind, 0) + int(count or 0)
        for label in list(metadata.get('participant_labels') or []):
            clean_label = str(label or '').strip()
            if clean_label and clean_label not in seen_participant_labels:
                seen_participant_labels.add(clean_label)
                participant_labels.append(clean_label)

    latest_channel_verifier = channel_verifier_events[-1] if channel_verifier_events else None
    latest_channel_verifier_metadata = latest_channel_verifier.get('metadata') if isinstance(latest_channel_verifier, dict) else {}
    motif_compare = (latest_channel_verifier_metadata or {}).get('motif') or {}
    participant_compare = (latest_channel_verifier_metadata or {}).get('participant_policy') or {}
    latest_channel_promotion = channel_promotion_events[-1] if channel_promotion_events else None
    latest_channel_promotion_metadata = latest_channel_promotion.get('metadata') if isinstance(latest_channel_promotion, dict) else {}
    promotion_motif = (latest_channel_promotion_metadata or {}).get('motif') or {}
    promotion_participant = (latest_channel_promotion_metadata or {}).get('participant_policy') or {}

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
        'linked_summary': {
            'team_synthesis_mode': team_synthesis_mode,
            'execution_mode': execution_mode,
            'execution_lane': execution_lane,
            'execution_mode_reasons': execution_mode_reasons,
            'execution_mode_signals': execution_mode_signals,
            'execution_quality_signals': execution_quality_signals,
            'execution_mode_history_tail': execution_mode_history_tail[-5:],
            'adaptive_expansion': latest_team_strategy,
            'selected_motif_ids': selected_motif_ids,
            'motif_feedback_run_count': motif_feedback_run_count,
            'motif_channel': motif_channel,
            'participant_signal_count': len(participant_signal_events),
            'participant_digest_count': len(participant_digest_events),
            'participant_kind_counts': participant_kind_counts,
            'participant_labels': participant_labels[:8],
            'channel_verifier_count': len(channel_verifier_events),
            'channel_promotion_count': len(channel_promotion_events),
            'latest_overall_recommendation': str((latest_channel_verifier_metadata or {}).get('overall_recommendation') or '').strip() or None,
            'motif_compare': motif_compare,
            'participant_policy_compare': participant_compare,
            'promoted_motif_ids': list((promotion_motif.get('promoted_motif_ids') or []))[:8],
            'rolled_back_motif_ids': list((promotion_motif.get('rolled_back_motif_ids') or []))[:8],
            'participant_policy_snapshot': (promotion_participant.get('snapshot') or {}),
        },
        'items': items,
    }


