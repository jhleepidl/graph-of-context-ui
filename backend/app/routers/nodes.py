from __future__ import annotations

import re
from typing import Dict, List, Tuple

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select

from app.db import engine
from app.models import ContextSet, Edge, Node
from app.schemas import SplitNodeRequest, SplitNodeResponse
from app.services.embedding import ensure_node_embedding
from app.services.graph import add_edge, jdump, jload

router = APIRouter(prefix="/api", tags=["nodes"])

TAG_HEADER_RE = re.compile(r"^\s*\[(FINAL|DECISIONS|ASSUMPTIONS|PLAN|CONTEXT_CANDIDATES)\]\s*$")
HEADING_RE = re.compile(r"^\s*(?:#{1,6}\s+.+|\d+[\).\s].+)$")
BULLET_START_RE = re.compile(r"^\s*(?:[-*•]\s+|\d+\.\s+)(.*\S)\s*$")
FENCE_START_RE = re.compile(r"^\s*([`~]{3,})")
BULLET_TAGS = {"DECISIONS", "ASSUMPTIONS", "PLAN", "CONTEXT_CANDIDATES"}
STRATEGY_CHAIN = ("tagged", "heading", "bullets", "paragraph", "sentences")


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def to_int(value, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def norm_limits(target_chars: int | None, max_chars: int | None) -> Tuple[int, int]:
    target = max(200, to_int(target_chars, 900))
    max_len = max(400, to_int(max_chars, 2000))
    if target > max_len:
        target = max_len
    return target, max_len


def is_table_line(line: str) -> bool:
    return line.count("|") >= 2


def split_preserving_blocks(text: str) -> List[Dict[str, str]]:
    lines = normalize_newlines(text).split("\n")
    out: List[Dict[str, str]] = []
    text_buf: List[str] = []
    i = 0
    in_code = False
    code_lines: List[str] = []
    fence_char = ""

    def flush_text_buffer() -> None:
        if not text_buf:
            return
        merged = "\n".join(text_buf).strip()
        text_buf.clear()
        if merged:
            out.append({"kind": "text", "text": merged})

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if in_code:
            code_lines.append(line)
            if stripped.startswith(fence_char * 3):
                merged = "\n".join(code_lines).strip()
                if merged:
                    out.append({"kind": "code", "text": merged})
                code_lines = []
                in_code = False
                fence_char = ""
            i += 1
            continue

        fence = FENCE_START_RE.match(line)
        if fence:
            flush_text_buffer()
            marker = fence.group(1)
            fence_char = marker[0]
            in_code = True
            code_lines = [line]
            i += 1
            continue

        if is_table_line(line):
            flush_text_buffer()
            tbl_lines = [line]
            i += 1
            while i < len(lines) and is_table_line(lines[i]):
                tbl_lines.append(lines[i])
                i += 1
            merged = "\n".join(tbl_lines).strip()
            if merged:
                out.append({"kind": "table", "text": merged})
            continue

        text_buf.append(line)
        i += 1

    if in_code and code_lines:
        merged = "\n".join(code_lines).strip()
        if merged:
            out.append({"kind": "code", "text": merged})

    flush_text_buffer()
    return out


def split_by_paragraphs(text: str) -> Tuple[List[Dict[str, str]], bool]:
    raw = normalize_newlines(text).strip()
    if not raw:
        return [], False
    pieces = [p.strip() for p in re.split(r"\n\s*\n+", raw) if p.strip()]
    if not pieces:
        return [], False
    return [{"kind": "paragraph", "text": p} for p in pieces], len(pieces) > 1


def split_hard(text: str, target_chars: int, max_chars: int) -> List[str]:
    out: List[str] = []
    rest = text.strip()
    if not rest:
        return out

    while len(rest) > max_chars:
        ideal = min(max_chars, max(200, target_chars))
        window = rest[:max_chars]
        start = max(0, ideal - 240)
        cut = -1
        for i in range(min(max_chars, len(window)) - 1, start - 1, -1):
            if window[i].isspace() or window[i] in ",.;:!?)]}":
                cut = i + 1
                break
        if cut <= 0:
            cut = max_chars
        piece = rest[:cut].strip()
        if piece:
            out.append(piece)
        rest = rest[cut:].lstrip()

    if rest:
        out.append(rest)
    return out


def split_by_sentences(text: str, target_chars: int, max_chars: int) -> List[str]:
    raw = re.sub(r"\s+", " ", text.strip())
    if not raw:
        return []

    sentences = [s.strip() for s in re.split(r"(?<=[\.\!\?。！？])\s+", raw) if s.strip()]
    if len(sentences) <= 1:
        return split_hard(raw, target_chars, max_chars)

    out: List[str] = []
    cur = ""
    for sent in sentences:
        if len(sent) > max_chars:
            if cur:
                out.append(cur.strip())
                cur = ""
            out.extend(split_hard(sent, target_chars, max_chars))
            continue

        candidate = f"{cur} {sent}".strip() if cur else sent
        if len(candidate) <= max_chars and (len(candidate) <= target_chars or not cur):
            cur = candidate
            continue

        if cur:
            out.append(cur.strip())
        cur = sent

    if cur:
        out.append(cur.strip())
    return [s for s in out if s]


def split_by_headings(text: str) -> Tuple[List[Dict[str, str]], bool]:
    lines = normalize_newlines(text).split("\n")
    chunks: List[str] = []
    buf: List[str] = []
    matched = False

    for line in lines:
        if HEADING_RE.match(line):
            matched = True
            if buf:
                merged = "\n".join(buf).strip()
                if merged:
                    chunks.append(merged)
            buf = [line]
            continue
        buf.append(line)

    if buf:
        merged = "\n".join(buf).strip()
        if merged:
            chunks.append(merged)

    if not chunks:
        return [], False
    return [{"kind": "heading", "text": c} for c in chunks], matched


def split_by_bullets(text: str) -> Tuple[List[Dict[str, str]], bool]:
    lines = normalize_newlines(text).split("\n")
    i = 0
    matched = False
    out: List[Dict[str, str]] = []
    plain_buf: List[str] = []

    def flush_plain() -> None:
        if not plain_buf:
            return
        merged = "\n".join(plain_buf).strip()
        plain_buf.clear()
        if merged:
            out.append({"kind": "paragraph", "text": merged})

    while i < len(lines):
        line = lines[i]
        m = BULLET_START_RE.match(line)
        if not m:
            plain_buf.append(line)
            i += 1
            continue

        matched = True
        flush_plain()
        item_lines = [m.group(1).strip()]
        i += 1
        while i < len(lines):
            nxt = lines[i]
            if BULLET_START_RE.match(nxt):
                break
            if nxt.startswith(" ") or nxt.startswith("\t"):
                item_lines.append(nxt.strip())
                i += 1
                continue
            if nxt.strip() == "" and i + 1 < len(lines) and (lines[i + 1].startswith(" ") or lines[i + 1].startswith("\t")):
                item_lines.append("")
                i += 1
                continue
            break

        merged = "\n".join(item_lines).strip()
        if merged:
            out.append({"kind": "bullet", "text": merged})

    flush_plain()
    return out, matched


def split_by_tagged(text: str) -> Tuple[List[Dict[str, str]], bool]:
    lines = normalize_newlines(text).split("\n")
    preamble: List[str] = []
    sec_tag: str | None = None
    sec_buf: List[str] = []
    sections: List[Tuple[str | None, str]] = []
    found = False

    for line in lines:
        m = TAG_HEADER_RE.match(line)
        if m:
            found = True
            if sec_tag is not None:
                sections.append((sec_tag, "\n".join(sec_buf).strip()))
            elif preamble:
                sections.append((None, "\n".join(preamble).strip()))
            sec_tag = m.group(1)
            sec_buf = []
            preamble = []
            continue

        if sec_tag is None:
            preamble.append(line)
        else:
            sec_buf.append(line)

    if sec_tag is not None:
        sections.append((sec_tag, "\n".join(sec_buf).strip()))
    elif preamble:
        sections.append((None, "\n".join(preamble).strip()))

    if not found:
        return [], False

    out: List[Dict[str, str]] = []
    for tag, body in sections:
        body = (body or "").strip()
        if not body:
            continue

        if tag in BULLET_TAGS:
            chunks, has_bullets = split_by_bullets(body)
            bullet_chunks = [c for c in chunks if c["kind"] == "bullet"]
            non_bullets = [c for c in chunks if c["kind"] != "bullet"]
            if has_bullets and bullet_chunks:
                out.extend(bullet_chunks)
                merged_rest = "\n\n".join(c["text"] for c in non_bullets if c["text"].strip()).strip()
                if merged_rest:
                    out.append({"kind": "tag", "text": merged_rest})
                continue

        out.append({"kind": "tag", "text": body})

    return out, True


def split_text_by_strategy(text: str, strategy: str, target_chars: int, max_chars: int) -> Tuple[List[Dict[str, str]], bool]:
    if strategy == "tagged":
        return split_by_tagged(text)
    if strategy == "heading":
        return split_by_headings(text)
    if strategy == "bullets":
        return split_by_bullets(text)
    if strategy == "paragraph":
        return split_by_paragraphs(text)
    if strategy == "sentences":
        parts = split_by_sentences(text, target_chars, max_chars)
        return [{"kind": "paragraph", "text": p} for p in parts], bool(parts)
    return [], False


def enforce_chunk_size(chunks: List[Dict[str, str]], target_chars: int, max_chars: int) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for chunk in chunks:
        kind = chunk["kind"]
        text = (chunk["text"] or "").strip()
        if not text:
            continue
        if kind in {"code", "table"} or len(text) <= max_chars:
            out.append({"kind": kind, "text": text})
            continue

        for part in split_by_sentences(text, target_chars, max_chars):
            if part:
                out.append({"kind": kind, "text": part})
    return out


def split_with_strategy(source_text: str, strategy: str, target_chars: int, max_chars: int) -> Tuple[List[Dict[str, str]], bool]:
    segments = split_preserving_blocks(source_text)
    out: List[Dict[str, str]] = []
    matched_any = False

    for seg in segments:
        seg_kind = seg["kind"]
        seg_text = seg["text"]
        if not seg_text.strip():
            continue

        if seg_kind in {"code", "table"}:
            out.append({"kind": seg_kind, "text": seg_text.strip()})
            continue

        text_chunks, matched = split_text_by_strategy(seg_text, strategy, target_chars, max_chars)
        matched_any = matched_any or matched
        if text_chunks:
            out.extend(text_chunks)
        else:
            out.append({"kind": "paragraph", "text": seg_text.strip()})

    return enforce_chunk_size(out, target_chars, max_chars), matched_any


def split_custom(custom_text: str, target_chars: int, max_chars: int) -> List[Dict[str, str]]:
    parts = [p.strip() for p in re.split(r"\n\s*\n+", normalize_newlines(custom_text)) if p.strip()]
    chunks = [{"kind": "custom", "text": p} for p in parts]
    return enforce_chunk_size(chunks, target_chars, max_chars)


def strategy_for_auto(text: str, target_chars: int, max_chars: int) -> str:
    for strategy in STRATEGY_CHAIN:
        _, matched = split_with_strategy(text, strategy, target_chars, max_chars)
        if matched:
            return strategy
    return "sentences"


def sorted_part_edges(session: Session, thread_id: str, parent_id: str) -> List[Edge]:
    edges = session.exec(
        select(Edge)
        .where(Edge.thread_id == thread_id, Edge.from_id == parent_id, Edge.type == "HAS_PART")
        .order_by(Edge.created_at.asc(), Edge.id.asc())
    ).all()
    return sorted(edges, key=lambda e: to_int(jload(e.payload_json, {}).get("index"), 0))


@router.get("/nodes/{node_id}")
def get_node(node_id: str):
    with Session(engine) as s:
        node = s.get(Node, node_id)
        if not node:
            raise HTTPException(404, "node not found")

        part_edges = sorted_part_edges(s, node.thread_id, node_id)
        parts: List[dict] = []
        for e in part_edges:
            child = s.get(Node, e.to_id)
            if not child or child.thread_id != node.thread_id:
                continue
            parts.append(child.model_dump())

        out = node.model_dump()
        out["parts"] = parts
        out["part_edges"] = [e.model_dump() for e in part_edges]
        return out


@router.post("/nodes/{node_id}/split")
def split_node(node_id: str, body: SplitNodeRequest):
    with Session(engine) as s:
        parent = s.get(Node, node_id)
        if not parent:
            raise HTTPException(404, "node not found")
        thread_id = parent.thread_id

        target_chars, max_chars = norm_limits(body.target_chars, body.max_chars)

        if body.strategy == "custom":
            custom_text = (body.custom_text or "").strip()
            if not custom_text:
                raise HTTPException(400, "custom_text is required when strategy=custom")
            strategy_used = "custom"
            chunks = split_custom(custom_text, target_chars, max_chars)
        else:
            source_text = (parent.text or "").strip()
            if not source_text:
                raise HTTPException(400, "parent node text is empty")
            strategy_used = body.strategy
            if strategy_used == "auto":
                strategy_used = strategy_for_auto(source_text, target_chars, max_chars)
            chunks, _ = split_with_strategy(source_text, strategy_used, target_chars, max_chars)

        if not chunks:
            raise HTTPException(400, "no chunks produced")

        child_type = (body.child_type or "").strip() or "ContextAtom"
        origin_created_at = parent.created_at.isoformat()
        created_nodes: List[Node] = []
        chunk_kinds: List[str] = []

        for i, chunk in enumerate(chunks):
            ctext = (chunk.get("text") or "").strip()
            if not ctext:
                continue
            ckind = chunk.get("kind") or "paragraph"
            child = Node(
                thread_id=thread_id,
                type=child_type,
                text=ctext,
                payload_json=jdump(
                    {
                        "source": "split",
                        "parent_id": parent.id,
                        "chunk_index": i,
                        "chunk_kind": ckind,
                        "origin_created_at": origin_created_at,
                    }
                ),
            )
            s.add(child)
            s.flush()
            created_nodes.append(child)
            chunk_kinds.append(ckind)

        if not created_nodes:
            raise HTTPException(400, "no non-empty chunks produced")

        for i, child in enumerate(created_nodes):
            s.add(add_edge(thread_id, parent.id, child.id, "HAS_PART", {"index": i, "kind": chunk_kinds[i]}))
            s.add(add_edge(thread_id, child.id, parent.id, "SPLIT_FROM", {"index": i}))
            if i > 0:
                s.add(add_edge(thread_id, created_nodes[i - 1].id, child.id, "NEXT_PART"))

        if body.inherit_reply_to:
            reply_edges = s.exec(
                select(Edge)
                .where(Edge.thread_id == thread_id, Edge.from_id == parent.id, Edge.type == "REPLY_TO")
                .order_by(Edge.created_at.asc(), Edge.id.asc())
            ).all()
            to_ids: List[str] = []
            seen_to = set()
            for edge in reply_edges:
                if edge.to_id in seen_to:
                    continue
                to_ids.append(edge.to_id)
                seen_to.add(edge.to_id)

            for child in created_nodes:
                for to_id in to_ids:
                    s.add(add_edge(thread_id, child.id, to_id, "REPLY_TO"))

        if body.context_set_id:
            cs = s.get(ContextSet, body.context_set_id)
            if not cs or cs.thread_id != thread_id:
                raise HTTPException(404, "context set not found in thread")

            active = jload(cs.active_node_ids_json, [])
            if body.replace_in_active:
                active = [nid for nid in active if nid != parent.id]
            seen_active = set(active)
            for child in created_nodes:
                if child.id in seen_active:
                    continue
                active.append(child.id)
                seen_active.add(child.id)
            cs.active_node_ids_json = jdump(active)
            s.add(cs)

        s.commit()

        for child in created_nodes:
            ensure_node_embedding(s, child)

        return SplitNodeResponse(
            ok=True,
            parent_id=parent.id,
            created_ids=[n.id for n in created_nodes],
            strategy_used=strategy_used,
        ).model_dump()
