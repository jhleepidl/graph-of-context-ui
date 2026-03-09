from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Any, Iterable


RUN_STEP_LINK_EDGE_TYPES = {"BELONGS_TO_RUN", "IN_RUN"}
CONTEXT_NODE_TYPES = {
    "Decision",
    "Assumption",
    "Plan",
    "ContextCandidate",
    "MemoryItem",
    "Observation",
    "ContextSummary",
    "Fold",
    "Resource",
    "Artifact",
    "Message",
    "Step",
    "Run",
    "ToolCall",
    "ToolResult",
}
CORE_CONTEXT_NODE_TYPES = {
    "Decision",
    "Assumption",
    "Plan",
    "MemoryItem",
    "Observation",
    "ContextSummary",
}
SUPPORTING_CONTEXT_NODE_TYPES = {
    "Artifact",
    "Resource",
    "ContextCandidate",
}
EXECUTION_CONTEXT_NODE_TYPES = {
    "Step",
    "Message",
    "Fold",
    "Run",
    "ToolCall",
    "ToolResult",
}


def _jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def _node_payload(node: Any) -> dict[str, Any]:
    payload = _jload(getattr(node, "payload_json", "{}"), {})
    if isinstance(payload, dict):
        return payload
    return {}


def _created_sort_key(node: Any) -> tuple[str, str]:
    created_at = getattr(node, "created_at", None)
    if isinstance(created_at, datetime):
        return created_at.isoformat(), str(getattr(node, "id", ""))
    return str(created_at or ""), str(getattr(node, "id", ""))


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


def conversation_projection(nodes: Iterable[Any], edges: Iterable[Any]) -> dict[str, Any]:
    message_nodes = [n for n in nodes if str(getattr(n, "type", "")) == "Message"]
    message_nodes.sort(key=_created_sort_key)
    message_ids = {str(n.id) for n in message_nodes}
    message_payload_by_id = {str(n.id): _node_payload(n) for n in message_nodes}

    outgoing_next: dict[str, list[str]] = defaultdict(list)
    outgoing_reply: dict[str, list[str]] = defaultdict(list)
    incoming_reply: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        src = str(getattr(edge, "from_id", "") or "")
        dst = str(getattr(edge, "to_id", "") or "")
        etype = str(getattr(edge, "type", "") or "")
        if src not in message_ids or dst not in message_ids:
            continue
        if etype == "NEXT":
            outgoing_next[src].append(dst)
        elif etype == "REPLY_TO":
            outgoing_reply[src].append(dst)
            incoming_reply[dst].append(src)

    items: list[dict[str, Any]] = []
    participants: set[str] = set()
    for node in message_nodes:
        nid = str(node.id)
        payload = message_payload_by_id.get(nid, {})
        role = str(payload.get("role") or "").strip() or "unknown"
        participants.add(role)
        items.append(
            {
                "id": nid,
                "role": role,
                "text": str(getattr(node, "text", "") or ""),
                "created_at": getattr(node, "created_at", None),
                "next_ids": outgoing_next.get(nid, []),
                "reply_to_ids": outgoing_reply.get(nid, []),
                "reply_from_ids": incoming_reply.get(nid, []),
            }
        )

    latest_user = next((item for item in reversed(items) if item.get("role") == "user"), None)
    latest_assistant = next((item for item in reversed(items) if item.get("role") == "assistant"), None)
    return {
        "message_count": len(items),
        "participant_roles": sorted(participants),
        "latest_user_message_id": latest_user.get("id") if latest_user else None,
        "latest_assistant_message_id": latest_assistant.get("id") if latest_assistant else None,
        "recent_messages": items[-12:],
    }


