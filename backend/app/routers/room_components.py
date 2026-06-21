from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from sqlmodel import Session, select

from app.db import engine
from app.models import AgentPackageRecord
from app.services.room_components import (
    build_room_components,
    create_borrowed_agent_invocation,
    list_package_components,
    recommend_borrowed_agents,
)
from app.services.room_packages import get_public_room_package, list_public_room_library, room_package_to_row
from app.tenant import require_thread_access

router = APIRouter(prefix='/api', tags=['room-components'])


def _thread_packages(session: Session, thread_id: str | None = None, *, public_only: bool = False, limit: int = 200) -> list[dict[str, Any]]:
    stmt = select(AgentPackageRecord).order_by(AgentPackageRecord.updated_at.desc()).limit(max(1, min(int(limit or 200), 1000)))
    if thread_id:
        stmt = select(AgentPackageRecord).where(AgentPackageRecord.thread_id == thread_id).order_by(AgentPackageRecord.updated_at.desc()).limit(max(1, min(int(limit or 200), 1000)))
    items: list[dict[str, Any]] = []
    for row in list(session.exec(stmt)):
        item = room_package_to_row(row)
        pkg = item.get('package') if isinstance(item.get('package'), dict) else {}
        if pkg.get('kind') != 'shared_room_package_v1':
            continue
        if public_only and item.get('visibility') not in {'public', 'unlisted'} and pkg.get('visibility') not in {'public', 'unlisted'}:
            continue
        items.append(item)
    return items


@router.get('/room-library/components')
def get_public_room_components(q: str | None = Query(default=None), limit: int = 200):
    with Session(engine) as session:
        library = list_public_room_library(session, query='', limit=max(1, min(int(limit or 200), 500)))
        return list_package_components(library.get('items') or [], query=q or '', limit=limit)


@router.get('/room-library/{package_id}/components')
def get_public_package_components(package_id: str):
    with Session(engine) as session:
        item = get_public_room_package(session, package_id)
        if not item:
            raise HTTPException(404, 'room package not found')
        pkg = item.get('package') if isinstance(item.get('package'), dict) else item
        return {'ok': True, 'package_id': package_id, 'components': build_room_components(pkg)}


@router.post('/room-library/{package_id}/borrow-preview')
def post_public_borrow_preview(package_id: str, body: dict[str, Any] = Body(default_factory=dict)):
    with Session(engine) as session:
        item = get_public_room_package(session, package_id)
        if not item:
            raise HTTPException(404, 'room package not found')
        pkg = item.get('package') if isinstance(item.get('package'), dict) else item
        agent_id = str((body or {}).get('agent_id') or (body or {}).get('agentId') or '').strip()
        if not agent_id:
            raise HTTPException(400, 'agent_id is required')
        invocation = create_borrowed_agent_invocation(
            source_room_package=pkg,
            agent_id=agent_id,
            target_room_id=str((body or {}).get('target_room_id') or (body or {}).get('targetRoomId') or 'current_room'),
            target_room_package_id=str((body or {}).get('target_room_package_id') or (body or {}).get('targetRoomPackageId') or 'current_room_package'),
            reason=str((body or {}).get('reason') or 'manual borrow preview'),
        )
        if not invocation:
            raise HTTPException(404, 'agent card not found in package')
        return {'ok': True, 'invocation': invocation}


@router.get('/threads/{thread_id}/room-components')
def get_thread_room_components(thread_id: str, q: str | None = Query(default=None), limit: int = 200):
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        items = _thread_packages(session, thread.id, limit=limit)
        return list_package_components(items, query=q or '', limit=limit)


@router.post('/threads/{thread_id}/room-borrow-recommendations')
def post_thread_room_borrow_recommendations(thread_id: str, body: dict[str, Any] = Body(default_factory=dict)):
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        public_items = _thread_packages(session, None, public_only=True, limit=int((body or {}).get('library_limit') or 200))
        thread_items = _thread_packages(session, thread.id, limit=int((body or {}).get('thread_limit') or 50))
        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        for item in [*thread_items, *public_items]:
            package_id = str(item.get('package_id') or (item.get('package') or {}).get('package_id') or '')
            key = f"{item.get('thread_id')}:{package_id}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return recommend_borrowed_agents(
            task_text=str((body or {}).get('task_text') or (body or {}).get('taskText') or ''),
            package_items=merged,
            target_room_id=thread.id,
            target_room_package_id=str((body or {}).get('target_room_package_id') or (body or {}).get('targetRoomPackageId') or 'current_room_package'),
            limit=int((body or {}).get('limit') or 8),
        )
