from __future__ import annotations

import json
from typing import Any

_ALLOWED_GRANTS = {
    "shared_summary",
    "global_memory",
    "conversation_tail",
    "upstream_results",
    "upstream_summaries",
    "user_pinned_nodes",
    "explicit_uploaded_files",
}


from sqlmodel import Session, select

from app.models import Conversation, ConversationTeamConfig, ConversationTeamConfigRevision


_TEAM_CONFIG_STATE_KEYS = (
    'install_proposal',
    'install_proposal_state',
    'credential_binding_state',
    'pattern_conflict',
    'temporary_execution_override',
    'pattern_recovery',
    'structure_v2',
)


def _jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def _jdump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _normalize_composition_mode(raw: Any, *, fallback: str = 'structured') -> str:
    value = str(raw or fallback).strip().lower() or fallback
    return value if value in {'structured', 'freeform'} else (fallback if fallback in {'structured', 'freeform'} else 'structured')


def _normalize_proposal_mode(raw: Any, *, fallback: str = 'suggest') -> str:
    value = str(raw or fallback).strip().lower() or fallback
    return value if value in {'suggest', 'create', 'refine', 'validate', 'apply'} else (fallback if fallback in {'suggest', 'create', 'refine', 'validate', 'apply'} else 'suggest')


def _normalize_team_config_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    status = str(raw.get('status') or 'none').strip().lower() or 'none'
    if status not in {'none', 'suggested', 'active', 'locked', 'editable'}:
        status = 'active' if raw.get('active_team') else ('suggested' if raw.get('pending_team') else 'none')
    active_team = raw.get('active_team') or raw.get('team_config') or {}
    pending_team = raw.get('pending_team') or {}
    if not isinstance(active_team, dict):
        active_team = {}
    if not isinstance(pending_team, dict):
        pending_team = {}
    composition_mode = _normalize_composition_mode(raw.get('composition_mode') or active_team.get('composition_mode') or pending_team.get('composition_mode') or 'structured')
    proposal_mode = _normalize_proposal_mode(raw.get('proposal_mode') or active_team.get('proposal_mode') or pending_team.get('proposal_mode') or ('create' if composition_mode == 'freeform' else 'suggest'))
    if status == 'none':
        active_team = {}
        pending_team = {}
    state = {key: raw.get(key) for key in _TEAM_CONFIG_STATE_KEYS if raw.get(key) is not None}
    return {'status': status, 'composition_mode': composition_mode, 'proposal_mode': proposal_mode, 'active_team': active_team, 'pending_team': pending_team, 'state': state}




def _clean_text(value: Any, *, lower: bool = False, max_len: int = 256) -> str:
    text = str(value or "").strip()
    if max_len > 0:
        text = text[:max_len]
    return text.lower() if lower else text


def _clean_list(value: Any, *, lower: bool = False, limit: int = 24, item_max_len: int = 128) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = []
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = _clean_text(item, lower=lower, max_len=item_max_len)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def _clean_int(value: Any, *, fallback: int | None = None, min_value: int = 0, max_value: int = 100000) -> int | None:
    if value is None or value == "":
        return fallback
    try:
        parsed = int(value)
    except Exception:
        return fallback
    return max(min_value, min(max_value, parsed))


def _find_agent_index(agents: list[Any], *, agent_id: str) -> int | None:
    clean_agent_id = _clean_text(agent_id, lower=True, max_len=128)
    if not clean_agent_id:
        return None
    for index, agent in enumerate(agents):
        if not isinstance(agent, dict):
            continue
        candidates = (
            agent.get("agent_id"),
            agent.get("agentId"),
            agent.get("id"),
            agent.get("name"),
        )
        for candidate in candidates:
            if _clean_text(candidate, lower=True, max_len=128) == clean_agent_id:
                return index
    return None


def patch_team_config_agent_context_policy(
    session: Session,
    *,
    thread_id: str,
    team_state: str,
    agent_id: str,
    visibility_mode: str | None = None,
    grants: list[str] | None = None,
    context_types: list[str] | None = None,
    publish_targets: list[str] | None = None,
    query_template: str | None = None,
    soft_tokens: int | None = None,
    hard_tokens: int | None = None,
) -> dict[str, Any]:
    payload = get_team_config_payload(session, thread_id=thread_id)
    clean_state = _clean_text(team_state, lower=True, max_len=16)
    if clean_state not in {"active", "pending"}:
        raise ValueError("team_state must be active or pending")
    team = payload.get(f"{clean_state}_team")
    if not isinstance(team, dict) or not team:
        raise ValueError(f"{clean_state}_team is not configured")
    agents = list(team.get("agents") or [])
    target_index = _find_agent_index(agents, agent_id=agent_id)
    if target_index is None:
        raise ValueError("agent not found in team_config")

    raw_agent = agents[target_index]
    agent = dict(raw_agent) if isinstance(raw_agent, dict) else {}
    context_policy = agent.get("context_policy") if isinstance(agent.get("context_policy"), dict) else (agent.get("contextPolicy") if isinstance(agent.get("contextPolicy"), dict) else {})
    context_policy = dict(context_policy)
    reads = context_policy.get("reads") if isinstance(context_policy.get("reads"), dict) else {}
    writes = context_policy.get("writes") if isinstance(context_policy.get("writes"), dict) else {}
    budget = context_policy.get("default_budget") if isinstance(context_policy.get("default_budget"), dict) else (context_policy.get("defaultBudget") if isinstance(context_policy.get("defaultBudget"), dict) else {})
    reads = dict(reads)
    writes = dict(writes)
    budget = dict(budget)

    if visibility_mode is not None:
        clean_visibility = _clean_text(visibility_mode, lower=True, max_len=32)
        context_policy["base_mode"] = clean_visibility or "scoped_context"
    if grants is not None:
        reads["grants"] = [grant for grant in _clean_list(grants, lower=True, limit=12, item_max_len=64) if grant in _ALLOWED_GRANTS]
    if context_types is not None:
        reads["context_types"] = _clean_list(context_types, lower=True, limit=16, item_max_len=64)
    if publish_targets is not None:
        writes["publish_targets"] = _clean_list(publish_targets, lower=True, limit=16, item_max_len=64)
    if query_template is not None:
        clean_query = _clean_text(query_template, max_len=512)
        if clean_query:
            reads["query_template"] = clean_query
        else:
            reads.pop("query_template", None)
    clean_soft = _clean_int(soft_tokens, fallback=None, min_value=200, max_value=6000)
    clean_hard = _clean_int(hard_tokens, fallback=None, min_value=200, max_value=8000)
    if clean_soft is not None:
        budget["soft_tokens"] = clean_soft
    elif soft_tokens is not None:
        budget.pop("soft_tokens", None)
    if clean_hard is not None:
        budget["hard_tokens"] = max(clean_hard, int(budget.get("soft_tokens") or clean_soft or 200))
    elif hard_tokens is not None:
        budget.pop("hard_tokens", None)
    if budget:
        context_policy["default_budget"] = budget
    else:
        context_policy.pop("default_budget", None)

    context_policy["reads"] = reads
    context_policy["writes"] = writes
    agent["context_policy"] = context_policy
    agents[target_index] = agent
    team["agents"] = agents
    payload[f"{clean_state}_team"] = team
    return save_team_config_payload(session, thread_id=thread_id, payload=payload)

