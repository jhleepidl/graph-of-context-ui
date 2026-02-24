from __future__ import annotations
import json
from typing import Any, Dict, List, Optional
from sqlmodel import Session, select

from app.models import Node, Edge

def jdump(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False)

def jload(s: str, default):
    try:
        return json.loads(s)
    except Exception:
        return default

def add_edge(thread_id: str, from_id: str, to_id: str, etype: str, payload: Optional[dict] = None) -> Edge:
    return Edge(
        thread_id=thread_id,
        from_id=from_id,
        to_id=to_id,
        type=etype,
        payload_json=jdump(payload or {}),
    )

def get_last_node(session: Session, thread_id: str) -> Optional[Node]:
    stmt = select(Node).where(Node.thread_id == thread_id).order_by(Node.created_at.desc()).limit(1)
    return session.exec(stmt).first()


def replace_ids_in_order(active_ids: List[str], old_id: str, new_ids: List[str]) -> List[str]:
    replaced = False
    expanded: List[str] = []

    for nid in active_ids:
        if nid == old_id:
            if not replaced:
                expanded.extend(new_ids)
                replaced = True
            continue
        expanded.append(nid)

    if not replaced:
        expanded.extend(new_ids)

    seen = set()
    out: List[str] = []
    for nid in expanded:
        if nid in seen:
            continue
        seen.add(nid)
        out.append(nid)
    return out


def compile_active_context(session: Session, thread_id: str, active_ids: List[str]) -> str:
    active_nodes: List[Node] = []
    seen_active = set()
    for nid in active_ids:
        if nid in seen_active:
            continue
        seen_active.add(nid)
        n = session.get(Node, nid)
        if not n or n.thread_id != thread_id:
            continue
        active_nodes.append(n)
    active_set = {n.id for n in active_nodes}

    parent_to_children: Dict[str, set] = {}

    for n in active_nodes:
        meta = jload(n.payload_json, {})
        parent_id = meta.get("parent_id")
        if isinstance(parent_id, str) and parent_id and parent_id in active_set:
            parent_to_children.setdefault(parent_id, set()).add(n.id)

    if active_set:
        edges = session.exec(
            select(Edge).where(
                Edge.thread_id == thread_id,
                Edge.type == "HAS_PART",
                Edge.from_id.in_(list(active_set)),
                Edge.to_id.in_(list(active_set)),
            )
        ).all()
        for e in edges:
            parent_to_children.setdefault(e.from_id, set()).add(e.to_id)

    excluded_parent_ids = {pid for pid, children in parent_to_children.items() if children}

    kept_nodes = [n for n in active_nodes if n.id not in excluded_parent_ids]

    parts: List[str] = []
    for n in kept_nodes:
        meta = jload(n.payload_json, {})
        head = f"[{n.type} {n.id[:6]} @ {n.created_at.isoformat()}]"
        if n.type == "Message":
            role = meta.get("role", "?")
            parts.append(f"{head} role={role}\n{n.text or ''}")
        elif n.type == "Fold":
            title = meta.get("title", "Fold")
            parts.append(f"{head} title={title}\n{n.text or ''}")
        else:
            parts.append(f"{head}\n{n.text or ''}")
    return "\n\n".join(parts).strip()
