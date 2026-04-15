from __future__ import annotations

import re
from typing import Any

from sqlmodel import Session, select

from app.models import Thread
from app.services.conversation_team_config import get_team_config_payload, save_team_config_payload
from app.services.team_admission import build_memory_acl_summary, build_team_capability_contract, compile_team_admission_decision


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _clean_text(value: Any, *, max_len: int = 256) -> str:
    return str(value or "").strip()[:max_len]


def _clean_id(value: Any, *, max_len: int = 128) -> str:
    text = _clean_text(value, max_len=max_len).lower()
    text = re.sub(r"[^a-z0-9_.-]+", "_", text)
    return text.strip("_")


def _unique_text_list(value: Any, *, limit: int = 12, lower: bool = False, item_max_len: int = 128) -> list[str]:
    items = _as_list(value) if isinstance(value, list) else ([value] if isinstance(value, str) else [])
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = _clean_text(item, max_len=item_max_len)
        if not clean:
            continue
        rendered = clean.lower() if lower else clean
        key = rendered.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(rendered)
        if len(out) >= limit:
            break
    return out


def _normalize_string_map(raw: Any, *, limit: int = 32) -> dict[str, Any]:
    row = _as_dict(raw)
    out: dict[str, Any] = {}
    for key, value in row.items():
        clean_key = _clean_text(key, max_len=128)
        if not clean_key or len(out) >= limit:
            continue
        if isinstance(value, dict):
            out[clean_key] = value
        elif value is not None:
            out[clean_key] = _clean_text(value, max_len=512)
    return out


def _normalize_approval_decision(raw: Any, fallback: str = 'allow') -> str:
    value = _clean_id(raw, max_len=32)
    return value if value in {'allow', 'ask', 'deny'} else fallback


def _normalize_approval_matrix(raw: Any) -> dict[str, str]:
    row = _as_dict(raw)
    return {
        'codex_exec': _normalize_approval_decision(row.get('codex_exec') or row.get('codexExec') or row.get('provider_exec') or row.get('providerExec'), 'allow'),
        'gemini_exec': _normalize_approval_decision(row.get('gemini_exec') or row.get('geminiExec') or row.get('provider_exec') or row.get('providerExec'), 'allow'),
        'workspace_write': _normalize_approval_decision(row.get('workspace_write') or row.get('workspaceWrite') or row.get('file_write') or row.get('fileWrite'), 'allow'),
        'shell_exec': _normalize_approval_decision(row.get('shell_exec') or row.get('shellExec') or row.get('command_exec') or row.get('commandExec'), 'ask'),
        'network': _normalize_approval_decision(row.get('network'), 'deny'),
        'mcp': _normalize_approval_decision(row.get('mcp'), 'ask'),
        'verification': _normalize_approval_decision(row.get('verification') or row.get('tool_proxy') or row.get('toolProxy'), 'allow'),
    }


