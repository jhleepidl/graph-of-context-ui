from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sqlmodel import Session, select

from app.models import Edge, Node, NodeEmbedding
from app.services.embedding import ensure_nodes_embeddings, jload
from app.services.vector_index import EMBED_DIM


HierarchyNode = Dict[str, Any]


def _safe_text(text: Optional[str]) -> str:
    return (text or "").strip()


def _compact(text: Optional[str], max_len: int = 56) -> str:
    s = " ".join((_safe_text(text)).split())
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + "..."


def _payload(node: Node) -> Dict[str, Any]:
    return jload(node.payload_json or "{}", {})


def _created_key(node: Node) -> str:
    try:
        return node.created_at.isoformat()
    except Exception:
        return ""


def _vector_for_node(node: Node, emb: Optional[NodeEmbedding]) -> Optional[np.ndarray]:
    if emb is not None and emb.embedding_json and emb.embedding_json != "[]":
        arr = np.asarray(jload(emb.embedding_json, []), dtype=np.float32)
        if arr.ndim == 1 and arr.size == EMBED_DIM:
            n = float(np.linalg.norm(arr))
            if n > 1e-9:
                return (arr / n).astype(np.float32)
    txt = _safe_text(node.text)
    if not txt:
        return None
    # deterministic lexical fallback if embedding missing/invalid (should be rare after ensure_nodes_embeddings)
    vec = np.zeros((EMBED_DIM,), dtype=np.float32)
    for tok in txt.lower().split():
        h = hash(tok)
        idx = abs(h) % EMBED_DIM
        sign = -1.0 if (h & 1) else 1.0
        vec[idx] += sign
    n = float(np.linalg.norm(vec))
    if n <= 1e-9:
        return None
    return (vec / n).astype(np.float32)


def _mean_vec(vectors: List[np.ndarray]) -> Optional[np.ndarray]:
    if not vectors:
        return None
    mat = np.stack(vectors, axis=0).astype(np.float32)
    v = mat.mean(axis=0)
    n = float(np.linalg.norm(v))
    if n <= 1e-9:
        return None
    return (v / n).astype(np.float32)


def _cos(a: Optional[np.ndarray], b: Optional[np.ndarray]) -> float:
    if a is None or b is None:
        return -1.0
    return float(np.dot(a, b))


def _node_sort_key(item: Dict[str, Any]) -> Tuple[str, str]:
    # stable ordering for deterministic hierarchy rendering
    return (item.get("created_at") or "", item.get("id") or "")


def _snippet_for_node(node: Optional[Node]) -> str:
    if not node:
        return ""
    if node.type == "Resource":
        p = _payload(node)
        name = str(p.get("name") or "").strip()
        if name:
            return name
    return _compact(node.text or node.type or node.id)


def _make_leaf_item(node: Node, vec: Optional[np.ndarray]) -> Dict[str, Any]:
    return {
        "kind": "leaf",
        "id": node.id,
        "label": f"{node.type}:{_snippet_for_node(node)}",
        "leaf_node_ids": [node.id],
        "centroid": vec,
        "created_at": _created_key(node),
        "node": node,
    }


def _make_group_item(group_id: str, label: str, kind: str, child_items: List[Dict[str, Any]], source_node: Optional[Node] = None) -> Dict[str, Any]:
    vecs = [c.get("centroid") for c in child_items if c.get("centroid") is not None]
    centroid = _mean_vec(vecs) if vecs else None
    leaf_ids: List[str] = []
    for c in child_items:
        leaf_ids.extend(c.get("leaf_node_ids") or [])
    return {
        "kind": kind,
        "id": group_id,
        "label": label,
        "children_items": child_items,
        "leaf_node_ids": leaf_ids,
        "centroid": centroid,
        "created_at": _created_key(source_node) if source_node else min([c.get("created_at") or "" for c in child_items] or [""]),
        "source_node": source_node,
    }


