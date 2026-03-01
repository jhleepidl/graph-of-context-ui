from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select

from app.auth import get_current_principal, require_admin_principal
from app.db import engine
from app.models import AgentPublishRequest, Node, Thread, utcnow
from app.schemas import PublishRequestCreate
from app.services.context_versions import snapshot_context_set
from app.services.embedding import ensure_node_embedding
from app.services.graph import add_edge, get_last_node
from app.services.public_library import ensure_public_library_thread
from app.tenant import require_node_access

router = APIRouter(prefix="/api", tags=["publish_requests"])
logger = logging.getLogger(__name__)


def jdump(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False)


def jload(s: str, default):
    try:
        return json.loads(s)
    except Exception:
        return default


def _payload(node: Node) -> dict[str, Any]:
    raw = jload(node.payload_json or "{}", {})
    if isinstance(raw, dict):
        return raw
    return {}


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _is_agent_profile(payload: dict[str, Any]) -> bool:
    kind = _as_text(payload.get("resource_kind"))
    agent_id = _as_text(payload.get("agent_id"))
    return kind == "agent_profile" or bool(agent_id)


def _extract_tags(payload: dict[str, Any]) -> list[str]:
    tags = payload.get("tags")
    if not isinstance(tags, list):
        return []
    out: list[str] = []
    for item in tags:
        clean = _as_text(item)
        if clean:
            out.append(clean)
    return out


