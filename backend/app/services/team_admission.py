from __future__ import annotations

import re
from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _clean_text(value: Any, *, max_len: int = 256) -> str:
    return str(value or '').strip()[:max_len]


def _clean_id(value: Any, *, max_len: int = 128) -> str:
    text = _clean_text(value, max_len=max_len).lower()
    text = re.sub(r'[^a-z0-9_.-]+', '_', text)
    return text.strip('_')


def _unique_clean_ids(values: Any, *, limit: int = 24) -> list[str]:
    items = values if isinstance(values, list) else ([values] if isinstance(values, str) else [])
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = _clean_id(item)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
        if len(out) >= limit:
            break
    return out


_CAPABILITY_ALIAS_MAP: dict[str, str] = {
    'workspace_fs': 'filesystem_write',
    'read_only_fs': 'filesystem_read',
    'shell': 'shell_exec',
    'web': 'web_browse',
}
_CAPABILITY_LEGACY_ALIAS_MAP: dict[str, str] = {value: key for key, value in _CAPABILITY_ALIAS_MAP.items()}


def _runtime_capability_key(value: Any) -> str:
    clean = _clean_id(value, max_len=64)
    if not clean:
        return ''
    if clean in _CAPABILITY_ALIAS_MAP:
        return _CAPABILITY_ALIAS_MAP[clean]
    if clean in _CAPABILITY_LEGACY_ALIAS_MAP:
        return clean
    if clean in {'long_running_process', 'network_access'}:
        return clean
    return ''


def _legacy_capability_id(value: Any) -> str:
    clean = _runtime_capability_key(value)
    if not clean:
        return ''
    return _CAPABILITY_LEGACY_ALIAS_MAP.get(clean, clean)


def _normalize_participant_execution(agent: Any) -> dict[str, list[str]]:
    row = _as_dict(agent)
    required_caps = _unique_clean_ids(row.get('runtime_capabilities_required') or row.get('runtimeCapabilitiesRequired'))
    optional_caps = _unique_clean_ids(row.get('runtime_capabilities_optional') or row.get('runtimeCapabilitiesOptional') or row.get('runtime_capabilities_recommended') or row.get('runtimeCapabilitiesRecommended'))
    required_external = _unique_clean_ids(row.get('external_tool_requirements') or row.get('externalToolRequirements'))
    optional_external = _unique_clean_ids(row.get('external_tool_preferences') or row.get('externalToolPreferences'))
    purpose_text = f"{_clean_text(row.get('purpose'))} {_clean_text(row.get('name'))}".lower()
    role = _clean_id(row.get('role'))
    if role == 'builder' and re.search(r'ipynb|notebook|jupyter|file|json|python|script|workspace|code|코드|노트북|파일', purpose_text):
        required_caps = sorted(set(required_caps) | {'filesystem_write'})
    if role == 'builder':
        optional_caps = sorted(set(optional_caps) | {'shell_exec'})
    if role in {'researcher', 'reviewer'} and re.search(r'research|review|evidence|fact|검토|조사', purpose_text):
        optional_caps = sorted(set(optional_caps) | {'web_browse'})
    optional_caps = [item for item in optional_caps if item not in required_caps]
    optional_external = [item for item in optional_external if item not in required_external]
    return {
        'required_capabilities': required_caps,
        'optional_capabilities': optional_caps,
        'required_external_tools': required_external,
        'optional_external_tools': optional_external,
        'required_tools': sorted([_legacy_capability_id(item) for item in required_caps if _legacy_capability_id(item)] + list(required_external)),
        'optional_tools': sorted([_legacy_capability_id(item) for item in optional_caps if _legacy_capability_id(item)] + list(optional_external)),
    }


