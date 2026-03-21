from __future__ import annotations

from typing import Any
from sqlmodel import Session

from app.models import Thread
from app.services.team_manifest import (
    build_team_manifest_payload,
    validate_team_manifest_payload,
    diff_team_manifest_payload,
    install_thread_team_manifest,
)
from app.services.team_blueprint_templates import list_team_blueprint_templates


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any, max_len: int = 256) -> str:
    text = str(value or '').strip()
    return text[:max_len]


def _clean_id(value: Any, max_len: int = 128) -> str:
    text = _clean_text(value, max_len).lower()
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


def _build_capability_contract(team: dict[str, Any], blueprint: dict[str, Any]) -> dict[str, Any]:
    existing = _as_dict(blueprint.get('capability_contract'))
    if existing:
        return existing
    required: list[str] = []
    optional: list[str] = []
    agent_contracts: list[dict[str, Any]] = []
    for agent in team.get('agents') or []:
        required_tools = _unique_tool_ids(agent.get('required_tool_ids') or agent.get('requiredToolIds') or [])
        optional_tools = _unique_tool_ids(agent.get('optional_tool_ids') or agent.get('optionalToolIds') or agent.get('recommended_tool_ids') or agent.get('recommendedToolIds') or [])
        optional_tools = [tool_id for tool_id in optional_tools if tool_id not in required_tools]
        required.extend(required_tools); optional.extend(optional_tools)
        agent_contracts.append({'agent_id': _clean_id(agent.get('agent_id') or agent.get('id') or agent.get('name') or 'agent'), 'agent_name': _clean_text(agent.get('name') or agent.get('agent_id') or 'agent', 120) or 'agent', 'role': _clean_id(agent.get('role') or 'agent', 64) or 'agent', 'required_tools': required_tools, 'optional_tools': optional_tools})
    required = _unique_tool_ids(required); optional = [tool_id for tool_id in _unique_tool_ids(optional) if tool_id not in required]
    return {'version': 'capability_contract_v1', 'runtime_bound': False, 'runtime_source': 'template', 'status': 'unbound', 'required_tools': required, 'optional_tools': optional, 'available_tools': [], 'missing_required_tools': required, 'missing_optional_tools': optional, 'auto_installable_missing_tools': [], 'mismatch_count': len(required) + len(optional), 'agent_contracts': agent_contracts}


def _manifest_to_blueprint_doc(manifest: Any) -> dict[str, Any]:
    row = _as_dict(manifest)
    structure = _as_dict(row.get('structure') or row.get('structure_v2') or row.get('structureV2'))
    team = _as_dict(row.get('team'))
    summary = _as_dict(row.get('summary'))
    blueprint = _as_dict(row.get('blueprint'))
    memory_plan = _as_dict(blueprint.get('memory_plan') or structure.get('memory_plan') or team.get('memory_plan') or team.get('memoryPlan'))
    title = _clean_text(blueprint.get('title') or team.get('team_name') or _as_dict(structure.get('metadata')).get('team_name') or 'Configured Team', 160) or 'Configured Team'
    description = _clean_text(blueprint.get('description') or team.get('task_brief') or _as_dict(structure.get('intent')).get('task_brief'), 512)
    topology = _as_dict(blueprint.get('topology')) or {
        'pattern': _clean_text(_as_dict(structure.get('topology')).get('pattern'), 64) or 'hybrid',
        'execution_pattern': _clean_text(_as_dict(structure.get('topology')).get('execution_pattern'), 64),
        'final_participant_id': _clean_text(_as_dict(structure.get('topology')).get('final_participant_id'), 128),
        'participants': structure.get('participants') or [],
        'nodes': _as_dict(structure.get('topology')).get('nodes') or [],
        'edges': _as_dict(structure.get('topology')).get('edges') or [],
    }
    runtime_policy = _as_dict(blueprint.get('runtime_policy')) or {
        'runtime_execution': _as_dict(_as_dict(structure.get('control_policy')).get('runtime_execution')),
    }
    catalog = _as_dict(blueprint.get('catalog')) or {
        'tags': list(team.get('catalog_tags') or row.get('catalog_tags') or []),
        'good_for': list(team.get('good_for') or row.get('good_for') or []),
        'bad_for': list(team.get('bad_for') or row.get('bad_for') or []),
    }
    artifact_contract = _as_dict(blueprint.get('artifact_contract')) or {
        'expected_outputs': list(_as_dict(structure.get('artifacts')).get('expected_outputs') or team.get('expected_outputs') or []),
        'artifact_contracts': list(_as_dict(structure.get('artifacts')).get('artifact_contracts') or team.get('artifact_contracts') or []),
    }
    team_seed = {
        **team,
        'structure': structure,
        'structure_v2': structure,
        'memory_plan': memory_plan,
        'primary_schema': 'team_blueprint_v1',
    }
    capability_contract = _build_capability_contract(team_seed, blueprint)
    return {
        **row,
        'kind': 'ddalggak_team_blueprint',
        'version': 1,
        'primary_schema': 'team_blueprint_v1',
        'summary': {
            **summary,
            'memory_surface_count': len(list(_as_dict(memory_plan).get('surfaces') or [])),
        },
        'blueprint': {
            'blueprint_id': _clean_text(blueprint.get('blueprint_id') or row.get('thread_id') or title.lower().replace(' ', '_'), 128),
            'title': title,
            'description': description,
            'task_archetype': _clean_text(blueprint.get('task_archetype') or summary.get('task_archetype') or 'general', 64) or 'general',
            'topology': topology,
            'structure': structure,
            'memory_plan': memory_plan,
            'memory_map': list(blueprint.get('memory_map') or []),
            'runtime_policy': runtime_policy,
            'artifact_contract': artifact_contract,
            'capability_contract': capability_contract,
            'catalog': catalog,
            'team_seed': team_seed,
        },
        'team': team_seed,
    }


def export_thread_team_blueprint(session: Session, thread: Thread) -> dict[str, Any]:
    return _manifest_to_blueprint_doc(build_team_manifest_payload(thread, _as_dict(thread.team_config_json and __import__('json').loads(thread.team_config_json) or {})))


def validate_team_blueprint_payload(blueprint: Any, apply_state: str = 'active') -> dict[str, Any]:
    result = validate_team_manifest_payload(blueprint, apply_state=apply_state)
    return {**result, 'manifest': _manifest_to_blueprint_doc(result.get('manifest'))}


def diff_team_blueprint_payload(current_blueprint: Any, candidate_blueprint: Any, apply_state: str = 'active') -> dict[str, Any]:
    result = diff_team_manifest_payload(current_blueprint, candidate_blueprint, apply_state=apply_state)
    result['current_manifest'] = _manifest_to_blueprint_doc(result.get('current_manifest'))
    result['candidate_manifest'] = _manifest_to_blueprint_doc(result.get('candidate_manifest'))
    return result


def install_thread_team_blueprint(session: Session, thread: Thread, blueprint: Any, apply_state: str = 'active') -> dict[str, Any]:
    manifest = install_thread_team_manifest(session, thread, blueprint, apply_state=apply_state)
    return _manifest_to_blueprint_doc(manifest)


def export_team_blueprint_templates() -> dict[str, Any]:
    return {'ok': True, 'items': list_team_blueprint_templates()}
