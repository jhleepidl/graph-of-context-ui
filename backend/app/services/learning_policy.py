from __future__ import annotations

from typing import Any, Iterable

from app.services.runtime_snapshot import node_payload as _runtime_node_payload

RAW_HISTORY_RESOURCE_KINDS = {
    'raw_history',
    'runtime_episode',
    'history_snapshot',
}

PROMOTION_CANDIDATE_RESOURCE_KINDS = {
    'skill_candidate',
    'team_candidate',
    'eval_case',
    'failure_pattern',
    'workflow_candidate',
}


def _clean_text(value: Any) -> str:
    return str(value or '').strip()



def node_payload(node: Any) -> dict[str, Any]:
    payload = _runtime_node_payload(node)
    return payload if isinstance(payload, dict) else {}



def resource_kind(payload: dict[str, Any] | None) -> str:
    row = payload if isinstance(payload, dict) else {}
    return _clean_text(row.get('resource_kind') or row.get('resourceKind') or row.get('kind')).lower()



def is_raw_history_payload(payload: dict[str, Any] | None) -> bool:
    row = payload if isinstance(payload, dict) else {}
    kind = resource_kind(row)
    if kind in RAW_HISTORY_RESOURCE_KINDS:
        return True
    if row.get('privacy_class') == 'raw_history':
        return True
    if row.get('history_visibility') == 'board_only':
        return True
    return False



def is_learning_excluded_payload(payload: dict[str, Any] | None) -> bool:
    row = payload if isinstance(payload, dict) else {}
    if not row:
        return False
    if is_raw_history_payload(row):
        return True
    if row.get('learning_excluded') is True:
        return True
    if row.get('exclude_from_learning') is True:
        return True
    reuse_mode = _clean_text(row.get('reuse_mode') or row.get('reuseMode')).lower()
    if reuse_mode in {'view_only', 'board_only', 'never'}:
        return True
    return False



def is_learning_excluded_node(node: Any) -> bool:
    return is_learning_excluded_payload(node_payload(node))



def filter_learning_eligible_nodes(nodes: Iterable[Any]) -> list[Any]:
    return [node for node in nodes if not is_learning_excluded_node(node)]



def is_promotion_candidate_payload(payload: dict[str, Any] | None) -> bool:
    row = payload if isinstance(payload, dict) else {}
    kind = resource_kind(row)
    if kind in PROMOTION_CANDIDATE_RESOURCE_KINDS:
        return True
    promotion_state = _clean_text(row.get('promotion_status') or row.get('promotionStatus')).lower()
    if promotion_state in {'candidate', 'queued', 'review_required', 'approved'}:
        return True
    if row.get('candidate_for_promotion') is True:
        return True
    return False
