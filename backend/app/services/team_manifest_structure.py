from __future__ import annotations

from typing import Any

from app.services import team_manifest as _core

_as_dict = _core._as_dict
_as_list = _core._as_list
_clean_text = _core._clean_text
_normalize_team_payload = _core._normalize_team_payload
_normalize_participant = _core._normalize_participant
_participant_id_by_label = _core._participant_id_by_label
_normalize_install_proposal_state = _core._normalize_install_proposal_state
_normalize_credential_binding_state = _core._normalize_credential_binding_state
_normalize_knowledge_surface = _core._normalize_knowledge_surface
_normalize_memory_policy = _core._normalize_memory_policy
_normalize_memory_plan = _core._normalize_memory_plan
_pattern_from_execution = _core._pattern_from_execution
_normalize_debate_policy = _core._normalize_debate_policy
_normalize_consensus_policy = _core._normalize_consensus_policy
_normalize_runtime_execution_policy = _core._normalize_runtime_execution_policy
_normalize_requirements = _core._normalize_requirements


def _build_structure_validation(pattern: str, participants: list[dict[str, Any]], edges: list[dict[str, Any]], final_participant_id: str = '') -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    if not participants:
        errors.append('structure_v2 must include at least one participant')
    if pattern == 'single' and len(participants) > 1:
        warnings.append('single pattern currently has multiple participants; runtime will degrade to a compatibility pipeline')
    if pattern == 'parallel' and len(participants) < 2:
        errors.append('parallel pattern requires at least two participants')
    if pattern == 'debate':
        if len(participants) < 3:
            warnings.append('debate pattern works best with at least two debaters plus one judge/synthesizer')
        if not final_participant_id:
            warnings.append('debate pattern has no explicit adjudicator/final participant')
    if pattern == 'committee' and len(participants) < 3:
        warnings.append('committee pattern usually needs at least three participants')
    if pattern == 'graph':
        if not edges:
            errors.append('graph pattern requires explicit edges')
    return {
        'warnings': warnings,
        'errors': errors,
        'pattern_ready': len(errors) == 0,
    }

