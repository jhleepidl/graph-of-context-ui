from __future__ import annotations
import json
from fastapi import APIRouter, HTTPException
from sqlmodel import Session

from app.db import engine
from app.models import ContextSet, Thread, Node
from app.schemas import RunCreate
from app.llm import call_openai
from app.services.graph import add_edge, get_last_node, jload
from app.services.graph import compile_active_context

router = APIRouter(prefix="/api", tags=["runs"])

def jdump(x) -> str:
    return json.dumps(x, ensure_ascii=False)

@router.post("/runs")
def run_agent(body: RunCreate):
    with Session(engine) as s:
        cs = s.get(ContextSet, body.context_set_id)
        if not cs:
            raise HTTPException(404, "context set not found")
        thread_id = cs.thread_id
        t = s.get(Thread, thread_id)
        if not t:
            raise HTTPException(404, "thread not found")

        active_ids = jload(cs.active_node_ids_json, [])
        active_ctx_text = compile_active_context(s, thread_id, active_ids)

        # Run node
        run_node = Node(
            thread_id=thread_id,
            type="Run",
            text=None,
            payload_json=jdump({"context_set_id": cs.id, "active_count": len(active_ids)}),
        )

        # User message node
        user_msg = Node(
            thread_id=thread_id,
            type="Message",
            text=body.user_message,
            payload_json=jdump({"role": "user"}),
        )

        last = get_last_node(s, thread_id)

        s.add(run_node)
        s.add(user_msg)

        if last:
            s.add(add_edge(thread_id, last.id, user_msg.id, "NEXT"))

        s.add(add_edge(thread_id, user_msg.id, run_node.id, "IN_RUN"))
        for nid in active_ids:
            s.add(add_edge(thread_id, nid, run_node.id, "USED_IN_RUN"))

        instructions = (
            "너는 사용자가 선택한 ACTIVE CONTEXT만을 근거로 답하는 LLM Agent다.\n"
            "ACTIVE CONTEXT에 없는 정보가 필요하면, 어떤 노드를 활성화해야 하는지 되물어라.\n"
            "한국어로 답하라."
        )
        prompt = f"""[ACTIVE CONTEXT]\n{active_ctx_text}\n\n[USER REQUEST]\n{body.user_message}\n"""
        response_text = call_openai(instructions, prompt)

        asst_msg = Node(
            thread_id=thread_id,
            type="Message",
            text=response_text,
            payload_json=jdump({"role": "assistant"}),
        )

        s.add(asst_msg)
        s.add(add_edge(thread_id, user_msg.id, asst_msg.id, "NEXT"))
        s.add(add_edge(thread_id, asst_msg.id, user_msg.id, "REPLY_TO"))
        s.add(add_edge(thread_id, asst_msg.id, run_node.id, "IN_RUN"))

        s.commit()
        s.refresh(run_node)
        s.refresh(asst_msg)

        return {
            "ok": True,
            "thread_id": thread_id,
            "run_id": run_node.id,
            "response_text": response_text,
            "active_node_ids": active_ids,
        }
