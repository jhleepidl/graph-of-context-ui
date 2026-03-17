from __future__ import annotations

from typing import Any

_MAX_SCOPE_SPECS = 64
_MAX_CONTEXT_TYPES = 16
_MAX_CLOSURE_EDGES = 24
_ALLOWED_SELECTION_STRATEGIES = {
    'query_plus_closure',
    'workspace_plus_closure',
    'upstream_results_only',
    'upstream_summary_plus_evidence',
    'control_plane_trace',
    'shared_context_fallback',
}


def _clean_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        clean = value.strip().lower()
        if clean in {"1", "true", "yes", "y", "on"}:
            return True
        if clean in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _clean_text(value: Any, *, lower: bool = False, max_len: int = 512) -> str:
    text = str(value or '').strip()
    if max_len > 0:
        text = text[:max_len]
    return text.lower() if lower else text


def _clean_list(value: Any, *, lower: bool = False, limit: int = 32, item_max_len: int = 64) -> list[str]:
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


def _clean_int(value: Any, fallback: int, *, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = fallback
    return max(min_value, min(max_value, parsed))




def _normalize_visibility_mode(value: Any) -> str:
    clean = _clean_text(value or 'scoped', lower=True, max_len=32) or 'scoped'
    if clean == 'scoped_context':
        return 'scoped'
    if clean in {'scoped', 'shared', 'shared_memory', 'shared_only'}:
        return clean
    return 'scoped'


def _normalize_selection_strategy(value: Any) -> str:
    clean = _clean_text(value or 'query_plus_closure', lower=True, max_len=64) or 'query_plus_closure'
    return clean if clean in _ALLOWED_SELECTION_STRATEGIES else 'query_plus_closure'


def sanitize_scope_spec(raw: dict[str, Any] | None, index: int = 0) -> dict[str, Any] | None:
    item = raw if isinstance(raw, dict) else {}
    scope_id = _clean_text(item.get('scope_id') or item.get('scopeId') or f'scope_{index + 1}', max_len=128)
    if not scope_id:
        return None

    node_selection = item.get('node_selection') if isinstance(item.get('node_selection'), dict) else (item.get('nodeSelection') if isinstance(item.get('nodeSelection'), dict) else {})
    memory_grants = item.get('memory_grants') if isinstance(item.get('memory_grants'), dict) else (item.get('memoryGrants') if isinstance(item.get('memoryGrants'), dict) else {})
    budget = item.get('budget') if isinstance(item.get('budget'), dict) else {}

    soft_tokens = _clean_int(budget.get('soft_tokens') or budget.get('softTokens') or 1800, 1800, min_value=200, max_value=6000)
    hard_tokens = _clean_int(budget.get('hard_tokens') or budget.get('hardTokens') or max(soft_tokens + 600, int(soft_tokens * 1.45)), max(soft_tokens + 600, int(soft_tokens * 1.45)), min_value=max(soft_tokens, 200), max_value=8000)

    return {
        'scope_id': scope_id,
        'target_instance_id': _clean_text(item.get('target_instance_id') or item.get('targetInstanceId'), max_len=128) or None,
        'target_slot_id': _clean_text(item.get('target_slot_id') or item.get('targetSlotId'), max_len=128) or None,
        'role_id': _clean_text(item.get('role_id') or item.get('roleId'), lower=True, max_len=64) or None,
        'visibility_mode': _normalize_visibility_mode(item.get('visibility_mode') or item.get('visibilityMode') or 'scoped'),
        'context_types': _clean_list(item.get('context_types') or item.get('contextTypes'), lower=True, limit=_MAX_CONTEXT_TYPES, item_max_len=64),
        'node_selection': {
            'strategy': _normalize_selection_strategy(node_selection.get('strategy') or node_selection.get('mode') or 'query_plus_closure'),
            'query': _clean_text(node_selection.get('query'), max_len=512) or None,
            'closure_edge_types': _clean_list(node_selection.get('closure_edge_types') or node_selection.get('closureEdgeTypes'), limit=_MAX_CLOSURE_EDGES, item_max_len=64),
            'max_nodes': _clean_int(node_selection.get('max_nodes') or node_selection.get('maxNodes') or 80, 80, min_value=1, max_value=128),
        },
        'memory_grants': {
            'shared_summary': _clean_bool(memory_grants.get('shared_summary'), default=False),
            'global_memory': _clean_bool(memory_grants.get('global_memory'), default=False),
            'conversation_tail': _clean_bool(memory_grants.get('conversation_tail'), default=False),
            'upstream_results': _clean_bool(memory_grants.get('upstream_results'), default=False),
            'upstream_summaries': _clean_bool(memory_grants.get('upstream_summaries') if memory_grants.get('upstream_summaries') is not None else memory_grants.get('upstream_summary'), default=False),
            'user_pinned_nodes': _clean_bool(memory_grants.get('user_pinned_nodes'), default=False),
            'explicit_uploaded_files': _clean_bool(memory_grants.get('explicit_uploaded_files'), default=False),
        },
        'budget': {
            'soft_tokens': soft_tokens,
            'hard_tokens': hard_tokens,
        },
        'selection_reason': _clean_text(item.get('selection_reason') or item.get('selectionReason'), max_len=512) or None,
        'visibility_rationale': _clean_text(item.get('visibility_rationale') or item.get('visibilityRationale'), max_len=512) or None,
    }


def list_scope_specs(runtime_snapshot: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    snapshot = runtime_snapshot or {}
    raw_specs = list(snapshot.get('scope_specs') or snapshot.get('scopeSpecs') or [])
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_specs[:_MAX_SCOPE_SPECS]):
        clean = sanitize_scope_spec(item, index=index)
        if not clean:
            continue
        scope_id = str(clean.get('scope_id') or '').strip()
        if not scope_id or scope_id in seen:
            continue
        seen.add(scope_id)
        out.append(clean)
    return out


def get_scope_spec(runtime_snapshot: dict[str, Any] | None, scope_id: str) -> dict[str, Any] | None:
    clean_scope_id = str(scope_id or '').strip()
    if not clean_scope_id:
        return None
    for item in list_scope_specs(runtime_snapshot):
        if str(item.get('scope_id') or item.get('scopeId') or '').strip() == clean_scope_id:
            return item
    return None
