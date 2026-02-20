from __future__ import annotations
import json
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import numpy as np
from sqlmodel import Session, select

from app.models import Node, NodeEmbedding
from app.llm import embed_text
from app.services.vector_index import get_index

_index = get_index()

def utcnow():
    return datetime.now(timezone.utc)

def jdump(x) -> str:
    return json.dumps(x, ensure_ascii=False)

def jload(s: str, default):
    try:
        return json.loads(s)
    except Exception:
        return default

def _norm(vec: List[float]) -> List[float]:
    if not vec:
        return []
    v = np.asarray(vec, dtype=np.float32)
    n = np.linalg.norm(v) + 1e-9
    return (v / n).astype(np.float32).tolist()

def ensure_node_embedding(session: Session, node: Node) -> Optional[NodeEmbedding]:
    text = (node.text or "").strip()
    if not text:
        return None

    existing = session.get(NodeEmbedding, node.id)
    if existing and existing.embedding_json and existing.embedding_json != "[]":
        vec = jload(existing.embedding_json, [])
        if vec:
            _index.upsert(node.thread_id, node.id, vec)
        return existing

    vec = embed_text(text)
    if not vec:
        return None
    vec = _norm(vec)

    ne = NodeEmbedding(
        node_id=node.id,
        thread_id=node.thread_id,
        dim=len(vec),
        embedding_json=jdump(vec),
        updated_at=utcnow(),
    )
    session.merge(ne)
    session.commit()

    _index.upsert(node.thread_id, node.id, vec)
    return ne

def ensure_thread_index(session: Session, thread_id: str) -> None:
    nodes = session.exec(select(Node).where(Node.thread_id == thread_id)).all()
    for n in nodes:
        if (n.text or "").strip():
            ensure_node_embedding(session, n)

def search_nodes(session: Session, thread_id: str, query: str, k: int = 10) -> List[Tuple[Node, float]]:
    qvec = embed_text(query)
    if not qvec:
        return []

    ensure_thread_index(session, thread_id)

    qvec = _norm(qvec)
    hits = _index.search(thread_id, qvec, k=k)

    out: List[Tuple[Node, float]] = []
    for node_id, score in hits:
        n = session.get(Node, node_id)
        if n and n.thread_id == thread_id:
            out.append((n, float(score)))
    return out
