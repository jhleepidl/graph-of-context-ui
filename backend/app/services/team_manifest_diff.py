from __future__ import annotations

from typing import Any

from app.services.team_manifest import (
    _as_dict,
    _as_list,
    _clean_text,
    _normalize_manifest,
    _normalize_memory_plan,
    _normalize_install_actions,
    _normalize_install_proposal,
    _normalize_install_proposal_state,
    _normalize_credential_binding_state,
    _normalize_runtime_execution_policy,
    _normalize_structure_v2,
    _normalize_team_payload,
    _derive_team_from_structure_v2,
)


def _agent_index(team_payload: Any) -> dict[str, dict[str, Any]]:
    team = _as_dict(team_payload)
    out: dict[str, dict[str, Any]] = {}
    for raw_agent in _as_list(team.get("agents")):
        agent = _as_dict(raw_agent)
        agent_id = _clean_text(agent.get("agent_id") or agent.get("agentId") or agent.get("id") or agent.get("name"), max_len=128)
        if agent_id:
            out[agent_id] = agent
    return out


def _requirement_key_set(requirements_payload: Any, *, kind: str) -> set[str]:
    requirements = _as_dict(requirements_payload)
    key_name = {
        "tools": "tool_id",
        "credentials": "credential_key",
        "skills": "skill_id",
    }.get(kind, "")
    out: set[str] = set()
    if not key_name:
        return out
    for raw in _as_list(requirements.get(kind)):
        row = _as_dict(raw)
        value = _clean_text(row.get(key_name), max_len=128).lower()
        if value:
            out.add(value)
    return out


def _select_manifest_team(manifest_payload: Any, apply_state: str) -> dict[str, Any]:
    manifest = _as_dict(manifest_payload)
    team_config = _as_dict(manifest.get("team_config"))
    structure = _as_dict(manifest.get('structure_v2') or manifest.get('structureV2'))
    if structure and _as_list(structure.get('participants')):
        return _normalize_team_payload(_derive_team_from_structure_v2(structure))
    if apply_state == "pending":
        team = _normalize_team_payload(team_config.get("pending_team"))
        if team.get("agents"):
            return team
    else:
        team = _normalize_team_payload(team_config.get("active_team"))
        if team.get("agents"):
            return team
    return _normalize_team_payload(manifest.get("team"))


def _participant_index(structure_payload: Any) -> dict[str, dict[str, Any]]:
    structure = _as_dict(structure_payload)
    out: dict[str, dict[str, Any]] = {}
    for raw in _as_list(structure.get('participants')):
        row = _as_dict(raw)
        participant_id = _clean_text(row.get('participant_id') or row.get('participantId') or row.get('id'), max_len=128)
        if participant_id:
            out[participant_id] = row
    return out


def _surface_index(memory_plan_payload: Any) -> dict[str, dict[str, Any]]:
    plan = _normalize_memory_plan(memory_plan_payload)
    out: dict[str, dict[str, Any]] = {}
    for raw in _as_list(plan.get('surfaces')):
        row = _as_dict(raw)
        surface_id = _clean_text(row.get('surface_id') or row.get('id'), max_len=64).lower()
        if surface_id:
            out[surface_id] = row
    return out


def _list_ids(value: Any, *, max_len: int = 128) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in _as_list(value):
        clean = _clean_text(raw, max_len=max_len).lower()
        if clean and clean not in seen:
            seen.add(clean)
            out.append(clean)
    return out


def _participant_label(row: Any, participant_id: str = '') -> str:
    item = _as_dict(row)
    return (
        _clean_text(item.get('name'), max_len=160)
        or _clean_text(item.get('label'), max_len=160)
        or _clean_text(item.get('participant_id') or item.get('participantId') or participant_id, max_len=160)
        or participant_id
        or 'participant'
    )


def _surface_matches_publish_target(surface: Any, target: str) -> bool:
    surface_dict = _as_dict(surface)
    target_id = _clean_text(target, max_len=128).lower()
    if not target_id:
        return False
    surface_id = _clean_text(surface_dict.get('surface_id') or surface_dict.get('id'), max_len=128).lower()
    if surface_id and surface_id == target_id:
        return True
    semantic_slots = _list_ids(surface_dict.get('semantic_slots') or surface_dict.get('semanticSlots'), max_len=128)
    return target_id in semantic_slots


