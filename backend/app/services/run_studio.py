from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlmodel import Session, select

from app.models import Agent, ContextSet, Conversation, ConversationAgent, Edge, Node, Thread
from app.services.context_decisions import build_context_decisions
from app.services.graph import compile_active_context_explain, load_thread_graph
from app.services.graph_projections import build_logical_projections


CLAIM_NODE_TYPES = {"Decision", "Assumption", "Plan", "Observation", "ContextSummary"}
EVIDENCE_EDGE_TYPES = {"SUPPORTS", "REFERENCES", "DEPENDS"}
CONFLICT_EDGE_TYPES = {"CONFLICTS", "CONTRADICTS"}
RUNTIME_TEAM_KEYS = ("runtime_team_snapshot", "runtime_agents", "team_plan")


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


def _clean_list_of_text(value: Any, *, limit: int = 12) -> list[str]:
    if isinstance(value, str):
        clean = value.strip()
        return [clean] if clean else []
    if not isinstance(value, (list, tuple, set)):
        return []
    out: list[str] = []
    for item in value:
        clean = str(item or "").strip()
        if not clean:
            continue
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def _runtime_member_list(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, str):
        clean = raw.strip()
        if not clean:
            return []
        if clean.startswith("{") or clean.startswith("["):
            parsed = _jload(clean, None)
            if parsed is not None:
                return _runtime_member_list(parsed)
        return [{"agent_id": clean}]

    if isinstance(raw, list):
        out: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                out.append(item)
            elif isinstance(item, str) and item.strip():
                out.append({"agent_id": item.strip()})
        return out
    if isinstance(raw, dict):
        for key in ("agents", "members", "team", "items", "runtime_agents"):
            nested = raw.get(key)
            nested_items = _runtime_member_list(nested)
            if nested_items:
                return nested_items

        # Support keyed maps like {"planner": {...}, "critic": {...}}.
        map_items: list[dict[str, Any]] = []
        for map_key, value in raw.items():
            if isinstance(value, dict):
                enriched = dict(value)
                if not any(k in enriched for k in ("agent_id", "id", "runtime_instance_id", "instance_id", "name")):
                    enriched["agent_id"] = str(map_key)
                map_items.append(enriched)
            elif isinstance(value, str) and value.strip():
                map_items.append({"agent_id": str(map_key), "name": value.strip()})
        if map_items:
            return map_items

        has_member_shape = any(
            key in raw for key in ("id", "agent_id", "runtime_instance_id", "instance_id", "role", "role_label", "name")
        )
        if has_member_shape:
            return [raw]
    return []


