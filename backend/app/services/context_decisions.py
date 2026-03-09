from __future__ import annotations

import json
from typing import Any, Iterable

from app.models import ContextSet, Edge, Node


CONTEXT_GAP_KEYS = (
    "missing_context",
    "needs_context",
    "context_gaps",
    "missing_node_ids",
    "needs_node_ids",
)


def _jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def _node_payload(node: Node | None) -> dict[str, Any]:
    if not node:
        return {}
    payload = _jload(node.payload_json, {})
    if isinstance(payload, dict):
        return payload
    return {}


def _short_text(value: str, max_len: int = 180) -> str:
    compact = " ".join(str(value or "").split())
    if len(compact) <= max_len:
        return compact
    return f"{compact[:max_len]}..."


def _collect_gap_refs(value: Any) -> list[str]:
    out: list[str] = []

    def _append_one(item: Any) -> None:
        if isinstance(item, str):
            clean = item.strip()
            if clean:
                out.append(clean)
            return
        if isinstance(item, dict):
            node_id = item.get("id")
            if isinstance(node_id, str) and node_id.strip():
                out.append(node_id.strip())
                return
            label = item.get("label")
            if isinstance(label, str) and label.strip():
                out.append(label.strip())

    if isinstance(value, (list, tuple, set)):
        for item in value:
            _append_one(item)
    else:
        _append_one(value)
    return out


def _node_summary(node: Node) -> dict[str, Any]:
    payload = _node_payload(node)
    pin_level = str(payload.get("pin_level") or "").strip().lower() or None
    is_pinned = bool(payload.get("pinned") or payload.get("is_pinned")) or pin_level in {"required", "preferred"}
    return {
        "id": node.id,
        "target_node_id": node.id,
        "type": node.type,
        "text": _short_text(node.text or ""),
        "created_at": node.created_at,
        "pin_level": pin_level,
        "pinned": is_pinned,
    }


