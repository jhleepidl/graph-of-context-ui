from __future__ import annotations
import json
import logging
from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select

from app.db import engine
from app.models import Thread, ContextSet, ContextSetVersion, Node, Edge, NodeEmbedding
from app.schemas import ThreadCreate, NodeLayoutUpdate, EdgeCreate
from app.services.context_versions import snapshot_context_set
from app.services.embedding import rebuild_thread_index, remove_thread_index
from app.auth import get_current_principal
from app.tenant import current_service_id, require_node_access, require_thread_access

router = APIRouter(prefix="/api/threads", tags=["threads"])
logger = logging.getLogger(__name__)


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
    "RELATED",
    "SUPPORTS",
    "INVOKES",
    "RETURNS",
    "USES",
    "IN_RUN",
    "FOLDS",
    "USED_IN_RUN",
    "HAS_PART",
    "NEXT_PART",
    "SPLIT_FROM",
    "ATTACHED_TO",
    "REFERENCES",
    "DEPENDS",
}


@router.get("")
def list_threads():
    principal = get_current_principal()
    with Session(engine) as s:
        query = select(Thread).order_by(Thread.created_at.desc())
        if principal.role != "admin":
            query = query.where(Thread.service_id == current_service_id())
        threads = s.exec(query).all()
        return [t.model_dump() for t in threads]


@router.post("")
def create_thread(body: ThreadCreate):
    principal = get_current_principal()
    if principal.role == "admin":
        service_id = (body.service_id or "").strip()
        if not service_id:
            raise HTTPException(400, "admin must provide service_id")
    else:
        service_id = current_service_id()
    t = Thread(title=body.title or "Untitled", service_id=service_id)
    with Session(engine) as s:
        s.add(t)
        s.commit()
        s.refresh(t)
        cs = ContextSet(thread_id=t.id, name="default")
        s.add(cs)
        s.flush()
        snapshot_context_set(s, cs, reason="create", meta={"name": "default", "thread_id": t.id})
        s.commit()
    return t.model_dump()


@router.delete("/{thread_id}")
def delete_thread(thread_id: str):
    with Session(engine) as s:
        t = require_thread_access(s, thread_id)

        edges = s.exec(select(Edge).where(Edge.thread_id == thread_id)).all()
        nodes = s.exec(select(Node).where(Node.thread_id == thread_id)).all()
        ctx_sets = s.exec(select(ContextSet).where(ContextSet.thread_id == thread_id)).all()
        ctx_versions = s.exec(select(ContextSetVersion).where(ContextSetVersion.thread_id == thread_id)).all()
        embeddings = s.exec(select(NodeEmbedding).where(NodeEmbedding.thread_id == thread_id)).all()

        for e in edges:
            s.delete(e)
        for ne in embeddings:
            s.delete(ne)
        for v in ctx_versions:
            s.delete(v)
        for n in nodes:
            s.delete(n)
        for cs in ctx_sets:
            s.delete(cs)
        s.delete(t)
        s.commit()

    warning = None
    try:
        remove_thread_index(thread_id)
    except Exception as e:
        warning = f"thread index cleanup failed: {e}"
        logger.exception("thread index cleanup failed (thread_id=%s)", thread_id)

    return {
        "ok": True,
        "deleted_thread_id": thread_id,
        "deleted_node_count": len(nodes),
        "deleted_edge_count": len(edges),
        "deleted_context_set_count": len(ctx_sets),
        "deleted_context_version_count": len(ctx_versions),
        "deleted_embedding_count": len(embeddings),
        "warning": warning,
    }


@router.get("/{thread_id}/graph")
def get_graph(thread_id: str):
    with Session(engine) as s:
        t = require_thread_access(s, thread_id)
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
        require_thread_access(s, thread_id)

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
        require_thread_access(s, thread_id)

        src = require_node_access(s, body.from_id)
        dst = require_node_access(s, body.to_id)
        if src.thread_id != thread_id:
            raise HTTPException(404, "source node not found in thread")
        if dst.thread_id != thread_id:
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
        require_thread_access(s, thread_id)

        e = s.get(Edge, edge_id)
        if not e or e.thread_id != thread_id:
            raise HTTPException(404, "edge not found")

        s.delete(e)
        s.commit()
        return {"ok": True, "deleted_edge_id": edge_id}


@router.delete("/{thread_id}/nodes/{node_id}")
def delete_node(thread_id: str, node_id: str):
    with Session(engine) as s:
        require_thread_access(s, thread_id)

        n = require_node_access(s, node_id)
        if n.thread_id != thread_id:
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
            snapshot_context_set(s, cs, reason="delete_node", changed_node_ids=[node_id], meta={"deleted_node_id": node_id})

        ne = s.get(NodeEmbedding, node_id)
        if ne:
            s.delete(ne)

        s.delete(n)
        s.commit()
        warning = None
        try:
            rebuild_thread_index(s, thread_id)
        except Exception as e:
            warning = f"index rebuild failed: {e}"
            logger.exception("index rebuild failed after node delete (thread_id=%s, node_id=%s)", thread_id, node_id)
        return {
            "ok": True,
            "deleted_node_id": node_id,
            "deleted_edge_count": len(edge_by_id),
            "warning": warning,
        }


@router.post("/{thread_id}/rebuild_index")
def rebuild_index(thread_id: str):
    with Session(engine) as s:
        require_thread_access(s, thread_id)
        stats = rebuild_thread_index(s, thread_id)
        return {"ok": True, "rebuild": stats}