def build_team_capability_contract(team: Any) -> dict[str, Any]:
    row = _as_dict(team)
    requirements = _as_dict(row.get('requirements'))
    agent_contracts: list[dict[str, Any]] = []
    required_caps: set[str] = set()
    optional_caps: set[str] = set()
    required_external: set[str] = set()
    optional_external: set[str] = set()

    for requirement in _as_list(requirements.get('capabilities')):
        req = _as_dict(requirement)
        cap = _clean_id(req.get('capability_id') or req.get('capabilityId'))
        if not cap:
            continue
        if _clean_id(req.get('severity') or 'blocking') == 'blocking':
            required_caps.add(cap)
        else:
            optional_caps.add(cap)
    for requirement in _as_list(requirements.get('external_tools')):
        req = _as_dict(requirement)
        tool = _clean_id(req.get('external_tool_id') or req.get('externalToolId') or req.get('tool_id') or req.get('toolId'))
        if not tool:
            continue
        if _clean_id(req.get('severity') or 'blocking') == 'blocking':
            required_external.add(tool)
        else:
            optional_external.add(tool)

    for agent in _as_list(row.get('agents')):
        agent_row = _as_dict(agent)
        participant = _normalize_participant_execution(agent_row)
        agent_contracts.append({
            'agent_id': _clean_text(agent_row.get('agent_id') or agent_row.get('id') or agent_row.get('name') or agent_row.get('role') or 'agent', max_len=128),
            'agent_name': _clean_text(agent_row.get('name') or agent_row.get('agent_id') or agent_row.get('role') or 'agent', max_len=128),
            'role': _clean_id(agent_row.get('role') or 'agent', max_len=64) or 'agent',
            **participant,
        })
        required_caps.update(participant['required_capabilities'])
        optional_caps.update(participant['optional_capabilities'])
        required_external.update(participant['required_external_tools'])
        optional_external.update(participant['optional_external_tools'])

    optional_caps = {item for item in optional_caps if item not in required_caps}
    optional_external = {item for item in optional_external if item not in required_external}
    required_cap_list = sorted(required_caps)
    optional_cap_list = sorted(optional_caps)
    required_external_list = sorted(required_external)
    optional_external_list = sorted(optional_external)
    required_tools = sorted([_legacy_capability_id(item) for item in required_cap_list if _legacy_capability_id(item)] + required_external_list)
    optional_tools = sorted([_legacy_capability_id(item) for item in optional_cap_list if _legacy_capability_id(item)] + optional_external_list)
    return {
        'version': 'capability_contract_v2',
        'runtime_bound': False,
        'runtime_source': 'template',
        'status': 'unbound',
        'required_capabilities': required_cap_list,
        'optional_capabilities': optional_cap_list,
        'required_external_tools': required_external_list,
        'optional_external_tools': optional_external_list,
        'required_tools': required_tools,
        'optional_tools': optional_tools,
        'available_tools': [],
        'missing_required_capabilities': required_cap_list,
        'missing_optional_capabilities': optional_cap_list,
        'missing_required_external_tools': required_external_list,
        'missing_optional_external_tools': optional_external_list,
        'missing_required_tools': required_tools,
        'missing_optional_tools': optional_tools,
        'auto_installable_missing_tools': [],
        'mismatch_count': len(required_cap_list) + len(optional_cap_list) + len(required_external_list) + len(optional_external_list),
        'agent_contracts': agent_contracts,
    }


