from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from app.services.context_packs import extract_context_pack_summaries
from app.services.planning_boundary import build_planning_boundary_projection
from app.services.runtime_authority import apply_runtime_authority, derive_runtime_authority
from app.services.runtime_scope import (
    build_step_run_id_index as _build_step_run_id_index,
    filter_nodes_for_run as _filter_nodes_for_run,
    infer_current_run_id as _infer_current_run_id,
    resolve_run_scoped_nodes,
)
from app.services.skill_projections import extract_runtime_agents_with_skills, extract_skill_usage_events
from app.services.skill_registry import build_skill_registry


EVIDENCE_NODE_TYPES = {"Decision", "Assumption", "Plan", "Observation", "ContextSummary", "Artifact", "Resource", "Message"}


def build_step_run_id_index(nodes: Iterable[Any], edges: Iterable[Any]) -> dict[str, str | None]:
    return _build_step_run_id_index(nodes, edges)


def infer_current_run_id(nodes: Iterable[Any], edges: Iterable[Any]) -> str | None:
    return _infer_current_run_id(nodes, edges)


def filter_nodes_for_run(
    nodes: Iterable[Any],
    edges: Iterable[Any],
    *,
    run_id: str | None,
) -> list[Any]:
    return _filter_nodes_for_run(nodes, edges, run_id=run_id)


