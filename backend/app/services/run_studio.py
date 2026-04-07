from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models import ContextSet, Edge, MemoryConflict, MemoryNode, MemoryProjection, Node, Thread
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
from app.services.memory_graph import summarize_memory_conflicts
from app.services.runtime_scope import build_step_run_id_index


CLAIM_NODE_TYPES = {"Decision", "Assumption", "Plan", "Observation", "ContextSummary"}
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
) -> dict[str, Any]:
    context_set = _resolve_context_set(session, thread_id=thread.id, context_set_id=context_set_id)
    active_ids = _active_ids(context_set)
    nodes, edges = load_thread_graph(session, thread.id)
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
) -> dict[str, Any]:
    nodes, edges = load_thread_graph(session, thread.id)
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
            'trace_anchor_related': bool(anchor_node_id and anchor_node_id in node_ids),
        }
        conflict_by_id[conflict_id] = entry
        for node_id in node_ids:
            node_to_conflict_ids.setdefault(node_id, set()).add(conflict_id)

    memory_to_claim_ids: dict[str, set[str]] = {node_id: set() for node_id in memory_by_id}
    conflict_to_claim_ids: dict[str, set[str]] = {conflict_id: set() for conflict_id in conflict_by_id}
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
        for memory_node_id in linked_memory_ids:
            memory_to_claim_ids.setdefault(memory_node_id, set()).add(claim_node_id)
        for conflict_id in linked_conflict_ids:
            conflict_to_claim_ids.setdefault(conflict_id, set()).add(claim_node_id)
        entry = {
            'claim_node_id': claim_node_id,
            'claim_node_type': str(item.get('claim_node_type') or '').strip() or None,
            'claim_text': str(item.get('claim_text') or '').strip() or None,
            'related_memory_node_ids': linked_memory_ids,
            'related_conflict_ids': linked_conflict_ids,
            'related_evidence_node_ids': _clean_node_ids([row.get('id') for row in (item.get('evidence_nodes') or []) if isinstance(row, dict)]),
            'compare_node_ids': _clean_node_ids([
                claim_node_id,
                *linked_memory_ids,
                *[node_id for conflict_id in linked_conflict_ids for node_id in conflict_by_id.get(conflict_id, {}).get('node_ids', [])],
                *[row.get('id') for row in (item.get('evidence_nodes') or []) if isinstance(row, dict)],
            ]),
            'trace_anchor_related': bool(anchor_node_id and anchor_node_id in related_ids),
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
        if anchor_node_id and memory_node_id == anchor_node_id:
            entry['trace_anchor_related'] = True

    for conflict_id, claim_ids in conflict_to_claim_ids.items():
        entry = conflict_by_id.get(conflict_id)
        if not entry:
            continue
        entry['related_claim_node_ids'] = sorted(claim_ids)
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

    claim_links.sort(key=lambda item: (
        len(item.get('related_memory_node_ids') or []),
        len(item.get('related_conflict_ids') or []),
        float(item.get('score') or 0),
        str(item.get('claim_node_id') or ''),
    ), reverse=True)
    memory_links = sorted(
        memory_by_id.values(),
        key=lambda item: (
            len(item.get('related_claim_node_ids') or []),
            len(item.get('related_conflict_ids') or []),
            int(item.get('visible_projection_count') or 0),
            str(item.get('memory_node_id') or ''),
        ),
        reverse=True,
    )
    conflict_links = sorted(
        conflict_by_id.values(),
        key=lambda item: (
            len(item.get('related_claim_node_ids') or []),
            len(item.get('related_memory_node_ids') or []),
            int(bool(item.get('resolution_summary'))),
            str(item.get('conflict_id') or ''),
        ),
        reverse=True,
    )

    return {
        'run_id': str(evidence_obj.get('run_id') or memory_obj.get('run_id') or trace_obj.get('run_id') or '').strip() or None,
        'scope': str(evidence_obj.get('scope') or memory_obj.get('scope') or trace_obj.get('scope') or 'thread').strip() or 'thread',
        'anchor_node_id': anchor_node_id,
        'claim_links': claim_links[:24],
        'memory_links': memory_links[:24],
        'conflict_links': conflict_links[:24],
        'counts': {
            'claim_links': len(claim_links),
            'memory_links': len(memory_links),
            'conflict_links': len(conflict_links),
            'claims_with_memory_links': sum(1 for item in claim_links if item.get('related_memory_node_ids')),
            'claims_with_conflicts': sum(1 for item in claim_links if item.get('related_conflict_ids')),
            'memory_nodes_with_claims': sum(1 for item in memory_links if item.get('related_claim_node_ids')),
            'conflicts_with_claims': sum(1 for item in conflict_links if item.get('related_claim_node_ids')),
            'conflicts_with_resolution_rationale': sum(1 for item in conflict_links if item.get('resolution_summary')),
            'conflicts_with_suggested_resolution': sum(1 for item in conflict_links if item.get('suggested_resolution')),
            'conflicts_with_history': sum(1 for item in conflict_links if int(item.get('history_count') or 0) > 0),
            'conflicts_with_merge_history': sum(1 for item in conflict_links if int(item.get('merge_history_count') or 0) > 0),
            'conflict_history_events': sum(int(item.get('history_count') or 0) for item in conflict_links),
        },
        'anchor_related': {
            'claim_node_ids': [item['claim_node_id'] for item in claim_links if item.get('trace_anchor_related')],
            'memory_node_ids': [item['memory_node_id'] for item in memory_links if item.get('trace_anchor_related')],
            'conflict_ids': [item['conflict_id'] for item in conflict_links if item.get('trace_anchor_related')],
        },
    }

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
            'resolution_json': _jload(row.resolution_json, {}),
        }
        for row in conflict_rows
    ])
    return {
        'run_id': clean_run_id,
        'scope': 'run' if clean_run_id else 'thread',
        'projections': items,
        'projection_count': len(items),
        'conflicts': conflict_summary.get('items') or [],
        'conflict_count': conflict_summary.get('count') or 0,
        'conflict_status_counts': conflict_summary.get('status_counts') or {},
        'conflict_reason_counts': conflict_summary.get('reason_counts') or {},
    }


