from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from sqlmodel import Session

from app.db import engine
from app.services.room_packages import (
    build_room_package_fork_preview,
    get_public_room_package,
    list_public_room_library,
    list_thread_room_packages,
    upsert_thread_room_package,
)
from app.tenant import require_thread_access, require_thread_write_access

router = APIRouter(prefix='/api', tags=['room-library'])


@router.get('/room-library')
def get_room_library(q: str | None = Query(default=None), limit: int = 100):
    with Session(engine) as session:
        return list_public_room_library(session, query=q or '', limit=limit)


@router.get('/room-library/{package_id}')
def get_room_library_package(package_id: str):
    with Session(engine) as session:
        item = get_public_room_package(session, package_id)
        if not item:
            raise HTTPException(404, 'room package not found')
        return {'ok': True, 'package': item}


@router.post('/room-library/{package_id}/fork-preview')
def post_room_library_fork_preview(package_id: str, body: dict[str, Any] = Body(default_factory=dict)):
    with Session(engine) as session:
        item = get_public_room_package(session, package_id)
        if not item:
            raise HTTPException(404, 'room package not found')
        return build_room_package_fork_preview(item, title=(body or {}).get('title'))


@router.get('/threads/{thread_id}/room-packages')
def get_thread_room_packages(thread_id: str, limit: int = 100):
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        return list_thread_room_packages(session, thread, limit=limit)


@router.post('/threads/{thread_id}/room-packages')
def post_thread_room_package(thread_id: str, body: dict[str, Any] = Body(default_factory=dict)):
    with Session(engine) as session:
        thread = require_thread_write_access(session, thread_id)
        try:
            return upsert_thread_room_package(session, thread, body or {}, source=str((body or {}).get('source') or 'ddalggak'))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