def _aggregate_attached_skills(runtime_agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aggregated: dict[str, dict[str, Any]] = {}

    for agent in runtime_agents:
        for attached in list(agent.get("attached_skills") or []):
            skill_id = str(attached.get("skill_id") or "").strip()
            if not skill_id:
                continue

            current = aggregated.get(skill_id)
            if not current:
                aggregated[skill_id] = {
                    "skill_id": skill_id,
                    "skill_name": attached.get("skill_name"),
                    "load_level": attached.get("load_level") or "metadata_only",
                    "selected_by": attached.get("selected_by") or "runtime",
                    "selection_reason": attached.get("selection_reason"),
                    "status": attached.get("status") or "active",
                    "role_count": 1,
                }
                continue

            current["role_count"] = int(current.get("role_count") or 0) + 1
            if attached.get("skill_name"):
                current["skill_name"] = attached.get("skill_name")
            if attached.get("selection_reason"):
                current["selection_reason"] = attached.get("selection_reason")
            if attached.get("selected_by"):
                current["selected_by"] = attached.get("selected_by")
            if attached.get("status"):
                current["status"] = attached.get("status")

            current_level = str(current.get("load_level") or "")
            incoming_level = str(attached.get("load_level") or "")
            level_rank = {"metadata_only": 1, "instructions": 2, "resources": 3}
            if level_rank.get(incoming_level, 0) >= level_rank.get(current_level, 0):
                current["load_level"] = incoming_level or current_level

    return sorted(
        aggregated.values(),
        key=lambda item: (
            str(item.get("skill_name") or "").lower(),
            str(item.get("skill_id") or ""),
        ),
    )


def _build_skill_lineage_projection(
    *,
    runtime_agents: list[dict[str, Any]],
    context_packs: list[dict[str, Any]],
    usage_events: list[dict[str, Any]],
    nodes: Iterable[Any],
    edges: Iterable[Any],
) -> dict[str, Any]:
    role_skill_links: list[dict[str, Any]] = []
    for agent in runtime_agents:
        for attached in list(agent.get("attached_skills") or []):
            role_skill_links.append(
                {
                    "runtime_instance_id": agent.get("runtime_instance_id"),
                    "role_label": agent.get("role_label"),
                    "skill_id": attached.get("skill_id"),
                    "skill_name": attached.get("skill_name"),
                    "load_level": attached.get("load_level"),
                    "selected_by": attached.get("selected_by"),
                    "selection_reason": attached.get("selection_reason"),
                }
            )

    skill_context_links: list[dict[str, Any]] = []
    for pack in context_packs:
        for skill_item in list(pack.get("skill_items") or []):
            skill_context_links.append(
                {
                    "context_pack_id": pack.get("context_pack_id"),
                    "target_runtime_agent_instance_id": pack.get("target_runtime_agent_instance_id"),
                    "scope": pack.get("scope"),
                    "skill_id": skill_item.get("skill_id"),
                    "load_level": skill_item.get("load_level"),
                    "count": skill_item.get("count"),
                }
            )

    nodes_by_id = {str(getattr(node, "id", "")): node for node in nodes}
    outgoing: dict[str, list[Any]] = {}
    for edge in edges:
        src = str(getattr(edge, "from_id", "") or "")
        outgoing.setdefault(src, []).append(edge)

    skill_evidence_links: list[dict[str, Any]] = []
    for event in usage_events:
        skill_id = str(event.get("skill_id") or "").strip()
        event_node_id = str(event.get("node_id") or "").strip()
        if not skill_id or not event_node_id:
            continue

        for edge in outgoing.get(event_node_id, []):
            target_id = str(getattr(edge, "to_id", "") or "")
            target_node = nodes_by_id.get(target_id)
            if not target_node:
                continue
            target_type = str(getattr(target_node, "type", "") or "")
            if target_type not in EVIDENCE_NODE_TYPES:
                continue
            skill_evidence_links.append(
                {
                    "skill_id": skill_id,
                    "event_type": event.get("event_type"),
                    "from_node_id": event_node_id,
                    "to_node_id": target_id,
                    "to_node_type": target_type,
                    "edge_type": str(getattr(edge, "type", "") or ""),
                }
            )

    return {
        "role_skill_links": role_skill_links[:180],
        "skill_context_links": skill_context_links[:220],
        "skill_evidence_links": skill_evidence_links[:260],
        "counts": {
            "role_skill_links": len(role_skill_links),
            "skill_context_links": len(skill_context_links),
            "skill_evidence_links": len(skill_evidence_links),
        },
    }


def build_run_skill_summary(
    *,
    nodes: Iterable[Any],
    edges: Iterable[Any],
    run_id: str | None = None,
) -> dict[str, Any]:
    nodes_list = list(nodes)
    edges_list = list(edges)
    scoped = resolve_run_scoped_nodes(nodes=nodes_list, edges=edges_list, run_id=run_id)
    target_run_id = scoped.get("run_id")
    scoped_nodes = list(scoped.get("nodes") or [])

    registry = build_skill_registry(nodes=nodes_list, include_defaults=True)

    runtime_projection = extract_runtime_agents_with_skills(scoped_nodes, skill_lookup=registry)
    runtime_agents = list(runtime_projection.get("items") or [])

    context_packs = extract_context_pack_summaries(scoped_nodes)
    usage_events = extract_skill_usage_events(scoped_nodes, skill_lookup=registry)
    attached_skill_summaries = _aggregate_attached_skills(runtime_agents)

    referenced_skill_ids: set[str] = set()
    for item in attached_skill_summaries:
        skill_id = str(item.get("skill_id") or "").strip()
        if skill_id:
            referenced_skill_ids.add(skill_id)
    for event in usage_events:
        skill_id = str(event.get("skill_id") or "").strip()
        if skill_id:
            referenced_skill_ids.add(skill_id)
    for pack in context_packs:
        for skill_item in list(pack.get("skill_items") or []):
            skill_id = str(skill_item.get("skill_id") or "").strip()
            if skill_id:
                referenced_skill_ids.add(skill_id)

    skill_packages = sorted(
        [registry[skill_id] for skill_id in referenced_skill_ids if skill_id in registry],
        key=lambda item: (str(item.get("name") or "").lower(), str(item.get("id") or "")),
    )

    lineage = _build_skill_lineage_projection(
        runtime_agents=runtime_agents,
        context_packs=context_packs,
        usage_events=usage_events,
        nodes=scoped_nodes,
        edges=edges_list,
    )
    authority = derive_runtime_authority(
        nodes=scoped_nodes,
        skill_packages=skill_packages,
        runtime_agents=runtime_agents,
        usage_events=usage_events,
        context_packs=context_packs,
        context_source_default="goc",
        plan_source_default="local",
    )

    out = {
        "run_id": target_run_id,
        "runtime_agents": runtime_agents,
        "attached_skills": attached_skill_summaries,
        "skill_packages": skill_packages,
        "context_packs": context_packs,
        "skill_usage": usage_events,
        "lineage": lineage,
        "counts": {
            "runtime_agents": len(runtime_agents),
            "attached_skills": len(attached_skill_summaries),
            "skill_packages": len(skill_packages),
            "context_packs": len(context_packs),
            "skill_usage": len(usage_events),
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    out = apply_runtime_authority(out, authority)
    out["planning_boundary"] = build_planning_boundary_projection(
        run_id=target_run_id,
        runtime_authority=authority,
    )
    return out


def build_thread_context_pack_summary(
    *,
    nodes: Iterable[Any],
    edges: Iterable[Any],
    run_id: str | None = None,
) -> dict[str, Any]:
    nodes_list = list(nodes)
    edges_list = list(edges)
    scoped = resolve_run_scoped_nodes(nodes=nodes_list, edges=edges_list, run_id=run_id)
    target_run_id = scoped.get("run_id")
    scoped_nodes = list(scoped.get("nodes") or [])

    context_packs = extract_context_pack_summaries(scoped_nodes)
    authority = derive_runtime_authority(
        nodes=scoped_nodes,
        context_packs=context_packs,
        context_source_default="goc",
        plan_source_default="local",
    )
    out = {
        "run_id": target_run_id,
        "items": context_packs,
        "count": len(context_packs),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    out = apply_runtime_authority(out, authority)
    out["planning_boundary"] = build_planning_boundary_projection(
        run_id=target_run_id,
        runtime_authority=authority,
    )
    return out


def build_thread_skill_usage_summary(
    *,
    nodes: Iterable[Any],
    edges: Iterable[Any],
    run_id: str | None = None,
) -> dict[str, Any]:
    nodes_list = list(nodes)
    edges_list = list(edges)
    scoped = resolve_run_scoped_nodes(nodes=nodes_list, edges=edges_list, run_id=run_id)
    target_run_id = scoped.get("run_id")
    scoped_nodes = list(scoped.get("nodes") or [])

    registry = build_skill_registry(nodes=nodes_list, include_defaults=True)
    events = extract_skill_usage_events(scoped_nodes, skill_lookup=registry)
    authority = derive_runtime_authority(
        nodes=scoped_nodes,
        usage_events=events,
        context_source_default="goc",
        plan_source_default="local",
    )
    out = {
        "run_id": target_run_id or None,
        "items": events,
        "count": len(events),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    out = apply_runtime_authority(out, authority)
    out["planning_boundary"] = build_planning_boundary_projection(
        run_id=target_run_id or None,
        runtime_authority=authority,
    )
    return out


def build_skill_lineage_projection(
    *,
    nodes: Iterable[Any],
    edges: Iterable[Any],
    run_id: str | None = None,
) -> dict[str, Any]:
    summary = build_run_skill_summary(nodes=nodes, edges=edges, run_id=run_id)
    return summary.get("lineage") or {
        "role_skill_links": [],
        "skill_context_links": [],
        "skill_evidence_links": [],
        "counts": {
            "role_skill_links": 0,
            "skill_context_links": 0,
            "skill_evidence_links": 0,
        },
    }