@router.post("/publish_requests")
def create_publish_request(body: PublishRequestCreate):
    principal = get_current_principal()
    if principal.role not in {"service", "ui"}:
        raise HTTPException(403, "service/ui authentication required")
    if not principal.service_id:
        raise HTTPException(401, "service scope is missing")

    source_node_id = (body.source_node_id or "").strip()
    if not source_node_id:
        raise HTTPException(400, "source_node_id is required")

    with Session(engine) as s:
        source_node = require_node_access(s, source_node_id)
        source_thread = s.get(Thread, source_node.thread_id)
        if not source_thread:
            raise HTTPException(404, "source thread not found")
        if source_thread.service_id != principal.service_id:
            raise HTTPException(403, "source node must belong to your service")

        payload = _payload(source_node)
        if not _is_agent_profile(payload):
            raise HTTPException(400, "source node is not an agent_profile resource")

        existing = s.exec(
            select(AgentPublishRequest)
            .where(
                AgentPublishRequest.service_id == principal.service_id,
                AgentPublishRequest.source_node_id == source_node.id,
                AgentPublishRequest.status == "pending",
            )
            .order_by(AgentPublishRequest.created_at.desc(), AgentPublishRequest.id.desc())
            .limit(1)
        ).first()
        if existing:
            return {"ok": True, "request": existing.model_dump(), "deduped": True}

        row = AgentPublishRequest(
            service_id=principal.service_id,
            source_node_id=source_node.id,
            status="pending",
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        return {"ok": True, "request": row.model_dump(), "deduped": False}


@router.get("/admin/publish_requests")
def list_publish_requests_admin(status: str = "pending"):
    require_admin_principal()
    status_clean = (status or "pending").strip().lower()
    if status_clean not in {"pending", "approved", "rejected", "all"}:
        raise HTTPException(400, "status must be pending|approved|rejected|all")

    with Session(engine) as s:
        query = select(AgentPublishRequest).order_by(
            AgentPublishRequest.created_at.desc(),
            AgentPublishRequest.id.desc(),
        )
        if status_clean != "all":
            query = query.where(AgentPublishRequest.status == status_clean)
        rows = s.exec(query).all()

        items: list[dict[str, Any]] = []
        for row in rows:
            out = row.model_dump()
            source = s.get(Node, row.source_node_id)
            if not source:
                out["source_preview"] = None
                items.append(out)
                continue
            source_payload = _payload(source)
            out["source_preview"] = {
                "node_id": source.id,
                "thread_id": source.thread_id,
                "resource_kind": _as_text(source_payload.get("resource_kind")) or None,
                "agent_id": _as_text(source_payload.get("agent_id")) or None,
                "title": _as_text(source_payload.get("title")) or _as_text(source_payload.get("name")) or None,
                "summary": _as_text(source_payload.get("summary")) or None,
                "snippet": _as_text(source.text).replace("\n", " ")[:220] or None,
            }
            items.append(out)

        return {"ok": True, "items": items}


@router.post("/admin/publish_requests/{request_id}/approve")
def approve_publish_request(request_id: str):
    require_admin_principal()
    with Session(engine) as s:
        row = s.get(AgentPublishRequest, request_id)
        if not row:
            raise HTTPException(404, "publish request not found")
        if row.status != "pending":
            raise HTTPException(400, f"publish request is already {row.status}")

        source_node = s.get(Node, row.source_node_id)
        if not source_node:
            raise HTTPException(404, "source node not found")
        source_thread = s.get(Thread, source_node.thread_id)
        if not source_thread:
            raise HTTPException(404, "source thread not found")
        if source_thread.service_id != row.service_id:
            raise HTTPException(400, "publish request source ownership mismatch")

        source_payload = _payload(source_node)
        if not _is_agent_profile(source_payload):
            raise HTTPException(400, "source node is not an agent_profile resource")

        library_thread, library_context = ensure_public_library_thread(s)

        origin_agent_id = _as_text(source_payload.get("agent_id")) or _as_text(source_payload.get("name"))
        summary = _as_text(source_payload.get("summary")) or None
        name = (
            _as_text(source_payload.get("title"))
            or _as_text(source_payload.get("name"))
            or origin_agent_id
            or "agent-blueprint"
        )

        raw_version = source_payload.get("version")
        try:
            version = max(1, int(raw_version))
        except Exception:
            version = 1

        blueprint_id = f"pub_{uuid4().hex[:12]}"
        published_at = utcnow()
        published_at_iso = published_at.isoformat()

        payload = {}
        if isinstance(source_payload, dict):
            payload.update(source_payload)
        payload.update(
            {
                "blueprint_id": blueprint_id,
                "origin_service_id": row.service_id,
                "origin_node_id": source_node.id,
                "origin_agent_id": origin_agent_id or None,
                "version": version,
                "tags": _extract_tags(source_payload),
                "published_at": published_at_iso,
            }
        )
        payload.update(
            {
                "name": name,
                "resource_kind": "agent_blueprint",
                "mime_type": _as_text(source_payload.get("mime_type")) or None,
                "uri": _as_text(source_payload.get("uri")) or None,
                "source": "manual",
                "context_set_id": library_context.id,
                "summary": summary,
                "tag": "RESOURCE",
            }
        )

        last = get_last_node(s, library_thread.id)
        public_node = Node(
            thread_id=library_thread.id,
            type="Resource",
            text=source_node.text or "",
            payload_json=jdump(payload),
        )
        s.add(public_node)
        s.flush()
        if last and last.id != public_node.id:
            s.add(add_edge(library_thread.id, last.id, public_node.id, "NEXT"))

        active_ids = jload(library_context.active_node_ids_json or "[]", [])
        if public_node.id not in active_ids:
            active_ids.append(public_node.id)
            library_context.active_node_ids_json = jdump(active_ids)
            snapshot_context_set(
                s,
                library_context,
                reason="add_resource",
                changed_node_ids=[public_node.id],
                meta={"node_type": "Resource", "resource_kind": "agent_blueprint"},
            )

        row.status = "approved"
        row.decided_at = published_at
        row.decided_by = "admin"
        row.public_node_id = public_node.id
        row.blueprint_id = blueprint_id
        s.add(row)
        s.commit()
        s.refresh(row)
        s.refresh(public_node)

        warning = None
        try:
            ensure_node_embedding(s, public_node, commit=True)
        except Exception as exc:
            warning = f"embedding failed: {exc}"
            logger.exception(
                "public blueprint embedding failed (request_id=%s, node_id=%s)",
                row.id,
                public_node.id,
            )

        return {
            "ok": True,
            "request": row.model_dump(),
            "blueprint_id": blueprint_id,
            "public_node_id": public_node.id,
            "warning": warning,
        }


@router.post("/admin/publish_requests/{request_id}/reject")
def reject_publish_request(request_id: str):
    require_admin_principal()
    with Session(engine) as s:
        row = s.get(AgentPublishRequest, request_id)
        if not row:
            raise HTTPException(404, "publish request not found")
        if row.status != "pending":
            raise HTTPException(400, f"publish request is already {row.status}")

        decided_at = utcnow()
        row.status = "rejected"
        row.decided_at = decided_at
        row.decided_by = "admin"
        s.add(row)
        s.commit()
        s.refresh(row)
        return {"ok": True, "request": row.model_dump()}
