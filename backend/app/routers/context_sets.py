from __future__ import annotations
import json
import math
from typing import Any
from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session, select

from app.db import engine
from app.goc_core import apply_unfold_seed_selection, plan_unfold_candidates
from app.models import ContextSet, ContextSetVersion, Node
from app.schemas import (
    ContextSetCreate,
    CloneContextSetRequest,
    ActivateNodes,
    ActiveOrderUpdate,
    UnfoldPlanRequest,
    ApplyUnfoldPlanRequest,
    RebuildActiveRequest,
)
from app.services.context_versions import snapshot_context_set
from app.services.graph import compile_active_context_explain, load_thread_graph
from app.tenant import (
    require_context_set_access,
    require_context_set_write_access,
    require_node_access,
    require_thread_access,
    require_thread_write_access,
)

router = APIRouter(prefix="/api", tags=["context_sets"])

_DEFAULT_PLANNER_EDGES = ["DEPENDS", "HAS_PART", "SPLIT_FROM", "REFERENCES"]

try:
    import tiktoken
except Exception:
    tiktoken = None


def jdump(x) -> str:
    return json.dumps(x, ensure_ascii=False)


def jload(s: str, default):
    try:
        return json.loads(s)
    except Exception:
        return default


def _normalize_string_set(values: list[str] | set[str] | tuple[str, ...] | None) -> set[str]:
    out: set[str] = set()
    for raw in values or []:
        if not isinstance(raw, str):
            continue
        clean = raw.strip().lower()
        if clean:
            out.add(clean)
    return out


def _parse_csv_query(value: str | None) -> set[str]:
    if not value:
        return set()
    return _normalize_string_set(value.split(","))


def _node_payload(node: Node) -> dict[str, Any]:
    payload = jload(node.payload_json or "{}", {})
    if isinstance(payload, dict):
        return payload
    return {}


def _node_type(node: Node) -> str:
    return str(node.type or "").strip() or "Unknown"


def _node_resource_kind(payload: dict[str, Any]) -> str:
    return str(payload.get("resource_kind") or "").strip().lower()


def _is_excluded_by_resource_kind(node: Node, payload: dict[str, Any], exclude_resource_kinds: set[str]) -> bool:
    if not exclude_resource_kinds:
        return False
    if _node_type(node) != "Resource":
        return False
    kind = _node_resource_kind(payload)
    return bool(kind and kind in exclude_resource_kinds)


def _should_exclude_for_compiled(
    node: Node,
    payload: dict[str, Any],
    exclude_types: set[str],
    exclude_resource_kinds: set[str],
) -> bool:
    ntype = _node_type(node).lower()
    if exclude_types and ntype in exclude_types:
        return True
    if _is_excluded_by_resource_kind(node, payload, exclude_resource_kinds):
        return True
    return False


def _has_hangul(text: str) -> bool:
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            return True
    return False


def _count_tokens_heuristic(text: str) -> int:
    if not text:
        return 0
    divisor = 3.0 if _has_hangul(text) else 4.0
    return int(math.ceil(len(text) / divisor))


def _estimate_tokens(text: str) -> tuple[int, str]:
    if not text:
        return 0, "heuristic"
    if tiktoken is not None:
        try:
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text)), "tiktoken"
        except Exception:
            pass
    return _count_tokens_heuristic(text), "heuristic"


def _is_pinned_payload(payload: dict[str, Any]) -> bool:
    if str(payload.get("pin_level") or "").strip().lower() == "required":
        return True
    if payload.get("pinned") is True or payload.get("is_pinned") is True or payload.get("pin") is True:
        return True
    return False


def _is_required_pin(payload: dict[str, Any]) -> bool:
    return str(payload.get("pin_level") or "").strip().lower() == "required"


def _pick_recent_ids(
    *,
    nodes_desc: list[Node],
    payload_by_id: dict[str, dict[str, Any]],
    limit: int,
    predicate,
    exclude_resource_kinds: set[str],
) -> list[str]:
    if limit <= 0:
        return []
    out: list[str] = []
    for node in nodes_desc:
        if len(out) >= limit:
            break
        payload = payload_by_id.get(node.id) or {}
        if _is_excluded_by_resource_kind(node, payload, exclude_resource_kinds):
            continue
        if not predicate(node, payload):
            continue
        out.append(node.id)
    return out


