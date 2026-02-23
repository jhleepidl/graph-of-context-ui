from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
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

def _parse_dt(v: Any) -> Optional[datetime]:
    if not isinstance(v, str):
        return None
    s = v.strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default

def compile_active_context(session: Session, thread_id: str, active_ids: List[str]) -> str:
    active_nodes: List[Node] = []
    active_set = set(active_ids)

    for nid in active_ids:
        n = session.get(Node, nid)
        if not n or n.thread_id != thread_id:
            continue
        active_nodes.append(n)

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

    def sort_key(n: Node):
        meta = jload(n.payload_json, {})
        origin_dt = _parse_dt(meta.get("origin_created_at"))
        chunk_index = meta.get("chunk_index")
        if origin_dt is not None and chunk_index is not None:
            return (origin_dt, _to_int(chunk_index, 0), n.created_at, n.id)
        return (n.created_at, 0, n.created_at, n.id)

    kept_nodes.sort(key=sort_key)

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
