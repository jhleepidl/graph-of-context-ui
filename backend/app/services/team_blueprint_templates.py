from __future__ import annotations

from copy import deepcopy
from typing import Any


def _clean_id(value: Any, max_len: int = 128) -> str:
    text = str(value or '').strip().lower()[:max_len]
    return ''.join(ch if ch.isalnum() or ch in '._:-' else '_' for ch in text)


def _unique_tool_ids(values: Any, max_items: int = 24) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values if isinstance(values, list) else []:
        tool_id = _clean_id(raw, 64)
        if not tool_id or tool_id in seen:
            continue
        seen.add(tool_id)
        out.append(tool_id)
        if len(out) >= max_items:
            break
    return out


def _build_capability_contract(team_seed: dict[str, Any]) -> dict[str, Any]:
    required: list[str] = []
    optional: list[str] = []
    agent_contracts: list[dict[str, Any]] = []
    for agent in team_seed.get('agents') or []:
        required_tools = _unique_tool_ids(agent.get('required_tool_ids') or agent.get('requiredToolIds') or [])
        optional_tools = _unique_tool_ids(agent.get('optional_tool_ids') or agent.get('optionalToolIds') or agent.get('recommended_tool_ids') or agent.get('recommendedToolIds') or [])
        optional_tools = [tool_id for tool_id in optional_tools if tool_id not in required_tools]
        required.extend(required_tools); optional.extend(optional_tools)
        agent_contracts.append({'agent_id': _clean_id(agent.get('agent_id') or agent.get('id') or agent.get('name') or 'agent'), 'agent_name': str(agent.get('name') or agent.get('agent_id') or 'agent').strip() or 'agent', 'role': _clean_id(agent.get('role') or 'agent', 64) or 'agent', 'required_tools': required_tools, 'optional_tools': optional_tools})
    required = _unique_tool_ids(required); optional = [tool_id for tool_id in _unique_tool_ids(optional) if tool_id not in required]
    return {'version': 'capability_contract_v1', 'runtime_bound': False, 'runtime_source': 'template', 'status': 'unbound', 'required_tools': required, 'optional_tools': optional, 'available_tools': [], 'missing_required_tools': required, 'missing_optional_tools': optional, 'auto_installable_missing_tools': [], 'mismatch_count': len(required) + len(optional), 'agent_contracts': agent_contracts}


def _doc(kind: str, title: str, description: str, tags: list[str], good_for: list[str], bad_for: list[str], team_seed: dict[str, Any]) -> dict[str, Any]:
    structure = deepcopy(team_seed.get('structure') or team_seed.get('structure_v2') or {})
    memory_plan = deepcopy(team_seed.get('memory_plan') or {})
    capability_contract = _build_capability_contract(team_seed)
    return {
        'kind': 'ddalggak_team_blueprint',
        'version': 1,
        'primary_schema': 'team_blueprint_v1',
        'source': 'task_archetype_template',
        'apply_state': 'pending',
        'summary': {
            'agent_count': len(list(team_seed.get('agents') or [])),
            'participant_count': len(list(structure.get('participants') or [])),
            'structure_pattern': (structure.get('topology') or {}).get('pattern') or 'hybrid',
            'memory_surface_count': len(list(memory_plan.get('surfaces') or [])),
            'task_archetype': kind,
        },
        'requirements': team_seed.get('requirements') or {},
        'blueprint': {
            'blueprint_id': f'{kind}_template',
            'title': title,
            'description': description,
            'task_archetype': kind,
            'topology': {
                'pattern': ((structure.get('topology') or {}).get('pattern') or 'hybrid'),
                'execution_pattern': ((structure.get('topology') or {}).get('execution_pattern') or ''),
                'final_participant_id': ((structure.get('topology') or {}).get('final_participant_id') or ''),
                'participants': structure.get('participants') or [],
                'nodes': (structure.get('topology') or {}).get('nodes') or [],
                'edges': (structure.get('topology') or {}).get('edges') or [],
            },
            'structure': structure,
            'memory_plan': memory_plan,
            'memory_map': [
                {
                    'surface_id': surface.get('surface_id'),
                    'file_name': surface.get('file_name'),
                    'load_policy': surface.get('load_policy'),
                    'write_policy': surface.get('write_policy'),
                    'target_roles': surface.get('target_roles') or [],
                    'semantic_slots': surface.get('semantic_slots') or [],
                }
                for surface in (memory_plan.get('surfaces') or [])
            ],
            'runtime_policy': {'runtime_execution': deepcopy(team_seed.get('runtime_execution') or {})},
            'capability_contract': capability_contract,
            'team_seed': deepcopy(team_seed),
            'catalog': {'tags': tags, 'good_for': good_for, 'bad_for': bad_for},
        },
        'team': deepcopy(team_seed),
    }


