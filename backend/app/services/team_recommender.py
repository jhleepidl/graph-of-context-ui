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



def _unique_texts(values: Any, max_items: int = 16) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in _as_list(values):
        value = _clean_text(raw, 128)
        key = value.lower()
        if not value or key in seen:
            continue
        seen.add(key)
        out.append(value)
        if len(out) >= max_items:
            break
    return out



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
        'surface_ids': _unique_texts([_clean_id(surface.get('surface_id')) for surface in surfaces], 16),
        'semantic_slots': _unique_texts([
            _clean_id(slot)
            for surface in surfaces
            for slot in _as_list(surface.get('semantic_slots'))
        ], 16),
    }



def _topology_summary(blueprint: dict[str, Any]) -> dict[str, Any]:
    topology = _as_dict(blueprint.get('topology'))
    structure = _as_dict(blueprint.get('structure'))
    participants = _as_list(topology.get('participants')) or _as_list(structure.get('participants'))
    edges = _as_list(topology.get('edges'))
    pattern = _clean_text(topology.get('pattern') or _as_dict(structure.get('topology')).get('pattern') or 'hybrid', 64) or 'hybrid'
    roles = _unique_texts([
        _clean_text(_as_dict(participant).get('role') or _as_dict(participant).get('kind'), 64)
        for participant in participants
    ], 12)
    return {
        'pattern': pattern,
        'participant_count': len(participants),
        'edge_count': len(edges),
        'participant_roles': roles,
        'review_present': any(_clean_id(role) in {'reviewer', 'critic', 'judge'} for role in roles),
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



def _blueprint_search_text(blueprint: dict[str, Any]) -> str:
    structure = _as_dict(blueprint.get('structure'))
    topology = _as_dict(blueprint.get('topology'))
    memory_plan = _as_dict(blueprint.get('memory_plan'))
    catalog = _as_dict(blueprint.get('catalog'))
    participants = _as_list(topology.get('participants')) or _as_list(structure.get('participants'))
    surfaces = [_as_dict(item) for item in _as_list(memory_plan.get('surfaces'))]
    pieces: list[str] = [
        _clean_text(blueprint.get('title')),
        _clean_text(blueprint.get('description')),
        _clean_text(blueprint.get('task_archetype'), 64),
        _clean_text(topology.get('pattern') or _as_dict(structure.get('topology')).get('pattern'), 64),
    ]
    pieces.extend(_clean_text(_as_dict(participant).get('role') or _as_dict(participant).get('kind'), 64) for participant in participants)
    pieces.extend(_clean_text(_as_dict(participant).get('name'), 64) for participant in participants)
    pieces.extend(_clean_text(surface.get('surface_id'), 64) for surface in surfaces)
    pieces.extend(_clean_text(surface.get('write_policy'), 64) for surface in surfaces)
    pieces.extend(_clean_text(slot, 64) for surface in surfaces for slot in _as_list(surface.get('semantic_slots')))
    pieces.extend(_clean_text(value, 64) for value in _as_list(catalog.get('tags')))
    pieces.extend(_clean_text(value, 64) for value in _as_list(catalog.get('good_for')))
    return ' '.join(piece for piece in pieces if piece)



def _score_template(task_text: str, manifest: dict[str, Any]) -> dict[str, Any]:
    blueprint = _as_dict(manifest.get('blueprint'))
    summary = _as_dict(manifest.get('summary'))
    title = _clean_text(blueprint.get('title') or summary.get('title') or '')
    description = _clean_text(blueprint.get('description') or '')
    archetype = _clean_text(blueprint.get('task_archetype') or summary.get('task_archetype') or 'general', 64) or 'general'
    feature_text = _blueprint_search_text(blueprint)
    keyword_overlap = _overlap_score(f"{title} {description} {feature_text}", task_text)
    task_lower = task_text.lower()
    implementation_boost = 4 if archetype == 'implementation' and any(token in task_lower for token in ['implement', 'code', 'patch', 'repo', 'fix', 'workspace']) else 0
    review_boost = 4 if archetype == 'review_repair' and any(token in task_lower for token in ['review', 'repair', 'regression', 'bug', 'audit']) else 0
    research_boost = 4 if archetype == 'research' and any(token in task_lower for token in ['research', 'brief', 'analysis', 'investigate']) else 0
    memory_fit = _memory_fit(blueprint)
    topology = _topology_summary(blueprint)
    topology_boost = 1 if topology.get('review_present') else 0
    memory_boost = 1 if memory_fit['final_answer_surface_ready'] else 0
    score = keyword_overlap + implementation_boost + review_boost + research_boost + topology_boost + memory_boost
    rationale = [f'archetype={archetype}', f'keyword_overlap={keyword_overlap}', f'topology={topology["pattern"]}']
    if memory_fit['final_answer_surface_ready']:
        rationale.append('final_answer_surface_ready')
    if memory_fit['surface_count']:
        rationale.append(f'memory_surfaces={memory_fit["surface_count"]}')
    return {
        'score': score,
        'semantic_score': keyword_overlap,
        'feature_score_breakdown': {
            'keyword_overlap': keyword_overlap,
            'implementation_boost': implementation_boost,
            'review_boost': review_boost,
            'research_boost': research_boost,
            'topology_boost': topology_boost,
            'memory_boost': memory_boost,
        },
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
            'feature_score_breakdown': scored['feature_score_breakdown'],
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






def _work_mode_view(value: Any) -> dict[str, Any] | None:
    row = _as_dict(value)
    if not row:
        return None
    return {
        'work_mode': _clean_text(row.get('work_mode') or row.get('mode'), 64) or 'quick_answer',
        'label': _clean_text(row.get('label'), 128) or None,
        'agents_hint': _clean_text(row.get('agents_hint'), 128) or None,
        'context_depth': _clean_text(row.get('context_depth'), 64) or None,
        'team_skeleton': _clean_text(row.get('team_skeleton'), 128) or None,
        'loop_budget': row.get('loop_budget'),
        'stop_condition': _clean_text(row.get('stop_condition'), 128) or None,
        'review_policy': _clean_text(row.get('review_policy'), 64) or None,
        'memory_mode': _clean_text(row.get('memory_mode'), 64) or None,
        'goc_mode': _clean_text(row.get('goc_mode'), 64) or None,
        'explicit': row.get('explicit') is True,
        'reason_codes': [str(v) for v in _as_list(row.get('reason_codes')) if str(v).strip()],
    }

def _memory_import_view(value: Any) -> dict[str, Any] | None:
    row = _as_dict(value)
    if not row:
        return None
    return {
        'import_intent': _clean_text(row.get('import_intent'), 64) or 'none',
        'topic': _clean_text(row.get('topic'), 160) or 'current_topic',
        'target_team': _clean_text(row.get('target_team'), 64) or 'general',
        'projection_profile': _clean_text(row.get('projection_profile'), 64) or 'general',
        'mode': _clean_text(row.get('mode'), 64) or 'snapshot',
        'scope': _clean_text(row.get('scope'), 64) or 'project',
        'previous_result_policy': _clean_text(row.get('previous_result_policy'), 64) or 'optional',
        'fork_policy': _clean_text(row.get('fork_policy'), 64) or 'none',
        'permissions': _as_dict(row.get('permissions')) or {},
        'reason_codes': [str(v) for v in _as_list(row.get('reason_codes')) if str(v).strip()],
    }


def _task_attempt_view(value: Any) -> dict[str, Any] | None:
    row = _as_dict(value)
    if not row:
        return None
    memory = _memory_import_view(row.get('memory_import'))
    work_mode = _work_mode_view(row.get('work_mode'))
    return {
        'task_id': _clean_text(row.get('task_id'), 128) or None,
        'attempt_id': _clean_text(row.get('attempt_id'), 128) or None,
        'parent_attempt_id': _clean_text(row.get('parent_attempt_id'), 128) or None,
        'run_mode': _clean_text(row.get('run_mode'), 64) or 'new',
        'retry_reason': _clean_text(row.get('retry_reason'), 64) or None,
        'reason_codes': [str(v) for v in _as_list(row.get('reason_codes')) if str(v).strip()],
        'target_team': _clean_text(row.get('target_team'), 64) or (memory or {}).get('target_team') or 'general',
        'previous_result_policy': _clean_text(row.get('previous_result_policy'), 64) or _clean_text(_as_dict(row.get('context_policy')).get('previous_result_policy'), 64) or None,
        'context_policy': _as_dict(row.get('context_policy')) or {},
        'work_mode': work_mode,
        'cycle_policy': _as_dict(row.get('cycle_policy')) or {},
        'memory_import': memory,
        'goc': _as_dict(row.get('goc')) or {},
    }

def _user_intent_view(candidate: dict[str, Any]) -> dict[str, Any] | None:
    intent = _as_dict(candidate.get('user_orchestration_intent') or candidate.get('user_team_intent'))
    if not intent:
        return None
    return {
        'team_intent': _clean_text(intent.get('team_intent'), 64) or 'neutral',
        'team_style': _clean_text(intent.get('team_style'), 64) or None,
        'required_roles': [str(v) for v in _as_list(intent.get('required_roles')) if str(v).strip()],
        'min_team_size': int(intent.get('min_team_size') or 1),
        'debt_policy': _clean_text(intent.get('debt_policy'), 64) or None,
        'reason_codes': [str(v) for v in _as_list(intent.get('reason_codes')) if str(v).strip()],
    }


def _advisory_view(candidate: dict[str, Any]) -> dict[str, Any] | None:
    advisory = _as_dict(candidate.get('skeleton_advisory') or candidate.get('learned_skeleton_advisory'))
    if not advisory:
        return None
    labels = _as_dict(advisory.get('labels'))
    score = _as_dict(candidate.get('score'))
    return {
        'status': _clean_text(advisory.get('status'), 64) or None,
        'source': _clean_text(advisory.get('source'), 64) or None,
        'utility_label': _clean_text(labels.get('Y_UTIL'), 32) or None,
        'debt_label': _clean_text(labels.get('Y_DEBT'), 32) or None,
        'frontier_needed': _clean_text(labels.get('Y_FRONTIER_NEEDED'), 32) or None,
        'capacity_gaps': [str(v) for v in _as_list(advisory.get('capacity_gaps')) if str(v).strip()],
        'warnings': [str(v) for v in _as_list(advisory.get('warnings')) if str(v).strip()],
        'confidence': advisory.get('confidence') if isinstance(advisory.get('confidence'), (int, float)) else None,
        'fused_utility': score.get('fused_utility') if isinstance(score.get('fused_utility'), (int, float)) else None,
        'base_utility': score.get('base_utility') if isinstance(score.get('base_utility'), (int, float)) else None,
        'learned_delta': score.get('learned_delta') if isinstance(score.get('learned_delta'), (int, float)) else None,
        'advisory_mode': _clean_text(score.get('advisory_mode') or advisory.get('mode'), 64) or None,
        'user_intent_match': score.get('user_intent_match') if isinstance(score.get('user_intent_match'), bool) else None,
        'user_intent_bonus': score.get('user_intent_bonus') if isinstance(score.get('user_intent_bonus'), (int, float)) else None,
        'user_requested_overhead_discount': score.get('user_requested_overhead_discount') if isinstance(score.get('user_requested_overhead_discount'), (int, float)) else None,
        'user_team_intent': _clean_text(score.get('user_team_intent'), 64) or None,
        'user_team_style': _clean_text(score.get('user_team_style'), 64) or None,
        'missing_user_required_roles': [str(v) for v in _as_list(score.get('missing_user_required_roles')) if str(v).strip()],
    }


def _candidate_training_view(candidate: dict[str, Any]) -> dict[str, Any]:
    memory_fit = _as_dict(candidate.get('memory_fit'))
    topology = _as_dict(candidate.get('topology'))
    executable = _executable_features(candidate)
    return {
        'template_id': _clean_text(candidate.get('template_id') or candidate.get('blueprint_id'), 128) or None,
        'title': _clean_text(candidate.get('title'), 160) or None,
        'task_archetype': _clean_text(candidate.get('task_archetype'), 64) or 'general',
        'score': float(candidate.get('score') or candidate.get('semantic_score') or 0),
        'semantic_score': float(candidate.get('semantic_score') or 0),
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
        'feature_score_breakdown': {
            str(key): float(value or 0)
            for key, value in _as_dict(candidate.get('feature_score_breakdown')).items()
            if str(key).strip()
        },
        'skeleton_advisory': _advisory_view(candidate),
        'user_orchestration_intent': _user_intent_view(candidate),
        'user_intent_satisfaction': _as_dict(candidate.get('user_intent_satisfaction')) or None,
        'task_attempt_plan': _task_attempt_view(candidate.get('task_attempt_plan')),
        'work_mode': _work_mode_view(candidate.get('work_mode') or _as_dict(candidate.get('task_attempt_plan')).get('work_mode')),
        'work_mode_satisfaction': _as_dict(candidate.get('work_mode_satisfaction')) or None,
        'task_attempt_satisfaction': _as_dict(candidate.get('task_attempt_satisfaction')) or None,
        'memory_import_intent': _memory_import_view(candidate.get('memory_import_intent')),
        'target_team': _clean_text(candidate.get('target_team'), 64) or None,
        'previous_result_policy': _clean_text(candidate.get('previous_result_policy'), 64) or None,
        'rationale': [str(v) for v in _as_list(candidate.get('rationale')) if str(v).strip()],
    }



def _recommendation_alignment(*, selected_found: bool, selected_rank: int | None, candidate_count: int) -> str:
    if candidate_count <= 0:
        return 'no_recommendation'
    if not selected_found:
        return 'off_recommendation'
    if selected_rank == 1:
        return 'top_pick'
    if selected_rank is not None:
        return 'in_candidates'
    return 'selected_snapshot_only'



def _selected_candidate_lookup(row: dict[str, Any], recommendation: dict[str, Any], candidates: list[dict[str, Any]]) -> tuple[str | None, dict[str, Any] | None, bool, str | None]:
    selected_blueprint_id = _clean_text(row.get('selected_blueprint_id'), 128) or None
    selected_snapshot = _as_dict(row.get('selected_candidate_snapshot') or recommendation.get('selected_candidate_snapshot'))
    selected_by_id = next(
        (
            candidate for candidate in candidates
            if _clean_text(candidate.get('template_id') or candidate.get('blueprint_id'), 128) == selected_blueprint_id
        ),
        None,
    ) if selected_blueprint_id else None
    snapshot_id = _clean_text(selected_snapshot.get('template_id') or selected_snapshot.get('blueprint_id'), 128) or None
    inferred_id = selected_blueprint_id or snapshot_id or None
    selected_candidate = selected_by_id or (selected_snapshot if snapshot_id else None)
    selected_found = bool(selected_candidate) and (
        not selected_blueprint_id
        or _clean_text(selected_candidate.get('template_id') or selected_candidate.get('blueprint_id'), 128) == selected_blueprint_id
        or snapshot_id == selected_blueprint_id
    )
    selected_source = 'recommendation_candidates' if selected_by_id else ('selected_candidate_snapshot' if snapshot_id else None)
    return inferred_id, selected_candidate, selected_found, selected_source



def build_team_selection_dataset(events: Any) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    archetype_counts: dict[str, int] = {}
    success_counts: dict[str, int] = {'success': 0, 'failure': 0}
    exclusion_reason_counts: dict[str, int] = {}
    alignment_counts: dict[str, int] = {}
    alignment_success_counts: dict[str, int] = {}
    alignment_quality_sums: dict[str, float] = {}
    alignment_gap_sums: dict[str, float] = {}
    alignment_gap_counts: dict[str, int] = {}
    alignment_event_samples: dict[str, list[dict[str, Any]]] = {}
    human_override_count = 0
    memory_fit_failure_count = 0
    advisory_status_counts: dict[str, int] = {}
    advisory_debt_counts: dict[str, int] = {}
    advisory_capacity_gap_counts: dict[str, int] = {}
    attempt_run_mode_counts: dict[str, int] = {}
    memory_import_profile_counts: dict[str, int] = {}
    work_mode_counts: dict[str, int] = {}
    work_mode_review_policy_counts: dict[str, int] = {}
    eligible_count = 0
    excluded_count = 0
    for item in _as_list(events):
        row = _as_dict(item)
        recommendation = _as_dict(row.get('recommendation'))
        task_attempt = _task_attempt_view(row.get('task_attempt_plan') or recommendation.get('task_attempt_plan'))
        work_mode = _work_mode_view(row.get('work_mode') or recommendation.get('work_mode') or (task_attempt or {}).get('work_mode'))
        memory_import = _memory_import_view(row.get('memory_import_intent') or recommendation.get('memory_import_intent') or (task_attempt or {}).get('memory_import'))
        if task_attempt:
            mode_key = task_attempt.get('run_mode') or 'new'
            attempt_run_mode_counts[mode_key] = attempt_run_mode_counts.get(mode_key, 0) + 1
        if work_mode:
            work_mode_key = work_mode.get('work_mode') or 'quick_answer'
            work_mode_counts[work_mode_key] = work_mode_counts.get(work_mode_key, 0) + 1
            review_key = work_mode.get('review_policy') or 'none'
            work_mode_review_policy_counts[review_key] = work_mode_review_policy_counts.get(review_key, 0) + 1
        if memory_import and memory_import.get('import_intent') != 'none':
            profile_key = memory_import.get('projection_profile') or 'general'
            memory_import_profile_counts[profile_key] = memory_import_profile_counts.get(profile_key, 0) + 1
        outcome = _as_dict(row.get('outcome'))
        candidates = [_as_dict(candidate) for candidate in _as_list(recommendation.get('candidates'))]
        selected_blueprint_id, selected_candidate, selected_candidate_found, selected_candidate_source = _selected_candidate_lookup(row, recommendation, candidates)
        task_text = _clean_text(row.get('task_text'), 1000)
        task_archetype = _clean_text((selected_candidate.get('task_archetype') if selected_candidate_found and selected_candidate else '') or recommendation.get('task_archetype') or _as_dict(candidates[0]).get('task_archetype') or outcome.get('task_archetype') or 'general', 64) or 'general'
        archetype_counts[task_archetype] = archetype_counts.get(task_archetype, 0) + 1
        success = outcome.get('success') is True
        success_counts['success' if success else 'failure'] += 1
        exclusion_reasons: list[str] = []
        if not selected_blueprint_id:
            exclusion_reasons.append('missing_selected_blueprint_id')
        if selected_blueprint_id and not selected_candidate_found:
            exclusion_reasons.append('selected_candidate_not_in_recommendation')
        if not candidates:
            exclusion_reasons.append('missing_recommendation_candidates')
        training_eligible = len(exclusion_reasons) == 0
        if training_eligible:
            eligible_count += 1
        else:
            excluded_count += 1
            for reason in exclusion_reasons:
                exclusion_reason_counts[reason] = exclusion_reason_counts.get(reason, 0) + 1
        selected_features = _candidate_training_view(selected_candidate) if selected_candidate_found and selected_candidate else None
        candidate_features = [_candidate_training_view(candidate) for candidate in candidates[:8]]
        for feature in candidate_features:
            advisory = _as_dict(feature.get('skeleton_advisory'))
            if advisory:
                status_key = _clean_text(advisory.get('status'), 64) or 'unknown'
                advisory_status_counts[status_key] = advisory_status_counts.get(status_key, 0) + 1
                debt_key = _clean_text(advisory.get('debt_label'), 32) or 'unknown'
                advisory_debt_counts[debt_key] = advisory_debt_counts.get(debt_key, 0) + 1
                for gap in _as_list(advisory.get('capacity_gaps')):
                    gap_key = _clean_text(gap, 64) or 'unknown'
                    advisory_capacity_gap_counts[gap_key] = advisory_capacity_gap_counts.get(gap_key, 0) + 1
        selected_rank = next(
            (
                index + 1
                for index, candidate in enumerate(candidates)
                if _clean_text(candidate.get('template_id') or candidate.get('blueprint_id'), 128) == selected_blueprint_id
            ),
            None,
        ) if selected_blueprint_id else None
        recommendation_alignment = _recommendation_alignment(
            selected_found=selected_candidate_found,
            selected_rank=selected_rank,
            candidate_count=len(candidates),
        )
        recommended_candidates = candidate_features[:5]
        top_recommended_candidate = recommended_candidates[0] if recommended_candidates else None
        recommendation_gap = None
        if top_recommended_candidate and selected_features:
            recommendation_gap = float(top_recommended_candidate.get('score') or 0) - float(selected_features.get('score') or 0)
        alignment_key = recommendation_alignment or 'unknown'
        alignment_counts[alignment_key] = alignment_counts.get(alignment_key, 0) + 1
        quality_score = float(outcome.get('quality_score') or 0)
        token_cost = float(outcome.get('token_cost') or 0)
        latency_ms = float(outcome.get('latency_ms') or 0)
        recovery_count = int(outcome.get('recovery_count') or 0)
        approval_friction = float(outcome.get('approval_friction') or 0)
        artifact_quality = float(outcome.get('artifact_quality') or quality_score or 0)
        human_override_reason = _clean_text(outcome.get('human_override_reason'), 256) or None
        memory_fit_failure = outcome.get('memory_fit_failure') is True
        if outcome.get('human_override') is True:
            human_override_count += 1
        if memory_fit_failure:
            memory_fit_failure_count += 1
        if success:
            alignment_success_counts[alignment_key] = alignment_success_counts.get(alignment_key, 0) + 1
        alignment_quality_sums[alignment_key] = alignment_quality_sums.get(alignment_key, 0.0) + artifact_quality
        if recommendation_gap is not None:
            alignment_gap_sums[alignment_key] = alignment_gap_sums.get(alignment_key, 0.0) + float(recommendation_gap)
            alignment_gap_counts[alignment_key] = alignment_gap_counts.get(alignment_key, 0) + 1
        event_id = _clean_text(row.get('id'), 128) or None
        thread_id = _clean_text(row.get('thread_id'), 128) or None
        run_id = _clean_text(row.get('run_id'), 128) or None
        created_at = row.get('created_at')
        row_payload = {
            'event_id': event_id,
            'thread_id': thread_id,
            'run_id': run_id,
            'task_text': task_text,
            'task_archetype': task_archetype,
            'selected_blueprint_id': selected_blueprint_id,
            'selected_candidate_found': selected_candidate_found,
            'selected_candidate_source': selected_candidate_source,
            'selected_candidate_rank': selected_rank,
            'recommendation_alignment': recommendation_alignment,
            'candidate_count': len(candidates),
            'training_eligible': training_eligible,
            'exclusion_reasons': exclusion_reasons,
            'recommended_candidates': recommended_candidates,
            'top_recommended_candidate': top_recommended_candidate,
            'recommendation_gap': recommendation_gap,
            'task_attempt_plan': task_attempt,
            'work_mode': work_mode,
            'memory_import_intent': memory_import,
            'selected_score': selected_features.get('score') if selected_features else None,
            'selected_topology_pattern': selected_features.get('topology_pattern') if selected_features else None,
            'selected_memory_surface_count': selected_features.get('surface_count') if selected_features else None,
            'selected_final_answer_surface_ready': selected_features.get('final_answer_surface_ready') if selected_features else None,
            'selected_member_count': selected_features.get('member_count') if selected_features else None,
            'selected_role_ids': selected_features.get('role_ids') if selected_features else [],
            'selected_ready': selected_features.get('ready') if selected_features else None,
            'selected_runtime_bound': selected_features.get('runtime_bound') if selected_features else None,
            'selected_blocking_reason_codes': selected_features.get('blocking_reason_codes') if selected_features else [],
            'selected_degrade_reason_codes': selected_features.get('degrade_reason_codes') if selected_features else [],
            'candidate_features': candidate_features,
            'input_features': {
                'task_text': task_text,
                'task_archetype': task_archetype,
                'candidate_count': len(candidates),
            },
            'selected_features': selected_features,
            'outcome_labels': {
                'success': success,
                'quality_score': quality_score,
                'artifact_quality': artifact_quality,
                'token_cost': token_cost,
                'latency_ms': latency_ms,
                'human_override': outcome.get('human_override') is True,
                'human_override_reason': human_override_reason,
                'recovery_count': recovery_count,
                'approval_friction': approval_friction,
                'memory_fit_failure': memory_fit_failure,
            },
            'success': success,
            'quality_score': quality_score,
            'artifact_quality': artifact_quality,
            'token_cost': token_cost,
            'latency_ms': latency_ms,
            'human_override': outcome.get('human_override'),
            'human_override_reason': human_override_reason,
            'recovery_count': recovery_count,
            'approval_friction': approval_friction,
            'memory_fit_failure': memory_fit_failure,
            'created_at': created_at,
        }
        rows.append(row_payload)
        sample_rows = alignment_event_samples.setdefault(alignment_key, [])
        if len(sample_rows) < 3:
            sample_rows.append({
                'event_id': event_id,
                'run_id': run_id,
                'created_at': created_at,
                'selected_blueprint_id': selected_blueprint_id,
                'recommendation_alignment': recommendation_alignment,
                'success': success,
                'artifact_quality': artifact_quality,
                'recommendation_gap': recommendation_gap,
                'training_eligible': training_eligible,
                'exclusion_reasons': exclusion_reasons,
            })
    selection_outcome_summary = {
        'alignment_counts': alignment_counts,
        'success_rate_by_alignment': {
            key: (float(alignment_success_counts.get(key, 0)) / float(count) if count else 0.0)
            for key, count in alignment_counts.items()
        },
        'average_artifact_quality_by_alignment': {
            key: (float(alignment_quality_sums.get(key, 0.0)) / float(count) if count else 0.0)
            for key, count in alignment_counts.items()
        },
        'average_recommendation_gap_by_alignment': {
            key: (float(alignment_gap_sums.get(key, 0.0)) / float(alignment_gap_counts.get(key, 0)) if alignment_gap_counts.get(key, 0) else None)
            for key in alignment_counts.keys()
        },
        'human_override_count': human_override_count,
        'memory_fit_failure_count': memory_fit_failure_count,
        'advisory_status_counts': advisory_status_counts,
        'advisory_debt_counts': advisory_debt_counts,
        'advisory_capacity_gap_counts': advisory_capacity_gap_counts,
        'attempt_run_mode_counts': attempt_run_mode_counts,
        'memory_import_profile_counts': memory_import_profile_counts,
        'work_mode_counts': work_mode_counts,
        'work_mode_review_policy_counts': work_mode_review_policy_counts,
        'alignment_event_samples': alignment_event_samples,
    }
    return {
        'kind': 'team_selection_dataset_v1',
        'schema_version': 7,
        'count': len(rows),
        'eligible_count': eligible_count,
        'excluded_count': excluded_count,
        'archetype_counts': archetype_counts,
        'success_counts': success_counts,
        'exclusion_reason_counts': exclusion_reason_counts,
        'selection_outcome_summary': selection_outcome_summary,
        'rows': rows,
    }



def serialize_team_selection_dataset_jsonl(events: Any) -> str:
    dataset = build_team_selection_dataset(events)
    return '\n'.join(json.dumps(row, ensure_ascii=False) for row in dataset.get('rows') or [] if row.get('training_eligible') is not False)
