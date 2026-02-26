from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence

from .context_ops import expand_closure_from_edges, ordered_unique

_TOKEN_RE = re.compile(r"[A-Za-z0-9_가-힣]{2,}")
_STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "into", "have", "will", "your",
    "있다", "하기", "에서", "그리고", "합니다", "대한", "하는", "해야", "관련", "으로", "했다",
}


def estimate_tokens(text: str) -> int:
    text = (text or "").strip()
    if not text:
        return 0
    # cheap, deterministic heuristic suitable for UI planning
    return max(1, math.ceil(len(text) / 4))


def tokenize_query(text: str) -> List[str]:
    out: List[str] = []
    seen = set()
    for tok in _TOKEN_RE.findall((text or "").lower()):
        if tok in _STOPWORDS or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out


def score_text(query_terms: Sequence[str], text: str) -> float:
    body = (text or "").lower()
    if not body:
        return 0.0
    counts = Counter(_TOKEN_RE.findall(body))
    score = 0.0
    for idx, term in enumerate(query_terms):
        tf = counts.get(term, 0)
        if tf <= 0:
            continue
        score += 3.0 / (idx + 1)
        score += min(2.5, 0.6 * tf)
        if term in body[:240]:
            score += 0.5
    return round(score, 4)


def _node_preview(node: Dict[str, Any], query: str, max_chars: int = 220) -> str:
    text = (node.get("text") or "").strip()
    if not text:
        return ""
    q_terms = tokenize_query(query)
    low = text.lower()
    pos = -1
    for t in q_terms:
        pos = low.find(t)
        if pos >= 0:
            break
    if pos < 0:
        snippet = text[:max_chars]
        return snippet + ("..." if len(text) > max_chars else "")
    start = max(0, pos - max_chars // 3)
    end = min(len(text), start + max_chars)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


def plan_unfold_candidates(
    *,
    query: str,
    nodes: Sequence[Dict[str, Any]],
    edges: Sequence[Dict[str, Any]],
    active_ids: Sequence[str],
    top_k: int = 8,
    max_candidates: int = 16,
    budget_tokens: int = 1200,
    closure_edge_types: Sequence[str] = ("DEPENDS", "HAS_PART", "SPLIT_FROM", "REFERENCES"),
    closure_direction: str = "both",
    max_closure_nodes: Optional[int] = 12,
) -> Dict[str, Any]:
    """UI-friendly unfold planner inspired by research `memory.py` candidate selection.

    It ranks seed nodes by lexical relevance, expands a bounded dependency closure,
    estimates marginal token cost, and returns deterministic candidates.
    """
    query_terms = tokenize_query(query)
    active_set = set(ordered_unique(active_ids))
    node_by_id = {str(n.get("id")): n for n in nodes if n.get("id")}

    scored: List[Dict[str, Any]] = []
    for node in nodes:
        nid = str(node.get("id") or "")
        if not nid or nid in active_set:
            continue
        text = node.get("text") or ""
        score = score_text(query_terms, text)
        if score <= 0:
            continue
        closure = expand_closure_from_edges(
            seed_ids=[nid],
            edges=edges,
            allowed_types=closure_edge_types,
            max_nodes=max_closure_nodes,
            direction=closure_direction,
        )
        ordered_ids = [x for x in closure["ordered_ids"] if x in node_by_id]
        marginal_ids = [x for x in ordered_ids if x not in active_set]
        marginal_cost = sum(estimate_tokens(node_by_id[x].get("text") or "") for x in marginal_ids)
        scored.append({
            "seed_id": nid,
            "seed_type": str(node.get("type") or "Node"),
            "score": score,
            "preview": _node_preview(node, query),
            "closure_ids": ordered_ids,
            "closure_added_ids": [x for x in ordered_ids if x != nid],
            "closure_size": len(ordered_ids),
            "marginal_cost_tokens": marginal_cost,
            "marginal_ratio": round(score / max(1, marginal_cost), 6),
            "closure_explain": closure,
        })

    scored.sort(key=lambda c: (float(c["marginal_ratio"]), float(c["score"]), -int(c["marginal_cost_tokens"])), reverse=True)
    scored = scored[: max(1, int(max_candidates))]

    selected_seed_ids: List[str] = []
    selected_ids = set(active_set)
    selected_cost = 0
    for cand in scored:
        add_ids = [nid for nid in cand["closure_ids"] if nid not in selected_ids]
        add_cost = sum(estimate_tokens(node_by_id[nid].get("text") or "") for nid in add_ids)
        if selected_cost + add_cost > max(1, int(budget_tokens)):
            continue
        selected_seed_ids.append(cand["seed_id"])
        selected_cost += add_cost
        for nid in add_ids:
            selected_ids.add(nid)
        if len(selected_seed_ids) >= max(1, int(top_k)):
            break

    return {
        "query": query,
        "query_terms": query_terms,
        "budget_tokens": int(budget_tokens),
        "closure_edge_types": list(closure_edge_types),
        "closure_direction": closure_direction,
        "max_closure_nodes": max_closure_nodes,
        "candidates": scored,
        "recommended_seed_ids": selected_seed_ids,
        "recommended_added_ids": [nid for nid in selected_ids if nid not in active_set],
        "recommended_added_count": len([nid for nid in selected_ids if nid not in active_set]),
        "recommended_cost_tokens": selected_cost,
    }


def apply_unfold_seed_selection(
    *,
    seed_node_ids: Sequence[str],
    nodes: Sequence[Dict[str, Any]],
    edges: Sequence[Dict[str, Any]],
    active_ids: Sequence[str],
    budget_tokens: int = 1200,
    closure_edge_types: Sequence[str] = ("DEPENDS", "HAS_PART", "SPLIT_FROM", "REFERENCES"),
    closure_direction: str = "both",
    max_closure_nodes: Optional[int] = 12,
) -> Dict[str, Any]:
    node_by_id = {str(n.get("id")): n for n in nodes if n.get("id")}
    active = ordered_unique(active_ids)
    active_set = set(active)
    selected = set(active_set)
    used = 0
    explain_steps: List[Dict[str, Any]] = []

    for seed_id in ordered_unique(seed_node_ids):
        if seed_id not in node_by_id:
            continue
        closure = expand_closure_from_edges(
            seed_ids=[seed_id],
            edges=edges,
            allowed_types=closure_edge_types,
            max_nodes=max_closure_nodes,
            direction=closure_direction,
        )
        add_ids = [nid for nid in closure["ordered_ids"] if nid in node_by_id and nid not in selected]
        add_cost = sum(estimate_tokens(node_by_id[nid].get("text") or "") for nid in add_ids)
        accepted = used + add_cost <= max(1, int(budget_tokens))
        explain_steps.append({
            "seed_id": seed_id,
            "candidate_add_ids": add_ids,
            "candidate_cost_tokens": add_cost,
            "accepted": accepted,
            "closure": closure,
        })
        if not accepted:
            continue
        used += add_cost
        for nid in add_ids:
            selected.add(nid)
            active.append(nid)

    return {
        "next_active_ids": ordered_unique(active),
        "added_ids": [nid for nid in active if nid not in active_set],
        "used_tokens": used,
        "budget_tokens": int(budget_tokens),
        "closure_edge_types": list(closure_edge_types),
        "closure_direction": closure_direction,
        "max_closure_nodes": max_closure_nodes,
        "steps": explain_steps,
    }
