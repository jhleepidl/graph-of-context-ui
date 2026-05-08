from __future__ import annotations

import copy
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import ContextSet, Edge, MemoryConflict, MemoryEdge, MemoryLifecycleEvent, MemoryNode, MemoryProjection, MemoryTopologySnapshot, MemoryTopologyEvent, MemoryDemandEvent, Node, TeamSelectionEvent, Thread
from app.services.conversation_team import build_conversation_team_projection
from app.services.context_decisions import build_context_decisions
from app.services.graph import compile_active_context_explain, load_thread_graph
from app.services.graph_projections import build_logical_projections
from app.services.resolved_runtime import resolve_runtime_projection, resolve_runtime_scope_state
from app.services.runtime_scope import filter_nodes_for_run
from app.services.runtime_snapshot import (
    created_sort_key as _created_sort_key,
    extract_runtime_team_snapshot as _extract_runtime_team_snapshot,
    node_payload as _node_payload,
    normalize_status as _normalize_status,
)
from app.services.run_skill_summary import (
    build_thread_context_pack_summary,
    build_thread_skill_usage_summary,
)
from app.services.memory_graph import summarize_memory_conflicts, summarize_memory_edge, summarize_memory_lifecycle_event
from app.services.memory_topology import build_run_studio_memory_topology
from app.services.memory_demand import build_run_studio_memory_demand
from app.services.run_studio_cross_references import build_run_bundle_cross_references as _build_run_bundle_cross_references_impl
from app.services.run_studio_audit_timeline import build_run_studio_audit_timeline_impl
from app.services.run_studio_graph_compression import build_run_studio_graph_compression
from app.services.context_cache import build_cache_key, get_global_context_cache
from app.services.harness_spec import get_thread_harness_spec, build_harness_summary
from app.services.harness_package import RUN_SYNC_SCHEMA_VERSION, RUN_TRACE_SCHEMA_VERSION, build_harness_package_payload
from app.services.runtime_scope import build_step_run_id_index
from app.services.team_recommender import build_team_selection_dataset


CLAIM_NODE_TYPES = {"Decision", "Assumption", "Plan", "Observation", "ContextSummary"}


RUN_BUNDLE_CACHE_VERSION = "v2"
PROJECTION_RETRIEVAL_CACHE_VERSION = "v1"
CROSS_REFERENCE_CACHE_VERSION = "v1"
AUDIT_TIMELINE_CACHE_VERSION = "v2"
GRAPH_COMPRESSION_CACHE_VERSION = "v1"


def _context_cache_versions() -> dict[str, str]:
    return {
        'run_bundle': RUN_BUNDLE_CACHE_VERSION,
        'projection_retrieval': PROJECTION_RETRIEVAL_CACHE_VERSION,
        'cross_references': CROSS_REFERENCE_CACHE_VERSION,
        'audit_timeline': AUDIT_TIMELINE_CACHE_VERSION,
        'graph_compression': GRAPH_COMPRESSION_CACHE_VERSION,
    }


def _query_version_stats(session: Session, model: Any, field: Any, *, thread_id: str) -> dict[str, Any]:
    latest, count = session.exec(
        select(func.max(field), func.count()).where(model.thread_id == thread_id)
    ).one()
    return {
        'latest_at': _iso_or_none(latest),
        'count': int(count or 0),
    }


def _build_graph_version_payload(session: Session, *, thread: Thread, context_set: ContextSet | None) -> dict[str, Any]:
    harness_spec = get_thread_harness_spec(thread)
    harness_summary = build_harness_summary(harness_spec)
    payload = {
        'thread_id': thread.id,
        'context_set_id': getattr(context_set, 'id', None),
        'context_set_version': int(getattr(context_set, 'version', 0) or 0),
        'context_set_updated_at': _iso_or_none(getattr(context_set, 'updated_at', None)),
        'harness_spec_hash': harness_summary.get('spec_hash'),
        'harness_spec_updated_at': harness_summary.get('updated_at'),
        'tables': {
            'nodes': _query_version_stats(session, Node, Node.created_at, thread_id=thread.id),
            'edges': _query_version_stats(session, Edge, Edge.created_at, thread_id=thread.id),
            'memory_nodes': _query_version_stats(session, MemoryNode, MemoryNode.updated_at, thread_id=thread.id),
            'memory_topology_snapshots': _query_version_stats(session, MemoryTopologySnapshot, MemoryTopologySnapshot.updated_at, thread_id=thread.id),
            'memory_topology_events': _query_version_stats(session, MemoryTopologyEvent, MemoryTopologyEvent.created_at, thread_id=thread.id),
            'memory_demand_events': _query_version_stats(session, MemoryDemandEvent, MemoryDemandEvent.created_at, thread_id=thread.id),
            'memory_edges': _query_version_stats(session, MemoryEdge, MemoryEdge.updated_at, thread_id=thread.id),
            'memory_conflicts': _query_version_stats(session, MemoryConflict, MemoryConflict.updated_at, thread_id=thread.id),
            'memory_lifecycle_events': _query_version_stats(session, MemoryLifecycleEvent, MemoryLifecycleEvent.created_at, thread_id=thread.id),
            'memory_projections': _query_version_stats(session, MemoryProjection, MemoryProjection.created_at, thread_id=thread.id),
            'team_selection_events': _query_version_stats(session, TeamSelectionEvent, TeamSelectionEvent.created_at, thread_id=thread.id),
        },
    }
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode('utf-8')).hexdigest()[:16]
    payload['graph_version'] = digest
    return payload


def _cached_artifact(cache: Any, *, namespace: str, payload: dict[str, Any], build_fn: Any) -> tuple[Any, bool, str]:
    key = build_cache_key(namespace, payload)
    cached = cache.get(key)
    if cached is not None:
        return cached, True, key
    value = build_fn()
    cache.set(key, value)
    return value, False, key
EVIDENCE_EDGE_TYPES = {"SUPPORTS", "REFERENCES", "DEPENDS"}
CONFLICT_EDGE_TYPES = {"CONFLICTS", "CONTRADICTS"}


def _jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def _short_text(value: str, max_len: int = 220) -> str:
    compact = " ".join(str(value or "").split())
    if len(compact) <= max_len:
        return compact
    return f"{compact[:max_len]}..."


def _iso_or_none(value: Any) -> str | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    clean = str(value or '').strip()
    return clean or None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    clean = str(value or '').strip()
    if not clean:
        return None
    try:
        if clean.endswith('Z'):
            clean = clean[:-1] + '+00:00'
        parsed = datetime.fromisoformat(clean)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _timeline_event_sort_key(item: dict[str, Any]) -> tuple[float, str, str]:
    parsed = _parse_datetime(item.get('timestamp'))
    ts = parsed.timestamp() if parsed else 0.0
    return (ts, str(item.get('category') or ''), str(item.get('event_id') or ''))


def _push_timeline_event(items: list[dict[str, Any]], seen: set[str], event: dict[str, Any]) -> None:
    event_id = str(event.get('event_id') or '').strip()
    if not event_id or event_id in seen:
        return
    seen.add(event_id)
    items.append(event)

def _clean_text(value: Any) -> str | None:
    clean = str(value or '').strip()
    return clean or None


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
    return bool(value)


def _count_entries(value: Any) -> int:
    if isinstance(value, (list, tuple, set)):
        return len(value)
    if value is None:
        return 0
    return 1


def _graph_or_load(
    session: Session,
    *,
    thread_id: str,
    nodes: list[Node] | None = None,
    edges: list[Edge] | None = None,
) -> tuple[list[Node], list[Edge]]:
    if nodes is not None and edges is not None:
        return nodes, edges
    loaded_nodes, loaded_edges = load_thread_graph(session, thread_id)
    return loaded_nodes, loaded_edges


def _resolve_context_set(
    session: Session,
    *,
    thread_id: str,
    context_set_id: str | None,
) -> ContextSet | None:
    requested = (context_set_id or "").strip()
    if requested:
        cs = session.get(ContextSet, requested)
        if not cs or cs.thread_id != thread_id:
            raise ValueError("context set not found in thread")
        return cs
    return session.exec(
        select(ContextSet)
        .where(ContextSet.thread_id == thread_id)
        .order_by(ContextSet.created_at.asc())
        .limit(1)
    ).first()


