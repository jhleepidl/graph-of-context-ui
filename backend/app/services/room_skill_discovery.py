from __future__ import annotations

from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _top_ids(rows: list[Any], limit: int = 5) -> list[str]:
    out: list[str] = []
    for row in rows[:limit]:
        item = _as_dict(row)
        value = str(item.get('id') or item.get('name') or '').strip()
        if value:
            out.append(value)
    return out


def build_room_skill_discovery_bundle(snapshot: dict[str, Any]) -> dict[str, Any]:
    aggregate = _as_dict(snapshot.get('aggregate'))
    counts = _as_dict(aggregate.get('counts'))
    objects = _top_ids(_as_list(aggregate.get('top_objects')), 5)
    probes = []
    for obj in objects[:4]:
        probes.append({
            'kind': 'room_probe_task_v1',
            'probe_id': f'probe:{obj}:extract-and-use',
            'target_object_type': obj,
            'challenge_type': 'memory_schema_utility_probe',
            'rubric': [
                'uses the smallest sufficient room memory projection',
                'preserves source references and uncertainty',
                'does not export private memory',
                'turns uncertain writes into proposals',
            ],
            'replay_tags': ['room_memory_schema_trial', 'room_specific_probe'],
        })
    if objects and (counts.get('correction') or counts.get('confirmation_need') or counts.get('image_input')):
        probes.append({
            'kind': 'room_probe_task_v1',
            'probe_id': 'probe:stale-conflicting-memory-rejection',
            'target_object_type': objects[0],
            'challenge_type': 'harmful_memory_rejection_probe',
            'replay_tags': ['room_memory_harmful_memory_rejection', 'cross_time_replay'],
        })
    trial_plan = {
        'kind': 'room_memory_schema_trial_plan_v1',
        'research_question': 'Which room-specific memory schema treatment improves future recurring room tasks under governance and privacy constraints?',
        'unit_of_treatment': 'room_specific_memory_package_or_schema_projection',
        'candidate_object_types': objects,
        'treatments': ['raw_tail', 'latest_summary', 'soft_typed_objects', 'schema_plus_confirmation', 'shadow_queryable_store'],
        'metrics': ['outcome_utility', 'harmful_memory_rejection', 'token_per_quality_gain', 'privacy_boundary_preservation'],
        'novelty_claims': [
            'memory schema is a room-scoped treatment rather than passive retrieval',
            'schema utility is evaluated by repeated room traces and governed outcomes',
            'private memory is separated from exportable room package structure',
        ],
    }
    return {
        'kind': 'room_skill_discovery_bundle_v1',
        'inspiration': 'ctx2skill_style_probe_reason_judge_propose_loop_adapted_to_ai_rooms',
        'probe_suite': {'kind': 'room_probe_suite_v1', 'probes': probes},
        'room_memory_schema_trial_plan': trial_plan,
        'cross_time_replay_plan': {
            'kind': 'cross_time_replay_plan_v1',
            'selection_rule': 'prefer robust schema/component candidates with lower memory harm and lower unnecessary complexity',
            'probe_ids': [probe.get('probe_id') for probe in probes],
        },
        'governance': {
            'ai_generates_probes_and_proposals': True,
            'runtime_validates': True,
            'goc_or_user_approves': True,
            'direct_memory_write': False,
            'private_memory_export': False,
        },
    }
