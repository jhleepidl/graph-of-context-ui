from __future__ import annotations

from typing import Any


def list_visibility_edges(runtime_snapshot: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    snapshot = runtime_snapshot or {}
    return [
        dict(item)
        for item in list(snapshot.get('visibility_graph') or snapshot.get('visibilityGraph') or [])
        if isinstance(item, dict)
    ]


def edges_for_scope(runtime_snapshot: dict[str, Any] | None, scope_id: str) -> list[dict[str, Any]]:
    clean_scope_id = str(scope_id or '').strip()
    if not clean_scope_id:
        return []
    return [
        edge
        for edge in list_visibility_edges(runtime_snapshot)
        if str(edge.get('from_scope_id') or edge.get('fromScopeId') or '').strip() == clean_scope_id
        or str(edge.get('to_scope_id') or edge.get('toScopeId') or '').strip() == clean_scope_id
    ]
