from __future__ import annotations
import json
from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session, select

from app.db import engine
from app.goc_core import apply_unfold_seed_selection, plan_unfold_candidates
from app.models import ContextSet, ContextSetVersion
from app.schemas import (
    ContextSetCreate,
    ActivateNodes,
    ActiveOrderUpdate,
    UnfoldPlanRequest,
    ApplyUnfoldPlanRequest,
)
from app.services.context_versions import snapshot_context_set
from app.services.graph import compile_active_context_explain, load_thread_graph
from app.tenant import require_context_set_access, require_node_access, require_thread_access

router = APIRouter(prefix="/api", tags=["context_sets"])

_DEFAULT_PLANNER_EDGES = ["DEPENDS", "HAS_PART", "SPLIT_FROM", "REFERENCES"]


def jdump(x) -> str:
    return json.dumps(x, ensure_ascii=False)


def jload(s: str, default):
    try:
        return json.loads(s)
    except Exception:
        return default


def _validate_node_ids(session: Session, thread_id: str, node_ids: list[str]) -> list[str]:
    seen = set()
    valid: list[str] = []
    for nid in node_ids:
        if not nid or nid in seen:
            continue
        seen.add(nid)
        n = require_node_access(session, nid)
        if n.thread_id != thread_id:
            raise HTTPException(404, f"node not found in thread: {nid}")
        valid.append(nid)
    return valid


def _version_payload(row: ContextSetVersion) -> dict:
    d = row.model_dump()
    d["active_node_ids"] = jload(row.active_node_ids_json, [])
    d["changed_node_ids"] = jload(row.changed_node_ids_json, [])
    d["meta"] = jload(row.meta_json, {})
    return d


@router.get("/threads/{thread_id}/context_sets")
def list_context_sets(thread_id: str):
    with Session(engine) as s:
        require_thread_access(s, thread_id)
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
        require_thread_access(s, body.thread_id)
        s.add(cs)
        s.flush()
        snapshot_context_set(s, cs, reason="create", meta={"name": cs.name})
        s.commit()
        s.refresh(cs)
    return cs.model_dump()


@router.get("/context_sets/{context_set_id}")
def get_context_set(context_set_id: str):
    with Session(engine) as s:
        cs = require_context_set_access(s, context_set_id)
        d = cs.model_dump()
        d["active_node_ids"] = jload(cs.active_node_ids_json, [])
        return d


@router.get("/context_sets/{context_set_id}/versions")
def list_context_set_versions(context_set_id: str, limit: int = Query(default=20, ge=1, le=200)):
    with Session(engine) as s:
        require_context_set_access(s, context_set_id)
        rows = s.exec(
            select(ContextSetVersion)
            .where(ContextSetVersion.context_set_id == context_set_id)
            .order_by(ContextSetVersion.version.desc())
            .limit(limit)
        ).all()
        return {"ok": True, "versions": [_version_payload(r) for r in rows]}


@router.get("/context_sets/{context_set_id}/versions/{version}")
def get_context_set_version(context_set_id: str, version: int):
    with Session(engine) as s:
        require_context_set_access(s, context_set_id)
        row = s.exec(
            select(ContextSetVersion)
            .where(ContextSetVersion.context_set_id == context_set_id)
            .where(ContextSetVersion.version == version)
            .limit(1)
        ).first()
        if not row:
            raise HTTPException(404, "context set version not found")
        return {"ok": True, "version": _version_payload(row)}


@router.get("/context_sets/{context_set_id}/diff")
def diff_context_set_versions(context_set_id: str, from_version: int, to_version: int):
    with Session(engine) as s:
        require_context_set_access(s, context_set_id)
        rows = s.exec(
            select(ContextSetVersion)
            .where(ContextSetVersion.context_set_id == context_set_id)
            .where(ContextSetVersion.version.in_([from_version, to_version]))
        ).all()
        by_version = {int(r.version): r for r in rows}
        src = by_version.get(int(from_version))
        dst = by_version.get(int(to_version))
        if not src or not dst:
            raise HTTPException(404, "one or both versions not found")

        src_ids = jload(src.active_node_ids_json, [])
        dst_ids = jload(dst.active_node_ids_json, [])
        src_set = set(src_ids)
        dst_set = set(dst_ids)
        added = [nid for nid in dst_ids if nid not in src_set]
        removed = [nid for nid in src_ids if nid not in dst_set]
        kept = [nid for nid in dst_ids if nid in src_set]
        moved = []
        pos_src = {nid: idx for idx, nid in enumerate(src_ids)}
        pos_dst = {nid: idx for idx, nid in enumerate(dst_ids)}
        for nid in kept:
            if pos_src.get(nid) != pos_dst.get(nid):
                moved.append({"node_id": nid, "from": pos_src.get(nid), "to": pos_dst.get(nid)})

        return {
            "ok": True,
            "from_version": _version_payload(src),
            "to_version": _version_payload(dst),
            "added_ids": added,
            "removed_ids": removed,
            "moved": moved,
            "kept_count": len(kept),
        }


@router.get("/context_sets/{context_set_id}/compiled")
def get_compiled_context(context_set_id: str, include_explain: bool = Query(default=False)):
    with Session(engine) as s:
        cs = require_context_set_access(s, context_set_id)
        active_ids = jload(cs.active_node_ids_json, [])
        # Strategy for freshness: no compiled_text cache.
        # Every call rebuilds from current DB state so node/edge/active edits are reflected immediately.
        compiled = compile_active_context_explain(s, cs.thread_id, active_ids)
        resp = {
            "ok": True,
            "context_set_id": cs.id,
            "thread_id": cs.thread_id,
            "version": cs.version,
            "active_node_ids": active_ids,
            "compiled_text": compiled["compiled_text"],
        }
        if include_explain:
            resp["explain"] = compiled["explain"]
        return resp