def compile_team_admission_decision(contract: Any) -> dict[str, Any]:
    row = _as_dict(contract)
    runtime_bound = row.get('runtime_bound') is True
    missing_required_tools = _unique_clean_ids(row.get('missing_required_tools'))
    missing_optional_tools = _unique_clean_ids(row.get('missing_optional_tools'))
    blocking_reason_codes: list[str] = []
    degrade_reason_codes: list[str] = []
    if not runtime_bound:
        blocking_reason_codes.append('runtime_unbound')
    if missing_required_tools:
        blocking_reason_codes.append('missing_required_tools')
    if missing_optional_tools:
        degrade_reason_codes.append('missing_optional_tools')
    blocking = runtime_bound and any(code != 'runtime_unbound' for code in blocking_reason_codes)
    degrade_only = (not blocking) and bool(degrade_reason_codes)
    status = 'unbound' if not runtime_bound else 'blocked' if blocking else 'degraded' if degrade_only else 'ready'
    return {
        'version': 'team_admission_decision_v1',
        'runtime_bound': runtime_bound,
        'capability_status': _clean_id(row.get('status') or 'unbound') or 'unbound',
        'status': status,
        'decision': 'defer' if not runtime_bound else 'deny' if blocking else 'allow',
        'runtime_ready': runtime_bound and not blocking,
        'blocking': blocking,
        'degrade_only': degrade_only,
        'reason_codes': _unique_clean_ids(blocking_reason_codes + degrade_reason_codes),
        'blocking_reason_codes': _unique_clean_ids(blocking_reason_codes),
        'degrade_reason_codes': _unique_clean_ids(degrade_reason_codes),
        'missing_required_tools': missing_required_tools,
        'missing_optional_tools': missing_optional_tools,
        'missing_required_tool_count': len(missing_required_tools),
        'missing_optional_tool_count': len(missing_optional_tools),
    }


def build_memory_acl_summary(memory_plan: Any, agents: Any, participants: Any | None = None) -> list[dict[str, Any]]:
    plan = _as_dict(memory_plan)
    surfaces = [_as_dict(item) for item in _as_list(plan.get('surfaces'))]
    default_load = {_clean_id(item) for item in _as_list(plan.get('default_load_surface_ids') or plan.get('defaultLoadSurfaceIds')) if _clean_id(item)}
    writable = {_clean_id(item) for item in _as_list(plan.get('writable_surface_ids') or plan.get('writableSurfaceIds')) if _clean_id(item)}
    role_order: list[str] = []
    seen_roles: set[str] = set()
    for source in (_as_list(agents), _as_list(participants)):
        for item in source:
            role_id = _clean_id(_as_dict(item).get('role') or _as_dict(item).get('role_id') or _as_dict(item).get('roleId'))
            if not role_id or role_id in seen_roles:
                continue
            seen_roles.add(role_id)
            role_order.append(role_id)
    out: list[dict[str, Any]] = []
    for role_id in role_order[:8]:
        read_surface_ids: list[str] = []
        write_surface_ids: list[str] = []
        publish_surface_ids: list[str] = []
        for surface in surfaces:
            surface_id = _clean_id(surface.get('surface_id') or surface.get('surfaceId') or surface.get('doc_id') or surface.get('id'))
            if not surface_id:
                continue
            target_roles = {_clean_id(item) for item in _as_list(surface.get('target_roles') or surface.get('targetRoles')) if _clean_id(item)}
            targets_role = not target_roles or role_id in target_roles
            write_policy = _clean_id(surface.get('write_policy') or surface.get('writePolicy') or 'shared') or 'shared'
            if surface_id in default_load or targets_role:
                if surface_id not in read_surface_ids:
                    read_surface_ids.append(surface_id)
            if targets_role and (surface_id in writable or write_policy not in {'read_only', 'readonly', 'none'}):
                if surface_id not in write_surface_ids:
                    write_surface_ids.append(surface_id)
            if targets_role and write_policy in {'final', 'index'} and surface_id not in publish_surface_ids:
                publish_surface_ids.append(surface_id)
        out.append({
            'role_id': role_id,
            'read_scope_mode': 'role_scoped_local_only',
            'write_scope_mode': 'role_scoped_reroute',
            'publish_scope_mode': 'declared_publish_only',
            'final_publish_rule': 'final_owner_declared_surface_required',
            'artifact_publish_rule': 'declared_artifact_surface_required',
            'read_surface_ids': read_surface_ids,
            'write_surface_ids': write_surface_ids,
            'publish_surface_ids': publish_surface_ids,
            'can_publish_final_answer': 'final_answer' in publish_surface_ids,
            'can_publish_artifact_index': 'artifact_index' in publish_surface_ids,
        })
    return out
