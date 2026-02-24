from __future__ import annotations
import json
import logging
from fastapi import APIRouter, HTTPException
from sqlmodel import Session

from app.db import engine
from app.models import Node, Thread, ContextSet
from app.schemas import MessageCreate, ResourceNodeCreate
from app.services.graph import add_edge, get_last_node
from app.services.embedding import ensure_node_embedding

router = APIRouter(prefix="/api", tags=["messages"])
logger = logging.getLogger(__name__)

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


def _resource_text(body: ResourceNodeCreate) -> str:
    lines = [f"Resource: {body.name.strip()}"]
    if body.resource_kind:
        lines.append(f"Kind: {body.resource_kind}")
    if body.mime_type:
        lines.append(f"MIME: {body.mime_type}")
    if body.uri:
        lines.append(f"URI: {body.uri.strip()}")
    if body.source:
        lines.append(f"Source: {body.source}")
    summary = (body.summary or '').strip()
    if summary:
        lines.append('Summary:')
        lines.append(summary)
    return '\n'.join(lines).strip()


@router.post("/threads/{thread_id}/resources")
def add_resource(thread_id: str, body: ResourceNodeCreate):
    name = (body.name or '').strip()
    if not name:
        raise HTTPException(400, 'name is required')

    with Session(engine) as s:
        t = s.get(Thread, thread_id)
        if not t:
            raise HTTPException(404, 'thread not found')

        attach_to_id = None
        if body.attach_to:
            attach_target = s.get(Node, body.attach_to)
            if attach_target and attach_target.thread_id == thread_id:
                attach_to_id = attach_target.id

        last = get_last_node(s, thread_id)
        payload = {
            'name': name,
            'resource_kind': (body.resource_kind or 'file').strip() or 'file',
            'mime_type': (body.mime_type or '').strip() or None,
            'uri': (body.uri or '').strip() or None,
            'source': body.source or 'unknown',
            'tag': 'RESOURCE',
        }
        if body.summary and body.summary.strip():
            payload['summary'] = body.summary.strip()

        node = Node(
            thread_id=thread_id,
            type='Resource',
            text=_resource_text(body),
            payload_json=jdump(payload),
        )
        s.add(node)
        s.flush()

        if last and last.id != node.id:
            s.add(add_edge(thread_id, last.id, node.id, 'NEXT'))
        if attach_to_id:
            s.add(add_edge(thread_id, attach_to_id, node.id, 'ATTACHED_TO'))

        if body.context_set_id and body.auto_activate:
            cs = s.get(ContextSet, body.context_set_id)
            if cs and cs.thread_id == thread_id:
                try:
                    active_ids = json.loads(cs.active_node_ids_json or '[]')
                except Exception:
                    active_ids = []
                if node.id not in active_ids:
                    active_ids.append(node.id)
                    cs.active_node_ids_json = jdump(active_ids)
                    s.add(cs)

        s.commit()
        s.refresh(node)

        warning = None
        try:
            ensure_node_embedding(s, node, commit=True)
        except Exception as e:
            warning = f'embedding failed: {e}'
            logger.exception('resource embedding failed (thread_id=%s, node_id=%s)', thread_id, node.id)

        return {'ok': True, 'node': node.model_dump(), 'attached_to': attach_to_id, 'warning': warning}
