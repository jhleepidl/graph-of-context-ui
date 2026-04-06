from __future__ import annotations

import hashlib
import json
from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _clean_text(value: Any, *, max_len: int = 240) -> str:
    return str(value or '').strip()[:max_len]


def _clean_id(value: Any, *, max_len: int = 128) -> str:
    text = _clean_text(value, max_len=max_len).lower()
    return ''.join(ch if ch.isalnum() or ch in '._:-' else '_' for ch in text).strip('_')


def _clean_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _content_signature(content: Any) -> str:
    row = _as_dict(content)
    if row:
        payload = json.dumps(row, ensure_ascii=False, sort_keys=True)
    else:
        payload = _clean_text(content, max_len=4096)
    return hashlib.sha1(payload.encode('utf-8')).hexdigest()


def _extract_conflict_key(node: dict[str, Any]) -> str:
    content = _as_dict(node.get('content') or node.get('content_json'))
    provenance = _as_dict(node.get('provenance') or node.get('provenance_json'))
    for candidate in (
        content.get('conflict_key'),
        content.get('key'),
        content.get('topic'),
        content.get('subject'),
        content.get('claim_id'),
        provenance.get('conflict_key'),
        provenance.get('topic'),
        provenance.get('subject'),
        provenance.get('entity'),
    ):
        clean = _clean_id(candidate, max_len=160)
        if clean:
            return clean
    return ''


def _extract_confidence(node: dict[str, Any]) -> float:
    content = _as_dict(node.get('content') or node.get('content_json'))
    provenance = _as_dict(node.get('provenance') or node.get('provenance_json'))
    candidates = [
        content.get('confidence'),
        content.get('confidence_score'),
        provenance.get('confidence'),
        provenance.get('confidence_score'),
        provenance.get('score'),
    ]
    for candidate in candidates:
        value = _clean_float(candidate, default=-1.0)
        if value >= 0:
            if value > 1.0:
                value = min(1.0, value / 100.0)
            return value
    return 0.0


_TRUST_RANKS = {
    'untrusted': -2,
    'speculative': -1,
    'derived': 0,
    'inferred': 0,
    'asserted': 1,
    'reported': 1,
    'verified': 2,
    'source': 2,
    'authoritative': 3,
}


def _extract_trust_tier(node: dict[str, Any]) -> str:
    return _clean_id(node.get('trust_tier') or node.get('trustTier') or 'derived', max_len=64) or 'derived'


def _trust_rank(tier: Any) -> int:
    return _TRUST_RANKS.get(_clean_id(tier, max_len=64), 0)


def _extract_provenance_fingerprint(node: dict[str, Any]) -> str:
    provenance = _as_dict(node.get('provenance') or node.get('provenance_json'))
    parts: list[str] = []
    for key in ('source_id', 'document_id', 'url', 'uri', 'thread_id', 'run_id', 'entity', 'topic'):
        value = _clean_text(provenance.get(key), max_len=160)
        if value:
            parts.append(f'{key}:{value}')
    for key in ('source_ids', 'document_ids', 'ref_ids', 'urls'):
        vals = [_clean_text(v, max_len=120) for v in _as_list(provenance.get(key)) if _clean_text(v, max_len=120)]
        if vals:
            parts.append(f'{key}:{"|".join(sorted(vals))}')
    return ' ; '.join(parts[:8])


def _extract_node_preview(node: dict[str, Any]) -> str:
    content = _as_dict(node.get('content') or node.get('content_json'))
    for key in ('claim', 'value', 'text', 'summary', 'decision', 'answer', 'note'):
        value = _clean_text(content.get(key), max_len=160)
        if value:
            return value
    if content:
        return _clean_text(json.dumps(content, ensure_ascii=False, sort_keys=True), max_len=160)
    return _clean_text(node.get('text'), max_len=160)


def _surface_visibility_reason(surface: dict[str, Any], *, clean_role_id: str, include_ids: set[str], exclude_ids: set[str]) -> str:
    surface_id = surface['surface_id']
    target_roles = set(surface.get('target_roles') or [])
    if surface_id in exclude_ids:
        return 'excluded_by_request'
    if include_ids and surface_id not in include_ids:
        return 'not_in_requested_scope'
    if target_roles and clean_role_id and clean_role_id not in target_roles:
        return 'role_not_allowed'
    if target_roles and not clean_role_id:
        return 'role_not_declared'
    return 'visible'