def _active_ids(context_set: ContextSet | None) -> list[str]:
    if not context_set:
        return []
    raw = _jload(context_set.active_node_ids_json, [])
    if not isinstance(raw, list):
        return []
    return [str(nid).strip() for nid in raw if isinstance(nid, str) and str(nid).strip()]


def _latest_user_message(nodes: list[Node]) -> Node | None:
    messages = [node for node in nodes if node.type == "Message"]
    messages.sort(key=_created_sort_key)
    for node in reversed(messages):
        payload = _node_payload(node)
        if str(payload.get("role") or "").strip().lower() == "user":
            return node
    return messages[-1] if messages else None


def _current_run_scope(nodes: list[Node], edges: list[Edge]) -> dict[str, Any]:
    return resolve_runtime_scope_state(nodes=nodes, edges=edges).scope


def _current_step(steps: list[Node]) -> tuple[Node | None, str]:
    ordered_steps = sorted([node for node in steps if node.type == "Step"], key=_created_sort_key)
    running = [step for step in ordered_steps if _normalize_status(_node_payload(step).get("status")) == "running"]
    if running:
        return running[-1], "running"
    queued = [step for step in ordered_steps if _normalize_status(_node_payload(step).get("status")) == "queued"]
    if queued:
        return queued[-1], "queued"
    if ordered_steps:
        return ordered_steps[-1], _normalize_status(_node_payload(ordered_steps[-1]).get("status"))
    return None, "idle"


