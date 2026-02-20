from __future__ import annotations
import json
from fastapi import APIRouter, HTTPException
from sqlmodel import Session

from app.db import engine
from app.models import Node, Thread
from app.schemas import MessageCreate
from app.services.graph import add_edge, get_last_node

router = APIRouter(prefix="/api", tags=["messages"])

def jdump(x) -> str:
    return json.dumps(x, ensure_ascii=False)

@router.post("/threads/{thread_id}/messages")
def add_message(thread_id: str, body: MessageCreate):
    if body.role not in ("user", "assistant"):
        raise HTTPException(400, "role must be user|assistant")

    with Session(engine) as s:
        t = s.get(Thread, thread_id)
        if not t:
            raise HTTPException(404, "thread not found")

        last = get_last_node(s, thread_id)
        n = Node(thread_id=thread_id, type="Message", text=body.text, payload_json=jdump({"role": body.role}))
        s.add(n)
        if last:
            s.add(add_edge(thread_id, last.id, n.id, "NEXT"))
        if body.reply_to:
            s.add(add_edge(thread_id, n.id, body.reply_to, "REPLY_TO"))
        s.commit()
        s.refresh(n)
        return n.model_dump()
