from __future__ import annotations

import json
from typing import Any



def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _clean_text(value: Any, max_len: int = 256) -> str:
    return str(value or '').strip()[:max_len]


def _clean_id(value: Any, max_len: int = 128) -> str:
    text = _clean_text(value, max_len).lower()
    return ''.join(ch if ch.isalnum() or ch in '._:-' else '_' for ch in text)


def _tokenize(text: str) -> list[str]:
    return [token for token in _clean_id(text, 1024).split('_') if token]


def _overlap_score(left: str, right: str) -> int:
    left_set = set(_tokenize(left))
    return sum(1 for token in _tokenize(right) if token in left_set)


def _memory_fit(blueprint: dict[str, Any]) -> dict[str, Any]:
    memory_plan = _as_dict(blueprint.get('memory_plan'))
    surfaces = [_as_dict(item) for item in _as_list(memory_plan.get('surfaces'))]
    final_ready = any(
        _clean_id(surface.get('surface_id')) == 'final_answer'
        or 'final_answer' in [_clean_id(item) for item in _as_list(surface.get('semantic_slots'))]
        for surface in surfaces
    )
    return {
        'surface_count': len(surfaces),
        'shared_surface_count': sum(1 for surface in surfaces if _clean_id(surface.get('write_policy') or 'shared') == 'shared'),
        'final_answer_surface_ready': final_ready,
        'append_only_surface_count': sum(1 for surface in surfaces if _clean_id(surface.get('write_policy') or 'shared') == 'append_only'),
    }


def _topology_summary(blueprint: dict[str, Any]) -> dict[str, Any]:
    topology = _as_dict(blueprint.get('topology'))
    participants = _as_list(topology.get('participants')) or _as_list(_as_dict(blueprint.get('structure')).get('participants'))
    edges = _as_list(topology.get('edges'))
    pattern = _clean_text(topology.get('pattern') or 'hybrid', 64) or 'hybrid'
    return {
        'pattern': pattern,
        'participant_count': len(participants),
        'edge_count': len(edges),
        'final_participant_id': _clean_text(topology.get('final_participant_id'), 128) or None,
    }


def _executable_features(candidate: dict[str, Any]) -> dict[str, Any]:
    executable = _as_dict(candidate.get('executable_definition') or candidate.get('manifest', {}).get('summary', {}).get('executable_team_definition'))
    readiness = _as_dict(executable.get('executable_readiness'))
    capability = _as_dict(executable.get('capability_contract'))
    return {
        'member_count': int(executable.get('member_count') or 0),
        'role_ids': [str(v) for v in _as_list(executable.get('role_ids')) if str(v).strip()],
        'ready': readiness.get('ready') is True,
        'runtime_bound': capability.get('runtime_bound') is True,
        'admission_status': _clean_text(capability.get('admission_status'), 64) or None,
        'blocking_reason_codes': [str(v) for v in _as_list(capability.get('blocking_reason_codes')) if str(v).strip()],
        'degrade_reason_codes': [str(v) for v in _as_list(capability.get('degrade_reason_codes')) if str(v).strip()],
    }


def _score_template(task_text: str, manifest: dict[str, Any]) -> dict[str, Any]:
    blueprint = _as_dict(manifest.get('blueprint'))
    summary = _as_dict(manifest.get('summary'))
    title = _clean_text(blueprint.get('title') or summary.get('title') or '')
    description = _clean_text(blueprint.get('description') or '')
    archetype = _clean_text(blueprint.get('task_archetype') or summary.get('task_archetype') or 'general', 64) or 'general'
    serialized = f"{title} {description} {manifest}"
    semantic = _overlap_score(serialized, task_text)
    task_lower = task_text.lower()
    if archetype == 'implementation' and any(token in task_lower for token in ['implement', 'code', 'patch', 'repo', 'fix', 'workspace']):
        semantic += 4
    if archetype == 'review_repair' and any(token in task_lower for token in ['review', 'repair', 'regression', 'bug', 'audit']):
        semantic += 4
    if archetype == 'research' and any(token in task_lower for token in ['research', 'brief', 'analysis', 'investigate']):
        semantic += 4
    memory_fit = _memory_fit(blueprint)
    topology = _topology_summary(blueprint)
    rationale = [f'archetype={archetype}', f'keyword_overlap={semantic}', f'topology={topology["pattern"]}']
    if memory_fit['final_answer_surface_ready']:
        rationale.append('final_answer_surface_ready')
    return {
        'score': semantic,
        'semantic_score': semantic,
        'memory_fit': memory_fit,
        'topology': topology,
        'rationale': rationale,
    }


