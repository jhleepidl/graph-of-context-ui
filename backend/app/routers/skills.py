from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session, select

from app.auth import get_current_principal
from app.db import engine
from app.models import ContextSet, Node, Thread
from app.schemas import SkillPackageInstallRequest, SkillPackagePublishRequest
from app.services.context_versions import snapshot_context_set
from app.services.graph import add_edge, get_last_node, load_thread_graph
from app.services.public_library import PUBLIC_SKILL_LIBRARY_TITLE, ensure_public_skill_library_thread
from app.services.skill_registry import get_skill_package, list_skill_registry, normalize_skill_package
from app.services.learning_policy import filter_learning_eligible_nodes
from app.tenant import PUBLIC_SERVICE_ID, require_thread_access, require_thread_write_access


router = APIRouter(prefix="/api/skills", tags=["skills"])


def _jdump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load_first_context_set(session: Session, *, thread_id: str) -> ContextSet:
    context_set = session.exec(
        select(ContextSet)
        .where(ContextSet.thread_id == thread_id)
        .order_by(ContextSet.created_at.asc(), ContextSet.id.asc())
        .limit(1)
    ).first()
    if context_set:
        return context_set
    context_set = ContextSet(thread_id=thread_id, name="default")
    session.add(context_set)
    session.flush()
    snapshot_context_set(
        session,
        context_set,
        reason="create",
        meta={"name": context_set.name, "thread_id": thread_id},
    )
    return context_set


def _activate_node_in_context_set(session: Session, *, context_set: ContextSet, node_id: str, resource_kind: str) -> None:
    try:
        active_ids = json.loads(context_set.active_node_ids_json or "[]")
    except Exception:
        active_ids = []
    if node_id in active_ids:
        return
    active_ids.append(node_id)
    context_set.active_node_ids_json = _jdump(active_ids)
    snapshot_context_set(
        session,
        context_set,
        reason="add_resource",
        changed_node_ids=[node_id],
        meta={"node_type": "Resource", "resource_kind": resource_kind},
    )


def _visible_thread_ids(session: Session, *, limit: int = 200) -> list[str]:
    principal = get_current_principal()
    stmt = select(Thread.id)
    if principal.role != "admin":
        service_id = str(principal.service_id or "").strip()
        stmt = stmt.where(Thread.service_id.in_([service_id, PUBLIC_SERVICE_ID]))
    rows = session.exec(stmt.order_by(Thread.created_at.desc()).limit(limit)).all()
    return [str(row).strip() for row in rows if str(row).strip()]


def _load_nodes_for_registry(
    session: Session,
    *,
    thread_id: str | None,
    max_nodes: int,
) -> list[Any]:
    allowed_types = {"Run", "Step", "Resource"}
    if thread_id:
        thread = require_thread_access(session, thread_id)
        nodes, _ = load_thread_graph(session, thread.id)
        return [node for node in filter_learning_eligible_nodes(nodes) if node.type in allowed_types]

    thread_ids = _visible_thread_ids(session)
    if not thread_ids:
        return []

    stmt = (
        select(Node)
        .where(Node.thread_id.in_(thread_ids))
        .where(Node.type.in_(["Run", "Step", "Resource"]))
        .order_by(Node.created_at.desc(), Node.id.desc())
        .limit(max_nodes)
    )
    return list(reversed(filter_learning_eligible_nodes(session.exec(stmt).all())))


def _skill_observability_meta(items: list[dict[str, Any]]) -> dict[str, Any]:
    has_default_registry = False
    has_runtime_projected = False
    has_public_library = False
    for item in items:
        source = str(item.get("source") or "").strip()
        if not source:
            continue
        if source.startswith("default_registry"):
            has_default_registry = True
        elif source.startswith("resource:") or source.startswith("skill_package"):
            has_public_library = True
            has_runtime_projected = True
        else:
            has_runtime_projected = True

    catalog_source = "local"
    if has_default_registry and has_runtime_projected:
        catalog_source = "mixed"
    elif has_default_registry:
        catalog_source = "goc"
    elif has_runtime_projected:
        catalog_source = "local"

    return {
        "skill_catalog_source": catalog_source,
        "projection_kind": "skill_observability",
        "has_public_library": has_public_library,
        "authority_note": "GoC now supports skill package install/export for sharing, while runtime remains primary authority for execution content.",
    }


def _resolve_skill_package(
    session: Session,
    *,
    skill_id: str | None = None,
    package: dict[str, Any] | None = None,
    thread_id: str | None = None,
    max_nodes: int = 1200,
) -> dict[str, Any]:
    normalized = normalize_skill_package(package or {}, source_key="request.package") if package else None
    if normalized:
        return normalized

    clean_skill_id = str(skill_id or "").strip()
    if not clean_skill_id:
        raise HTTPException(400, "skill_id or package is required")

    nodes = _load_nodes_for_registry(
        session,
        thread_id=(thread_id or "").strip() or None,
        max_nodes=max_nodes,
    )
    resolved = get_skill_package(clean_skill_id, nodes=nodes, include_defaults=True)
    normalized = normalize_skill_package(resolved or {"id": clean_skill_id}, source_key="resolved")
    if not normalized:
        raise HTTPException(404, f"skill package not found: {clean_skill_id}")
    return normalized


