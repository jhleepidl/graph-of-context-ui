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

class VectorIndex:
    def upsert(self, thread_id: str, node_id: str, vec: List[float]) -> None:
        raise NotImplementedError

    def search(self, thread_id: str, qvec: List[float], k: int) -> List[Tuple[str, float]]:
        raise NotImplementedError

class BruteForceIndex(VectorIndex):
    def __init__(self):
        self.store: Dict[str, Dict[str, np.ndarray]] = {}

    def upsert(self, thread_id: str, node_id: str, vec: List[float]) -> None:
        vec = _norm(vec)
        if not vec:
            return
        self.store.setdefault(thread_id, {})[node_id] = np.asarray(vec, dtype=np.float32)

    def search(self, thread_id: str, qvec: List[float], k: int) -> List[Tuple[str, float]]:
        qvec = _norm(qvec)
        if not qvec:
            return []
        q = np.asarray(qvec, dtype=np.float32)
        items = self.store.get(thread_id, {})
        scored = [(nid, float(np.dot(q, v))) for nid, v in items.items()]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:max(1, min(k, 50))]

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
            self.indices[thread_id] = self.faiss.read_index(idx_path)
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

def get_index() -> VectorIndex:
    if VECTOR_BACKEND == "bruteforce":
        return BruteForceIndex()
    return FaissIndex()
