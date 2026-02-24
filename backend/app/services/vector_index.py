from __future__ import annotations
import os
import json
from typing import Dict, List, Tuple

import numpy as np

from app.config import get_env

VECTOR_BACKEND = (get_env("GOC_VECTOR_BACKEND", "faiss") or "faiss").lower()
FAISS_DIR = get_env("GOC_FAISS_DIR", "./data/faiss") or "./data/faiss"
EMBED_DIM = int(get_env("GOC_EMBED_DIM", "1536") or "1536")

def _ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)

def _norm(vec: List[float]) -> List[float]:
    if not vec:
        return []
    v = np.asarray(vec, dtype=np.float32)
    n = np.linalg.norm(v) + 1e-9
    return (v / n).astype(np.float32).tolist()


def _validate_dim(vec: List[float], *, where: str) -> List[float]:
    if not vec:
        return []
    if len(vec) != EMBED_DIM:
        raise ValueError(
            f"{where}: embedding dim mismatch (expected {EMBED_DIM}, got {len(vec)}). "
            "Check GOC_EMBED_DIM and embedding source consistency."
        )
    return vec


class VectorIndex:
    def upsert(self, thread_id: str, node_id: str, vec: List[float]) -> None:
        raise NotImplementedError

    def search(self, thread_id: str, qvec: List[float], k: int) -> List[Tuple[str, float]]:
        raise NotImplementedError

    def rebuild_thread(self, thread_id: str, vectors: List[Tuple[str, List[float]]]) -> Dict[str, int]:
        raise NotImplementedError

    def remove_thread(self, thread_id: str) -> None:
        raise NotImplementedError

class BruteForceIndex(VectorIndex):
    def __init__(self):
        self.store: Dict[str, Dict[str, np.ndarray]] = {}

    def upsert(self, thread_id: str, node_id: str, vec: List[float]) -> None:
        vec = _validate_dim(vec, where="vector upsert")
        vec = _norm(vec)
        if not vec:
            return
        self.store.setdefault(thread_id, {})[node_id] = np.asarray(vec, dtype=np.float32)

    def search(self, thread_id: str, qvec: List[float], k: int) -> List[Tuple[str, float]]:
        qvec = _validate_dim(qvec, where="vector search query")
        qvec = _norm(qvec)
        if not qvec:
            return []
        q = np.asarray(qvec, dtype=np.float32)
        items = self.store.get(thread_id, {})
        scored = [(nid, float(np.dot(q, v))) for nid, v in items.items()]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:max(1, min(k, 50))]

    def rebuild_thread(self, thread_id: str, vectors: List[Tuple[str, List[float]]]) -> Dict[str, int]:
        next_store: Dict[str, np.ndarray] = {}
        seen = set()
        skipped = 0
        for node_id, vec in vectors:
            if node_id in seen:
                skipped += 1
                continue
            seen.add(node_id)
            if len(vec) != EMBED_DIM:
                skipped += 1
                continue
            normed = _norm(vec)
            if not normed:
                skipped += 1
                continue
            next_store[node_id] = np.asarray(normed, dtype=np.float32)
        self.store[thread_id] = next_store
        return {"indexed": len(next_store), "skipped": skipped}

    def remove_thread(self, thread_id: str) -> None:
        self.store.pop(thread_id, None)

class FaissIndex(VectorIndex):
    def __init__(self):
        _ensure_dir(FAISS_DIR)
        import faiss
        self.faiss = faiss
        self.indices: Dict[str, "faiss.Index"] = {}
        self.idmaps: Dict[str, List[str]] = {}

    def _paths(self, thread_id: str) -> Tuple[str, str]:
        idx = os.path.join(FAISS_DIR, f"{thread_id}.index")
        mp = os.path.join(FAISS_DIR, f"{thread_id}.map.json")
        return idx, mp

    def _load_or_create(self, thread_id: str):
        if thread_id in self.indices:
            return
        idx_path, map_path = self._paths(thread_id)
        if os.path.exists(idx_path) and os.path.exists(map_path):
            idx = self.faiss.read_index(idx_path)
            if getattr(idx, "d", EMBED_DIM) != EMBED_DIM:
                raise ValueError(
                    f"faiss index dim mismatch for thread {thread_id}: "
                    f"expected {EMBED_DIM}, got {getattr(idx, 'd', 'unknown')}."
                )
            self.indices[thread_id] = idx
            with open(map_path, "r", encoding="utf-8") as f:
                self.idmaps[thread_id] = json.load(f)
        else:
            self.indices[thread_id] = self.faiss.IndexFlatIP(EMBED_DIM)  # cosine via normalized vectors
            self.idmaps[thread_id] = []

    def _persist(self, thread_id: str) -> None:
        idx_path, map_path = self._paths(thread_id)
        self.faiss.write_index(self.indices[thread_id], idx_path)
        with open(map_path, "w", encoding="utf-8") as f:
            json.dump(self.idmaps[thread_id], f, ensure_ascii=False)

    def upsert(self, thread_id: str, node_id: str, vec: List[float]) -> None:
        vec = _validate_dim(vec, where="vector upsert")
        vec = _norm(vec)
        if not vec:
            return
        self._load_or_create(thread_id)
        # MVP: append-only (no updates/deletes). Use a set check to avoid duplicates.
        if node_id in set(self.idmaps[thread_id]):
            return
        v = np.asarray([vec], dtype=np.float32)
        self.indices[thread_id].add(v)
        self.idmaps[thread_id].append(node_id)
        self._persist(thread_id)

    def search(self, thread_id: str, qvec: List[float], k: int) -> List[Tuple[str, float]]:
        qvec = _validate_dim(qvec, where="vector search query")
        qvec = _norm(qvec)
        if not qvec:
            return []
        self._load_or_create(thread_id)
        if self.indices[thread_id].ntotal == 0:
            return []
        q = np.asarray([qvec], dtype=np.float32)
        k = max(1, min(k, 50))
        scores, ids = self.indices[thread_id].search(q, k)
        out: List[Tuple[str, float]] = []
        for score, idx in zip(scores[0].tolist(), ids[0].tolist()):
            if idx == -1:
                continue
            if 0 <= idx < len(self.idmaps[thread_id]):
                out.append((self.idmaps[thread_id][idx], float(score)))
        return out

    def rebuild_thread(self, thread_id: str, vectors: List[Tuple[str, List[float]]]) -> Dict[str, int]:
        seen = set()
        idmap: List[str] = []
        rows: List[List[float]] = []
        skipped = 0

        for node_id, vec in vectors:
            if node_id in seen:
                skipped += 1
                continue
            seen.add(node_id)
            if len(vec) != EMBED_DIM:
                skipped += 1
                continue
            normed = _norm(vec)
            if not normed:
                skipped += 1
                continue
            idmap.append(node_id)
            rows.append(normed)

        index = self.faiss.IndexFlatIP(EMBED_DIM)
        if rows:
            index.add(np.asarray(rows, dtype=np.float32))

        self.indices[thread_id] = index
        self.idmaps[thread_id] = idmap
        self._persist(thread_id)
        return {"indexed": len(idmap), "skipped": skipped}

    def remove_thread(self, thread_id: str) -> None:
        self.indices.pop(thread_id, None)
        self.idmaps.pop(thread_id, None)
        idx_path, map_path = self._paths(thread_id)
        if os.path.exists(idx_path):
            os.remove(idx_path)
        if os.path.exists(map_path):
            os.remove(map_path)

def get_index() -> VectorIndex:
    if VECTOR_BACKEND == "bruteforce":
        return BruteForceIndex()
    return FaissIndex()
