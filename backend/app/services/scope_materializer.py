from __future__ import annotations

import hashlib
import json
import math
from collections import deque
from datetime import datetime, timezone
from typing import Any, Iterable

try:
    from sqlmodel import Session
except Exception:  # pragma: no cover - optional for pure logic tests
    Session = Any

from app.services.scope_registry import get_scope_spec, list_scope_specs

_DEFAULT_CLOSURE_EDGES = {"CITES", "TABLE_OF", "SUMMARIZES", "REFERENCES", "HAS_PART", "DEPENDS", "SUPPORTS"}
_DEFAULT_MAX_NODES = 80
_DEFAULT_SOFT_TOKENS = 1800
_DEFAULT_HARD_TOKENS = 2600
_MAX_COMPILED_CHARS = 24000


_CONTEXT_TYPE_ALIASES = {
    "filings": {"filing", "dart", "sec", "regulatory"},
    "financial_tables": {"table", "financial", "statement"},
    "news": {"news", "headline", "market"},
    "workspace": {"workspace", "repo", "code", "patch"},
    "code": {"code", "repo", "patch", "diff"},
    "tests": {"test", "tests", "qa"},
    "upstream_results": {"summary", "result", "artifact", "observation"},
    "upstream_summaries": {"summary", "summaries", "contextsummary", "observation"},
    "claim_check": {"claim", "audit", "verify", "review"},
    "workflow": {"workflow", "run", "trace", "step", "decision"},
    "explicit_uploaded_files": {"upload", "file", "document", "pdf", "sheet"},
}


_ALLOWED_STRATEGIES = {
    "query_plus_closure",
    "workspace_plus_closure",
    "upstream_results_only",
    "upstream_summary_plus_evidence",
    "control_plane_trace",
    "shared_context_fallback",
}


def _graph_services():
    from app.services.graph import compile_active_context_explain, load_thread_graph

    return compile_active_context_explain, load_thread_graph


def _clean_text(value: Any, *, lower: bool = False, max_len: int | None = None) -> str:
    text = str(value or "").strip()
    if isinstance(max_len, int) and max_len > 0:
        text = text[:max_len]
    return text.lower() if lower else text


def _clean_list(value: Any, *, lower: bool = False, limit: int = 128) -> list[str]:
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = []
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = _clean_text(item, lower=lower)
        if not clean or clean in seen:
            continue
        seen.add(clean)
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def _jload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _node_payload(node: Any) -> dict[str, Any]:
    return _jload(getattr(node, "payload_json", None))


def _node_type(node: Any) -> str:
    return _clean_text(getattr(node, "type", None)) or "Unknown"


def _node_resource_kind(payload: dict[str, Any]) -> str:
    return _clean_text(
        payload.get("resource_kind")
        or payload.get("resourceKind")
        or payload.get("kind")
        or payload.get("file_kind")
        or payload.get("fileKind"),
        lower=True,
    )


def _record_text(node: Any, payload: dict[str, Any]) -> str:
    parts = [
        _clean_text(getattr(node, "text", None)),
        _clean_text(payload.get("summary")),
        _clean_text(payload.get("title")),
        _clean_text(payload.get("name")),
        _clean_text(payload.get("description")),
        _clean_text(payload.get("caption")),
        _clean_text(payload.get("content")),
        _clean_text(payload.get("source_name")),
    ]
    return "\n".join(part for part in parts if part)


def _has_hangul(text: str) -> bool:
    return any(0xAC00 <= ord(ch) <= 0xD7A3 for ch in text)


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    divisor = 3.0 if _has_hangul(text) else 4.0
    return int(math.ceil(len(text) / divisor))


def _clip_compiled_text_to_budget(text: str, *, hard_tokens: int) -> tuple[str, bool]:
    clean = _clean_text(text, max_len=_MAX_COMPILED_CHARS)
    if not clean:
        return "", False
    divisor = 3 if _has_hangul(clean) else 4
    max_chars = max(400, min(_MAX_COMPILED_CHARS, int(hard_tokens * divisor)))
    if len(clean) <= max_chars:
        return clean, False
    clipped = clean[: max(0, max_chars - 1)].rstrip()
    if not clipped:
        return "", True
    return f"{clipped}…", True