def _cluster_label(items: List[Dict[str, Any]], nodes_by_id: Dict[str, Node], prefix: str = "Cluster") -> str:
    # pick representative leaf with earliest created_at among top similarity to centroid
    vecs = [it.get("centroid") for it in items if it.get("centroid") is not None]
    centroid = _mean_vec([v for v in vecs if v is not None])
    rep_leaf: Optional[str] = None
    rep_score = -10.0
    for it in items:
        for nid in it.get("leaf_node_ids") or []:
            node = nodes_by_id.get(nid)
            v = None
            # leaf lookup from node vectors happens in caller via items' centroids only; centroid fallback OK
            if it.get("kind") == "leaf" and it.get("id") == nid:
                v = it.get("centroid")
            score = _cos(centroid, v if v is not None else it.get("centroid"))
            if score > rep_score or (abs(score - rep_score) < 1e-9 and rep_leaf and nid < rep_leaf):
                rep_score = score
                rep_leaf = nid
    if rep_leaf and rep_leaf in nodes_by_id:
        rep = _snippet_for_node(nodes_by_id[rep_leaf])
        return f"{prefix} · {rep}"
    return f"{prefix} ({sum(len(it.get('leaf_node_ids') or []) for it in items)})"


def _partition_bisect(items: List[Dict[str, Any]]) -> Optional[Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]]:
    if len(items) < 4:
        return None
    with_vec = [it for it in items if it.get("centroid") is not None]
    without_vec = [it for it in items if it.get("centroid") is None]
    if len(with_vec) < 2:
        # deterministic split by time/id only
        mid = len(items) // 2
        if mid <= 0 or mid >= len(items):
            return None
        return items[:mid], items[mid:]

    # deterministic seeds: first by sort key, then farthest pair heuristic
    ordered = sorted(with_vec, key=_node_sort_key)
    seed_a = ordered[0]
    a_vec = seed_a["centroid"]
    far_b = max(ordered[1:] or ordered, key=lambda it: (1 - _cos(a_vec, it.get("centroid")), _node_sort_key(it)))
    b_vec = far_b["centroid"]
    if far_b is seed_a and len(ordered) >= 2:
        far_b = ordered[-1]
        b_vec = far_b["centroid"]
    far_c = max(ordered, key=lambda it: (1 - _cos(b_vec, it.get("centroid")), _node_sort_key(it)))
    c_vec = far_c["centroid"]

    if b_vec is None or c_vec is None:
        return None
    if np.allclose(b_vec, c_vec):
        mid = len(items) // 2
        return (sorted(items, key=_node_sort_key)[:mid], sorted(items, key=_node_sort_key)[mid:]) if 0 < mid < len(items) else None

    left: List[Dict[str, Any]] = []
    right: List[Dict[str, Any]] = []
    for it in items:
        v = it.get("centroid")
        if v is None:
            # attach missing-vector items to smaller side for balance
            (left if len(left) <= len(right) else right).append(it)
            continue
        sb = _cos(v, b_vec)
        sc = _cos(v, c_vec)
        if sb > sc:
            left.append(it)
        elif sc > sb:
            right.append(it)
        else:
            # stable tie-break
            (left if _node_sort_key(it) <= _node_sort_key(seed_a) else right).append(it)

    if not left or not right:
        ordered_all = sorted(items, key=_node_sort_key)
        mid = len(ordered_all) // 2
        if mid <= 0 or mid >= len(ordered_all):
            return None
        left, right = ordered_all[:mid], ordered_all[mid:]

    return sorted(left, key=_node_sort_key), sorted(right, key=_node_sort_key)


