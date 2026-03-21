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
