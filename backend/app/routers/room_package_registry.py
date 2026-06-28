from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from sqlmodel import Session, select

from app.db import engine
from app.models import AgentPackageRecord
from app.services.room_package_registry import (
    build_room_package_export_preview,
    build_room_package_lifecycle_preview,
    build_room_package_registry,
    build_room_package_registry_card,
)
from app.services.room_packages import (
    get_public_room_package,
    list_public_room_library,
    list_thread_room_packages,
    room_package_to_row,
)
from app.tenant import require_thread_access

router = APIRouter(prefix="/api", tags=["room-package-registry"])


def _find_thread_package(session: Session, thread_id: str, package_id: str) -> dict[str, Any] | None:
    row = session.exec(
        select(AgentPackageRecord).where(
            AgentPackageRecord.thread_id == thread_id,
            AgentPackageRecord.package_id == package_id,
        )
    ).first()
    if not row:
        return None
    item = room_package_to_row(row)
    pkg = item.get("package") if isinstance(item.get("package"), dict) else {}
    if pkg.get("kind") != "shared_room_package_v1":
        return None
    return item


@router.get("/room-package-registry")
def get_public_room_package_registry(q: str | None = Query(default=None), limit: int = 100):
    with Session(engine) as session:
        library = list_public_room_library(session, query="", limit=max(1, min(int(limit or 100), 500)))
        return build_room_package_registry(library.get("items") or [], query=q or "", limit=limit)


@router.get("/room-package-registry/{package_id}/card")
def get_public_room_package_registry_card(package_id: str):
    with Session(engine) as session:
        item = get_public_room_package(session, package_id)
        if not item:
            raise HTTPException(404, "room package not found")
        return {"ok": True, "card": build_room_package_registry_card(item)}


@router.post("/room-package-registry/{package_id}/export-preview")
def post_public_room_package_export_preview(
    package_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
):
    target_format = str((body or {}).get("target_format") or (body or {}).get("targetFormat") or "claude_md")
    with Session(engine) as session:
        item = get_public_room_package(session, package_id)
        if not item:
            raise HTTPException(404, "room package not found")
        return build_room_package_export_preview(item, target_format=target_format)


@router.get("/threads/{thread_id}/room-package-registry")
def get_thread_room_package_registry(thread_id: str, q: str | None = Query(default=None), limit: int = 100):
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        result = list_thread_room_packages(session, thread, limit=max(1, min(int(limit or 100), 500)))
        return {
            **build_room_package_registry(result.get("items") or [], query=q or "", limit=limit),
            "thread_id": thread.id,
        }


@router.get("/threads/{thread_id}/room-packages/{package_id}/registry-card")
def get_thread_room_package_registry_card(thread_id: str, package_id: str):
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        item = _find_thread_package(session, thread.id, package_id)
        if not item:
            raise HTTPException(404, "room package not found")
        return {"ok": True, "thread_id": thread.id, "card": build_room_package_registry_card(item)}


@router.post("/threads/{thread_id}/room-packages/{package_id}/export-preview")
def post_thread_room_package_export_preview(
    thread_id: str,
    package_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
):
    target_format = str((body or {}).get("target_format") or (body or {}).get("targetFormat") or "claude_md")
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        item = _find_thread_package(session, thread.id, package_id)
        if not item:
            raise HTTPException(404, "room package not found")
        return build_room_package_export_preview(item, target_format=target_format)


@router.post("/threads/{thread_id}/room-packages/{package_id}/lifecycle-preview")
def post_thread_room_package_lifecycle_preview(
    thread_id: str,
    package_id: str,
    body: dict[str, Any] = Body(default_factory=dict),
):
    action = str((body or {}).get("action") or "publish_review")
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        item = _find_thread_package(session, thread.id, package_id)
        if not item:
            raise HTTPException(404, "room package not found")
        return build_room_package_lifecycle_preview(item, action=action)
