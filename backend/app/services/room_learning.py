from __future__ import annotations

from typing import Any

from app.services.room_evolution import propose_room_evolution, public_room_evolution_export


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def summarize_room_usage_events(items: list[dict[str, Any]]) -> dict[str, Any]:
    by_event: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    by_approach: dict[str, int] = {}
    for item in items:
        event_type = item.get('event_type') or 'room_event'
        domain = item.get('domain_label') or 'general_workbench'
        by_event[event_type] = by_event.get(event_type, 0) + 1
        by_domain[domain] = by_domain.get(domain, 0) + 1
        if item.get('recommended_approach'):
            by_approach[item.get('recommended_approach')] = by_approach.get(item.get('recommended_approach'), 0) + 1
    return {
        'event_count': len(items),
        'by_event_type': by_event,
        'by_domain': by_domain,
        'by_recommended_approach': by_approach,
    }


def build_room_learning_snapshot(items: list[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize_room_usage_events(items)
    by_domain = summary.get('by_domain') or {}
    top_domain = ''
    top_count = 0
    for domain, count in by_domain.items():
        if int(count or 0) > top_count:
            top_domain = domain
            top_count = int(count or 0)
    ask_count = 0
    team_count = 0
    loop_count = 0
    component_views = 0
    package_exports = 0
    package_installs = 0
    memory_signals = 0
    for item in items:
        event_type = str(item.get('event_type') or '').lower()
        command = str(item.get('command') or '').lower()
        payload = _as_dict(item.get('payload'))
        extra = _as_dict(payload.get('extra'))
        depth = str(extra.get('depth') or '').lower()
        if command == '/ask' or depth == 'ask':
            ask_count += 1
        if command == '/team' or depth in {'team', 'team_task'}:
            team_count += 1
        if command == '/loop' or depth in {'loop', 'team_loop_task'}:
            loop_count += 1
        if 'component' in event_type:
            component_views += 1
        if 'export' in event_type:
            package_exports += 1
        if 'install' in event_type:
            package_installs += 1
        if 'memory' in event_type or 'memory' in str(payload).lower():
            memory_signals += 1
    recommended_depth = 'ask'
    reasons: list[str] = []
    if loop_count > 0:
        recommended_depth = 'team_loop_task'
        reasons.append('loop_usage_observed')
    elif team_count > 0:
        recommended_depth = 'team_task'
        reasons.append('team_usage_observed')
    elif ask_count >= 3 and top_count >= 3:
        recommended_depth = 'team_task'
        reasons.append('repeated_ask_same_domain')
    else:
        reasons.append('insufficient_repetition_for_specialization')
    suggested_actions: list[dict[str, Any]] = []
    if top_domain:
        suggested_actions.append({'action': 'suggest_room_package', 'domain_label': top_domain, 'reason': 'dominant_room_usage_domain'})
    if ask_count >= 3 and team_count == 0:
        suggested_actions.append({'action': 'offer_team_task_upgrade', 'domain_label': top_domain or 'general_workbench', 'reason': 'many ask turns without team review'})
    if team_count > 0 and package_exports == 0:
        suggested_actions.append({'action': 'offer_room_package_export', 'domain_label': top_domain or 'general_workbench', 'reason': 'specialized room use without exported package'})
    if memory_signals > 0:
        suggested_actions.append({'action': 'review_memory_schema_card', 'domain_label': top_domain or 'general_workbench', 'reason': 'memory-related room signals observed'})
    return {
        'kind': 'room_learning_snapshot_v1',
        'summary': summary,
        'top_domain': top_domain or 'general_workbench',
        'recommended_depth': recommended_depth,
        'reason_codes': reasons,
        'signals': {
            'ask_count': ask_count,
            'team_count': team_count,
            'loop_count': loop_count,
            'component_views': component_views,
            'package_exports': package_exports,
            'package_installs': package_installs,
            'memory_signals': memory_signals,
        },
        'component_reuse_policy': {
            'reuse_components': True,
            'copy_private_memory': False,
            'borrowed_agents_receive_target_projection_only': True,
            'memory_updates': 'proposal_only',
        },
        'room_evolution': propose_room_evolution(items),
        'public_evolution_export': public_room_evolution_export(propose_room_evolution(items)),
        'suggested_actions': suggested_actions,
    }
