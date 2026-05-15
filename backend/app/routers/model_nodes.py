from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query
from sqlmodel import Session

from app.db import engine
from app.services.model_catalog import ingest_model_usage, list_model_nodes, list_model_usage, upsert_model_nodes
from app.auth import get_current_principal
from fastapi import HTTPException


def require_catalog_write() -> None:
    principal = get_current_principal()
    if principal.role not in {"admin", "service"}:
        raise HTTPException(403, "model catalog write requires admin or service principal")

router = APIRouter(prefix="/api/model-nodes", tags=["model-nodes"])


@router.get("")
def get_model_nodes(provider: str | None = Query(default=None), limit: int = 200):
    with Session(engine) as session:
        return list_model_nodes(session, provider=provider, limit=limit)


@router.post("")
def post_model_nodes(body: dict[str, Any] = Body(default_factory=dict)):
    require_catalog_write()
    with Session(engine) as session:
        return upsert_model_nodes(session, body or {}, source=str((body or {}).get("source") or "ddalggak"))


@router.get("/usage")
def get_model_node_usage(thread_id: str | None = Query(default=None), run_id: str | None = Query(default=None), limit: int = 100):
    with Session(engine) as session:
        return list_model_usage(session, thread_id=thread_id, run_id=run_id, limit=limit)


@router.post("/usage")
def post_model_node_usage(body: dict[str, Any] = Body(default_factory=dict)):
    require_catalog_write()
    with Session(engine) as session:
        return ingest_model_usage(session, body or {}, source=str((body or {}).get("source") or "ddalggak"))
