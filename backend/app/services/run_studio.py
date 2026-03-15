from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models import ContextSet, Edge, Node, Thread
from app.services.conversation_team import build_conversation_team_projection
from app.services.context_decisions import build_context_decisions
from app.services.graph import compile_active_context_explain, load_thread_graph
from app.services.graph_projections import build_logical_projections
from app.services.resolved_runtime import resolve_runtime_projection, resolve_runtime_scope_state
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
) -> dict[str, Any]:
    context_set = _resolve_context_set(session, thread_id=thread.id, context_set_id=context_set_id)
    active_ids = _active_ids(context_set)
    nodes, edges = load_thread_graph(session, thread.id)
    return _evidence_summary(nodes=nodes, edges=edges, active_ids=active_ids)


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
