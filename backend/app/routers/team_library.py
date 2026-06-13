from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from sqlmodel import Session

from app.db import engine
from app.models import Thread
from app.services.team_packages import (
    build_team_package_fork_preview,
    get_public_team_package,
    list_public_team_library,
    list_thread_team_packages,
    upsert_thread_team_package,
)
from app.tenant import require_thread_access, require_thread_write_access

router = APIRouter(prefix='/api', tags=['team-library'])


@router.get('/team-library')
def get_team_library(q: str | None = Query(default=None), limit: int = 100):
    with Session(engine) as session:
        return list_public_team_library(session, query=q or '', limit=limit)


@router.get('/team-library/{package_id}')
def get_team_library_package(package_id: str):
    with Session(engine) as session:
        item = get_public_team_package(session, package_id)
        if not item:
            raise HTTPException(404, 'team package not found')
        return {'ok': True, 'package': item}


@router.post('/team-library/{package_id}/fork-preview')
def post_team_library_fork_preview(package_id: str, body: dict[str, Any] = Body(default_factory=dict)):
    with Session(engine) as session:
        item = get_public_team_package(session, package_id)
        if not item:
            raise HTTPException(404, 'team package not found')
        return build_team_package_fork_preview(item, title=(body or {}).get('title'))


@router.get('/threads/{thread_id}/team-packages')
def get_thread_team_packages(thread_id: str, limit: int = 100):
    with Session(engine) as session:
        thread = require_thread_access(session, thread_id)
        return list_thread_team_packages(session, thread, limit=limit)


@router.post('/threads/{thread_id}/team-packages')
def post_thread_team_package(thread_id: str, body: dict[str, Any] = Body(default_factory=dict)):
    with Session(engine) as session:
        thread = require_thread_write_access(session, thread_id)
        try:
            return upsert_thread_team_package(session, thread, body or {}, source=str((body or {}).get('source') or 'ddalggak'))
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