def recommend_team_blueprints(task_text: str, *, limit: int = 3) -> dict[str, Any]:
    from app.services.team_blueprint_templates import list_team_blueprint_templates
    from app.services.team_admission import build_memory_acl_summary

    candidates: list[dict[str, Any]] = []
    for template in list_team_blueprint_templates():
        manifest = template
        scored = _score_template(task_text, manifest)
        blueprint = _as_dict(manifest.get('blueprint'))
        summary = _as_dict(manifest.get('summary'))
        structure = _as_dict(blueprint.get('structure'))
        memory_acl_summary = build_memory_acl_summary(
            blueprint.get('memory_plan') or {},
            _as_dict(manifest.get('team')).get('agents') or [],
            structure.get('participants') or [],
        )
        candidates.append({
            'template_id': _clean_text(blueprint.get('blueprint_id'), 128) or 'template',
            'title': _clean_text(blueprint.get('title'), 160) or 'Configured Team',
            'task_archetype': _clean_text(blueprint.get('task_archetype'), 64) or 'general',
            'score': scored['score'],
            'semantic_score': scored['semantic_score'],
            'rationale': scored['rationale'],
            'topology': scored['topology'],
            'memory_fit': scored['memory_fit'],
            'memory_acl_summary': memory_acl_summary[:8],
            'executable_definition': summary.get('executable_team_definition') or {},
            'manifest': manifest,
        })
    candidates.sort(key=lambda item: (-int(item.get('score') or 0), str(item.get('title') or '')))
    return {
        'kind': 'team_composer_recommendation_v1',
        'task_text': _clean_text(task_text, 1000),
        'candidate_count': min(len(candidates), max(1, limit)),
        'candidates': candidates[:max(1, limit)],
    }


def _candidate_training_view(candidate: dict[str, Any]) -> dict[str, Any]:
    memory_fit = _as_dict(candidate.get('memory_fit'))
    topology = _as_dict(candidate.get('topology'))
    executable = _executable_features(candidate)
    return {
        'template_id': _clean_text(candidate.get('template_id') or candidate.get('blueprint_id'), 128) or None,
        'task_archetype': _clean_text(candidate.get('task_archetype'), 64) or 'general',
        'score': float(candidate.get('score') or candidate.get('semantic_score') or 0),
        'topology_pattern': _clean_text(topology.get('pattern'), 64) or None,
        'participant_count': int(topology.get('participant_count') or executable.get('member_count') or 0),
        'edge_count': int(topology.get('edge_count') or 0),
        'surface_count': int(memory_fit.get('surface_count') or 0),
        'shared_surface_count': int(memory_fit.get('shared_surface_count') or 0),
        'final_answer_surface_ready': memory_fit.get('final_answer_surface_ready') is True,
        'append_only_surface_count': int(memory_fit.get('append_only_surface_count') or 0),
        'member_count': int(executable.get('member_count') or 0),
        'role_ids': executable.get('role_ids') or [],
        'ready': executable.get('ready') is True,
        'runtime_bound': executable.get('runtime_bound') is True,
        'admission_status': executable.get('admission_status'),
        'blocking_reason_codes': executable.get('blocking_reason_codes') or [],
        'degrade_reason_codes': executable.get('degrade_reason_codes') or [],
        'rationale': [str(v) for v in _as_list(candidate.get('rationale')) if str(v).strip()],
    }


