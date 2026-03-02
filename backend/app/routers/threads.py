from __future__ import annotations
import json
import logging
from typing import Any
from fastapi import APIRouter, HTTPException
from sqlalchemy import or_
from sqlmodel import Session, select

from app.db import engine
from app.models import Thread, ContextSet, ContextSetVersion, Node, Edge, NodeEmbedding
from app.schemas import (
    ThreadCreate,
    ThreadEnsureRequest,
    ThreadRead,
    NodeLayoutUpdate,
    EdgeCreate,
    NodeCreate,
    NodeCreateResponse,
)
from app.services.context_versions import snapshot_context_set
from app.services.embedding import rebuild_thread_index, remove_thread_index
from app.services.graph import add_edge, get_last_node
from app.auth import get_current_principal
from app.tenant import current_service_id, require_node_access, require_thread_access, require_thread_write_access, PUBLIC_SERVICE_ID

router = APIRouter(prefix="/api/threads", tags=["threads"])
logger = logging.getLogger(__name__)


def jdump(x):
    return json.dumps(x, ensure_ascii=False)


def jload(s: str, default):
    try:
        return json.loads(s)
    except Exception:
        return default


def _normalize_external_ref(value: str | None) -> str | None:
    clean = (value or "").strip()
    return clean or None


def _normalize_meta_json(value: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _merge_meta(existing: dict[str, Any], incoming: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    base = existing if isinstance(existing, dict) else {}
    incoming_obj = incoming if isinstance(incoming, dict) else {}
    merged: dict[str, Any] = dict(base)

    for key, incoming_value in incoming_obj.items():
        if key == "telegram" and isinstance(incoming_value, dict):
            current_telegram = merged.get("telegram")
            telegram_merged = dict(current_telegram) if isinstance(current_telegram, dict) else {}

            incoming_chat_id = incoming_value.get("chat_id")
            if _has_value(incoming_chat_id):
                telegram_merged["chat_id"] = incoming_chat_id

            for fill_key in ("title", "type"):
                if _has_value(telegram_merged.get(fill_key)):
                    continue
                incoming_fill = incoming_value.get(fill_key)
                if _has_value(incoming_fill):
                    telegram_merged[fill_key] = incoming_fill

            for telegram_key, telegram_value in incoming_value.items():
                if telegram_key in {"chat_id", "title", "type"}:
                    continue
                if telegram_key in telegram_merged:
                    continue
                if telegram_value is None:
                    continue
                telegram_merged[telegram_key] = telegram_value

            merged["telegram"] = telegram_merged
            continue

        if key in merged:
            continue
        merged[key] = incoming_value

    return merged, merged != base


def _apply_existing_thread_updates(
    session: Session,
    thread: Thread,
    incoming_title: str | None,
    incoming_meta: dict[str, Any],
) -> Thread:
    existing_meta_raw = jload(thread.meta_json or "{}", {})
    existing_meta = existing_meta_raw if isinstance(existing_meta_raw, dict) else {}
    merged_meta, meta_changed = _merge_meta(existing_meta, incoming_meta)

    title_changed = False
    next_title = (incoming_title or "").strip()
    current_title = (thread.title or "").strip()
    if next_title and (not current_title or current_title == "Untitled" or current_title.lower().startswith("job:")):
        if thread.title != next_title:
            thread.title = next_title
            title_changed = True

    if meta_changed:
        thread.meta_json = jdump(merged_meta)

    if meta_changed or title_changed:
        session.add(thread)
        session.commit()
        session.refresh(thread)

    return thread


def _thread_to_response(thread: Thread) -> ThreadRead:
    out = thread.model_dump()
    out["meta_json"] = jload(thread.meta_json or "{}", {})
    return ThreadRead(**out)


def _resolve_target_service_id_from_body(service_id_override: str | None) -> str:
    principal = get_current_principal()
    if principal.role == "admin":
        service_id = (service_id_override or "").strip()
        if not service_id:
            raise HTTPException(400, "admin must provide service_id")
        return service_id
    return current_service_id()


def _find_thread_by_external_ref(session: Session, service_id: str, external_ref: str) -> Thread | None:
    return session.exec(
        select(Thread)
        .where(Thread.service_id == service_id)
        .where(Thread.external_ref == external_ref)
        .order_by(Thread.created_at.asc(), Thread.id.asc())
        .limit(1)
    ).first()


def _create_thread_with_default_context_set(
    session: Session,
    service_id: str,
    title: str,
    external_ref: str | None,
    meta_json: dict[str, Any],
) -> Thread:
    thread = Thread(
        title=title or "Untitled",
        service_id=service_id,
        external_ref=external_ref,
        meta_json=jdump(meta_json),
    )
    session.add(thread)
    session.flush()
    context_set = ContextSet(thread_id=thread.id, name="default")
    session.add(context_set)
    session.flush()
    snapshot_context_set(
        session,
        context_set,
        reason="create",
        meta={"name": "default", "thread_id": thread.id},
    )
    return thread


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
    "JOINS",
    "BELONGS_TO_RUN",
}

ALLOWED_NODE_TYPES = {
    "Message",
    "Run",
    "Step",
    "ToolCall",
    "ToolResult",
    "Artifact",
    "Resource",
    "Fold",
    "Decision",
    "Assumption",
    "Plan",
    "ContextCandidate",
    "MemoryItem",
    "Observation",
    "ContextSummary",
}


@router.get("", response_model=list[ThreadRead])
def list_threads():
    principal = get_current_principal()
    with Session(engine) as s:
        query = select(Thread).order_by(Thread.created_at.desc())
        if principal.role != "admin":
            service_id = current_service_id()
            query = query.where(
                or_(
                    Thread.service_id == service_id,
                    Thread.service_id == PUBLIC_SERVICE_ID,
                )
            )
        threads = s.exec(query).all()
        return [_thread_to_response(t) for t in threads]


@router.post("", response_model=ThreadRead)
def create_thread(body: ThreadCreate):
    service_id = _resolve_target_service_id_from_body(body.service_id)
    external_ref = _normalize_external_ref(body.external_ref)
    meta_json = _normalize_meta_json(body.meta_json)
    with Session(engine) as s:
        if external_ref:
            existing = _find_thread_by_external_ref(s, service_id, external_ref)
            if existing:
                existing = _apply_existing_thread_updates(
                    s,
                    existing,
                    incoming_title=body.title,
                    incoming_meta=meta_json,
                )
                return _thread_to_response(existing)

        t = _create_thread_with_default_context_set(
            s,
            service_id=service_id,
            title=body.title or "Untitled",
            external_ref=external_ref,
            meta_json=meta_json,
        )
        s.commit()
        s.refresh(t)
    return _thread_to_response(t)


@router.post("/ensure", response_model=ThreadRead)
def ensure_thread(body: ThreadEnsureRequest):
    external_ref = _normalize_external_ref(body.external_ref)
    if not external_ref:
        raise HTTPException(400, "external_ref is required")
    service_id = _resolve_target_service_id_from_body(body.service_id)
    meta_json = _normalize_meta_json(body.meta_json)

    with Session(engine) as s:
        existing = _find_thread_by_external_ref(s, service_id, external_ref)
        if existing:
            existing = _apply_existing_thread_updates(
                s,
                existing,
                incoming_title=body.title,
                incoming_meta=meta_json,
            )
            return _thread_to_response(existing)

        t = _create_thread_with_default_context_set(
            s,
            service_id=service_id,
            title=body.title or "Untitled",
            external_ref=external_ref,
            meta_json=meta_json,
        )
        s.commit()
        s.refresh(t)
        return _thread_to_response(t)


@router.delete("/{thread_id}")
def delete_thread(thread_id: str):
    with Session(engine) as s:
        t = require_thread_write_access(s, thread_id)

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
            "thread": _thread_to_response(t),
            "nodes": [n.model_dump() for n in nodes],
            "edges": [e.model_dump() for e in edges],
        }