def _build_structure_v2_from_team(team_payload: Any, *, apply_state: str = 'pending', install_proposal_state: Any = None, credential_binding_state: Any = None) -> dict[str, Any]:
    team = _normalize_team_payload(team_payload)
    participants = []
    for index, item in enumerate(_as_list(team.get('agents'))):
        normalized = _normalize_participant({
            'participant_id': _as_dict(item).get('agent_id') or _as_dict(item).get('agentId'),
            'kind': 'agent',
            'name': _as_dict(item).get('name'),
            'role': _as_dict(item).get('role'),
            'purpose': _as_dict(item).get('purpose'),
            'provider': _as_dict(item).get('provider') or _as_dict(item).get('llm_provider') or _as_dict(item).get('llmProvider'),
            'model': _as_dict(item).get('model'),
            'capabilities': _as_dict(item).get('capabilities') or _as_dict(item).get('skills'),
            'attached_skill_ids': _as_dict(item).get('attached_skill_ids') or _as_dict(item).get('attachedSkillIds'),
            'required_tool_ids': _as_dict(item).get('required_tool_ids') or _as_dict(item).get('requiredToolIds'),
            'optional_tool_ids': _as_dict(item).get('optional_tool_ids') or _as_dict(item).get('optionalToolIds'),
            'recommended_tool_ids': _as_dict(item).get('recommended_tool_ids') or _as_dict(item).get('recommendedToolIds'),
            'generated_skill_briefs': _as_dict(item).get('generated_skill_briefs') or _as_dict(item).get('generatedSkillBriefs'),
            'context_policy': _as_dict(item).get('context_policy') or _as_dict(item).get('contextPolicy'),
            'provider_spec': _as_dict(item).get('provider_spec') or _as_dict(item).get('providerSpec'),
            'provider_runtime_config': _as_dict(item).get('provider_runtime_config') or _as_dict(item).get('providerRuntimeConfig'),
            'role_profile': _as_dict(item).get('role_profile') or _as_dict(item).get('roleProfile'),
            'skill_package': _as_dict(item).get('skill_package') or _as_dict(item).get('skillPackage'),
            'runtime_capabilities_required': _as_dict(item).get('runtime_capabilities_required') or _as_dict(item).get('runtimeCapabilitiesRequired'),
            'runtime_capabilities_optional': _as_dict(item).get('runtime_capabilities_optional') or _as_dict(item).get('runtimeCapabilitiesOptional'),
            'external_tool_requirements': _as_list(_as_dict(item).get('external_tool_requirements') or _as_dict(item).get('externalToolRequirements') or []),
            'external_tool_preferences': _as_list(_as_dict(item).get('external_tool_preferences') or _as_dict(item).get('externalToolPreferences') or []),
            'memory_contract': _as_dict(item).get('memory_contract') or _as_dict(item).get('memoryContract'),
        }, index)
        if normalized:
            participants.append(normalized)
    interaction = _as_dict(team.get('interaction_spec') or team.get('interactionSpec'))
    policies = _as_dict(interaction.get('policies'))
    edges = []
    for index, item in enumerate(_as_list(interaction.get('handoffs'))):
        handoff = _as_dict(item)
        from_id = _participant_id_by_label(participants, handoff.get('from'))
        to_id = _participant_id_by_label(participants, handoff.get('to'))
        if not from_id or not to_id:
            continue
        edges.append({
            'edge_id': _clean_text(handoff.get('edge_id') or f'{from_id}_to_{to_id}_{index + 1}', max_len=128).lower(),
            'from': from_id,
            'to': to_id,
            'kind': 'handoff',
            'payload': _clean_text(handoff.get('payload') or 'summary_only', max_len=64).lower() or 'summary_only',
        })
    if not edges and len(participants) > 1:
        for index in range(len(participants) - 1):
            edges.append({
                'edge_id': f"{participants[index]['participant_id']}_to_{participants[index + 1]['participant_id']}_sequential",
                'from': participants[index]['participant_id'],
                'to': participants[index + 1]['participant_id'],
                'kind': 'implied_sequence',
                'payload': 'summary_only',
            })
    final_owner = _participant_id_by_label(participants, interaction.get('final_answer_owner') or interaction.get('finalAnswerOwner'))
    install_state = _normalize_install_proposal_state(install_proposal_state) if install_proposal_state else None
    binding_state = _normalize_credential_binding_state(credential_binding_state or {})
    knowledge_surface = _normalize_knowledge_surface(
        _as_dict(_as_dict(team.get('structure_v2')).get('knowledge_surface')) or team.get('knowledge_surface') or team.get('knowledgeSurface'),
        fallback_profile=team.get('knowledge_base_profile') or team.get('knowledgeBaseProfile'),
        fallback_team=team,
    )
    memory_policy = _normalize_memory_policy(
        _as_dict(_as_dict(team.get('structure_v2')).get('memory_policy')) or team.get('memory_policy') or team.get('memoryPolicy'),
        knowledge_surface=knowledge_surface,
    )
    memory_plan = _normalize_memory_plan(
        _as_dict(_as_dict(team.get('structure_v2')).get('memory_plan')) or team.get('memory_plan') or team.get('memoryPlan'),
        knowledge_surface=knowledge_surface,
        memory_policy=memory_policy,
    )
    return {
        'kind': 'team_structure_v2',
        'version': 2,
        'metadata': {
            'team_name': _clean_text(team.get('team_name') or 'configured_team', max_len=128) or 'configured_team',
            'composition_mode': _clean_text(team.get('composition_mode') or 'structured', max_len=32).lower() or 'structured',
            'proposal_mode': _clean_text(team.get('proposal_mode') or 'suggest', max_len=32).lower() or 'suggest',
            'status': _clean_text(team.get('status') or 'draft', max_len=32).lower() or 'draft',
            'planner_metadata': _as_dict(team.get('planner_metadata') or team.get('plannerMetadata')),
        },
        'intent': {
            'task_brief': _clean_text(team.get('task_brief') or team.get('taskBrief') or team.get('design_prompt') or team.get('designPrompt'), max_len=512),
            'design_prompt': _clean_text(team.get('design_prompt') or team.get('designPrompt') or team.get('task_brief') or team.get('taskBrief'), max_len=512),
            'success_criteria': [_clean_text(v, max_len=128) for v in _as_list(team.get('success_criteria') or team.get('successCriteria')) if _clean_text(v, max_len=128)][:8],
            'risk_profile': _clean_text(team.get('risk_profile') or team.get('riskProfile') or 'medium', max_len=32).lower() or 'medium',
        },
        'participants': participants,
        'topology': {
            'pattern': (
                'single'
                if not _clean_text(interaction.get('execution_pattern') or interaction.get('executionPattern'), max_len=64)
                and not _clean_text(_as_dict(team.get('structure_v2')).get('topology', {}).get('pattern'), max_len=32)
                else _pattern_from_execution(_clean_text(interaction.get('execution_pattern') or interaction.get('executionPattern'), max_len=64), len(participants), _clean_text(_as_dict(team.get('structure_v2')).get('topology', {}).get('pattern'), max_len=32))
            ),
            'execution_pattern': _clean_text(interaction.get('execution_pattern') or interaction.get('executionPattern'), max_len=64).lower(),
            'nodes': [{'node_id': f"node_{row['participant_id']}", 'participant_id': row['participant_id'], 'kind': 'gate' if row.get('kind') == 'gate' else 'task', 'label': row.get('name')} for row in participants],
            'edges': edges[:32],
            'final_participant_id': final_owner or None,
        },
        'interaction_policy': {
            'visibility': {
                'reviewer_visibility': _clean_text(policies.get('reviewer_visibility') or 'summaries_plus_selected_evidence', max_len=64).lower() or 'summaries_plus_selected_evidence',
                'synthesizer_visibility': _clean_text(policies.get('synthesizer_visibility') or 'upstream_outputs_only', max_len=64).lower() or 'upstream_outputs_only',
            },
            'handoff_policy': {
                'direct_response_enabled': bool(policies.get('builder_direct_response')),
                'followup_shortcuts_enabled': _as_dict(team.get('shortcut_policy') or team.get('shortcutPolicy')).get('enabled') is not False,
                'max_recent_turns': int(_as_dict(team.get('shortcut_policy') or team.get('shortcutPolicy')).get('max_recent_turns') or 6),
            },
            'followup_policy': {
                'only_for_followups': _as_dict(team.get('shortcut_policy') or team.get('shortcutPolicy')).get('only_for_followups') is not False,
                'disallow_when_pending_approval': _as_dict(team.get('shortcut_policy') or team.get('shortcutPolicy')).get('disallow_when_pending_approval') is not False,
            },
            'debate_policy': _normalize_debate_policy(_as_dict(_as_dict(team.get('structure_v2')).get('interaction_policy')).get('debate_policy'), participants, final_owner),
            'consensus_policy': _normalize_consensus_policy(_as_dict(_as_dict(team.get('structure_v2')).get('interaction_policy')).get('consensus_policy'), participants),
        },
        'control_policy': {
            'final_answer_owner_participant_id': final_owner or None,
            'require_reviewer_before_final': policies.get('require_reviewer_before_final') is not False,
            'approval_mode': 'unlocked' if team.get('lock_after_apply') is False else 'apply_then_lock',
            'resume_supported': True,
            'runtime_execution': _normalize_runtime_execution_policy(
                _as_dict(_as_dict(team.get('structure_v2')).get('control_policy')).get('runtime_execution')
                or _as_dict(team.get('control_policy')).get('runtime_execution')
                or team.get('runtime_execution')
                or team.get('runtimeExecution')
            ),
        },
        'artifacts': {
            'expected_outputs': [_clean_text(v, max_len=128) for v in _as_list(team.get('expected_outputs') or team.get('expectedOutputs')) if _clean_text(v, max_len=128)][:8],
            'artifact_contracts': _as_list(team.get('artifact_contracts') or team.get('artifactContracts'))[:12],
        },
        'knowledge_surface': knowledge_surface,
        'memory_policy': memory_policy,
        'memory_plan': memory_plan,
        'requirements': _normalize_requirements(team.get('requirements'), team),
        'runtime_state': {
            'apply_state': 'active' if _clean_text(apply_state, max_len=16).lower() == 'active' else 'pending',
            'install_proposal_status': _clean_text((install_state or {}).get('status'), max_len=64) or None,
            'bound_credential_keys': _as_list(binding_state.get('bound_keys'))[:16],
        },
        'validation': _build_structure_validation(_pattern_from_execution(_clean_text(interaction.get('execution_pattern') or interaction.get('executionPattern'), max_len=64), len(participants), _clean_text(_as_dict(team.get('structure_v2')).get('topology', {}).get('pattern'), max_len=32)), participants, edges[:32], final_owner),
    }

