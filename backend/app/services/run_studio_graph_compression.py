from __future__ import annotations

from typing import Any


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

_EDGE_PRIORITY = {
    'supports': 4,
    'published_from': 4,
    'derived_from': 3,
    'contradicts': 3,
    'supersedes': 3,
    'related_to': 1,
}

_STATUS_PRIORITY = {
    'published': 4,
    'active': 3,
    'draft': 2,
    'conflicted': 1,
    'quarantined': 0,
    'superseded': -1,
}


def _clean_text(value: Any) -> str:
    return str(value or '').strip()


def _clean_ids(values: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    if not isinstance(values, (list, tuple, set)):
        return out
    for value in values:
        clean = _clean_text(value)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
    return out


def _short_text(value: Any, max_len: int = 160) -> str | None:
    clean = ' '.join(str(value or '').split())
    if not clean:
        return None
    if len(clean) <= max_len:
        return clean
    return clean[:max_len - 3] + '...'


def _trust_rank(value: Any) -> int:
    return _TRUST_RANKS.get(_clean_text(value).lower(), 0)


def _status_rank(value: Any) -> int:
    return _STATUS_PRIORITY.get(_clean_text(value).lower(), 0)


def _edge_rank(edge_type: Any) -> int:
    return _EDGE_PRIORITY.get(_clean_text(edge_type).lower(), 0)


def _node_score(entry: dict[str, Any]) -> tuple[float, int, int, str]:
    confidence = float(entry.get('confidence') or 0.0)
    return (
        float(_status_rank(entry.get('status'))) + confidence,
        _trust_rank(entry.get('trust_tier')),
        int(entry.get('visible_projection_count') or 0) - int(entry.get('blocked_projection_count') or 0),
        _clean_text(entry.get('memory_node_id')),
    )


def _render_role_context(
    *,
    role_label: str,
    clusters: list[dict[str, Any]],
    memory_by_id: dict[str, dict[str, Any]],
    conflict_by_id: dict[str, dict[str, Any]],
    lifecycle_by_id: dict[str, dict[str, Any]],
) -> str:
    lines: list[str] = []
    lines.append(f"Role: {role_label}")

    core_claims: list[str] = []
    supports: list[str] = []
    tensions: list[str] = []
    decisions: list[str] = []

    for cluster in clusters[:4]:
        headline = _clean_text(cluster.get('headline')) or _clean_text(cluster.get('label'))
        if headline:
            core_claims.append(headline)
        for node_id in (cluster.get('support_frontier_node_ids') or [])[:2]:
            node = memory_by_id.get(node_id) or {}
            preview = _short_text(node.get('content_preview') or node.get('summary') or node_id, 96)
            if preview:
                supports.append(preview)
        for conflict_id in (cluster.get('conflict_frontier_ids') or [])[:2]:
            conflict = conflict_by_id.get(conflict_id) or {}
            summary = _short_text(conflict.get('resolution_summary') or conflict.get('reason') or conflict_id, 96)
            if summary:
                tensions.append(summary)
        for event_id in (cluster.get('decision_path_event_ids') or [])[:2]:
            event = lifecycle_by_id.get(event_id) or {}
            summary = _short_text(event.get('summary') or event.get('event_title') or event.get('event_type') or event_id, 96)
            if summary:
                decisions.append(summary)

    if core_claims:
        lines.append('[WORKING CLAIMS]')
        for item in core_claims[:3]:
            lines.append(f'- {item}')
    if supports:
        lines.append('[SUPPORT FRONTIER]')
        for item in supports[:4]:
            lines.append(f'- {item}')
    if tensions:
        lines.append('[OPEN TENSIONS]')
        for item in tensions[:3]:
            lines.append(f'- {item}')
    if decisions:
        lines.append('[DECISION PATH]')
        for item in decisions[:3]:
            lines.append(f'- {item}')

    return '\n'.join(lines)


def build_run_studio_graph_compression(
    *,
    evidence: dict[str, Any] | None,
    memory_graph: dict[str, Any] | None,
    trace_scope: dict[str, Any] | None,
    cross_references: dict[str, Any] | None,
    projection_retrieval: dict[str, Any] | None,
) -> dict[str, Any]:
    evidence_obj = evidence or {}
    memory_obj = memory_graph or {}
    trace_obj = trace_scope or {}
    cross_obj = cross_references or {}
    retrieval_obj = projection_retrieval or {}

    run_id = _clean_text(memory_obj.get('run_id') or trace_obj.get('run_id') or evidence_obj.get('run_id')) or None
    scope = _clean_text(memory_obj.get('scope') or trace_obj.get('scope') or 'thread') or 'thread'
    anchor_node_id = _clean_text(trace_obj.get('anchor_node_id')) or None

    memory_by_id: dict[str, dict[str, Any]] = {}
    surface_by_id: dict[str, set[str]] = {}
    for projection in memory_obj.get('projections') or []:
        for bucket, blocked in (('visible_nodes', False), ('blocked_nodes', True)):
            for node in projection.get(bucket) or []:
                node_id = _clean_text(node.get('node_id'))
                if not node_id:
                    continue
                entry = memory_by_id.setdefault(node_id, {
                    'memory_node_id': node_id,
                    'surface_id': _clean_text(node.get('surface_id')) or None,
                    'node_type': _clean_text(node.get('node_type')) or None,
                    'status': _clean_text(node.get('status')) or None,
                    'trust_tier': _clean_text(node.get('trust_tier')) or None,
                    'confidence': float(node.get('confidence') or 0.0),
                    'owner_role_id': _clean_text(node.get('owner_role_id')) or None,
                    'content_preview': _clean_text(node.get('content_preview')) or None,
                    'visible_projection_count': 0,
                    'blocked_projection_count': 0,
                    'projection_role_ids': [],
                })
                role_id = _clean_text(projection.get('role_id'))
                if role_id and role_id not in entry['projection_role_ids']:
                    entry['projection_role_ids'].append(role_id)
                if blocked:
                    entry['blocked_projection_count'] += 1
                else:
                    entry['visible_projection_count'] += 1
                surface_id = _clean_text(entry.get('surface_id'))
                if surface_id:
                    surface_by_id.setdefault(surface_id, set()).add(node_id)

    edge_by_id: dict[str, dict[str, Any]] = {}
    edges_by_node: dict[str, set[str]] = {}
    for edge in memory_obj.get('edges') or []:
        edge_id = _clean_text(edge.get('id'))
        if not edge_id:
            continue
        entry = {
            'edge_id': edge_id,
            'edge_type': _clean_text(edge.get('edge_type')) or None,
            'from_node_id': _clean_text(edge.get('from_node_id')) or None,
            'to_node_id': _clean_text(edge.get('to_node_id')) or None,
            'status': _clean_text(edge.get('status')) or None,
            'rationale': _clean_text(edge.get('rationale')) or None,
            'supporting_claim_node_ids': _clean_ids(edge.get('supporting_claim_node_ids') or []),
            'evidence_node_ids': _clean_ids(edge.get('evidence_node_ids') or []),
            'supporting_memory_node_ids': _clean_ids(edge.get('supporting_memory_node_ids') or []),
        }
        edge_by_id[edge_id] = entry
        for node_id in (entry['from_node_id'], entry['to_node_id']):
            if node_id:
                edges_by_node.setdefault(node_id, set()).add(edge_id)

    lifecycle_by_id: dict[str, dict[str, Any]] = {}
    lifecycle_by_node: dict[str, set[str]] = {}
    for event in memory_obj.get('lifecycle_events') or []:
        event_id = _clean_text(event.get('event_id') or event.get('id'))
        if not event_id:
            continue
        entry = {
            'event_id': event_id,
            'event_type': _clean_text(event.get('event_type')) or None,
            'event_title': _clean_text(event.get('event_title')) or None,
            'node_id': _clean_text(event.get('node_id')) or None,
            'surface_id': _clean_text(event.get('surface_id')) or None,
            'summary': _clean_text(event.get('summary')) or None,
            'created_at': _clean_text(event.get('created_at')) or None,
            'supporting_claim_node_ids': _clean_ids(event.get('supporting_claim_node_ids') or []),
            'supporting_evidence_node_ids': _clean_ids(event.get('supporting_evidence_node_ids') or []),
            'supporting_memory_node_ids': _clean_ids(event.get('supporting_memory_node_ids') or []),
        }
        lifecycle_by_id[event_id] = entry
        node_id = entry.get('node_id')
        if node_id:
            lifecycle_by_node.setdefault(node_id, set()).add(event_id)

    conflict_by_id: dict[str, dict[str, Any]] = {}
    conflicts_by_node: dict[str, set[str]] = {}
    unresolved_conflict_ids: list[str] = []
    for conflict in memory_obj.get('conflicts') or []:
        conflict_id = _clean_text(conflict.get('id'))
        if not conflict_id:
            continue
        node_ids = _clean_ids([
            conflict.get('left_node_id'),
            conflict.get('right_node_id'),
            conflict.get('winning_node_id'),
            *(conflict.get('losing_node_ids') or []),
        ])
        entry = {
            'conflict_id': conflict_id,
            'status': _clean_text(conflict.get('status')) or None,
            'reason': _clean_text(conflict.get('reason')) or None,
            'resolution_summary': _clean_text(conflict.get('resolution_summary')) or None,
            'node_ids': node_ids,
            'related_claim_node_ids': _clean_ids(conflict.get('supporting_claim_node_ids') or conflict.get('related_claim_node_ids') or []),
            'related_evidence_node_ids': _clean_ids(conflict.get('supporting_evidence_node_ids') or []),
            'related_memory_node_ids': _clean_ids(conflict.get('supporting_memory_node_ids') or []),
        }
        conflict_by_id[conflict_id] = entry
        if entry['status'] in {'pending', 'active', 'open'}:
            unresolved_conflict_ids.append(conflict_id)
        for node_id in node_ids:
            conflicts_by_node.setdefault(node_id, set()).add(conflict_id)

    claim_by_id: dict[str, dict[str, Any]] = {}
    claim_clusters: list[dict[str, Any]] = []
    covered_memory_node_ids: set[str] = set()

    for claim in cross_obj.get('claim_links') or []:
        claim_id = _clean_text(claim.get('claim_node_id'))
        if not claim_id:
            continue
        related_memory_node_ids = _clean_ids(claim.get('related_memory_node_ids') or [])
        related_edge_ids = _clean_ids(claim.get('related_memory_edge_ids') or [])
        related_conflict_ids = _clean_ids(claim.get('related_conflict_ids') or [])
        related_evidence_node_ids = _clean_ids(claim.get('related_evidence_node_ids') or [])
        related_lifecycle_event_ids = _clean_ids(claim.get('related_lifecycle_event_ids') or [])

        if not related_edge_ids:
            related_edge_ids = [
                edge_id for edge_id, edge_entry in edge_by_id.items()
                if claim_id in (edge_entry.get('supporting_claim_node_ids') or [])
            ]
        if not related_lifecycle_event_ids:
            related_lifecycle_event_ids = [
                event_id for event_id, event_entry in lifecycle_by_id.items()
                if claim_id in (event_entry.get('supporting_claim_node_ids') or [])
            ]
        if not related_conflict_ids:
            related_conflict_ids = [
                conflict_id for conflict_id, conflict_entry in conflict_by_id.items()
                if claim_id in (conflict_entry.get('related_claim_node_ids') or [])
            ]
        if not related_memory_node_ids:
            discovered_memory_node_ids: list[str] = []
            for edge_id in related_edge_ids:
                edge_entry = edge_by_id.get(edge_id) or {}
                discovered_memory_node_ids.extend([edge_entry.get('from_node_id'), edge_entry.get('to_node_id')])
                discovered_memory_node_ids.extend(edge_entry.get('supporting_memory_node_ids') or [])
            for event_id in related_lifecycle_event_ids:
                event_entry = lifecycle_by_id.get(event_id) or {}
                discovered_memory_node_ids.extend([event_entry.get('node_id')])
                discovered_memory_node_ids.extend(event_entry.get('supporting_memory_node_ids') or [])
            for conflict_id in related_conflict_ids:
                conflict_entry = conflict_by_id.get(conflict_id) or {}
                discovered_memory_node_ids.extend(conflict_entry.get('node_ids') or [])
                discovered_memory_node_ids.extend(conflict_entry.get('related_memory_node_ids') or [])
            related_memory_node_ids = _clean_ids(discovered_memory_node_ids)

        memory_candidates = [memory_by_id[node_id] for node_id in related_memory_node_ids if node_id in memory_by_id]
        memory_candidates.sort(key=_node_score, reverse=True)
        representative_memory_node_ids = [entry['memory_node_id'] for entry in memory_candidates[:3]]
        support_frontier_node_ids = [entry['memory_node_id'] for entry in memory_candidates if _status_rank(entry.get('status')) >= 2][:3] or representative_memory_node_ids[:2]

        edge_candidates = [edge_by_id[edge_id] for edge_id in related_edge_ids if edge_id in edge_by_id]
        edge_candidates.sort(key=lambda item: (_edge_rank(item.get('edge_type')), _clean_text(item.get('edge_id'))), reverse=True)
        representative_edge_ids = [entry['edge_id'] for entry in edge_candidates[:3]]

        lifecycle_candidates = [lifecycle_by_id[event_id] for event_id in related_lifecycle_event_ids if event_id in lifecycle_by_id]
        if not lifecycle_candidates:
            discovered: set[str] = set()
            for node_id in related_memory_node_ids:
                discovered.update(lifecycle_by_node.get(node_id) or set())
            lifecycle_candidates = [lifecycle_by_id[event_id] for event_id in discovered if event_id in lifecycle_by_id]
        lifecycle_candidates.sort(key=lambda item: (_clean_text(item.get('created_at')), _clean_text(item.get('event_id'))), reverse=True)
        decision_path_event_ids = [entry['event_id'] for entry in lifecycle_candidates[:3]]

        conflict_candidates = [conflict_by_id[conflict_id] for conflict_id in related_conflict_ids if conflict_id in conflict_by_id]
        if not conflict_candidates:
            discovered_conflicts: set[str] = set()
            for node_id in related_memory_node_ids:
                discovered_conflicts.update(conflicts_by_node.get(node_id) or set())
            conflict_candidates = [conflict_by_id[conflict_id] for conflict_id in discovered_conflicts if conflict_id in conflict_by_id]
        conflict_candidates.sort(key=lambda item: (item.get('status') in {'pending', 'active', 'open'}, _clean_text(item.get('conflict_id'))), reverse=True)
        conflict_frontier_ids = [entry['conflict_id'] for entry in conflict_candidates[:3]]

        related_role_ids: list[str] = []
        seen_roles: set[str] = set()
        for node_id in related_memory_node_ids:
            for role_id in (memory_by_id.get(node_id, {}).get('projection_role_ids') or []):
                if role_id not in seen_roles:
                    seen_roles.add(role_id)
                    related_role_ids.append(role_id)
        status = 'stable'
        if any((conflict_by_id.get(conflict_id) or {}).get('status') in {'pending', 'active', 'open'} for conflict_id in conflict_frontier_ids):
            status = 'contested'
        elif any((memory_by_id.get(node_id) or {}).get('status') in {'conflicted', 'quarantined'} for node_id in related_memory_node_ids):
            status = 'unstable'
        headline = _short_text(claim.get('claim_text') or claim_id, 140) or claim_id
        representative_evidence_node_ids = related_evidence_node_ids[:3]
        cluster = {
            'cluster_id': f'claim::{claim_id}',
            'cluster_type': 'claim_neighborhood',
            'label': headline,
            'headline': headline,
            'status': status,
            'claim_node_ids': [claim_id],
            'evidence_node_ids': representative_evidence_node_ids,
            'memory_node_ids': related_memory_node_ids,
            'edge_ids': related_edge_ids,
            'lifecycle_event_ids': [entry['event_id'] for entry in lifecycle_candidates],
            'conflict_ids': [entry['conflict_id'] for entry in conflict_candidates],
            'role_ids': related_role_ids,
            'surface_ids': sorted({_clean_text(memory_by_id.get(node_id, {}).get('surface_id')) for node_id in related_memory_node_ids if _clean_text(memory_by_id.get(node_id, {}).get('surface_id'))}),
            'representative_claim_node_ids': [claim_id],
            'representative_evidence_node_ids': representative_evidence_node_ids,
            'representative_memory_node_ids': representative_memory_node_ids,
            'representative_edge_ids': representative_edge_ids,
            'representative_lifecycle_event_ids': decision_path_event_ids,
            'support_frontier_node_ids': support_frontier_node_ids,
            'conflict_frontier_ids': conflict_frontier_ids,
            'decision_path_event_ids': decision_path_event_ids,
            'omitted_memory_node_ids': [node_id for node_id in related_memory_node_ids if node_id not in representative_memory_node_ids],
            'rendered_summary': _short_text(
                '; '.join(filter(None, [
                    headline,
                    f"supports: {', '.join((_short_text(memory_by_id.get(node_id, {}).get('content_preview') or node_id, 48) or node_id) for node_id in support_frontier_node_ids[:2])}" if support_frontier_node_ids else '',
                    f"open tensions: {len(conflict_frontier_ids)}" if conflict_frontier_ids else '',
                ])),
                220,
            ),
            'reexpand_handles': {
                'claim_node_ids': [claim_id],
                'evidence_node_ids': related_evidence_node_ids,
                'memory_node_ids': related_memory_node_ids,
                'edge_ids': related_edge_ids,
                'lifecycle_event_ids': [entry['event_id'] for entry in lifecycle_candidates],
                'conflict_ids': [entry['conflict_id'] for entry in conflict_candidates],
                'trace_anchor_related': bool(claim.get('trace_anchor_related')),
            },
        }
        claim_by_id[claim_id] = cluster
        claim_clusters.append(cluster)
        covered_memory_node_ids.update(related_memory_node_ids)

    memory_clusters: list[dict[str, Any]] = []
    unclaimed_by_surface: dict[tuple[str, str], list[str]] = {}
    for node_id, node in memory_by_id.items():
        if node_id in covered_memory_node_ids:
            continue
        surface_id = _clean_text(node.get('surface_id')) or 'memory'
        owner_role_id = _clean_text(node.get('owner_role_id')) or 'shared'
        unclaimed_by_surface.setdefault((surface_id, owner_role_id), []).append(node_id)

    for (surface_id, owner_role_id), node_ids in sorted(unclaimed_by_surface.items()):
        node_entries = [memory_by_id[node_id] for node_id in node_ids if node_id in memory_by_id]
        node_entries.sort(key=_node_score, reverse=True)
        representative_memory_node_ids = [entry['memory_node_id'] for entry in node_entries[:3]]
        support_frontier_node_ids = [entry['memory_node_id'] for entry in node_entries if _status_rank(entry.get('status')) >= 2][:3] or representative_memory_node_ids[:2]
        discovered_edges: set[str] = set()
        discovered_conflicts: set[str] = set()
        discovered_lifecycle: set[str] = set()
        related_role_ids: set[str] = set()
        for node_id in node_ids:
            discovered_edges.update(edges_by_node.get(node_id) or set())
            discovered_conflicts.update(conflicts_by_node.get(node_id) or set())
            discovered_lifecycle.update(lifecycle_by_node.get(node_id) or set())
            for role_id in (memory_by_id.get(node_id, {}).get('projection_role_ids') or []):
                if role_id:
                    related_role_ids.add(role_id)
        edge_candidates = [edge_by_id[edge_id] for edge_id in discovered_edges if edge_id in edge_by_id]
        edge_candidates.sort(key=lambda item: (_edge_rank(item.get('edge_type')), _clean_text(item.get('edge_id'))), reverse=True)
        lifecycle_candidates = [lifecycle_by_id[event_id] for event_id in discovered_lifecycle if event_id in lifecycle_by_id]
        lifecycle_candidates.sort(key=lambda item: (_clean_text(item.get('created_at')), _clean_text(item.get('event_id'))), reverse=True)
        conflict_candidates = [conflict_by_id[conflict_id] for conflict_id in discovered_conflicts if conflict_id in conflict_by_id]
        conflict_candidates.sort(key=lambda item: (item.get('status') in {'pending', 'active', 'open'}, _clean_text(item.get('conflict_id'))), reverse=True)
        label = f'{surface_id} / {owner_role_id}'
        memory_clusters.append({
            'cluster_id': f'surface::{surface_id}::{owner_role_id}',
            'cluster_type': 'surface_remainder',
            'label': label,
            'headline': f'{surface_id} memory for {owner_role_id}',
            'status': 'contested' if any(item.get('status') in {'pending', 'active', 'open'} for item in conflict_candidates) else 'stable',
            'claim_node_ids': [],
            'evidence_node_ids': [],
            'memory_node_ids': node_ids,
            'edge_ids': [entry['edge_id'] for entry in edge_candidates],
            'lifecycle_event_ids': [entry['event_id'] for entry in lifecycle_candidates],
            'conflict_ids': [entry['conflict_id'] for entry in conflict_candidates],
            'role_ids': sorted(related_role_ids),
            'surface_ids': [surface_id],
            'representative_claim_node_ids': [],
            'representative_evidence_node_ids': [],
            'representative_memory_node_ids': representative_memory_node_ids,
            'representative_edge_ids': [entry['edge_id'] for entry in edge_candidates[:3]],
            'representative_lifecycle_event_ids': [entry['event_id'] for entry in lifecycle_candidates[:3]],
            'support_frontier_node_ids': support_frontier_node_ids,
            'conflict_frontier_ids': [entry['conflict_id'] for entry in conflict_candidates[:3]],
            'decision_path_event_ids': [entry['event_id'] for entry in lifecycle_candidates[:3]],
            'omitted_memory_node_ids': [node_id for node_id in node_ids if node_id not in representative_memory_node_ids],
            'rendered_summary': _short_text(
                f"{label}: {len(node_ids)} nodes, focus on {', '.join((_short_text(memory_by_id.get(node_id, {}).get('content_preview') or node_id, 48) or node_id) for node_id in representative_memory_node_ids[:2])}",
                220,
            ),
            'reexpand_handles': {
                'claim_node_ids': [],
                'evidence_node_ids': [],
                'memory_node_ids': node_ids,
                'edge_ids': [entry['edge_id'] for entry in edge_candidates],
                'lifecycle_event_ids': [entry['event_id'] for entry in lifecycle_candidates],
                'conflict_ids': [entry['conflict_id'] for entry in conflict_candidates],
                'trace_anchor_related': anchor_node_id in node_ids,
            },
        })

    clusters = claim_clusters + memory_clusters
    cluster_lookup = {cluster['cluster_id']: cluster for cluster in clusters}

    role_status_by_id: dict[str, dict[str, Any]] = {}
    for item in retrieval_obj.get('items') or []:
        role_id = _clean_text(item.get('role_id'))
        if role_id:
            role_status_by_id[role_id] = item
    for item in retrieval_obj.get('planner_system_paths') or []:
        role_id = _clean_text(item.get('role_id'))
        if role_id and role_id not in role_status_by_id:
            role_status_by_id[role_id] = item

    role_views: list[dict[str, Any]] = []
    role_cluster_counts: dict[str, int] = {}
    projection_items = memory_obj.get('projections') or []
    if projection_items:
        for projection in projection_items:
            role_id = _clean_text(projection.get('role_id')) or 'unknown'
            status_entry = role_status_by_id.get(role_id) or {}
            visible_ids = set(_clean_ids(projection.get('visible_node_ids') or []))
            blocked_ids = set(_clean_ids(projection.get('blocked_node_ids') or []))
            visible_clusters = [
                cluster for cluster in clusters
                if visible_ids.intersection(cluster.get('memory_node_ids') or [])
            ]
            blocked_clusters = [
                cluster for cluster in clusters
                if blocked_ids.intersection(cluster.get('memory_node_ids') or []) and cluster not in visible_clusters
            ]
            role_cluster_counts[role_id] = len(visible_clusters)
            core_claim_node_ids = _clean_ids([claim_id for cluster in visible_clusters for claim_id in (cluster.get('claim_node_ids') or [])])
            support_frontier_node_ids = _clean_ids([node_id for cluster in visible_clusters for node_id in (cluster.get('support_frontier_node_ids') or []) if node_id in visible_ids])
            conflict_frontier_ids = _clean_ids([conflict_id for cluster in (visible_clusters + blocked_clusters) for conflict_id in (cluster.get('conflict_frontier_ids') or [])])
            decision_path_event_ids = _clean_ids([event_id for cluster in visible_clusters for event_id in (cluster.get('decision_path_event_ids') or [])])
            rendered_context = _render_role_context(
                role_label=_clean_text(status_entry.get('display_label') or role_id or 'runtime role'),
                clusters=visible_clusters,
                memory_by_id=memory_by_id,
                conflict_by_id=conflict_by_id,
                lifecycle_by_id=lifecycle_by_id,
            ) if visible_clusters else None
            role_views.append({
                'role_id': role_id,
                'display_label': _clean_text(status_entry.get('display_label') or role_id) or role_id,
                'projection_id': _clean_text(projection.get('projection_id')) or None,
                'status': _clean_text(status_entry.get('status') or ('blocked_only' if blocked_clusters and not visible_clusters else 'visible_non_authoritative')) or None,
                'visible_cluster_ids': [cluster['cluster_id'] for cluster in visible_clusters],
                'blocked_cluster_ids': [cluster['cluster_id'] for cluster in blocked_clusters],
                'core_claim_node_ids': core_claim_node_ids,
                'support_frontier_node_ids': support_frontier_node_ids,
                'conflict_frontier_ids': conflict_frontier_ids,
                'decision_path_event_ids': decision_path_event_ids,
                'rendered_context': rendered_context,
                'reexpand_handles': {
                    'memory_node_ids': _clean_ids(list(visible_ids | blocked_ids)),
                    'cluster_ids': [cluster['cluster_id'] for cluster in visible_clusters + blocked_clusters],
                },
            })

    role_views.sort(key=lambda item: (_clean_text(item.get('display_label')) or _clean_text(item.get('role_id')), _clean_text(item.get('role_id'))))
    cluster_count_by_type: dict[str, int] = {}
    for cluster in clusters:
        key = _clean_text(cluster.get('cluster_type')) or 'cluster'
        cluster_count_by_type[key] = cluster_count_by_type.get(key, 0) + 1

    omitted_clusters = [
        {
            'cluster_id': cluster['cluster_id'],
            'cluster_type': cluster.get('cluster_type'),
            'reason': 'not_visible_to_current_projection',
            'memory_node_count': len(cluster.get('memory_node_ids') or []),
        }
        for cluster in clusters
        if not cluster.get('role_ids') and cluster.get('cluster_type') == 'surface_remainder'
    ]

    return {
        'run_id': run_id,
        'scope': scope,
        'anchor_node_id': anchor_node_id,
        'summary': {
            'compression_mode': 'graph_native',
            'cluster_count': len(clusters),
            'role_view_count': len(role_views),
            'core_claim_count': len(claim_clusters),
            'support_frontier_count': len(_clean_ids([node_id for cluster in clusters for node_id in (cluster.get('support_frontier_node_ids') or [])])),
            'conflict_frontier_count': len(_clean_ids([conflict_id for cluster in clusters for conflict_id in (cluster.get('conflict_frontier_ids') or [])])),
            'decision_path_count': len(_clean_ids([event_id for cluster in clusters for event_id in (cluster.get('decision_path_event_ids') or [])])),
            'omitted_cluster_count': len(omitted_clusters),
            'unresolved_conflict_count': len(unresolved_conflict_ids),
            'compression_note': 'Graph-native compression keeps claim neighborhoods, support frontier, conflict frontier, and re-expand handles instead of collapsing to a single linear summary.',
        },
        'counts': {
            'clusters': len(clusters),
            'role_views': len(role_views),
            'claim_clusters': len(claim_clusters),
            'surface_remainder_clusters': len(memory_clusters),
            'unresolved_conflicts': len(unresolved_conflict_ids),
            'anchor_related_clusters': sum(1 for cluster in clusters if bool(cluster.get('reexpand_handles', {}).get('trace_anchor_related'))),
            **{f'cluster_type::{key}': value for key, value in cluster_count_by_type.items()},
            **{f'role_visible_clusters::{role_id}': value for role_id, value in role_cluster_counts.items()},
        },
        'clusters': clusters,
        'role_views': role_views,
        'omitted_clusters': omitted_clusters,
    }
