from __future__ import annotations
import json
import logging
from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select

from app.config import get_env
from app.db import engine
from app.models import Node, Edge, ContextSet
from app.schemas import FoldCreate
from app.llm import call_openai
from app.services.embedding import ensure_node_embedding
from app.services.graph import add_edge, get_last_node, replace_ids_in_order

router = APIRouter(prefix="/api", tags=["folds"])
logger = logging.getLogger(__name__)
FOLD_SUMMARY_MODEL = get_env("GOC_FOLD_SUMMARY_MODEL", "gpt-5-nano") or "gpt-5-nano"

def jdump(x) -> str:
    return json.dumps(x, ensure_ascii=False)

def jload(s: str, default):
    try:
        return json.loads(s)
    except Exception:
        return default

def summarize_fold(texts):
    instructions = (
        "너는 사용자가 선택한 컨텍스트 노드들을 요약하는 도우미다.\n"
        "규칙:\n"
        "- 한국어로\n"
        "- 5~8개 불릿\n"
        "- 추측 금지\n"
    )
    joined = "\n\n---\n\n".join(texts)
    prompt = f"[원문]\n{joined}\n\n[요약]"
    return call_openai(instructions, prompt, model=FOLD_SUMMARY_MODEL)

@router.post("/folds")
def create_fold(body: FoldCreate):
    if len(body.member_node_ids) < 2:
        raise HTTPException(400, "need at least 2 nodes to fold")

    with Session(engine) as s:
        members = []
        for nid in body.member_node_ids:
            n = s.get(Node, nid)
            if not n or n.thread_id != body.thread_id:
                raise HTTPException(404, f"node not found in thread: {nid}")
            members.append(n)

        members_sorted = sorted(members, key=lambda x: x.created_at)
        summary = summarize_fold([(m.text or "") for m in members_sorted])

        last = get_last_node(s, body.thread_id)
        fold = Node(
            thread_id=body.thread_id,
            type="Fold",
            text=summary,
            payload_json=jdump({"title": body.title or "Fold", "member_count": len(members_sorted)}),
        )
        s.add(fold)
        if last:
            s.add(add_edge(body.thread_id, last.id, fold.id, "NEXT"))

        for i, m in enumerate(members_sorted):
            s.add(add_edge(body.thread_id, fold.id, m.id, "FOLDS", {"index": i}))

        s.commit()
        s.refresh(fold)
        warning = None
        try:
            ensure_node_embedding(s, fold, commit=True)
        except Exception as e:
            warning = f"embedding failed: {e}"
            logger.exception("fold embedding failed (thread_id=%s, fold_id=%s)", body.thread_id, fold.id)

        return {"ok": True, "fold_id": fold.id, "warning": warning}

@router.post("/context_sets/{context_set_id}/unfold/{fold_id}")
def unfold(context_set_id: str, fold_id: str):
    with Session(engine) as s:
        cs = s.get(ContextSet, context_set_id)
        if not cs:
            raise HTTPException(404, "context set not found")
        fold = s.get(Node, fold_id)
        if not fold or fold.type != "Fold":
            raise HTTPException(404, "fold not found")

        edges = s.exec(
            select(Edge)
            .where(Edge.thread_id == fold.thread_id, Edge.from_id == fold_id, Edge.type == "FOLDS")
        ).all()
        members = [e.to_id for e in sorted(edges, key=lambda x: jload(x.payload_json, {}).get("index", 0))]

        active = replace_ids_in_order(jload(cs.active_node_ids_json, []), fold_id, members)

        cs.active_node_ids_json = jdump(active)
        s.add(cs)
        s.commit()

        return {"ok": True, "active_node_ids": active, "members": members}