def _recent_nodes(nodes: Iterable[Any], *, limit: int) -> list[Any]:
    ordered = sorted(list(nodes or []), key=_sort_key, reverse=True)
    return ordered[: max(1, limit)]


def _scope_strategy(scope_spec: dict[str, Any]) -> str:
    selection = scope_spec.get("node_selection") if isinstance(scope_spec.get("node_selection"), dict) else {}
    strategy = _clean_text(selection.get("strategy") or selection.get("mode") or "query_plus_closure", lower=True) or "query_plus_closure"
    return strategy if strategy in _ALLOWED_STRATEGIES else "query_plus_closure"


def _extract_query_terms(scope_spec: dict[str, Any]) -> list[str]:
    selection = scope_spec.get("node_selection") or {}
    query = _clean_text(selection.get("query") or scope_spec.get("selection_reason") or "")
    if not query:
        return []
    tokens: list[str] = []
    for raw in query.replace("/", " ").replace("_", " ").split():
        term = _clean_text(raw, lower=True).strip(".,:;()[]{}!?\"'")
        if len(term) < 2:
            continue
        if term in {"the", "and", "for", "with", "this", "that", "from", "only", "role"}:
            continue
        tokens.append(term)
        if len(tokens) >= 24:
            break
    return tokens


def _scope_has_selection_signal(scope_spec: dict[str, Any]) -> bool:
    return bool(_clean_list(scope_spec.get("context_types"), lower=True, limit=16) or _extract_query_terms(scope_spec))


def _matches_context_types(node: Any, payload: dict[str, Any], context_types: list[str]) -> int:
    if not context_types:
        return 0
    node_type = _node_type(node).lower()
    resource_kind = _node_resource_kind(payload)
    haystack = " ".join([
        node_type,
        resource_kind,
        _clean_text(payload.get("kind"), lower=True),
        _clean_text(payload.get("category"), lower=True),
        _clean_text(payload.get("source_type"), lower=True),
        _clean_text(payload.get("source_name"), lower=True),
        _clean_text(payload.get("title"), lower=True),
    ])
    score = 0
    for context_type in context_types:
        context_key = _clean_text(context_type, lower=True)
        if not context_key:
            continue
        aliases = {context_key} | set(_CONTEXT_TYPE_ALIASES.get(context_key, set()))
        matched = False
        for alias in aliases:
            if alias in haystack:
                score += 3
                matched = True
                break
            if alias.endswith("s") and alias[:-1] and alias[:-1] in haystack:
                score += 2
                matched = True
                break
        if matched:
            continue
        if node_type == "resource" and context_key in {"file", "files", "evidence", "artifact", "artifacts"}:
            score += 1
    return score


def _strategy_node_score(node: Any, payload: dict[str, Any], *, strategy: str, role_id: str) -> int:
    node_type = _node_type(node).lower()
    resource_kind = _node_resource_kind(payload)
    strategy_key = _clean_text(strategy, lower=True) or "query_plus_closure"
    score = 0
    if strategy_key == "upstream_results_only":
        if node_type in {"artifact", "plan", "observation", "contextsummary"}:
            score += 6
        elif node_type == "message":
            score += 1
        else:
            score -= 2
    elif strategy_key == "upstream_summary_plus_evidence":
        if node_type in {"contextsummary", "observation", "artifact"}:
            score += 5
        elif node_type in {"resource", "decision"}:
            score += 2
    elif strategy_key == "workspace_plus_closure":
        if node_type in {"resource", "artifact"}:
            score += 4
        if any(key in resource_kind for key in {"code", "repo", "patch", "workspace", "file"}):
            score += 4
        if node_type == "message":
            score -= 1
    elif strategy_key == "control_plane_trace":
        if node_type in {"run", "step", "plan", "decision", "observation"}:
            score += 5
        elif node_type == "message":
            score += 1
    elif strategy_key == "shared_context_fallback":
        if node_type == "message":
            score += 1
    else:
        if role_id == "reviewer" and node_type in {"observation", "contextsummary", "resource"}:
            score += 2
        elif role_id == "builder" and node_type in {"artifact", "resource"}:
            score += 2
    return score


