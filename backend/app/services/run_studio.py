from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models import Agent, ContextSet, Conversation, ConversationAgent, Edge, Node, Thread
from app.services.context_decisions import build_context_decisions
from app.services.graph import compile_active_context_explain, load_thread_graph
from app.services.graph_projections import build_logical_projections


CLAIM_NODE_TYPES = {"Decision", "Assumption", "Plan", "Observation", "ContextSummary"}
EVIDENCE_EDGE_TYPES = {"SUPPORTS", "REFERENCES", "DEPENDS"}
CONFLICT_EDGE_TYPES = {"CONFLICTS", "CONTRADICTS"}


def _jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def _node_payload(node: Node | None) -> dict[str, Any]:
    if not node:
        return {}
    payload = _jload(node.payload_json, {})
    if isinstance(payload, dict):
        return payload
    return {}


def _short_text(value: str, max_len: int = 220) -> str:
    compact = " ".join(str(value or "").split())
    if len(compact) <= max_len:
        return compact
    return f"{compact[:max_len]}..."


def _created_sort_key(node: Node) -> tuple[str, str]:
    created_at = node.created_at.isoformat() if hasattr(node.created_at, "isoformat") else str(node.created_at or "")
    return created_at, node.id


def _normalize_status(raw: Any) -> str:
    clean = str(raw or "").strip().lower()
    if not clean:
        return "unknown"
    if clean in {"queued", "pending", "waiting"}:
        return "queued"
    if clean in {"running", "in_progress", "active"}:
        return "running"
    if clean in {"done", "completed", "success", "ok"}:
        return "done"
    if clean in {"error", "failed", "failure", "blocked"}:
        return "error"
    return clean


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


def _current_step(nodes: list[Node]) -> tuple[Node | None, str]:
    steps = [node for node in nodes if node.type == "Step"]
    steps.sort(key=_created_sort_key)
    running = [step for step in steps if _normalize_status(_node_payload(step).get("status")) == "running"]
    if running:
        return running[-1], "running"
    queued = [step for step in steps if _normalize_status(_node_payload(step).get("status")) == "queued"]
    if queued:
        return queued[-1], "queued"
    if steps:
        return steps[-1], _normalize_status(_node_payload(steps[-1]).get("status"))
    return None, "idle"


