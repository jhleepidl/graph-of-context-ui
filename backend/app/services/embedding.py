from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
from sqlmodel import Session, select

from app.config import get_env
from app.models import Node, NodeEmbedding
from app.llm import embed_text
from app.services.vector_index import EMBED_DIM, get_index

SEARCH_EMBED_CAP = max(1, int(get_env("GOC_SEARCH_EMBED_CAP", "100") or "100"))

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


def _validate_dim(vec: List[float], source: str) -> List[float]:
    if not vec:
        return []
    if len(vec) != EMBED_DIM:
        raise ValueError(
            f"{source}: embedding dim mismatch (expected {EMBED_DIM}, got {len(vec)}). "
            "Check GOC_EMBED_DIM and embedding source consistency."
        )
    return vec


def _has_text(node: Node) -> bool:
    return bool((node.text or "").strip())


def _extract_valid_vec(embedding: Optional[NodeEmbedding], node_id: str) -> Optional[List[float]]:
    if not embedding:
        return None
    if not embedding.embedding_json or embedding.embedding_json == "[]":
        return None
    vec = jload(embedding.embedding_json, [])
    if not vec:
        return None
    _validate_dim(vec, source=f"node embedding {node_id}")
    return vec


def _build_embedding_row(node: Node, vec: List[float]) -> NodeEmbedding:
    return NodeEmbedding(
        node_id=node.id,
        thread_id=node.thread_id,
        dim=len(vec),
        embedding_json=jdump(vec),
        updated_at=utcnow(),
    )


def ensure_node_embedding(
    session: Session,
    node: Node,
    *,
    commit: bool = True,
    upsert_index: bool = True,
) -> Optional[NodeEmbedding]:
    text = (node.text or "").strip()
    if not text:
        return None

    existing = session.get(NodeEmbedding, node.id)
    try:
        existing_vec = _extract_valid_vec(existing, node.id)
    except ValueError:
        existing_vec = None
    if existing_vec:
        if upsert_index:
            _index.upsert(node.thread_id, node.id, existing_vec)
        return existing

    vec = embed_text(text)
    if not vec:
        return None
    vec = _validate_dim(vec, source=f"embed_text({node.id})")
    vec = _norm(vec)

    ne = _build_embedding_row(node, vec)
    session.merge(ne)
    if commit:
        session.commit()
    if upsert_index:
        _index.upsert(node.thread_id, node.id, vec)
    return ne


def ensure_nodes_embeddings(
    session: Session,
    nodes: List[Node],
    *,
    commit: bool = True,
) -> Dict[str, int]:
    pending: List[Tuple[Node, List[float]]] = []
    reused = 0
    skipped = 0

    for node in nodes:
        if not _has_text(node):
            skipped += 1
            continue

        existing = session.get(NodeEmbedding, node.id)
        try:
            existing_vec = _extract_valid_vec(existing, node.id)
        except ValueError:
            existing_vec = None
        if existing_vec:
            _index.upsert(node.thread_id, node.id, existing_vec)
            reused += 1
            continue

        vec = embed_text((node.text or "").strip())
        if not vec:
            skipped += 1
            continue
        vec = _validate_dim(vec, source=f"embed_text({node.id})")
        vec = _norm(vec)
        session.merge(_build_embedding_row(node, vec))
        pending.append((node, vec))

    if commit and pending:
        session.commit()

    for node, vec in pending:
        _index.upsert(node.thread_id, node.id, vec)

    return {
        "embedded": len(pending),
        "reused": reused,
        "skipped": skipped,
    }


