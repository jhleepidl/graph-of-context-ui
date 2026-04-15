from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from typing import Any


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def build_cache_key(namespace: str, payload: dict[str, Any]) -> str:
    encoded = _stable_json(payload)
    digest = hashlib.sha1(encoded.encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"


class ContextArtifactCache:
    def __init__(self, *, ttl_sec: int = 1800, max_entries: int = 512) -> None:
        self.ttl_sec = max(1, int(ttl_sec))
        self.max_entries = max(16, int(max_entries))
        self._store: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        self._lock = threading.RLock()

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def _prune_locked(self) -> None:
        now = time.time()
        stale = [key for key, entry in self._store.items() if float(entry.get("expires_at") or 0.0) <= now]
        for key in stale:
            self._store.pop(key, None)
        while len(self._store) > self.max_entries:
            self._store.popitem(last=False)

    def get(self, key: str) -> Any | None:
        with self._lock:
            self._prune_locked()
            entry = self._store.get(key)
            if not entry:
                return None
            self._store.move_to_end(key)
            return copy.deepcopy(entry.get("value"))

    def set(self, key: str, value: Any) -> Any:
        with self._lock:
            self._store[key] = {
                "value": copy.deepcopy(value),
                "expires_at": time.time() + self.ttl_sec,
            }
            self._store.move_to_end(key)
            self._prune_locked()
        return value


_GLOBAL_CACHE: ContextArtifactCache | None = None


def get_global_context_cache() -> ContextArtifactCache:
    global _GLOBAL_CACHE
    if _GLOBAL_CACHE is None:
        ttl_sec = int(os.environ.get("OPENHARNESS_CONTEXT_CACHE_TTL_SEC", "1800") or "1800")
        max_entries = int(os.environ.get("OPENHARNESS_CONTEXT_CACHE_MAX_ENTRIES", "512") or "512")
        _GLOBAL_CACHE = ContextArtifactCache(ttl_sec=ttl_sec, max_entries=max_entries)
    return _GLOBAL_CACHE


def clear_global_context_cache() -> None:
    get_global_context_cache().clear()
