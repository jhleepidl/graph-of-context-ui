from __future__ import annotations

import re
from typing import Any

from sqlmodel import Session, select

from app.models import Thread
from app.services.conversation_team_config import get_team_config_payload, save_team_config_payload


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
        return {
            "tool_id": tool_id,
            "required_by": _clean_text(row.get("required_by") or row.get("requiredBy") or row.get("agent_name") or row.get("agentName") or row.get("agent") or row.get("label") or "agent", max_len=128) or "agent",
            "severity": _clean_text(row.get("severity") or "blocking", max_len=32).lower() or "blocking",
            "reason": _clean_text(row.get("reason") or row.get("detail") or row.get("note"), max_len=256),
            "source_kind": _clean_text(row.get("source_kind") or row.get("sourceKind") or row.get("kind") or "missing_tool", max_len=64).lower() or "missing_tool",
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
    tools = _as_list(requirements.get("tools"))
    credentials = _as_list(requirements.get("credentials"))
    hints: list[str] = []
    if any('workspace_fs' in _clean_text(row.get('tool_id')).lower() or 'write_file' in _clean_text(row.get('tool_id')).lower() for row in tools if isinstance(row, dict)):
        hints.append('workspace_fs 또는 file writer tool을 연결하면 파일·노트북 산출물을 만들 수 있습니다.')
    if any(any(token in _clean_text(row.get('tool_id')).lower() for token in ['web', 'browser', 'search']) for row in tools if isinstance(row, dict)):
        hints.append('검색형 작업이면 web/browser/search tool을 가진 agent 또는 preset을 사용하세요.')
    if credentials:
        keys = ', '.join(_clean_text(row.get('credential_key') or 'API_KEY', max_len=64) for row in credentials[:3] if isinstance(row, dict)) or 'API_KEY'
        hints.append(f'필요한 credential({keys})을 안전한 비밀 저장소나 환경 변수로 제공하세요.')
    if tools or credentials or _as_list(requirements.get('skills')):
        hints.append('manifest를 ddalggak Telegram의 /team install 또는 /team push 흐름과 함께 사용할 수 있습니다.')
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
    tool_entries: list[dict[str, Any]] = []
    credential_entries: list[dict[str, Any]] = []
    skill_entries: list[dict[str, Any]] = []
    warnings: list[str] = []

    for row in _as_list(raw.get("tools")):
        normalized = _normalize_requirement_entry(row, kind="tool")
        if normalized:
            tool_entries.append(normalized)
    for row in _as_list(raw.get("credentials")):
        normalized = _normalize_requirement_entry(row, kind="credential")
        if normalized:
            credential_entries.append(normalized)
    for row in _as_list(raw.get("skills")):
        normalized = _normalize_requirement_entry(row, kind="skill")
        if normalized:
            skill_entries.append(normalized)
    for item in _as_list(raw.get("warnings")):
        text = _clean_text(item, max_len=256)
        if text:
            warnings.append(text)

    for raw_gap in _as_list(team.get("capability_gaps") or team.get("capabilityGaps")):
        gap = _as_dict(raw_gap)
        kind = _clean_text(gap.get("kind"), max_len=64).lower()
        detail = _clean_text(gap.get("detail") or gap.get("reason"), max_len=256)
        if kind == "missing_tool":
            normalized = _normalize_requirement_entry({
                **gap,
                "required_by": gap.get("agent_name") or gap.get("agentName") or gap.get("agent") or gap.get("label"),
                "reason": detail,
                "source_kind": kind,
            }, kind="tool")
            if normalized:
                tool_entries.append(normalized)
        elif kind == "missing_credential":
            normalized = _normalize_requirement_entry({
                **gap,
                "required_by": gap.get("agent_name") or gap.get("agentName") or gap.get("agent") or gap.get("label"),
                "reason": detail,
                "source_kind": kind,
            }, kind="credential")
            if normalized:
                credential_entries.append(normalized)
        elif kind == "missing_skill":
            normalized = _normalize_requirement_entry({
                **gap,
                "required_by": gap.get("agent_name") or gap.get("agentName") or gap.get("agent") or gap.get("label"),
                "reason": detail,
                "source_kind": kind,
            }, kind="skill")
            if normalized:
                skill_entries.append(normalized)
        if detail:
            warnings.append(detail)

    normalized_tools = _dedupe_entries(tool_entries, key_fields=("tool_id", "required_by", "source_kind"))
    normalized_credentials = _dedupe_entries(credential_entries, key_fields=("credential_key", "required_by", "source_kind"))
    normalized_skills = _dedupe_entries(skill_entries, key_fields=("skill_id", "required_by", "source_kind"))
    normalized_warnings = _dedupe_entries([{"value": item} for item in warnings if item], key_fields=("value",), limit=12)
    install_hints = _build_install_hints({
        "tools": normalized_tools,
        "credentials": normalized_credentials,
        "skills": normalized_skills,
    }, has_thread_target=bool(team.get('thread_id') or team.get('threadId')))

    return {
        "tools": normalized_tools,
        "credentials": normalized_credentials,
        "skills": normalized_skills,
        "warnings": [row["value"] for row in normalized_warnings],
        "install_hints": install_hints,
        "summary": {
            "tool_count": len(normalized_tools),
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
        return {
            'kind': 'tool_install_proposal',
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
    tool_install_proposals = _dedupe_entries(
        [normalized for item in _as_list(row.get('tool_install_proposals') or row.get('toolInstallProposals')) if (normalized := _normalize_install_action_entry(item, kind='tool_install_proposal'))],
        key_fields=('tool_id', 'required_by', 'strategy'),
    )
    credential_requests = _dedupe_entries(
        [normalized for item in _as_list(row.get('credential_requests') or row.get('credentialRequests')) if (normalized := _normalize_install_action_entry(item, kind='credential_request'))],
        key_fields=('credential_key', 'required_by', 'delivery_method'),
    )
    generated_skill_proposals = _dedupe_entries(
        [normalized for item in _as_list(row.get('generated_skill_proposals') or row.get('generatedSkillProposals')) if (normalized := _normalize_install_action_entry(item, kind='generated_skill_proposal'))],
        key_fields=('skill_id', 'required_by', 'strategy'),
    )
    return {
        'tool_install_proposals': tool_install_proposals,
        'credential_requests': credential_requests,
        'generated_skill_proposals': generated_skill_proposals,
        'summary': {
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
    gap_count = sum(len(_as_list(normalized_requirements.get(key))) for key in ('tools', 'credentials', 'skills'))
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
    role = _clean_text(row.get('role') or row.get('role_id') or row.get('roleId') or 'specialist', max_len=64).lower() or 'specialist'
    kind = _clean_text(row.get('kind') or ('gate' if role == 'approval' else 'agent'), max_len=32).lower() or 'agent'
    return {
        'participant_id': participant_id,
        'kind': kind,
        'name': _clean_text(row.get('name') or row.get('label') or participant_id, max_len=128) or participant_id,
        'role': role,
        'purpose': _clean_text(row.get('purpose') or row.get('description'), max_len=256),
        'model': _clean_text(row.get('model'), max_len=128),
        'capabilities': [_clean_text(v, max_len=128) for v in _as_list(row.get('capabilities') or row.get('skills')) if _clean_text(v, max_len=128)][:8],
        'attached_skill_ids': [_clean_text(v, max_len=128) for v in _as_list(row.get('attached_skill_ids') or row.get('attachedSkillIds')) if _clean_text(v, max_len=128)][:8],
        'recommended_tool_ids': [_clean_text(v, max_len=128) for v in _as_list(row.get('recommended_tool_ids') or row.get('recommendedToolIds')) if _clean_text(v, max_len=128)][:8],
        'generated_skill_briefs': _as_list(row.get('generated_skill_briefs') or row.get('generatedSkillBriefs'))[:8],
        'context_policy': _as_dict(row.get('context_policy') or row.get('contextPolicy')),
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
            'model': _as_dict(item).get('model'),
            'capabilities': _as_dict(item).get('capabilities') or _as_dict(item).get('skills'),
            'attached_skill_ids': _as_dict(item).get('attached_skill_ids') or _as_dict(item).get('attachedSkillIds'),
            'recommended_tool_ids': _as_dict(item).get('recommended_tool_ids') or _as_dict(item).get('recommendedToolIds'),
            'generated_skill_briefs': _as_dict(item).get('generated_skill_briefs') or _as_dict(item).get('generatedSkillBriefs'),
            'context_policy': _as_dict(item).get('context_policy') or _as_dict(item).get('contextPolicy'),
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
            'model': item.get('model') or '',
            'capabilities': _as_list(item.get('capabilities'))[:8],
            'skills': _as_list(item.get('capabilities'))[:8],
            'attached_skill_ids': _as_list(item.get('attached_skill_ids'))[:8],
            'recommended_tool_ids': _as_list(item.get('recommended_tool_ids'))[:8],
            'generated_skill_briefs': _as_list(item.get('generated_skill_briefs'))[:8],
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
        "stable_memory_slot_count": len(_as_list(_as_dict(structure_v2.get('memory_policy')).get('stable_semantic_slots'))),
        "continuous_improvement_enabled": _as_dict(_as_dict(structure_v2.get('control_policy')).get('runtime_execution')).get('continuous_improvement', {}).get('enabled') is True,
        "codex_sandbox_mode": _clean_text(_as_dict(_as_dict(_as_dict(structure_v2.get('control_policy')).get('runtime_execution')).get('providers')).get('codex').get('sandbox_mode'), max_len=64) or None,
        "codex_mcp_count": len(_as_dict(_as_dict(_as_dict(_as_dict(structure_v2.get('control_policy')).get('runtime_execution')).get('providers')).get('codex').get('mcp_servers'))),
        "gemini_mcp_count": len(_as_dict(_as_dict(_as_dict(_as_dict(structure_v2.get('control_policy')).get('runtime_execution')).get('providers')).get('gemini').get('mcp_servers'))),
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
    final_participant_id = _clean_text(topology.get('final_participant_id') or topology.get('finalParticipantId'), max_len=128)
    if final_participant_id and participant_ids and final_participant_id not in participant_ids:
        errors.append(f"final_participant_id references an unknown participant: {final_participant_id}")
    for raw_edge in _as_list(topology.get('edges')):
        edge = _as_dict(raw_edge)
        src = _clean_text(edge.get('from') or edge.get('source') or edge.get('from_node_id'), max_len=128)
        dst = _clean_text(edge.get('to') or edge.get('target') or edge.get('to_node_id'), max_len=128)
        if src and node_ids and src not in node_ids:
            errors.append(f"topology edge references unknown source node: {src}")
        if dst and node_ids and dst not in node_ids:
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
        for raw_role in _as_list(surface.get('target_roles') or surface.get('targetRoles')):
            target_role = _clean_text(raw_role, max_len=64).lower()
            if target_role and role_ids and target_role not in role_ids:
                errors.append(f"memory surface {surface_id} targets an unknown role: {target_role}")
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
    return _normalize_manifest(saved, fallback_thread=thread, fallback_apply_state=clean_state)

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
            'kind': _clean_text(surface.get('kind') or 'shared_doc', max_len=64).lower() or 'shared_doc',
            'file_name': _clean_text(surface.get('file_name') or surface.get('fileName') or f'{surface_id}.md', max_len=160) or f'{surface_id}.md',
            'load': _clean_text(surface.get('load') or 'on_demand', max_len=64).lower() or 'on_demand',
            'write_policy': _normalize_memory_write_policy(surface.get('write_policy') or surface.get('writePolicy') or 'shared'),
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
                'kind': 'shared_doc',
                'file_name': _clean_text(doc.get('file_name') or doc.get('fileName') or f'{doc_id}.md', max_len=160) or f'{doc_id}.md',
                'load': 'always' if doc_id in {'mission_brief', 'working_memory', 'final_answer', 'artifact_index'} else 'on_demand',
                'write_policy': 'append_only' if doc_id in {'working_memory'} else ('index' if doc_id == 'artifact_index' else ('final' if doc_id == 'final_answer' else 'shared')),
                'target_roles': [],
            })
    default_load_surface_ids = [_clean_text(v, max_len=64).lower() for v in _as_list(row.get('default_load_surface_ids') or row.get('defaultLoadSurfaceIds')) if _clean_text(v, max_len=64)][:12]
    if not default_load_surface_ids:
        default_load_surface_ids = [surface['surface_id'] for surface in surfaces if surface.get('load') == 'always']
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

