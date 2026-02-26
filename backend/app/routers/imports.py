from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select

from app.db import engine
from app.models import ContextSet, Node, Thread
from app.schemas import ChatGPTImportRequest
from app.services.context_versions import snapshot_context_set
from app.services.embedding import ensure_nodes_embeddings
from app.services.graph import add_edge, get_last_node, jdump, jload

router = APIRouter(prefix="/api", tags=["imports"])
logger = logging.getLogger(__name__)

SECTION_TAGS = (
    "FINAL",
    "MEMORY",
    "NEEDS_CONTEXT",
    "DECISIONS",
    "ASSUMPTIONS",
    "PLAN",
    "CONTEXT_CANDIDATES",
)
SECTION_HEADER_RE = re.compile(
    r"^\s*\[(FINAL|MEMORY|NEEDS_CONTEXT|DECISIONS|ASSUMPTIONS|PLAN|CONTEXT_CANDIDATES)\]\s*$"
)
BULLET_RE = re.compile(r"^\s*(?:[-*]\s+)+(.*\S)\s*$")
MEMORY_PREFIX_RE = re.compile(r"^\s*([A-Za-z가-힣_][A-Za-z0-9가-힣_\- ]{0,40})\s*:\s*(.+\S)\s*$")

LEGACY_LIST_TAGS = (
    ("DECISIONS", "Decision", "decision"),
    ("ASSUMPTIONS", "Assumption", "assumption"),
    ("PLAN", "Plan", "next_step"),
    ("CONTEXT_CANDIDATES", "ContextCandidate", "needs_context"),
)

MEMORY_PREFIX_MAP = {
    "decision": ("Decision", "decision"),
    "결정": ("Decision", "decision"),
    "assumption": ("Assumption", "assumption"),
    "전제": ("Assumption", "assumption"),
    "가정": ("Assumption", "assumption"),
    "next_step": ("Plan", "next_step"),
    "next step": ("Plan", "next_step"),
    "plan": ("Plan", "next_step"),
    "action": ("Plan", "next_step"),
    "todo": ("Plan", "next_step"),
    "memory": ("MemoryItem", "memory"),
    "note": ("MemoryItem", "memory"),
    "insight": ("MemoryItem", "memory"),
    "fact": ("MemoryItem", "memory"),
    "constraint": ("MemoryItem", "memory"),
    "preference": ("MemoryItem", "memory"),
    "기억": ("MemoryItem", "memory"),
    "메모": ("MemoryItem", "memory"),
    "선호": ("MemoryItem", "memory"),
    "제약": ("MemoryItem", "memory"),
}


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


def parse_memory_items(text: str) -> List[Tuple[str, str, str]]:
    parsed: List[Tuple[str, str, str]] = []
    for item in parse_bullets(text):
        m = MEMORY_PREFIX_RE.match(item)
        if not m:
            parsed.append(("MemoryItem", item, "memory"))
            continue
        prefix = re.sub(r"\s+", " ", m.group(1).strip().lower())
        clean_text = m.group(2).strip()
        node_type, memory_kind = MEMORY_PREFIX_MAP.get(prefix, ("MemoryItem", "memory"))
        parsed.append((node_type, clean_text, memory_kind))
    return parsed


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
        parse_mode = "tagged" if found_any_tag else "free"
        if not found_any_tag:
            sections = {"FINAL": raw_text}

        source = body.source or "unknown"
        created_order: List[Node] = []
        decision_ids: List[str] = []
        assumption_ids: List[str] = []
        plan_ids: List[str] = []
        candidate_ids: List[str] = []
        memory_item_ids: List[str] = []
        final_node_id: Optional[str] = None

        final_text = (sections.get("FINAL") or "").strip()
        if final_text:
            final_node = Node(
                thread_id=thread_id,
                type="Message",
                text=final_text,
                payload_json=jdump({"role": "assistant", "source": source, "tag": "FINAL", "parse_mode": parse_mode}),
            )
            s.add(final_node)
            s.flush()
            created_order.append(final_node)
            final_node_id = final_node.id

        memory_section = sections.get("MEMORY") or ""
        if memory_section.strip():
            parse_mode = "light"
            for node_type, text, memory_kind in parse_memory_items(memory_section):
                node = Node(
                    thread_id=thread_id,
                    type=node_type,
                    text=text,
                    payload_json=jdump({"source": source, "tag": "MEMORY", "memory_kind": memory_kind, "parse_mode": "light"}),
                )
                s.add(node)
                s.flush()
                created_order.append(node)
                if node_type == "Decision":
                    decision_ids.append(node.id)
                elif node_type == "Assumption":
                    assumption_ids.append(node.id)
                elif node_type == "Plan":
                    plan_ids.append(node.id)
                else:
                    memory_item_ids.append(node.id)

        needs_context_text = sections.get("NEEDS_CONTEXT") or ""
        if needs_context_text.strip():
            parse_mode = "light"
            for item in parse_bullets(needs_context_text):
                node = Node(
                    thread_id=thread_id,
                    type="ContextCandidate",
                    text=item,
                    payload_json=jdump({"source": source, "tag": "NEEDS_CONTEXT", "memory_kind": "needs_context", "parse_mode": "light"}),
                )
                s.add(node)
                s.flush()
                created_order.append(node)
                candidate_ids.append(node.id)

        legacy_item_count = 0
        for tag, node_type, memory_kind in LEGACY_LIST_TAGS:
            items = parse_bullets(sections.get(tag, ""))
            if not items:
                continue
            parse_mode = "full"
            for item in items:
                node = Node(
                    thread_id=thread_id,
                    type=node_type,
                    text=item,
                    payload_json=jdump({"source": source, "tag": tag, "memory_kind": memory_kind, "parse_mode": "full"}),
                )
                s.add(node)
                s.flush()
                created_order.append(node)
                legacy_item_count += 1
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
            snapshot_context_set(
                s,
                cs,
                reason='import_chatgpt',
                changed_node_ids=[n.id for n in created_order],
                meta={'source': source, 'created_count': len(created_order), 'parse_mode': parse_mode},
            )

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
            "parse_mode": parse_mode,
            "created": {
                "final_node_id": final_node_id,
                "decision_ids": decision_ids,
                "assumption_ids": assumption_ids,
                "plan_ids": plan_ids,
                "candidate_ids": candidate_ids,
                "memory_item_ids": memory_item_ids,
                "legacy_item_count": legacy_item_count,
            },
            "created_order": [n.id for n in created_order],
            "reply_to_used": reply_to_used,
            "warning": warning,
        }