def _normalize_structure_v2(raw: Any, *, team_payload: Any = None, apply_state: str = 'pending', install_proposal_state: Any = None, credential_binding_state: Any = None) -> dict[str, Any]:
    row = _as_dict(raw)
    if not row:
        return _build_structure_v2_from_team(team_payload or {}, apply_state=apply_state, install_proposal_state=install_proposal_state, credential_binding_state=credential_binding_state)
    participants = [normalized for index, item in enumerate(_as_list(row.get('participants'))) if (normalized := _normalize_participant(item, index))]
    topology = _as_dict(row.get('topology'))
    edges = []
    for index, item in enumerate(_as_list(topology.get('edges'))):
        edge = _as_dict(item)
        from_id = _participant_id_by_label(participants, edge.get('from'))
        to_id = _participant_id_by_label(participants, edge.get('to'))
        if not from_id or not to_id:
            continue
        edges.append({
            'edge_id': _clean_text(edge.get('edge_id') or edge.get('edgeId') or f'edge_{index + 1}', max_len=128).lower() or f'edge_{index + 1}',
            'from': from_id,
            'to': to_id,
            'kind': _clean_text(edge.get('kind') or 'handoff', max_len=64).lower() or 'handoff',
            'payload': _clean_text(edge.get('payload') or 'summary_only', max_len=64).lower() or 'summary_only',
            'condition': _clean_text(edge.get('condition'), max_len=128),
        })
    if not edges and len(participants) > 1:
        for index in range(len(participants) - 1):
            edges.append({
                'edge_id': f"{participants[index]['participant_id']}_to_{participants[index + 1]['participant_id']}_sequential",
                'from': participants[index]['participant_id'],
                'to': participants[index + 1]['participant_id'],
                'kind': 'implied_sequence',
                'payload': 'summary_only',
            })
    install_state = _normalize_install_proposal_state(install_proposal_state) if install_proposal_state else None
    binding_state = _normalize_credential_binding_state(credential_binding_state or {})
    knowledge_surface = _normalize_knowledge_surface(
        row.get('knowledge_surface') or row.get('knowledgeSurface'),
        fallback_profile=_as_dict(team_payload).get('knowledge_base_profile') if isinstance(team_payload, dict) else None,
        fallback_team=team_payload,
    )
    memory_policy = _normalize_memory_policy(
        row.get('memory_policy') or row.get('memoryPolicy') or (_as_dict(team_payload).get('memory_policy') if isinstance(team_payload, dict) else None),
        knowledge_surface=knowledge_surface,
    )
    memory_plan = _normalize_memory_plan(
        row.get('memory_plan') or row.get('memoryPlan') or (_as_dict(team_payload).get('memory_plan') if isinstance(team_payload, dict) else None),
        knowledge_surface=knowledge_surface,
        memory_policy=memory_policy,
    )
    return {
        'kind': 'team_structure_v2',
        'version': 2,
        'metadata': {
            'team_name': _clean_text(_as_dict(row.get('metadata')).get('team_name') or _as_dict(row.get('metadata')).get('teamName') or 'configured_team', max_len=128) or 'configured_team',
            'composition_mode': _clean_text(_as_dict(row.get('metadata')).get('composition_mode') or _as_dict(row.get('metadata')).get('compositionMode') or 'structured', max_len=32).lower() or 'structured',
            'proposal_mode': _clean_text(_as_dict(row.get('metadata')).get('proposal_mode') or _as_dict(row.get('metadata')).get('proposalMode') or 'suggest', max_len=32).lower() or 'suggest',
            'status': _clean_text(_as_dict(row.get('metadata')).get('status') or 'draft', max_len=32).lower() or 'draft',
            'planner_metadata': _as_dict(_as_dict(row.get('metadata')).get('planner_metadata') or _as_dict(row.get('metadata')).get('plannerMetadata')),
        },
        'intent': {
            'task_brief': _clean_text(_as_dict(row.get('intent')).get('task_brief') or _as_dict(row.get('intent')).get('taskBrief'), max_len=512),
            'design_prompt': _clean_text(_as_dict(row.get('intent')).get('design_prompt') or _as_dict(row.get('intent')).get('designPrompt') or _as_dict(row.get('intent')).get('task_brief') or _as_dict(row.get('intent')).get('taskBrief'), max_len=512),
            'success_criteria': [_clean_text(v, max_len=128) for v in _as_list(_as_dict(row.get('intent')).get('success_criteria') or _as_dict(row.get('intent')).get('successCriteria')) if _clean_text(v, max_len=128)][:8],
            'risk_profile': _clean_text(_as_dict(row.get('intent')).get('risk_profile') or _as_dict(row.get('intent')).get('riskProfile') or 'medium', max_len=32).lower() or 'medium',
        },
        'participants': participants,
        'topology': {
            'pattern': _pattern_from_execution(_clean_text(topology.get('execution_pattern') or topology.get('executionPattern'), max_len=64), len(participants), _clean_text(topology.get('pattern'), max_len=32)),
            'execution_pattern': _clean_text(topology.get('execution_pattern') or topology.get('executionPattern'), max_len=64).lower(),
            'nodes': _as_list(topology.get('nodes')) or [{'node_id': f"node_{row['participant_id']}", 'participant_id': row['participant_id'], 'kind': 'gate' if row.get('kind') == 'gate' else 'task', 'label': row.get('name')} for row in participants],
            'edges': edges[:32],
            'final_participant_id': _participant_id_by_label(participants, topology.get('final_participant_id') or topology.get('finalParticipantId') or _as_dict(row.get('control_policy')).get('final_answer_owner_participant_id') or _as_dict(row.get('control_policy')).get('finalAnswerOwnerParticipantId')) or None,
        },
        'interaction_policy': {
            'visibility': {
                'reviewer_visibility': _clean_text(_as_dict(_as_dict(row.get('interaction_policy')).get('visibility')).get('reviewer_visibility') or _as_dict(_as_dict(row.get('interaction_policy')).get('visibility')).get('reviewerVisibility') or 'summaries_plus_selected_evidence', max_len=64).lower() or 'summaries_plus_selected_evidence',
                'synthesizer_visibility': _clean_text(_as_dict(_as_dict(row.get('interaction_policy')).get('visibility')).get('synthesizer_visibility') or _as_dict(_as_dict(row.get('interaction_policy')).get('visibility')).get('synthesizerVisibility') or 'upstream_outputs_only', max_len=64).lower() or 'upstream_outputs_only',
            },
            'handoff_policy': {
                'direct_response_enabled': _as_dict(_as_dict(row.get('interaction_policy')).get('handoff_policy')).get('direct_response_enabled') is True or _as_dict(_as_dict(row.get('interaction_policy')).get('handoff_policy')).get('directResponseEnabled') is True,
                'followup_shortcuts_enabled': _as_dict(_as_dict(row.get('interaction_policy')).get('handoff_policy')).get('followup_shortcuts_enabled') is not False and _as_dict(_as_dict(row.get('interaction_policy')).get('handoff_policy')).get('followupShortcutsEnabled') is not False,
                'max_recent_turns': int(_as_dict(_as_dict(row.get('interaction_policy')).get('handoff_policy')).get('max_recent_turns') or _as_dict(_as_dict(row.get('interaction_policy')).get('handoff_policy')).get('maxRecentTurns') or 6),
            },
            'followup_policy': {
                'only_for_followups': _as_dict(_as_dict(row.get('interaction_policy')).get('followup_policy')).get('only_for_followups') is not False and _as_dict(_as_dict(row.get('interaction_policy')).get('followup_policy')).get('onlyForFollowups') is not False,
                'disallow_when_pending_approval': _as_dict(_as_dict(row.get('interaction_policy')).get('followup_policy')).get('disallow_when_pending_approval') is not False and _as_dict(_as_dict(row.get('interaction_policy')).get('followup_policy')).get('disallowWhenPendingApproval') is not False,
            },
            'debate_policy': _normalize_debate_policy(_as_dict(_as_dict(row.get('interaction_policy')).get('debate_policy') or _as_dict(row.get('interaction_policy')).get('debatePolicy')), participants, _participant_id_by_label(participants, topology.get('final_participant_id') or topology.get('finalParticipantId'))),
            'consensus_policy': _normalize_consensus_policy(_as_dict(_as_dict(row.get('interaction_policy')).get('consensus_policy') or _as_dict(row.get('interaction_policy')).get('consensusPolicy')), participants),
        },
        'control_policy': {
            'final_answer_owner_participant_id': _participant_id_by_label(participants, _as_dict(row.get('control_policy')).get('final_answer_owner_participant_id') or _as_dict(row.get('control_policy')).get('finalAnswerOwnerParticipantId')) or None,
            'require_reviewer_before_final': _as_dict(row.get('control_policy')).get('require_reviewer_before_final') is not False and _as_dict(row.get('control_policy')).get('requireReviewerBeforeFinal') is not False,
            'approval_mode': _clean_text(_as_dict(row.get('control_policy')).get('approval_mode') or _as_dict(row.get('control_policy')).get('approvalMode') or 'apply_then_lock', max_len=64).lower() or 'apply_then_lock',
            'resume_supported': _as_dict(row.get('control_policy')).get('resume_supported') is not False and _as_dict(row.get('control_policy')).get('resumeSupported') is not False,
            'runtime_execution': _normalize_runtime_execution_policy(
                _as_dict(row.get('control_policy')).get('runtime_execution')
                or _as_dict(row.get('control_policy')).get('runtimeExecution')
                or row.get('runtime_execution')
                or row.get('runtimeExecution')
                or _as_dict(team_payload).get('runtime_execution')
            ),
        },
        'artifacts': {
            'expected_outputs': [_clean_text(v, max_len=128) for v in _as_list(_as_dict(row.get('artifacts')).get('expected_outputs') or _as_dict(row.get('artifacts')).get('expectedOutputs')) if _clean_text(v, max_len=128)][:8],
            'artifact_contracts': _as_list(_as_dict(row.get('artifacts')).get('artifact_contracts') or _as_dict(row.get('artifacts')).get('artifactContracts'))[:12],
        },
        'knowledge_surface': knowledge_surface,
        'memory_policy': memory_policy,
        'memory_plan': memory_plan,
        'requirements': _normalize_requirements(row.get('requirements'), team_payload or {}),
        'runtime_state': {
            'apply_state': 'active' if _clean_text(_as_dict(row.get('runtime_state')).get('apply_state') or _as_dict(row.get('runtime_state')).get('applyState') or apply_state, max_len=16).lower() == 'active' else 'pending',
            'install_proposal_status': _clean_text(_as_dict(row.get('runtime_state')).get('install_proposal_status') or _as_dict(row.get('runtime_state')).get('installProposalStatus') or (install_state or {}).get('status'), max_len=64) or None,
            'bound_credential_keys': _as_list(_as_dict(row.get('runtime_state')).get('bound_credential_keys') or _as_dict(row.get('runtime_state')).get('boundCredentialKeys') or binding_state.get('bound_keys'))[:16],
        },
        'validation': _build_structure_validation(_pattern_from_execution(_clean_text(topology.get('execution_pattern') or topology.get('executionPattern'), max_len=64), len(participants), _clean_text(topology.get('pattern'), max_len=32)), participants, edges[:32], _participant_id_by_label(participants, topology.get('final_participant_id') or topology.get('finalParticipantId') or _as_dict(row.get('control_policy')).get('final_answer_owner_participant_id') or _as_dict(row.get('control_policy')).get('finalAnswerOwnerParticipantId'))),
    }

