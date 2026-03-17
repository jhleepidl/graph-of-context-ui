from __future__ import annotations

from typing import Any


def _clean_text(value: Any) -> str | None:
    clean = str(value or "").strip()
    return clean or None


def _clean_list(value: Any, *, limit: int = 16) -> list[str]:
    if isinstance(value, str):
        clean = value.strip()
        return [clean] if clean else []
    if not isinstance(value, (list, tuple, set)):
        return []
    out: list[str] = []
    for item in value:
        clean = str(item or "").strip()
        if not clean:
            continue
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def build_scope_projection(runtime_snapshot: dict[str, Any] | None = None, *, team_view: dict[str, Any] | None = None) -> dict[str, Any]:
    snapshot = runtime_snapshot or {}
    items = list((team_view or {}).get("items") or [])
    labels_by_instance = {
        str(item.get("runtime_instance_id") or item.get("instance_id") or "").strip(): (
            str(item.get("display_label") or item.get("role_label") or item.get("role_id") or "runtime agent").strip()
        )
        for item in items
        if str(item.get("runtime_instance_id") or item.get("instance_id") or "").strip()
    }
    labels_by_slot = {
        str(item.get("slot_id") or "").strip(): (
            str(item.get("display_label") or item.get("slot_label") or item.get("role_label") or item.get("role_id") or "runtime agent").strip()
        )
        for item in items
        if str(item.get("slot_id") or "").strip()
    }

    scope_specs = list(snapshot.get("scope_specs") or [])
    materialized_by_scope = {
        str(item.get("scope_id") or "").strip(): item
        for item in list(snapshot.get("materialized_scopes") or [])
        if str(item.get("scope_id") or "").strip()
    }

    projection_items: list[dict[str, Any]] = []
    grant_counts: dict[str, int] = {}
    visibility_counts: dict[str, int] = {}
    grant_fields = (
        "shared_summary",
        "global_memory",
        "conversation_tail",
        "upstream_results",
        "upstream_summaries",
        "user_pinned_nodes",
        "explicit_uploaded_files",
    )
    for spec in scope_specs:
        scope_id = _clean_text(spec.get("scope_id") or spec.get("scopeId"))
        target_instance_id = _clean_text(spec.get("target_instance_id") or spec.get("targetInstanceId"))
        target_slot_id = _clean_text(spec.get("target_slot_id") or spec.get("targetSlotId"))
        display_label = labels_by_instance.get(target_instance_id or "") or labels_by_slot.get(target_slot_id or "")
        visibility_mode = _clean_text(spec.get("visibility_mode") or spec.get("visibilityMode") or "scoped") or "scoped"
        visibility_counts[visibility_mode] = int(visibility_counts.get(visibility_mode) or 0) + 1
        memory_grants = spec.get("memory_grants") or spec.get("memoryGrants") or {}
        materialized = materialized_by_scope.get(scope_id or "", {})
        active_node_ids = _clean_list(materialized.get("active_node_ids") or materialized.get("activeNodeIds"), limit=128)
        type_breakdown = materialized.get("type_breakdown") if isinstance(materialized.get("type_breakdown"), dict) else {}
        active_type_labels = [f"{key}:{value}" for key, value in list(type_breakdown.items())[:8]]
        enabled_grants = []
        if isinstance(memory_grants, dict):
            for field in grant_fields:
                if memory_grants.get(field) is True:
                    enabled_grants.append(field)
                    grant_counts[field] = int(grant_counts.get(field) or 0) + 1
        lineage = materialized.get("lineage") if isinstance(materialized.get("lineage"), dict) else {}
        authoritative_scope = str(lineage.get("compiler") or "").strip().lower() == "goc_scope_materializer"
        projection_items.append({
            "scope_id": scope_id,
            "runtime_instance_id": target_instance_id,
            "slot_id": target_slot_id,
            "display_label": display_label,
            "visibility_mode": visibility_mode,
            "context_types": _clean_list(spec.get("context_types"), limit=12),
            "memory_grants": memory_grants if isinstance(memory_grants, dict) else {},
            "grant_labels": enabled_grants,
            "selection_reason": _clean_text(spec.get("selection_reason") or spec.get("selectionReason")),
            "visibility_rationale": _clean_text(spec.get("visibility_rationale") or spec.get("visibilityRationale")),
            "context_set_id": _clean_text(materialized.get("context_set_id") or materialized.get("contextSetId")),
            "token_estimate": materialized.get("token_estimate"),
            "scope_version": materialized.get("scope_version") or materialized.get("scopeVersion"),
            "active_node_ids": active_node_ids,
            "active_node_count": len(active_node_ids),
            "active_type_labels": active_type_labels,
            "compiler": _clean_text(lineage.get("compiler")),
            "selection_strategy": _clean_text(lineage.get("selection_strategy") or lineage.get("selectionStrategy")),
            "selection_summary": _clean_text(lineage.get("selection_summary") or lineage.get("selectionSummary")),
            "matched_query_terms": _clean_list(lineage.get("matched_query_terms") or lineage.get("matchedQueryTerms"), limit=8),
            "matched_context_types": _clean_list(lineage.get("matched_context_types") or lineage.get("matchedContextTypes"), limit=8),
            "seed_node_count": int(lineage.get("seed_node_count") or 0),
            "candidate_node_count": int(lineage.get("candidate_node_count") or 0),
            "positive_candidate_count": int(lineage.get("positive_candidate_count") or 0),
            "rejected_positive_node_ids": _clean_list(lineage.get("rejected_positive_node_ids") or lineage.get("rejectedPositiveNodeIds"), limit=6),
            "selection_confidence": _clean_text(lineage.get("selection_confidence") or lineage.get("selectionConfidence")),
            "truncated": bool(lineage.get("truncated") is True),
            "authoritative_scope": authoritative_scope,
            "empty_scope": bool(lineage.get("empty_scope") is True),
            "soft_budget_exceeded": bool(lineage.get("soft_budget_exceeded") is True),
        })

    context_runtime_mode = _clean_text(snapshot.get("context_runtime_mode") or snapshot.get("contextRuntimeMode")) or (
        "scoped_context" if projection_items else "shared_memory"
    )
    legacy_context_pack_count = int(snapshot.get("legacy_context_pack_count") or snapshot.get("legacyContextPackCount") or 0)
    legacy_context_packs_enabled = bool(snapshot.get("legacy_context_packs_enabled") or snapshot.get("legacyContextPacksEnabled"))
    legacy_context_strategy = _clean_text(snapshot.get("legacy_context_strategy") or snapshot.get("legacyContextStrategy")) or (
        "primary" if legacy_context_packs_enabled else ("fallback_only" if legacy_context_pack_count > 0 else "disabled")
    )
    return {
        "context_runtime_mode": context_runtime_mode,
        "items": projection_items,
        "count": len(projection_items),
        "grant_counts": grant_counts,
        "visibility_counts": visibility_counts,
        "legacy_context_pack_count": legacy_context_pack_count,
        "legacy_context_packs_enabled": legacy_context_packs_enabled,
        "legacy_context_strategy": legacy_context_strategy,
        "scope_first_ready": len(projection_items) > 0 and context_runtime_mode == "scoped_context",
        "scope_projection_note": _clean_text(snapshot.get("scope_projection_note") or snapshot.get("scopeProjectionNote")),
    }