def _normalize_checkpointing_policy(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    return {
        'enabled': row.get('enabled') is not False,
        'write_on_turn_end': row.get('write_on_turn_end') is True or row.get('writeOnTurnEnd') is True,
        'write_on_approval_pause': row.get('write_on_approval_pause') is not False and row.get('writeOnApprovalPause') is not False,
        'write_on_resume': row.get('write_on_resume') is not False and row.get('writeOnResume') is not False,
        'expose_restore_context_to_agents': row.get('expose_restore_context_to_agents') is not False and row.get('exposeRestoreContextToAgents') is not False,
    }


def _bounded_int(value: Any, *, fallback: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        return fallback
    return max(minimum, min(maximum, parsed))


def _normalize_continuous_improvement_policy(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    return {
        'enabled': row.get('enabled') is True,
        'mode': _clean_id(row.get('mode') or row.get('strategy') or 'until_quality_threshold', max_len=64) or 'until_quality_threshold',
        'max_turns': _bounded_int(row.get('max_turns') if row.get('max_turns') is not None else row.get('maxTurns'), fallback=8, minimum=1, maximum=24),
        'max_total_actions': _bounded_int(row.get('max_total_actions') if row.get('max_total_actions') is not None else row.get('maxTotalActions'), fallback=48, minimum=1, maximum=200),
        'min_turns': _bounded_int(row.get('min_turns') if row.get('min_turns') is not None else row.get('minTurns'), fallback=1, minimum=1, maximum=12),
        'progress_report_each_turn': row.get('progress_report_each_turn') is not False and row.get('progressReportEachTurn') is not False,
        'stop_signals': _unique_text_list(row.get('stop_signals') or row.get('stopSignals') or ['quality_threshold_met', 'ready_for_user', 'final_answer_ready', 'done_enough'], limit=12),
        'self_refine_prompt': _clean_text(row.get('self_refine_prompt') or row.get('selfRefinePrompt'), max_len=1024),
    }


def _normalize_codex_provider_policy(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    config_overrides = _as_dict(row.get('config_overrides') or row.get('configOverrides'))
    mcp_servers = _as_dict(row.get('mcp_servers') or row.get('mcpServers'))
    if mcp_servers and 'mcp_servers' not in config_overrides:
        config_overrides = {**config_overrides, 'mcp_servers': mcp_servers}
    return {
        'sandbox_mode': _clean_id(row.get('sandbox_mode') or row.get('sandboxMode') or 'workspace-write', max_len=64) or 'workspace-write',
        'approval_policy': _clean_id(row.get('approval_policy') or row.get('approvalPolicy') or 'never', max_len=64) or 'never',
        'profile': _clean_text(row.get('profile'), max_len=128),
        'add_dirs': _unique_text_list(row.get('add_dirs') or row.get('addDirs'), limit=16, item_max_len=256),
        'config_overrides': config_overrides,
        'mcp_servers': mcp_servers,
    }


def _normalize_gemini_provider_policy(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    workspace_settings = _as_dict(row.get('workspace_settings') or row.get('workspaceSettings'))
    mcp_servers = _as_dict(row.get('mcp_servers') or row.get('mcpServers'))
    if mcp_servers and 'mcpServers' not in workspace_settings and 'mcp_servers' not in workspace_settings:
        workspace_settings = {**workspace_settings, 'mcpServers': mcp_servers}
    return {
        'approval_mode': _clean_id(row.get('approval_mode') or row.get('approvalMode') or 'default', max_len=64) or 'default',
        'settings_overwrite': _clean_id(row.get('settings_overwrite') or row.get('settingsOverwrite') or 'merge', max_len=64) or 'merge',
        'workspace_settings': workspace_settings,
        'extra_env': _normalize_string_map(row.get('extra_env') or row.get('extraEnv'), limit=24),
        'mcp_servers': mcp_servers,
    }


def _normalize_runtime_execution_policy(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    providers_row = _as_dict(row.get('providers') or row.get('provider_policies') or row.get('providerPolicies') or row)
    providers = {
        'codex': _normalize_codex_provider_policy(providers_row.get('codex') or providers_row.get('codex_cli') or providers_row.get('codexCli')),
        'gemini': _normalize_gemini_provider_policy(providers_row.get('gemini') or providers_row.get('gemini_cli') or providers_row.get('geminiCli')),
    }
    return {
        'checkpointing': _normalize_checkpointing_policy(row.get('checkpointing') or row.get('checkpoints')),
        'continuous_improvement': _normalize_continuous_improvement_policy(row.get('continuous_improvement') or row.get('continuousImprovement')),
        'approval_matrix': _normalize_approval_matrix(row.get('approval_matrix') or row.get('approvalMatrix')),
        'providers': providers,
        'codex': providers['codex'],
        'gemini': providers['gemini'],
    }


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


def _unique_clean_ids(values: Any, *, limit: int = 24, max_len: int = 128) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    if isinstance(values, list):
        items = values
    elif isinstance(values, str):
        items = [values]
    else:
        items = []
    for item in items:
        clean = _clean_id(item, max_len=max_len)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def _merge_unique_ids(*groups: Any, limit: int = 24, max_len: int = 128) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in _unique_clean_ids(group, limit=limit, max_len=max_len):
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
            if len(out) >= limit:
                return out
    return out


def _collect_runtime_capability_ids(*values: Any, limit: int = 24) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if isinstance(value, dict):
            items = [key for key, enabled in value.items() if enabled is not False]
        elif isinstance(value, list):
            items = value
        elif isinstance(value, str):
            items = [value]
        else:
            items = []
        for item in items:
            clean = _runtime_capability_key(item)
            if not clean or clean in seen:
                continue
            seen.add(clean)
            out.append(clean)
            if len(out) >= limit:
                return out
    return out


def _split_toolish_ids(values: Any) -> tuple[list[str], list[str]]:
    caps: list[str] = []
    tools: list[str] = []
    seen_caps: set[str] = set()
    seen_tools: set[str] = set()
    for raw in _unique_clean_ids(values, limit=32):
        capability_id = _runtime_capability_key(raw)
        if capability_id:
            if capability_id not in seen_caps:
                seen_caps.add(capability_id)
                caps.append(capability_id)
            continue
        if raw not in seen_tools:
            seen_tools.add(raw)
            tools.append(raw)
    return caps, tools


def _legacy_tool_alias_lists(required_capabilities: Any, optional_capabilities: Any, required_external_tools: Any, optional_external_tools: Any) -> dict[str, list[str]]:
    required = _merge_unique_ids([_legacy_capability_id(item) for item in _collect_runtime_capability_ids(required_capabilities)], required_external_tools, limit=24)
    optional = [
        item for item in _merge_unique_ids([_legacy_capability_id(item) for item in _collect_runtime_capability_ids(optional_capabilities)], optional_external_tools, limit=24)
        if item not in required
    ]
    recommended = _merge_unique_ids(required, optional, limit=24)
    return {
        'required_tool_ids': required,
        'optional_tool_ids': optional,
        'recommended_tool_ids': recommended,
    }


def _normalize_memory_contract(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    return {
        'read_surface_ids': _unique_text_list(row.get('read_surface_ids') or row.get('readSurfaceIds'), limit=16, lower=True, item_max_len=64),
        'write_surface_ids': _unique_text_list(row.get('write_surface_ids') or row.get('writeSurfaceIds'), limit=16, lower=True, item_max_len=64),
        'publish_surface_ids': _unique_text_list(row.get('publish_surface_ids') or row.get('publishSurfaceIds'), limit=16, lower=True, item_max_len=64),
        'enforcement_mode': _clean_id(row.get('enforcement_mode') or row.get('enforcementMode') or 'hard_role_scoped_local_only', max_len=64) or 'hard_role_scoped_local_only',
    }



def _normalize_knowledge_doc(raw: Any, *, index: int = 0) -> dict[str, Any] | None:
    row = _as_dict(raw)
    doc_id = _clean_text(row.get('doc_id') or row.get('docId') or row.get('slot') or row.get('name'), max_len=64).lower().replace(' ', '_')
    file_name = _clean_text(row.get('file_name') or row.get('fileName') or row.get('path') or row.get('name'), max_len=160)
    if not doc_id and not file_name:
        return None
    if not doc_id:
        doc_id = f'doc_{index + 1}'
    if not file_name:
        file_name = f'{doc_id}.md'
    return {
        'doc_id': doc_id,
        'file_name': file_name,
        'label': _clean_text(row.get('label') or row.get('title') or doc_id.replace('_', ' '), max_len=128) or doc_id,
        'purpose': _clean_text(row.get('purpose') or row.get('description'), max_len=256),
        'write_policy': _clean_text(row.get('write_policy') or row.get('writePolicy') or row.get('mode') or 'mutable', max_len=32).lower() or 'mutable',
        'required': row.get('required') is not False,
        'semantic_slot': _clean_text(row.get('semantic_slot') or row.get('semanticSlot') or doc_id, max_len=64).lower() or doc_id,
    }


def _normalize_knowledge_surface(raw: Any, *, fallback_profile: Any = None, fallback_team: Any = None) -> dict[str, Any] | None:
    row = _as_dict(raw)
    profile = _as_dict(fallback_profile)
    team = _as_dict(fallback_team)

    docs_source = _as_list(
        row.get('docs')
        or row.get('documents')
        or profile.get('docs')
        or team.get('knowledge_docs')
        or team.get('knowledgeDocs')
    )
    docs: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(docs_source):
        normalized = _normalize_knowledge_doc(item, index=index)
        if not normalized:
            continue
        if normalized['doc_id'] in seen_ids:
            continue
        seen_ids.add(normalized['doc_id'])
        docs.append(normalized)

    if not docs:
        docs = [
            {'doc_id': 'plan', 'file_name': 'plan.md', 'label': 'Plan', 'purpose': 'Execution plan and blueprint', 'write_policy': 'mutable', 'required': True, 'semantic_slot': 'plan'},
            {'doc_id': 'research', 'file_name': 'research.md', 'label': 'Research', 'purpose': 'Evidence and findings', 'write_policy': 'mutable', 'required': True, 'semantic_slot': 'research'},
            {'doc_id': 'progress', 'file_name': 'progress.md', 'label': 'Progress', 'purpose': 'Run log and intermediate status', 'write_policy': 'append_only', 'required': True, 'semantic_slot': 'progress'},
            {'doc_id': 'decisions', 'file_name': 'decisions.md', 'label': 'Decisions', 'purpose': 'Stable decisions and rationale', 'write_policy': 'append_only', 'required': True, 'semantic_slot': 'decisions'},
            {'doc_id': 'artifacts', 'file_name': 'artifacts.md', 'label': 'Artifacts', 'purpose': 'Artifact registry and deliverables', 'write_policy': 'append_only', 'required': True, 'semantic_slot': 'artifacts'},
        ]

    profile_id = _clean_text(
        row.get('profile_id')
        or row.get('profileId')
        or profile.get('profile_id')
        or profile.get('profileId')
        or team.get('team_name')
        or 'default_kb',
        max_len=128,
    ).lower().replace(' ', '_') or 'default_kb'

    return {
        'profile_id': profile_id,
        'display_name': _clean_text(
            row.get('display_name')
            or row.get('displayName')
            or profile.get('display_name')
            or profile.get('displayName')
            or team.get('team_name')
            or 'Default Knowledge Base',
            max_len=160,
        ) or 'Default Knowledge Base',
        'profile_kind': _clean_text(
            row.get('profile_kind')
            or row.get('profileKind')
            or profile.get('profile_kind')
            or profile.get('profileKind')
            or 'dynamic',
            max_len=64,
        ).lower() or 'dynamic',
        'docs': docs[:16],
        'stable_memory_files': [
            _clean_text(item, max_len=160)
            for item in _as_list(row.get('stable_memory_files') or row.get('stableMemoryFiles') or profile.get('stable_memory_files') or profile.get('stableMemoryFiles'))
            if _clean_text(item, max_len=160)
        ][:16],
    }


def _normalize_memory_policy(raw: Any, *, knowledge_surface: Any = None) -> dict[str, Any]:
    row = _as_dict(raw)
    stable_slots = [
        _clean_text(item, max_len=64).lower()
        for item in _as_list(row.get('stable_semantic_slots') or row.get('stableSemanticSlots') or ['decisions', 'artifacts'])
        if _clean_text(item, max_len=64)
    ][:16]
    mutable_slots = [
        _clean_text(item, max_len=64).lower()
        for item in _as_list(row.get('mutable_semantic_slots') or row.get('mutableSemanticSlots') or ['plan', 'research', 'progress'])
        if _clean_text(item, max_len=64)
    ][:16]
    immutable_file_names = [
        _clean_text(item, max_len=160)
        for item in _as_list(row.get('immutable_file_names') or row.get('immutableFileNames') or ['knowledge_base_profile.json', 'knowledge_base_profile.md', 'knowledge_base_contract.md'])
        if _clean_text(item, max_len=160)
    ][:16]
    if knowledge_surface:
        immutable_file_names = [
            *immutable_file_names,
            *[
                _clean_text(item, max_len=160)
                for item in _as_list(_as_dict(knowledge_surface).get('stable_memory_files'))
                if _clean_text(item, max_len=160)
            ],
        ]
        deduped: list[str] = []
        seen_files: set[str] = set()
        for item in immutable_file_names:
            key = item.lower()
            if not key or key in seen_files:
                continue
            seen_files.add(key)
            deduped.append(item)
        immutable_file_names = deduped[:16]
    return {
        'stable_semantic_slots': stable_slots,
        'mutable_semantic_slots': mutable_slots,
        'migration_strategy': _clean_text(row.get('migration_strategy') or row.get('migrationStrategy') or 'semantic_slot_preserving', max_len=64).lower() or 'semantic_slot_preserving',
        'preserve_history': row.get('preserve_history') is not False and row.get('preserveHistory') is not False,
        'immutable_file_names': immutable_file_names,
    }


def _normalize_team_payload(team_payload: Any) -> dict[str, Any]:
    team = _as_dict(team_payload)
    agents = []
    seen_ids: set[str] = set()
    for raw_agent in _as_list(team.get("agents")):
        agent = _as_dict(raw_agent)
        agent_id = _clean_text(agent.get("agent_id") or agent.get("agentId") or agent.get("id") or agent.get("name"), max_len=128)
        if not agent_id:
            continue
        if agent_id in seen_ids:
            continue
        seen_ids.add(agent_id)
        normalized = dict(agent)
        normalized["agent_id"] = agent_id
        if "agentId" in normalized and "agent_id" not in agent:
            normalized.pop("agentId", None)
        if "id" in normalized and "agent_id" not in agent:
            normalized.pop("id", None)
        agents.append(normalized)

    normalized_team = dict(team)
    normalized_team["agents"] = agents
    runtime_execution = _normalize_runtime_execution_policy(
        team.get('runtime_execution')
        or team.get('runtimeExecution')
        or _as_dict(team.get('control_policy')).get('runtime_execution')
        or _as_dict(team.get('controlPolicy')).get('runtimeExecution')
        or _as_dict(_as_dict(team.get('structure_v2')).get('control_policy')).get('runtime_execution')
        or _as_dict(_as_dict(team.get('structureV2')).get('controlPolicy')).get('runtimeExecution')
    )
    normalized_team['runtime_execution'] = runtime_execution
    raw_structure = team.get('structure_v2') or team.get('structureV2')
    if isinstance(raw_structure, dict):
        normalized_team['structure_v2'] = raw_structure
    return normalized_team

def _team_has_agents(team_payload: Any) -> bool:
    team = _normalize_team_payload(team_payload)
    return len(_as_list(team.get('agents'))) > 0

def _normalize_pattern_conflict_state(payload: Any) -> dict[str, Any] | None:
    raw = _as_dict(payload)
    if not raw:
        return None
    out = dict(raw)
    out['classification'] = _clean_text(raw.get('classification') or raw.get('type'), max_len=64).lower() or None
    out['current_pattern'] = _clean_text(raw.get('current_pattern') or raw.get('currentPattern'), max_len=64).lower() or None
    out['requested_pattern'] = _clean_text(raw.get('requested_pattern') or raw.get('requestedPattern') or raw.get('target_pattern') or raw.get('targetPattern'), max_len=64).lower() or None
    out['reason'] = _clean_text(raw.get('reason') or raw.get('detail') or raw.get('message'), max_len=256) or None
    return out


def _normalize_temporary_execution_override(payload: Any) -> dict[str, Any] | None:
    raw = _as_dict(payload)
    if not raw:
        return None
    out = dict(raw)
    out['mode'] = _clean_text(raw.get('mode') or raw.get('override_mode') or raw.get('overrideMode'), max_len=64).lower() or None
    out['original_pattern'] = _clean_text(raw.get('original_pattern') or raw.get('originalPattern'), max_len=64).lower() or None
    out['effective_pattern'] = _clean_text(raw.get('effective_pattern') or raw.get('effectivePattern'), max_len=64).lower() or None
    out['reason'] = _clean_text(raw.get('reason') or raw.get('detail') or raw.get('message'), max_len=256) or None
    return out


def _normalize_pattern_recovery_state(payload: Any) -> dict[str, Any] | None:
    raw = _as_dict(payload)
    if not raw:
        return None
    out = dict(raw)
    out['original_pattern'] = _clean_text(raw.get('original_pattern') or raw.get('originalPattern'), max_len=64).lower() or None
    out['recovery_mode'] = _clean_text(raw.get('recovery_mode') or raw.get('recoveryMode'), max_len=64).lower() or None
    out['reason'] = _clean_text(raw.get('reason') or raw.get('detail') or raw.get('message'), max_len=256) or None
    return out


def _normalize_requirement_entry(raw: Any, *, kind: str) -> dict[str, Any] | None:
    row = _as_dict(raw)
    if kind == "tool":
        tool_id = _clean_text(row.get("tool_id") or row.get("toolId") or row.get("id") or row.get("tool"), max_len=128).lower()
        if not tool_id:
            return None
        capability_id = _runtime_capability_key(tool_id)
        return {
            "tool_id": tool_id,
            "capability_id": capability_id or None,
            "required_by": _clean_text(row.get("required_by") or row.get("requiredBy") or row.get("agent_name") or row.get("agentName") or row.get("agent") or row.get("label") or "agent", max_len=128) or "agent",
            "severity": _clean_text(row.get("severity") or "blocking", max_len=32).lower() or "blocking",
            "reason": _clean_text(row.get("reason") or row.get("detail") or row.get("note"), max_len=256),
            "source_kind": _clean_text(row.get("source_kind") or row.get("sourceKind") or row.get("kind") or ("missing_capability" if capability_id else "missing_external_tool"), max_len=64).lower() or ("missing_capability" if capability_id else "missing_external_tool"),
        }
    if kind == "capability":
        capability_id = _runtime_capability_key(row.get("capability_id") or row.get("capabilityId") or row.get("id") or row.get("capability") or row.get("tool_id") or row.get("toolId"))
        if not capability_id:
            return None
        return {
            "capability_id": capability_id,
            "tool_id": _legacy_capability_id(capability_id),
            "required_by": _clean_text(row.get("required_by") or row.get("requiredBy") or row.get("agent_name") or row.get("agentName") or row.get("agent") or row.get("label") or "agent", max_len=128) or "agent",
            "severity": _clean_text(row.get("severity") or "blocking", max_len=32).lower() or "blocking",
            "reason": _clean_text(row.get("reason") or row.get("detail") or row.get("note"), max_len=256),
            "source_kind": _clean_text(row.get("source_kind") or row.get("sourceKind") or row.get("kind") or "missing_capability", max_len=64).lower() or "missing_capability",
        }
    if kind == "external_tool":
        tool_id = _clean_text(row.get("tool_id") or row.get("toolId") or row.get("id") or row.get("tool"), max_len=128).lower()
        if not tool_id:
            return None
        return {
            "tool_id": tool_id,
            "required_by": _clean_text(row.get("required_by") or row.get("requiredBy") or row.get("agent_name") or row.get("agentName") or row.get("agent") or row.get("label") or "agent", max_len=128) or "agent",
            "severity": _clean_text(row.get("severity") or "blocking", max_len=32).lower() or "blocking",
            "reason": _clean_text(row.get("reason") or row.get("detail") or row.get("note"), max_len=256),
            "source_kind": _clean_text(row.get("source_kind") or row.get("sourceKind") or row.get("kind") or "missing_external_tool", max_len=64).lower() or "missing_external_tool",
        }
    if kind == "credential":
        credential_key = _clean_text(row.get("credential_key") or row.get("credentialKey") or row.get("key") or "API_KEY", max_len=128) or "API_KEY"
        return {
            "credential_key": credential_key,
            "required_by": _clean_text(row.get("required_by") or row.get("requiredBy") or row.get("agent_name") or row.get("agentName") or row.get("agent") or row.get("label") or "agent", max_len=128) or "agent",
            "severity": _clean_text(row.get("severity") or "blocking", max_len=32).lower() or "blocking",
            "reason": _clean_text(row.get("reason") or row.get("detail") or row.get("note"), max_len=256),
            "source_kind": _clean_text(row.get("source_kind") or row.get("sourceKind") or row.get("kind") or "missing_credential", max_len=64).lower() or "missing_credential",
        }
    if kind == "skill":
        skill_id = _clean_text(row.get("skill_id") or row.get("skillId") or row.get("id") or row.get("skill"), max_len=128).lower()
        if not skill_id:
            return None
        return {
            "skill_id": skill_id,
            "required_by": _clean_text(row.get("required_by") or row.get("requiredBy") or row.get("agent_name") or row.get("agentName") or row.get("agent") or row.get("label") or "agent", max_len=128) or "agent",
            "severity": _clean_text(row.get("severity") or "blocking", max_len=32).lower() or "blocking",
            "reason": _clean_text(row.get("reason") or row.get("detail") or row.get("note"), max_len=256),
            "source_kind": _clean_text(row.get("source_kind") or row.get("sourceKind") or row.get("kind") or "missing_skill", max_len=64).lower() or "missing_skill",
        }
    return None



def _dedupe_entries(entries: list[dict[str, Any]], *, key_fields: tuple[str, ...], limit: int = 24) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        key = "|".join(_clean_text(entry.get(field), max_len=256).lower() for field in key_fields)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(entry)
        if len(out) >= limit:
            break
    return out




def _build_install_hints(requirements: dict[str, Any], *, has_thread_target: bool = False) -> list[str]:
    capabilities = _as_list(requirements.get("capabilities"))
    external_tools = _as_list(requirements.get("external_tools"))
    tools = _as_list(requirements.get("tools"))
    credentials = _as_list(requirements.get("credentials"))
    hints: list[str] = []
    capability_ids = {
        _runtime_capability_key(_as_dict(row).get('capability_id') or _as_dict(row).get('tool_id') or _as_dict(row).get('toolId'))
        for row in capabilities
        if isinstance(row, dict)
    }
    capability_ids = {value for value in capability_ids if value}
    tool_like_ids = {
        _clean_text(_as_dict(row).get('tool_id') or _as_dict(row).get('toolId'), max_len=128).lower()
        for row in tools + external_tools
        if isinstance(row, dict)
    }
    tool_like_ids = {value for value in tool_like_ids if value}
    if 'filesystem_write' in capability_ids or any(item in tool_like_ids for item in {'workspace_fs', 'write_file', 'workspace_write'}):
        hints.append('filesystem_write capability 또는 file writer tool을 연결하면 파일·노트북 산출물을 만들 수 있습니다.')
    if 'web_browse' in capability_ids or any(any(token in tool_id for token in ['web', 'browser', 'search']) for tool_id in tool_like_ids):
        hints.append('검색형 작업이면 web_browse capability 또는 browser/search external tool을 가진 agent 또는 preset을 사용하세요.')
    if credentials:
        keys = ', '.join(_clean_text(row.get('credential_key') or 'API_KEY', max_len=64) for row in credentials[:3] if isinstance(row, dict)) or 'API_KEY'
        hints.append(f'필요한 credential({keys})을 안전한 비밀 저장소나 환경 변수로 제공하세요.')
    if capabilities or external_tools or tools or credentials or _as_list(requirements.get('skills')):
        hints.append('manifest를 ddalggak Telegram의 /team install 또는 /team push 흐름과 함께 사용할 수 있습니다. 이 단계는 주로 team metadata와 requirement를 동기화합니다.')
    if has_thread_target:
        hints.append('이 thread에서는 Validate 후 active/pending team으로 바로 Install 할 수 있습니다.')
    deduped: list[str] = []
    seen: set[str] = set()
    for item in hints:
        key = _clean_text(item, max_len=256).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= 8:
            break
    return deduped


def _normalize_requirements(requirements_payload: Any, team_payload: Any = None) -> dict[str, Any]:
    raw = _as_dict(requirements_payload)
    team = _as_dict(team_payload)
    capability_entries: list[dict[str, Any]] = []
    external_tool_entries: list[dict[str, Any]] = []
    credential_entries: list[dict[str, Any]] = []
    skill_entries: list[dict[str, Any]] = []
    warnings: list[str] = []

    for row in _as_list(raw.get("capabilities") or raw.get('runtime_capabilities') or raw.get('runtimeCapabilities')):
        normalized = _normalize_requirement_entry(row, kind="capability")
        if normalized:
            capability_entries.append(normalized)
    for row in _as_list(raw.get("external_tools") or raw.get('externalTools')):
        normalized = _normalize_requirement_entry(row, kind="external_tool")
        if normalized:
            external_tool_entries.append(normalized)
    for row in _as_list(raw.get("tools")):
        normalized = _normalize_requirement_entry(row, kind="tool")
        if not normalized:
            continue
        if normalized.get('capability_id'):
            capability_entries.append(_normalize_requirement_entry(normalized, kind='capability') or {})
        else:
            external_tool_entries.append(_normalize_requirement_entry(normalized, kind='external_tool') or {})
    for row in _as_list(raw.get("credentials")):
        normalized = _normalize_requirement_entry(row, kind="credential")
        if normalized:
            credential_entries.append(normalized)
    for row in _as_list(raw.get("skills")):
        normalized = _normalize_requirement_entry(row, kind="skill")
        if normalized:
            skill_entries.append(normalized)
    for item in _as_list(raw.get("warnings")):
        text_item = _clean_text(item, max_len=256)
        if text_item:
            warnings.append(text_item)

    for raw_gap in _as_list(team.get("capability_gaps") or team.get("capabilityGaps")):
        gap = _as_dict(raw_gap)
        kind = _clean_text(gap.get("kind"), max_len=64).lower()
        detail = _clean_text(gap.get("detail") or gap.get("reason"), max_len=256)
        common = {
            **gap,
            "required_by": gap.get("agent_name") or gap.get("agentName") or gap.get("agent") or gap.get("label"),
            "reason": detail,
            "source_kind": kind,
        }
        if kind == "missing_capability":
            normalized = _normalize_requirement_entry(common, kind="capability")
            if normalized:
                capability_entries.append(normalized)
        elif kind == "missing_external_tool":
            normalized = _normalize_requirement_entry(common, kind="external_tool")
            if normalized:
                external_tool_entries.append(normalized)
        elif kind == "missing_tool":
            normalized = _normalize_requirement_entry(common, kind="tool")
            if normalized and normalized.get('capability_id'):
                capability_entries.append(_normalize_requirement_entry(normalized, kind='capability') or {})
            elif normalized:
                external_tool_entries.append(_normalize_requirement_entry(normalized, kind='external_tool') or {})
        elif kind == "missing_credential":
            normalized = _normalize_requirement_entry(common, kind="credential")
            if normalized:
                credential_entries.append(normalized)
        elif kind == "missing_skill":
            normalized = _normalize_requirement_entry(common, kind="skill")
            if normalized:
                skill_entries.append(normalized)
        if detail:
            warnings.append(detail)

    normalized_capabilities = _dedupe_entries(capability_entries, key_fields=("capability_id", "required_by", "source_kind"))
    normalized_external_tools = _dedupe_entries(external_tool_entries, key_fields=("tool_id", "required_by", "source_kind"))
    normalized_credentials = _dedupe_entries(credential_entries, key_fields=("credential_key", "required_by", "source_kind"))
    normalized_skills = _dedupe_entries(skill_entries, key_fields=("skill_id", "required_by", "source_kind"))
    normalized_warnings = _dedupe_entries([{"value": item} for item in warnings if item], key_fields=("value",), limit=12)

    legacy_tools = _dedupe_entries(
        [
            {
                'tool_id': entry.get('tool_id') or _legacy_capability_id(entry.get('capability_id')),
                'required_by': entry.get('required_by'),
                'severity': entry.get('severity'),
                'reason': entry.get('reason'),
                'source_kind': entry.get('source_kind') or 'missing_capability',
            }
            for entry in normalized_capabilities
            if entry.get('capability_id')
        ]
        + [
            {
                'tool_id': entry.get('tool_id'),
                'required_by': entry.get('required_by'),
                'severity': entry.get('severity'),
                'reason': entry.get('reason'),
                'source_kind': entry.get('source_kind') or 'missing_external_tool',
            }
            for entry in normalized_external_tools
            if entry.get('tool_id')
        ],
        key_fields=('tool_id', 'required_by', 'source_kind'),
    )

    install_hints = _build_install_hints({
        "capabilities": normalized_capabilities,
        "external_tools": normalized_external_tools,
        "tools": legacy_tools,
        "credentials": normalized_credentials,
        "skills": normalized_skills,
    }, has_thread_target=bool(team.get('thread_id') or team.get('threadId')))

    return {
        "capabilities": normalized_capabilities,
        "external_tools": normalized_external_tools,
        "tools": legacy_tools,
        "credentials": normalized_credentials,
        "skills": normalized_skills,
        "warnings": [row["value"] for row in normalized_warnings],
        "install_hints": install_hints,
        "summary": {
            "capability_count": len(normalized_capabilities),
            "external_tool_count": len(normalized_external_tools),
            "tool_count": len(legacy_tools),
            "credential_count": len(normalized_credentials),
            "skill_count": len(normalized_skills),
            "warning_count": len(normalized_warnings),
            "install_hint_count": len(install_hints),
        },
    }



def _normalize_install_action_entry(raw: Any, *, kind: str) -> dict[str, Any] | None:
    row = _as_dict(raw)
    if kind == 'tool_install_proposal':
        tool_id = _clean_text(row.get('tool_id') or row.get('toolId') or row.get('id') or row.get('tool'), max_len=128).lower()
        if not tool_id:
            return None
        capability_id = _runtime_capability_key(tool_id)
        if capability_id:
            return _normalize_install_action_entry({**row, 'capability_id': capability_id, 'tool_id': tool_id}, kind='capability_enable_proposal')
        return _normalize_install_action_entry({**row, 'tool_id': tool_id}, kind='external_tool_install_proposal')
    if kind == 'capability_enable_proposal':
        capability_id = _runtime_capability_key(row.get('capability_id') or row.get('capabilityId') or row.get('tool_id') or row.get('toolId') or row.get('id'))
        if not capability_id:
            return None
        return {
            'kind': 'capability_enable_proposal',
            'capability_id': capability_id,
            'tool_id': _legacy_capability_id(capability_id),
            'required_by': _clean_text(row.get('required_by') or row.get('requiredBy') or row.get('agent_name') or row.get('agentName') or row.get('agent') or row.get('label') or 'agent', max_len=128) or 'agent',
            'severity': _clean_text(row.get('severity') or 'blocking', max_len=32).lower() or 'blocking',
            'install_target': _clean_text(row.get('install_target') or row.get('installTarget') or 'runtime', max_len=64).lower() or 'runtime',
            'strategy': _clean_text(row.get('strategy') or 'enable_runtime_capability', max_len=64).lower() or 'enable_runtime_capability',
            'auto_installable': bool(row.get('auto_installable') or row.get('autoInstallable')),
            'approval_required': row.get('approval_required') is not False and row.get('approvalRequired') is not False,
            'reason': _clean_text(row.get('reason') or row.get('detail') or row.get('note'), max_len=256),
        }
    if kind == 'external_tool_install_proposal':
        tool_id = _clean_text(row.get('tool_id') or row.get('toolId') or row.get('id') or row.get('tool'), max_len=128).lower()
        if not tool_id:
            return None
        return {
            'kind': 'external_tool_install_proposal',
            'tool_id': tool_id,
            'required_by': _clean_text(row.get('required_by') or row.get('requiredBy') or row.get('agent_name') or row.get('agentName') or row.get('agent') or row.get('label') or 'agent', max_len=128) or 'agent',
            'severity': _clean_text(row.get('severity') or 'blocking', max_len=32).lower() or 'blocking',
            'install_target': _clean_text(row.get('install_target') or row.get('installTarget') or 'runtime', max_len=64).lower() or 'runtime',
            'strategy': _clean_text(row.get('strategy') or 'connect_runtime_tool', max_len=64).lower() or 'connect_runtime_tool',
            'auto_installable': bool(row.get('auto_installable') or row.get('autoInstallable')),
            'approval_required': row.get('approval_required') is not False and row.get('approvalRequired') is not False,
            'reason': _clean_text(row.get('reason') or row.get('detail') or row.get('note'), max_len=256),
        }
    if kind == 'credential_request':
        credential_key = _clean_text(row.get('credential_key') or row.get('credentialKey') or row.get('key') or 'API_KEY', max_len=128) or 'API_KEY'
        return {
            'kind': 'credential_request',
            'credential_key': credential_key,
            'required_by': _clean_text(row.get('required_by') or row.get('requiredBy') or row.get('agent_name') or row.get('agentName') or row.get('agent') or row.get('label') or 'agent', max_len=128) or 'agent',
            'severity': _clean_text(row.get('severity') or 'blocking', max_len=32).lower() or 'blocking',
            'delivery_method': _clean_text(row.get('delivery_method') or row.get('deliveryMethod') or 'env_var', max_len=64).lower() or 'env_var',
            'prompt': _clean_text(row.get('prompt') or f'Provide {credential_key} through env var or secret store.', max_len=256) or f'Provide {credential_key} through env var or secret store.',
            'approval_required': row.get('approval_required') is not False and row.get('approvalRequired') is not False,
            'reason': _clean_text(row.get('reason') or row.get('detail') or row.get('note'), max_len=256),
        }
    if kind == 'generated_skill_proposal':
        skill_id = _clean_text(row.get('skill_id') or row.get('skillId') or row.get('id') or row.get('skill'), max_len=128).lower()
        if not skill_id:
            return None
        return {
            'kind': 'generated_skill_proposal',
            'skill_id': skill_id,
            'required_by': _clean_text(row.get('required_by') or row.get('requiredBy') or row.get('agent_name') or row.get('agentName') or row.get('agent') or row.get('label') or 'agent', max_len=128) or 'agent',
            'severity': _clean_text(row.get('severity') or 'blocking', max_len=32).lower() or 'blocking',
            'strategy': _clean_text(row.get('strategy') or 'generate_inline_brief', max_len=64).lower() or 'generate_inline_brief',
            'approval_required': row.get('approval_required') is not False and row.get('approvalRequired') is not False,
            'prompt_brief': _clean_text(row.get('prompt_brief') or row.get('promptBrief'), max_len=256),
            'reason': _clean_text(row.get('reason') or row.get('detail') or row.get('note'), max_len=256),
        }
    return None


def _normalize_install_actions(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    capability_enable_proposals = _dedupe_entries(
        [normalized for item in _as_list(row.get('capability_enable_proposals') or row.get('capabilityEnableProposals')) if (normalized := _normalize_install_action_entry(item, kind='capability_enable_proposal'))],
        key_fields=('capability_id', 'required_by', 'strategy'),
    )
    external_tool_install_proposals = _dedupe_entries(
        [normalized for item in _as_list(row.get('external_tool_install_proposals') or row.get('externalToolInstallProposals')) if (normalized := _normalize_install_action_entry(item, kind='external_tool_install_proposal'))],
        key_fields=('tool_id', 'required_by', 'strategy'),
    )
    for item in _as_list(row.get('tool_install_proposals') or row.get('toolInstallProposals')):
        normalized = _normalize_install_action_entry(item, kind='tool_install_proposal')
        if not normalized:
            continue
        if normalized.get('kind') == 'capability_enable_proposal':
            capability_enable_proposals.append(normalized)
        else:
            external_tool_install_proposals.append(normalized)
    capability_enable_proposals = _dedupe_entries(capability_enable_proposals, key_fields=('capability_id', 'required_by', 'strategy'))
    external_tool_install_proposals = _dedupe_entries(external_tool_install_proposals, key_fields=('tool_id', 'required_by', 'strategy'))
    credential_requests = _dedupe_entries(
        [normalized for item in _as_list(row.get('credential_requests') or row.get('credentialRequests')) if (normalized := _normalize_install_action_entry(item, kind='credential_request'))],
        key_fields=('credential_key', 'required_by', 'delivery_method'),
    )
    generated_skill_proposals = _dedupe_entries(
        [normalized for item in _as_list(row.get('generated_skill_proposals') or row.get('generatedSkillProposals')) if (normalized := _normalize_install_action_entry(item, kind='generated_skill_proposal'))],
        key_fields=('skill_id', 'required_by', 'strategy'),
    )
    tool_install_proposals = _dedupe_entries(
        [
            {
                'kind': 'tool_install_proposal',
                'tool_id': proposal.get('tool_id') or _legacy_capability_id(proposal.get('capability_id')),
                'required_by': proposal.get('required_by'),
                'severity': proposal.get('severity'),
                'install_target': proposal.get('install_target'),
                'strategy': proposal.get('strategy'),
                'auto_installable': proposal.get('auto_installable'),
                'approval_required': proposal.get('approval_required'),
                'reason': proposal.get('reason'),
            }
            for proposal in capability_enable_proposals
        ]
        + [
            {
                'kind': 'tool_install_proposal',
                'tool_id': proposal.get('tool_id'),
                'required_by': proposal.get('required_by'),
                'severity': proposal.get('severity'),
                'install_target': proposal.get('install_target'),
                'strategy': proposal.get('strategy'),
                'auto_installable': proposal.get('auto_installable'),
                'approval_required': proposal.get('approval_required'),
                'reason': proposal.get('reason'),
            }
            for proposal in external_tool_install_proposals
        ],
        key_fields=('tool_id', 'required_by', 'strategy'),
    )
    return {
        'capability_enable_proposals': capability_enable_proposals,
        'external_tool_install_proposals': external_tool_install_proposals,
        'tool_install_proposals': tool_install_proposals,
        'credential_requests': credential_requests,
        'generated_skill_proposals': generated_skill_proposals,
        'summary': {
            'capability_enable_count': len(capability_enable_proposals),
            'external_tool_install_count': len(external_tool_install_proposals),
            'tool_install_count': len(tool_install_proposals),
            'credential_request_count': len(credential_requests),
            'generated_skill_count': len(generated_skill_proposals),
        },
    }



def _normalize_install_proposal(raw: Any) -> dict[str, Any] | None:
    row = _as_dict(raw)
    if not row:
        return None
    kind = _clean_text(row.get('kind') or 'capability_install_proposal', max_len=64) or 'capability_install_proposal'
    requirements = _normalize_requirements(row.get('requirements'), {})
    return {
        'kind': kind,
        'version': 1,
        'source': _clean_text(row.get('source') or 'team_requirement', max_len=64) or 'team_requirement',
        'blocking': bool(row.get('blocking')),
        'apply_state': 'active' if _clean_text(row.get('apply_state') or row.get('applyState') or 'pending', max_len=16).lower() == 'active' else 'pending',
        'gap_count': int(row.get('gap_count') or row.get('gapCount') or 0),
        'requirements': requirements,
        'actions': _normalize_install_actions(row.get('actions')),
        'suggested_commands': [_clean_text(v, max_len=128) for v in _as_list(row.get('suggested_commands')) if _clean_text(v, max_len=128)][:8],
        'gap_preview_lines': [_clean_text(v, max_len=256) for v in _as_list(row.get('gap_preview_lines')) if _clean_text(v, max_len=256)][:8],
    }




def _derive_credential_binding_state(credential_binding_state: Any, install_proposal: Any) -> dict[str, Any]:
    explicit = _normalize_credential_binding_state(credential_binding_state)
    if explicit.get('bindings'):
        return explicit
    proposal = _normalize_install_proposal(install_proposal) or {}
    derived_bindings = []
    for item in _as_list(_as_dict(proposal.get('actions')).get('credential_requests')):
        row = _as_dict(item)
        credential_key = (_clean_text(row.get('credential_key') or row.get('credentialKey') or row.get('key'), max_len=128) or '').upper()
        if not credential_key:
            continue
        derived_bindings.append({
            'credential_key': credential_key,
            'source': 'install_proposal',
            'delivery_method': _clean_text(row.get('delivery_method') or row.get('deliveryMethod') or 'pending_bind', max_len=64) or 'pending_bind',
            'masked_value': _clean_text(row.get('masked_value') or row.get('maskedValue'), max_len=128),
            'last4': _clean_text(row.get('last4'), max_len=16),
            'bound_at': _clean_text(row.get('bound_at') or row.get('boundAt'), max_len=64),
            'updated_at': _clean_text(row.get('updated_at') or row.get('updatedAt') or row.get('bound_at') or row.get('boundAt'), max_len=64),
        })
    if not derived_bindings and proposal:
        fallback_key = ''
        credentials = _as_list(_as_dict(proposal.get('requirements')).get('credentials'))
        tools = _as_list(_as_dict(proposal.get('requirements')).get('tools'))
        if credentials:
            first = _as_dict(credentials[0])
            fallback_key = (_clean_text(first.get('credential_key') or first.get('credentialKey') or first.get('key'), max_len=128) or '').upper()
        if not fallback_key and tools:
            first = _as_dict(tools[0])
            tool_id = _clean_text(first.get('tool_id') or first.get('toolId') or first.get('id'), max_len=128) or 'install_proposal'
            fallback_key = f"TOOL:{tool_id.upper()}"
        if not fallback_key:
            fallback_key = 'INSTALL_PROPOSAL'
        derived_bindings.append({
            'credential_key': fallback_key,
            'source': 'install_proposal',
            'delivery_method': 'pending_bind',
            'masked_value': None,
            'last4': None,
            'bound_at': None,
            'updated_at': None,
        })
    if derived_bindings:
        return _normalize_credential_binding_state({'bindings': derived_bindings})
    return explicit


def _build_default_install_proposal(requirements: Any, apply_state: str) -> dict[str, Any] | None:
    normalized_requirements = _normalize_requirements(requirements, {})
    gap_count = sum(len(_as_list(normalized_requirements.get(key))) for key in ('capabilities', 'external_tools', 'credentials', 'skills'))
    if gap_count <= 0:
        return None
    return {
        'kind': 'capability_install_proposal',
        'version': 1,
        'source': 'team_requirement',
        'blocking': gap_count > 0,
        'apply_state': 'active' if _clean_text(apply_state, max_len=16).lower() == 'active' else 'pending',
        'gap_count': gap_count,
        'requirements': normalized_requirements,
        'actions': _normalize_install_actions({}),
        'suggested_commands': [],
        'gap_preview_lines': [],
    }


def _normalize_credential_binding_state(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    bindings = _dedupe_entries([
        {
            'credential_key': (_clean_text(_as_dict(item).get('credential_key') or _as_dict(item).get('credentialKey') or _as_dict(item).get('key'), max_len=128) or '').upper(),
            'source': _clean_text(_as_dict(item).get('source') or 'telegram_command', max_len=64) or 'telegram_command',
            'delivery_method': _clean_text(_as_dict(item).get('delivery_method') or _as_dict(item).get('deliveryMethod') or 'session_vault', max_len=64) or 'session_vault',
            'masked_value': _clean_text(_as_dict(item).get('masked_value') or _as_dict(item).get('maskedValue'), max_len=128),
            'last4': _clean_text(_as_dict(item).get('last4'), max_len=16),
            'bound_at': _clean_text(_as_dict(item).get('bound_at') or _as_dict(item).get('boundAt'), max_len=64),
            'updated_at': _clean_text(_as_dict(item).get('updated_at') or _as_dict(item).get('updatedAt') or _as_dict(item).get('bound_at') or _as_dict(item).get('boundAt'), max_len=64),
        }
        for item in _as_list(row.get('bindings') or row.get('items') or row.get('credentials'))
        if (_clean_text(_as_dict(item).get('credential_key') or _as_dict(item).get('credentialKey') or _as_dict(item).get('key'), max_len=128) or '').upper()
    ], key_fields=('credential_key',), limit=24)
    return {
        'kind': 'credential_binding_state',
        'version': 1,
        'bindings': bindings,
        'bound_keys': [entry.get('credential_key') for entry in bindings if entry.get('credential_key')],
        'summary': {
            'bound_count': len(bindings),
        },
        'updated_at': _clean_text(row.get('updated_at') or row.get('updatedAt'), max_len=64),
    }


def _normalize_install_proposal_state(raw: Any) -> dict[str, Any] | None:
    row = _as_dict(raw)
    proposal = _normalize_install_proposal(row.get('proposal'))
    if not proposal:
        return None
    status = _clean_text(row.get('status') or 'awaiting_install_approval', max_len=64).lower() or 'awaiting_install_approval'
    if status not in {'awaiting_install_approval', 'installed_pending', 'applied_active', 'dismissed'}:
        status = 'awaiting_install_approval'
    return {
        'kind': 'team_install_proposal_state',
        'version': 1,
        'status': status,
        'apply_state': 'active' if _clean_text(row.get('apply_state') or row.get('applyState') or proposal.get('apply_state') or 'pending', max_len=16).lower() == 'active' else 'pending',
        'source': _clean_text(row.get('source') or proposal.get('source') or 'execution_gap', max_len=64) or 'execution_gap',
        'created_at': _clean_text(row.get('created_at') or row.get('createdAt'), max_len=64),
        'updated_at': _clean_text(row.get('updated_at') or row.get('updatedAt') or row.get('created_at') or row.get('createdAt'), max_len=64),
        'summary': _clean_text(row.get('summary'), max_len=256),
        'proposal': proposal,
    }



def _normalize_participant(raw: Any, index: int = 0) -> dict[str, Any] | None:
    row = _as_dict(raw)
    participant_id = _clean_text(row.get('participant_id') or row.get('participantId') or row.get('id') or row.get('agent_id') or row.get('agentId') or row.get('name') or f'participant_{index + 1}', max_len=128).lower()
    if not participant_id:
        return None
    provider_spec_row = _as_dict(row.get('provider_spec') or row.get('providerSpec'))
    provider_runtime_row = _as_dict(row.get('provider_runtime_config') or row.get('providerRuntimeConfig'))
    role_profile_row = _as_dict(row.get('role_profile') or row.get('roleProfile'))
    skill_package_row = _as_dict(row.get('skill_package') or row.get('skillPackage'))
    memory_contract_row = _as_dict(row.get('memory_contract') or row.get('memoryContract'))

    role = _clean_text(role_profile_row.get('role') or row.get('role') or row.get('role_id') or row.get('roleId') or 'specialist', max_len=64).lower() or 'specialist'
    kind = _clean_text(row.get('kind') or ('gate' if role == 'approval' else 'agent'), max_len=32).lower() or 'agent'
    label = _clean_text(row.get('name') or row.get('label') or participant_id, max_len=128) or participant_id
    purpose = _clean_text(role_profile_row.get('purpose') or row.get('purpose') or row.get('description'), max_len=256)
    specialty = _clean_text(role_profile_row.get('specialty') or row.get('specialty'), max_len=128)

    provider = _clean_text(provider_spec_row.get('provider') or row.get('provider') or row.get('llm_provider') or row.get('llmProvider'), max_len=64).lower()
    model = _clean_text(provider_spec_row.get('model') or row.get('model'), max_len=128)
    execution_channel = _clean_text(provider_spec_row.get('execution_channel') or provider_spec_row.get('executionChannel') or row.get('execution_channel') or row.get('executionChannel') or row.get('source'), max_len=64).lower()
    interaction_mode = _clean_text(provider_spec_row.get('interaction_mode') or provider_spec_row.get('interactionMode') or row.get('interaction_mode') or row.get('interactionMode'), max_len=64).lower()

    required_caps_legacy, required_external_legacy = _split_toolish_ids(row.get('required_tool_ids') or row.get('requiredToolIds'))
    optional_caps_legacy, optional_external_legacy = _split_toolish_ids(row.get('optional_tool_ids') or row.get('optionalToolIds') or row.get('recommended_tool_ids') or row.get('recommendedToolIds'))
    runtime_capabilities_required = _collect_runtime_capability_ids(row.get('runtime_capabilities_required') or row.get('runtimeCapabilitiesRequired'), required_caps_legacy)
    runtime_capabilities_optional = [
        item for item in _collect_runtime_capability_ids(row.get('runtime_capabilities_optional') or row.get('runtimeCapabilitiesOptional') or row.get('runtime_capabilities_preferred') or row.get('runtimeCapabilitiesPreferred'), optional_caps_legacy)
        if item not in runtime_capabilities_required
    ]
    external_tool_requirements = _merge_unique_ids(row.get('external_tool_requirements') or row.get('externalToolRequirements'), required_external_legacy, limit=16)
    external_tool_preferences = [
        item for item in _merge_unique_ids(row.get('external_tool_preferences') or row.get('externalToolPreferences') or row.get('external_tool_optional') or row.get('externalToolOptional'), optional_external_legacy, limit=16)
        if item not in external_tool_requirements
    ]
    legacy_tool_aliases = _legacy_tool_alias_lists(runtime_capabilities_required, runtime_capabilities_optional, external_tool_requirements, external_tool_preferences)

    attached_skill_ids = _merge_unique_ids(skill_package_row.get('skill_ids') or skill_package_row.get('attached_skill_ids') or skill_package_row.get('attachedSkillIds'), row.get('attached_skill_ids') or row.get('attachedSkillIds'), limit=16)
    generated_skill_briefs = _as_list(skill_package_row.get('generated_skill_briefs') or skill_package_row.get('generatedSkillBriefs') or row.get('generated_skill_briefs') or row.get('generatedSkillBriefs'))[:8]
    memory_contract = _normalize_memory_contract(memory_contract_row)

    return {
        'participant_id': participant_id,
        'kind': kind,
        'name': label,
        'label': label,
        'role': role,
        'purpose': purpose,
        'specialty': specialty,
        'provider': provider,
        'model': model,
        'execution_channel': execution_channel,
        'interaction_mode': interaction_mode,
        'capabilities': [_clean_text(v, max_len=128) for v in _as_list(row.get('capabilities') or row.get('skills')) if _clean_text(v, max_len=128)][:8],
        'attached_skill_ids': attached_skill_ids[:16],
        'generated_skill_briefs': generated_skill_briefs,
        'context_policy': _as_dict(row.get('context_policy') or row.get('contextPolicy')),
        'role_profile': {
            'role': role,
            'purpose': purpose,
            'specialty': specialty,
            'final_owner': bool(role_profile_row.get('final_owner') or role_profile_row.get('finalOwner') or row.get('final_owner') or row.get('finalOwner')),
        },
        'provider_spec': {
            'provider': provider,
            'model': model,
            'execution_channel': execution_channel,
            'interaction_mode': interaction_mode,
        },
        'provider_runtime_config': {
            'sandbox_mode': _clean_text(provider_runtime_row.get('sandbox_mode') or provider_runtime_row.get('sandboxMode'), max_len=64).lower(),
            'approval_policy': _clean_text(provider_runtime_row.get('approval_policy') or provider_runtime_row.get('approvalPolicy'), max_len=64).lower(),
            'workspace_settings': _as_dict(provider_runtime_row.get('workspace_settings') or provider_runtime_row.get('workspaceSettings')),
            'mcp_servers': _as_dict(provider_runtime_row.get('mcp_servers') or provider_runtime_row.get('mcpServers')),
            'network_policy': _clean_text(provider_runtime_row.get('network_policy') or provider_runtime_row.get('networkPolicy'), max_len=64).lower(),
        },
        'skill_package': {
            'skill_ids': attached_skill_ids[:16],
            'generated_skill_briefs': generated_skill_briefs,
        },
        'runtime_capabilities_required': {key: True for key in runtime_capabilities_required},
        'runtime_capabilities_optional': {key: True for key in runtime_capabilities_optional},
        'external_tool_requirements': external_tool_requirements[:16],
        'external_tool_preferences': external_tool_preferences[:16],
        'memory_contract': memory_contract,
        'required_tool_ids': legacy_tool_aliases['required_tool_ids'][:8],
        'optional_tool_ids': legacy_tool_aliases['optional_tool_ids'][:8],
        'recommended_tool_ids': legacy_tool_aliases['recommended_tool_ids'][:8],
    }



def _participant_id_by_label(participants: list[dict[str, Any]], raw: Any) -> str:
    target = _clean_text(raw, max_len=128)
    if not target:
        return ''
    target = target.lower()
    for row in participants:
        if _clean_text(row.get('participant_id'), max_len=128).lower() == target:
            return str(row.get('participant_id'))
    for row in participants:
        if _clean_text(row.get('name'), max_len=128).lower() == target:
            return str(row.get('participant_id'))
    for row in participants:
        if _clean_text(row.get('role'), max_len=64).lower() == target:
            return str(row.get('participant_id'))
    return ''


def _pattern_from_execution(execution_pattern: str, participant_count: int, explicit: str = '') -> str:
    direct = _clean_text(explicit, max_len=32).lower()
    if direct in {'single', 'router', 'supervisor', 'sequential', 'parallel', 'debate', 'committee', 'graph', 'workflow', 'hybrid'}:
        return direct
    pattern = _clean_text(execution_pattern, max_len=64).lower()
    if pattern == 'single_specialist':
        return 'single' if participant_count <= 1 else 'sequential'
    if pattern == 'sequential_pipeline':
        return 'sequential'
    if pattern == 'parallel_research_then_review_then_synthesize':
        return 'parallel'
    if pattern == 'multi_research_adjudication':
        return 'debate'
    if pattern in {'builder_reviewer_loop', 'operator_gated_workflow'}:
        return 'workflow'
    return 'single' if participant_count <= 1 else 'hybrid'


def _normalize_debate_policy(raw: Any, participants: list[dict[str, Any]], final_participant_id: str = '') -> dict[str, Any]:
    row = _as_dict(raw)
    rounds = row.get('rounds')
    try:
        rounds_value = max(1, min(6, int(rounds)))
    except (TypeError, ValueError):
        rounds_value = 1
    return {
        'rounds': rounds_value,
        'rebuttal_required': row.get('rebuttal_required') is not False and row.get('rebuttalRequired') is not False,
        'adjudicator_participant_id': _participant_id_by_label(participants, row.get('adjudicator_participant_id') or row.get('adjudicatorParticipantId') or row.get('judge') or final_participant_id) or None,
    }


def _normalize_consensus_policy(raw: Any, participants: list[dict[str, Any]]) -> dict[str, Any]:
    row = _as_dict(raw)
    quorum = row.get('quorum')
    try:
        quorum_value = max(1, min(max(len(participants), 1), int(quorum)))
    except (TypeError, ValueError):
        quorum_value = max(1, (len(participants) + 1) // 2)
    return {
        'mode': _clean_text(row.get('mode') or row.get('policy') or 'majority', max_len=32).lower() or 'majority',
        'quorum': quorum_value,
    }


def _build_structure_validation(*args, **kwargs):
    from app.services.team_manifest_structure import _build_structure_validation as _impl
    return _impl(*args, **kwargs)



def _build_structure_v2_from_team(*args, **kwargs):
    from app.services.team_manifest_structure import _build_structure_v2_from_team as _impl
    return _impl(*args, **kwargs)



def _normalize_structure_v2(*args, **kwargs):
    from app.services.team_manifest_structure import _normalize_structure_v2 as _impl
    return _impl(*args, **kwargs)



def _derive_team_from_structure_v2(*args, **kwargs):
    from app.services.team_manifest_structure import _derive_team_from_structure_v2 as _impl
    return _impl(*args, **kwargs)


def _normalize_manifest(manifest: Any, *, fallback_thread: Thread | None = None, fallback_apply_state: str = "active") -> dict[str, Any]:
    raw = _as_dict(manifest)
    team_config = _as_dict(raw.get("team_config"))

    explicit_structure = _as_dict(raw.get('structure_v2') or raw.get('structureV2'))
    has_explicit_structure = bool(explicit_structure)

    if not team_config:
        team_seed = _derive_team_from_structure_v2(explicit_structure) if has_explicit_structure else (raw.get("team") or raw.get("active_team") or raw.get("pending_team"))
        team_only = _normalize_team_payload(team_seed)
        status = "active" if fallback_apply_state == "active" else "suggested"
        team_config = {
            "status": status,
            "composition_mode": _clean_text(raw.get("composition_mode") or team_only.get("composition_mode") or "structured", max_len=32) or "structured",
            "proposal_mode": _clean_text(raw.get("proposal_mode") or team_only.get("proposal_mode") or ("apply" if fallback_apply_state == "active" else "refine"), max_len=32) or ("apply" if fallback_apply_state == "active" else "refine"),
            "active_team": team_only if fallback_apply_state == "active" else {},
            "pending_team": team_only if fallback_apply_state == "pending" else {},
        }
    else:
        normalized_status = _clean_text(team_config.get("status") or ("active" if fallback_apply_state == "active" else "suggested"), max_len=24).lower() or ("active" if fallback_apply_state == "active" else "suggested")
        team_config = {
            "status": normalized_status,
            "composition_mode": _clean_text(team_config.get("composition_mode") or "structured", max_len=32) or "structured",
            "proposal_mode": _clean_text(team_config.get("proposal_mode") or ("apply" if fallback_apply_state == "active" else "refine"), max_len=32) or ("apply" if fallback_apply_state == "active" else "refine"),
            "active_team": _normalize_team_payload(team_config.get("active_team")),
            "pending_team": _normalize_team_payload(team_config.get("pending_team")),
        }

    active_team = _normalize_team_payload(team_config.get("active_team"))
    pending_team = _normalize_team_payload(team_config.get("pending_team"))
    has_active_team = _team_has_agents(active_team)
    has_pending_team = _team_has_agents(pending_team)
    status = _clean_text(team_config.get("status") or ("active" if has_active_team else "suggested" if has_pending_team else "none"), max_len=24).lower() or "none"
    composition_mode = _clean_text(team_config.get("composition_mode") or active_team.get("composition_mode") or pending_team.get("composition_mode") or "structured", max_len=32) or "structured"
    proposal_mode = _clean_text(team_config.get("proposal_mode") or active_team.get("proposal_mode") or pending_team.get("proposal_mode") or ("create" if composition_mode == "freeform" else "suggest"), max_len=32) or ("create" if composition_mode == "freeform" else "suggest")
    team = active_team if has_active_team else pending_team if has_pending_team else (active_team or pending_team)

    requirements = _normalize_requirements(
        raw.get("requirements") or team_config.get("requirements") or team.get("requirements") or _as_dict(raw.get('structure_v2') or raw.get('structureV2')).get('requirements'),
        {**team, 'thread_id': _clean_text(raw.get('thread_id') or (fallback_thread.id if fallback_thread else ''), max_len=128)},
    )
    install_proposal = _normalize_install_proposal(raw.get('install_proposal') or team_config.get('install_proposal'))
    if install_proposal is None:
        install_proposal = _build_default_install_proposal(requirements, fallback_apply_state)
    install_proposal_state = _normalize_install_proposal_state(raw.get('install_proposal_state') or raw.get('installProposalState') or team_config.get('install_proposal_state'))
    credential_binding_state = _derive_credential_binding_state(raw.get('credential_binding_state') or raw.get('credentialBindingState') or team_config.get('credential_binding_state'), install_proposal)
    pattern_conflict = _normalize_pattern_conflict_state(raw.get('pattern_conflict') or raw.get('patternConflict') or team_config.get('pattern_conflict'))
    temporary_execution_override = _normalize_temporary_execution_override(raw.get('temporary_execution_override') or raw.get('temporaryExecutionOverride') or team_config.get('temporary_execution_override'))
    pattern_recovery = _normalize_pattern_recovery_state(raw.get('pattern_recovery') or raw.get('patternRecovery') or team_config.get('pattern_recovery'))
    explicit_team_input = _as_dict(raw.get('team'))
    structure_source = explicit_structure if has_explicit_structure else (team.get('structure_v2') or raw.get('structure_v2') or raw.get('structureV2'))
    structure_v2 = _normalize_structure_v2(structure_source, team_payload={**team, 'requirements': requirements}, apply_state=fallback_apply_state, install_proposal_state=install_proposal_state, credential_binding_state=credential_binding_state)
    if explicit_team_input and not has_explicit_structure and len(_as_list(team.get('agents'))) > 1:
        topology = _as_dict(structure_v2.get('topology'))
        if not _clean_text(topology.get('execution_pattern'), max_len=64):
            structure_v2['topology'] = {**topology, 'pattern': 'sequential'}
            structure_v2['validation'] = _build_structure_validation('sequential', _as_list(structure_v2.get('participants')), _as_list(topology.get('edges')), _participant_id_by_label(_as_list(structure_v2.get('participants')), topology.get('final_participant_id') or _as_dict(structure_v2.get('control_policy')).get('final_answer_owner_participant_id')))
    compatibility_team = _normalize_team_payload(_derive_team_from_structure_v2(structure_v2) or team)
    publish_contract_issues = _summarize_publish_contract_issues(structure_v2)
    capability_contract = build_team_capability_contract({**compatibility_team, 'requirements': requirements})
    admission_decision = compile_team_admission_decision(capability_contract)
    memory_acl_summary = build_memory_acl_summary(_as_dict(structure_v2.get('memory_plan')), _as_list(compatibility_team.get('agents')), _as_list(structure_v2.get('participants')))
    summary = {
        "agent_count": len(_as_list(compatibility_team.get("agents"))),
        "participant_count": len(_as_list(structure_v2.get("participants"))),
        "structure_pattern": _clean_text(_as_dict(structure_v2.get("topology")).get("pattern"), max_len=32) or None,
        "structure_warnings": len(_as_list(_as_dict(structure_v2.get("validation")).get("warnings"))),
        "status": status,
        "composition_mode": composition_mode,
        "proposal_mode": proposal_mode,
        "tool_requirements": len(_as_list(requirements.get("tools"))),
        "credential_requirements": len(_as_list(requirements.get("credentials"))),
        "install_hints": len(_as_list(requirements.get("install_hints"))),
        "install_proposal_gaps": int((install_proposal or {}).get('gap_count') or 0),
        "install_proposal_state": _clean_text((install_proposal_state or {}).get('status'), max_len=64) or None,
        "bound_credentials": int((credential_binding_state or {}).get('summary', {}).get('bound_count') or 0),
        "pattern_conflict": _clean_text((pattern_conflict or {}).get('classification'), max_len=64) or None,
        "temporary_execution_override": _clean_text((temporary_execution_override or {}).get('effective_pattern') or (temporary_execution_override or {}).get('mode'), max_len=64) or None,
        "pattern_recovery": _clean_text((pattern_recovery or {}).get('recovery_mode') or (pattern_recovery or {}).get('original_pattern'), max_len=64) or None,
        "knowledge_doc_count": len(_as_list(_as_dict(structure_v2.get('knowledge_surface')).get('docs'))),
        "memory_surface_count": len(_as_list(_as_dict(structure_v2.get('memory_plan')).get('surfaces'))),
        "memory_contract_enforcement": {
            "read_scope": "hard_role_scoped_local_only",
            "write_scope": "hard_reroute",
            "publish_scope": "declared_only",
            "final_publish_rule": "final_owner_declared_surface_required",
            "artifact_publish_rule": "declared_artifact_surface_required",
        },
        "publish_contract_readiness": {
            "final_owner": publish_contract_issues.get('final_owner_publish_label') or None,
            "final_owner_id": publish_contract_issues.get('final_owner_id') or None,
            "final_owner_missing": bool(publish_contract_issues.get('final_owner_missing')),
            "final_answer_publish_ok": not bool(publish_contract_issues.get('final_owner_publish_blocked')) and not bool(publish_contract_issues.get('final_owner_missing')),
            "final_answer_publish_state": 'unset' if bool(publish_contract_issues.get('final_owner_missing')) else ('blocked' if bool(publish_contract_issues.get('final_owner_publish_blocked')) else 'ready'),
            "artifact_publish_ok": not bool(publish_contract_issues.get('artifact_publish_missing')),
            "artifact_publish_state": 'blocked' if bool(publish_contract_issues.get('artifact_publish_missing')) else 'ready',
            "artifact_publishers": _as_list(publish_contract_issues.get('artifact_publishers'))[:6],
            "artifact_publisher_ids": _as_list(publish_contract_issues.get('artifact_publisher_ids'))[:12],
        },
        "stable_memory_slot_count": len(_as_list(_as_dict(structure_v2.get('memory_policy')).get('stable_semantic_slots'))),
        "continuous_improvement_enabled": _as_dict(_as_dict(structure_v2.get('control_policy')).get('runtime_execution')).get('continuous_improvement', {}).get('enabled') is True,
        "codex_sandbox_mode": _clean_text(_as_dict(_as_dict(_as_dict(structure_v2.get('control_policy')).get('runtime_execution')).get('providers')).get('codex').get('sandbox_mode'), max_len=64) or None,
        "codex_mcp_count": len(_as_dict(_as_dict(_as_dict(_as_dict(structure_v2.get('control_policy')).get('runtime_execution')).get('providers')).get('codex').get('mcp_servers'))),
        "gemini_mcp_count": len(_as_dict(_as_dict(_as_dict(_as_dict(structure_v2.get('control_policy')).get('runtime_execution')).get('providers')).get('gemini').get('mcp_servers'))),
        "runtime_bound": admission_decision.get('runtime_bound') is True,
        "admission_status": _clean_text(admission_decision.get('status'), max_len=32) or None,
        "admission_decision": _clean_text(admission_decision.get('decision'), max_len=32) or None,
        "blocking_reason_codes": _as_list(admission_decision.get('blocking_reason_codes'))[:8],
        "degrade_reason_codes": _as_list(admission_decision.get('degrade_reason_codes'))[:8],
        "memory_acl_summary": memory_acl_summary[:8],
    }

    manifest_out = {
        "kind": "ddalggak_team_blueprint",
        "version": 1,
        "primary_schema": "team_blueprint_v1",
        "thread_id": _clean_text(raw.get("thread_id") or (fallback_thread.id if fallback_thread else ""), max_len=128) or None,
        "service_id": _clean_text(raw.get("service_id") or (fallback_thread.service_id if fallback_thread else ""), max_len=128) or None,
        "status": status,
        "composition_mode": composition_mode,
        "proposal_mode": proposal_mode,
        "compatibility": {
            "ddalggak": True,
            "goc": True,
            "install_target": "thread_team_config",
        },
        "summary": summary,
        "requirements": requirements,
        "capability_contract": capability_contract,
        "admission_decision": admission_decision,
        "install_proposal": install_proposal,
        "install_proposal_state": install_proposal_state,
        "credential_binding_state": credential_binding_state,
        "pattern_conflict": pattern_conflict,
        "temporary_execution_override": temporary_execution_override,
        "pattern_recovery": pattern_recovery,
        "structure_v2": structure_v2,
        "team": {**compatibility_team, "structure_v2": structure_v2},
        "team_config": {
            "status": status,
            "composition_mode": composition_mode,
            "proposal_mode": proposal_mode,
            "active_team": active_team,
            "pending_team": pending_team,
            "install_proposal": install_proposal,
            "install_proposal_state": install_proposal_state,
            "credential_binding_state": credential_binding_state,
            "pattern_conflict": pattern_conflict,
            "temporary_execution_override": temporary_execution_override,
            "pattern_recovery": pattern_recovery,
            "structure_v2": structure_v2,
        },
    }
    return manifest_out


def build_team_manifest_payload(thread: Thread, team_config_payload: dict[str, Any] | None) -> dict[str, Any]:
    return _normalize_manifest(team_config_payload or {}, fallback_thread=thread, fallback_apply_state="active")


def validate_team_manifest_payload(manifest: Any, apply_state: str = "active") -> dict[str, Any]:
    clean_state = "pending" if str(apply_state or "active").strip().lower() == "pending" else "active"
    normalized = _normalize_manifest(manifest, fallback_apply_state=clean_state)
    team = normalized.get("team") if isinstance(normalized.get("team"), dict) else {}
    agents = _as_list(team.get("agents"))
    structure = _as_dict(normalized.get('structure_v2') or normalized.get('structureV2') or team.get('structure_v2') or team.get('structureV2'))
    topology = _as_dict(structure.get('topology'))
    memory_plan = _as_dict(normalized.get('memory_plan') or normalized.get('memoryPlan') or structure.get('memory_plan') or structure.get('memoryPlan') or team.get('memory_plan') or team.get('memoryPlan'))
    errors: list[str] = []
    if not agents:
        errors.append("team manifest must include at least one agent")
    seen_ids: set[str] = set()
    role_ids: set[str] = set()
    for raw_agent in agents:
        agent = _as_dict(raw_agent)
        agent_id = _clean_text(agent.get("agent_id") or agent.get("name"), max_len=128)
        if not agent_id:
            errors.append("team manifest contains an agent without agent_id")
            continue
        if agent_id in seen_ids:
            errors.append(f"duplicate agent_id: {agent_id}")
            continue
        seen_ids.add(agent_id)
        role_id = _clean_text(agent.get('role') or '', max_len=64).lower()
        if role_id:
            role_ids.add(role_id)
    participant_ids = {_clean_text(_as_dict(item).get('participant_id') or _as_dict(item).get('id'), max_len=128) for item in _as_list(structure.get('participants'))}
    participant_ids = {value for value in participant_ids if value}
    node_ids = {_clean_text(_as_dict(item).get('node_id') or _as_dict(item).get('id'), max_len=128) for item in _as_list(topology.get('nodes'))}
    node_ids = {value for value in node_ids if value}
    valid_edge_refs = participant_ids | node_ids
    final_participant_id = _clean_text(topology.get('final_participant_id') or topology.get('finalParticipantId'), max_len=128)
    if final_participant_id and participant_ids and final_participant_id not in participant_ids:
        errors.append(f"final_participant_id references an unknown participant: {final_participant_id}")
    for raw_edge in _as_list(topology.get('edges')):
        edge = _as_dict(raw_edge)
        src = _clean_text(edge.get('from') or edge.get('source') or edge.get('from_node_id'), max_len=128)
        dst = _clean_text(edge.get('to') or edge.get('target') or edge.get('to_node_id'), max_len=128)
        if src and valid_edge_refs and src not in valid_edge_refs:
            errors.append(f"topology edge references unknown source node: {src}")
        if dst and valid_edge_refs and dst not in valid_edge_refs:
            errors.append(f"topology edge references unknown target node: {dst}")
    surface_ids: set[str] = set()
    for raw_surface in _as_list(memory_plan.get('surfaces')):
        surface = _as_dict(raw_surface)
        surface_id = _clean_text(surface.get('surface_id') or surface.get('id'), max_len=64).lower()
        if not surface_id:
            errors.append('memory_plan contains a surface without surface_id')
            continue
        if surface_id in surface_ids:
            errors.append(f"duplicate memory surface_id: {surface_id}")
            continue
        surface_ids.add(surface_id)
        load_policy = _clean_text(surface.get('load_policy') or surface.get('loadPolicy') or surface.get('load') or 'on_demand', max_len=64).lower()
        if load_policy and load_policy not in {'always', 'on_demand', 'lazy', 'never'}:
            errors.append(f"memory surface {surface_id} uses unknown load_policy: {load_policy}")
        write_policy = _normalize_memory_write_policy(surface.get('write_policy') or surface.get('writePolicy') or 'shared')
        if write_policy not in {'shared', 'append_only', 'final', 'index', 'read_only', 'none'}:
            errors.append(f"memory surface {surface_id} uses unknown write_policy: {write_policy}")
        semantic_slots = {_clean_text(v, max_len=64).lower() for v in _as_list(surface.get('semantic_slots') or surface.get('semanticSlots')) if _clean_text(v, max_len=64)}
        if not semantic_slots:
            errors.append(f"memory surface {surface_id} must include at least one semantic_slot")
        for raw_role in _as_list(surface.get('target_roles') or surface.get('targetRoles')):
            target_role = _clean_text(raw_role, max_len=64).lower()
            if target_role and role_ids and target_role not in role_ids:
                errors.append(f"memory surface {surface_id} targets an unknown role: {target_role}")
    for ref in _as_list(memory_plan.get('default_load_surface_ids') or memory_plan.get('defaultLoadSurfaceIds')):
        surface_id = _clean_text(ref, max_len=64).lower()
        if surface_id and surface_ids and surface_id not in surface_ids:
            errors.append(f"default_load_surface_ids references unknown surface: {surface_id}")
    for ref in _as_list(memory_plan.get('writable_surface_ids') or memory_plan.get('writableSurfaceIds')):
        surface_id = _clean_text(ref, max_len=64).lower()
        if surface_id and surface_ids and surface_id not in surface_ids:
            errors.append(f"writable_surface_ids references unknown surface: {surface_id}")
    for raw_tool in _as_list(_as_dict(normalized.get('requirements')).get('tools')):
        tool = _as_dict(raw_tool)
        tool_id = _clean_text(tool.get('tool_id') or tool.get('toolId'), max_len=64).lower()
        if not tool_id:
            errors.append('tool requirement is missing tool_id')
    return {
        "ok": not errors,
        "errors": errors,
        "apply_state": clean_state,
        "manifest": normalized,
    }




def _summarize_publish_contract_issues(structure: Any) -> dict[str, Any]:
    from app.services.team_manifest_diff import _summarize_publish_contract_issues as _impl

    return _impl(structure)


def _build_guardrails(current_manifest: Any, candidate_manifest: Any, apply_state: str = "active") -> dict[str, Any]:
    from app.services.team_manifest_diff import _build_guardrails as _impl

    return _impl(current_manifest, candidate_manifest, apply_state)


def diff_team_manifest_payload(current_manifest: Any, candidate_manifest: Any, apply_state: str = "active") -> dict[str, Any]:
    from app.services.team_manifest_diff import diff_team_manifest_payload as _impl

    return _impl(current_manifest, candidate_manifest, apply_state)


def export_thread_team_manifest(session: Session, thread: Thread) -> dict[str, Any]:
    payload = get_team_config_payload(session, thread_id=thread.id)
    return build_team_manifest_payload(thread, payload)


def install_thread_team_manifest(session: Session, thread: Thread, manifest: Any, apply_state: str = "active") -> dict[str, Any]:
    validation = validate_team_manifest_payload(manifest, apply_state=apply_state)
    if not validation.get("ok"):
        raise ValueError("; ".join(validation.get("errors") or ["invalid team manifest"]))

    normalized = _as_dict(validation.get("manifest"))
    team_config = _as_dict(normalized.get("team_config"))
    clean_state = validation.get("apply_state") or "active"
    team = _normalize_team_payload(_derive_team_from_structure_v2(normalized.get("structure_v2")) or normalized.get("team"))
    team["requirements"] = _normalize_requirements(normalized.get("requirements"), team)
    team["structure_v2"] = _normalize_structure_v2(normalized.get("structure_v2"), team_payload=team, apply_state=clean_state, install_proposal_state=normalized.get("install_proposal_state"), credential_binding_state=normalized.get("credential_binding_state"))
    status = "active" if clean_state == "active" else "suggested"

    current_payload = get_team_config_payload(session, thread_id=thread.id)
    current_manifest = build_team_manifest_payload(thread, current_payload)
    install_guardrails = _build_guardrails(current_manifest, normalized, clean_state)
    next_payload = {
        "status": status,
        "composition_mode": _clean_text(team_config.get("composition_mode") or normalized.get("composition_mode") or current_payload.get("composition_mode") or "structured", max_len=32) or "structured",
        "proposal_mode": _clean_text(team_config.get("proposal_mode") or normalized.get("proposal_mode") or current_payload.get("proposal_mode") or ("apply" if clean_state == "active" else "refine"), max_len=32) or ("apply" if clean_state == "active" else "refine"),
        "active_team": team if clean_state == "active" else _normalize_team_payload(current_payload.get("active_team")),
        "pending_team": team if clean_state == "pending" else _normalize_team_payload(current_payload.get("pending_team")),
        "install_proposal": _normalize_install_proposal(normalized.get('install_proposal') or current_payload.get('install_proposal')),
        "install_proposal_state": _normalize_install_proposal_state(normalized.get('install_proposal_state') or current_payload.get('install_proposal_state')),
        "credential_binding_state": _normalize_credential_binding_state(normalized.get('credential_binding_state') or current_payload.get('credential_binding_state')),
        "pattern_conflict": _normalize_pattern_conflict_state(normalized.get('pattern_conflict') or current_payload.get('pattern_conflict')),
        "temporary_execution_override": _normalize_temporary_execution_override(normalized.get('temporary_execution_override') or current_payload.get('temporary_execution_override')),
        "pattern_recovery": _normalize_pattern_recovery_state(normalized.get('pattern_recovery') or current_payload.get('pattern_recovery')),
        "structure_v2": _normalize_structure_v2(normalized.get('structure_v2') or current_payload.get('structure_v2') or team.get('structure_v2'), team_payload=team, apply_state=clean_state, install_proposal_state=normalized.get('install_proposal_state'), credential_binding_state=normalized.get('credential_binding_state')),
    }
    saved = save_team_config_payload(session, thread_id=thread.id, payload=next_payload)
    out = _normalize_manifest(saved, fallback_thread=thread, fallback_apply_state=clean_state)
    out['install_guardrails'] = install_guardrails
    return out

def _normalize_memory_write_policy(value: Any) -> str:
    clean = _clean_text(value, max_len=64).lower()
    mapping = {'owner_only': 'shared', 'shared_append': 'append_only', 'final_owner': 'final', 'read_only': 'read_only', 'none': 'none', 'shared': 'shared', 'append_only': 'append_only', 'final': 'final', 'index': 'index'}
    return mapping.get(clean, clean or 'shared')


def _normalize_memory_plan(raw: Any, *, knowledge_surface: Any = None, memory_policy: Any = None) -> dict[str, Any]:
    row = _as_dict(raw)
    clean_surface = _as_dict(knowledge_surface)
    clean_policy = _as_dict(memory_policy)
    surfaces = []
    seen = set()
    for item in _as_list(row.get('surfaces')):
        surface = _as_dict(item)
        surface_id = _clean_text(surface.get('surface_id') or surface.get('id'), max_len=64).lower()
        if not surface_id or surface_id in seen:
            continue
        seen.add(surface_id)
        surfaces.append({
            'surface_id': surface_id,
            'title': _clean_text(surface.get('title') or surface.get('label') or surface_id.replace('_', ' ').title(), max_len=160) or surface_id.replace('_', ' ').title(),
            'purpose': _clean_text(surface.get('purpose') or surface.get('description') or 'Team memory surface.', max_len=280) or 'Team memory surface.',
            'kind': _clean_text(surface.get('kind') or 'shared_doc', max_len=64).lower() or 'shared_doc',
            'file_name': _clean_text(surface.get('file_name') or surface.get('fileName') or f'{surface_id}.md', max_len=160) or f'{surface_id}.md',
            'load_policy': _clean_text(surface.get('load_policy') or surface.get('loadPolicy') or surface.get('load') or 'on_demand', max_len=64).lower() or 'on_demand',
            'write_policy': _normalize_memory_write_policy(surface.get('write_policy') or surface.get('writePolicy') or 'shared'),
            'create_mode': _clean_text(surface.get('create_mode') or surface.get('createMode') or 'lazy', max_len=64).lower() or 'lazy',
            'semantic_slots': [_clean_text(v, max_len=64).lower() for v in _as_list(surface.get('semantic_slots') or surface.get('semanticSlots') or [surface_id]) if _clean_text(v, max_len=64)][:8],
            'target_roles': [_clean_text(v, max_len=64).lower() for v in _as_list(surface.get('target_roles') or surface.get('targetRoles')) if _clean_text(v, max_len=64)][:8],
        })
    if not surfaces:
        docs = _as_list(clean_surface.get('docs'))
        for item in docs[:16]:
            doc = _as_dict(item)
            doc_id = _clean_text(doc.get('doc_id') or doc.get('id'), max_len=64).lower()
            if not doc_id or doc_id in seen:
                continue
            seen.add(doc_id)
            surfaces.append({
                'surface_id': doc_id,
                'title': _clean_text(doc.get('title') or doc_id.replace('_', ' ').title(), max_len=160) or doc_id.replace('_', ' ').title(),
                'purpose': _clean_text(doc.get('purpose') or 'Team memory surface.', max_len=280) or 'Team memory surface.',
                'kind': 'shared_doc',
                'file_name': _clean_text(doc.get('file_name') or doc.get('fileName') or f'{doc_id}.md', max_len=160) or f'{doc_id}.md',
                'load_policy': 'always' if doc_id in {'mission_brief', 'working_memory', 'final_answer', 'artifact_index'} else 'on_demand',
                'write_policy': 'append_only' if doc_id in {'working_memory'} else ('index' if doc_id == 'artifact_index' else ('final' if doc_id == 'final_answer' else 'shared')),
                'create_mode': 'lazy',
                'semantic_slots': [doc_id],
                'target_roles': [],
            })
    default_load_surface_ids = [_clean_text(v, max_len=64).lower() for v in _as_list(row.get('default_load_surface_ids') or row.get('defaultLoadSurfaceIds')) if _clean_text(v, max_len=64)][:12]
    if not default_load_surface_ids:
        default_load_surface_ids = [surface['surface_id'] for surface in surfaces if surface.get('load_policy') == 'always']
    writable_surface_ids = [_clean_text(v, max_len=64).lower() for v in _as_list(row.get('writable_surface_ids') or row.get('writableSurfaceIds')) if _clean_text(v, max_len=64)][:12]
    if not writable_surface_ids:
        writable_surface_ids = [surface['surface_id'] for surface in surfaces if surface.get('write_policy') not in {'read_only', 'none'}]
    return {
        'plan_id': _clean_text(row.get('plan_id') or row.get('planId') or clean_surface.get('profile_id') or 'default_memory_plan', max_len=128) or 'default_memory_plan',
        'display_name': _clean_text(row.get('display_name') or row.get('displayName') or clean_surface.get('display_name') or 'Default Memory Plan', max_len=160) or 'Default Memory Plan',
        'surfaces': surfaces[:16],
        'default_load_surface_ids': default_load_surface_ids[:12],
        'writable_surface_ids': writable_surface_ids[:12],
        'migration_strategy': _clean_text(row.get('migration_strategy') or row.get('migrationStrategy') or clean_policy.get('migration_strategy') or 'semantic_slot_preserving', max_len=64).lower() or 'semantic_slot_preserving',
    }