def _build_recursive_cluster(
    items: List[Dict[str, Any]],
    *,
    nodes_by_id: Dict[str, Node],
    max_leaf_size: int,
    depth: int,
    cluster_seq: List[int],
) -> Dict[str, Any]:
    # returns cluster tree node dict (view-only, virtual)
    total_leaves = sum(len(it.get("leaf_node_ids") or []) for it in items)
    items = sorted(items, key=_node_sort_key)

    if total_leaves <= max_leaf_size or len(items) <= 2:
        children: List[HierarchyNode] = []
        for it in items:
            if it.get("kind") == "leaf":
                n: Node = it["node"]
                children.append({
                    "id": f"leaf:{n.id}",
                    "kind": "leaf",
                    "label": _snippet_for_node(n) or n.type,
                    "node_id": n.id,
                    "node_type": n.type,
                    "leaf_node_ids": [n.id],
                    "size": 1,
                })
            else:
                # keep structural groups visible as subtrees even if leaf cap satisfied
                grp_children_items = it.get("children_items") or []
                group_node = _build_recursive_cluster(
                    grp_children_items,
                    nodes_by_id=nodes_by_id,
                    max_leaf_size=max(2, max_leaf_size - 1),
                    depth=depth + 1,
                    cluster_seq=cluster_seq,
                )
                group_node["id"] = it["id"]
                group_node["kind"] = it["kind"]
                group_node["label"] = it["label"]
                group_node["leaf_node_ids"] = list(it.get("leaf_node_ids") or [])
                group_node["size"] = len(group_node["leaf_node_ids"])
                children.append(group_node)

        return {
            "id": f"cluster:{depth}:{cluster_seq[0]}",
            "kind": "cluster" if depth > 0 else "root",
            "label": _cluster_label(items, nodes_by_id, prefix="Topic" if depth > 0 else "Hierarchy"),
            "children": children,
            "leaf_node_ids": [nid for c in children for nid in (c.get("leaf_node_ids") or [])],
            "size": sum(c.get("size", 0) for c in children),
        }

    part = _partition_bisect(items)
    if not part:
        # fallback terminal container
        return _build_recursive_cluster(items, nodes_by_id=nodes_by_id, max_leaf_size=10_000, depth=depth, cluster_seq=cluster_seq)

    left_items, right_items = part
    left_idx = cluster_seq[0]
    cluster_seq[0] += 1
    left_node = _build_recursive_cluster(left_items, nodes_by_id=nodes_by_id, max_leaf_size=max_leaf_size, depth=depth + 1, cluster_seq=cluster_seq)
    right_idx = cluster_seq[0]
    cluster_seq[0] += 1
    right_node = _build_recursive_cluster(right_items, nodes_by_id=nodes_by_id, max_leaf_size=max_leaf_size, depth=depth + 1, cluster_seq=cluster_seq)

    left_node.setdefault("id", f"cluster:{depth+1}:{left_idx}")
    right_node.setdefault("id", f"cluster:{depth+1}:{right_idx}")

    children = sorted([left_node, right_node], key=lambda c: ((c.get("children") or [{}])[0].get("label") if c.get("children") else c.get("label", ""), c.get("id", "")))
    return {
        "id": f"cluster:{depth}:{cluster_seq[0]}",
        "kind": "root" if depth == 0 else "cluster",
        "label": _cluster_label(items, nodes_by_id, prefix="Hierarchy" if depth == 0 else "Topic"),
        "children": children,
        "leaf_node_ids": [nid for c in children for nid in (c.get("leaf_node_ids") or [])],
        "size": sum(c.get("size", 0) for c in children),
    }


def _collect_leaf_layout(root: HierarchyNode) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    leaf_rows: List[Dict[str, Any]] = []
    depth_by_node: Dict[str, int] = {}

    def dfs(node: HierarchyNode, path: List[str], depth: int) -> None:
        kind = node.get("kind")
        if kind == "leaf":
            nid = node.get("node_id")
            if not nid:
                return
            rank = len(leaf_rows)
            cluster_path = [p for p in path if p and not p.startswith("leaf:")]
            leaf_depth = len(cluster_path)
            leaf_rows.append({
                "node_id": nid,
                "rank": rank,
                "depth": leaf_depth,
                "cluster_path": cluster_path,
            })
            depth_by_node[nid] = leaf_depth
            return
        for ch in node.get("children") or []:
            dfs(ch, path + [str(node.get("id") or "")], depth + 1)

    dfs(root, [], 0)
    return leaf_rows, depth_by_node


