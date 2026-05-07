from __future__ import annotations
import math
import re
from typing import Any
from sqlmodel import Session, select

from app.models import RuntimeProposal, Thread

DIM = 256


def _clean(value: Any = "", max_len: int = 12000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:max_len]


def _tokens(text: str) -> list[str]:
    src = _clean(text, 12000).lower()
    rows = re.findall(r"[a-z0-9_]{2,}|[가-힣]{2,}", src)
    out: list[str] = []
    seen: set[str] = set()
    for token in rows:
        candidates = [token]
        if re.fullmatch(r"[가-힣]{3,}", token):
            candidates += [token[i:i+2] for i in range(0, len(token) - 1)]
        for cand in candidates:
            if cand and cand not in seen:
                seen.add(cand)
                out.append(cand)
    return out[:512]


def _hash(value: str) -> int:
    h = 2166136261
    for ch in value:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def embed_local_hash(text: str, dim: int = DIM) -> list[float]:
    vector = [0.0] * dim
    for token in _tokens(text):
        h = _hash(token)
        vector[h % dim] += -1.0 if (h & 0x10000) else 1.0
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [round(x / norm, 6) for x in vector]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    an = math.sqrt(sum(a[i] * a[i] for i in range(n))) or 1.0
    bn = math.sqrt(sum(b[i] * b[i] for i in range(n))) or 1.0
    return dot / (an * bn)


def _proposal_text(row: RuntimeProposal) -> str:
    return "\n".join(filter(None, [row.title, row.summary, row.source_original_text, row.canonical_text_en]))


def search_thread_semantic_items(session: Session, thread: Thread, *, query: str = "", item_types: list[str] | None = None, limit: int = 10, include_inactive: bool = False) -> dict[str, Any]:
    qvec = embed_local_hash(query)
    stmt = select(RuntimeProposal).where(RuntimeProposal.thread_id == thread.id)
    rows = list(session.exec(stmt).all())
    type_set = {str(x).lower() for x in (item_types or []) if str(x or '').strip()}
    out: list[dict[str, Any]] = []
    for row in rows:
        if not include_inactive and row.status not in {"active", "pending_review", "review_required", "needs_evidence", "candidate", "approved"}:
            continue
        if type_set and row.proposal_kind not in type_set:
            continue
        score = cosine(qvec, embed_local_hash(_proposal_text(row)))
        if score <= 0:
            continue
        out.append({
            "item_id": row.proposal_id,
            "item_type": row.proposal_kind,
            "title": row.title,
            "summary": row.summary,
            "source_original_text": row.source_original_text,
            "canonical_text_en": row.canonical_text_en,
            "canonical_projection_status": row.canonical_projection_status,
            "status": row.status,
            "risk": row.risk,
            "evidence_status": row.evidence_status,
            "vector_score": round(score, 4),
        })
    out.sort(key=lambda x: x["vector_score"], reverse=True)
    return {"ok": True, "kind": "thread_semantic_index_search_v1", "query": _clean(query, 1000), "vector_backend": "local_hash_embedding", "item_count": len(out[:limit]), "items": out[:max(1, min(limit, 50))]}
