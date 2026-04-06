from __future__ import annotations

from typing import Any
from sqlmodel import Session

from app.models import Thread
from app.services.team_manifest import (
    build_team_manifest_payload,
    validate_team_manifest_payload,
    diff_team_manifest_payload,
    install_thread_team_manifest,
    _runtime_capability_key,
    _legacy_capability_id,
)
from app.services.team_blueprint_templates import list_team_blueprint_templates
from app.services.team_admission import build_memory_acl_summary, build_team_capability_contract, compile_team_admission_decision


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


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

    required_capabilities: set[str] = set()
    optional_capabilities: set[str] = set()
    required_external_tools: set[str] = set()
    optional_external_tools: set[str] = set()
    agent_contracts: list[dict[str, Any]] = []

    requirements = _as_dict(team.get('requirements'))
    for requirement in _as_list(requirements.get('capabilities')):
        row = _as_dict(requirement)
        capability_id = _runtime_capability_key(row.get('capability_id') or row.get('tool_id') or row.get('toolId'))
        if not capability_id:
            continue
        if _clean_id(row.get('severity') or 'blocking', 32) == 'blocking':
            required_capabilities.add(capability_id)
        else:
            optional_capabilities.add(capability_id)
    for requirement in _as_list(requirements.get('external_tools')):
        row = _as_dict(requirement)
        tool_id = _clean_id(row.get('tool_id') or row.get('toolId'), 64)
        if not tool_id:
            continue
        if _clean_id(row.get('severity') or 'blocking', 32) == 'blocking':
            required_external_tools.add(tool_id)
        else:
            optional_external_tools.add(tool_id)
    for requirement in _as_list(requirements.get('tools')):
        row = _as_dict(requirement)
        tool_id = _clean_id(row.get('tool_id') or row.get('toolId'), 64)
        if not tool_id:
            continue
        capability_id = _runtime_capability_key(tool_id)
        if capability_id:
            if _clean_id(row.get('severity') or 'blocking', 32) == 'blocking':
                required_capabilities.add(capability_id)
            else:
                optional_capabilities.add(capability_id)
        elif _clean_id(row.get('severity') or 'blocking', 32) == 'blocking':
            required_external_tools.add(tool_id)
        else:
            optional_external_tools.add(tool_id)

    for agent in team.get('agents') or []:
        agent_row = _as_dict(agent)
        role = _clean_id(_as_dict(agent_row.get('role_profile')).get('role') or agent_row.get('role') or 'agent', 64) or 'agent'
        purpose_text = f"{_clean_text(_as_dict(agent_row.get('role_profile')).get('purpose') or agent_row.get('purpose'), 256)} {_clean_text(agent_row.get('name'), 256)}".lower()
        explicit_required_capabilities = {
            capability_id
            for raw_key, enabled in _as_dict(agent_row.get('runtime_capabilities_required') or agent_row.get('runtimeCapabilitiesRequired')).items()
            for capability_id in [_runtime_capability_key(raw_key)]
            if enabled is not False and capability_id
        }
        explicit_optional_capabilities = {
            capability_id
            for raw_key, enabled in _as_dict(agent_row.get('runtime_capabilities_optional') or agent_row.get('runtimeCapabilitiesOptional')).items()
            for capability_id in [_runtime_capability_key(raw_key)]
            if enabled is not False and capability_id
        }
        explicit_required_external = set(_unique_tool_ids(agent_row.get('external_tool_requirements') or agent_row.get('externalToolRequirements') or []))
        explicit_optional_external = set(_unique_tool_ids(agent_row.get('external_tool_preferences') or agent_row.get('externalToolPreferences') or []))
        legacy_required = _unique_tool_ids(agent_row.get('required_tool_ids') or agent_row.get('requiredToolIds') or [])
        legacy_optional = _unique_tool_ids(agent_row.get('optional_tool_ids') or agent_row.get('optionalToolIds') or agent_row.get('recommended_tool_ids') or agent_row.get('recommendedToolIds') or [])
        for tool_id in legacy_required:
            capability_id = _runtime_capability_key(tool_id)
            if capability_id:
                explicit_required_capabilities.add(capability_id)
            else:
                explicit_required_external.add(tool_id)
        for tool_id in legacy_optional:
            capability_id = _runtime_capability_key(tool_id)
            if capability_id:
                explicit_optional_capabilities.add(capability_id)
            else:
                explicit_optional_external.add(tool_id)

        inferred_required_capabilities = set(explicit_required_capabilities)
        inferred_optional_capabilities = {item for item in explicit_optional_capabilities if item not in explicit_required_capabilities}
        inferred_required_external = set(explicit_required_external)
        inferred_optional_external = {item for item in explicit_optional_external if item not in explicit_required_external}

        code_like = any(token in purpose_text for token in ['ipynb', 'notebook', 'jupyter', 'file', 'json', 'python', 'script', 'workspace', 'code', '코드', '노트북', '파일'])
        if role == 'builder' and code_like:
            inferred_required_capabilities.add('filesystem_write')
            inferred_optional_capabilities.add('shell_exec')
        if role in {'researcher', 'reviewer'} and any(token in purpose_text for token in ['research', 'review', 'evidence', 'fact', '검토', '조사']):
            inferred_optional_capabilities.add('web_browse')

        required_capabilities.update(inferred_required_capabilities)
        optional_capabilities.update(item for item in inferred_optional_capabilities if item not in required_capabilities)
        required_external_tools.update(inferred_required_external)
        optional_external_tools.update(item for item in inferred_optional_external if item not in required_external_tools)

        agent_contracts.append({
            'agent_id': _clean_id(agent_row.get('agent_id') or agent_row.get('id') or agent_row.get('name') or 'agent'),
            'agent_name': _clean_text(agent_row.get('name') or agent_row.get('agent_id') or 'agent', 120) or 'agent',
            'role': role,
            'required_capabilities': sorted(inferred_required_capabilities),
            'optional_capabilities': sorted(item for item in inferred_optional_capabilities if item not in inferred_required_capabilities),
            'required_external_tools': sorted(inferred_required_external),
            'optional_external_tools': sorted(item for item in inferred_optional_external if item not in inferred_required_external),
            'required_tools': sorted([_legacy_capability_id(item) for item in inferred_required_capabilities] + list(inferred_required_external)),
            'optional_tools': sorted([_legacy_capability_id(item) for item in inferred_optional_capabilities if item not in inferred_required_capabilities] + list(item for item in inferred_optional_external if item not in inferred_required_external)),
        })

    required_capability_list = sorted(required_capabilities)
    optional_capability_list = sorted(item for item in optional_capabilities if item not in required_capabilities)
    required_external_list = sorted(required_external_tools)
    optional_external_list = sorted(item for item in optional_external_tools if item not in required_external_tools)
    required_tool_list = sorted([_legacy_capability_id(item) for item in required_capability_list] + required_external_list)
    optional_tool_list = sorted([_legacy_capability_id(item) for item in optional_capability_list] + optional_external_list)
    return {
        'version': 'capability_contract_v2',
        'runtime_bound': False,
        'runtime_source': 'template',
        'status': 'unbound',
        'required_capabilities': required_capability_list,
        'optional_capabilities': optional_capability_list,
        'required_external_tools': required_external_list,
        'optional_external_tools': optional_external_list,
        'required_tools': required_tool_list,
        'optional_tools': optional_tool_list,
        'available_tools': [],
        'missing_required_capabilities': required_capability_list,
        'missing_optional_capabilities': optional_capability_list,
        'missing_required_external_tools': required_external_list,
        'missing_optional_external_tools': optional_external_list,
        'missing_required_tools': required_tool_list,
        'missing_optional_tools': optional_tool_list,
        'auto_installable_missing_tools': [],
        'mismatch_count': len(required_capability_list) + len(optional_capability_list) + len(required_external_list) + len(optional_external_list),
        'agent_contracts': agent_contracts,
    }


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
    capability_contract = build_team_capability_contract({**team_seed, 'requirements': row.get('requirements') or team.get('requirements') or {}})
    admission_decision = compile_team_admission_decision(capability_contract)
    memory_acl_summary = build_memory_acl_summary(memory_plan, team_seed.get('agents') or team.get('agents') or [], structure.get('participants') or [])
    return {
        **row,
        'kind': 'ddalggak_team_blueprint',
        'version': 1,
        'primary_schema': 'team_blueprint_v1',
        'summary': {
            **summary,
            'memory_surface_count': len(list(_as_dict(memory_plan).get('surfaces') or [])),
            'runtime_bound': admission_decision.get('runtime_bound') is True,
            'admission_status': _clean_text(admission_decision.get('status'), 32) or None,
            'admission_decision': _clean_text(admission_decision.get('decision'), 32) or None,
            'blocking_reason_codes': _as_list(admission_decision.get('blocking_reason_codes'))[:8],
            'degrade_reason_codes': _as_list(admission_decision.get('degrade_reason_codes'))[:8],
            'memory_acl_summary': memory_acl_summary[:8],
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
            'admission_decision': admission_decision,
            'catalog': catalog,
            'team_seed': team_seed,
            'memory_acl_summary': memory_acl_summary,
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