def _role_can_publish_surface(structure: Any, role: str, target: str) -> bool:
    structure_dict = _as_dict(structure)
    role_id = _clean_text(role, max_len=64).lower()
    target_id = _clean_text(target, max_len=128).lower()
    if not role_id or not target_id:
        return False
    memory_plan = _normalize_memory_plan(_as_dict(structure_dict.get('memory_plan')))
    for surface in _as_list(memory_plan.get('surfaces')):
        surface_dict = _as_dict(surface)
        if not _surface_matches_publish_target(surface_dict, target_id):
            continue
        write_policy = _clean_text(surface_dict.get('write_policy') or surface_dict.get('writePolicy') or 'shared', max_len=64).lower()
        if target_id == 'final_answer' and write_policy not in {'final', 'shared', 'append_only'}:
            continue
        if target_id == 'artifact_index' and write_policy not in {'index', 'shared', 'append_only'}:
            continue
        target_roles = _list_ids(surface_dict.get('target_roles') or surface_dict.get('targetRoles'), max_len=64)
        if not target_roles or role_id in target_roles:
            return True
    return False


def _summarize_publish_contract_issues(structure: Any) -> dict[str, Any]:
    structure_dict = _normalize_structure_v2(structure, team_payload={}, apply_state='active')
    participants = _as_list(structure_dict.get('participants'))
    control_policy = _as_dict(structure_dict.get('control_policy'))
    topology = _as_dict(structure_dict.get('topology'))
    final_owner_id = _clean_text(
        control_policy.get('final_answer_owner_participant_id')
        or control_policy.get('finalAnswerOwnerParticipantId')
        or topology.get('final_participant_id')
        or topology.get('finalParticipantId'),
        max_len=128,
    )
    final_owner = next((row for row in participants if _clean_text(_as_dict(row).get('participant_id') or _as_dict(row).get('agent_id') or _as_dict(row).get('id'), max_len=128) == final_owner_id), None)
    final_owner_role = _clean_text(_as_dict(final_owner).get('role'), max_len=64).lower()
    final_owner_missing = not bool(final_owner_id) or final_owner is None
    final_owner_publish_blocked = final_owner_missing or (not final_owner_role or not _role_can_publish_surface(structure_dict, final_owner_role, 'final_answer'))
    artifact_publisher_rows = [
        row for row in participants
        if _role_can_publish_surface(structure_dict, _clean_text(_as_dict(row).get('role'), max_len=64).lower(), 'artifact_index')
    ]
    artifact_publishers = [
        _clean_text(_as_dict(row).get('name') or _as_dict(row).get('participant_id') or _as_dict(row).get('agent_id'), max_len=160)
        for row in artifact_publisher_rows
    ]
    artifact_publishers = [label for label in artifact_publishers if label]
    artifact_publisher_ids = [
        _clean_text(_as_dict(row).get('participant_id') or _as_dict(row).get('agent_id') or _as_dict(row).get('id') or _as_dict(row).get('name'), max_len=160)
        for row in artifact_publisher_rows
    ]
    artifact_publisher_ids = [label.lower() for label in artifact_publisher_ids if label]
    return {
        'final_owner_missing': final_owner_missing,
        'final_owner_id': _clean_text(_as_dict(final_owner).get('participant_id') or _as_dict(final_owner).get('agent_id') or _as_dict(final_owner).get('id') or final_owner_id, max_len=160),
        'final_owner_publish_blocked': final_owner_publish_blocked,
        'final_owner_publish_label': _clean_text(_as_dict(final_owner).get('name') or final_owner_id, max_len=160),
        'artifact_publish_missing': len(artifact_publishers) == 0,
        'artifact_publishers': artifact_publishers,
        'artifact_publisher_ids': artifact_publisher_ids,
    }