def _node_type_breakdown(nodes: list[Node], include_set: set[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for node in nodes:
        if node.id not in include_set:
            continue
        ntype = _node_type(node)
        out[ntype] = out.get(ntype, 0) + 1
    return dict(sorted(out.items(), key=lambda item: item[0].lower()))


def _resource_kind_breakdown(nodes: list[Node], include_set: set[str], payload_by_id: dict[str, dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for node in nodes:
        if node.id not in include_set:
            continue
        ntype = _node_type(node)
        if ntype == "Resource":
            kind = _node_resource_kind(payload_by_id.get(node.id) or {}) or "unknown"
        elif ntype == "Artifact":
            kind = "artifact"
        else:
            continue
        out[kind] = out.get(kind, 0) + 1
    return dict(sorted(out.items(), key=lambda item: item[0].lower()))


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
        require_thread_write_access(s, body.thread_id)
        s.add(cs)
        s.flush()
        snapshot_context_set(s, cs, reason="create", meta={"name": cs.name})
        s.commit()
        s.refresh(cs)
    return cs.model_dump()


@router.post("/context_sets/{base_context_set_id}/clone")
def clone_context_set(base_context_set_id: str, body: CloneContextSetRequest | None = None):
    req = body or CloneContextSetRequest()
    incoming_meta = req.meta if isinstance(req.meta, dict) else {}

    with Session(engine) as s:
        base = require_context_set_access(s, base_context_set_id)
        require_thread_write_access(s, base.thread_id)

        base_active_ids = jload(base.active_node_ids_json, [])
        clone_name = (req.name or "").strip() or f"{base.name}-scope"

        clone = ContextSet(
            thread_id=base.thread_id,
            name=clone_name,
            active_node_ids_json=jdump(base_active_ids),
        )
        s.add(clone)
        s.flush()
        snapshot_context_set(
            s,
            clone,
            reason="clone",
            changed_node_ids=[],
            meta={
                "base_context_set_id": base.id,
                "active_count": len(base_active_ids),
                **incoming_meta,
            },
        )
        s.commit()
        s.refresh(clone)
        d = clone.model_dump()
        d["active_node_ids"] = base_active_ids
        return d


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
def get_compiled_context(
    context_set_id: str,
    include_explain: bool = Query(default=False),
    max_chars: int | None = Query(default=None, ge=0, le=200000),
    exclude_types: str | None = Query(default=None),
    exclude_resource_kinds: str | None = Query(default=None),
    include_meta: bool = Query(default=False),
):
    with Session(engine) as s:
        cs = require_context_set_access(s, context_set_id)
        active_ids = jload(cs.active_node_ids_json, [])
        exclude_type_set = _parse_csv_query(exclude_types)
        exclude_kind_set = _parse_csv_query(exclude_resource_kinds)

        filtered_active_ids: list[str] = []
        filtered_nodes: list[Node] = []
        filtered_payload_by_id: dict[str, dict[str, Any]] = {}
        for node_id in active_ids:
            node = s.get(Node, node_id)
            if not node or node.thread_id != cs.thread_id:
                continue
            payload = _node_payload(node)
            if _should_exclude_for_compiled(node, payload, exclude_type_set, exclude_kind_set):
                continue
            filtered_active_ids.append(node_id)
            filtered_nodes.append(node)
            filtered_payload_by_id[node.id] = payload

        # Strategy for freshness: no compiled_text cache.
        # Every call rebuilds from current DB state so node/edge/active edits are reflected immediately.
        compiled = compile_active_context_explain(s, cs.thread_id, filtered_active_ids)
        original_compiled_text = str(compiled.get("compiled_text") or "")
        compiled_text = original_compiled_text
        if max_chars is not None:
            compiled_text = compiled_text[:max_chars]
        resp = {
            "ok": True,
            "context_set_id": cs.id,
            "thread_id": cs.thread_id,
            "version": cs.version,
            "active_node_ids": filtered_active_ids,
            "compiled_text": compiled_text,
        }
        if include_explain:
            resp["explain"] = compiled["explain"]
        if include_meta:
            token_estimate, token_method = _estimate_tokens(compiled_text)
            original_token_estimate, original_token_method = _estimate_tokens(original_compiled_text)
            resp["token_estimate"] = token_estimate
            resp["token_estimate_method"] = token_method
            resp["original_token_estimate"] = original_token_estimate
            resp["original_token_estimate_method"] = original_token_method
            resp["compiled_chars"] = len(compiled_text)
            resp["original_compiled_chars"] = len(original_compiled_text)
            resp["active_node_ids_count"] = len(filtered_active_ids)
            resp["node_count"] = len(filtered_active_ids)
            resp["node_type_breakdown"] = _node_type_breakdown(filtered_nodes, set(filtered_active_ids))
            resp["node_resource_kind_breakdown"] = _resource_kind_breakdown(
                filtered_nodes,
                set(filtered_active_ids),
                filtered_payload_by_id,
            )
        return resp


@router.post("/context_sets/{context_set_id}/activate")
def activate_nodes(context_set_id: str, body: ActivateNodes):
    with Session(engine) as s:
        cs = require_context_set_write_access(s, context_set_id)
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
        cs = require_context_set_write_access(s, context_set_id)
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
        cs = require_context_set_write_access(s, context_set_id)

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


@router.post("/context_sets/{context_set_id}/rebuild_active")
def rebuild_active_nodes(context_set_id: str, body: RebuildActiveRequest):
    with Session(engine) as s:
        cs = require_context_set_write_access(s, context_set_id)
        policy = body.policy
        exclude_kind_set = _normalize_string_set(policy.exclude_resource_kinds)

        nodes, _ = load_thread_graph(s, cs.thread_id)
        nodes_desc = list(reversed(nodes))
        payload_by_id = {node.id: _node_payload(node) for node in nodes}

        user_message_ids = _pick_recent_ids(
            nodes_desc=nodes_desc,
            payload_by_id=payload_by_id,
            limit=max(0, int(policy.recent_user_messages)),
            exclude_resource_kinds=exclude_kind_set,
            predicate=lambda n, payload: _node_type(n) == "Message" and str(payload.get("role") or "").strip().lower() == "user",
        )
        assistant_message_ids = _pick_recent_ids(
            nodes_desc=nodes_desc,
            payload_by_id=payload_by_id,
            limit=max(0, int(policy.recent_assistant_messages)),
            exclude_resource_kinds=exclude_kind_set,
            predicate=lambda n, payload: _node_type(n) == "Message" and str(payload.get("role") or "").strip().lower() == "assistant",
        )
        recent_step_ids = _pick_recent_ids(
            nodes_desc=nodes_desc,
            payload_by_id=payload_by_id,
            limit=max(0, int(policy.recent_steps)),
            exclude_resource_kinds=exclude_kind_set,
            predicate=lambda n, _payload: _node_type(n) == "Step",
        )
        recent_artifact_ids = _pick_recent_ids(
            nodes_desc=nodes_desc,
            payload_by_id=payload_by_id,
            limit=max(0, int(policy.recent_artifacts)),
            exclude_resource_kinds=exclude_kind_set,
            predicate=lambda n, _payload: _node_type(n) in {"Artifact", "Resource"},
        )

        pinned_ids: list[str] = []
        pinned_required_ids: list[str] = []
        pinned_flag_ids: list[str] = []
        for node in nodes_desc:
            payload = payload_by_id.get(node.id) or {}
            if not _is_pinned_payload(payload):
                continue
            pinned_ids.append(node.id)
            if _is_required_pin(payload):
                pinned_required_ids.append(node.id)
            else:
                pinned_flag_ids.append(node.id)

        selected_set = set(user_message_ids) | set(assistant_message_ids) | set(recent_step_ids) | set(recent_artifact_ids) | set(pinned_ids)
        next_active_ids = [node.id for node in nodes if node.id in selected_set]

        before_active_ids = jload(cs.active_node_ids_json, [])
        before_set = set(before_active_ids)
        next_set = set(next_active_ids)
        added_ids = [nid for nid in next_active_ids if nid not in before_set]
        removed_ids = [nid for nid in before_active_ids if nid not in next_set]
        changed_ids = added_ids + removed_ids

        cs.active_node_ids_json = jdump(next_active_ids)
        breakdown = {
            "selected_counts": {
                "recent_user_messages": len(user_message_ids),
                "recent_assistant_messages": len(assistant_message_ids),
                "recent_steps": len(recent_step_ids),
                "recent_artifacts": len(recent_artifact_ids),
                "pinned": len(pinned_ids),
                "pinned_required": len(pinned_required_ids),
                "pinned_flagged": len(pinned_flag_ids),
            },
            "active_before_count": len(before_active_ids),
            "active_after_count": len(next_active_ids),
            "added_count": len(added_ids),
            "removed_count": len(removed_ids),
            "excluded_resource_kinds": sorted(exclude_kind_set),
            "exclude_applies_to_node_type": "Resource",
            "include_pinned_requested": bool(policy.include_pinned),
            "include_pinned_enforced": True,
            "by_type": _node_type_breakdown(nodes, next_set),
            "by_resource_kind": _resource_kind_breakdown(nodes, next_set, payload_by_id),
        }

        snapshot_context_set(
            s,
            cs,
            reason="rebuild_active",
            changed_node_ids=changed_ids,
            meta={"policy": policy.model_dump(), "breakdown": breakdown},
        )
        s.commit()
        return {
            "ok": True,
            "context_set_id": cs.id,
            "version": cs.version,
            "active_node_ids": next_active_ids,
            "breakdown": {
                **breakdown,
                "node_type_breakdown": breakdown["by_type"],
                "added_ids": added_ids,
                "removed_ids": removed_ids,
                "pinned_ids": [nid for nid in next_active_ids if nid in set(pinned_ids)],
                "pinned_required_ids": [nid for nid in next_active_ids if nid in set(pinned_required_ids)],
            },
        }


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
        cs = require_context_set_write_access(s, context_set_id)
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