def _ensure_conversation(session: Session, *, thread_id: str) -> Conversation | None:
    return session.exec(select(Conversation).where(Conversation.thread_id == thread_id)).first()


def get_team_config_payload(session: Session, *, thread_id: str) -> dict[str, Any]:
    conversation = _ensure_conversation(session, thread_id=thread_id)
    if not conversation:
        return {
            "thread_id": thread_id,
            "conversation_id": "",
            "status": "none",
            "composition_mode": "structured",
            "proposal_mode": "suggest",
            "active_team": {},
            "pending_team": {},
            **{key: None for key in _TEAM_CONFIG_STATE_KEYS},
            "updated_at": None,
        }
    row = session.exec(
        select(ConversationTeamConfig).where(ConversationTeamConfig.conversation_id == conversation.id)
    ).first()
    if not row:
        return {
            "thread_id": thread_id,
            "conversation_id": conversation.id,
            "status": "none",
            "composition_mode": "structured",
            "proposal_mode": "suggest",
            "active_team": {},
            "pending_team": {},
            **{key: None for key in _TEAM_CONFIG_STATE_KEYS},
            "updated_at": None,
        }
    state = _jload(getattr(row, 'state_json', '{}'), {})
    if not isinstance(state, dict):
        state = {}
    return {
        "thread_id": row.thread_id,
        "conversation_id": row.conversation_id,
        "status": row.status or "none",
        "composition_mode": _normalize_composition_mode((_jload(row.active_team_json, {}) or {}).get('composition_mode') or (_jload(row.pending_team_json, {}) or {}).get('composition_mode') or 'structured'),
        "proposal_mode": _normalize_proposal_mode((_jload(row.active_team_json, {}) or {}).get('proposal_mode') or (_jload(row.pending_team_json, {}) or {}).get('proposal_mode') or 'suggest'),
        "active_team": _jload(row.active_team_json, {}),
        "pending_team": _jload(row.pending_team_json, {}),
        **{key: state.get(key) for key in _TEAM_CONFIG_STATE_KEYS},
        "updated_at": row.updated_at,
    }


def save_team_config_payload(session: Session, *, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    conversation = _ensure_conversation(session, thread_id=thread_id)
    if not conversation:
        raise ValueError("conversation not found for thread")
    row = session.exec(
        select(ConversationTeamConfig).where(ConversationTeamConfig.conversation_id == conversation.id)
    ).first()
    if not row:
        row = ConversationTeamConfig(conversation_id=conversation.id, thread_id=thread_id)
    normalized = _normalize_team_config_payload(payload)
    row.status = normalized['status']
    row.active_team_json = _jdump(normalized['active_team'])
    row.pending_team_json = _jdump(normalized['pending_team'])
    row.state_json = _jdump(normalized.get('state') or {})
    session.add(row)
    session.flush()
    session.add(ConversationTeamConfigRevision(
        conversation_id=conversation.id,
        thread_id=thread_id,
        revision_kind="update",
        payload_json=_jdump({
            "status": row.status,
            "composition_mode": normalized['composition_mode'],
            "proposal_mode": normalized['proposal_mode'],
            "active_team": _jload(row.active_team_json, {}),
            "pending_team": _jload(row.pending_team_json, {}),
            **(_jload(getattr(row, 'state_json', '{}'), {}) if isinstance(_jload(getattr(row, 'state_json', '{}'), {}), dict) else {}),
        }),
    ))
    session.commit()
    session.refresh(row)
    return {
        "thread_id": row.thread_id,
        "conversation_id": row.conversation_id,
        "status": row.status,
        "composition_mode": normalized['composition_mode'],
        "proposal_mode": normalized['proposal_mode'],
        "active_team": _jload(row.active_team_json, {}),
        "pending_team": _jload(row.pending_team_json, {}),
        **{key: (normalized.get('state') or {}).get(key) for key in _TEAM_CONFIG_STATE_KEYS},
        "updated_at": row.updated_at,
    }
