from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
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


def _clean_timestamp(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    text = _clean_text(value, max_len=64)
    return text or None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _surface_visibility_reason(surface: dict[str, Any], *, clean_role_id: str, clean_agent_id: str, include_ids: set[str], exclude_ids: set[str]) -> str:
    surface_id = surface['surface_id']
    target_roles = set(surface.get('target_roles') or [])
    target_agent_ids = set(surface.get('target_agent_ids') or [])
    visibility_scope = _clean_id(surface.get('visibility_scope') or 'shared', max_len=64) or 'shared'
    if surface_id in exclude_ids:
        return 'excluded_by_request'
    if include_ids and surface_id not in include_ids:
        return 'not_in_requested_scope'
    if target_agent_ids and clean_agent_id and clean_agent_id not in target_agent_ids:
        return 'agent_not_allowed'
    if target_agent_ids and not clean_agent_id:
        return 'agent_not_declared'
    if target_roles and clean_role_id and clean_role_id not in target_roles:
        return 'role_not_allowed'
    if target_roles and not clean_role_id:
        return 'role_not_declared'
    if visibility_scope == 'private' and not (target_roles or target_agent_ids):
        return 'private_scope_requires_target'
    return 'visible'



def normalize_memory_surfaces(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in _as_list(raw):
        row = _as_dict(item)
        policy = _as_dict(row.get('policy'))
        surface_id = _clean_id(row.get('surface_id') or row.get('surfaceId') or row.get('id'))
        if not surface_id or surface_id in seen:
            continue
        seen.add(surface_id)
        min_confidence = _clean_float(policy.get('min_confidence'), default=-1.0)
        if min_confidence < 0:
            min_confidence = None
        min_trust_tier = _clean_id(policy.get('min_trust_tier'), max_len=64) or None
        out.append({
            'surface_id': surface_id,
            'title': _clean_text(row.get('title') or surface_id, max_len=160) or surface_id,
            'semantic_kind': _clean_id(row.get('semantic_kind') or row.get('semanticKind') or 'generic', max_len=64) or 'generic',
            'visibility_scope': _clean_id(row.get('visibility_scope') or row.get('visibilityScope') or 'shared', max_len=64) or 'shared',
            'write_mode': _clean_id(row.get('write_mode') or row.get('writeMode') or row.get('write_policy') or 'shared', max_len=64) or 'shared',
            'target_roles': [_clean_id(v) for v in _as_list(row.get('target_roles') or row.get('targetRoles') or policy.get('target_roles')) if _clean_id(v)],
            'target_agent_ids': [_clean_id(v, max_len=128) for v in _as_list(row.get('target_agent_ids') or row.get('targetAgentIds') or policy.get('target_agent_ids')) if _clean_id(v, max_len=128)],
            'allowed_trust_tiers': [_clean_id(v, max_len=64) for v in _as_list(policy.get('allowed_trust_tiers')) if _clean_id(v, max_len=64)],
            'min_trust_tier': min_trust_tier,
            'min_confidence': min_confidence,
            'policy': policy,
        })
    return out


def _node_visibility_reason(node: dict[str, Any], *, visible_surface_ids: set[str], surface_reason_map: dict[str, str], surface_lookup: dict[str, dict[str, Any]], unresolved_conflict_node_ids: set[str]) -> str:
    surface_id = _clean_id(node.get('surface_id') or node.get('surfaceId'))
    node_id = _clean_text(node.get('id') or node.get('node_id'), max_len=128)
    if surface_id not in visible_surface_ids:
        return surface_reason_map.get(surface_id) or 'surface_not_visible'
    status = _clean_id(node.get('status') or 'draft', max_len=64) or 'draft'
    if node_id and node_id in unresolved_conflict_node_ids:
        return 'pending_conflict'
    if status == 'conflicted':
        return 'pending_conflict'
    if status in {'quarantined', 'superseded', 'rejected', 'deleted', 'archived', 'blocked', 'pending_merge'}:
        return f'status_{status}'
    surface = surface_lookup.get(surface_id) or {}
    allowed_trust_tiers = set(surface.get('allowed_trust_tiers') or [])
    trust_tier = _extract_trust_tier(node)
    if allowed_trust_tiers and trust_tier not in allowed_trust_tiers:
        return 'trust_tier_not_allowed'
    min_trust_tier = surface.get('min_trust_tier')
    if min_trust_tier and _trust_rank(trust_tier) < _trust_rank(min_trust_tier):
        return 'trust_tier_below_minimum'
    min_confidence = surface.get('min_confidence')
    if min_confidence is not None and _extract_confidence(node) < float(min_confidence):
        return 'confidence_below_minimum'
    return 'visible'



def build_memory_projection(*, role_id: Any = None, agent_id: Any = None, surfaces: Any = None, nodes: Any = None, include_surface_ids: Any = None, exclude_surface_ids: Any = None, unresolved_conflict_node_ids: Any = None) -> dict[str, Any]:
    clean_role_id = _clean_id(role_id)
    clean_agent_id = _clean_id(agent_id, max_len=128)
    include_ids = {_clean_id(v) for v in _as_list(include_surface_ids) if _clean_id(v)}
    exclude_ids = {_clean_id(v) for v in _as_list(exclude_surface_ids) if _clean_id(v)}
    unresolved_conflict_ids = {_clean_text(v, max_len=128) for v in _as_list(unresolved_conflict_node_ids) if _clean_text(v, max_len=128)}
    surface_rows = normalize_memory_surfaces(surfaces)
    surface_lookup = {surface['surface_id']: surface for surface in surface_rows}
    visible_surface_ids: list[str] = []
    blocked_surface_ids: list[str] = []
    visible_surfaces: list[dict[str, Any]] = []
    blocked_surfaces: list[dict[str, Any]] = []
    surface_reasons: dict[str, str] = {}
    for surface in surface_rows:
        surface_id = surface['surface_id']
        reason = _surface_visibility_reason(
            surface,
            clean_role_id=clean_role_id,
            clean_agent_id=clean_agent_id,
            include_ids=include_ids,
            exclude_ids=exclude_ids,
        )
        surface_reasons[surface_id] = reason
        if reason == 'visible':
            visible_surface_ids.append(surface_id)
            visible_surfaces.append({**surface, 'reason': reason})
        else:
            blocked_surface_ids.append(surface_id)
            blocked_surfaces.append({**surface, 'reason': reason})
    visible_surface_id_set = set(visible_surface_ids)
    visible_node_ids: list[str] = []
    blocked_node_ids: list[str] = []
    visible_nodes: list[dict[str, Any]] = []
    blocked_nodes: list[dict[str, Any]] = []
    node_reason_map: dict[str, str] = {}
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
        reason = _node_visibility_reason(
            row,
            visible_surface_ids=visible_surface_id_set,
            surface_reason_map=surface_reasons,
            surface_lookup=surface_lookup,
            unresolved_conflict_node_ids=unresolved_conflict_ids,
        )
        node_reason_map[node_id] = reason
        if reason == 'visible':
            detail['visibility_reason'] = reason
            visible_node_ids.append(node_id)
            visible_nodes.append(detail)
        else:
            detail['blocked_reason'] = reason
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
        'node_reason_map': node_reason_map,
        'visible_node_count': len(visible_node_ids),
        'blocked_node_count': len(blocked_node_ids),
    }



def summarize_memory_projection(projection: dict[str, Any]) -> dict[str, Any]:
    row = _as_dict(projection)
    visible_surfaces = _as_list(row.get('visible_surfaces'))
    blocked_surfaces = _as_list(row.get('blocked_surfaces'))
    return {
        'role_id': _clean_id(row.get('role_id')) or None,
        'agent_id': _clean_id(row.get('agent_id'), max_len=128) or None,
        'visible_surface_count': len(_as_list(row.get('visible_surface_ids')) or visible_surfaces),
        'blocked_surface_count': len(_as_list(row.get('blocked_surface_ids')) or blocked_surfaces),
        'visible_node_count': int(row.get('visible_node_count') or len(_as_list(row.get('visible_node_ids'))) or 0),
        'blocked_node_count': int(row.get('blocked_node_count') or len(_as_list(row.get('blocked_node_ids'))) or 0),
    }


VALID_MEMORY_EDGE_TYPES = {
    'supports',
    'derived_from',
    'contradicts',
    'supersedes',
    'published_from',
    'related_to',
}

VALID_MEMORY_LIFECYCLE_EVENT_TYPES = {
    'node_drafted',
    'node_published',
    'node_conflicted',
    'node_quarantined',
    'node_superseded',
    'node_merged',
    'node_reopened',
    'node_updated',
}


_LIFECYCLE_EVENT_TITLES = {
    'node_drafted': 'Node drafted',
    'node_published': 'Node published',
    'node_conflicted': 'Node conflicted',
    'node_quarantined': 'Node quarantined',
    'node_superseded': 'Node superseded',
    'node_merged': 'Node merged',
    'node_reopened': 'Node reopened',
    'node_updated': 'Node updated',
}


def lifecycle_event_type_for_status(status: Any, *, default: str = 'node_updated') -> str:
    clean_status = _clean_id(status or '', max_len=64) or ''
    mapping = {
        'draft': 'node_drafted',
        'published': 'node_published',
        'conflicted': 'node_conflicted',
        'quarantined': 'node_quarantined',
        'superseded': 'node_superseded',
        'merged': 'node_merged',
        'pending': 'node_reopened',
    }
    return mapping.get(clean_status, default)


def normalize_memory_lifecycle_event(event: dict[str, Any]) -> dict[str, Any]:
    row = _as_dict(event)
    event_type = _clean_id(row.get('event_type') or row.get('type') or 'node_updated', max_len=64) or 'node_updated'
    if event_type not in VALID_MEMORY_LIFECYCLE_EVENT_TYPES:
        event_type = 'node_updated'
    return {
        'id': _clean_text(row.get('id') or row.get('event_id'), max_len=128) or None,
        'thread_id': _clean_text(row.get('thread_id'), max_len=128) or None,
        'node_id': _clean_text(row.get('node_id'), max_len=128) or None,
        'surface_id': _clean_id(row.get('surface_id') or row.get('surfaceId')) or None,
        'event_type': event_type,
        'from_status': _clean_id(row.get('from_status') or row.get('fromStatus'), max_len=64) or None,
        'to_status': _clean_id(row.get('to_status') or row.get('toStatus'), max_len=64) or None,
        'actor': _clean_text(row.get('actor'), max_len=128) or None,
        'source': _clean_text(row.get('source'), max_len=128) or None,
        'summary': _clean_text(row.get('summary') or row.get('rationale') or '', max_len=320) or None,
        'metadata': _as_dict(row.get('metadata') or row.get('metadata_json')),
        'created_run_id': _clean_text(row.get('created_run_id') or row.get('run_id'), max_len=128) or None,
        'created_at': _clean_timestamp(row.get('created_at')),
    }


def summarize_memory_lifecycle_event(event: dict[str, Any]) -> dict[str, Any]:
    row = normalize_memory_lifecycle_event(event)
    metadata = _as_dict(row.get('metadata'))
    return {
        'id': row.get('id'),
        'thread_id': row.get('thread_id'),
        'node_id': row.get('node_id'),
        'surface_id': row.get('surface_id'),
        'event_type': row.get('event_type'),
        'event_title': _LIFECYCLE_EVENT_TITLES.get(row.get('event_type') or '', str(row.get('event_type') or 'node_updated').replace('_', ' ').title()),
        'from_status': row.get('from_status'),
        'to_status': row.get('to_status'),
        'actor': row.get('actor'),
        'source': row.get('source'),
        'summary': row.get('summary'),
        'metadata': metadata,
        'created_run_id': row.get('created_run_id'),
        'created_at': row.get('created_at'),
        'related_edge_ids': [_clean_text(v, max_len=128) for v in _as_list(metadata.get('related_edge_ids')) if _clean_text(v, max_len=128)],
        'related_conflict_ids': [_clean_text(v, max_len=128) for v in _as_list(metadata.get('related_conflict_ids')) if _clean_text(v, max_len=128)],
        'supporting_memory_node_ids': [_clean_text(v, max_len=128) for v in _as_list(metadata.get('supporting_memory_node_ids')) if _clean_text(v, max_len=128)],
        'supporting_claim_node_ids': [_clean_text(v, max_len=128) for v in _as_list(metadata.get('supporting_claim_node_ids')) if _clean_text(v, max_len=128)],
        'supporting_evidence_node_ids': [_clean_text(v, max_len=128) for v in _as_list(metadata.get('supporting_evidence_node_ids')) if _clean_text(v, max_len=128)],
    }


def normalize_memory_edge(edge: dict[str, Any]) -> dict[str, Any]:
    row = _as_dict(edge)
    edge_type = _clean_id(row.get('edge_type') or row.get('type') or 'related_to', max_len=64) or 'related_to'
    if edge_type not in VALID_MEMORY_EDGE_TYPES:
        edge_type = 'related_to'
    return {
        'id': _clean_text(row.get('id') or row.get('edge_id'), max_len=128) or None,
        'edge_type': edge_type,
        'from_node_id': _clean_text(row.get('from_node_id') or row.get('source_node_id') or row.get('left_node_id'), max_len=128),
        'to_node_id': _clean_text(row.get('to_node_id') or row.get('target_node_id') or row.get('right_node_id'), max_len=128),
        'from_surface_id': _clean_id(row.get('from_surface_id') or row.get('source_surface_id') or row.get('surface_id')) or None,
        'to_surface_id': _clean_id(row.get('to_surface_id') or row.get('target_surface_id') or row.get('surface_id')) or None,
        'status': _clean_id(row.get('status') or 'active', max_len=64) or 'active',
        'rationale': _clean_text(row.get('rationale') or row.get('summary') or '', max_len=320) or None,
        'created_run_id': _clean_text(row.get('created_run_id') or row.get('run_id'), max_len=128) or None,
        'provenance': _as_dict(row.get('provenance') or row.get('provenance_json')),
        'created_at': _clean_timestamp(row.get('created_at')),
        'updated_at': _clean_timestamp(row.get('updated_at')),
    }


_EDGE_TYPE_TITLES = {
    'supports': 'Supports',
    'derived_from': 'Derived from',
    'contradicts': 'Contradicts',
    'supersedes': 'Supersedes',
    'published_from': 'Published from',
    'related_to': 'Related to',
}


def summarize_memory_edge(edge: dict[str, Any], node_lookup: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    row = normalize_memory_edge(edge)
    node_lookup = node_lookup or {}
    from_node = _as_dict(node_lookup.get(row['from_node_id']))
    to_node = _as_dict(node_lookup.get(row['to_node_id']))
    provenance = _as_dict(row.get('provenance'))
    return {
        'id': row.get('id'),
        'edge_type': row['edge_type'],
        'edge_type_title': _EDGE_TYPE_TITLES.get(row['edge_type'], row['edge_type'].replace('_', ' ').title()),
        'from_node_id': row['from_node_id'],
        'to_node_id': row['to_node_id'],
        'from_surface_id': row.get('from_surface_id'),
        'to_surface_id': row.get('to_surface_id'),
        'status': row.get('status') or 'active',
        'rationale': row.get('rationale'),
        'created_run_id': row.get('created_run_id'),
        'created_at': row.get('created_at'),
        'updated_at': row.get('updated_at'),
        'from_node_type': _clean_id(from_node.get('node_type') or from_node.get('nodeType'), max_len=64) or None,
        'to_node_type': _clean_id(to_node.get('node_type') or to_node.get('nodeType'), max_len=64) or None,
        'from_node_preview': _extract_node_preview(from_node) or None,
        'to_node_preview': _extract_node_preview(to_node) or None,
        'from_owner_role_id': _clean_id(from_node.get('owner_role_id'), max_len=128) or None,
        'to_owner_role_id': _clean_id(to_node.get('owner_role_id'), max_len=128) or None,
        'provenance_fingerprint': _extract_provenance_fingerprint({'provenance_json': provenance}) or None,
        'evidence_node_ids': [_clean_text(v, max_len=128) for v in _as_list(provenance.get('evidence_node_ids')) if _clean_text(v, max_len=128)],
        'supporting_claim_node_ids': [_clean_text(v, max_len=128) for v in _as_list(provenance.get('supporting_claim_node_ids')) if _clean_text(v, max_len=128)],
        'supporting_memory_node_ids': [_clean_text(v, max_len=128) for v in _as_list(provenance.get('supporting_memory_node_ids')) if _clean_text(v, max_len=128)],
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
    history = [normalize_conflict_history_entry(item) for item in _as_list(resolution.get('history'))]
    merge_history = [normalize_conflict_history_entry(item) for item in _as_list(resolution.get('merge_history'))]
    latest_event = normalize_conflict_history_entry(resolution.get('latest_event')) if _as_dict(resolution.get('latest_event')) else (history[-1] if history else None)
    latest_merge_event = normalize_conflict_history_entry(resolution.get('latest_merge_event')) if _as_dict(resolution.get('latest_merge_event')) else (merge_history[-1] if merge_history else None)
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
        'resolution_summary': _clean_text(resolution.get('summary'), max_len=400) or None,
        'resolution_rationale_codes': [_clean_id(v, max_len=96) for v in _as_list(resolution.get('rationale_codes')) if _clean_id(v, max_len=96)],
        'supporting_claim_node_ids': [_clean_text(v, max_len=128) for v in _as_list(resolution.get('supporting_claim_node_ids')) if _clean_text(v, max_len=128)],
        'supporting_evidence_node_ids': [_clean_text(v, max_len=128) for v in _as_list(resolution.get('supporting_evidence_node_ids')) if _clean_text(v, max_len=128)],
        'supporting_memory_node_ids': [_clean_text(v, max_len=128) for v in _as_list(resolution.get('supporting_memory_node_ids')) if _clean_text(v, max_len=128)],
        'history': history,
        'history_count': len(history),
        'latest_history_event': latest_event,
        'merge_history': merge_history,
        'merge_history_count': len(merge_history),
        'latest_merge_event': latest_merge_event,
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



def normalize_conflict_history_entry(raw: Any, *, default_event_type: str | None = None, default_source: str | None = None, default_created_at: str | None = None) -> dict[str, Any]:
    row = _as_dict(raw)
    return {
        'event_type': _clean_id(row.get('event_type') or row.get('type') or default_event_type or 'conflict_update', max_len=96) or 'conflict_update',
        'status': _clean_id(row.get('status') or row.get('resolution_status') or '', max_len=64) or None,
        'previous_status': _clean_id(row.get('previous_status') or '', max_len=64) or None,
        'actor': _clean_text(row.get('actor') or row.get('resolved_by') or row.get('actor_label'), max_len=120) or None,
        'source': _clean_id(row.get('source') or row.get('resolution_source') or default_source or 'system', max_len=96) or 'system',
        'created_at': _clean_timestamp(row.get('created_at')) or default_created_at or _now_iso(),
        'summary': _clean_text(row.get('summary') or row.get('resolution_summary') or row.get('note'), max_len=400) or None,
        'merge_note': _clean_text(row.get('merge_note'), max_len=240) or None,
        'winning_node_id': _clean_text(row.get('winning_node_id'), max_len=128) or None,
        'losing_node_ids': [_clean_text(v, max_len=128) for v in _as_list(row.get('losing_node_ids')) if _clean_text(v, max_len=128)],
        'rationale_codes': [_clean_id(v, max_len=96) for v in _as_list(row.get('rationale_codes')) if _clean_id(v, max_len=96)],
        'supporting_claim_node_ids': [_clean_text(v, max_len=128) for v in _as_list(row.get('supporting_claim_node_ids')) if _clean_text(v, max_len=128)],
        'supporting_evidence_node_ids': [_clean_text(v, max_len=128) for v in _as_list(row.get('supporting_evidence_node_ids')) if _clean_text(v, max_len=128)],
        'supporting_memory_node_ids': [_clean_text(v, max_len=128) for v in _as_list(row.get('supporting_memory_node_ids')) if _clean_text(v, max_len=128)],
    }


def append_conflict_history(resolution: Any, event: Any, *, max_items: int = 50) -> dict[str, Any]:
    out = _as_dict(resolution).copy()
    history = [normalize_conflict_history_entry(item) for item in _as_list(out.get('history'))]
    clean_event = normalize_conflict_history_entry(event)
    history.append(clean_event)
    history = history[-max_items:]
    merge_history = [
        item for item in history
        if item.get('event_type') in {'conflict_resolved', 'conflict_merged', 'conflict_quarantined', 'conflict_reopened'}
        or item.get('status') in {'resolved', 'merged', 'accepted', 'quarantined', 'pending'}
    ]
    out['history'] = history
    out['merge_history'] = merge_history[-max_items:]
    out['latest_event'] = clean_event
    if merge_history:
        out['latest_merge_event'] = merge_history[-1]
    return out


def normalize_conflict_resolution(raw: Any) -> dict[str, Any]:
    row = _as_dict(raw)
    status = _clean_id(row.get('status') or 'resolved', max_len=64) or 'resolved'
    winning = _clean_text(row.get('winning_node_id'), max_len=128) or None
    losing = [_clean_text(v, max_len=128) for v in _as_list(row.get('losing_node_ids')) if _clean_text(v, max_len=128)]
    summary = _clean_text(row.get('summary'), max_len=400)
    rationale_codes = [_clean_id(v, max_len=96) for v in _as_list(row.get('rationale_codes')) if _clean_id(v, max_len=96)]
    supporting_claim_node_ids = [_clean_text(v, max_len=128) for v in _as_list(row.get('supporting_claim_node_ids')) if _clean_text(v, max_len=128)]
    supporting_evidence_node_ids = [_clean_text(v, max_len=128) for v in _as_list(row.get('supporting_evidence_node_ids')) if _clean_text(v, max_len=128)]
    supporting_memory_node_ids = [_clean_text(v, max_len=128) for v in _as_list(row.get('supporting_memory_node_ids')) if _clean_text(v, max_len=128)]
    resolved_by = _clean_text(row.get('resolved_by'), max_len=120) or None
    resolution_source = _clean_id(row.get('resolution_source') or 'operator', max_len=96) or 'operator'
    merge_note = _clean_text(row.get('merge_note'), max_len=240) or None
    return {
        'status': status,
        'winning_node_id': winning,
        'losing_node_ids': losing,
        'summary': summary or None,
        'rationale_codes': rationale_codes,
        'supporting_claim_node_ids': supporting_claim_node_ids,
        'supporting_evidence_node_ids': supporting_evidence_node_ids,
        'supporting_memory_node_ids': supporting_memory_node_ids,
        'resolved_by': resolved_by,
        'resolution_source': resolution_source,
        'merge_note': merge_note,
    }