def _extract_match_diagnostics(node: Any, payload: dict[str, Any], *, scope_spec: dict[str, Any]) -> dict[str, Any]:
    query_terms = _extract_query_terms(scope_spec)
    record_text = _record_text(node, payload).lower()
    resource_kind = _node_resource_kind(payload)
    matched_terms = [term for term in query_terms if term and (term in record_text or term in resource_kind)][:8]
    matched_context_types: list[str] = []
    for context_type in _clean_list(scope_spec.get("context_types"), lower=True, limit=16):
        aliases = {context_type} | set(_CONTEXT_TYPE_ALIASES.get(context_type, set()))
        if any(alias and (alias in record_text or alias in resource_kind or alias in _node_type(node).lower()) for alias in aliases):
            matched_context_types.append(context_type)
    return {
        "matched_terms": matched_terms,
        "matched_context_types": matched_context_types[:8],
    }


def _score_node(node: Any, payload: dict[str, Any], *, scope_spec: dict[str, Any]) -> int:
    score = 0
    context_types = _clean_list(scope_spec.get("context_types"), lower=True, limit=16)
    query_terms = _extract_query_terms(scope_spec)
    grants = scope_spec.get("memory_grants") if isinstance(scope_spec.get("memory_grants"), dict) else {}
    record_text = _record_text(node, payload).lower()
    node_type = _node_type(node).lower()
    resource_kind = _node_resource_kind(payload)
    role_id = _clean_text(scope_spec.get("role_id"), lower=True)
    strategy = _scope_strategy(scope_spec)

    score += _matches_context_types(node, payload, context_types)
    score += _strategy_node_score(node, payload, strategy=strategy, role_id=role_id)

    for term in query_terms:
        if term and term in record_text:
            score += 2
        elif term and term in resource_kind:
            score += 1

    if node_type == "message":
        role = _clean_text(payload.get("role"), lower=True)
        if grants.get("conversation_tail") is True and role in {"user", "assistant"}:
            score += 1
        elif role_id in {"reviewer", "synthesizer"}:
            score -= 1
        elif strategy != "shared_context_fallback":
            score -= 1
    if grants.get("explicit_uploaded_files") is True and node_type in {"resource", "artifact"}:
        if any(key in resource_kind for key in {"upload", "file", "document", "pdf", "sheet"}):
            score += 3
        else:
            score += 1
    elif role_id in {"reviewer", "synthesizer"} and node_type == "resource":
        score -= 1
    if grants.get("user_pinned_nodes") is True and (
        payload.get("pinned") is True or payload.get("is_pinned") is True or _clean_text(payload.get("pin_level"), lower=True) == "required"
    ):
        score += 5
    if grants.get("upstream_results") is True and node_type in {"artifact", "plan", "observation", "contextsnapshot", "contextsummary"}:
        score += 2
    if grants.get("upstream_summaries") is True and node_type in {"message", "contextsummary", "plan", "observation"}:
        score += 1
    created_at = getattr(node, "created_at", None)
    if score > 0 and isinstance(created_at, datetime):
        age_hours = max(0.0, (datetime.now(timezone.utc) - created_at).total_seconds() / 3600.0)
        if age_hours <= 24:
            score += 1
    return score


def _seed_row_is_relevant(*, score: int, diagnostics: dict[str, Any], scope_spec: dict[str, Any]) -> bool:
    if score <= 0:
        return False
    strategy = _scope_strategy(scope_spec)
    matched_terms = list(diagnostics.get("matched_terms") or [])
    matched_context_types = list(diagnostics.get("matched_context_types") or [])
    if matched_terms or matched_context_types:
        return True
    if strategy == "shared_context_fallback":
        return True
    if strategy in {"upstream_results_only", "upstream_summary_plus_evidence", "workspace_plus_closure", "control_plane_trace"}:
        return score >= 4
    if not _scope_has_selection_signal(scope_spec):
        return score >= 2
    return False


