from __future__ import annotations
import json
from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select

from app.db import engine
from app.models import Thread, ContextSet, Node, Edge, NodeEmbedding
from app.schemas import ThreadCreate, NodeLayoutUpdate, EdgeCreate
from app.services.graph import add_edge, get_last_node

router = APIRouter(prefix="/api/threads", tags=["threads"])


def jdump(x):
    return json.dumps(x, ensure_ascii=False)


def jload(s: str, default):
    try:
        return json.loads(s)
    except Exception:
        return default


ALLOWED_EDGE_TYPES = {
    "NEXT",
    "REPLY_TO",
    "INVOKES",
    "RETURNS",
    "USES",
    "IN_RUN",
    "FOLDS",
    "USED_IN_RUN",
    "HAS_PART",
    "NEXT_PART",
    "SPLIT_FROM",
}

@router.get("")
def list_threads():
    with Session(engine) as s:
        threads = s.exec(select(Thread).order_by(Thread.created_at.desc())).all()
        return [t.model_dump() for t in threads]

@router.post("")
def create_thread(body: ThreadCreate):
    t = Thread(title=body.title or "Untitled")
    with Session(engine) as s:
        s.add(t)
        s.commit()
        s.refresh(t)
        # default context set
        cs = ContextSet(thread_id=t.id, name="default")
        s.add(cs)
        s.commit()
    return t.model_dump()

@router.get("/{thread_id}/graph")
def get_graph(thread_id: str):
    with Session(engine) as s:
        t = s.get(Thread, thread_id)
        if not t:
            raise HTTPException(404, "thread not found")
        nodes = s.exec(
            select(Node)
            .where(Node.thread_id == thread_id)
            .order_by(Node.created_at.asc(), Node.id.asc())
        ).all()
        edges = s.exec(
            select(Edge)
            .where(Edge.thread_id == thread_id)
            .order_by(Edge.created_at.asc(), Edge.id.asc())
        ).all()
        return {
            "thread": t.model_dump(),
            "nodes": [n.model_dump() for n in nodes],
            "edges": [e.model_dump() for e in edges],
        }


@router.post("/{thread_id}/layout")
def save_layout(thread_id: str, body: NodeLayoutUpdate):
    with Session(engine) as s:
        t = s.get(Thread, thread_id)
        if not t:
            raise HTTPException(404, "thread not found")

        ids = [p.id for p in body.positions]
        if not ids:
            return {"ok": True, "updated": 0}

        nodes = s.exec(
            select(Node)
            .where(Node.thread_id == thread_id)
            .where(Node.id.in_(ids))
        ).all()
        by_id = {n.id: n for n in nodes}

        updated = 0
        for p in body.positions:
            n = by_id.get(p.id)
            if not n:
                continue
            payload = jload(n.payload_json, {})
            payload["_ui_pos"] = {"x": float(p.x), "y": float(p.y)}
            n.payload_json = jdump(payload)
            s.add(n)
            updated += 1

        s.commit()
        return {"ok": True, "updated": updated}


@router.post("/{thread_id}/edges")
def create_edge(thread_id: str, body: EdgeCreate):
    if body.type not in ALLOWED_EDGE_TYPES:
        raise HTTPException(400, f"invalid edge type: {body.type}")

    with Session(engine) as s:
        t = s.get(Thread, thread_id)
        if not t:
            raise HTTPException(404, "thread not found")

        src = s.get(Node, body.from_id)
        dst = s.get(Node, body.to_id)
        if not src or src.thread_id != thread_id:
            raise HTTPException(404, "source node not found in thread")
        if not dst or dst.thread_id != thread_id:
            raise HTTPException(404, "target node not found in thread")

        existing = s.exec(
            select(Edge)
            .where(Edge.thread_id == thread_id)
            .where(Edge.from_id == body.from_id)
            .where(Edge.to_id == body.to_id)
            .where(Edge.type == body.type)
            .limit(1)
        ).first()
        if existing:
            return existing.model_dump()

        e = Edge(
            thread_id=thread_id,
            from_id=body.from_id,
            to_id=body.to_id,
            type=body.type,
            payload_json=jdump({}),
        )
        s.add(e)
        s.commit()
        s.refresh(e)
        return e.model_dump()


@router.delete("/{thread_id}/edges/{edge_id}")
def delete_edge(thread_id: str, edge_id: str):
    with Session(engine) as s:
        t = s.get(Thread, thread_id)
        if not t:
            raise HTTPException(404, "thread not found")

        e = s.get(Edge, edge_id)
        if not e or e.thread_id != thread_id:
            raise HTTPException(404, "edge not found")

        s.delete(e)
        s.commit()
        return {"ok": True, "deleted_edge_id": edge_id}


@router.delete("/{thread_id}/nodes/{node_id}")
def delete_node(thread_id: str, node_id: str):
    with Session(engine) as s:
        t = s.get(Thread, thread_id)
        if not t:
            raise HTTPException(404, "thread not found")

        n = s.get(Node, node_id)
        if not n or n.thread_id != thread_id:
            raise HTTPException(404, "node not found")

        outgoing = s.exec(
            select(Edge)
            .where(Edge.thread_id == thread_id)
            .where(Edge.from_id == node_id)
        ).all()
        incoming = s.exec(
            select(Edge)
            .where(Edge.thread_id == thread_id)
            .where(Edge.to_id == node_id)
        ).all()
        edge_by_id = {e.id: e for e in outgoing}
        for e in incoming:
            edge_by_id[e.id] = e
        for e in edge_by_id.values():
            s.delete(e)

        sets = s.exec(select(ContextSet).where(ContextSet.thread_id == thread_id)).all()
        for cs in sets:
            active = jload(cs.active_node_ids_json, [])
            next_active = [nid for nid in active if nid != node_id]
            if len(next_active) == len(active):
                continue
            cs.active_node_ids_json = jdump(next_active)
            s.add(cs)

        ne = s.get(NodeEmbedding, node_id)
        if ne:
            s.delete(ne)

        s.delete(n)
        s.commit()
        return {
            "ok": True,
            "deleted_node_id": node_id,
            "deleted_edge_count": len(edge_by_id),
        }