def _apply_structural_grouping(
    nodes: List[Node],
    edges: List[Edge],
    node_vecs: Dict[str, Optional[np.ndarray]],
) -> List[Dict[str, Any]]:
    nodes_by_id = {n.id: n for n in nodes}
    node_set = set(nodes_by_id.keys())

    # Only create structural virtual groups when parent is OUTSIDE the selected subset.
    # This avoids overlapping parent+children leaves and matches the user's mental model:
    # unfold is view/context-only, fold/split mutate the graph, while hierarchy view is a projection.
    group_children_by_parent: Dict[Tuple[str, str], List[str]] = {}
    for e in edges:
        if e.type not in {"HAS_PART", "FOLDS"}:
            continue
        if e.to_id not in node_set:
            continue
        if e.from_id in node_set:
            continue
        key = (e.type, e.from_id)
        group_children_by_parent.setdefault(key, []).append(e.to_id)

    consumed: set[str] = set()
    items: List[Dict[str, Any]] = []

    for (etype, parent_id), child_ids in sorted(group_children_by_parent.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        uniq = []
        seen = set()
        for cid in child_ids:
            if cid in seen or cid not in node_set:
                continue
            seen.add(cid)
            uniq.append(cid)
        if len(uniq) < 2:
            continue
        child_nodes = [nodes_by_id[cid] for cid in sorted(uniq, key=lambda nid: (_created_key(nodes_by_id[nid]), nid))]
        child_items = [_make_leaf_item(n, node_vecs.get(n.id)) for n in child_nodes]
        if etype == "FOLDS":
            label = f"Unfolded Fold · {parent_id[:6]}"
            kind = "structural_fold"
        else:
            label = f"Split Parts · {parent_id[:6]}"
            kind = "structural_split"
        items.append(_make_group_item(f"struct:{etype}:{parent_id}", label, kind, child_items))
        consumed.update(uniq)

    for n in sorted(nodes, key=lambda x: (_created_key(x), x.id)):
        if n.id in consumed:
            continue
        items.append(_make_leaf_item(n, node_vecs.get(n.id)))

    return items


def build_hierarchy_preview(
    session: Session,
    thread_id: str,
    *,
    node_ids: Optional[List[str]] = None,
    max_leaf_size: int = 6,
) -> Dict[str, Any]:
    q = select(Node).where(Node.thread_id == thread_id).order_by(Node.created_at.asc(), Node.id.asc())
    nodes = session.exec(q).all()
    if node_ids is not None:
        allow = set(node_ids)
        nodes = [n for n in nodes if n.id in allow]

    if not nodes:
        empty_root = {"id": "root", "kind": "root", "label": "Hierarchy", "children": [], "leaf_node_ids": [], "size": 0}
        return {
            "ok": True,
            "root": empty_root,
            "leaf_layout": [],
            "node_depths": {},
            "stats": {"selected_nodes": 0, "clustered_nodes": 0, "max_leaf_size": max_leaf_size},
        }

    # Ensure embeddings exist for better clustering (batch, one commit).
    ensure_nodes_embeddings(session, nodes, commit=True)

    node_ids_sel = [n.id for n in nodes]
    emb_rows = session.exec(
        select(NodeEmbedding).where(NodeEmbedding.thread_id == thread_id, NodeEmbedding.node_id.in_(node_ids_sel))
    ).all()
    emb_by_id = {e.node_id: e for e in emb_rows}

    edges = session.exec(
        select(Edge)
        .where(Edge.thread_id == thread_id)
        .where(Edge.type.in_(["HAS_PART", "FOLDS"]))
        .order_by(Edge.created_at.asc(), Edge.id.asc())
    ).all()

    node_vecs: Dict[str, Optional[np.ndarray]] = {}
    for n in nodes:
        node_vecs[n.id] = _vector_for_node(n, emb_by_id.get(n.id))

    top_items = _apply_structural_grouping(nodes, edges, node_vecs)
    nodes_by_id = {n.id: n for n in nodes}
    seq = [1]
    root = _build_recursive_cluster(
        top_items,
        nodes_by_id=nodes_by_id,
        max_leaf_size=max(2, int(max_leaf_size or 6)),
        depth=0,
        cluster_seq=seq,
    )
    root["id"] = "root"
    root["kind"] = "root"
    root["label"] = root.get("label") or "Hierarchy"

    leaf_layout, node_depths = _collect_leaf_layout(root)
    return {
        "ok": True,
        "root": root,
        "leaf_layout": leaf_layout,
        "node_depths": node_depths,
        "stats": {
            "selected_nodes": len(nodes),
            "clustered_nodes": len(leaf_layout),
            "max_leaf_size": max(2, int(max_leaf_size or 6)),
            "top_groups": len(top_items),
        },
    }
