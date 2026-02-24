from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select

from app.db import engine
from app.models import ContextSet, Node, Thread
from app.schemas import ChatGPTImportRequest
from app.services.embedding import ensure_nodes_embeddings
from app.services.graph import add_edge, get_last_node, jdump, jload

router = APIRouter(prefix="/api", tags=["imports"])
logger = logging.getLogger(__name__)

SECTION_TAGS = ("FINAL", "DECISIONS", "ASSUMPTIONS", "PLAN", "CONTEXT_CANDIDATES")
SECTION_HEADER_RE = re.compile(
    r"^\s*\[(FINAL|DECISIONS|ASSUMPTIONS|PLAN|CONTEXT_CANDIDATES)\]\s*$"
)
BULLET_RE = re.compile(r"^\s*(?:[-*]\s+)+(.*\S)\s*$")
LIST_TAGS = (
    ("DECISIONS", "Decision"),
    ("ASSUMPTIONS", "Assumption"),
    ("PLAN", "Plan"),
    ("CONTEXT_CANDIDATES", "ContextCandidate"),
)


def parse_tagged_sections(raw_text: str) -> Tuple[Dict[str, str], bool]:
    chunks: Dict[str, List[str]] = {tag: [] for tag in SECTION_TAGS}
    found = False
    current_tag: Optional[str] = None
    buffer: List[str] = []

    lines = raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for line in lines:
        m = SECTION_HEADER_RE.match(line)
        if m:
            if current_tag is not None:
                section_text = "\n".join(buffer).strip()
                if section_text:
                    chunks[current_tag].append(section_text)
            current_tag = m.group(1)
            buffer = []
            found = True
            continue

        if current_tag is not None:
            buffer.append(line)

    if current_tag is not None:
        section_text = "\n".join(buffer).strip()
        if section_text:
            chunks[current_tag].append(section_text)

    sections: Dict[str, str] = {}
    for tag in SECTION_TAGS:
        if not chunks[tag]:
            continue
        sections[tag] = "\n\n".join(chunks[tag]).strip()
    return sections, found


def parse_bullets(text: str) -> List[str]:
    out: List[str] = []
    for line in text.splitlines():
        m = BULLET_RE.match(line)
        if not m:
            continue
        item = m.group(1).strip()
        if item:
            out.append(item)
    return out


def find_recent_user_message(session: Session, thread_id: str) -> Optional[Node]:
    nodes = session.exec(
        select(Node)
        .where(Node.thread_id == thread_id, Node.type == "Message")
        .order_by(Node.created_at.desc(), Node.id.desc())
    ).all()
    for node in nodes:
        meta = jload(node.payload_json, {})
        if meta.get("role") == "user":
            return node
    return None


@router.post("/threads/{thread_id}/import_chatgpt")
def import_chatgpt(thread_id: str, body: ChatGPTImportRequest):
    raw_text = (body.raw_text or "").strip()
    if not raw_text:
        raise HTTPException(400, "raw_text is required")

    with Session(engine) as s:
        t = s.get(Thread, thread_id)
        if not t:
            raise HTTPException(404, "thread not found")

        last_before_create = get_last_node(s, thread_id)

        reply_to_used: Optional[str] = None
        if body.reply_to:
            reply_node = s.get(Node, body.reply_to)
            if reply_node and reply_node.thread_id == thread_id:
                reply_to_used = reply_node.id

        if not reply_to_used:
            latest_user = find_recent_user_message(s, thread_id)
            if latest_user:
                reply_to_used = latest_user.id

        sections, found_any_tag = parse_tagged_sections(raw_text)
        if not found_any_tag:
            sections = {"FINAL": raw_text}

        source = body.source or "unknown"
        created_order: List[Node] = []
        decision_ids: List[str] = []
        assumption_ids: List[str] = []
        plan_ids: List[str] = []
        candidate_ids: List[str] = []
        final_node_id: Optional[str] = None

        final_text = (sections.get("FINAL") or "").strip()
        if final_text:
            final_node = Node(
                thread_id=thread_id,
                type="Message",
                text=final_text,
                payload_json=jdump({"role": "assistant", "source": source, "tag": "FINAL"}),
            )
            s.add(final_node)
            s.flush()
            created_order.append(final_node)
            final_node_id = final_node.id

        for tag, node_type in LIST_TAGS:
            for item in parse_bullets(sections.get(tag, "")):
                node = Node(
                    thread_id=thread_id,
                    type=node_type,
                    text=item,
                    payload_json=jdump({"source": source, "tag": tag}),
                )
                s.add(node)
                s.flush()
                created_order.append(node)
                if tag == "DECISIONS":
                    decision_ids.append(node.id)
                elif tag == "ASSUMPTIONS":
                    assumption_ids.append(node.id)
                elif tag == "PLAN":
                    plan_ids.append(node.id)
                elif tag == "CONTEXT_CANDIDATES":
                    candidate_ids.append(node.id)

        if created_order:
            if last_before_create:
                s.add(add_edge(thread_id, last_before_create.id, created_order[0].id, "NEXT"))

            for i in range(len(created_order) - 1):
                s.add(add_edge(thread_id, created_order[i].id, created_order[i + 1].id, "NEXT"))

            if reply_to_used:
                for node in created_order:
                    s.add(add_edge(thread_id, node.id, reply_to_used, "REPLY_TO"))

        auto_activate = body.auto_activate if body.auto_activate is not None else bool(body.context_set_id)
        if body.context_set_id and auto_activate and created_order:
            cs = s.get(ContextSet, body.context_set_id)
            if not cs or cs.thread_id != thread_id:
                raise HTTPException(404, "context set not found in thread")
            active_ids = jload(cs.active_node_ids_json, [])
            seen = set(active_ids)
            for node in created_order:
                if node.id in seen:
                    continue
                active_ids.append(node.id)
                seen.add(node.id)
            cs.active_node_ids_json = jdump(active_ids)
            s.add(cs)

        s.commit()
        warning = None
        if created_order:
            try:
                ensure_nodes_embeddings(s, created_order, commit=True)
            except Exception as e:
                warning = f"embedding failed: {e}"
                logger.exception("import embedding failed (thread_id=%s)", thread_id)

        return {
            "ok": True,
            "created": {
                "final_node_id": final_node_id,
                "decision_ids": decision_ids,
                "assumption_ids": assumption_ids,
                "plan_ids": plan_ids,
                "candidate_ids": candidate_ids,
            },
            "created_order": [n.id for n in created_order],
            "reply_to_used": reply_to_used,
            "warning": warning,
        }
