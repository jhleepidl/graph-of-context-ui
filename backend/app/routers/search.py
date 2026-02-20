from __future__ import annotations
from fastapi import APIRouter, HTTPException, Query
from sqlmodel import Session

from app.db import engine
from app.models import Thread
from app.schemas import SearchResponseItem
from app.services.embedding import search_nodes

router = APIRouter(prefix="/api", tags=["search"])

@router.get("/threads/{thread_id}/search")
def search(thread_id: str, q: str = Query(min_length=1), k: int = 10):
    with Session(engine) as s:
        t = s.get(Thread, thread_id)
        if not t:
            raise HTTPException(404, "thread not found")
        results = search_nodes(s, thread_id, q, k=k)
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
        return {"ok": True, "results": out}