def _unique_items(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        item_id = str(
            item.get("id")
            or item.get("node_id")
            or item.get("edge_id")
            or f"{item.get('from_id') or ''}->{item.get('to_id') or ''}"
            or ""
        )
        reason = str(item.get("reason") or "")
        key = (item_id, reason)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def build_context_decisions(
    *,
    context_set: ContextSet,
    nodes: list[Node],
    edges: list[Edge],
    compiled_explain: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_ids = _jload(context_set.active_node_ids_json, [])
    if not isinstance(active_ids, list):
        active_ids = []
    active_ids = [str(nid).strip() for nid in active_ids if isinstance(nid, str) and str(nid).strip()]

    nodes_by_id = {node.id: node for node in nodes}
    payload_by_id = {node.id: _node_payload(node) for node in nodes}

    selected_items = [_node_summary(nodes_by_id[nid]) for nid in active_ids if nid in nodes_by_id]
    pinned_items = [item for item in selected_items if item.get("pinned")]

    explain = compiled_explain if isinstance(compiled_explain, dict) else {}
    excluded_parent_ids = [
        str(nid).strip()
        for nid in explain.get("excluded_parent_ids", [])
        if isinstance(nid, str) and str(nid).strip()
    ]
    kept_node_ids = [
        str(nid).strip()
        for nid in explain.get("kept_node_ids", [])
        if isinstance(nid, str) and str(nid).strip()
    ]

    # Rebuild exclusion diagnostics from active set + HAS_PART + payload.parent_id.
    active_set = set(active_ids)
    parent_to_children: dict[str, set[str]] = {}
    for node_id in active_ids:
        payload = payload_by_id.get(node_id, {})
        parent_id = payload.get("parent_id")
        if isinstance(parent_id, str) and parent_id in active_set:
            parent_to_children.setdefault(parent_id, set()).add(node_id)
    for edge in edges:
        if edge.type != "HAS_PART":
            continue
        if edge.from_id in active_set and edge.to_id in active_set:
            parent_to_children.setdefault(edge.from_id, set()).add(edge.to_id)

    if not excluded_parent_ids:
        excluded_parent_ids = [nid for nid in active_ids if parent_to_children.get(nid)]
    if not kept_node_ids:
        kept_node_ids = [nid for nid in active_ids if nid not in set(excluded_parent_ids)]

    excluded_items: list[dict[str, Any]] = []
    for parent_id in excluded_parent_ids:
        node = nodes_by_id.get(parent_id)
        if not node:
            continue
        excluded_items.append(
            {
                "id": parent_id,
                "target_node_id": parent_id,
                "type": node.type,
                "text": _short_text(node.text or ""),
                "reason": "Excluded from compiled context because child parts are active",
                "child_ids": sorted(parent_to_children.get(parent_id, set())),
            }
        )

    missing_items: list[dict[str, Any]] = []
    for node in nodes:
        payload = payload_by_id.get(node.id, {})
        node_type = str(node.type or "")
        if node.id in active_set:
            continue
        if node_type == "ContextCandidate":
            status = str(payload.get("status") or "").strip().lower()
            explicit_missing = payload.get("missing") is True or status in {"missing", "todo", "needed", "required"}
            text_like_gap = "?" in str(node.text or "") or "missing" in str(node.text or "").lower()
            if explicit_missing or text_like_gap:
                missing_items.append(
                    {
                        "id": node.id,
                        "target_node_id": node.id,
                        "type": node_type,
                        "text": _short_text(node.text or ""),
                        "reason": str(payload.get("why") or payload.get("reason") or "Context candidate is not selected"),
                    }
                )

    recent_steps = [node for node in nodes if node.type == "Step"]
    recent_steps.sort(key=lambda row: (str(row.created_at or ""), row.id))
    for step in recent_steps[-18:]:
        payload = payload_by_id.get(step.id, {})
        for key in CONTEXT_GAP_KEYS:
            raw = payload.get(key)
            refs = _collect_gap_refs(raw)
            for ref in refs:
                linked = nodes_by_id.get(ref)
                if linked:
                    missing_items.append(
                        {
                            "id": linked.id,
                            "target_node_id": linked.id,
                            "type": linked.type,
                            "text": _short_text(linked.text or ""),
                            "reason": f"Mentioned as missing by step {step.id[:8]}",
                        }
                    )
                else:
                    missing_items.append(
                        {
                            "id": "",
                            "target_node_id": "",
                            "type": "MissingReference",
                            "text": _short_text(ref),
                            "reason": f"Unresolved missing context reference in step {step.id[:8]}",
                        }
                    )

    conflict_items: list[dict[str, Any]] = []
    for edge in edges:
        if edge.type not in {"CONFLICTS", "CONTRADICTS"}:
            continue
        src = nodes_by_id.get(edge.from_id)
        dst = nodes_by_id.get(edge.to_id)
        conflict_items.append(
            {
                "edge_id": edge.id,
                "type": edge.type,
                "from_id": edge.from_id,
                "to_id": edge.to_id,
                "related_node_ids": [edge.from_id, edge.to_id],
                "from_text": _short_text(src.text or "") if src else "",
                "to_text": _short_text(dst.text or "") if dst else "",
                "reason": "Explicit conflict edge in graph",
            }
        )

    for node in nodes:
        payload = payload_by_id.get(node.id, {})
        conflict_ref = payload.get("conflicts_with") or payload.get("contradicts")
        refs = _collect_gap_refs(conflict_ref)
        for ref in refs:
            other = nodes_by_id.get(ref)
            conflict_items.append(
                {
                    "edge_id": "",
                    "type": "payload_conflict_ref",
                    "from_id": node.id,
                    "to_id": ref,
                    "related_node_ids": [node.id, ref],
                    "from_text": _short_text(node.text or ""),
                    "to_text": _short_text(other.text or "") if other else _short_text(ref),
                    "reason": f"Node payload marks conflict via '{'conflicts_with' if payload.get('conflicts_with') else 'contradicts'}'",
                }
            )

    missing_items = _unique_items(missing_items)
    conflict_items = _unique_items(conflict_items)

    return {
        "context_set_id": context_set.id,
        "context_set_name": context_set.name,
        "selected": selected_items,
        "pinned": pinned_items,
        "excluded": excluded_items,
        "missing": missing_items[:40],
        "conflicting": conflict_items[:40],
        "compiled_kept_node_ids": kept_node_ids,
        "counts": {
            "selected": len(selected_items),
            "pinned": len(pinned_items),
            "excluded": len(excluded_items),
            "missing": len(missing_items),
            "conflicting": len(conflict_items),
        },
    }