def _build_guardrails(current_manifest: Any, candidate_manifest: Any, apply_state: str = 'active') -> dict[str, Any]:
    clean_state = 'pending' if str(apply_state or 'active').strip().lower() == 'pending' else 'active'
    current = _normalize_manifest(current_manifest, fallback_apply_state=clean_state)
    candidate = _normalize_manifest(candidate_manifest, fallback_apply_state=clean_state)
    current_structure = _as_dict(current.get('structure_v2'))
    candidate_structure = _as_dict(candidate.get('structure_v2'))
    current_team = _select_manifest_team(current, clean_state)
    candidate_team = _select_manifest_team(candidate, clean_state)
    current_participants = _participant_index(current_structure)
    candidate_participants = _participant_index(candidate_structure)
    current_pids = set(current_participants.keys())
    candidate_pids = set(candidate_participants.keys())
    removed_participants = sorted(current_pids - candidate_pids)
    added_participants = sorted(candidate_pids - current_pids)
    shared_pids = sorted(current_pids & candidate_pids)

    current_agent_roles = {_clean_text(_as_dict(item).get('role'), max_len=64).lower() for item in _as_list(_as_dict(current_team).get('agents')) if _clean_text(_as_dict(item).get('role'), max_len=64)}
    candidate_agent_roles = {_clean_text(_as_dict(item).get('role'), max_len=64).lower() for item in _as_list(_as_dict(candidate_team).get('agents')) if _clean_text(_as_dict(item).get('role'), max_len=64)}
    lost_role_coverage = sorted(current_agent_roles - candidate_agent_roles)

    current_final = _clean_text(_as_dict(current_structure.get('topology')).get('final_participant_id') or _as_dict(current_structure.get('topology')).get('finalParticipantId'), max_len=128)
    candidate_final = _clean_text(_as_dict(candidate_structure.get('topology')).get('final_participant_id') or _as_dict(candidate_structure.get('topology')).get('finalParticipantId'), max_len=128)
    current_final_owner = _clean_text(_as_dict(current_structure.get('control_policy')).get('final_answer_owner_participant_id') or _as_dict(current_structure.get('control_policy')).get('finalAnswerOwnerParticipantId'), max_len=128)
    candidate_final_owner = _clean_text(_as_dict(candidate_structure.get('control_policy')).get('final_answer_owner_participant_id') or _as_dict(candidate_structure.get('control_policy')).get('finalAnswerOwnerParticipantId'), max_len=128)

    role_changes: list[dict[str, Any]] = []
    provider_drops: list[dict[str, Any]] = []
    model_drops: list[dict[str, Any]] = []
    required_tool_drops: list[dict[str, Any]] = []
    optional_tool_drops: list[dict[str, Any]] = []
    for participant_id in shared_pids:
        before = _as_dict(current_participants.get(participant_id))
        after = _as_dict(candidate_participants.get(participant_id))
        before_role = _clean_text(before.get('role'), max_len=64).lower()
        after_role = _clean_text(after.get('role'), max_len=64).lower()
        if before_role and after_role and before_role != after_role:
            role_changes.append({
                'participant_id': participant_id,
                'label': _participant_label(after or before, participant_id),
                'before_role': before_role,
                'after_role': after_role,
            })
        before_provider = _clean_text(before.get('provider'), max_len=64).lower()
        after_provider = _clean_text(after.get('provider'), max_len=64).lower()
        if before_provider and not after_provider:
            provider_drops.append({'participant_id': participant_id, 'label': _participant_label(before, participant_id), 'provider': before_provider})
        before_model = _clean_text(before.get('model'), max_len=160)
        after_model = _clean_text(after.get('model'), max_len=160)
        if before_model and not after_model:
            model_drops.append({'participant_id': participant_id, 'label': _participant_label(before, participant_id), 'model': before_model})
        before_required = set(_list_ids(before.get('required_tool_ids') or before.get('requiredToolIds')))
        after_required = set(_list_ids(after.get('required_tool_ids') or after.get('requiredToolIds')))
        removed_required = sorted(before_required - after_required)
        if removed_required:
            required_tool_drops.append({'participant_id': participant_id, 'label': _participant_label(before, participant_id), 'tools': removed_required})
        before_optional = set(_list_ids(before.get('optional_tool_ids') or before.get('optionalToolIds') or before.get('recommended_tool_ids') or before.get('recommendedToolIds')))
        after_optional = set(_list_ids(after.get('optional_tool_ids') or after.get('optionalToolIds') or after.get('recommended_tool_ids') or after.get('recommendedToolIds')))
        removed_optional = sorted(before_optional - after_optional)
        if removed_optional:
            optional_tool_drops.append({'participant_id': participant_id, 'label': _participant_label(before, participant_id), 'tools': removed_optional})

    current_plan = _normalize_memory_plan(_as_dict(current_structure.get('memory_plan')))
    candidate_plan = _normalize_memory_plan(_as_dict(candidate_structure.get('memory_plan')))
    current_surfaces = _surface_index(current_plan)
    candidate_surfaces = _surface_index(candidate_plan)
    removed_surfaces = sorted(set(current_surfaces.keys()) - set(candidate_surfaces.keys()))
    current_default_load = set(_list_ids(current_plan.get('default_load_surface_ids') or current_plan.get('defaultLoadSurfaceIds'), max_len=64))
    candidate_default_load = set(_list_ids(candidate_plan.get('default_load_surface_ids') or candidate_plan.get('defaultLoadSurfaceIds'), max_len=64))
    current_writable = set(_list_ids(current_plan.get('writable_surface_ids') or current_plan.get('writableSurfaceIds'), max_len=64))
    candidate_writable = set(_list_ids(candidate_plan.get('writable_surface_ids') or candidate_plan.get('writableSurfaceIds'), max_len=64))
    removed_default_load = sorted(current_default_load - candidate_default_load)
    removed_writable = sorted(current_writable - candidate_writable)
    candidate_publish_issues = _summarize_publish_contract_issues(candidate_structure)

    warnings: list[str] = []
    if removed_participants:
        labels = [_participant_label(current_participants.get(pid), pid) for pid in removed_participants]
        warnings.append(f"Removing participants: {', '.join(labels)}")
    if lost_role_coverage:
        warnings.append(f"Losing role coverage: {', '.join(lost_role_coverage)}")
    for entry in role_changes[:8]:
        warnings.append(f"Changing participant role: {entry['label']} ({entry['before_role']} → {entry['after_role']})")
    if current_final and current_final != candidate_final:
        warnings.append(f"Changing final participant: {_participant_label(current_participants.get(current_final), current_final)} → {_participant_label(candidate_participants.get(candidate_final), candidate_final)}")
    if current_final_owner and current_final_owner != candidate_final_owner:
        warnings.append(f"Changing final answer owner: {_participant_label(current_participants.get(current_final_owner), current_final_owner)} → {_participant_label(candidate_participants.get(candidate_final_owner), candidate_final_owner)}")
    if provider_drops:
        warnings.append('Dropping provider hints: ' + ', '.join(f"{entry['label']} ({entry['provider']})" for entry in provider_drops[:8]))
    if model_drops:
        warnings.append('Dropping model hints: ' + ', '.join(f"{entry['label']} ({entry['model']})" for entry in model_drops[:8]))
    for entry in required_tool_drops[:8]:
        warnings.append(f"Removing required tools from {entry['label']}: {', '.join(entry['tools'])}")
    for entry in optional_tool_drops[:8]:
        warnings.append(f"Removing optional/recommended tools from {entry['label']}: {', '.join(entry['tools'])}")
    if removed_surfaces:
        warnings.append(f"Removing memory surfaces: {', '.join(removed_surfaces)}")
    if removed_default_load:
        warnings.append(f"Removing default-load memory surfaces: {', '.join(removed_default_load)}")
    if removed_writable:
        warnings.append(f"Removing writable memory surfaces: {', '.join(removed_writable)}")
    if candidate_publish_issues.get('final_owner_missing'):
        warnings.append('Final answer owner is not declared for final publish handoff.')
    elif candidate_publish_issues['final_owner_publish_blocked']:
        warnings.append(f"Final answer owner cannot publish final_answer: {candidate_publish_issues['final_owner_publish_label'] or 'unknown owner'}")
    if candidate_publish_issues['artifact_publish_missing']:
        warnings.append('No participant can publish artifact_index for final artifact delivery.')

    destructive = bool(
        removed_participants
        or lost_role_coverage
        or role_changes
        or removed_surfaces
        or removed_writable
        or required_tool_drops
        or current_final != candidate_final and current_final
        or current_final_owner != candidate_final_owner and current_final_owner
        or candidate_publish_issues.get('final_owner_missing')
        or candidate_publish_issues['final_owner_publish_blocked']
        or candidate_publish_issues['artifact_publish_missing']
    )
    risk_level = 'low'
    if destructive or len(warnings) >= 3:
        risk_level = 'high'
    elif warnings:
        risk_level = 'medium'

    if candidate_publish_issues.get('final_owner_missing'):
        recommended_action = 'fix_publish_contract'
        summary_line = 'A final answer owner is not declared. Fix the publish contract before installing.'
    elif candidate_publish_issues['final_owner_publish_blocked']:
        recommended_action = 'fix_publish_contract'
        summary_line = 'The declared final answer owner cannot publish final_answer. Fix the publish contract before installing.'
    elif candidate_publish_issues['artifact_publish_missing']:
        recommended_action = 'fix_publish_contract'
        summary_line = 'No participant can publish artifact_index. Fix the publish contract before installing.'
    elif risk_level == 'high' and destructive:
        recommended_action = 'review_and_confirm_install'
        summary_line = 'This install includes destructive team changes. Review the warnings and confirm once more before applying.'
    elif warnings:
        recommended_action = 'review_warnings'
        summary_line = f'This install has {len(warnings)} guardrail warning(s). Review the diff before applying.'
    else:
        recommended_action = 'safe_to_install'
        summary_line = 'No destructive guardrail changes detected.'

    return {
        'risk_level': risk_level,
        'warning_count': len(warnings),
        'recommended_action': recommended_action,
        'summary_line': summary_line,
        'destructive_change_count': int(bool(removed_participants)) + int(bool(lost_role_coverage)) + len(role_changes) + int(bool(removed_surfaces)) + int(bool(removed_writable)) + len(required_tool_drops),
        'destructive_changes_present': destructive,
        'warnings': warnings,
        'issues': {
            'removed_participants': removed_participants,
            'added_participants': added_participants,
            'lost_role_coverage': lost_role_coverage,
            'role_changes': role_changes,
            'provider_drops': provider_drops,
            'model_drops': model_drops,
            'required_tool_drops': required_tool_drops,
            'optional_tool_drops': optional_tool_drops,
            'removed_memory_surfaces': removed_surfaces,
            'removed_default_load_surfaces': removed_default_load,
            'removed_writable_surfaces': removed_writable,
            'final_participant_changed': bool(current_final and current_final != candidate_final),
            'final_answer_owner_changed': bool(current_final_owner and current_final_owner != candidate_final_owner),
            'final_owner_missing': bool(candidate_publish_issues.get('final_owner_missing')),
            'final_owner_publish_blocked': bool(candidate_publish_issues.get('final_owner_publish_blocked')),
            'artifact_publish_missing': bool(candidate_publish_issues.get('artifact_publish_missing')),
        },
    }