def _selection_confidence(*, active_node_ids: list[str], seed_nodes: list[Any], matched_query_terms: list[str], matched_context_types: list[str], scope_spec: dict[str, Any]) -> str:
    if not active_node_ids:
        return "none"
    if matched_query_terms and matched_context_types:
        return "high"
    if matched_query_terms or matched_context_types:
        return "medium"
    if _scope_strategy(scope_spec) in {"upstream_results_only", "upstream_summary_plus_evidence", "workspace_plus_closure", "control_plane_trace"} and len(seed_nodes) >= 1:
        return "medium"
    if len(seed_nodes) >= 2:
        return "low"
    return "low"


def _sort_key(node: Any) -> tuple[int, str]:
    created_at = getattr(node, "created_at", None)
    if isinstance(created_at, datetime):
        stamp = created_at.timestamp()
    else:
        stamp = 0.0
    return int(stamp), _clean_text(getattr(node, "id", None))


def _build_neighbors(edges: Iterable[Any], *, allowed_types: set[str]) -> dict[str, set[str]]:
    neighbors: dict[str, set[str]] = {}
    allowed_types_lower = {entry.lower() for entry in allowed_types}
    for edge in edges:
        edge_type = _clean_text(getattr(edge, "type", None), lower=True)
        if allowed_types and edge_type.upper() not in allowed_types and edge_type not in allowed_types_lower:
            continue
        from_id = _clean_text(getattr(edge, "from_id", None))
        to_id = _clean_text(getattr(edge, "to_id", None))
        if not from_id or not to_id:
            continue
        neighbors.setdefault(from_id, set()).add(to_id)
        neighbors.setdefault(to_id, set()).add(from_id)
    return neighbors


def _expand_with_closure(seed_ids: list[str], *, neighbors: dict[str, set[str]], max_nodes: int) -> list[str]:
    if not seed_ids:
        return []
    visited: set[str] = set()
    out: list[str] = []
    queue = deque(seed_ids)
    while queue and len(out) < max_nodes:
        current = queue.popleft()
        if current in visited:
            continue
        visited.add(current)
        out.append(current)
        for neighbor in sorted(neighbors.get(current) or []):
            if neighbor not in visited:
                queue.append(neighbor)
    return out


