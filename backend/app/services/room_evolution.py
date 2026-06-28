from __future__ import annotations

import re
from typing import Any

from app.services.room_skill_discovery import build_room_skill_discovery_bundle


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean(value: Any = '', max_len: int = 800) -> str:
    return re.sub(r'\s+', ' ', str(value or '')).strip()[:max_len]


def _inc(map_: dict[str, int], key: str, n: int = 1) -> None:
    key = _clean(key, 160) or 'unknown'
    map_[key] = int(map_.get(key, 0)) + n


def _signal_pack(item: dict[str, Any]) -> dict[str, Any]:
    payload = _as_dict(item.get('payload'))
    return _as_dict(item.get('signal_pack') or payload.get('signal_pack') or _as_dict(payload.get('event')).get('signal_pack'))


def _bool(pack: dict[str, Any], key: str) -> bool:
    return bool(pack.get(key))


def aggregate_room_evolution_signals(items: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {
        'total_events': len(items),
        'ask_count': 0,
        'team_count': 0,
        'loop_count': 0,
        'repeated_work': 0,
        'preference': 0,
        'observation_event': 0,
        'aggregate_query': 0,
        'correction': 0,
        'image_input': 0,
        'external_search': 0,
        'gateway_need': 0,
        'database_need': 0,
        'confirmation_need': 0,
    }
    object_counts: dict[str, int] = {}
    domain_counts: dict[str, int] = {}
    for item in items:
        pack = _signal_pack(item)
        command = _clean(item.get('command') or pack.get('command') or '', 80).lower()
        mode = _clean(pack.get('work_mode') or '', 80).lower()
        if command == '/ask' or mode == 'ask':
            counts['ask_count'] += 1
        if command == '/team' or mode == 'team_task':
            counts['team_count'] += 1
        if command == '/loop' or mode == 'team_loop_task':
            counts['loop_count'] += 1
        for pack_key, count_key in [
            ('repeated_work_signal', 'repeated_work'),
            ('preference_signal', 'preference'),
            ('observation_event_signal', 'observation_event'),
            ('aggregate_query_signal', 'aggregate_query'),
            ('correction_signal', 'correction'),
            ('image_input_signal', 'image_input'),
            ('external_search_signal', 'external_search'),
            ('gateway_need_signal', 'gateway_need'),
            ('database_need_signal', 'database_need'),
            ('uncertainty_or_confirmation_signal', 'confirmation_need'),
        ]:
            if _bool(pack, pack_key):
                counts[count_key] += 1
        for obj in _as_list(pack.get('candidate_object_types')):
            _inc(object_counts, str(obj))
        for domain in _as_list(pack.get('domain_hints')):
            _inc(domain_counts, str(domain))
        domain = _clean(item.get('domain_label') or _as_dict(item.get('room')).get('domain_label') or '', 160)
        if domain and domain != 'general_workbench':
            _inc(domain_counts, domain)
    return {
        'counts': counts,
        'top_objects': [{'id': k, 'count': v} for k, v in sorted(object_counts.items(), key=lambda kv: kv[1], reverse=True)],
        'top_domains': [{'id': k, 'count': v} for k, v in sorted(domain_counts.items(), key=lambda kv: kv[1], reverse=True)],
    }


def _confidence(count: int, total: int, boost: float = 0.0) -> float:
    raw = 0.25 + min(0.5, (float(count) / float(max(4, total))) * 0.5) + boost
    return max(0.1, min(0.92, round(raw, 2)))


def _schema_proposal(obj: str, count: int, total: int, needs_confirmation: bool) -> dict[str, Any]:
    local = re.sub(r'[^a-zA-Z0-9가-힣._:-]+', '_', obj or 'observed_event').strip('_') or 'observed_event'
    return {
        'kind': 'room_evolution_proposal_v1',
        'proposal_type': 'memory_schema',
        'proposal_id': f'schema:{local}',
        'status': 'pending_review',
        'confidence': _confidence(count, total),
        'title': f'Create soft memory object: {local}',
        'reason_codes': ['repeated_memory_shape_observed'] + (['uncertain_observation_requires_confirmation'] if needs_confirmation else []),
        'memory_schema_card': {
            'kind': 'memory_schema_proposal_v1',
            'schema_name': local,
            'maturity_stage': 'soft_typed_object',
            'fields': [
                {'name': 'id', 'type': 'text', 'required': True},
                {'name': 'observed_at', 'type': 'datetime?', 'required': False},
                {'name': 'summary', 'type': 'text', 'required': True},
                {'name': 'attributes_json', 'type': 'json', 'required': False},
                {'name': 'source_ref', 'type': 'text', 'required': True},
                {'name': 'confidence', 'type': 'number', 'required': True},
                {'name': 'user_confirmed', 'type': 'boolean', 'required': True, 'default': False},
                {'name': 'status', 'type': 'active|corrected|discarded', 'required': True, 'default': 'active'},
            ],
            'write_policy': 'proposal_then_user_or_policy_confirm',
            'export_policy': {'copies_private_memory': False, 'share_schema_only': True},
        },
    }


def _agent_proposal(role: str, *, title: str, description: str, allowed_tools: list[str], reasons: list[str], confidence: float) -> dict[str, Any]:
    return {
        'kind': 'room_evolution_proposal_v1',
        'proposal_type': 'agent_component',
        'proposal_id': f'agent:{role}',
        'status': 'pending_review',
        'confidence': confidence,
        'title': title,
        'reason_codes': reasons,
        'agent_card': {
            'kind': 'room_component_v1',
            'component_type': 'agent_card',
            'local_id': role,
            'title': title,
            'role': role,
            'description': description,
            'tool_policy': {'allowed_tools': allowed_tools, 'external_side_effects': 'approval_required' if allowed_tools else 'none'},
            'memory_access': {'write_memory_directly': False, 'allow_propose_update': True},
            'install_policy': {'default_scope': 'borrow_or_install_after_review', 'can_borrow': True, 'can_install_resident': True, 'can_fork': True},
        },
    }


def infer_room_maturity(counts: dict[str, int]) -> str:
    if int(counts.get('database_need') or 0) > 0 or int(counts.get('aggregate_query') or 0) >= 3:
        return 'shadow_store_candidate'
    if int(counts.get('observation_event') or 0) >= 3 or int(counts.get('preference') or 0) >= 2:
        return 'soft_typed_memory_candidate'
    if int(counts.get('total_events') or 0) >= 2:
        return 'room_pattern_observed'
    return 'raw_interaction_only'


def propose_room_evolution(items: list[dict[str, Any]], *, room_package: dict[str, Any] | None = None) -> dict[str, Any]:
    aggregate = aggregate_room_evolution_signals(items)
    counts = aggregate.get('counts') or {}
    total = int(counts.get('total_events') or 0)
    proposals: list[dict[str, Any]] = []
    needs_confirmation = bool(counts.get('confirmation_need') or counts.get('image_input'))
    for obj in aggregate.get('top_objects') or []:
        if int(obj.get('count') or 0) >= 2 or (total <= 2 and int(obj.get('count') or 0) >= 1 and counts.get('observation_event')):
            proposals.append(_schema_proposal(str(obj.get('id') or 'observed_event'), int(obj.get('count') or 0), total, needs_confirmation))
    if counts.get('image_input'):
        proposals.append(_agent_proposal('image_interpreter', title='Add image interpretation agent component', description='Interpret uploaded images into uncertain candidate records and ask for confirmation before persistent memory writes.', allowed_tools=['vision_model'], reasons=['image_uploads_or_image_requests_observed', 'image_outputs_must_remain_uncertain_until_confirmed'], confidence=_confidence(int(counts.get('image_input') or 0), total, 0.1)))
    if counts.get('external_search'):
        proposals.append(_agent_proposal('local_info_scout', title='Add live/local information scout component', description='Fetch fresh external facts with TTL and provenance when user asks for live/local information.', allowed_tools=['web_search', 'maps_or_local_search'], reasons=['fresh_external_or_local_information_needed', 'facts_need_ttl_and_provenance'], confidence=_confidence(int(counts.get('external_search') or 0), total, 0.05)))
    if counts.get('aggregate_query') or counts.get('database_need'):
        proposals.append(_agent_proposal('pattern_analyst', title='Add pattern analyst component', description='Analyze repeated typed memories using query tools after shadow/canonical materialization is approved.', allowed_tools=['room_memory_query'], reasons=['aggregate_or_db_analysis_requests_observed'], confidence=_confidence(int(counts.get('aggregate_query') or 0) + int(counts.get('database_need') or 0), total)))
    if counts.get('confirmation_need') or counts.get('correction') or counts.get('image_input'):
        proposals.append(_agent_proposal('confirmation_clerk', title='Add confirmation/correction agent component', description='Turn uncertain observations into confirmation questions and handle user corrections.', allowed_tools=[], reasons=['uncertain_or_corrected_records_need_confirmation_flow'], confidence=_confidence(int(counts.get('confirmation_need') or 0) + int(counts.get('correction') or 0) + int(counts.get('image_input') or 0), total)))
    if counts.get('database_need') or int(counts.get('aggregate_query') or 0) >= 2 or int(counts.get('observation_event') or 0) >= 4:
        proposals.append({
            'kind': 'room_evolution_proposal_v1',
            'proposal_type': 'memory_materialization',
            'proposal_id': 'memory:soft_object_to_shadow_store',
            'status': 'pending_review',
            'confidence': _confidence(int(counts.get('aggregate_query') or 0) + int(counts.get('database_need') or 0) + int(counts.get('observation_event') or 0), total, 0.05),
            'title': 'Materialize repeated room memory into a queryable shadow store',
            'reason_codes': ['aggregate_or_database_need_observed'],
            'materialization_plan': {
                'maturity_stage_from': 'soft_typed_object',
                'maturity_stage_to': 'shadow_queryable_store',
                'canonical_write': False,
                'review_required': True,
                'preserves_raw_source_refs': True,
                'rollback_supported': True,
                'suggested_object_types': [x.get('id') for x in aggregate.get('top_objects', [])[:5]],
                'store_sequence': ['raw_notes', 'memory_candidates', 'typed_jsonl', 'shadow_table', 'approved_canonical_store'],
            },
        })
    if counts.get('gateway_need') or counts.get('database_need') or int(counts.get('correction') or 0) >= 2 or int(counts.get('image_input') or 0) >= 2 or total >= 6:
        proposals.append({
            'kind': 'room_evolution_proposal_v1',
            'proposal_type': 'gateway_or_board',
            'proposal_id': 'gateway:room_memory_board',
            'status': 'pending_review',
            'confidence': _confidence(int(counts.get('gateway_need') or 0) + int(counts.get('correction') or 0) + int(counts.get('image_input') or 0) + int(counts.get('database_need') or 0), total, 0.05),
            'title': 'Create a room-specific memory board/gateway',
            'reason_codes': ['room_needs_review_correction_or_visualization_surface'],
            'gateway_spec': {
                'kind': 'room_gateway_proposal_v1',
                'default_surface': 'goc_room_board',
                'capabilities': ['review_memory_candidates', 'correct_records', 'quick_add_entry', 'view_recent_patterns'],
                'suggested_object_types': [x.get('id') for x in aggregate.get('top_objects', [])[:5]],
                'privacy': {'local_or_tenant_private_content_only': True, 'public_package_exports_schema_only': True},
            },
        })
    room_package = room_package or {}
    skill_discovery = build_room_skill_discovery_bundle({'aggregate': aggregate, 'proposals': proposals})
    top_domain = (aggregate.get('top_domains') or [{}])[0].get('id') if aggregate.get('top_domains') else ''
    return {
        'kind': 'room_evolution_snapshot_v1',
        'room': {
            'package_id': room_package.get('package_id') or room_package.get('packageId') or '',
            'domain_label': top_domain or room_package.get('domain_label') or 'emergent_room',
            'formation_mode': 'emergent_from_interactions',
        },
        'maturity': infer_room_maturity(counts),
        'aggregate': aggregate,
        'proposals': proposals,
        'skill_discovery': skill_discovery,
        'room_memory_trial_plan': skill_discovery.get('room_memory_schema_trial_plan'),
        'governance': {
            'ai_role': 'architect_advisor_proposer_not_controller',
            'auto_apply': False,
            'runtime_validates': True,
            'goc_review_required': True,
            'private_content_export': 'never_by_default',
            'schema_is_dynamic': True,
            'canonical_db_write_requires_approval': True,
        },
    }


def public_room_evolution_export(snapshot: dict[str, Any]) -> dict[str, Any]:
    aggregate = _as_dict(snapshot.get('aggregate'))
    counts = _as_dict(aggregate.get('counts'))
    return {
        'kind': 'public_room_evolution_signal_v1',
        'room': {
            'domain_label': _as_dict(snapshot.get('room')).get('domain_label') or 'emergent_room',
            'formation_mode': 'emergent_from_interactions',
        },
        'maturity': snapshot.get('maturity') or 'raw_interaction_only',
        'counts': {k: int(counts.get(k) or 0) for k in ['total_events', 'ask_count', 'team_count', 'loop_count', 'image_input', 'external_search', 'aggregate_query', 'database_need', 'gateway_need']},
        'top_object_type_labels': [str(x.get('id')) for x in _as_list(aggregate.get('top_objects'))[:8] if x.get('id')],
        'proposal_types': sorted({str(p.get('proposal_type')) for p in _as_list(snapshot.get('proposals')) if p.get('proposal_type')}),
        'privacy': {
            'includes_raw_text': False,
            'includes_private_memory': False,
            'includes_uploaded_files': False,
            'includes_location_or_health_records': False,
        },
    }