def build_run_studio_run_bundle(
    session: Session,
    *,
    thread: Thread,
    context_set_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    clean_run_id = str(run_id or '').strip() or None
    context_set = _resolve_context_set(session, thread_id=thread.id, context_set_id=context_set_id)
    evidence = build_run_studio_evidence(session, thread=thread, context_set_id=getattr(context_set, 'id', None), run_id=clean_run_id)
    context_packs = build_run_studio_context_packs(session, thread=thread, run_id=clean_run_id)
    skill_usage = build_run_studio_skill_usage(session, thread=thread, run_id=clean_run_id)
    memory_graph = build_run_studio_memory_graph(session, thread=thread, run_id=clean_run_id)
    trace_scope = build_run_studio_trace_scope(session, thread=thread, run_id=clean_run_id)
    cross_references = _build_run_bundle_cross_references(
        evidence=evidence,
        memory_graph=memory_graph,
        trace_scope=trace_scope,
    )
    return {
        'run_id': clean_run_id,
        'scope': 'run' if clean_run_id else 'thread',
        'context_set_id': getattr(context_set, 'id', None),
        'evidence': evidence,
        'context_packs': context_packs,
        'skill_usage': skill_usage,
        'memory_graph': memory_graph,
        'trace_scope': trace_scope,
        'cross_references': cross_references,
    }

def build_run_studio_context_packs(
    session: Session,
    *,
    thread: Thread,
    run_id: str | None = None,
) -> dict[str, Any]:
    nodes, edges = load_thread_graph(session, thread.id)
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
) -> dict[str, Any]:
    nodes, edges = load_thread_graph(session, thread.id)
    return build_thread_skill_usage_summary(
        nodes=nodes,
        edges=edges,
        run_id=run_id,
    )