def _extract_runtime_team_snapshot(nodes: list[Node]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    sorted_nodes = sorted([node for node in nodes if node.type in {"Run", "Step"}], key=_created_sort_key)
    for node in sorted_nodes:
        payload = _node_payload(node)
        containers: list[tuple[str, Any]] = [(key, payload.get(key)) for key in RUNTIME_TEAM_KEYS]
        for block_name in ("runtime", "meta", "result", "output", "state", "data"):
            block = payload.get(block_name)
            if isinstance(block, dict):
                containers.extend((f"{block_name}.{key}", block.get(key)) for key in RUNTIME_TEAM_KEYS)

        for source_key, raw in containers:
            members = _runtime_member_list(raw)
            if not members:
                continue
            candidates.append(
                {
                    "node_id": node.id,
                    "node_type": node.type,
                    "created_at": node.created_at,
                    "source_key": source_key,
                    "members": members,
                }
            )

    if not candidates:
        return None

    # Prefer the latest snapshot; tie-break by explicitness of source key.
    source_priority = {
        "runtime_team_snapshot": 3,
        "runtime.runtime_team_snapshot": 3,
        "meta.runtime_team_snapshot": 3,
        "runtime_agents": 2,
        "runtime.runtime_agents": 2,
        "meta.runtime_agents": 2,
        "team_plan": 1,
        "runtime.team_plan": 1,
        "meta.team_plan": 1,
    }
    candidates.sort(
        key=lambda item: (
            str(item.get("created_at") or ""),
            source_priority.get(str(item.get("source_key") or ""), 0),
            str(item.get("node_id") or ""),
        )
    )
    return candidates[-1]


def _step_activity_index(nodes: list[Node]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for step in sorted([node for node in nodes if node.type == "Step"], key=_created_sort_key):
        payload = _node_payload(step)
        status = _normalize_status(payload.get("status"))
        keys = {
            str(payload.get("agent_id") or "").strip(),
            str(payload.get("agent") or "").strip(),
            str(payload.get("assignee") or "").strip(),
            str(payload.get("runtime_instance_id") or "").strip(),
            str(payload.get("instance_id") or "").strip(),
            str(payload.get("executor_id") or "").strip(),
            str(payload.get("template_id") or "").strip(),
        }
        keys = {k for k in keys if k}
        for key in keys:
            row = out.setdefault(key, {})
            row[status] = row.get(status, 0) + 1
    return out


def _runtime_status_from_counts(status_counts: dict[str, int]) -> str:
    if status_counts.get("running", 0) > 0:
        return "running"
    if status_counts.get("error", 0) > 0:
        return "error"
    if status_counts.get("queued", 0) > 0:
        return "queued"
    if sum(status_counts.values()) > 0:
        return "done"
    return "idle"


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
    step_activity_by_agent = _step_activity_index(nodes)

    runtime_snapshot = _extract_runtime_team_snapshot(nodes)
    if runtime_snapshot:
        runtime_items: list[dict[str, Any]] = []
        for raw_member in runtime_snapshot.get("members", []):
            if not isinstance(raw_member, dict):
                continue
            llm_block = raw_member.get("llm")
            llm_info = llm_block if isinstance(llm_block, dict) else {}
            runtime_instance_id = str(raw_member.get("runtime_instance_id") or raw_member.get("instance_id") or "").strip() or None
            agent_id = str(raw_member.get("agent_id") or raw_member.get("id") or raw_member.get("agent") or "").strip() or None
            template_id = str(
                raw_member.get("template_id")
                or raw_member.get("agent_template_id")
                or raw_member.get("template")
                or ""
            ).strip() or None
            lookup_keys = [key for key in [runtime_instance_id, agent_id, template_id] if key]
            status_counts: dict[str, int] = {}
            for key in lookup_keys:
                source_counts = step_activity_by_agent.get(key, {})
                for status_key, count in source_counts.items():
                    status_counts[status_key] = status_counts.get(status_key, 0) + int(count)

            runtime_items.append(
                {
                    "agent_id": agent_id or runtime_instance_id or template_id or "unknown-runtime-agent",
                    "runtime_instance_id": runtime_instance_id,
                    "name": str(raw_member.get("name") or raw_member.get("display_name") or raw_member.get("label") or agent_id or runtime_instance_id or "").strip() or None,
                    "role_label": str(raw_member.get("role_label") or raw_member.get("role") or raw_member.get("title") or "").strip() or None,
                    "template_id": template_id,
                    "provider": str(raw_member.get("provider") or raw_member.get("llm_provider") or llm_info.get("provider") or "").strip() or None,
                    "model": str(raw_member.get("model") or raw_member.get("model_name") or llm_info.get("model") or "").strip() or None,
                    "runtime_status": _normalize_status(raw_member.get("runtime_status") or raw_member.get("status") or raw_member.get("state")) if (
                        raw_member.get("runtime_status") is not None
                        or raw_member.get("status") is not None
                        or raw_member.get("state") is not None
                    ) else _runtime_status_from_counts(status_counts),
                    "status_counts": status_counts,
                    "source": "runtime_snapshot",
                    "source_key": str(runtime_snapshot.get("source_key") or ""),
                    "snapshot_node_id": runtime_snapshot.get("node_id"),
                    "snapshot_node_type": runtime_snapshot.get("node_type"),
                    "enabled": bool(raw_member.get("enabled", True)),
                    "responsibilities": _clean_list_of_text(raw_member.get("responsibilities") or raw_member.get("responsibility")),
                    "capability_tags": _clean_list_of_text(raw_member.get("capability_tags") or raw_member.get("capabilities")),
                    "ephemeral": bool(raw_member.get("ephemeral") or raw_member.get("transient") or False),
                }
            )

        return {
            "conversation_id": conversation.id if conversation else None,
            "snapshot_node_id": runtime_snapshot.get("node_id"),
            "snapshot_node_type": runtime_snapshot.get("node_type"),
            "snapshot_source_key": runtime_snapshot.get("source_key"),
            "items": runtime_items,
            "active_count": sum(1 for item in runtime_items if item["runtime_status"] in {"running", "queued"}),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    if not conversation:
        inferred_items = []
        for agent_id in sorted(step_activity_by_agent.keys()):
            status_counts = step_activity_by_agent.get(agent_id, {})
            runtime_status = _runtime_status_from_counts(status_counts)
            inferred_items.append(
                {
                    "agent_id": agent_id,
                    "name": agent_id,
                    "runtime_instance_id": None,
                    "role_label": None,
                    "template_id": None,
                    "provider": None,
                    "model": None,
                    "enabled": True,
                    "order_index": None,
                    "runtime_status": runtime_status,
                    "status_counts": status_counts,
                    "responsibilities": [],
                    "capability_tags": [],
                    "ephemeral": False,
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
        runtime_status = _runtime_status_from_counts(status_counts)

        raw_responsibilities = overrides.get("responsibilities") or overrides.get("responsibility") or []
        responsibilities: list[str] = []
        if isinstance(raw_responsibilities, str):
            clean = raw_responsibilities.strip()
            if clean:
                responsibilities = [clean]
        elif isinstance(raw_responsibilities, list):
            responsibilities = [str(item).strip() for item in raw_responsibilities if str(item).strip()]

        role_label = str(
            overrides.get("role_label")
            or overrides.get("role")
            or overrides.get("title")
            or agent.name
            or ""
        ).strip() or None
        capability_tags = _clean_list_of_text(overrides.get("capability_tags") or overrides.get("capabilities"))
        if not capability_tags and agent:
            capability_tags = _clean_list_of_text(_jload(getattr(agent, "tools_json", "[]"), []))

        items.append(
            {
                "membership_id": membership.id,
                "agent_id": membership.agent_id,
                "name": agent.name if agent else membership.agent_id,
                "runtime_instance_id": None,
                "role_label": role_label,
                "template_id": str(overrides.get("template_id") or overrides.get("agent_template_id") or "").strip() or None,
                "provider": str(overrides.get("provider") or overrides.get("llm_provider") or "").strip() or None,
                "enabled": bool(membership.enabled),
                "order_index": int(membership.order_index),
                "runtime_status": runtime_status,
                "status_counts": status_counts,
                "responsibilities": responsibilities,
                "capability_tags": capability_tags,
                "ephemeral": bool(overrides.get("ephemeral") or False),
                "description": agent.description if agent else "",
                "model": agent.model if agent else "",
                "visibility": agent.visibility if agent else "",
                "source": "conversation_membership",
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