def _derive_team_from_structure_v2(raw: Any) -> dict[str, Any]:
    structure = _normalize_structure_v2(raw)
    participants = {row.get('participant_id'): row for row in _as_list(structure.get('participants')) if isinstance(row, dict) and row.get('participant_id')}
    agents = []
    for row in _as_list(structure.get('participants')):
        item = _as_dict(row)
        if item.get('kind') != 'agent':
            continue
        agents.append({
            'agent_id': item.get('participant_id'),
            'name': item.get('name') or item.get('participant_id'),
            'role': item.get('role') or 'specialist',
            'purpose': item.get('purpose') or '',
            'provider': item.get('provider') or _as_dict(item.get('provider_spec')).get('provider') or '',
            'model': item.get('model') or _as_dict(item.get('provider_spec')).get('model') or '',
            'execution_channel': item.get('execution_channel') or _as_dict(item.get('provider_spec')).get('execution_channel') or '',
            'capabilities': _as_list(item.get('capabilities'))[:8],
            'skills': _as_list(item.get('capabilities'))[:8],
            'attached_skill_ids': _as_list(item.get('attached_skill_ids') or _as_dict(item.get('skill_package')).get('skill_ids'))[:8],
            'required_tool_ids': _as_list(item.get('required_tool_ids'))[:8],
            'optional_tool_ids': _as_list(item.get('optional_tool_ids') or item.get('recommended_tool_ids'))[:8],
            'recommended_tool_ids': _as_list(item.get('recommended_tool_ids') or list(_as_list(item.get('required_tool_ids')) + _as_list(item.get('optional_tool_ids'))))[:8],
            'runtime_capabilities_required': _as_dict(item.get('runtime_capabilities_required') or item.get('runtimeCapabilitiesRequired')),
            'runtime_capabilities_optional': _as_dict(item.get('runtime_capabilities_optional') or item.get('runtimeCapabilitiesOptional')),
            'external_tool_requirements': _as_list(item.get('external_tool_requirements') or item.get('externalToolRequirements'))[:8],
            'external_tool_preferences': _as_list(item.get('external_tool_preferences') or item.get('externalToolPreferences'))[:8],
            'provider_spec': _as_dict(item.get('provider_spec') or item.get('providerSpec')),
            'provider_runtime_config': _as_dict(item.get('provider_runtime_config') or item.get('providerRuntimeConfig')),
            'role_profile': _as_dict(item.get('role_profile') or item.get('roleProfile')),
            'skill_package': _as_dict(item.get('skill_package') or item.get('skillPackage')),
            'memory_contract': _as_dict(item.get('memory_contract') or item.get('memoryContract')),
            'generated_skill_briefs': _as_list(item.get('generated_skill_briefs') or _as_dict(item.get('skill_package')).get('generated_skill_briefs'))[:8],
            'context_policy': _as_dict(item.get('context_policy')),
        })
    final_owner = participants.get(_as_dict(structure.get('control_policy')).get('final_answer_owner_participant_id') or _as_dict(structure.get('topology')).get('final_participant_id') or '')
    execution_pattern = _clean_text(_as_dict(structure.get('topology')).get('execution_pattern'), max_len=64).lower()
    if not execution_pattern:
        execution_pattern = {
            'single': 'single_specialist',
            'sequential': 'sequential_pipeline',
            'parallel': 'parallel_research_then_review_then_synthesize',
            'debate': 'multi_research_adjudication',
            'workflow': 'builder_reviewer_loop',
        }.get(_clean_text(_as_dict(structure.get('topology')).get('pattern'), max_len=32).lower(), 'single_specialist')
    handoffs = []
    for item in _as_list(_as_dict(structure.get('topology')).get('edges')):
        edge = _as_dict(item)
        from_row = participants.get(edge.get('from'))
        to_row = participants.get(edge.get('to'))
        if not from_row or not to_row:
            continue
        handoffs.append({
            'from': from_row.get('name') or from_row.get('participant_id'),
            'to': to_row.get('name') or to_row.get('participant_id'),
            'payload': _clean_text(edge.get('payload') or 'summary_only', max_len=64).lower() or 'summary_only',
        })
    return {
        'team_name': _clean_text(_as_dict(structure.get('metadata')).get('team_name') or 'configured_team', max_len=128) or 'configured_team',
        'composition_mode': _clean_text(_as_dict(structure.get('metadata')).get('composition_mode') or 'structured', max_len=32).lower() or 'structured',
        'proposal_mode': _clean_text(_as_dict(structure.get('metadata')).get('proposal_mode') or 'suggest', max_len=32).lower() or 'suggest',
        'task_brief': _clean_text(_as_dict(structure.get('intent')).get('task_brief') or _as_dict(structure.get('intent')).get('taskBrief'), max_len=512),
        'design_prompt': _clean_text(_as_dict(structure.get('intent')).get('design_prompt') or _as_dict(structure.get('intent')).get('designPrompt') or _as_dict(structure.get('intent')).get('task_brief') or _as_dict(structure.get('intent')).get('taskBrief'), max_len=512),
        'planner_metadata': _as_dict(_as_dict(structure.get('metadata')).get('planner_metadata')),
        'agents': agents,
        'interaction_spec': {
            'execution_pattern': execution_pattern,
            'final_answer_owner': (final_owner or {}).get('name') or (final_owner or {}).get('participant_id') or (agents[-1]['name'] if agents else ''),
            'handoffs': handoffs,
            'policies': {
                'reviewer_visibility': _clean_text(_as_dict(_as_dict(structure.get('interaction_policy')).get('visibility')).get('reviewer_visibility') or 'summaries_plus_selected_evidence', max_len=64).lower() or 'summaries_plus_selected_evidence',
                'synthesizer_visibility': _clean_text(_as_dict(_as_dict(structure.get('interaction_policy')).get('visibility')).get('synthesizer_visibility') or 'upstream_outputs_only', max_len=64).lower() or 'upstream_outputs_only',
                'builder_direct_response': _as_dict(_as_dict(structure.get('interaction_policy')).get('handoff_policy')).get('direct_response_enabled') is True,
                'require_reviewer_before_final': _as_dict(structure.get('control_policy')).get('require_reviewer_before_final') is not False,
            },
            'selection_reason': f"Derived from structure_v2 pattern={_clean_text(_as_dict(structure.get('topology')).get('pattern'), max_len=32)}",
        },
        'shortcut_policy': {
            'enabled': _as_dict(_as_dict(structure.get('interaction_policy')).get('handoff_policy')).get('followup_shortcuts_enabled') is not False,
            'only_for_followups': _as_dict(_as_dict(structure.get('interaction_policy')).get('followup_policy')).get('only_for_followups') is not False,
            'disallow_when_pending_approval': _as_dict(_as_dict(structure.get('interaction_policy')).get('followup_policy')).get('disallow_when_pending_approval') is not False,
            'max_recent_turns': int(_as_dict(_as_dict(structure.get('interaction_policy')).get('handoff_policy')).get('max_recent_turns') or 6),
        },
        'knowledge_surface': _as_dict(structure.get('knowledge_surface')),
        'memory_policy': _as_dict(structure.get('memory_policy')),
        'memory_plan': _as_dict(structure.get('memory_plan')),
        'knowledge_base_profile': {
            'profile_id': _clean_text(_as_dict(structure.get('knowledge_surface')).get('profile_id') or 'default_kb', max_len=128) or 'default_kb',
            'display_name': _clean_text(_as_dict(structure.get('knowledge_surface')).get('display_name') or 'Default Knowledge Base', max_len=160) or 'Default Knowledge Base',
            'docs': _as_list(_as_dict(structure.get('knowledge_surface')).get('docs'))[:16],
            'memory_policy': _as_dict(structure.get('memory_policy')),
        'memory_plan': _as_dict(structure.get('memory_plan')),
            'stable_memory_files': _as_list(_as_dict(structure.get('knowledge_surface')).get('stable_memory_files'))[:16],
        },
        'requirements': _normalize_requirements(structure.get('requirements'), {}),
        'runtime_execution': _normalize_runtime_execution_policy(_as_dict(structure.get('control_policy')).get('runtime_execution')),
        'status': _clean_text(_as_dict(structure.get('metadata')).get('status') or 'draft', max_len=32).lower() or 'draft',
        'structure_v2': structure,
    }