def _now_panel_summary(
    *,
    thread: Thread,
    nodes: list[Node],
    edges: list[Edge],
    active_ids: list[str],
) -> dict[str, Any]:
    run_scope = _current_run_scope(nodes, edges)
    current_run_node = run_scope.get("current_run_node")
    current_run_payload = _node_payload(current_run_node)
    current_steps = run_scope.get("current_run_steps") or []
    current_step_node, current_step_status = _current_step(current_steps)
    current_step_payload = _node_payload(current_step_node)
    latest_user = _latest_user_message(nodes)
    latest_user_payload = _node_payload(latest_user)
    run_nodes = [node for node in nodes if node.type == "Run"]
    run_nodes.sort(key=_created_sort_key)
    latest_run = run_nodes[-1] if run_nodes else None
    latest_run_payload = _node_payload(latest_run)
    step_run_id_by_step_id = run_scope.get("step_run_id_by_step_id", {})
    current_candidate_key = str(run_scope.get("current_candidate_key") or "")
    current_run_id = run_scope.get("current_run_id")

    pending_approval_nodes: list[Node] = []
    current_pending_approval_nodes: list[Node] = []
    for node in nodes:
        payload = _node_payload(node)
        if payload.get("pending_approval") is not True and payload.get("requires_approval") is not True:
            continue
        pending_approval_nodes.append(node)

        node_candidate_key = ""
        if node.type == "Run":
            node_candidate_key = str(node.id)
        elif node.type == "Step":
            node_candidate_key = str(step_run_id_by_step_id.get(node.id) or "__unscoped__")
        else:
            node_run_id = str(payload.get("run_id") or "").strip()
            if node_run_id:
                node_candidate_key = node_run_id

        if current_candidate_key and node_candidate_key == current_candidate_key:
            current_pending_approval_nodes.append(node)
    pending_approval_nodes.sort(key=_created_sort_key)
    current_pending_approval_nodes.sort(key=_created_sort_key)

    blocked_nodes: list[Node] = []
    current_blocked_nodes: list[Node] = []
    for node in nodes:
        if node.type != "Step":
            continue
        payload = _node_payload(node)
        status = _normalize_status(payload.get("status"))
        if status not in {"error", "blocked"} and not str(payload.get("blocked_reason") or "").strip():
            continue
        blocked_nodes.append(node)

        step_candidate_key = str(step_run_id_by_step_id.get(node.id) or "__unscoped__")
        if current_candidate_key and step_candidate_key == current_candidate_key:
            current_blocked_nodes.append(node)
    blocked_nodes.sort(key=_created_sort_key)
    current_blocked_nodes.sort(key=_created_sort_key)
    latest_blocked = blocked_nodes[-1] if blocked_nodes else None
    latest_blocked_payload = _node_payload(latest_blocked)
    latest_current_blocked = current_blocked_nodes[-1] if current_blocked_nodes else None
    latest_current_blocked_payload = _node_payload(latest_current_blocked)

    global_step_status_counts = run_scope.get("global_step_status_counts") or {}
    current_run_step_status_counts = run_scope.get("current_run_step_status_counts") or {}
    run_status = str(run_scope.get("current_run_status") or "idle")

    current_task = str(
        latest_user.text
        if latest_user and latest_user.text
        else current_run_payload.get("task")
        or current_run_payload.get("goal")
        or latest_run_payload.get("task")
        or latest_run_payload.get("goal")
        or thread.title
        or ""
    ).strip()
    current_objective = str(
        current_step_payload.get("goal")
        or current_step_payload.get("title")
        or current_run_payload.get("goal")
        or current_run_payload.get("task")
        or latest_run_payload.get("goal")
        or (latest_user.text if latest_user else "")
        or ""
    ).strip()
    current_step = str(
        current_step_payload.get("title")
        or current_step_payload.get("goal")
        or current_step_node.text
        or ""
    ).strip() if current_step_node else ""

    return {
        "task": {
            "current_task": current_task or None,
            "current_objective": current_objective or None,
            "current_step": current_step or None,
            "current_step_id": current_step_node.id if current_step_node else None,
            "current_step_status": current_step_status,
            "latest_user_message_id": latest_user.id if latest_user else None,
            "latest_user_message_text": _short_text(latest_user.text or "", 280) if latest_user else None,
            "latest_user_message_role": str(latest_user_payload.get("role") or "").strip() if latest_user else None,
        },
        "state": {
            "run_status": run_status,
            "blocked": bool(latest_blocked),
            "blocked_reason": str(
                latest_blocked_payload.get("blocked_reason")
                or latest_blocked_payload.get("error")
                or latest_blocked_payload.get("error_message")
                or ""
            ).strip()
            if latest_blocked
            else "",
            "current_blocked": bool(latest_current_blocked),
            "current_blocked_reason": str(
                latest_current_blocked_payload.get("blocked_reason")
                or latest_current_blocked_payload.get("error")
                or latest_current_blocked_payload.get("error_message")
                or ""
            ).strip()
            if latest_current_blocked
            else "",
            "pending_approval": len(pending_approval_nodes) > 0,
            "pending_approval_count": len(pending_approval_nodes),
            "current_pending_approval": len(current_pending_approval_nodes) > 0,
            "current_pending_approval_count": len(current_pending_approval_nodes),
            "active_context_count": len(active_ids),
            "step_status_counts": global_step_status_counts,
            "current_run_step_status_counts": current_run_step_status_counts,
            "current_run_id": current_run_id,
            "current_run_status": run_status,
            "current_run_inactive": bool(run_scope.get("current_run_inactive")),
            "current_run_selection_source": run_scope.get("current_run_selection_source"),
            "current_run_step_count": len(current_steps),
            "stale_queued_step_count": int(run_scope.get("stale_queued_step_count") or 0),
        },
        "pending_approval_items": [
            {
                "id": node.id,
                "type": node.type,
                "text": _short_text(node.text or ""),
                "created_at": node.created_at,
            }
            for node in pending_approval_nodes[-10:]
        ],
        "current_pending_approval_items": [
            {
                "id": node.id,
                "type": node.type,
                "text": _short_text(node.text or ""),
                "created_at": node.created_at,
            }
            for node in current_pending_approval_nodes[-10:]
        ],
        "latest_run": {
            "id": latest_run.id if latest_run else None,
            "created_at": latest_run.created_at if latest_run else None,
            "summary": _short_text(latest_run.text or str(latest_run_payload.get("summary") or ""), 280) if latest_run else None,
        },
        "current_run": {
            "id": current_run_id,
            "node_id": current_run_node.id if current_run_node else None,
            "created_at": current_run_node.created_at if current_run_node else None,
            "status": run_status,
            "inactive": bool(run_scope.get("current_run_inactive")),
            "selection_source": run_scope.get("current_run_selection_source"),
            "step_count": len(current_steps),
            "stale_queued_step_count": int(run_scope.get("stale_queued_step_count") or 0),
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _agent_team_summary(
    session: Session,
    *,
    thread_id: str,
    nodes: list[Node],
) -> dict[str, Any]:
    return build_conversation_team_projection(session, thread_id=thread_id, nodes=nodes)


def _context_decisions_summary(
    session: Session,
    *,
    thread_id: str,
    context_set: ContextSet | None,
    nodes: list[Node],
    edges: list[Edge],
) -> dict[str, Any]:
    if not context_set:
        return {
            "context_set_id": None,
            "context_set_name": None,
            "selected": [],
            "pinned": [],
            "excluded": [],
            "missing": [],
            "conflicting": [],
            "compiled_kept_node_ids": [],
            "counts": {
                "selected": 0,
                "pinned": 0,
                "excluded": 0,
                "missing": 0,
                "conflicting": 0,
            },
        }
    active_ids = _active_ids(context_set)
    compiled = compile_active_context_explain(session, thread_id, active_ids)
    explain = compiled.get("explain", {}) if isinstance(compiled, dict) else {}
    return build_context_decisions(
        context_set=context_set,
        nodes=nodes,
        edges=edges,
        compiled_explain=explain if isinstance(explain, dict) else {},
    )




def _scope_graph_for_run(
    *,
    nodes: list[Node],
    edges: list[Edge],
    run_id: str | None,
) -> tuple[list[Node], list[Edge]]:
    clean_run_id = str(run_id or "").strip()
    if not clean_run_id:
        return nodes, edges

    scoped_nodes = filter_nodes_for_run(nodes, edges, run_id=clean_run_id)
    scoped_ids = {str(getattr(node, "id", "") or "") for node in scoped_nodes if str(getattr(node, "id", "") or "")}
    if not scoped_ids:
        return [], []

    relation_edge_types = EVIDENCE_EDGE_TYPES | CONFLICT_EDGE_TYPES
    for edge in edges:
        if edge.type not in relation_edge_types:
            continue
        if edge.from_id in scoped_ids and edge.to_id:
            scoped_ids.add(edge.to_id)
        if edge.to_id in scoped_ids and edge.from_id:
            scoped_ids.add(edge.from_id)

    filtered_nodes = [node for node in nodes if str(getattr(node, "id", "") or "") in scoped_ids]
    filtered_edges = [
        edge
        for edge in edges
        if str(getattr(edge, "from_id", "") or "") in scoped_ids and str(getattr(edge, "to_id", "") or "") in scoped_ids
    ]
    return filtered_nodes, filtered_edges

def _evidence_summary(
    *,
    nodes: list[Node],
    edges: list[Edge],
    active_ids: list[str],
) -> dict[str, Any]:
    nodes_by_id = {node.id: node for node in nodes}
    active_set = set(active_ids)
    payload_by_id = {node.id: _node_payload(node) for node in nodes}
    incoming_edges: dict[str, list[Edge]] = {}
    outgoing_edges: dict[str, list[Edge]] = {}
    for edge in edges:
        incoming_edges.setdefault(edge.to_id, []).append(edge)
        outgoing_edges.setdefault(edge.from_id, []).append(edge)

    candidate_claim_nodes = [
        node
        for node in nodes
        if node.type in CLAIM_NODE_TYPES or (node.type == "Message" and str(payload_by_id.get(node.id, {}).get("role") or "").strip() == "assistant")
    ]
    candidate_claim_nodes.sort(key=_created_sort_key)

    raw_items: list[dict[str, Any]] = []
    candidate_slice = candidate_claim_nodes[-64:]
    total_candidates = max(1, len(candidate_slice))
    for idx, node in enumerate(candidate_slice):
        payload = payload_by_id.get(node.id, {})
        claim_text = str(payload.get("claim") or node.text or "").strip()
        if not claim_text:
            continue

        evidence_nodes: list[dict[str, Any]] = []
        provenance: list[str] = []
        uncertainty_notes: list[str] = []
        conflict_node_ids: list[str] = []

        for edge in incoming_edges.get(node.id, []):
            if edge.type in EVIDENCE_EDGE_TYPES:
                src = nodes_by_id.get(edge.from_id)
                if not src:
                    continue
                evidence_nodes.append(
                    {
                        "id": src.id,
                        "type": src.type,
                        "text": _short_text(src.text or ""),
                        "edge_type": edge.type,
                    }
                )
            if edge.type in CONFLICT_EDGE_TYPES:
                conflict_node_ids.append(edge.from_id)

        for edge in outgoing_edges.get(node.id, []):
            if edge.type in CONFLICT_EDGE_TYPES:
                conflict_node_ids.append(edge.to_id)

        if isinstance(payload.get("provenance"), str) and str(payload.get("provenance")).strip():
            provenance.append(str(payload.get("provenance")).strip())
        for key in ("source", "uri", "reference"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                provenance.append(value.strip())

        uncertainty_value = payload.get("uncertainty")
        if isinstance(uncertainty_value, str) and uncertainty_value.strip():
            uncertainty_notes.append(uncertainty_value.strip())
        confidence = payload.get("confidence")
        if confidence is not None:
            uncertainty_notes.append(f"confidence={confidence}")

        if isinstance(payload.get("unknowns"), list):
            for unknown in payload.get("unknowns")[:3]:
                clean = str(unknown or "").strip()
                if clean:
                    uncertainty_notes.append(clean)

        if node.type == "Message" and not evidence_nodes and not provenance:
            # De-prioritize low-signal assistant chatter.
            if len(claim_text) > 280:
                continue

        selected_in_context = node.id in active_set
        claim_type = node.type
        normalized_text = _short_text(claim_text, 300)
        pin_level = str(payload.get("pin_level") or "").strip().lower() or None
        is_pinned = pin_level in {"required", "preferred"} or bool(payload.get("pinned") or payload.get("is_pinned"))
        recency_bonus = ((idx + 1) / total_candidates) * 2.0
        score = 0.0
        if selected_in_context:
            score += 5.0
        if evidence_nodes:
            score += 4.0 + min(2.0, len(evidence_nodes) * 0.5)
        if provenance:
            score += 3.0
        if conflict_node_ids:
            score += 2.0
        if claim_type in CLAIM_NODE_TYPES:
            score += 2.0
        else:
            score -= 1.0
        if claim_type == "Message":
            score -= 2.0
        if 32 <= len(claim_text) <= 220:
            score += 1.0
        elif len(claim_text) > 460:
            score -= 1.0
        if uncertainty_notes:
            score += 0.3
        score += recency_bonus

        related_ids = [node.id]
        related_ids.extend([item["id"] for item in evidence_nodes if item.get("id")])
        related_ids.extend(sorted(set(conflict_node_ids)))
        seen_ids: set[str] = set()
        related_ids = [rid for rid in related_ids if rid and not (rid in seen_ids or seen_ids.add(rid))]

        raw_items.append(
            {
                "claim_node_id": node.id,
                "claim_node_type": claim_type,
                "claim_text": normalized_text,
                "created_at": node.created_at,
                "selected_in_context": selected_in_context,
                "evidence_nodes": evidence_nodes[:8],
                "provenance": provenance[:6],
                "uncertainty": uncertainty_notes[:6],
                "conflict_node_ids": sorted(set(conflict_node_ids))[:8],
                "related_node_ids": related_ids[:16],
                "pin_level": pin_level,
                "pinned": is_pinned,
                "score": round(score, 3),
            }
        )

    items = sorted(
        raw_items,
        key=lambda item: (
            float(item.get("score") or 0),
            str(item.get("created_at") or ""),
            str(item.get("claim_node_id") or ""),
        ),
        reverse=True,
    )

    conflict_count = sum(1 for item in items if item["conflict_node_ids"])
    uncertain_count = sum(1 for item in items if item["uncertainty"])
    supported_count = sum(1 for item in items if item["evidence_nodes"])

    return {
        "items": items[:30],
        "counts": {
            "claims": len(items),
            "supported": supported_count,
            "with_conflicts": conflict_count,
            "with_uncertainty": uncertain_count,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

def build_run_studio_summary(
    session: Session,
    *,
    thread: Thread,
    context_set_id: str | None = None,
) -> dict[str, Any]:
    context_set = _resolve_context_set(session, thread_id=thread.id, context_set_id=context_set_id)
    active_ids = _active_ids(context_set)
    nodes, edges = load_thread_graph(session, thread.id)

    projections = build_logical_projections(nodes, edges, active_node_ids=active_ids)
    now_panel = _now_panel_summary(thread=thread, nodes=nodes, edges=edges, active_ids=active_ids)
    current_run_id = str((now_panel.get("state") or {}).get("current_run_id") or "").strip() or None
    runtime_projection = resolve_runtime_projection(
        nodes=nodes,
        edges=edges,
        run_id=current_run_id,
        session=session,
        thread_id=thread.id,
        team_nodes=nodes,
        include_conversation_team=True,
        context_source_default="goc",
        plan_source_default="local",
        mode_default="goc",
    )
    run_skill_summary = runtime_projection.capability_payload()

    now_state = dict(now_panel.get("state") or {})
    runtime_projection.apply_authority(now_state)
    now_panel["state"] = now_state

    current_run_panel = dict(now_panel.get("current_run") or {})
    runtime_projection.apply_authority(current_run_panel)
    now_panel["current_run"] = current_run_panel

    agent_team = runtime_projection.conversation_team_payload()

    context_decisions = _context_decisions_summary(
        session,
        thread_id=thread.id,
        context_set=context_set,
        nodes=nodes,
        edges=edges,
    )
    evidence = _evidence_summary(nodes=nodes, edges=edges, active_ids=active_ids)

    current_run_skills = dict(run_skill_summary)
    planning_boundary = dict(runtime_projection.planning_boundary)
    team_view = dict(run_skill_summary.get("team_view") or {})
    why_this_team = dict(run_skill_summary.get("why_this_team") or {})
    orchestration = dict(run_skill_summary.get("orchestration") or {})
    scope_projection = dict(run_skill_summary.get("scope_projection") or {})
    visibility_projection = dict(run_skill_summary.get("visibility_projection") or {})
    collaboration = dict(run_skill_summary.get("collaboration") or {})
    authority_projection = dict(run_skill_summary.get("authority") or {})
    checkpoints = dict(run_skill_summary.get("checkpoints") or {})
    team_items = team_view.get("items") if isinstance(team_view.get("items"), list) else []
    agent_room = {
        "kind": "agent_room_profile_projection_v1",
        "status": "active" if team_items else "unconfigured",
        "default_agents": [str((row or {}).get("role") or (row or {}).get("id") or (row or {}).get("agent_id") or "").strip() for row in team_items if str((row or {}).get("role") or (row or {}).get("id") or (row or {}).get("agent_id") or "").strip()],
        "default_workflow": orchestration.get("workflow_kind") or why_this_team.get("workflow_kind") or "task-adaptive",
        "autonomy_policy": {
            "small_safe_changes": "auto_or_review_by_task",
            "risky_or_large_changes": "approval_required",
            "deployment": "forbidden_without_explicit_approval",
        },
        "memory_scope": "room",
        "growth_surfaces": ["memory", "skill", "rule", "role", "team_blueprint"],
    }

    out = {
        "thread": {
            "id": thread.id,
            "title": thread.title,
            "external_ref": thread.external_ref,
        },
        "context_set": {
            "id": context_set.id if context_set else None,
            "name": context_set.name if context_set else None,
            "active_count": len(active_ids),
        },
        "now": now_panel,
        "agent_team": agent_team,
        "agent_room": agent_room,
        "projections": projections,
        "context_decisions_counts": context_decisions.get("counts", {}),
        "evidence_counts": evidence.get("counts", {}),
        "skill_counts": run_skill_summary.get("counts", {}),
        "current_run_skills": current_run_skills,
        "team_view": team_view,
        "why_this_team": why_this_team,
        "orchestration": orchestration,
        "scope_projection": scope_projection,
        "visibility_projection": visibility_projection,
        "collaboration": collaboration,
        "authority": authority_projection,
        "checkpoints": checkpoints,
        "planning_boundary": planning_boundary,
        "graph_counts": {
            "nodes": len(nodes),
            "edges": len(edges),
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return runtime_projection.apply_authority(out)


def build_run_studio_agent_team(
    session: Session,
    *,
    thread: Thread,
) -> dict[str, Any]:
    nodes, edges = load_thread_graph(session, thread.id)
    runtime_projection = resolve_runtime_projection(
        nodes=nodes,
        edges=edges,
        session=session,
        thread_id=thread.id,
        team_nodes=nodes,
        include_conversation_team=True,
        context_source_default="goc",
        plan_source_default="local",
        mode_default="goc",
    )
    return runtime_projection.conversation_team_payload()


def build_run_studio_context_decisions(
    session: Session,
    *,
    thread: Thread,
    context_set_id: str | None = None,
) -> dict[str, Any]:
    context_set = _resolve_context_set(session, thread_id=thread.id, context_set_id=context_set_id)
    nodes, edges = load_thread_graph(session, thread.id)
    return _context_decisions_summary(
        session,
        thread_id=thread.id,
        context_set=context_set,
        nodes=nodes,
        edges=edges,
    )


def build_run_studio_evidence(
    session: Session,
    *,
    thread: Thread,
    context_set_id: str | None = None,
    run_id: str | None = None,
    nodes: list[Node] | None = None,
    edges: list[Edge] | None = None,
) -> dict[str, Any]:
    context_set = _resolve_context_set(session, thread_id=thread.id, context_set_id=context_set_id)
    active_ids = _active_ids(context_set)
    nodes, edges = _graph_or_load(session, thread_id=thread.id, nodes=nodes, edges=edges)
    scoped_nodes, scoped_edges = _scope_graph_for_run(nodes=nodes, edges=edges, run_id=run_id)
    active_scope = set(str(node_id).strip() for node_id in active_ids if str(node_id).strip())
    if run_id:
        scoped_node_ids = {str(getattr(node, 'id', '') or '') for node in scoped_nodes}
        active_ids = [node_id for node_id in active_ids if node_id in scoped_node_ids]
    summary = _evidence_summary(nodes=scoped_nodes, edges=scoped_edges, active_ids=active_ids)
    summary['run_id'] = str(run_id or '').strip() or None
    summary['scope'] = 'run' if str(run_id or '').strip() else 'thread'
    summary['active_context_count'] = len(active_scope.intersection({str(getattr(node, 'id', '') or '') for node in scoped_nodes})) if run_id else len(active_ids)
    return summary


def build_run_studio_trace_scope(
    session: Session,
    *,
    thread: Thread,
    run_id: str | None = None,
    nodes: list[Node] | None = None,
    edges: list[Edge] | None = None,
) -> dict[str, Any]:
    nodes, edges = _graph_or_load(session, thread_id=thread.id, nodes=nodes, edges=edges)
    scoped_nodes, scoped_edges = _scope_graph_for_run(nodes=nodes, edges=edges, run_id=run_id)
    clean_run_id = str(run_id or '').strip() or None
    step_run_id_by_step_id = build_step_run_id_index(nodes, edges)

    node_ids: list[str] = []
    step_node_ids: list[str] = []
    evidence_node_ids: list[str] = []
    memory_node_ids: list[str] = []
    run_node_id: str | None = None
    anchor_node_id: str | None = None

    for node in scoped_nodes:
        node_id = str(getattr(node, 'id', '') or '').strip()
        if not node_id:
            continue
        node_ids.append(node_id)
        node_type = str(getattr(node, 'type', '') or '').strip()
        payload = _node_payload(node)
        payload_run_id = str(payload.get('run_id') or '').strip()
        if node_type == 'Run' and (not clean_run_id or node_id == clean_run_id):
            run_node_id = node_id
        if node_type == 'Step':
            node_run_id = step_run_id_by_step_id.get(node_id) or payload_run_id or None
            if not clean_run_id or node_run_id == clean_run_id:
                step_node_ids.append(node_id)
        if node_type in CLAIM_NODE_TYPES or node_type in {'Evidence', 'Observation', 'Citation'}:
            evidence_node_ids.append(node_id)
        if payload.get('surface_id') is not None or payload.get('memory_surface_id') is not None or payload.get('memory_node_id') is not None:
            memory_node_ids.append(node_id)

    anchor_node_id = run_node_id or (step_node_ids[-1] if step_node_ids else (node_ids[0] if node_ids else None))

    return {
        'run_id': clean_run_id,
        'scope': 'run' if clean_run_id else 'thread',
        'node_ids': node_ids,
        'edge_ids': [str(getattr(edge, 'id', '') or '') for edge in scoped_edges if str(getattr(edge, 'id', '') or '').strip()],
        'node_count': len(node_ids),
        'edge_count': len(scoped_edges),
        'run_node_id': run_node_id,
        'anchor_node_id': anchor_node_id,
        'step_node_ids': step_node_ids,
        'step_count': len(step_node_ids),
        'evidence_node_ids': evidence_node_ids,
        'evidence_node_count': len(evidence_node_ids),
        'memory_node_ids': memory_node_ids,
        'memory_node_count': len(memory_node_ids),
    }






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



def _build_run_bundle_cross_references(
    *,
    evidence: dict[str, Any] | None,
    memory_graph: dict[str, Any] | None,
    trace_scope: dict[str, Any] | None,
) -> dict[str, Any]:
    return _build_run_bundle_cross_references_impl(
        evidence=evidence,
        memory_graph=memory_graph,
        trace_scope=trace_scope,
    )


def _team_selection_event_payload(row: TeamSelectionEvent | None) -> dict[str, Any] | None:
    if not row:
        return None
    dataset = build_team_selection_dataset([{
        'id': row.id,
        'thread_id': row.thread_id,
        'run_id': row.run_id,
        'task_text': row.task_text,
        'selected_blueprint_id': row.selected_blueprint_id,
        'recommendation': _jload(row.recommendation_json, {}),
        'outcome': _jload(row.outcome_json, {}),
        'created_at': row.created_at.isoformat() if row.created_at else None,
    }])
    rows = dataset.get('rows') or []
    return rows[0] if rows else None


def _latest_team_selection_event(
    session: Session,
    *,
    thread_id: str,
    run_id: str | None,
) -> TeamSelectionEvent | None:
    statement = select(TeamSelectionEvent).where(TeamSelectionEvent.thread_id == thread_id)
    clean_run_id = str(run_id or '').strip() or None
    if clean_run_id:
        statement = statement.where(TeamSelectionEvent.run_id == clean_run_id)
    return session.exec(statement.order_by(TeamSelectionEvent.created_at.desc()).limit(1)).first()



def build_run_studio_audit_timeline(
    session: Session,
    *,
    thread: Thread,
    context_set_id: str | None = None,
    run_id: str | None = None,
    evidence: dict[str, Any] | None = None,
    memory_graph: dict[str, Any] | None = None,
    trace_scope: dict[str, Any] | None = None,
    cross_references: dict[str, Any] | None = None,
    projection_retrieval: dict[str, Any] | None = None,
    nodes: list[Node] | None = None,
    edges: list[Edge] | None = None,
) -> dict[str, Any]:
    return build_run_studio_audit_timeline_impl(
        session,
        thread=thread,
        context_set_id=context_set_id,
        run_id=run_id,
        evidence=evidence,
        memory_graph=memory_graph,
        trace_scope=trace_scope,
        cross_references=cross_references,
        projection_retrieval=projection_retrieval,
        nodes=nodes,
        edges=edges,
        _build_run_bundle_cross_references=_build_run_bundle_cross_references,
        _clean_node_ids=_clean_node_ids,
        _clean_text=_clean_text,
        _graph_or_load=_graph_or_load,
        _iso_or_none=_iso_or_none,
        _jload=_jload,
        _latest_team_selection_event=_latest_team_selection_event,
        _node_payload=_node_payload,
        _push_timeline_event=_push_timeline_event,
        _resolve_context_set=_resolve_context_set,
        _scope_graph_for_run=_scope_graph_for_run,
        _short_text=_short_text,
        _team_selection_event_payload=_team_selection_event_payload,
        _timeline_event_sort_key=_timeline_event_sort_key,
        _extract_runtime_team_snapshot=_extract_runtime_team_snapshot,
        build_run_studio_evidence=build_run_studio_evidence,
        build_run_studio_memory_graph=build_run_studio_memory_graph,
        build_run_studio_projection_retrieval=build_run_studio_projection_retrieval,
        build_run_studio_trace_scope=build_run_studio_trace_scope,
    )


def build_run_studio_memory_graph(
    session: Session,
    *,
    thread: Thread,
    run_id: str | None = None,
    projection_limit: int = 12,
    conflict_limit: int = 30,
) -> dict[str, Any]:
    clean_run_id = str(run_id or '').strip() or None
    clean_projection_limit = max(1, min(int(projection_limit or 12), 50))
    clean_conflict_limit = max(1, min(int(conflict_limit or 30), 100))

    statement = select(MemoryProjection).where(MemoryProjection.thread_id == thread.id)
    if clean_run_id:
        statement = statement.where(MemoryProjection.run_id == clean_run_id)
    rows = session.exec(statement.order_by(MemoryProjection.created_at.desc()).limit(clean_projection_limit)).all()
    node_map = {row.id: row for row in session.exec(select(MemoryNode).where(MemoryNode.thread_id == thread.id)).all()}
    lifecycle_statement = select(MemoryLifecycleEvent).where(MemoryLifecycleEvent.thread_id == thread.id)
    if clean_run_id:
        lifecycle_statement = lifecycle_statement.where(MemoryLifecycleEvent.created_run_id == clean_run_id)
    lifecycle_rows = session.exec(lifecycle_statement.order_by(MemoryLifecycleEvent.created_at.desc()).limit(max(clean_conflict_limit * 4, 80))).all()
    if clean_run_id:
        allowed_node_ids = {row.id for row in node_map.values() if str(getattr(row, 'created_run_id', '') or '').strip() == clean_run_id}
        lifecycle_rows = [row for row in lifecycle_rows if row.node_id in allowed_node_ids or str(getattr(row, 'created_run_id', '') or '').strip() == clean_run_id]
    lifecycle_by_node: dict[str, list[dict[str, Any]]] = {}
    lifecycle_items: list[dict[str, Any]] = []
    for row in lifecycle_rows:
        summary = summarize_memory_lifecycle_event({
            'id': row.id,
            'thread_id': row.thread_id,
            'node_id': row.node_id,
            'surface_id': row.surface_id,
            'event_type': row.event_type,
            'from_status': row.from_status,
            'to_status': row.to_status,
            'actor': row.actor,
            'source': row.source,
            'summary': row.summary,
            'metadata_json': _jload(row.metadata_json, {}),
            'created_run_id': row.created_run_id,
            'created_at': row.created_at.isoformat() if row.created_at else None,
        })
        lifecycle_items.append(summary)
        node_id = str(summary.get('node_id') or '').strip()
        if node_id:
            lifecycle_by_node.setdefault(node_id, []).append(summary)

    items: list[dict[str, Any]] = []
    for row in rows:
        summary = _jload(row.summary_json, {})
        visible_node_ids = _jload(row.visible_node_ids_json, [])
        blocked_node_ids = _jload(row.blocked_node_ids_json, [])
        surface_reason_map = summary.get('surface_reason_map') or {}
        node_reason_map = summary.get('node_reason_map') or {}

        def _node_detail(node_id: str, *, blocked: bool = False) -> dict[str, Any]:
            node = node_map.get(node_id)
            if not node:
                return {'node_id': node_id, 'blocked_reason': 'missing'} if blocked else {'node_id': node_id}
            content = _jload(node.content_json, {})
            provenance = _jload(node.provenance_json, {})
            preview = ''
            if isinstance(content, dict):
                for key in ('claim', 'value', 'text', 'summary', 'decision', 'answer', 'note'):
                    value = str(content.get(key) or '').strip()
                    if value:
                        preview = value[:160]
                        break
                if not preview:
                    preview = json.dumps(content, ensure_ascii=False, sort_keys=True)[:160]
            else:
                preview = str(content or '')[:160]
            node_lifecycle = lifecycle_by_node.get(node.id) or []
            detail = {
                'node_id': node.id,
                'surface_id': node.surface_id,
                'node_type': node.node_type,
                'status': node.status,
                'trust_tier': node.trust_tier,
                'confidence': provenance.get('confidence') or provenance.get('confidence_score') or (content.get('confidence') if isinstance(content, dict) else 0) or (content.get('confidence_score') if isinstance(content, dict) else 0) or 0,
                'owner_agent_id': node.owner_agent_id,
                'owner_role_id': node.owner_role_id,
                'created_run_id': node.created_run_id,
                'content_preview': preview,
                'provenance_fingerprint': (provenance.get('source_id') or provenance.get('document_id') or provenance.get('url') or provenance.get('entity') or provenance.get('topic')),
                'lifecycle_event_count': len(node_lifecycle),
                'latest_lifecycle_event': node_lifecycle[0] if node_lifecycle else None,
                'lifecycle_status_path': [str(item.get('to_status') or item.get('event_type') or '') for item in reversed(node_lifecycle[:5]) if str(item.get('to_status') or item.get('event_type') or '').strip()],
            }
            if blocked:
                detail['blocked_reason'] = node_reason_map.get(node.id) or surface_reason_map.get(node.surface_id) or 'surface_not_visible'
            else:
                detail['visibility_reason'] = node_reason_map.get(node.id) or 'visible'
            return detail

        items.append({
            'projection_id': row.id,
            'run_id': row.run_id,
            'agent_id': row.agent_id,
            'role_id': row.role_id,
            'summary': summary,
            'visible_surface_ids': summary.get('visible_surface_ids') or [],
            'blocked_surface_ids': summary.get('blocked_surface_ids') or [],
            'visible_node_ids': visible_node_ids,
            'blocked_node_ids': blocked_node_ids,
            'visible_nodes': [_node_detail(node_id) for node_id in visible_node_ids],
            'blocked_nodes': [_node_detail(node_id, blocked=True) for node_id in blocked_node_ids],
            'created_at': row.created_at.isoformat() if row.created_at else None,
        })

    conflict_statement = select(MemoryConflict).where(MemoryConflict.thread_id == thread.id)
    conflict_rows = session.exec(conflict_statement.order_by(MemoryConflict.updated_at.desc()).limit(clean_conflict_limit)).all()
    if clean_run_id:
        allowed_node_ids = {row.id for row in node_map.values() if str(getattr(row, 'created_run_id', '') or '').strip() == clean_run_id}
        conflict_rows = [
            row for row in conflict_rows
            if row.left_node_id in allowed_node_ids or row.right_node_id in allowed_node_ids
        ]
    conflict_summary = summarize_memory_conflicts([
        {
            'id': row.id,
            'surface_id': row.surface_id,
            'left_node_id': row.left_node_id,
            'right_node_id': row.right_node_id,
            'status': row.status,
            'reason': row.reason,
            'created_at': row.created_at.isoformat() if row.created_at else None,
            'updated_at': row.updated_at.isoformat() if row.updated_at else None,
            'resolution_json': _jload(row.resolution_json, {}),
        }
        for row in conflict_rows
    ])
    edge_statement = select(MemoryEdge).where(MemoryEdge.thread_id == thread.id)
    if clean_run_id:
        edge_statement = edge_statement.where(MemoryEdge.created_run_id == clean_run_id)
    edge_rows = session.exec(edge_statement.order_by(MemoryEdge.updated_at.desc()).limit(max(clean_conflict_limit, 40))).all()
    if clean_run_id:
        allowed_node_ids = {row.id for row in node_map.values() if str(getattr(row, 'created_run_id', '') or '').strip() == clean_run_id}
        edge_rows = [
            row for row in edge_rows
            if row.from_node_id in allowed_node_ids or row.to_node_id in allowed_node_ids or str(getattr(row, 'created_run_id', '') or '').strip() == clean_run_id
        ]
    edge_lookup = {
        node_id: {
            'id': node.id,
            'node_type': node.node_type,
            'owner_role_id': node.owner_role_id,
            'content_json': _jload(node.content_json, {}),
            'provenance_json': _jload(node.provenance_json, {}),
        }
        for node_id, node in node_map.items()
    }
    edge_items = [summarize_memory_edge({
        'id': row.id,
        'edge_type': row.edge_type,
        'from_node_id': row.from_node_id,
        'to_node_id': row.to_node_id,
        'from_surface_id': row.from_surface_id,
        'to_surface_id': row.to_surface_id,
        'status': row.status,
        'rationale': row.rationale,
        'provenance_json': _jload(row.provenance_json, {}),
        'created_run_id': row.created_run_id,
        'created_at': row.created_at,
        'updated_at': row.updated_at,
    }, node_lookup=edge_lookup) for row in edge_rows]
    edge_type_counts: dict[str, int] = {}
    for item in edge_items:
        key = str(item.get('edge_type') or 'related_to')
        edge_type_counts[key] = edge_type_counts.get(key, 0) + 1
    lifecycle_event_type_counts: dict[str, int] = {}
    for item in lifecycle_items:
        key = str(item.get('event_type') or 'node_updated')
        lifecycle_event_type_counts[key] = lifecycle_event_type_counts.get(key, 0) + 1
    return {
        'run_id': clean_run_id,
        'scope': 'run' if clean_run_id else 'thread',
        'projections': items,
        'projection_count': len(items),
        'conflicts': conflict_summary.get('items') or [],
        'conflict_count': conflict_summary.get('count') or 0,
        'conflict_status_counts': conflict_summary.get('status_counts') or {},
        'conflict_reason_counts': conflict_summary.get('reason_counts') or {},
        'edges': edge_items,
        'edge_count': len(edge_items),
        'edge_type_counts': edge_type_counts,
        'lifecycle_events': lifecycle_items,
        'lifecycle_event_count': len(lifecycle_items),
        'lifecycle_event_type_counts': lifecycle_event_type_counts,
    }


def build_run_studio_projection_retrieval(
    session: Session,
    *,
    thread: Thread,
    run_id: str | None = None,
    memory_graph: dict[str, Any] | None = None,
    nodes: list[Node] | None = None,
    edges: list[Edge] | None = None,
) -> dict[str, Any]:
    clean_run_id = str(run_id or '').strip() or None
    nodes, edges = _graph_or_load(session, thread_id=thread.id, nodes=nodes, edges=edges)
    runtime_projection = resolve_runtime_projection(
        nodes=nodes,
        edges=edges,
        run_id=clean_run_id,
        session=session,
        thread_id=thread.id,
        team_nodes=nodes,
        include_conversation_team=True,
        context_source_default='goc',
        plan_source_default='local',
        mode_default='goc',
    )
    capability = runtime_projection.capability_payload()
    runtime_authority = dict(capability.get('runtime_authority') or {})
    team_view = dict(capability.get('team_view') or {})
    scope_projection = dict(capability.get('scope_projection') or {})
    visibility_projection = dict(capability.get('visibility_projection') or {})
    memory_obj = memory_graph if isinstance(memory_graph, dict) else build_run_studio_memory_graph(session, thread=thread, run_id=clean_run_id)

    projection_by_role: dict[str, dict[str, Any]] = {}
    projection_by_agent: dict[str, dict[str, Any]] = {}
    for projection in list(memory_obj.get('projections') or []):
        role_id = _clean_text(projection.get('role_id'))
        agent_id = _clean_text(projection.get('agent_id'))
        current_key = (
            _count_entries(projection.get('visible_node_ids')),
            -_count_entries(projection.get('blocked_node_ids')),
            _parse_datetime(projection.get('created_at')).timestamp() if _parse_datetime(projection.get('created_at')) else 0.0,
        )
        if role_id:
            existing = projection_by_role.get(role_id)
            existing_key = (
                _count_entries((existing or {}).get('visible_node_ids')),
                -_count_entries((existing or {}).get('blocked_node_ids')),
                _parse_datetime((existing or {}).get('created_at')).timestamp() if _parse_datetime((existing or {}).get('created_at')) else 0.0,
            )
            if existing is None or current_key >= existing_key:
                projection_by_role[role_id] = projection
        if agent_id:
            existing = projection_by_agent.get(agent_id)
            existing_key = (
                _count_entries((existing or {}).get('visible_node_ids')),
                -_count_entries((existing or {}).get('blocked_node_ids')),
                _parse_datetime((existing or {}).get('created_at')).timestamp() if _parse_datetime((existing or {}).get('created_at')) else 0.0,
            )
            if existing is None or current_key >= existing_key:
                projection_by_agent[agent_id] = projection

    coverage_items: list[dict[str, Any]] = []
    for item in list(team_view.get('items') or []):
        runtime_instance_id = _clean_text(item.get('runtime_instance_id'))
        role_id = _clean_text(item.get('role_id'))
        scope_id = _clean_text(item.get('scope_id'))
        display_label = _clean_text(item.get('display_label') or item.get('role_label') or role_id or runtime_instance_id) or 'runtime agent'
        scope_item = None
        for candidate in list(scope_projection.get('items') or []):
            if runtime_instance_id and _clean_text(candidate.get('runtime_instance_id')) == runtime_instance_id:
                scope_item = candidate
                break
            if scope_item is None and scope_id and _clean_text(candidate.get('scope_id')) == scope_id:
                scope_item = candidate
            if scope_item is None and _clean_text(candidate.get('display_label')) == display_label:
                scope_item = candidate
        projection = None
        if role_id:
            projection = projection_by_role.get(role_id)
        if projection is None and runtime_instance_id:
            projection = projection_by_agent.get(runtime_instance_id)
        visible_count = _count_entries((projection or {}).get('visible_node_ids'))
        blocked_count = _count_entries((projection or {}).get('blocked_node_ids'))
        active_node_count = int((scope_item or {}).get('active_node_count') or 0)
        authoritative_scope = _boolish((scope_item or {}).get('authoritative_scope'))
        empty_scope = _boolish((scope_item or {}).get('empty_scope')) or active_node_count == 0
        degraded_mode = _boolish(runtime_authority.get('degraded_mode'))
        context_source = str(runtime_authority.get('context_source') or capability.get('context_source') or '').strip().lower()
        missing_projection = projection is None
        blocked_only = blocked_count > 0 and visible_count == 0
        partial = visible_count > 0 and blocked_count > 0
        authoritative = bool(not degraded_mode and context_source == 'goc' and authoritative_scope and visible_count > 0)
        status = 'planned_only'
        if degraded_mode:
            status = 'degraded'
        elif authoritative:
            status = 'authoritative'
        elif blocked_only:
            status = 'blocked_only'
        elif empty_scope:
            status = 'empty_scope'
        elif missing_projection and authoritative_scope:
            status = 'missing_projection'
        elif missing_projection:
            status = 'planned_only'
        elif partial:
            status = 'partial'
        elif visible_count > 0:
            status = 'visible_non_authoritative'
        elif blocked_count > 0:
            status = 'blocked_only'
        elif projection is not None:
            status = 'empty_projection'

        coverage_items.append({
            'runtime_instance_id': runtime_instance_id,
            'role_id': role_id,
            'display_label': display_label,
            'scope_id': scope_id,
            'visibility_mode': _clean_text((scope_item or {}).get('visibility_mode')),
            'grant_labels': list((scope_item or {}).get('grant_labels') or []),
            'active_node_count': active_node_count,
            'authoritative_scope': authoritative_scope,
            'empty_scope': empty_scope,
            'scope_context_set_id': _clean_text((scope_item or {}).get('context_set_id')),
            'selection_summary': _clean_text((scope_item or {}).get('selection_summary') or (scope_item or {}).get('selection_reason')),
            'selection_confidence': _clean_text((scope_item or {}).get('selection_confidence')),
            'projection_id': _clean_text((projection or {}).get('projection_id')),
            'projection_created_at': _clean_text((projection or {}).get('created_at')),
            'visible_node_count': visible_count,
            'blocked_node_count': blocked_count,
            'visible_surface_ids': list((projection or {}).get('visible_surface_ids') or []),
            'blocked_surface_ids': list((projection or {}).get('blocked_surface_ids') or []),
            'status': status,
            'projection_authoritative': authoritative,
            'traceable_in_memory_graph': projection is not None,
            'context_source': context_source or None,
            'degraded_mode': degraded_mode,
            'fallback_reason': _clean_text(runtime_authority.get('fallback_reason') or capability.get('fallback_reason')),
        })

    def _planner_or_system(item: dict[str, Any]) -> bool:
        role_text = ' '.join([
            str(item.get('role_id') or ''),
            str(item.get('display_label') or ''),
        ]).strip().lower()
        return any(token in role_text for token in ('planner', 'operator', 'system', 'supervisor', 'router'))

    coverage_items.sort(
        key=lambda item: (
            1 if item.get('projection_authoritative') else 0,
            int(item.get('visible_node_count') or 0),
            -int(item.get('blocked_node_count') or 0),
            str(item.get('display_label') or ''),
        ),
        reverse=True,
    )
    planner_system_paths = [item for item in coverage_items if _planner_or_system(item)]
    counts = {
        'roles': len(coverage_items),
        'authoritative_roles': sum(1 for item in coverage_items if item.get('projection_authoritative')),
        'degraded_roles': sum(1 for item in coverage_items if item.get('status') == 'degraded'),
        'partial_roles': sum(1 for item in coverage_items if item.get('status') == 'partial'),
        'visible_non_authoritative_roles': sum(1 for item in coverage_items if item.get('status') == 'visible_non_authoritative'),
        'blocked_only_roles': sum(1 for item in coverage_items if item.get('status') == 'blocked_only'),
        'empty_scope_roles': sum(1 for item in coverage_items if item.get('status') == 'empty_scope'),
        'missing_projection_roles': sum(1 for item in coverage_items if item.get('status') == 'missing_projection'),
        'planned_only_roles': sum(1 for item in coverage_items if item.get('status') == 'planned_only'),
        'planner_system_roles': len(planner_system_paths),
        'planner_system_authoritative_roles': sum(1 for item in planner_system_paths if item.get('projection_authoritative')),
        'planner_system_missing_roles': sum(1 for item in planner_system_paths if item.get('status') in {'missing_projection', 'planned_only'}),
    }
    scope_first_ready = _boolish(scope_projection.get('scope_first_ready'))
    degraded_mode = _boolish(runtime_authority.get('degraded_mode'))
    context_source = str(runtime_authority.get('context_source') or capability.get('context_source') or '').strip().lower() or None
    projection_authoritative = bool(
        context_source == 'goc'
        and scope_first_ready
        and not degraded_mode
        and counts['roles'] > 0
        and counts['authoritative_roles'] >= max(1, counts['roles'] - counts['empty_scope_roles'])
    )
    overall_status = 'partial'
    if degraded_mode:
        overall_status = 'degraded'
    elif projection_authoritative:
        overall_status = 'authoritative'
    elif counts['authoritative_roles'] > 0:
        overall_status = 'partial'
    elif counts['missing_projection_roles'] > 0 or counts['planned_only_roles'] > 0:
        overall_status = 'planned_only'
    elif counts['empty_scope_roles'] == counts['roles'] and counts['roles'] > 0:
        overall_status = 'empty'
    note_parts: list[str] = []
    if scope_first_ready:
        note_parts.append('scope-first runtime is active')
    if projection_authoritative:
        note_parts.append('projection retrieval is authoritative for the focused run')
    elif counts['authoritative_roles'] > 0:
        note_parts.append('projection retrieval covers part of the focused run')
    elif counts['missing_projection_roles'] > 0 or counts['planned_only_roles'] > 0:
        note_parts.append('some runtime paths still rely on pre-projection planning metadata')
    if counts['planner_system_roles'] > 0 and counts['planner_system_authoritative_roles'] < counts['planner_system_roles']:
        note_parts.append('planner/system coverage is not fully projection-authoritative yet')
    fallback_reason = _clean_text(runtime_authority.get('fallback_reason') or capability.get('fallback_reason'))
    if fallback_reason:
        note_parts.append(f'fallback: {fallback_reason}')
    return {
        'run_id': clean_run_id,
        'scope': 'run' if clean_run_id else 'thread',
        'summary': {
            'status': overall_status,
            'projection_authoritative': projection_authoritative,
            'scope_first_ready': scope_first_ready,
            'context_runtime_mode': _clean_text(scope_projection.get('context_runtime_mode')),
            'context_source': context_source,
            'degraded_mode': degraded_mode,
            'fallback_reason': fallback_reason,
            'coverage_note': '; '.join(note_parts) or None,
            'scope_projection_note': _clean_text(scope_projection.get('scope_projection_note')),
            'visibility_relation_count': int(visibility_projection.get('count') or 0),
        },
        'counts': counts,
        'items': coverage_items,
        'planner_system_paths': planner_system_paths,
        'visibility_relation_counts': dict(visibility_projection.get('relation_counts') or {}),
        'runtime_authority': runtime_authority,
    }



def build_run_studio_run_bundle(
    session: Session,
    *,
    thread: Thread,
    context_set_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    clean_run_id = str(run_id or '').strip() or None
    context_set = _resolve_context_set(session, thread_id=thread.id, context_set_id=context_set_id)
    graph_version_payload = _build_graph_version_payload(session, thread=thread, context_set=context_set)
    graph_version = str(graph_version_payload.get('graph_version') or '')
    harness_spec = get_thread_harness_spec(thread)
    harness_summary = build_harness_summary(harness_spec)
    cache = get_global_context_cache()
    cache_versions = _context_cache_versions()
    bundle_cache_key = build_cache_key('run_bundle', {
        'v': cache_versions['run_bundle'],
        'thread_id': thread.id,
        'context_set_id': getattr(context_set, 'id', None),
        'run_id': clean_run_id,
        'graph_version': graph_version,
    })
    cached_bundle = cache.get(bundle_cache_key)
    if cached_bundle is not None:
        cached_bundle = copy.deepcopy(cached_bundle)
        cached_bundle['context_cache'] = {
            **dict(cached_bundle.get('context_cache') or {}),
            'graph_version': graph_version,
            'graph_version_payload': graph_version_payload,
            'bundle_cache_hit': True,
        }
        cached_bundle['performance'] = {
            **dict(cached_bundle.get('performance') or {}),
            'bundle_elapsed_ms': round((time.perf_counter() - started) * 1000.0, 3),
            'bundle_cache_hit': True,
        }
        return cached_bundle

    nodes, edges = load_thread_graph(session, thread.id)
    evidence = build_run_studio_evidence(
        session,
        thread=thread,
        context_set_id=getattr(context_set, 'id', None),
        run_id=clean_run_id,
        nodes=nodes,
        edges=edges,
    )
    context_packs = build_run_studio_context_packs(session, thread=thread, run_id=clean_run_id, nodes=nodes, edges=edges)
    skill_usage = build_run_studio_skill_usage(session, thread=thread, run_id=clean_run_id, nodes=nodes, edges=edges)
    memory_graph = build_run_studio_memory_graph(session, thread=thread, run_id=clean_run_id)
    memory_topology = build_run_studio_memory_topology(session, thread=thread, run_id=clean_run_id)
    memory_demand = build_run_studio_memory_demand(session, thread=thread, run_id=clean_run_id)
    trace_scope = build_run_studio_trace_scope(session, thread=thread, run_id=clean_run_id, nodes=nodes, edges=edges)

    cache_hits: dict[str, bool] = {}
    cross_references, cache_hits['cross_references'], _ = _cached_artifact(
        cache,
        namespace='run_bundle_cross_references',
        payload={
            'v': cache_versions['cross_references'],
            'thread_id': thread.id,
            'context_set_id': getattr(context_set, 'id', None),
            'run_id': clean_run_id,
            'graph_version': graph_version,
        },
        build_fn=lambda: _build_run_bundle_cross_references(
            evidence=evidence,
            memory_graph=memory_graph,
            trace_scope=trace_scope,
        ),
    )
    projection_retrieval, cache_hits['projection_retrieval'], _ = _cached_artifact(
        cache,
        namespace='run_bundle_projection_retrieval',
        payload={
            'v': cache_versions['projection_retrieval'],
            'thread_id': thread.id,
            'run_id': clean_run_id,
            'graph_version': graph_version,
        },
        build_fn=lambda: build_run_studio_projection_retrieval(
            session,
            thread=thread,
            run_id=clean_run_id,
            memory_graph=memory_graph,
            nodes=nodes,
            edges=edges,
        ),
    )
    audit_timeline, cache_hits['audit_timeline'], _ = _cached_artifact(
        cache,
        namespace='run_bundle_audit_timeline',
        payload={
            'v': cache_versions['audit_timeline'],
            'thread_id': thread.id,
            'context_set_id': getattr(context_set, 'id', None),
            'run_id': clean_run_id,
            'graph_version': graph_version,
        },
        build_fn=lambda: build_run_studio_audit_timeline(
            session,
            thread=thread,
            context_set_id=getattr(context_set, 'id', None),
            run_id=clean_run_id,
            evidence=evidence,
            memory_graph=memory_graph,
            trace_scope=trace_scope,
            cross_references=cross_references,
            projection_retrieval=projection_retrieval,
            nodes=nodes,
            edges=edges,
        ),
    )
    graph_compression, cache_hits['graph_native_compression'], _ = _cached_artifact(
        cache,
        namespace='run_bundle_graph_compression',
        payload={
            'v': cache_versions['graph_compression'],
            'thread_id': thread.id,
            'context_set_id': getattr(context_set, 'id', None),
            'run_id': clean_run_id,
            'graph_version': graph_version,
        },
        build_fn=lambda: build_run_studio_graph_compression(
            evidence=evidence,
            memory_graph=memory_graph,
            trace_scope=trace_scope,
            cross_references=cross_references,
            projection_retrieval=projection_retrieval,
        ),
    )
    harness_package = build_harness_package_payload(session, thread=thread, harness_spec=harness_spec, harness_summary=harness_summary)
    bundle = {
        'schema_version': 'openharness.run_bundle/v1',
        'run_trace_schema_version': RUN_TRACE_SCHEMA_VERSION,
        'run_sync_schema_version': RUN_SYNC_SCHEMA_VERSION,
        'harness_package_ref': {
            'schema_version': str(harness_package.get('schema_version') or ''),
            'package_id': str(harness_package.get('package_id') or ''),
            'package_hash': str(harness_package.get('package_hash') or ''),
            'version': int(harness_package.get('version') or 1),
            'name': str(((harness_package.get('metadata') or {}).get('name')) or ''),
        },
        'run_id': clean_run_id,
        'scope': 'run' if clean_run_id else 'thread',
        'context_set_id': getattr(context_set, 'id', None),
        'graph_version': graph_version,
        'evidence': evidence,
        'context_packs': context_packs,
        'skill_usage': skill_usage,
        'memory_graph': memory_graph,
        'memory_topology': memory_topology,
        'memory_demand': memory_demand,
        'trace_scope': trace_scope,
        'cross_references': cross_references,
        'projection_retrieval': projection_retrieval,
        'audit_timeline': audit_timeline,
        'graph_native_compression': graph_compression,
        'harness_spec': harness_spec,
        'harness_summary': harness_summary,
        'trace_contract': {
            'schema_version': RUN_TRACE_SCHEMA_VERSION,
            'transport': 'goc_execution_graph',
            'storage': 'run_step_toolcall_nodes',
        },
        'sync_contract': {
            'schema_version': RUN_SYNC_SCHEMA_VERSION,
            'mode': 'ddalggak_push_goc_observe',
            'direction': 'ddalggak_to_goc',
            'semantics': 'append_only',
        },
        'runtime_policy': dict(harness_package.get('runtime_policy') or {}),
        'context_cache': {
            'graph_version': graph_version,
            'graph_version_payload': graph_version_payload,
            'harness_spec_hash': harness_summary.get('spec_hash'),
            'bundle_cache_hit': False,
            'artifact_cache_hits': cache_hits,
            'cache_versions': cache_versions,
        },
        'performance': {
            'bundle_elapsed_ms': round((time.perf_counter() - started) * 1000.0, 3),
            'bundle_cache_hit': False,
        },
    }
    cache.set(bundle_cache_key, bundle)
    return bundle

def build_run_studio_context_packs(
    session: Session,
    *,
    thread: Thread,
    run_id: str | None = None,
    nodes: list[Node] | None = None,
    edges: list[Edge] | None = None,
) -> dict[str, Any]:
    nodes, edges = _graph_or_load(session, thread_id=thread.id, nodes=nodes, edges=edges)
    return build_thread_context_pack_summary(
        nodes=nodes,
        edges=edges,
        run_id=run_id,
    )


def build_run_studio_skill_usage(
    session: Session,
    *,
    thread: Thread,
    run_id: str | None = None,
    nodes: list[Node] | None = None,
    edges: list[Edge] | None = None,
) -> dict[str, Any]:
    nodes, edges = _graph_or_load(session, thread_id=thread.id, nodes=nodes, edges=edges)
    return build_thread_skill_usage_summary(
        nodes=nodes,
        edges=edges,
        run_id=run_id,
    )