def ensure_thread_embeddings(
    session: Session,
    thread_id: str,
    *,
    limit: Optional[int] = None,
    commit: bool = True,
) -> Dict[str, int | bool]:
    nodes = session.exec(
        select(Node)
        .where(Node.thread_id == thread_id)
        .order_by(Node.created_at.asc(), Node.id.asc())
    ).all()
    text_nodes = [n for n in nodes if _has_text(n)]
    total_text_nodes = len(text_nodes)
    if total_text_nodes == 0:
        return {
            "total_text_nodes": 0,
            "embedded_nodes": 0,
            "coverage_percent": 100.0,
            "indexing_incomplete": False,
            "embedded_this_call": 0,
            "remaining_missing": 0,
            "embed_cap": limit if limit is not None else -1,
        }

    embeddings = session.exec(
        select(NodeEmbedding).where(NodeEmbedding.thread_id == thread_id)
    ).all()
    by_node_id = {e.node_id: e for e in embeddings}

    valid_existing = 0
    missing_nodes: List[Node] = []
    for node in text_nodes:
        existing = by_node_id.get(node.id)
        try:
            vec = _extract_valid_vec(existing, node.id)
        except ValueError:
            vec = None
        if vec:
            valid_existing += 1
            continue
        missing_nodes.append(node)

    if limit is not None:
        to_embed = missing_nodes[: max(0, limit)]
    else:
        to_embed = missing_nodes

    embed_result = ensure_nodes_embeddings(session, to_embed, commit=commit)
    embedded_this_call = int(embed_result["embedded"])
    embedded_nodes = valid_existing + embedded_this_call
    remaining_missing = max(0, total_text_nodes - embedded_nodes)
    coverage_percent = (embedded_nodes / total_text_nodes) * 100.0 if total_text_nodes else 100.0

    return {
        "total_text_nodes": total_text_nodes,
        "embedded_nodes": embedded_nodes,
        "coverage_percent": round(coverage_percent, 2),
        # Keep lazy indexing, but cap write-on-read to avoid heavy GET-time churn.
        "indexing_incomplete": remaining_missing > 0,
        "embedded_this_call": embedded_this_call,
        "remaining_missing": remaining_missing,
        "embed_cap": limit if limit is not None else -1,
    }


def ensure_thread_index(session: Session, thread_id: str) -> Dict[str, int | bool]:
    return ensure_thread_embeddings(session, thread_id, limit=None, commit=True)


def rebuild_thread_index(session: Session, thread_id: str) -> Dict[str, int]:
    nodes = session.exec(select(Node).where(Node.thread_id == thread_id)).all()
    node_ids = {n.id for n in nodes}
    embeddings = session.exec(
        select(NodeEmbedding).where(NodeEmbedding.thread_id == thread_id)
    ).all()

    vectors: List[Tuple[str, List[float]]] = []
    skipped_missing_node = 0
    skipped_invalid = 0
    for row in embeddings:
        if row.node_id not in node_ids:
            skipped_missing_node += 1
            continue
        vec = jload(row.embedding_json, [])
        if not vec or len(vec) != EMBED_DIM:
            skipped_invalid += 1
            continue
        vectors.append((row.node_id, vec))

    rebuilt = _index.rebuild_thread(thread_id, vectors)
    return {
        "thread_id": thread_id,
        "db_embeddings": len(embeddings),
        "indexed": int(rebuilt.get("indexed", 0)),
        "skipped_missing_node": skipped_missing_node,
        "skipped_invalid_embedding": skipped_invalid + int(rebuilt.get("skipped", 0)),
    }


def remove_thread_index(thread_id: str) -> None:
    _index.remove_thread(thread_id)


def search_nodes(
    session: Session,
    thread_id: str,
    query: str,
    k: int = 10,
) -> Tuple[List[Tuple[Node, float]], Dict[str, int | float | bool]]:
    qvec = embed_text(query)
    if not qvec:
        return [], {
            "total_text_nodes": 0,
            "embedded_nodes": 0,
            "coverage_percent": 0.0,
            "indexing_incomplete": False,
            "embedded_this_call": 0,
            "remaining_missing": 0,
            "embed_cap": SEARCH_EMBED_CAP,
        }

    qvec = _validate_dim(qvec, source="search query embedding")

    coverage = ensure_thread_embeddings(
        session,
        thread_id,
        limit=SEARCH_EMBED_CAP,
        commit=True,
    )

    qvec = _norm(qvec)
    hits = _index.search(thread_id, qvec, k=k)

    out: List[Tuple[Node, float]] = []
    for node_id, score in hits:
        n = session.get(Node, node_id)
        if n and n.thread_id == thread_id:
            out.append((n, float(score)))
    return out, coverage
