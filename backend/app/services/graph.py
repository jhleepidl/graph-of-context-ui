from __future__ import annotations
import json
from typing import Any, Dict, List, Optional, Sequence, Tuple
from sqlmodel import Session, select

from app.goc_core import compile_active_context_records
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


def load_thread_graph(session: Session, thread_id: str) -> Tuple[List[Node], List[Edge]]:
    nodes = session.exec(
        select(Node)
        .where(Node.thread_id == thread_id)
        .order_by(Node.created_at.asc(), Node.id.asc())
    ).all()
    edges = session.exec(
        select(Edge)
        .where(Edge.thread_id == thread_id)
        .order_by(Edge.created_at.asc(), Edge.id.asc())
    ).all()
    return nodes, edges


def _active_nodes_and_edges(session: Session, thread_id: str, active_ids: Sequence[str]) -> Tuple[List[Node], List[Edge]]:
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

    edges: List[Edge] = []
    if active_set:
        edges = session.exec(
            select(Edge).where(
                Edge.thread_id == thread_id,
                Edge.type.in_(["HAS_PART"]),
                Edge.from_id.in_(list(active_set)),
                Edge.to_id.in_(list(active_set)),
            )
        ).all()
    return active_nodes, edges


def compile_active_context_explain(session: Session, thread_id: str, active_ids: List[str]) -> Dict[str, Any]:
    active_nodes, edges = _active_nodes_and_edges(session, thread_id, active_ids)
    text, explain = compile_active_context_records(
        records=[
            {
                "id": n.id,
                "type": n.type,
                "text": n.text,
                "payload_json": n.payload_json,
                "created_at": n.created_at,
            }
            for n in active_nodes
        ],
        active_ids=active_ids,
        edges=[{"from_id": e.from_id, "to_id": e.to_id, "type": e.type} for e in edges],
    )
    return {
        "compiled_text": text,
        "explain": explain,
    }


def compile_active_context(session: Session, thread_id: str, active_ids: List[str]) -> str:
    return compile_active_context_explain(session, thread_id, active_ids)["compiled_text"]