def _now_panel_summary(
    *,
    thread: Thread,
    nodes: list[Node],
    edges: list[Edge],
    active_ids: list[str],
) -> dict[str, Any]:
    current_step_node, current_step_status = _current_step(nodes)
    current_step_payload = _node_payload(current_step_node)
    latest_user = _latest_user_message(nodes)
    latest_user_payload = _node_payload(latest_user)
    run_nodes = [node for node in nodes if node.type == "Run"]
    run_nodes.sort(key=_created_sort_key)
    latest_run = run_nodes[-1] if run_nodes else None
    latest_run_payload = _node_payload(latest_run)

    pending_approval_nodes = []
    for node in nodes:
        payload = _node_payload(node)
        if payload.get("pending_approval") is True or payload.get("requires_approval") is True:
            pending_approval_nodes.append(node)
    pending_approval_nodes.sort(key=_created_sort_key)

    blocked_nodes = []
    for node in nodes:
        if node.type != "Step":
            continue
        payload = _node_payload(node)
        status = _normalize_status(payload.get("status"))
        if status in {"error", "blocked"} or str(payload.get("blocked_reason") or "").strip():
            blocked_nodes.append(node)
    blocked_nodes.sort(key=_created_sort_key)
    latest_blocked = blocked_nodes[-1] if blocked_nodes else None
    latest_blocked_payload = _node_payload(latest_blocked)

    step_status_counts: dict[str, int] = {}
    for node in nodes:
        if node.type != "Step":
            continue
        status = _normalize_status(_node_payload(node).get("status"))
        step_status_counts[status] = step_status_counts.get(status, 0) + 1

    run_status = "idle"
    if step_status_counts.get("running", 0) > 0:
        run_status = "running"
    elif step_status_counts.get("error", 0) > 0:
        run_status = "blocked"
    elif step_status_counts.get("queued", 0) > 0:
        run_status = "queued"
    elif step_status_counts:
        run_status = "done"

    current_task = str(
        latest_user.text
        if latest_user and latest_user.text
        else latest_run_payload.get("task")
        or latest_run_payload.get("goal")
        or thread.title
        or ""
    ).strip()
    current_objective = str(
        current_step_payload.get("goal")
        or current_step_payload.get("title")
        or latest_run_payload.get("goal")
        or latest_user.text
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
            "pending_approval": len(pending_approval_nodes) > 0,
            "pending_approval_count": len(pending_approval_nodes),
            "active_context_count": len(active_ids),
            "step_status_counts": step_status_counts,
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
        "latest_run": {
            "id": latest_run.id if latest_run else None,
            "created_at": latest_run.created_at if latest_run else None,
            "summary": _short_text(latest_run.text or str(latest_run_payload.get("summary") or ""), 280) if latest_run else None,
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _agent_team_summary(
    session: Session,
    *,
    thread_id: str,
    nodes: list[Node],
) -> dict[str, Any]:
    conversation = session.exec(
        select(Conversation)
        .where(Conversation.thread_id == thread_id)
        .limit(1)
    ).first()
    step_nodes = [node for node in nodes if node.type == "Step"]
    step_nodes.sort(key=_created_sort_key)

    step_activity_by_agent: dict[str, dict[str, int]] = {}
    for step in step_nodes:
        payload = _node_payload(step)
        agent_id = str(payload.get("agent_id") or payload.get("agent") or payload.get("assignee") or "").strip()
        if not agent_id:
            continue
        status = _normalize_status(payload.get("status"))
        by_status = step_activity_by_agent.setdefault(agent_id, {})
        by_status[status] = by_status.get(status, 0) + 1

    if not conversation:
        inferred_items = []
        for agent_id in sorted(step_activity_by_agent.keys()):
            status_counts = step_activity_by_agent.get(agent_id, {})
            runtime_status = "idle"
            if status_counts.get("running", 0) > 0:
                runtime_status = "running"
            elif status_counts.get("error", 0) > 0:
                runtime_status = "error"
            elif status_counts.get("queued", 0) > 0:
                runtime_status = "queued"
            elif sum(status_counts.values()) > 0:
                runtime_status = "done"
            inferred_items.append(
                {
                    "agent_id": agent_id,
                    "name": agent_id,
                    "enabled": True,
                    "order_index": None,
                    "runtime_status": runtime_status,
                    "status_counts": status_counts,
                    "responsibilities": [],
                    "source": "inferred_from_steps",
                }
            )
        return {
            "conversation_id": None,
            "items": inferred_items,
            "active_count": sum(1 for item in inferred_items if item["runtime_status"] in {"running", "queued"}),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    memberships = session.exec(
        select(ConversationAgent)
        .where(ConversationAgent.conversation_id == conversation.id)
        .order_by(ConversationAgent.order_index.asc(), ConversationAgent.created_at.asc(), ConversationAgent.id.asc())
    ).all()
    agent_ids = [row.agent_id for row in memberships]
    agents = session.exec(select(Agent).where(Agent.id.in_(agent_ids))).all() if agent_ids else []
    agents_by_id = {agent.id: agent for agent in agents}

    items: list[dict[str, Any]] = []
    for membership in memberships:
        agent = agents_by_id.get(membership.agent_id)
        overrides = _jload(membership.overrides_json, {})
        if not isinstance(overrides, dict):
            overrides = {}

        status_counts = step_activity_by_agent.get(membership.agent_id, {})
        if not status_counts and agent:
            status_counts = step_activity_by_agent.get(agent.name, {})
        runtime_status = "idle"
        if status_counts.get("running", 0) > 0:
            runtime_status = "running"
        elif status_counts.get("error", 0) > 0:
            runtime_status = "error"
        elif status_counts.get("queued", 0) > 0:
            runtime_status = "queued"
        elif sum(status_counts.values()) > 0:
            runtime_status = "done"

        raw_responsibilities = overrides.get("responsibilities") or overrides.get("responsibility") or []
        responsibilities: list[str] = []
        if isinstance(raw_responsibilities, str):
            clean = raw_responsibilities.strip()
            if clean:
                responsibilities = [clean]
        elif isinstance(raw_responsibilities, list):
            responsibilities = [str(item).strip() for item in raw_responsibilities if str(item).strip()]

        items.append(
            {
                "membership_id": membership.id,
                "agent_id": membership.agent_id,
                "name": agent.name if agent else membership.agent_id,
                "enabled": bool(membership.enabled),
                "order_index": int(membership.order_index),
                "runtime_status": runtime_status,
                "status_counts": status_counts,
                "responsibilities": responsibilities,
                "description": agent.description if agent else "",
                "model": agent.model if agent else "",
                "visibility": agent.visibility if agent else "",
            }
        )

    return {
        "conversation_id": conversation.id,
        "items": items,
        "active_count": sum(1 for item in items if item["runtime_status"] in {"running", "queued"}),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


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

    items: list[dict[str, Any]] = []
    for node in candidate_claim_nodes[-48:]:
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

        items.append(
            {
                "claim_node_id": node.id,
                "claim_node_type": node.type,
                "claim_text": _short_text(claim_text, 300),
                "created_at": node.created_at,
                "selected_in_context": node.id in set(active_ids),
                "evidence_nodes": evidence_nodes[:8],
                "provenance": provenance[:6],
                "uncertainty": uncertainty_notes[:6],
                "conflict_node_ids": sorted(set(conflict_node_ids))[:8],
            }
        )

    conflict_count = sum(1 for item in items if item["conflict_node_ids"])
    uncertain_count = sum(1 for item in items if item["uncertainty"])
    supported_count = sum(1 for item in items if item["evidence_nodes"])

    return {
        "items": items[-30:],
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
    context_decisions = _context_decisions_summary(
        session,
        thread_id=thread.id,
        context_set=context_set,
        nodes=nodes,
        edges=edges,
    )
    evidence = _evidence_summary(nodes=nodes, edges=edges, active_ids=active_ids)

    return {
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
        "projections": projections,
        "context_decisions_counts": context_decisions.get("counts", {}),
        "evidence_counts": evidence.get("counts", {}),
        "graph_counts": {
            "nodes": len(nodes),
            "edges": len(edges),
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_run_studio_agent_team(
    session: Session,
    *,
    thread: Thread,
) -> dict[str, Any]:
    nodes, _ = load_thread_graph(session, thread.id)
    return _agent_team_summary(session, thread_id=thread.id, nodes=nodes)


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
