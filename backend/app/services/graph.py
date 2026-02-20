from __future__ import annotations
import json
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

def compile_active_context(session: Session, thread_id: str, active_ids: List[str]) -> str:
    parts: List[str] = []
    for nid in active_ids:
        n = session.get(Node, nid)
        if not n or n.thread_id != thread_id:
            continue
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
