from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from sqlmodel import Session, select

from app.auth import get_current_principal
from app.db import engine
from app.models import Node, Thread
from app.services.graph import load_thread_graph
from app.services.skill_registry import get_skill_package, list_skill_registry
from app.tenant import PUBLIC_SERVICE_ID, require_thread_access


router = APIRouter(prefix="/api/skills", tags=["skills"])


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
    if thread_id:
        thread = require_thread_access(session, thread_id)
        nodes, _ = load_thread_graph(session, thread.id)
        return [node for node in nodes if node.type in {"Run", "Step"}]

    thread_ids = _visible_thread_ids(session)
    if not thread_ids:
        return []

    stmt = (
        select(Node)
        .where(Node.thread_id.in_(thread_ids))
        .where(Node.type.in_(["Run", "Step"]))
        .order_by(Node.created_at.desc(), Node.id.desc())
        .limit(max_nodes)
    )
    return list(reversed(session.exec(stmt).all()))


@router.get("")
def list_skills(
    thread_id: str | None = Query(default=None),
    max_nodes: int = Query(default=1200, ge=100, le=5000),
):
    with Session(engine) as session:
        nodes = _load_nodes_for_registry(
            session,
            thread_id=(thread_id or "").strip() or None,
            max_nodes=max_nodes,
        )
        items = list_skill_registry(nodes=nodes, include_defaults=True)
        return {
            "ok": True,
            "items": items,
            "count": len(items),
            "thread_id": (thread_id or "").strip() or None,
        }


@router.get("/{skill_id}")
def get_skill(
    skill_id: str,
    thread_id: str | None = Query(default=None),
    max_nodes: int = Query(default=1200, ge=100, le=5000),
):
    with Session(engine) as session:
        nodes = _load_nodes_for_registry(
            session,
            thread_id=(thread_id or "").strip() or None,
            max_nodes=max_nodes,
        )
        package = get_skill_package(skill_id, nodes=nodes, include_defaults=True)
        return {
            "ok": True,
            "item": package,
            "thread_id": (thread_id or "").strip() or None,
        }