def normalize_memory_surfaces(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _as_list(raw):
        row = _as_dict(item)
        surface_id = _clean_id(row.get('surface_id') or row.get('surfaceId') or row.get('id'))
        if not surface_id or surface_id in seen:
            continue
        seen.add(surface_id)
        out.append({
            'surface_id': surface_id,
            'title': _clean_text(row.get('title') or surface_id, max_len=160) or surface_id,
            'semantic_kind': _clean_id(row.get('semantic_kind') or row.get('semanticKind') or 'generic', max_len=64) or 'generic',
            'visibility_scope': _clean_id(row.get('visibility_scope') or row.get('visibilityScope') or 'shared', max_len=64) or 'shared',
            'write_mode': _clean_id(row.get('write_mode') or row.get('writeMode') or row.get('write_policy') or 'shared', max_len=64) or 'shared',
            'target_roles': [_clean_id(v) for v in _as_list(row.get('target_roles') or row.get('targetRoles')) if _clean_id(v)],
            'policy': _as_dict(row.get('policy')),
        })
    return out



def build_memory_projection(*, role_id: Any = None, agent_id: Any = None, surfaces: Any = None, nodes: Any = None, include_surface_ids: Any = None, exclude_surface_ids: Any = None) -> dict[str, Any]:
    clean_role_id = _clean_id(role_id)
    clean_agent_id = _clean_id(agent_id)
    include_ids = {_clean_id(v) for v in _as_list(include_surface_ids) if _clean_id(v)}
    exclude_ids = {_clean_id(v) for v in _as_list(exclude_surface_ids) if _clean_id(v)}
    surface_rows = normalize_memory_surfaces(surfaces)
    visible_surface_ids: list[str] = []
    blocked_surface_ids: list[str] = []
    visible_surfaces: list[dict[str, Any]] = []
    blocked_surfaces: list[dict[str, Any]] = []
    surface_reasons: dict[str, str] = {}
    for surface in surface_rows:
        surface_id = surface['surface_id']
        reason = _surface_visibility_reason(surface, clean_role_id=clean_role_id, include_ids=include_ids, exclude_ids=exclude_ids)
        surface_reasons[surface_id] = reason
        if reason == 'visible':
            visible_surface_ids.append(surface_id)
            visible_surfaces.append({**surface, 'reason': reason})
        else:
            blocked_surface_ids.append(surface_id)
            blocked_surfaces.append({**surface, 'reason': reason})
    visible_node_ids: list[str] = []
    blocked_node_ids: list[str] = []
    visible_nodes: list[dict[str, Any]] = []
    blocked_nodes: list[dict[str, Any]] = []
    for item in _as_list(nodes):
        row = _as_dict(item)
        node_id = _clean_text(row.get('id') or row.get('node_id'), max_len=128)
        surface_id = _clean_id(row.get('surface_id') or row.get('surfaceId'))
        if not node_id or not surface_id:
            continue
        detail = {
            'node_id': node_id,
            'surface_id': surface_id,
            'node_type': _clean_id(row.get('node_type') or row.get('nodeType') or 'note', max_len=64) or 'note',
            'status': _clean_id(row.get('status') or 'draft', max_len=64) or 'draft',
            'trust_tier': _extract_trust_tier(row),
            'confidence': _extract_confidence(row),
            'owner_agent_id': _clean_text(row.get('owner_agent_id'), max_len=128) or None,
            'owner_role_id': _clean_id(row.get('owner_role_id'), max_len=128) or None,
            'created_run_id': _clean_text(row.get('created_run_id'), max_len=128) or None,
            'content_preview': _extract_node_preview(row),
            'provenance_fingerprint': _extract_provenance_fingerprint(row) or None,
        }
        if surface_id in visible_surface_ids:
            visible_node_ids.append(node_id)
            visible_nodes.append(detail)
        else:
            detail['blocked_reason'] = surface_reasons.get(surface_id) or 'surface_not_visible'
            blocked_node_ids.append(node_id)
            blocked_nodes.append(detail)
    return {
        'role_id': clean_role_id or None,
        'agent_id': clean_agent_id or None,
        'visible_surface_ids': visible_surface_ids,
        'blocked_surface_ids': blocked_surface_ids,
        'visible_surfaces': visible_surfaces,
        'blocked_surfaces': blocked_surfaces,
        'visible_node_ids': visible_node_ids,
        'blocked_node_ids': blocked_node_ids,
        'visible_nodes': visible_nodes,
        'blocked_nodes': blocked_nodes,
        'surface_reason_map': surface_reasons,
        'visible_node_count': len(visible_node_ids),
        'blocked_node_count': len(blocked_node_ids),
    }



def summarize_memory_projection(projection: dict[str, Any]) -> dict[str, Any]:
    row = _as_dict(projection)
    visible_surfaces = _as_list(row.get('visible_surfaces'))
    blocked_surfaces = _as_list(row.get('blocked_surfaces'))
    return {
        'role_id': _clean_id(row.get('role_id')) or None,
        'agent_id': _clean_id(row.get('agent_id')) or None,
        'visible_surface_count': len(_as_list(row.get('visible_surface_ids')) or visible_surfaces),
        'blocked_surface_count': len(_as_list(row.get('blocked_surface_ids')) or blocked_surfaces),
        'visible_node_count': int(row.get('visible_node_count') or len(_as_list(row.get('visible_node_ids'))) or 0),
        'blocked_node_count': int(row.get('blocked_node_count') or len(_as_list(row.get('blocked_node_ids'))) or 0),
    }



def detect_memory_conflicts(*, new_node: dict[str, Any], existing_nodes: Any, existing_conflicts: Any = None) -> list[dict[str, Any]]:
    row = _as_dict(new_node)
    node_id = _clean_text(row.get('id') or row.get('node_id'), max_len=128)
    if not node_id:
        return []
    surface_id = _clean_id(row.get('surface_id') or row.get('surfaceId'))
    node_type = _clean_id(row.get('node_type') or row.get('nodeType') or 'note', max_len=64) or 'note'
    conflict_key = _extract_conflict_key(row)
    signature = _content_signature(row.get('content') or row.get('content_json'))
    confidence = _extract_confidence(row)
    trust_tier = _extract_trust_tier(row)
    trust_rank = _trust_rank(trust_tier)
    provenance = _extract_provenance_fingerprint(row)
    active_existing_pairs: set[tuple[str, str]] = set()
    for conflict in _as_list(existing_conflicts):
        conflict_row = _as_dict(conflict)
        left_id = _clean_text(conflict_row.get('left_node_id'), max_len=128)
        right_id = _clean_text(conflict_row.get('right_node_id'), max_len=128)
        status = _clean_id(conflict_row.get('status') or 'pending', max_len=64) or 'pending'
        if left_id and right_id and status in {'pending', 'accepted', 'merged'}:
            active_existing_pairs.add(tuple(sorted((left_id, right_id))))
    out: list[dict[str, Any]] = []
    for item in _as_list(existing_nodes):
        existing = _as_dict(item)
        existing_id = _clean_text(existing.get('id') or existing.get('node_id'), max_len=128)
        if not existing_id or existing_id == node_id:
            continue
        if _clean_id(existing.get('surface_id') or existing.get('surfaceId')) != surface_id:
            continue
        if _clean_id(existing.get('node_type') or existing.get('nodeType') or 'note', max_len=64) != node_type:
            continue
        existing_key = _extract_conflict_key(existing)
        if conflict_key and existing_key and conflict_key != existing_key:
            continue
        if conflict_key and not existing_key:
            continue
        existing_signature = _content_signature(existing.get('content') or existing.get('content_json'))
        if existing_signature == signature:
            continue
        pair = tuple(sorted((node_id, existing_id)))
        if pair in active_existing_pairs:
            continue
        existing_confidence = _extract_confidence(existing)
        existing_trust_tier = _extract_trust_tier(existing)
        existing_trust_rank = _trust_rank(existing_trust_tier)
        existing_provenance = _extract_provenance_fingerprint(existing)
        provenance_divergent = bool(provenance and existing_provenance and provenance != existing_provenance)
        confidence_gap = abs(confidence - existing_confidence)
        trust_gap = abs(trust_rank - existing_trust_rank)
        if provenance_divergent and confidence_gap >= 0.35:
            reason = 'same_key_divergent_provenance_and_confidence'
        elif provenance_divergent:
            reason = 'same_key_divergent_provenance'
        elif trust_gap >= 2:
            reason = 'same_key_trust_tier_mismatch'
        elif confidence_gap >= 0.35:
            reason = 'same_key_confidence_mismatch'
        else:
            reason = 'same_surface_same_type_divergent_content'
        out.append({
            'surface_id': surface_id,
            'left_node_id': existing_id,
            'right_node_id': node_id,
            'status': 'pending',
            'reason': reason,
            'conflict_key': conflict_key or existing_key or None,
            'left_signature': existing_signature,
            'right_signature': signature,
            'left_trust_tier': existing_trust_tier,
            'right_trust_tier': trust_tier,
            'left_confidence': existing_confidence,
            'right_confidence': confidence,
            'left_provenance_fingerprint': existing_provenance or None,
            'right_provenance_fingerprint': provenance or None,
        })
    return out



def summarize_memory_conflict(conflict: Any) -> dict[str, Any]:
    row = _as_dict(conflict)
    resolution = _as_dict(row.get('resolution') or row.get('resolution_json'))
    return {
        'id': _clean_text(row.get('id'), max_len=128) or None,
        'surface_id': _clean_id(row.get('surface_id')) or None,
        'left_node_id': _clean_text(row.get('left_node_id'), max_len=128) or None,
        'right_node_id': _clean_text(row.get('right_node_id'), max_len=128) or None,
        'status': _clean_id(row.get('status') or 'pending', max_len=64) or 'pending',
        'reason': _clean_text(row.get('reason'), max_len=160) or None,
        'conflict_key': _clean_id(resolution.get('conflict_key'), max_len=160) or None,
        'left_trust_tier': _clean_id(resolution.get('left_trust_tier'), max_len=64) or None,
        'right_trust_tier': _clean_id(resolution.get('right_trust_tier'), max_len=64) or None,
        'left_confidence': _clean_float(resolution.get('left_confidence'), default=0.0),
        'right_confidence': _clean_float(resolution.get('right_confidence'), default=0.0),
        'left_provenance_fingerprint': _clean_text(resolution.get('left_provenance_fingerprint'), max_len=200) or None,
        'right_provenance_fingerprint': _clean_text(resolution.get('right_provenance_fingerprint'), max_len=200) or None,
        'resolution_status': _clean_id(resolution.get('status') or '', max_len=64) or None,
        'winning_node_id': _clean_text(resolution.get('winning_node_id'), max_len=128) or None,
        'losing_node_ids': [_clean_text(v, max_len=128) for v in _as_list(resolution.get('losing_node_ids')) if _clean_text(v, max_len=128)],
    }



def summarize_memory_conflicts(conflicts: Any) -> dict[str, Any]:
    items = [summarize_memory_conflict(item) for item in _as_list(conflicts)]
    counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    for item in items:
        status = item.get('status') or 'pending'
        reason = item.get('reason') or 'unknown'
        counts[status] = counts.get(status, 0) + 1
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    return {
        'items': items,
        'count': len(items),
        'status_counts': counts,
        'reason_counts': reason_counts,
    }



def normalize_conflict_resolution(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    status = _clean_id(row.get('status') or 'resolved', max_len=64) or 'resolved'
    winning = _clean_text(row.get('winning_node_id'), max_len=128) or None
    losing = [_clean_text(v, max_len=128) for v in _as_list(row.get('losing_node_ids')) if _clean_text(v, max_len=128)]
    summary = _clean_text(row.get('summary'), max_len=400)
    return {
        'status': status,
        'winning_node_id': winning,
        'losing_node_ids': losing,
        'summary': summary or None,
    }