@router.post("/{thread_id}/layout")
def save_layout(thread_id: str, body: NodeLayoutUpdate):
    with Session(engine) as s:
        require_thread_write_access(s, thread_id)

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


@router.post("/{thread_id}/nodes", response_model=NodeCreateResponse)
def create_node(thread_id: str, body: NodeCreate):
    node_type = (body.type or "").strip()
    if not node_type:
        raise HTTPException(400, "type is required")
    if node_type not in ALLOWED_NODE_TYPES:
        raise HTTPException(400, f"invalid node type: {node_type}")

    connect_from = body.connect_from
    connect_source: Node | None = None
    connect_edge_type: str | None = None

    with Session(engine) as s:
        require_thread_write_access(s, thread_id)

        last_node_before_insert: Node | None = None
        if connect_from == "last":
            last_node_before_insert = get_last_node(s, thread_id)
            connect_edge_type = "NEXT"
        elif connect_from is not None:
            source_id = (connect_from.node_id or "").strip()
            edge_type = (connect_from.edge_type or "").strip() or "NEXT"
            if not source_id:
                raise HTTPException(400, "connect_from.node_id is required")
            if edge_type not in ALLOWED_EDGE_TYPES:
                raise HTTPException(400, f"invalid edge type: {edge_type}")

            source_node = require_node_access(s, source_id)
            if source_node.thread_id != thread_id:
                raise HTTPException(404, "source node not found in thread")
            connect_source = source_node
            connect_edge_type = edge_type

        node = Node(
            thread_id=thread_id,
            type=node_type,
            text=body.text,
            payload_json=jdump(body.payload_json if isinstance(body.payload_json, dict) else {}),
        )
        s.add(node)
        s.flush()

        if connect_from == "last" and last_node_before_insert and last_node_before_insert.id != node.id:
            s.add(add_edge(thread_id, last_node_before_insert.id, node.id, "NEXT"))
        elif connect_source and connect_edge_type and connect_source.id != node.id:
            s.add(add_edge(thread_id, connect_source.id, node.id, connect_edge_type))

        s.commit()
        s.refresh(node)
        return node.model_dump()


@router.post("/{thread_id}/edges")
def create_edge(thread_id: str, body: EdgeCreate):
    if body.type not in ALLOWED_EDGE_TYPES:
        raise HTTPException(400, f"invalid edge type: {body.type}")

    with Session(engine) as s:
        require_thread_write_access(s, thread_id)

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
        require_thread_write_access(s, thread_id)

        e = s.get(Edge, edge_id)
        if not e or e.thread_id != thread_id:
            raise HTTPException(404, "edge not found")

        s.delete(e)
        s.commit()
        return {"ok": True, "deleted_edge_id": edge_id}


@router.delete("/{thread_id}/nodes/{node_id}")
def delete_node(thread_id: str, node_id: str):
    with Session(engine) as s:
        require_thread_write_access(s, thread_id)

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
        require_thread_write_access(s, thread_id)
        stats = rebuild_thread_index(s, thread_id)
        return {"ok": True, "rebuild": stats}