@router.post("/context_sets/{context_set_id}/activate")
def activate_nodes(context_set_id: str, body: ActivateNodes):
    with Session(engine) as s:
        cs = require_context_set_access(s, context_set_id)
        to_add = _validate_node_ids(s, cs.thread_id, body.node_ids)
        active = jload(cs.active_node_ids_json, [])
        seen = set(active)
        changed: list[str] = []
        for nid in to_add:
            if nid in seen:
                continue
            active.append(nid)
            seen.add(nid)
            changed.append(nid)
        cs.active_node_ids_json = jdump(active)
        snapshot_context_set(s, cs, reason="activate", changed_node_ids=changed, meta={"requested": len(body.node_ids)})
        s.commit()
        return {"ok": True, "active_node_ids": active, "changed_node_ids": changed, "version": cs.version}


@router.post("/context_sets/{context_set_id}/deactivate")
def deactivate_nodes(context_set_id: str, body: ActivateNodes):
    with Session(engine) as s:
        cs = require_context_set_access(s, context_set_id)
        remove_ids = _validate_node_ids(s, cs.thread_id, body.node_ids)
        remove_set = set(remove_ids)
        before = jload(cs.active_node_ids_json, [])
        active = [nid for nid in before if nid not in remove_set]
        changed = [nid for nid in before if nid in remove_set]
        cs.active_node_ids_json = jdump(active)
        snapshot_context_set(s, cs, reason="deactivate", changed_node_ids=changed, meta={"requested": len(body.node_ids)})
        s.commit()
        return {"ok": True, "active_node_ids": active, "changed_node_ids": changed, "version": cs.version}


@router.post("/context_sets/{context_set_id}/reorder")
def reorder_nodes(context_set_id: str, body: ActiveOrderUpdate):
    with Session(engine) as s:
        cs = require_context_set_access(s, context_set_id)

        requested = _validate_node_ids(s, cs.thread_id, body.node_ids)
        current = jload(cs.active_node_ids_json, [])
        current_set = set(current)
        seen = set()
        reordered = []

        for nid in requested:
            if nid in current_set and nid not in seen:
                reordered.append(nid)
                seen.add(nid)

        for nid in current:
            if nid not in seen:
                reordered.append(nid)
                seen.add(nid)

        cs.active_node_ids_json = jdump(reordered)
        snapshot_context_set(s, cs, reason="reorder", changed_node_ids=requested, meta={"active_count": len(reordered)})
        s.commit()
        return {"ok": True, "active_node_ids": reordered, "version": cs.version}


@router.post("/context_sets/{context_set_id}/unfold_plan")
def preview_unfold_plan(context_set_id: str, body: UnfoldPlanRequest):
    query = (body.query or "").strip()
    if not query:
        raise HTTPException(400, "query is required")

    with Session(engine) as s:
        cs = require_context_set_access(s, context_set_id)
        active_ids = jload(cs.active_node_ids_json, [])
        nodes, edges = load_thread_graph(s, cs.thread_id)
        planned = plan_unfold_candidates(
            query=query,
            nodes=[n.model_dump() for n in nodes],
            edges=[e.model_dump() for e in edges],
            active_ids=active_ids,
            top_k=body.top_k,
            max_candidates=body.max_candidates,
            budget_tokens=body.budget_tokens,
            closure_edge_types=body.closure_edge_types or _DEFAULT_PLANNER_EDGES,
            closure_direction=body.closure_direction,
            max_closure_nodes=body.max_closure_nodes,
        )
        planned["ok"] = True
        planned["context_set_id"] = cs.id
        planned["thread_id"] = cs.thread_id
        planned["active_node_ids"] = active_ids
        return planned


@router.post("/context_sets/{context_set_id}/apply_unfold_plan")
def apply_unfold_plan(context_set_id: str, body: ApplyUnfoldPlanRequest):
    with Session(engine) as s:
        cs = require_context_set_access(s, context_set_id)
        seed_ids = _validate_node_ids(s, cs.thread_id, body.seed_node_ids)
        current_active = jload(cs.active_node_ids_json, [])
        nodes, edges = load_thread_graph(s, cs.thread_id)
        applied = apply_unfold_seed_selection(
            seed_node_ids=seed_ids,
            nodes=[n.model_dump() for n in nodes],
            edges=[e.model_dump() for e in edges],
            active_ids=current_active,
            budget_tokens=body.budget_tokens,
            closure_edge_types=body.closure_edge_types or _DEFAULT_PLANNER_EDGES,
            closure_direction=body.closure_direction,
            max_closure_nodes=body.max_closure_nodes,
        )
        next_active = applied["next_active_ids"]
        cs.active_node_ids_json = jdump(next_active)
        snapshot_context_set(
            s,
            cs,
            reason="apply_unfold_plan",
            changed_node_ids=applied["added_ids"],
            meta={
                "seed_node_ids": seed_ids,
                "budget_tokens": body.budget_tokens,
                "closure_edge_types": body.closure_edge_types or _DEFAULT_PLANNER_EDGES,
                "closure_direction": body.closure_direction,
                "max_closure_nodes": body.max_closure_nodes,
            },
        )
        s.commit()
        resp = {
            "ok": True,
            "active_node_ids": next_active,
            "added_ids": applied["added_ids"],
            "version": cs.version,
            "planner": applied,
        }
        if body.include_explain:
            resp["compiled"] = compile_active_context_explain(s, cs.thread_id, next_active)
        return resp