def execution_projection(nodes: Iterable[Any], edges: Iterable[Any]) -> dict[str, Any]:
    nodes_list = list(nodes)
    nodes_by_id = {str(n.id): n for n in nodes_list}
    payload_by_id = {str(n.id): _node_payload(n) for n in nodes_list}

    run_nodes = [n for n in nodes_list if str(getattr(n, "type", "")) == "Run"]
    step_nodes = [n for n in nodes_list if str(getattr(n, "type", "")) == "Step"]
    tool_nodes = [n for n in nodes_list if str(getattr(n, "type", "")) in {"ToolCall", "ToolResult"}]
    artifact_nodes = [n for n in nodes_list if str(getattr(n, "type", "")) in {"Artifact", "Resource"}]

    run_to_steps: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        src = str(getattr(edge, "from_id", "") or "")
        dst = str(getattr(edge, "to_id", "") or "")
        etype = str(getattr(edge, "type", "") or "")
        if etype not in RUN_STEP_LINK_EDGE_TYPES:
            continue
        src_node = nodes_by_id.get(src)
        dst_node = nodes_by_id.get(dst)
        if not src_node or not dst_node:
            continue
        src_type = str(getattr(src_node, "type", "") or "")
        dst_type = str(getattr(dst_node, "type", "") or "")
        if src_type == "Run" and dst_type == "Step":
            run_to_steps[src].add(dst)
        elif src_type == "Step" and dst_type == "Run":
            run_to_steps[dst].add(src)

    for step in step_nodes:
        payload = payload_by_id.get(str(step.id), {})
        payload_run_id = str(payload.get("run_id") or "").strip()
        if payload_run_id and payload_run_id in nodes_by_id:
            run_to_steps[payload_run_id].add(str(step.id))

    step_items: list[dict[str, Any]] = []
    for step in sorted(step_nodes, key=_created_sort_key):
        payload = payload_by_id.get(str(step.id), {})
        status = _normalize_status(payload.get("status"))
        step_items.append(
            {
                "id": str(step.id),
                "run_id": str(payload.get("run_id") or "").strip() or None,
                "status": status,
                "agent_id": str(payload.get("agent_id") or payload.get("agent") or payload.get("assignee") or "").strip() or None,
                "goal": str(payload.get("goal") or payload.get("title") or getattr(step, "text", "") or "").strip(),
                "created_at": getattr(step, "created_at", None),
                "started_at": payload.get("started_at"),
                "ended_at": payload.get("ended_at"),
            }
        )

    running_step = next((item for item in reversed(step_items) if item.get("status") == "running"), None)
    if not running_step and step_items:
        running_step = step_items[-1]

    run_items: list[dict[str, Any]] = []
    for run in sorted(run_nodes, key=_created_sort_key):
        run_id = str(run.id)
        step_ids = sorted(run_to_steps.get(run_id, set()))
        step_statuses = [_normalize_status(payload_by_id.get(step_id, {}).get("status")) for step_id in step_ids]
        status = "done"
        if any(s == "running" for s in step_statuses):
            status = "running"
        elif any(s in {"error", "blocked"} for s in step_statuses):
            status = "error"
        elif any(s == "queued" for s in step_statuses):
            status = "queued"
        run_items.append(
            {
                "id": run_id,
                "status": status,
                "step_count": len(step_ids),
                "running_step_count": sum(1 for s in step_statuses if s == "running"),
                "error_step_count": sum(1 for s in step_statuses if s in {"error", "blocked"}),
                "created_at": getattr(run, "created_at", None),
                "text": str(getattr(run, "text", "") or ""),
            }
        )

    return {
        "run_count": len(run_items),
        "step_count": len(step_items),
        "tool_count": len(tool_nodes),
        "artifact_count": len(artifact_nodes),
        "current_step": running_step,
        "recent_runs": run_items[-8:],
        "recent_steps": step_items[-20:],
    }


def memory_context_projection(
    nodes: Iterable[Any],
    edges: Iterable[Any],
    *,
    active_node_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    nodes_list = list(nodes)
    active_set = {str(nid) for nid in (active_node_ids or []) if isinstance(nid, str)}
    payload_by_id = {str(n.id): _node_payload(n) for n in nodes_list}
    context_nodes = [n for n in nodes_list if str(getattr(n, "type", "")) in CONTEXT_NODE_TYPES]
    context_nodes.sort(key=_created_sort_key)

    core_items: list[dict[str, Any]] = []
    supporting_items: list[dict[str, Any]] = []
    execution_items: list[dict[str, Any]] = []
    for node in context_nodes:
        nid = str(node.id)
        payload = payload_by_id.get(nid, {})
        pin_level = str(payload.get("pin_level") or "").strip().lower()
        is_pinned = pin_level in {"required", "preferred"} or bool(payload.get("pinned") or payload.get("is_pinned"))
        text = str(getattr(node, "text", "") or "").strip()
        item_type = str(getattr(node, "type", "") or "Unknown")
        item = {
            "id": nid,
            "type": item_type,
            "text": text,
            "created_at": getattr(node, "created_at", None),
            "selected": nid in active_set,
            "pinned": is_pinned,
            "pin_level": pin_level or None,
            "category": "core" if item_type in CORE_CONTEXT_NODE_TYPES else (
                "supporting" if item_type in SUPPORTING_CONTEXT_NODE_TYPES else "execution"
            ),
        }
        if item_type in CORE_CONTEXT_NODE_TYPES:
            core_items.append(item)
        elif item_type in SUPPORTING_CONTEXT_NODE_TYPES:
            supporting_items.append(item)
        else:
            execution_items.append(item)

    all_items = core_items + supporting_items + execution_items

    conflicts: list[dict[str, Any]] = []
    supports: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    for edge in edges:
        src = str(getattr(edge, "from_id", "") or "")
        dst = str(getattr(edge, "to_id", "") or "")
        etype = str(getattr(edge, "type", "") or "")
        if etype in {"CONFLICTS", "CONTRADICTS"}:
            conflicts.append({"from_id": src, "to_id": dst, "type": etype})
        elif etype == "SUPPORTS":
            supports.append({"from_id": src, "to_id": dst, "type": etype})
        elif etype in {"REFERENCES", "DEPENDS"}:
            references.append({"from_id": src, "to_id": dst, "type": etype})

    return {
        "context_node_count": len(all_items),
        "core_count": len(core_items),
        "supporting_count": len(supporting_items),
        "execution_count": len(execution_items),
        "selected_count": sum(1 for item in all_items if item["selected"]),
        "pinned_count": sum(1 for item in all_items if item["pinned"]),
        "conflict_count": len(conflicts),
        "support_count": len(supports),
        "reference_count": len(references),
        "core_items": core_items[-30:],
        "supporting_items": supporting_items[-30:],
        "execution_items": execution_items[-30:],
        "recent_items": (core_items + supporting_items)[-30:],
        "conflicts": conflicts[-20:],
        "supports": supports[-30:],
        "references": references[-40:],
    }


def build_logical_projections(
    nodes: Iterable[Any],
    edges: Iterable[Any],
    *,
    active_node_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    return {
        "conversation": conversation_projection(nodes, edges),
        "execution": execution_projection(nodes, edges),
        "memory_context": memory_context_projection(nodes, edges, active_node_ids=active_node_ids),
    }