def diff_team_manifest_payload(current_manifest: Any, candidate_manifest: Any, apply_state: str = "active") -> dict[str, Any]:
    clean_state = "pending" if str(apply_state or "active").strip().lower() == "pending" else "active"
    current = _normalize_manifest(current_manifest, fallback_apply_state=clean_state)
    candidate = _normalize_manifest(candidate_manifest, fallback_apply_state=clean_state)

    current_team = _select_manifest_team(current, clean_state)
    candidate_team = _select_manifest_team(candidate, clean_state)
    current_agents = _agent_index(current_team)
    candidate_agents = _agent_index(candidate_team)
    current_ids = set(current_agents.keys())
    candidate_ids = set(candidate_agents.keys())

    added_agents = sorted(candidate_ids - current_ids)
    removed_agents = sorted(current_ids - candidate_ids)
    shared_agents = sorted(current_ids & candidate_ids)
    changed_agents = []
    unchanged_agents = []
    for agent_id in shared_agents:
        before = current_agents.get(agent_id) or {}
        after = candidate_agents.get(agent_id) or {}
        if before == after:
            unchanged_agents.append(agent_id)
        else:
            changed_agents.append(agent_id)

    current_requirements = _as_dict(current.get("requirements"))
    candidate_requirements = _as_dict(candidate.get("requirements"))
    current_tools = _requirement_key_set(current_requirements, kind="tools")
    candidate_tools = _requirement_key_set(candidate_requirements, kind="tools")
    current_credentials = _requirement_key_set(current_requirements, kind="credentials")
    candidate_credentials = _requirement_key_set(candidate_requirements, kind="credentials")
    current_skills = _requirement_key_set(current_requirements, kind="skills")
    candidate_skills = _requirement_key_set(candidate_requirements, kind="skills")

    current_binding = _normalize_credential_binding_state(current.get('credential_binding_state'))
    candidate_binding = _normalize_credential_binding_state(candidate.get('credential_binding_state'))
    current_bound_keys = set(str(v).lower() for v in _as_list(current_binding.get('bound_keys')) if _clean_text(v, max_len=128))
    candidate_bound_keys = set(str(v).lower() for v in _as_list(candidate_binding.get('bound_keys')) if _clean_text(v, max_len=128))

    current_install_proposal = _normalize_install_proposal(current.get('install_proposal')) or {}
    candidate_install_proposal = _normalize_install_proposal(candidate.get('install_proposal')) or {}
    current_install_state = _normalize_install_proposal_state(current.get('install_proposal_state')) or {}
    candidate_install_state = _normalize_install_proposal_state(candidate.get('install_proposal_state')) or {}
    current_actions = _normalize_install_actions(current_install_proposal.get('actions'))
    candidate_actions = _normalize_install_actions(candidate_install_proposal.get('actions'))
    current_knowledge_docs = set(
        (_clean_text(_as_dict(row).get('file_name'), max_len=160) or _clean_text(_as_dict(row).get('doc_id'), max_len=64).lower())
        for row in _as_list(_as_dict(_as_dict(current.get('structure_v2')).get('knowledge_surface')).get('docs'))
        if (_clean_text(_as_dict(row).get('file_name'), max_len=160) or _clean_text(_as_dict(row).get('doc_id'), max_len=64).lower())
    )
    candidate_knowledge_docs = set(
        (_clean_text(_as_dict(row).get('file_name'), max_len=160) or _clean_text(_as_dict(row).get('doc_id'), max_len=64).lower())
        for row in _as_list(_as_dict(_as_dict(candidate.get('structure_v2')).get('knowledge_surface')).get('docs'))
        if (_clean_text(_as_dict(row).get('file_name'), max_len=160) or _clean_text(_as_dict(row).get('doc_id'), max_len=64).lower())
    )
    current_stable_slots = set(
        _clean_text(item, max_len=64).lower()
        for item in _as_list(_as_dict(_as_dict(current.get('structure_v2')).get('memory_policy')).get('stable_semantic_slots'))
        if _clean_text(item, max_len=64)
    )
    candidate_stable_slots = set(
        _clean_text(item, max_len=64).lower()
        for item in _as_list(_as_dict(_as_dict(candidate.get('structure_v2')).get('memory_policy')).get('stable_semantic_slots'))
        if _clean_text(item, max_len=64)
    )
    current_runtime_execution = _normalize_runtime_execution_policy(_as_dict(_as_dict(current.get('structure_v2')).get('control_policy')).get('runtime_execution') or current.get('runtime_execution'))
    candidate_runtime_execution = _normalize_runtime_execution_policy(_as_dict(_as_dict(candidate.get('structure_v2')).get('control_policy')).get('runtime_execution') or candidate.get('runtime_execution'))
    current_codex = _as_dict(_as_dict(current_runtime_execution.get('providers')).get('codex'))
    candidate_codex = _as_dict(_as_dict(candidate_runtime_execution.get('providers')).get('codex'))
    current_gemini = _as_dict(_as_dict(current_runtime_execution.get('providers')).get('gemini'))
    candidate_gemini = _as_dict(_as_dict(candidate_runtime_execution.get('providers')).get('gemini'))

    guardrails = _build_guardrails(current, candidate, clean_state)

    preview_lines = [
        f"apply_state={clean_state}",
        f"agents: +{len(added_agents)} / -{len(removed_agents)} / ~{len(changed_agents)}",
        f"requirements.tools: +{len(candidate_tools - current_tools)} / -{len(current_tools - candidate_tools)}",
        f"requirements.credentials: +{len(candidate_credentials - current_credentials)} / -{len(current_credentials - candidate_credentials)}",
        f"requirements.skills: +{len(candidate_skills - current_skills)} / -{len(current_skills - candidate_skills)}",
        f"install_proposal.gaps: {int(candidate_install_proposal.get('gap_count') or 0)} (was {int(current_install_proposal.get('gap_count') or 0)})",
        f"install_proposal.actions: tools={int(candidate_actions.get('summary', {}).get('tool_install_count') or 0)} / creds={int(candidate_actions.get('summary', {}).get('credential_request_count') or 0)} / skills={int(candidate_actions.get('summary', {}).get('generated_skill_count') or 0)}",
        f"install_proposal.state: {_clean_text(candidate_install_state.get('status'), max_len=64) or 'none'} (was {_clean_text(current_install_state.get('status'), max_len=64) or 'none'})",
        f"credential_binding: +{len(candidate_bound_keys - current_bound_keys)} / -{len(current_bound_keys - candidate_bound_keys)}",
        f"structure.pattern: {_clean_text(_as_dict(_as_dict(candidate.get('structure_v2')).get('topology')).get('pattern'), max_len=32) or 'none'} (was {_clean_text(_as_dict(_as_dict(current.get('structure_v2')).get('topology')).get('pattern'), max_len=32) or 'none'})",
        f"knowledge.docs: +{len(candidate_knowledge_docs - current_knowledge_docs)} / -{len(current_knowledge_docs - candidate_knowledge_docs)}",
        f"memory_policy.stable_slots: +{len(candidate_stable_slots - current_stable_slots)} / -{len(current_stable_slots - candidate_stable_slots)}",
        f"runtime_execution.continuous_improvement: {'enabled' if _as_dict(candidate_runtime_execution.get('continuous_improvement')).get('enabled') else 'disabled'} (was {'enabled' if _as_dict(current_runtime_execution.get('continuous_improvement')).get('enabled') else 'disabled'})",
        f"runtime_execution.codex: sandbox={_clean_text(candidate_codex.get('sandbox_mode'), max_len=64) or 'workspace-write'} / approval={_clean_text(candidate_codex.get('approval_policy'), max_len=64) or 'never'} / mcp={len(_as_dict(candidate_codex.get('mcp_servers')))}",
        f"runtime_execution.gemini: approval_mode={_clean_text(candidate_gemini.get('approval_mode'), max_len=64) or 'default'} / mcp={len(_as_dict(candidate_gemini.get('mcp_servers')))}",
    ]

    return {
        "ok": True,
        "apply_state": clean_state,
        "current_manifest": current,
        "candidate_manifest": candidate,
        "diff": {
            "agents": {
                "added": added_agents,
                "removed": removed_agents,
                "changed": changed_agents,
                "unchanged": unchanged_agents,
            },
            "requirements": {
                "tools_added": sorted(candidate_tools - current_tools),
                "tools_removed": sorted(current_tools - candidate_tools),
                "credentials_added": sorted(candidate_credentials - current_credentials),
                "credentials_removed": sorted(current_credentials - candidate_credentials),
                "skills_added": sorted(candidate_skills - current_skills),
                "skills_removed": sorted(current_skills - candidate_skills),
            },
            "structure_v2": {
                "current_pattern": _clean_text(_as_dict(_as_dict(current.get("structure_v2")).get("topology")).get("pattern"), max_len=32) or None,
                "candidate_pattern": _clean_text(_as_dict(_as_dict(candidate.get("structure_v2")).get("topology")).get("pattern"), max_len=32) or None,
                "current_participant_count": len(_as_list(_as_dict(current.get("structure_v2")).get("participants"))),
                "candidate_participant_count": len(_as_list(_as_dict(candidate.get("structure_v2")).get("participants"))),
                "current_warning_count": len(_as_list(_as_dict(_as_dict(current.get("structure_v2")).get("validation")).get("warnings"))),
                "candidate_warning_count": len(_as_list(_as_dict(_as_dict(candidate.get("structure_v2")).get("validation")).get("warnings"))),
                "current_knowledge_doc_count": len(current_knowledge_docs),
                "candidate_knowledge_doc_count": len(candidate_knowledge_docs),
                "current_stable_memory_slot_count": len(current_stable_slots),
                "candidate_stable_memory_slot_count": len(candidate_stable_slots),
            },
            "knowledge_surface": {
                "docs_added": sorted(candidate_knowledge_docs - current_knowledge_docs),
                "docs_removed": sorted(current_knowledge_docs - candidate_knowledge_docs),
                "current": _as_dict(_as_dict(current.get('structure_v2')).get('knowledge_surface')),
                "candidate": _as_dict(_as_dict(candidate.get('structure_v2')).get('knowledge_surface')),
            },
            "memory_policy": {
                "stable_slots_added": sorted(candidate_stable_slots - current_stable_slots),
                "stable_slots_removed": sorted(current_stable_slots - candidate_stable_slots),
                "current": _as_dict(_as_dict(current.get('structure_v2')).get('memory_policy')),
                "candidate": _as_dict(_as_dict(candidate.get('structure_v2')).get('memory_policy')),
            },
            "runtime_execution": {
                "current": current_runtime_execution,
                "candidate": candidate_runtime_execution,
                "continuous_improvement_changed": _as_dict(current_runtime_execution.get('continuous_improvement')) != _as_dict(candidate_runtime_execution.get('continuous_improvement')),
                "approval_matrix_changed": _as_dict(current_runtime_execution.get('approval_matrix')) != _as_dict(candidate_runtime_execution.get('approval_matrix')),
                "codex_changed": current_codex != candidate_codex,
                "gemini_changed": current_gemini != candidate_gemini,
            },
            "credential_binding": {
                "bound_added": sorted(candidate_bound_keys - current_bound_keys),
                "bound_removed": sorted(current_bound_keys - candidate_bound_keys),
                "current": current_binding,
                "candidate": candidate_binding,
            },
            "install_proposal": {
                "current_gap_count": int(current_install_proposal.get('gap_count') or 0),
                "candidate_gap_count": int(candidate_install_proposal.get('gap_count') or 0),
                "current_state": _clean_text(current_install_state.get('status'), max_len=64) or None,
                "candidate_state": _clean_text(candidate_install_state.get('status'), max_len=64) or None,
                "blocking_changed": bool(current_install_proposal.get('blocking')) != bool(candidate_install_proposal.get('blocking')),
                "current_actions": current_actions,
                "candidate_actions": candidate_actions,
            },
            "guardrails": guardrails,
            "summary": {
                "agent_add_count": len(added_agents),
                "agent_remove_count": len(removed_agents),
                "agent_change_count": len(changed_agents),
                "tool_add_count": len(candidate_tools - current_tools),
                "tool_remove_count": len(current_tools - candidate_tools),
                "credential_add_count": len(candidate_credentials - current_credentials),
                "credential_remove_count": len(current_credentials - candidate_credentials),
                "skill_add_count": len(candidate_skills - current_skills),
                "skill_remove_count": len(current_skills - candidate_skills),
                "install_proposal_gap_delta": int(candidate_install_proposal.get('gap_count') or 0) - int(current_install_proposal.get('gap_count') or 0),
                "tool_install_delta": int(candidate_actions.get('summary', {}).get('tool_install_count') or 0) - int(current_actions.get('summary', {}).get('tool_install_count') or 0),
                "credential_request_delta": int(candidate_actions.get('summary', {}).get('credential_request_count') or 0) - int(current_actions.get('summary', {}).get('credential_request_count') or 0),
                "generated_skill_delta": int(candidate_actions.get('summary', {}).get('generated_skill_count') or 0) - int(current_actions.get('summary', {}).get('generated_skill_count') or 0),
                "bound_credential_delta": len(candidate_bound_keys - current_bound_keys) - len(current_bound_keys - candidate_bound_keys),
                "participant_delta": len(_as_list(_as_dict(candidate.get("structure_v2")).get("participants"))) - len(_as_list(_as_dict(current.get("structure_v2")).get("participants"))),
                "pattern_changed": _clean_text(_as_dict(_as_dict(candidate.get("structure_v2")).get("topology")).get("pattern"), max_len=32) != _clean_text(_as_dict(_as_dict(current.get("structure_v2")).get("topology")).get("pattern"), max_len=32),
                "structure_warning_delta": len(_as_list(_as_dict(_as_dict(candidate.get("structure_v2")).get("validation")).get("warnings"))) - len(_as_list(_as_dict(_as_dict(current.get("structure_v2")).get("validation")).get("warnings"))),
                "knowledge_doc_delta": len(candidate_knowledge_docs) - len(current_knowledge_docs),
                "stable_memory_slot_delta": len(candidate_stable_slots) - len(current_stable_slots),
                "runtime_execution_changed": current_runtime_execution != candidate_runtime_execution,
                "runtime_execution_mcp_delta": (len(_as_dict(candidate_codex.get('mcp_servers'))) + len(_as_dict(candidate_gemini.get('mcp_servers')))) - (len(_as_dict(current_codex.get('mcp_servers'))) + len(_as_dict(current_gemini.get('mcp_servers')))),
            },
            "preview_lines": preview_lines,
        },
    }