def _create_skill_resource_node(
    session: Session,
    *,
    thread: Thread,
    context_set: ContextSet,
    package: dict[str, Any],
    source: str,
    origin: dict[str, Any] | None = None,
) -> Node:
    skill_id = str(package.get("id") or package.get("slug") or "").strip()
    if not skill_id:
        raise HTTPException(400, "package.id is required")
    payload = {
        **package,
        "name": str(package.get("name") or skill_id).strip(),
        "resource_kind": "skill_package",
        "summary": str(package.get("description") or "").strip() or None,
        "source": source,
        "context_set_id": context_set.id,
        "tag": "RESOURCE",
        "skill_package": package,
    }
    if origin:
        payload["origin"] = origin

    last = get_last_node(session, thread.id)
    node = Node(
        thread_id=thread.id,
        type="Resource",
        text=_jdump(package),
        payload_json=_jdump(payload),
    )
    session.add(node)
    session.flush()
    if last and last.id != node.id:
        session.add(add_edge(thread.id, last.id, node.id, "NEXT"))
    _activate_node_in_context_set(session, context_set=context_set, node_id=node.id, resource_kind="skill_package")
    return node


@router.get("")
def list_skills(
    thread_id: str | None = Query(default=None),
    max_nodes: int = Query(default=1200, ge=100, le=5000),
    include_defaults: bool = Query(default=True),
):
    with Session(engine) as session:
        nodes = _load_nodes_for_registry(
            session,
            thread_id=(thread_id or "").strip() or None,
            max_nodes=max_nodes,
        )
        items = list_skill_registry(nodes=nodes, include_defaults=include_defaults)
        return {
            "ok": True,
            "items": items,
            "count": len(items),
            "thread_id": (thread_id or "").strip() or None,
            "include_defaults": bool(include_defaults),
            "public_library_title": PUBLIC_SKILL_LIBRARY_TITLE,
            "observability": _skill_observability_meta(items),
        }


@router.get("/{skill_id}")
def get_skill(
    skill_id: str,
    thread_id: str | None = Query(default=None),
    max_nodes: int = Query(default=1200, ge=100, le=5000),
    include_defaults: bool = Query(default=True),
):
    with Session(engine) as session:
        nodes = _load_nodes_for_registry(
            session,
            thread_id=(thread_id or "").strip() or None,
            max_nodes=max_nodes,
        )
        package = get_skill_package(skill_id, nodes=nodes, include_defaults=include_defaults)
        item = package if isinstance(package, dict) else {}
        return {
            "ok": True,
            "item": package,
            "thread_id": (thread_id or "").strip() or None,
            "include_defaults": bool(include_defaults),
            "observability": _skill_observability_meta([item] if item else []),
        }


@router.get("/{skill_id}/export")
def export_skill(
    skill_id: str,
    thread_id: str | None = Query(default=None),
    max_nodes: int = Query(default=1200, ge=100, le=5000),
    include_defaults: bool = Query(default=True),
):
    with Session(engine) as session:
        package = _resolve_skill_package(
            session,
            skill_id=skill_id,
            thread_id=(thread_id or "").strip() or None,
            max_nodes=max_nodes,
        )
        if not include_defaults and str(package.get("source") or "").startswith("default_registry"):
            raise HTTPException(404, "skill package not found")
        return {
            "ok": True,
            "skill_id": str(package.get("id") or skill_id),
            "package": package,
        }


@router.post("/install")
def install_skill(body: SkillPackageInstallRequest):
    with Session(engine) as session:
        thread = require_thread_write_access(session, body.thread_id)
        target_context = session.get(ContextSet, body.context_set_id) if body.context_set_id else None
        if target_context and target_context.thread_id != thread.id:
            raise HTTPException(404, "context set not found in thread")
        if target_context is None:
            target_context = _load_first_context_set(session, thread_id=thread.id)

        package = _resolve_skill_package(
            session,
            skill_id=body.skill_id,
            package=body.package,
            thread_id=body.source_thread_id,
        )
        node = _create_skill_resource_node(
            session,
            thread=thread,
            context_set=target_context,
            package=package,
            source="manual",
            origin={
                "type": "skill_install",
                "source_thread_id": (body.source_thread_id or "").strip() or None,
                "installed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        session.commit()
        session.refresh(node)
        return {
            "ok": True,
            "thread_id": thread.id,
            "node": node.model_dump(),
            "package": package,
        }


@router.post("/publish")
def publish_skill(body: SkillPackagePublishRequest):
    principal = get_current_principal()
    if principal.role not in {"admin", "service", "ui"}:
        raise HTTPException(403, "authenticated principal required")

    with Session(engine) as session:
        package = _resolve_skill_package(
            session,
            skill_id=body.skill_id,
            package=body.package,
            thread_id=body.thread_id,
        )
        library_thread, library_context = ensure_public_skill_library_thread(session)
        node = _create_skill_resource_node(
            session,
            thread=library_thread,
            context_set=library_context,
            package={**package, "visibility": body.visibility or package.get("visibility") or "public"},
            source="manual",
            origin={
                "type": "skill_publish",
                "origin_service_id": str(principal.service_id or "").strip() or None,
                "source_thread_id": (body.thread_id or "").strip() or None,
            },
        )
        session.commit()
        session.refresh(node)
        return {
            "ok": True,
            "thread_id": library_thread.id,
            "library_title": PUBLIC_SKILL_LIBRARY_TITLE,
            "node": node.model_dump(),
            "package": package,
        }
