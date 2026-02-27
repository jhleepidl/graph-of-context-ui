from __future__ import annotations
from fastapi import APIRouter, Query
from sqlmodel import Session

from app.db import engine
from app.schemas import SearchResponseItem
from app.services.embedding import search_nodes
from app.tenant import require_thread_access

router = APIRouter(prefix="/api", tags=["search"])

@router.get("/threads/{thread_id}/search")
def search(thread_id: str, q: str = Query(min_length=1), k: int = 10):
    with Session(engine) as s:
        require_thread_access(s, thread_id)
        results, coverage = search_nodes(s, thread_id, q, k=k)
        out = []
        for node, score in results:
            snippet = (node.text or "").replace("\n", " ")
            snippet = snippet[:220]
            out.append(SearchResponseItem(
                node_id=node.id,
                score=score,
                node_type=node.type,
                snippet=snippet
            ).model_dump())
        return {"ok": True, "results": out, "coverage": coverage}
