from __future__ import annotations

from typing import Any


def _short_text(value: str, max_len: int = 220) -> str:
    compact = " ".join(str(value or "").split())
    if len(compact) <= max_len:
        return compact
    return f"{compact[:max_len]}..."


def _clean_node_ids(values: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    if not isinstance(values, list):
        return out
    for value in values:
        clean = str(value or '').strip()
        if not clean or clean in seen:
            continue
        out.append(clean)
        seen.add(clean)
    return out


_XREF_TRUST_RANKS = {
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



_XREF_TRUST_RANKS = {
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


def _xref_trust_rank(value: Any) -> int:
    clean = str(value or '').strip().lower()
    return _XREF_TRUST_RANKS.get(clean, 0)

def _build_conflict_resolution_suggestion(
    conflict_entry: dict[str, Any],
    *,
    memory_by_id: dict[str, dict[str, Any]],
    claim_links_by_id: dict[str, dict[str, Any]],
    anchor_node_id: str | None,
) -> dict[str, Any] | None:
    node_ids = _clean_node_ids(list(conflict_entry.get('node_ids') or []))
    if not node_ids:
        return None
    candidates: list[dict[str, Any]] = []
    for node_id in node_ids:
        memory_entry = memory_by_id.get(node_id) or {}
        trust_tier = str(memory_entry.get('trust_tier') or '').strip() or None
        confidence = float(memory_entry.get('confidence') or 0.0)
        visible_projection_count = int(memory_entry.get('visible_projection_count') or 0)
        blocked_projection_count = int(memory_entry.get('blocked_projection_count') or 0)
        status = str(memory_entry.get('status') or '').strip().lower() or None
        status_bonus = 0.0
        if status == 'published':
            status_bonus = 1.0
        elif status in {'conflicted', 'quarantined', 'superseded'}:
            status_bonus = -1.0
        score = (
            (_xref_trust_rank(trust_tier) * 100.0)
            + (confidence * 10.0)
            + (visible_projection_count * 2.0)
            - float(blocked_projection_count)
            + status_bonus
        )
        candidates.append({
            'node_id': node_id,
            'score': score,
            'trust_tier': trust_tier,
            'confidence': confidence,
            'visible_projection_count': visible_projection_count,
            'blocked_projection_count': blocked_projection_count,
            'status': status,
            'content_preview': str(memory_entry.get('content_preview') or '').strip() or None,
        })
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            float(item.get('score') or 0.0),
            _xref_trust_rank(item.get('trust_tier')),
            float(item.get('confidence') or 0.0),
            int(item.get('visible_projection_count') or 0),
            str(item.get('node_id') or ''),
        ),
        reverse=True,
    )
    winner = candidates[0]
    losers = candidates[1:]
    rationale_codes: list[str] = []
    if losers:
        best_loser = losers[0]
        if _xref_trust_rank(winner.get('trust_tier')) > _xref_trust_rank(best_loser.get('trust_tier')):
            rationale_codes.append('higher_trust_tier')
        if float(winner.get('confidence') or 0.0) >= float(best_loser.get('confidence') or 0.0) + 0.05:
            rationale_codes.append('higher_confidence')
        if int(winner.get('visible_projection_count') or 0) > int(best_loser.get('visible_projection_count') or 0):
            rationale_codes.append('broader_projection_visibility')
    supporting_claim_ids = _clean_node_ids(list(conflict_entry.get('related_claim_node_ids') or []))
    claim_entries = [claim_links_by_id[claim_id] for claim_id in supporting_claim_ids if claim_id in claim_links_by_id]
    claim_entries.sort(key=lambda item: (float(item.get('score') or 0.0), str(item.get('claim_node_id') or '')), reverse=True)
    if claim_entries:
        rationale_codes.append('linked_claim_support')
    top_claim = claim_entries[0] if claim_entries else None
    supporting_evidence_node_ids = _clean_node_ids([
        *(conflict_entry.get('supporting_evidence_node_ids') or []),
        *[evidence_id for claim in claim_entries for evidence_id in (claim.get('related_evidence_node_ids') or [])],
    ])
    supporting_memory_node_ids = _clean_node_ids([
        *(conflict_entry.get('supporting_memory_node_ids') or []),
        *node_ids,
    ])
    if top_claim and top_claim.get('related_evidence_node_ids'):
        rationale_codes.append('linked_evidence_nodes')
    if anchor_node_id and winner.get('node_id') == anchor_node_id:
        rationale_codes.append('trace_anchor_alignment')
    rationale_codes = _clean_node_ids(rationale_codes)

    summary_parts: list[str] = [f"Keep {winner['node_id']} as the winning memory node"]
    if rationale_codes:
        reason_fragments: list[str] = []
        if 'higher_trust_tier' in rationale_codes:
            reason_fragments.append('it has a stronger trust tier')
        if 'higher_confidence' in rationale_codes:
            reason_fragments.append('it carries higher confidence')
        if 'broader_projection_visibility' in rationale_codes:
            reason_fragments.append('it remains visible in more role-conditioned projections')
        if 'linked_claim_support' in rationale_codes and top_claim:
            claim_text = str(top_claim.get('claim_text') or '').strip()
            if claim_text:
                reason_fragments.append(f'it is better aligned with the linked claim “{_short_text(claim_text, 120)}”')
            else:
                reason_fragments.append('it is better aligned with the linked execution claim')
        if 'linked_evidence_nodes' in rationale_codes:
            reason_fragments.append('the linked claim is backed by evidence nodes in the same run')
        if 'trace_anchor_alignment' in rationale_codes:
            reason_fragments.append('it aligns with the focused trace anchor')
        if reason_fragments:
            summary_parts.append('because ' + '; '.join(reason_fragments))
    summary = ' '.join(summary_parts).strip()

    return {
        'winning_node_id': winner.get('node_id'),
        'losing_node_ids': [item.get('node_id') for item in losers if item.get('node_id')],
        'summary': summary,
        'rationale_codes': rationale_codes,
        'supporting_claim_node_ids': supporting_claim_ids,
        'supporting_evidence_node_ids': supporting_evidence_node_ids,
        'supporting_memory_node_ids': supporting_memory_node_ids,
        'top_claim_node_id': top_claim.get('claim_node_id') if top_claim else None,
        'top_claim_text': str(top_claim.get('claim_text') or '').strip() or None if top_claim else None,
    }




def build_run_bundle_cross_references(
    *,
    evidence: dict[str, Any] | None,
    memory_graph: dict[str, Any] | None,
    trace_scope: dict[str, Any] | None,
) -> dict[str, Any]:
    evidence_obj = evidence or {}
    memory_obj = memory_graph or {}
    trace_obj = trace_scope or {}
    anchor_node_id = str(trace_obj.get('anchor_node_id') or '').strip() or None

    memory_by_id: dict[str, dict[str, Any]] = {}
    for projection in memory_obj.get('projections') or []:
        projection_role_id = str(projection.get('role_id') or '').strip() or None
        for blocked in (False, True):
            for node in projection.get('blocked_nodes' if blocked else 'visible_nodes') or []:
                node_id = str(node.get('node_id') or '').strip()
                if not node_id:
                    continue
                entry = memory_by_id.setdefault(
                    node_id,
                    {
                        'memory_node_id': node_id,
                        'surface_id': str(node.get('surface_id') or '').strip() or None,
                        'node_type': str(node.get('node_type') or '').strip() or None,
                        'status': str(node.get('status') or '').strip() or None,
                        'owner_role_id': str(node.get('owner_role_id') or '').strip() or None,
                        'trust_tier': str(node.get('trust_tier') or '').strip() or None,
                        'confidence': float(node.get('confidence') or 0.0),
                        'content_preview': str(node.get('content_preview') or '').strip() or None,
                        'provenance_fingerprint': str(node.get('provenance_fingerprint') or '').strip() or None,
                        'projection_role_ids': [],
                        'visible_projection_count': 0,
                        'blocked_projection_count': 0,
                        'related_claim_node_ids': [],
                        'related_conflict_ids': [],
                        'related_edge_ids': [],
                        'related_lifecycle_event_ids': [],
                        'trace_anchor_related': False,
                    },
                )
                if projection_role_id and projection_role_id not in entry['projection_role_ids']:
                    entry['projection_role_ids'].append(projection_role_id)
                if blocked:
                    entry['blocked_projection_count'] += 1
                else:
                    entry['visible_projection_count'] += 1
                if anchor_node_id and node_id == anchor_node_id:
                    entry['trace_anchor_related'] = True

    conflict_by_id: dict[str, dict[str, Any]] = {}
    node_to_conflict_ids: dict[str, set[str]] = {}
    for conflict in memory_obj.get('conflicts') or []:
        conflict_id = str(conflict.get('id') or '').strip()
        if not conflict_id:
            continue
        node_ids = _clean_node_ids([
            conflict.get('left_node_id'),
            conflict.get('right_node_id'),
            conflict.get('winning_node_id'),
            *list(conflict.get('losing_node_ids') or []),
        ])
        entry = {
            'conflict_id': conflict_id,
            'surface_id': str(conflict.get('surface_id') or '').strip() or None,
            'status': str(conflict.get('status') or '').strip() or None,
            'reason': str(conflict.get('reason') or '').strip() or None,
            'node_ids': node_ids,
            'winning_node_id': str(conflict.get('winning_node_id') or '').strip() or None,
            'losing_node_ids': _clean_node_ids(list(conflict.get('losing_node_ids') or [])),
            'resolution_summary': str(conflict.get('resolution_summary') or '').strip() or None,
            'resolution_rationale_codes': _clean_node_ids(list(conflict.get('resolution_rationale_codes') or [])),
            'supporting_claim_node_ids': _clean_node_ids(list(conflict.get('supporting_claim_node_ids') or [])),
            'supporting_evidence_node_ids': _clean_node_ids(list(conflict.get('supporting_evidence_node_ids') or [])),
            'supporting_memory_node_ids': _clean_node_ids(list(conflict.get('supporting_memory_node_ids') or [])),
            'history': [item for item in (conflict.get('history') or []) if isinstance(item, dict)],
            'history_count': int(conflict.get('history_count') or len(conflict.get('history') or [])),
            'latest_history_event': conflict.get('latest_history_event') if isinstance(conflict.get('latest_history_event'), dict) else None,
            'merge_history': [item for item in (conflict.get('merge_history') or []) if isinstance(item, dict)],
            'merge_history_count': int(conflict.get('merge_history_count') or len(conflict.get('merge_history') or [])),
            'latest_merge_event': conflict.get('latest_merge_event') if isinstance(conflict.get('latest_merge_event'), dict) else None,
            'related_claim_node_ids': [],
            'related_memory_node_ids': [node_id for node_id in node_ids if node_id in memory_by_id],
            'related_edge_ids': [],
            'trace_anchor_related': bool(anchor_node_id and anchor_node_id in node_ids),
        }
        conflict_by_id[conflict_id] = entry
        for node_id in node_ids:
            node_to_conflict_ids.setdefault(node_id, set()).add(conflict_id)

    edge_by_id: dict[str, dict[str, Any]] = {}
    node_to_edge_ids: dict[str, set[str]] = {}
    edge_to_conflict_ids: dict[str, set[str]] = {}
    for edge in memory_obj.get('edges') or []:
        edge_id = str(edge.get('id') or '').strip()
        if not edge_id:
            continue
        endpoint_node_ids = _clean_node_ids([
            edge.get('from_node_id'),
            edge.get('to_node_id'),
            *list(edge.get('supporting_memory_node_ids') or []),
        ])
        entry = {
            'edge_id': edge_id,
            'edge_type': str(edge.get('edge_type') or '').strip() or 'related_to',
            'edge_type_title': str(edge.get('edge_type_title') or '').strip() or None,
            'from_node_id': str(edge.get('from_node_id') or '').strip() or None,
            'to_node_id': str(edge.get('to_node_id') or '').strip() or None,
            'from_surface_id': str(edge.get('from_surface_id') or '').strip() or None,
            'to_surface_id': str(edge.get('to_surface_id') or '').strip() or None,
            'status': str(edge.get('status') or '').strip() or None,
            'rationale': str(edge.get('rationale') or '').strip() or None,
            'created_run_id': str(edge.get('created_run_id') or '').strip() or None,
            'created_at': edge.get('created_at'),
            'updated_at': edge.get('updated_at'),
            'from_node_type': str(edge.get('from_node_type') or '').strip() or None,
            'to_node_type': str(edge.get('to_node_type') or '').strip() or None,
            'from_node_preview': str(edge.get('from_node_preview') or '').strip() or None,
            'to_node_preview': str(edge.get('to_node_preview') or '').strip() or None,
            'from_owner_role_id': str(edge.get('from_owner_role_id') or '').strip() or None,
            'to_owner_role_id': str(edge.get('to_owner_role_id') or '').strip() or None,
            'provenance_fingerprint': str(edge.get('provenance_fingerprint') or '').strip() or None,
            'evidence_node_ids': _clean_node_ids(list(edge.get('evidence_node_ids') or [])),
            'supporting_claim_node_ids': _clean_node_ids(list(edge.get('supporting_claim_node_ids') or [])),
            'supporting_memory_node_ids': _clean_node_ids(list(edge.get('supporting_memory_node_ids') or [])),
            'related_memory_node_ids': endpoint_node_ids,
            'related_claim_node_ids': [],
            'related_conflict_ids': [],
            'trace_anchor_related': bool(anchor_node_id and anchor_node_id in endpoint_node_ids),
        }
        edge_by_id[edge_id] = entry
        for node_id in endpoint_node_ids:
            node_to_edge_ids.setdefault(node_id, set()).add(edge_id)
        related_conflict_ids = {
            conflict_id
            for node_id in endpoint_node_ids
            for conflict_id in node_to_conflict_ids.get(node_id, set())
            if conflict_id in conflict_by_id
        }
        if related_conflict_ids:
            entry['related_conflict_ids'] = sorted(related_conflict_ids)
        for conflict_id in related_conflict_ids:
            edge_to_conflict_ids.setdefault(edge_id, set()).add(conflict_id)

    memory_to_claim_ids: dict[str, set[str]] = {node_id: set() for node_id in memory_by_id}
    conflict_to_claim_ids: dict[str, set[str]] = {conflict_id: set() for conflict_id in conflict_by_id}
    edge_to_claim_ids: dict[str, set[str]] = {edge_id: set() for edge_id in edge_by_id}
    claim_to_evidence_ids: dict[str, set[str]] = {}
    memory_to_lifecycle_ids: dict[str, set[str]] = {node_id: set() for node_id in memory_by_id}
    claim_to_lifecycle_ids: dict[str, set[str]] = {}
    lifecycle_links: list[dict[str, Any]] = []
    claim_links: list[dict[str, Any]] = []
    claim_links_by_id: dict[str, dict[str, Any]] = {}
    for item in evidence_obj.get('items') or []:
        claim_node_id = str(item.get('claim_node_id') or '').strip()
        if not claim_node_id:
            continue
        related_ids = _clean_node_ids([
            claim_node_id,
            *list(item.get('related_node_ids') or []),
            *[row.get('id') for row in (item.get('evidence_nodes') or []) if isinstance(row, dict)],
            *list(item.get('conflict_node_ids') or []),
        ])
        linked_memory_ids = sorted({node_id for node_id in related_ids if node_id in memory_by_id})
        linked_conflict_ids = sorted({
            conflict_id
            for node_id in related_ids
            for conflict_id in node_to_conflict_ids.get(node_id, set())
            if conflict_id in conflict_by_id
        })
        linked_edge_ids = sorted({
            edge_id
            for node_id in linked_memory_ids
            for edge_id in node_to_edge_ids.get(node_id, set())
            if edge_id in edge_by_id
        })
        claim_to_evidence_ids[claim_node_id] = set(_clean_node_ids([row.get('id') for row in (item.get('evidence_nodes') or []) if isinstance(row, dict)]))
        for memory_node_id in linked_memory_ids:
            memory_to_claim_ids.setdefault(memory_node_id, set()).add(claim_node_id)
        for conflict_id in linked_conflict_ids:
            conflict_to_claim_ids.setdefault(conflict_id, set()).add(claim_node_id)
        for edge_id in linked_edge_ids:
            edge_to_claim_ids.setdefault(edge_id, set()).add(claim_node_id)
        entry = {
            'claim_node_id': claim_node_id,
            'claim_node_type': str(item.get('claim_node_type') or '').strip() or None,
            'claim_text': str(item.get('claim_text') or '').strip() or None,
            'related_memory_node_ids': linked_memory_ids,
            'related_memory_edge_ids': linked_edge_ids,
            'related_conflict_ids': linked_conflict_ids,
            'related_evidence_node_ids': _clean_node_ids([row.get('id') for row in (item.get('evidence_nodes') or []) if isinstance(row, dict)]),
            'related_lifecycle_event_ids': [],
            'compare_node_ids': _clean_node_ids([
                claim_node_id,
                *linked_memory_ids,
                *[node_id for conflict_id in linked_conflict_ids for node_id in conflict_by_id.get(conflict_id, {}).get('node_ids', [])],
                *[node_id for edge_id in linked_edge_ids for node_id in edge_by_id.get(edge_id, {}).get('related_memory_node_ids', [])],
                *[row.get('id') for row in (item.get('evidence_nodes') or []) if isinstance(row, dict)],
            ]),
            'trace_anchor_related': bool(anchor_node_id and (anchor_node_id in related_ids or anchor_node_id in linked_memory_ids)),
            'selected_in_context': bool(item.get('selected_in_context')),
            'pinned': bool(item.get('pinned')),
            'score': item.get('score'),
        }
        claim_links.append(entry)
        claim_links_by_id[claim_node_id] = entry

    for memory_node_id, claim_ids in memory_to_claim_ids.items():
        entry = memory_by_id.get(memory_node_id)
        if not entry:
            continue
        entry['related_claim_node_ids'] = sorted(claim_ids)
        entry['related_conflict_ids'] = sorted(node_to_conflict_ids.get(memory_node_id, set()))
        entry['related_edge_ids'] = sorted(node_to_edge_ids.get(memory_node_id, set()))
        if anchor_node_id and memory_node_id == anchor_node_id:
            entry['trace_anchor_related'] = True

    for conflict_id, claim_ids in conflict_to_claim_ids.items():
        entry = conflict_by_id.get(conflict_id)
        if not entry:
            continue
        entry['related_claim_node_ids'] = sorted(claim_ids)
        entry['related_edge_ids'] = sorted({
            edge_id
            for node_id in entry.get('node_ids') or []
            for edge_id in node_to_edge_ids.get(node_id, set())
            if edge_id in edge_by_id
        })
        entry['supporting_claim_node_ids'] = _clean_node_ids([
            *(entry.get('supporting_claim_node_ids') or []),
            *sorted(claim_ids),
        ])
        linked_claim_entries = [claim_links_by_id[claim_id] for claim_id in entry['related_claim_node_ids'] if claim_id in claim_links_by_id]
        entry['supporting_evidence_node_ids'] = _clean_node_ids([
            *(entry.get('supporting_evidence_node_ids') or []),
            *[evidence_id for claim in linked_claim_entries for evidence_id in (claim.get('related_evidence_node_ids') or [])],
        ])
        entry['supporting_memory_node_ids'] = _clean_node_ids([
            *(entry.get('supporting_memory_node_ids') or []),
            *(entry.get('related_memory_node_ids') or []),
        ])
        entry['suggested_resolution'] = _build_conflict_resolution_suggestion(
            entry,
            memory_by_id=memory_by_id,
            claim_links_by_id=claim_links_by_id,
            anchor_node_id=anchor_node_id,
        )
        if anchor_node_id and anchor_node_id in entry.get('node_ids', []):
            entry['trace_anchor_related'] = True

    for edge_id, claim_ids in edge_to_claim_ids.items():
        entry = edge_by_id.get(edge_id)
        if not entry:
            continue
        entry['related_claim_node_ids'] = sorted(claim_ids)
        entry['related_conflict_ids'] = sorted(edge_to_conflict_ids.get(edge_id, set()) or {
            conflict_id
            for node_id in entry.get('related_memory_node_ids') or []
            for conflict_id in node_to_conflict_ids.get(node_id, set())
            if conflict_id in conflict_by_id
        })
        entry['supporting_claim_node_ids'] = _clean_node_ids([
            *(entry.get('supporting_claim_node_ids') or []),
            *sorted(claim_ids),
        ])
        linked_claim_entries = [claim_links_by_id[claim_id] for claim_id in entry['related_claim_node_ids'] if claim_id in claim_links_by_id]
        entry['evidence_node_ids'] = _clean_node_ids([
            *(entry.get('evidence_node_ids') or []),
            *[evidence_id for claim in linked_claim_entries for evidence_id in (claim.get('related_evidence_node_ids') or [])],
        ])
        entry['supporting_memory_node_ids'] = _clean_node_ids([
            *(entry.get('supporting_memory_node_ids') or []),
            *(entry.get('related_memory_node_ids') or []),
        ])
        if anchor_node_id and anchor_node_id in entry.get('related_memory_node_ids', []):
            entry['trace_anchor_related'] = True

    lifecycle_by_id: dict[str, dict[str, Any]] = {}
    lifecycle_to_claim_ids: dict[str, set[str]] = {}
    lifecycle_to_evidence_ids: dict[str, set[str]] = {}
    lifecycle_to_conflict_ids: dict[str, set[str]] = {}
    lifecycle_to_edge_ids: dict[str, set[str]] = {}
    for event in memory_obj.get('lifecycle_events') or []:
        event_id = str(event.get('id') or '').strip()
        if not event_id:
            continue
        endpoint_node_ids = _clean_node_ids([
            event.get('node_id'),
            *(event.get('supporting_memory_node_ids') or []),
        ])
        explicit_claim_ids = _clean_node_ids(list(event.get('supporting_claim_node_ids') or []))
        explicit_evidence_ids = _clean_node_ids(list(event.get('supporting_evidence_node_ids') or []))
        inferred_claim_ids = sorted({
            claim_id
            for node_id in endpoint_node_ids
            for claim_id in memory_to_claim_ids.get(node_id, set())
            if claim_id in claim_links_by_id
        })
        related_claim_ids = _clean_node_ids([*explicit_claim_ids, *inferred_claim_ids])
        related_evidence_ids = _clean_node_ids([
            *explicit_evidence_ids,
            *[evidence_id for claim_id in related_claim_ids for evidence_id in claim_to_evidence_ids.get(claim_id, set())],
        ])
        related_conflict_ids = sorted({
            *[conflict_id for conflict_id in _clean_node_ids(list(event.get('related_conflict_ids') or [])) if conflict_id in conflict_by_id],
            *{
                conflict_id
                for node_id in endpoint_node_ids
                for conflict_id in node_to_conflict_ids.get(node_id, set())
                if conflict_id in conflict_by_id
            },
        })
        related_edge_ids = sorted({
            *[edge_id for edge_id in _clean_node_ids(list(event.get('related_edge_ids') or [])) if edge_id in edge_by_id],
            *{
                edge_id
                for node_id in endpoint_node_ids
                for edge_id in node_to_edge_ids.get(node_id, set())
                if edge_id in edge_by_id
            },
        })
        entry = {
            'event_id': event_id,
            'event_type': str(event.get('event_type') or '').strip() or None,
            'event_title': str(event.get('event_title') or '').strip() or None,
            'node_id': str(event.get('node_id') or '').strip() or None,
            'surface_id': str(event.get('surface_id') or '').strip() or None,
            'from_status': str(event.get('from_status') or '').strip() or None,
            'to_status': str(event.get('to_status') or '').strip() or None,
            'actor': str(event.get('actor') or '').strip() or None,
            'source': str(event.get('source') or '').strip() or None,
            'summary': str(event.get('summary') or '').strip() or None,
            'created_run_id': str(event.get('created_run_id') or '').strip() or None,
            'created_at': event.get('created_at'),
            'supporting_memory_node_ids': _clean_node_ids(list(event.get('supporting_memory_node_ids') or [])),
            'supporting_claim_node_ids': related_claim_ids,
            'supporting_evidence_node_ids': related_evidence_ids,
            'related_claim_node_ids': related_claim_ids,
            'related_evidence_node_ids': related_evidence_ids,
            'related_conflict_ids': related_conflict_ids,
            'related_edge_ids': related_edge_ids,
            'trace_anchor_related': bool(anchor_node_id and anchor_node_id in endpoint_node_ids),
        }
        lifecycle_by_id[event_id] = entry
        if entry['trace_anchor_related']:
            pass
        for node_id in endpoint_node_ids:
            memory_to_lifecycle_ids.setdefault(node_id, set()).add(event_id)
        for claim_id in related_claim_ids:
            lifecycle_to_claim_ids.setdefault(event_id, set()).add(claim_id)
            claim_to_lifecycle_ids.setdefault(claim_id, set()).add(event_id)
        for evidence_id in related_evidence_ids:
            lifecycle_to_evidence_ids.setdefault(event_id, set()).add(evidence_id)
        for conflict_id in related_conflict_ids:
            lifecycle_to_conflict_ids.setdefault(event_id, set()).add(conflict_id)
        for edge_id in related_edge_ids:
            lifecycle_to_edge_ids.setdefault(event_id, set()).add(edge_id)
        lifecycle_links.append(entry)

    for claim_id, lifecycle_ids in claim_to_lifecycle_ids.items():
        entry = claim_links_by_id.get(claim_id)
        if entry:
            entry['related_lifecycle_event_ids'] = sorted(lifecycle_ids)

    for memory_node_id, lifecycle_ids in memory_to_lifecycle_ids.items():
        entry = memory_by_id.get(memory_node_id)
        if entry:
            entry['related_lifecycle_event_ids'] = sorted(lifecycle_ids)

    for edge_id, entry in edge_by_id.items():
        linked_lifecycle_ids = sorted({
            lifecycle_id
            for lifecycle_id, related_edge_ids in lifecycle_to_edge_ids.items()
            if edge_id in related_edge_ids
        })
        entry['related_lifecycle_event_ids'] = linked_lifecycle_ids

    for conflict_id, entry in conflict_by_id.items():
        linked_lifecycle_ids = sorted({
            lifecycle_id
            for lifecycle_id, related_conflict_ids in lifecycle_to_conflict_ids.items()
            if conflict_id in related_conflict_ids
        })
        entry['related_lifecycle_event_ids'] = linked_lifecycle_ids


    claim_links.sort(key=lambda item: (
        len(item.get('related_memory_node_ids') or []),
        len(item.get('related_memory_edge_ids') or []),
        len(item.get('related_conflict_ids') or []),
        float(item.get('score') or 0),
        str(item.get('claim_node_id') or ''),
    ), reverse=True)
    memory_links = sorted(
        memory_by_id.values(),
        key=lambda item: (
            len(item.get('related_claim_node_ids') or []),
            len(item.get('related_edge_ids') or []),
            len(item.get('related_conflict_ids') or []),
            int(item.get('visible_projection_count') or 0),
            str(item.get('memory_node_id') or ''),
        ),
        reverse=True,
    )
    edge_links = sorted(
        edge_by_id.values(),
        key=lambda item: (
            len(item.get('related_claim_node_ids') or []),
            len(item.get('related_conflict_ids') or []),
            len(item.get('evidence_node_ids') or []),
            str(item.get('edge_id') or ''),
        ),
        reverse=True,
    )
    conflict_links = sorted(
        conflict_by_id.values(),
        key=lambda item: (
            len(item.get('related_claim_node_ids') or []),
            len(item.get('related_edge_ids') or []),
            len(item.get('related_memory_node_ids') or []),
            int(bool(item.get('resolution_summary'))),
            str(item.get('conflict_id') or ''),
        ),
        reverse=True,
    )
    lifecycle_links = sorted(
        lifecycle_links,
        key=lambda item: (
            len(item.get('related_claim_node_ids') or []),
            len(item.get('related_evidence_node_ids') or []),
            len(item.get('related_edge_ids') or []),
            len(item.get('related_conflict_ids') or []),
            str(item.get('created_at') or ''),
            str(item.get('event_id') or ''),
        ),
        reverse=True,
    )

    return {
        'run_id': str(evidence_obj.get('run_id') or memory_obj.get('run_id') or trace_obj.get('run_id') or '').strip() or None,
        'scope': str(evidence_obj.get('scope') or memory_obj.get('scope') or trace_obj.get('scope') or 'thread').strip() or 'thread',
        'anchor_node_id': anchor_node_id,
        'claim_links': claim_links[:24],
        'memory_links': memory_links[:24],
        'edge_links': edge_links[:24],
        'conflict_links': conflict_links[:24],
        'lifecycle_links': lifecycle_links[:24],
        'counts': {
            'claim_links': len(claim_links),
            'memory_links': len(memory_links),
            'edge_links': len(edge_links),
            'conflict_links': len(conflict_links),
            'lifecycle_links': len(lifecycle_links),
            'claims_with_memory_links': sum(1 for item in claim_links if item.get('related_memory_node_ids')),
            'claims_with_edge_links': sum(1 for item in claim_links if item.get('related_memory_edge_ids')),
            'claims_with_conflicts': sum(1 for item in claim_links if item.get('related_conflict_ids')),
            'claims_with_lifecycle_links': sum(1 for item in claim_links if item.get('related_lifecycle_event_ids')),
            'memory_nodes_with_claims': sum(1 for item in memory_links if item.get('related_claim_node_ids')),
            'memory_nodes_with_edges': sum(1 for item in memory_links if item.get('related_edge_ids')),
            'memory_nodes_with_lifecycle': sum(1 for item in memory_links if item.get('related_lifecycle_event_ids')),
            'edges_with_claims': sum(1 for item in edge_links if item.get('related_claim_node_ids')),
            'edges_with_conflicts': sum(1 for item in edge_links if item.get('related_conflict_ids')),
            'edges_with_lifecycle': sum(1 for item in edge_links if item.get('related_lifecycle_event_ids')),
            'conflicts_with_claims': sum(1 for item in conflict_links if item.get('related_claim_node_ids')),
            'conflicts_with_edges': sum(1 for item in conflict_links if item.get('related_edge_ids')),
            'conflicts_with_lifecycle': sum(1 for item in conflict_links if item.get('related_lifecycle_event_ids')),
            'lifecycle_with_claims': sum(1 for item in lifecycle_links if item.get('related_claim_node_ids')),
            'lifecycle_with_evidence': sum(1 for item in lifecycle_links if item.get('related_evidence_node_ids')),
            'lifecycle_with_edges': sum(1 for item in lifecycle_links if item.get('related_edge_ids')),
            'lifecycle_with_conflicts': sum(1 for item in lifecycle_links if item.get('related_conflict_ids')),
            'conflicts_with_resolution_rationale': sum(1 for item in conflict_links if item.get('resolution_summary')),
            'conflicts_with_suggested_resolution': sum(1 for item in conflict_links if item.get('suggested_resolution')),
            'conflicts_with_history': sum(1 for item in conflict_links if int(item.get('history_count') or 0) > 0),
            'conflicts_with_merge_history': sum(1 for item in conflict_links if int(item.get('merge_history_count') or 0) > 0),
            'conflict_history_events': sum(int(item.get('history_count') or 0) for item in conflict_links),
        },
        'anchor_related': {
            'claim_node_ids': [item['claim_node_id'] for item in claim_links if item.get('trace_anchor_related')],
            'memory_node_ids': [item['memory_node_id'] for item in memory_links if item.get('trace_anchor_related')],
            'edge_ids': [item['edge_id'] for item in edge_links if item.get('trace_anchor_related')],
            'conflict_ids': [item['conflict_id'] for item in conflict_links if item.get('trace_anchor_related')],
            'lifecycle_event_ids': [item['event_id'] for item in lifecycle_links if item.get('trace_anchor_related')],
        },
    }