def list_team_blueprint_templates() -> list[dict[str, Any]]:
    return [
        _doc(
            'research',
            'Research Briefing Team',
            'Investigate a topic, gather evidence, and deliver a concise recommendation memo.',
            ['research', 'briefing', 'evidence', 'sequential'],
            ['source-grounded research', 'briefing memos', 'recommendation synthesis'],
            ['large repo patching'],
            {
                'team_name': 'Research Briefing Team',
                'task_brief': 'Investigate a topic and deliver a concise recommendation memo.',
                'agents': [
                    {'agent_id': 'research_lead', 'name': 'Research Lead', 'role': 'researcher', 'purpose': 'Gather evidence and maintain the evidence ledger.', 'required_tool_ids': ['web'], 'optional_tool_ids': ['read_only_fs']},
                    {'agent_id': 'analyst', 'name': 'Analyst', 'role': 'synthesizer', 'purpose': 'Draft a concise recommendation memo.', 'optional_tool_ids': ['read_only_fs']},
                    {'agent_id': 'fact_reviewer', 'name': 'Fact Reviewer', 'role': 'reviewer', 'purpose': 'Challenge unsupported claims before delivery.', 'required_tool_ids': ['web'], 'optional_tool_ids': ['read_only_fs']},
                ],
                'memory_plan': {
                    'version': 1,
                    'plan_id': 'research_memory_plan',
                    'display_name': 'Research memory plan',
                    'surfaces': [
                        {'surface_id': 'mission_brief', 'file_name': 'mission_brief.md', 'load_policy': 'always', 'write_policy': 'shared', 'target_roles': ['researcher', 'synthesizer', 'reviewer'], 'semantic_slots': ['plan']},
                        {'surface_id': 'working_memory', 'file_name': 'working_memory.md', 'load_policy': 'always', 'write_policy': 'shared', 'target_roles': ['researcher', 'synthesizer'], 'semantic_slots': ['research', 'progress']},
                        {'surface_id': 'evidence_ledger', 'file_name': 'evidence_ledger.md', 'load_policy': 'on_demand', 'write_policy': 'append_only', 'target_roles': ['researcher', 'reviewer'], 'semantic_slots': ['research']},
                        {'surface_id': 'final_answer', 'file_name': 'final_answer.md', 'load_policy': 'always', 'write_policy': 'final', 'target_roles': ['synthesizer', 'reviewer'], 'semantic_slots': ['decisions']},
                        {'surface_id': 'artifact_index', 'file_name': 'artifact_index.md', 'load_policy': 'on_demand', 'write_policy': 'index', 'target_roles': ['synthesizer'], 'semantic_slots': ['artifacts']},
                    ],
                },
                'runtime_execution': {'continuous_improvement': {'enabled': True, 'mode': 'bounded_iteration', 'max_turns': 3}},
                'structure': {
                    'participants': [
                        {'participant_id': 'research_lead', 'kind': 'agent', 'name': 'Research Lead', 'role': 'researcher'},
                        {'participant_id': 'analyst', 'kind': 'agent', 'name': 'Analyst', 'role': 'synthesizer'},
                        {'participant_id': 'fact_reviewer', 'kind': 'agent', 'name': 'Fact Reviewer', 'role': 'reviewer'},
                    ],
                    'topology': {'pattern': 'sequential', 'execution_pattern': 'sequential_pipeline', 'final_participant_id': 'fact_reviewer', 'nodes': [], 'edges': []},
                },
            },
        ),
        _doc(
            'implementation',
            'Implementation Strike Team',
            'Inspect a repository, implement a scoped patch, verify it, and summarize the change.',
            ['implementation', 'repair', 'repo', 'review'],
            ['repo fixes', 'scoped feature work', 'patch + verification'],
            ['open-ended research'],
            {
                'team_name': 'Implementation Strike Team',
                'task_brief': 'Inspect a repository, implement a scoped patch, and verify it.',
                'agents': [
                    {'agent_id': 'repo_scout', 'name': 'Repo Scout', 'role': 'researcher', 'purpose': 'Map the repo and locate relevant files.'},
                    {'agent_id': 'builder', 'name': 'Builder', 'role': 'builder', 'purpose': 'Make the scoped changes and keep notes precise.'},
                    {'agent_id': 'reviewer', 'name': 'Reviewer', 'role': 'reviewer', 'purpose': 'Verify correctness and regression risk.'},
                    {'agent_id': 'delivery_owner', 'name': 'Delivery Owner', 'role': 'synthesizer', 'purpose': 'Summarize the final patch for the user.'},
                ],
                'memory_plan': {
                    'version': 1,
                    'plan_id': 'implementation_memory_plan',
                    'display_name': 'Implementation memory plan',
                    'surfaces': [
                        {'surface_id': 'mission_brief', 'file_name': 'mission_brief.md', 'load_policy': 'always', 'write_policy': 'shared', 'target_roles': ['researcher', 'builder', 'reviewer', 'synthesizer'], 'semantic_slots': ['plan']},
                        {'surface_id': 'working_memory', 'file_name': 'working_memory.md', 'load_policy': 'always', 'write_policy': 'shared', 'target_roles': ['researcher', 'builder', 'reviewer'], 'semantic_slots': ['research', 'progress']},
                        {'surface_id': 'implementation_notes', 'file_name': 'implementation_notes.md', 'load_policy': 'on_demand', 'write_policy': 'append_only', 'target_roles': ['builder'], 'semantic_slots': ['progress']},
                        {'surface_id': 'review_findings', 'file_name': 'review_findings.md', 'load_policy': 'on_demand', 'write_policy': 'append_only', 'target_roles': ['reviewer', 'synthesizer'], 'semantic_slots': ['decisions']},
                        {'surface_id': 'final_answer', 'file_name': 'final_answer.md', 'load_policy': 'always', 'write_policy': 'final', 'target_roles': ['synthesizer'], 'semantic_slots': ['decisions']},
                        {'surface_id': 'artifact_index', 'file_name': 'artifact_index.md', 'load_policy': 'on_demand', 'write_policy': 'index', 'target_roles': ['builder', 'synthesizer'], 'semantic_slots': ['artifacts']},
                    ],
                },
                'runtime_execution': {'continuous_improvement': {'enabled': True, 'mode': 'bounded_iteration', 'max_turns': 3}},
                'structure': {
                    'participants': [
                        {'participant_id': 'repo_scout', 'kind': 'agent', 'name': 'Repo Scout', 'role': 'researcher'},
                        {'participant_id': 'builder', 'kind': 'agent', 'name': 'Builder', 'role': 'builder'},
                        {'participant_id': 'reviewer', 'kind': 'agent', 'name': 'Reviewer', 'role': 'reviewer'},
                        {'participant_id': 'delivery_owner', 'kind': 'agent', 'name': 'Delivery Owner', 'role': 'synthesizer'},
                    ],
                    'topology': {'pattern': 'sequential', 'execution_pattern': 'sequential_pipeline', 'final_participant_id': 'delivery_owner', 'nodes': [], 'edges': []},
                },
            },
        ),
        _doc(
            'review_repair',
            'Review & Repair Team',
            'Audit an existing plan or implementation, identify defects, and produce a minimal repair patch.',
            ['review_repair', 'audit', 'repair', 'quality'],
            ['post-failure repair', 'audit + patch follow-up', 'quality regression cleanup'],
            ['greenfield implementation'],
            {
                'team_name': 'Review & Repair Team',
                'task_brief': 'Audit an existing implementation and produce a minimal repair patch.',
                'agents': [
                    {'agent_id': 'auditor', 'name': 'Auditor', 'role': 'reviewer', 'purpose': 'Identify the highest-value defects and regressions.'},
                    {'agent_id': 'repair_planner', 'name': 'Repair Planner', 'role': 'researcher', 'purpose': 'Turn review findings into a bounded repair plan.'},
                    {'agent_id': 'repair_builder', 'name': 'Repair Builder', 'role': 'builder', 'purpose': 'Apply the minimal repair patch.', 'required_tool_ids': ['workspace_fs'], 'optional_tool_ids': ['shell']},
                    {'agent_id': 'signoff_owner', 'name': 'Signoff Owner', 'role': 'synthesizer', 'purpose': 'Summarize repaired state and residual risk.'},
                ],
                'memory_plan': {
                    'version': 1,
                    'plan_id': 'review_repair_memory_plan',
                    'display_name': 'Review/repair memory plan',
                    'surfaces': [
                        {'surface_id': 'mission_brief', 'file_name': 'mission_brief.md', 'load_policy': 'always', 'write_policy': 'shared', 'target_roles': ['reviewer', 'researcher', 'builder', 'synthesizer'], 'semantic_slots': ['plan']},
                        {'surface_id': 'working_memory', 'file_name': 'working_memory.md', 'load_policy': 'always', 'write_policy': 'shared', 'target_roles': ['reviewer', 'researcher', 'builder'], 'semantic_slots': ['research', 'progress']},
                        {'surface_id': 'defect_log', 'file_name': 'defect_log.md', 'load_policy': 'on_demand', 'write_policy': 'append_only', 'target_roles': ['reviewer', 'researcher'], 'semantic_slots': ['research']},
                        {'surface_id': 'repair_log', 'file_name': 'repair_log.md', 'load_policy': 'on_demand', 'write_policy': 'append_only', 'target_roles': ['builder'], 'semantic_slots': ['progress']},
                        {'surface_id': 'final_answer', 'file_name': 'final_answer.md', 'load_policy': 'always', 'write_policy': 'final', 'target_roles': ['synthesizer'], 'semantic_slots': ['decisions']},
                        {'surface_id': 'artifact_index', 'file_name': 'artifact_index.md', 'load_policy': 'on_demand', 'write_policy': 'index', 'target_roles': ['builder', 'synthesizer'], 'semantic_slots': ['artifacts']},
                    ],
                },
                'runtime_execution': {'continuous_improvement': {'enabled': True, 'mode': 'bounded_iteration', 'max_turns': 3}},
                'structure': {
                    'participants': [
                        {'participant_id': 'auditor', 'kind': 'agent', 'name': 'Auditor', 'role': 'reviewer'},
                        {'participant_id': 'repair_planner', 'kind': 'agent', 'name': 'Repair Planner', 'role': 'researcher'},
                        {'participant_id': 'repair_builder', 'kind': 'agent', 'name': 'Repair Builder', 'role': 'builder'},
                        {'participant_id': 'signoff_owner', 'kind': 'agent', 'name': 'Signoff Owner', 'role': 'synthesizer'},
                    ],
                    'topology': {'pattern': 'sequential', 'execution_pattern': 'builder_reviewer_loop', 'final_participant_id': 'signoff_owner', 'nodes': [], 'edges': []},
                },
            },
        ),
    ]
