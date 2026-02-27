from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlmodel import Session

from app.db import engine
from app.schemas import HierarchyPreviewRequest
from app.services.graph import jload
from app.services.hierarchy import build_hierarchy_preview
from app.tenant import require_context_set_access, require_thread_access

router = APIRouter(prefix="/api", tags=["hierarchy"])


@router.post("/threads/{thread_id}/hierarchy_preview")
def hierarchy_preview(thread_id: str, body: HierarchyPreviewRequest):
    with Session(engine) as s:
        require_thread_access(s, thread_id)

        node_ids = list(body.node_ids or []) if body.node_ids is not None else None

        if body.context_set_id:
            cs = require_context_set_access(s, body.context_set_id)
            if cs.thread_id != thread_id:
                raise HTTPException(404, "context set not found in thread")
            if node_ids is None:
                node_ids = [x for x in jload(cs.active_node_ids_json, []) if isinstance(x, str)]

        out = build_hierarchy_preview(
            s,
            thread_id,
            node_ids=node_ids,
            max_leaf_size=body.max_leaf_size,
        )
        out["scope"] = {
            "thread_id": thread_id,
            "context_set_id": body.context_set_id,
            "node_count_filter": len(node_ids or []) if node_ids is not None else None,
        }
        return out
