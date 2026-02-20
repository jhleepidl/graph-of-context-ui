from __future__ import annotations
import json
from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select

from app.db import engine
from app.models import ContextSet, Thread
from app.schemas import ContextSetCreate, ActivateNodes, ActiveOrderUpdate

router = APIRouter(prefix="/api", tags=["context_sets"])

def jdump(x) -> str:
    return json.dumps(x, ensure_ascii=False)

def jload(s: str, default):
    try:
        return json.loads(s)
    except Exception:
        return default

@router.get("/threads/{thread_id}/context_sets")
def list_context_sets(thread_id: str):
    with Session(engine) as s:
        sets = s.exec(
            select(ContextSet)
            .where(ContextSet.thread_id == thread_id)
            .order_by(ContextSet.created_at.asc())
        ).all()
        return [c.model_dump() for c in sets]

@router.post("/context_sets")
def create_context_set(body: ContextSetCreate):
    cs = ContextSet(thread_id=body.thread_id, name=body.name)
    with Session(engine) as s:
        t = s.get(Thread, body.thread_id)
        if not t:
            raise HTTPException(404, "thread not found")
        s.add(cs)
        s.commit()
        s.refresh(cs)
    return cs.model_dump()

@router.get("/context_sets/{context_set_id}")
def get_context_set(context_set_id: str):
    with Session(engine) as s:
        cs = s.get(ContextSet, context_set_id)
        if not cs:
            raise HTTPException(404, "context set not found")
        d = cs.model_dump()
        d["active_node_ids"] = jload(cs.active_node_ids_json, [])
        return d

@router.post("/context_sets/{context_set_id}/activate")
def activate_nodes(context_set_id: str, body: ActivateNodes):
    with Session(engine) as s:
        cs = s.get(ContextSet, context_set_id)
        if not cs:
            raise HTTPException(404, "context set not found")
        active = jload(cs.active_node_ids_json, [])
        seen = set(active)
        for nid in body.node_ids:
            if nid in seen:
                continue
            active.append(nid)
            seen.add(nid)
        cs.active_node_ids_json = jdump(active)
        s.add(cs)
        s.commit()
        return {"ok": True, "active_node_ids": active}

@router.post("/context_sets/{context_set_id}/deactivate")
def deactivate_nodes(context_set_id: str, body: ActivateNodes):
    with Session(engine) as s:
        cs = s.get(ContextSet, context_set_id)
        if not cs:
            raise HTTPException(404, "context set not found")
        remove_set = set(body.node_ids)
        active = [nid for nid in jload(cs.active_node_ids_json, []) if nid not in remove_set]
        cs.active_node_ids_json = jdump(active)
        s.add(cs)
        s.commit()
        return {"ok": True, "active_node_ids": active}


@router.post("/context_sets/{context_set_id}/reorder")
def reorder_nodes(context_set_id: str, body: ActiveOrderUpdate):
    with Session(engine) as s:
        cs = s.get(ContextSet, context_set_id)
        if not cs:
            raise HTTPException(404, "context set not found")

        current = jload(cs.active_node_ids_json, [])
        current_set = set(current)
        seen = set()
        reordered = []

        for nid in body.node_ids:
            if nid in current_set and nid not in seen:
                reordered.append(nid)
                seen.add(nid)

        for nid in current:
            if nid not in seen:
                reordered.append(nid)
                seen.add(nid)

        cs.active_node_ids_json = jdump(reordered)
        s.add(cs)
        s.commit()
        return {"ok": True, "active_node_ids": reordered}