def build_team_selection_dataset(events: Any) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    archetype_counts: dict[str, int] = {}
    success_counts: dict[str, int] = {'success': 0, 'failure': 0}
    for item in _as_list(events):
        row = _as_dict(item)
        recommendation = _as_dict(row.get('recommendation'))
        outcome = _as_dict(row.get('outcome'))
        candidates = [_as_dict(candidate) for candidate in _as_list(recommendation.get('candidates'))]
        selected_blueprint_id = _clean_text(row.get('selected_blueprint_id'), 128) or None
        selected_candidate = next((candidate for candidate in candidates if _clean_text(candidate.get('template_id') or candidate.get('blueprint_id'), 128) == selected_blueprint_id), {})
        task_text = _clean_text(row.get('task_text'), 1000)
        task_archetype = _clean_text(selected_candidate.get('task_archetype') or recommendation.get('task_archetype') or outcome.get('task_archetype') or 'general', 64) or 'general'
        archetype_counts[task_archetype] = archetype_counts.get(task_archetype, 0) + 1
        success = outcome.get('success') is True
        success_counts['success' if success else 'failure'] += 1
        selected_features = _candidate_training_view(selected_candidate)
        candidate_features = [_candidate_training_view(candidate) for candidate in candidates[:8]]
        rows.append({
            'event_id': _clean_text(row.get('id'), 128) or None,
            'thread_id': _clean_text(row.get('thread_id'), 128) or None,
            'run_id': _clean_text(row.get('run_id'), 128) or None,
            'task_text': task_text,
            'task_archetype': task_archetype,
            'selected_blueprint_id': selected_blueprint_id,
            'candidate_count': len(candidates),
            'selected_score': selected_features.get('score', 0),
            'selected_topology_pattern': selected_features.get('topology_pattern'),
            'selected_memory_surface_count': selected_features.get('surface_count'),
            'selected_final_answer_surface_ready': selected_features.get('final_answer_surface_ready'),
            'selected_member_count': selected_features.get('member_count'),
            'selected_role_ids': selected_features.get('role_ids'),
            'selected_ready': selected_features.get('ready'),
            'selected_runtime_bound': selected_features.get('runtime_bound'),
            'selected_blocking_reason_codes': selected_features.get('blocking_reason_codes'),
            'selected_degrade_reason_codes': selected_features.get('degrade_reason_codes'),
            'candidate_features': candidate_features,
            'input_features': {
                'task_text': task_text,
                'task_archetype': task_archetype,
                'candidate_count': len(candidates),
            },
            'selected_features': selected_features,
            'outcome_labels': {
                'success': success,
                'quality_score': float(outcome.get('quality_score') or 0),
                'token_cost': float(outcome.get('token_cost') or 0),
                'latency_ms': float(outcome.get('latency_ms') or 0),
                'human_override': outcome.get('human_override') is True,
                'recovery_count': int(outcome.get('recovery_count') or 0),
            },
            'success': success,
            'quality_score': outcome.get('quality_score'),
            'token_cost': outcome.get('token_cost'),
            'latency_ms': outcome.get('latency_ms'),
            'human_override': outcome.get('human_override'),
            'recovery_count': outcome.get('recovery_count'),
            'created_at': row.get('created_at'),
        })
    return {
        'kind': 'team_selection_dataset_v1',
        'schema_version': 2,
        'count': len(rows),
        'archetype_counts': archetype_counts,
        'success_counts': success_counts,
        'rows': rows,
    }


def serialize_team_selection_dataset_jsonl(events: Any) -> str:
    dataset = build_team_selection_dataset(events)
    return '\n'.join(json.dumps(row, ensure_ascii=False) for row in dataset.get('rows') or [])