def build_visibility_projection(runtime_snapshot: dict[str, Any] | None = None, *, scope_projection: dict[str, Any] | None = None) -> dict[str, Any]:
    snapshot = runtime_snapshot or {}
    scope_items = list((scope_projection or {}).get("items") or [])
    labels_by_scope = {
        str(item.get("scope_id") or "").strip(): (
            str(item.get("display_label") or item.get("scope_id") or "scope").strip()
        )
        for item in scope_items
        if str(item.get("scope_id") or "").strip()
    }
    edges = []
    relation_counts: dict[str, int] = {}
    for index, raw in enumerate(list(snapshot.get("visibility_graph") or []), start=1):
        from_scope_id = _clean_text(raw.get("from_scope_id") or raw.get("fromScopeId"))
        to_scope_id = _clean_text(raw.get("to_scope_id") or raw.get("toScopeId"))
        relation = _clean_text(raw.get("relation") or "visible_to") or "visible_to"
        relation_counts[relation] = int(relation_counts.get(relation) or 0) + 1
        edges.append({
            "edge_id": _clean_text(raw.get("edge_id") or raw.get("edgeId") or f"visibility_edge_{index}"),
            "from_scope_id": from_scope_id,
            "to_scope_id": to_scope_id,
            "from_label": labels_by_scope.get(from_scope_id or "") or from_scope_id,
            "to_label": labels_by_scope.get(to_scope_id or "") or to_scope_id,
            "relation": relation,
        })
    return {
        "items": edges,
        "count": len(edges),
        "relation_counts": relation_counts,
    }
