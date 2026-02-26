from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


def ordered_unique(ids: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for nid in ids:
        if not isinstance(nid, str) or not nid or nid in seen:
            continue
        seen.add(nid)
        out.append(nid)
    return out


def _jload(payload: Any, default: Any) -> Any:
    if isinstance(payload, dict):
        return payload
    try:
        import json
        return json.loads(payload)
    except Exception:
        return default


def compile_active_context_records(
    *,
    records: Sequence[Dict[str, Any]],
    active_ids: Sequence[str],
    edges: Sequence[Dict[str, Any]] = (),
) -> Tuple[str, Dict[str, Any]]:
    """Compile ordered active context while suppressing parent placeholders.

    `records` items should contain: id, type, text, created_at, payload_json/payload.
    `edges` items should contain: from_id, to_id, type.
    Returns (compiled_text, explain_dict).
    """
    by_id = {str(r.get("id")): r for r in records if r.get("id")}
    ordered_ids = [nid for nid in ordered_unique(active_ids) if nid in by_id]
    active_records = [by_id[nid] for nid in ordered_ids]
    active_set = set(ordered_ids)

    parent_to_children: Dict[str, set] = defaultdict(set)
    parent_sources: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for r in active_records:
        meta = _jload(r.get("payload_json", r.get("payload", {})), {})
        parent_id = meta.get("parent_id") if isinstance(meta, dict) else None
        if isinstance(parent_id, str) and parent_id and parent_id in active_set:
            parent_to_children[parent_id].add(str(r.get("id")))
            parent_sources[parent_id].append({"child_id": str(r.get("id")), "source": "payload.parent_id"})

    for e in edges:
        if (e.get("type") or "") != "HAS_PART":
            continue
        u = str(e.get("from_id") or "")
        v = str(e.get("to_id") or "")
        if u in active_set and v in active_set and u and v:
            parent_to_children[u].add(v)
            parent_sources[u].append({"child_id": v, "source": "edge.HAS_PART"})

    excluded_parent_ids = [nid for nid in ordered_ids if parent_to_children.get(nid)]
    kept_records = [r for r in active_records if str(r.get("id")) not in set(excluded_parent_ids)]

    parts: List[str] = []
    for r in kept_records:
        nid = str(r.get("id"))
        rtype = str(r.get("type") or "Node")
        text = (r.get("text") or "")
        created_at = r.get("created_at")
        created_str = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at or "")
        meta = _jload(r.get("payload_json", r.get("payload", {})), {})
        head = f"[{rtype} {nid[:6]} @ {created_str}]"
        if rtype == "Message":
            role = meta.get("role", "?") if isinstance(meta, dict) else "?"
            parts.append(f"{head} role={role}\n{text}")
        elif rtype == "Fold":
            title = meta.get("title", "Fold") if isinstance(meta, dict) else "Fold"
            parts.append(f"{head} title={title}\n{text}")
        else:
            parts.append(f"{head}\n{text}")

    explain = {
        "active_input_ids": ordered_ids,
        "active_input_count": len(ordered_ids),
        "excluded_parent_ids": excluded_parent_ids,
        "kept_node_ids": [str(r.get("id")) for r in kept_records],
        "kept_node_count": len(kept_records),
        "parent_to_children": {k: sorted(v) for k, v in parent_to_children.items()},
        "parent_sources": dict(parent_sources),
    }
    return "\n\n".join(parts).strip(), explain


def expand_closure_from_edges(
    *,
    seed_ids: Sequence[str],
    edges: Sequence[Dict[str, Any]],
    allowed_types: Sequence[str],
    max_nodes: Optional[int] = None,
    direction: str = "out",
) -> Dict[str, Any]:
    """Deterministic BFS closure over selected edge types.

    This is adapted for the UI backend from the research code's dependency-closure
    semantics. It keeps traversal deterministic, bounded, and explainable.
    """
    allowed = {str(t) for t in (allowed_types or []) if str(t)}
    seed_order = ordered_unique(seed_ids)
    if not seed_order or not allowed:
        return {
            "ordered_ids": seed_order,
            "seed_ids": seed_order,
            "closure_added_ids": [],
            "visited_edge_count": 0,
            "truncated": False,
            "max_nodes": max_nodes,
            "allowed_types": sorted(allowed),
            "direction": direction,
            "edge_trace": [],
        }

    if direction not in {"out", "in", "both"}:
        direction = "out"

    out_adj: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    in_adj: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    for e in edges:
        et = str(e.get("type") or "")
        if et not in allowed:
            continue
        u = str(e.get("from_id") or "")
        v = str(e.get("to_id") or "")
        if not u or not v:
            continue
        out_adj[u].append((v, et))
        in_adj[v].append((u, et))

    for adj in (out_adj, in_adj):
        for k in list(adj.keys()):
            adj[k] = sorted(adj[k], key=lambda x: (x[0], x[1]))

    visited = set(seed_order)
    q = deque(seed_order)
    edge_trace: List[Dict[str, str]] = []
    truncated = False

    def _offer(src: str, dst: str, etype: str, rel: str) -> None:
        nonlocal truncated
        if max_nodes is not None and len(visited) >= int(max_nodes) and dst not in visited:
            truncated = True
            return
        edge_trace.append({"from": src, "to": dst, "type": etype, "dir": rel})
        if dst not in visited:
            visited.add(dst)
            q.append(dst)

    while q:
        cur = q.popleft()
        if direction in {"out", "both"}:
            for nxt, et in out_adj.get(cur, []):
                _offer(cur, nxt, et, "out")
                if truncated:
                    break
        if truncated:
            break
        if direction in {"in", "both"}:
            for prv, et in in_adj.get(cur, []):
                _offer(prv, cur, et, "in")
                if truncated:
                    break
        if truncated:
            break

    ordered = seed_order + [nid for nid in sorted(visited) if nid not in set(seed_order)]
    return {
        "ordered_ids": ordered,
        "seed_ids": seed_order,
        "closure_added_ids": [nid for nid in ordered if nid not in set(seed_order)],
        "visited_edge_count": len(edge_trace),
        "truncated": truncated,
        "max_nodes": max_nodes,
        "allowed_types": sorted(allowed),
        "direction": direction,
        "edge_trace": edge_trace[:200],
    }
