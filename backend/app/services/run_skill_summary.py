from __future__ import annotations

from typing import Any, Iterable

from app.services.resolved_runtime import (
    build_skill_lineage_projection as _build_skill_lineage_projection,
    resolve_run_capabilities,
    resolve_runtime_projection,
)
from app.services.runtime_scope import (
    build_step_run_id_index as _build_step_run_id_index,
    filter_nodes_for_run as _filter_nodes_for_run,
    infer_current_run_id as _infer_current_run_id,
)


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


def build_run_skill_summary(
    *,
    nodes: Iterable[Any],
    edges: Iterable[Any],
    run_id: str | None = None,
) -> dict[str, Any]:
    projection = resolve_runtime_projection(
        nodes=nodes,
        edges=edges,
        run_id=run_id,
        include_conversation_team=False,
        context_source_default="goc",
        plan_source_default="local",
    )
    return projection.capability_payload()


def build_thread_context_pack_summary(
    *,
    nodes: Iterable[Any],
    edges: Iterable[Any],
    run_id: str | None = None,
) -> dict[str, Any]:
    projection = resolve_runtime_projection(
        nodes=nodes,
        edges=edges,
        run_id=run_id,
        include_conversation_team=False,
        context_source_default="goc",
        plan_source_default="local",
    )
    return projection.context_pack_payload()


def build_thread_skill_usage_summary(
    *,
    nodes: Iterable[Any],
    edges: Iterable[Any],
    run_id: str | None = None,
) -> dict[str, Any]:
    projection = resolve_runtime_projection(
        nodes=nodes,
        edges=edges,
        run_id=run_id,
        include_conversation_team=False,
        context_source_default="goc",
        plan_source_default="local",
    )
    return projection.skill_usage_payload()


def build_skill_lineage_projection(
    *,
    nodes: Iterable[Any],
    edges: Iterable[Any],
    run_id: str | None = None,
) -> dict[str, Any]:
    capabilities = resolve_run_capabilities(nodes=nodes, edges=edges, run_id=run_id)
    return capabilities.lineage or _build_skill_lineage_projection(
        runtime_agents=[],
        context_packs=[],
        usage_events=[],
        nodes=[],
        edges=[],
    )