def materialize_scope_from_graph(
    scope_spec: dict[str, Any],
    *,
    nodes: Iterable[Any],
    edges: Iterable[Any],
    thread_id: str,
    session: Session | None = None,
) -> dict[str, Any]:
    spec = dict(scope_spec or {})
    scope_id = _clean_text(spec.get("scope_id") or spec.get("scopeId")) or "scope_runtime"
    selection = spec.get("node_selection") if isinstance(spec.get("node_selection"), dict) else {}
    strategy = _scope_strategy(spec)
    max_nodes = int(selection.get("max_nodes") or selection.get("maxNodes") or _DEFAULT_MAX_NODES)
    max_nodes = max(1, min(128, max_nodes))
    closure_edge_types = {
        _clean_text(item).upper()
        for item in _clean_list(selection.get("closure_edge_types") or selection.get("closureEdgeTypes") or list(_DEFAULT_CLOSURE_EDGES), lower=False, limit=24)
    } or set(_DEFAULT_CLOSURE_EDGES)

    nodes_list = list(nodes or [])
    edges_list = list(edges or [])
    scored: list[tuple[int, tuple[int, str], Any, dict[str, Any]]] = []
    for node in nodes_list:
        payload = _node_payload(node)
        diagnostics = _extract_match_diagnostics(node, payload, scope_spec=spec)
        score = _score_node(node, payload, scope_spec=spec)
        scored.append((score, _sort_key(node), node, diagnostics))

    scored.sort(key=lambda item: (item[0], item[1][0], item[1][1]), reverse=True)
    positive_seed_rows = [
        item for item in scored
        if _seed_row_is_relevant(score=item[0], diagnostics=item[3], scope_spec=spec)
    ][: max(1, min(24, max_nodes))]
    positive_seed_nodes = [item[2] for item in positive_seed_rows]
    visibility_mode = _clean_text(spec.get("visibility_mode") or spec.get("visibilityMode") or "scoped", lower=True)
    has_selection_signal = _scope_has_selection_signal(spec)
    if positive_seed_nodes:
        seed_nodes = positive_seed_nodes
    elif visibility_mode in {"shared", "shared_memory", "shared_only"} and not has_selection_signal:
        seed_nodes = _recent_nodes(nodes_list, limit=max(1, min(12, max_nodes)))
    else:
        seed_nodes = []

    seed_node_ids = [_clean_text(getattr(node, "id", None)) for node in seed_nodes if _clean_text(getattr(node, "id", None))]
    matched_query_terms: list[str] = []
    matched_context_types: list[str] = []
    for _, _, _, diagnostics in positive_seed_rows[:8]:
        for term in diagnostics.get("matched_terms") or []:
            if term not in matched_query_terms:
                matched_query_terms.append(term)
        for context_type in diagnostics.get("matched_context_types") or []:
            if context_type not in matched_context_types:
                matched_context_types.append(context_type)

    rejected_node_ids: list[str] = []
    for score, _, node, diagnostics in scored:
        node_id = _clean_text(getattr(node, "id", None))
        if not node_id or node_id in seed_node_ids:
            continue
        if score > 0 and not _seed_row_is_relevant(score=score, diagnostics=diagnostics, scope_spec=spec):
            rejected_node_ids.append(node_id)
        if len(rejected_node_ids) >= 6:
            break

    neighbors = _build_neighbors(edges_list, allowed_types=closure_edge_types)
    expanded_ids = _expand_with_closure(seed_node_ids, neighbors=neighbors, max_nodes=max_nodes)

    ordered_ids: list[str] = []
    seen: set[str] = set()
    for node in seed_nodes:
        node_id = _clean_text(getattr(node, "id", None))
        if node_id and node_id not in seen:
            seen.add(node_id)
            ordered_ids.append(node_id)
    for node_id in expanded_ids:
        if node_id and node_id not in seen:
            seen.add(node_id)
            ordered_ids.append(node_id)
        if len(ordered_ids) >= max_nodes:
            break

    node_by_id = {
        _clean_text(getattr(node, "id", None)): node
        for node in nodes_list
        if _clean_text(getattr(node, "id", None))
    }
    active_node_ids = [node_id for node_id in ordered_ids if node_id in node_by_id][:max_nodes]

    if session is not None and active_node_ids:
        compile_active_context_explain, _ = _graph_services()
        compiled = compile_active_context_explain(session, thread_id, active_node_ids)
        compiled_text = _clean_text(compiled.get("compiled_text")) or ""
    else:
        lines: list[str] = []
        for node_id in active_node_ids:
            node = node_by_id.get(node_id)
            payload = _node_payload(node)
            text = _record_text(node, payload)
            if text:
                lines.append(f"[{_node_type(node)}] {text}")
        compiled_text = "\n\n".join(lines)

    type_breakdown: dict[str, int] = {}
    for node_id in active_node_ids:
        node = node_by_id.get(node_id)
        node_type = _node_type(node)
        type_breakdown[node_type] = int(type_breakdown.get(node_type) or 0) + 1

    budget = spec.get("budget") if isinstance(spec.get("budget"), dict) else {}
    soft_tokens = int(budget.get("soft_tokens") or budget.get("softTokens") or _DEFAULT_SOFT_TOKENS)
    soft_tokens = max(200, min(6000, soft_tokens))
    hard_tokens = int(budget.get("hard_tokens") or budget.get("hardTokens") or max(_DEFAULT_HARD_TOKENS, soft_tokens + 600))
    hard_tokens = max(max(soft_tokens, 200), min(8000, hard_tokens))
    compiled_text, truncated = _clip_compiled_text_to_budget(compiled_text, hard_tokens=hard_tokens)
    token_estimate = _estimate_tokens(compiled_text)
    scope_version = hashlib.sha1("|".join(active_node_ids).encode("utf-8")).hexdigest()[:12] if active_node_ids else "empty"
    selection_confidence = _selection_confidence(
        active_node_ids=active_node_ids,
        seed_nodes=seed_nodes,
        matched_query_terms=matched_query_terms,
        matched_context_types=matched_context_types,
        scope_spec=spec,
    )
    return {
        "scope_id": scope_id,
        "context_set_id": f"virtual_scope::{scope_id}",
        "active_node_ids": active_node_ids,
        "compiled_text": compiled_text,
        "token_estimate": token_estimate,
        "actual_tokens": token_estimate,
        "type_breakdown": dict(sorted(type_breakdown.items(), key=lambda item: item[0].lower())),
        "scope_version": scope_version,
        "lineage": {
            "compiler": "goc_scope_materializer",
            "compiler_version": "v4",
            "thread_id": thread_id,
            "selection_strategy": strategy,
            "seed_node_count": len(seed_nodes),
            "seed_node_ids": seed_node_ids[:12],
            "matched_query_terms": matched_query_terms[:8],
            "matched_context_types": matched_context_types[:8],
            "candidate_node_count": len(nodes_list),
            "positive_candidate_count": len(positive_seed_rows),
            "rejected_positive_node_ids": rejected_node_ids,
            "selection_confidence": selection_confidence,
            "selection_summary": f"{len(active_node_ids)} active nodes from {len(seed_nodes)} seeds ({selection_confidence})",
            "closure_edge_types": sorted(closure_edge_types),
            "truncated": truncated,
            "hard_tokens": hard_tokens,
            "soft_tokens": soft_tokens,
            "empty_scope": len(active_node_ids) == 0,
            "soft_budget_exceeded": token_estimate > soft_tokens,
            "materialized_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def materialize_runtime_scopes(
    session: Session,
    *,
    thread_id: str,
    runtime_snapshot: dict[str, Any] | None = None,
    scope_id: str | None = None,
) -> list[dict[str, Any]]:
    snapshot = runtime_snapshot or {}
    scope_specs = list_scope_specs(snapshot)
    clean_scope_id = _clean_text(scope_id) if scope_id is not None else ""
    if clean_scope_id:
        scope_specs = [spec for spec in scope_specs if _clean_text(spec.get("scope_id") or spec.get("scopeId")) == clean_scope_id]
    if not scope_specs:
        return []
    _, load_thread_graph = _graph_services()
    nodes, edges = load_thread_graph(session, thread_id)
    return [
        materialize_scope_from_graph(spec, nodes=nodes, edges=edges, thread_id=thread_id, session=session)
        for spec in scope_specs
    ]


def list_materialized_scopes(runtime_snapshot: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    snapshot = runtime_snapshot or {}
    return [
        dict(item)
        for item in list(snapshot.get("materialized_scopes") or snapshot.get("materializedScopes") or [])
        if isinstance(item, dict)
    ]


def materialize_scope(
    runtime_snapshot: dict[str, Any] | None,
    scope_id: str,
    *,
    session: Session | None = None,
    thread_id: str | None = None,
) -> dict[str, Any] | None:
    clean_scope_id = _clean_text(scope_id)
    if not clean_scope_id:
        return None

    if session is not None and thread_id:
        spec = get_scope_spec(runtime_snapshot, clean_scope_id)
        if spec:
            _, load_thread_graph = _graph_services()
            nodes, edges = load_thread_graph(session, thread_id)
            return materialize_scope_from_graph(spec, nodes=nodes, edges=edges, thread_id=thread_id, session=session)

    for item in list_materialized_scopes(runtime_snapshot):
        if _clean_text(item.get("scope_id") or item.get("scopeId")) == clean_scope_id:
            return item
    return None
