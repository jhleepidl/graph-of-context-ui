from __future__ import annotations

from typing import Any, Iterable

from app.services.runtime_snapshot import (
    created_sort_key as _created_sort_key,
    has_non_empty_value as _has_non_empty_value,
    node_payload as _node_payload,
    normalize_status as _normalize_status,
)


RUN_STEP_LINK_EDGE_TYPES = {"BELONGS_TO_RUN", "IN_RUN"}
INACTIVE_RUN_STATUS_VALUES = {
    "superseded",
    "abandoned",
    "replaced",
    "cancelled",
    "canceled",
    "inactive",
    "skipped",
}


def normalize_run_status(raw: Any) -> str:
    clean = _normalize_status(raw)
    if clean in {"error", "blocked"}:
        return "blocked"
    if clean in {"running", "queued", "done"}:
        return clean
    return "idle"


def run_status_from_step_counts(step_status_counts: dict[str, int]) -> str:
    if step_status_counts.get("running", 0) > 0:
        return "running"
    if step_status_counts.get("error", 0) > 0 or step_status_counts.get("blocked", 0) > 0:
        return "blocked"
    if step_status_counts.get("queued", 0) > 0:
        return "queued"
    if sum(step_status_counts.values()) > 0:
        return "done"
    return "idle"


def run_status_priority(status: str) -> int:
    if status == "running":
        return 50
    if status == "queued":
        return 40
    if status == "blocked":
        return 30
    if status == "done":
        return 20
    if status == "idle":
        return 10
    return 0


def run_is_inactive(payload: dict[str, Any]) -> bool:
    status_raw = str(
        payload.get("status")
        or payload.get("run_status")
        or payload.get("state")
        or ""
    ).strip().lower()
    if status_raw in INACTIVE_RUN_STATUS_VALUES:
        return True

    for key in (
        "superseded",
        "abandoned",
        "cancelled",
        "canceled",
        "inactive",
        "is_superseded",
        "is_abandoned",
        "is_cancelled",
        "is_inactive",
    ):
        if payload.get(key) is True:
            return True

    if _has_non_empty_value(payload.get("superseded_by_run_id")):
        return True
    if _has_non_empty_value(payload.get("replaced_by_run_id")):
        return True
    return False


def build_step_run_id_index(nodes: Iterable[Any], edges: Iterable[Any]) -> dict[str, str | None]:
    nodes_list = list(nodes)
    nodes_by_id = {str(getattr(node, "id", "") or ""): node for node in nodes_list}
    step_run_id_by_step_id: dict[str, str | None] = {}

    for node in nodes_list:
        if str(getattr(node, "type", "") or "") != "Step":
            continue
        payload = _node_payload(node)
        run_id = str(payload.get("run_id") or "").strip() or None
        step_run_id_by_step_id[str(getattr(node, "id", "") or "")] = run_id

    def _is_known_run_id(run_id: str | None) -> bool:
        if not run_id:
            return False
        run_node = nodes_by_id.get(run_id)
        return bool(run_node and str(getattr(run_node, "type", "") or "") == "Run")

    for edge in edges:
        edge_type = str(getattr(edge, "type", "") or "")
        if edge_type not in RUN_STEP_LINK_EDGE_TYPES:
            continue

        src_id = str(getattr(edge, "from_id", "") or "")
        dst_id = str(getattr(edge, "to_id", "") or "")
        src = nodes_by_id.get(src_id)
        dst = nodes_by_id.get(dst_id)
        if not src or not dst:
            continue

        src_type = str(getattr(src, "type", "") or "")
        dst_type = str(getattr(dst, "type", "") or "")

        if src_type == "Run" and dst_type == "Step":
            existing = step_run_id_by_step_id.get(dst_id)
            if not _is_known_run_id(existing):
                step_run_id_by_step_id[dst_id] = src_id
        elif src_type == "Step" and dst_type == "Run":
            existing = step_run_id_by_step_id.get(src_id)
            if not _is_known_run_id(existing):
                step_run_id_by_step_id[src_id] = dst_id

    return step_run_id_by_step_id


def resolve_current_runtime_scope(nodes: Iterable[Any], edges: Iterable[Any]) -> dict[str, Any]:
    nodes_list = list(nodes)
    edges_list = list(edges)
    nodes_by_id = {str(getattr(node, "id", "") or ""): node for node in nodes_list}
    run_nodes = sorted(
        [node for node in nodes_list if str(getattr(node, "type", "") or "") == "Run"],
        key=_created_sort_key,
    )
    step_nodes = sorted(
        [node for node in nodes_list if str(getattr(node, "type", "") or "") == "Step"],
        key=_created_sort_key,
    )
    step_run_id_by_step_id = build_step_run_id_index(nodes_list, edges_list)

    global_step_status_counts: dict[str, int] = {}
    for step in step_nodes:
        status = _normalize_status(_node_payload(step).get("status"))
        global_step_status_counts[status] = global_step_status_counts.get(status, 0) + 1

    candidate_keys = {str(getattr(run, "id", "") or "") for run in run_nodes}
    has_unscoped_steps = False
    for step in step_nodes:
        step_id = str(getattr(step, "id", "") or "")
        run_id = step_run_id_by_step_id.get(step_id)
        if run_id:
            candidate_keys.add(run_id)
        else:
            has_unscoped_steps = True
    if has_unscoped_steps:
        candidate_keys.add("__unscoped__")

    candidates: list[dict[str, Any]] = []
    for candidate_key in sorted(candidate_keys):
        run_node: Any | None = None
        if candidate_key != "__unscoped__":
            candidate_run_node = nodes_by_id.get(candidate_key)
            if candidate_run_node and str(getattr(candidate_run_node, "type", "") or "") == "Run":
                run_node = candidate_run_node

        steps_for_candidate = [
            step
            for step in step_nodes
            if (step_run_id_by_step_id.get(str(getattr(step, "id", "") or "")) or "__unscoped__") == candidate_key
        ]

        step_status_counts: dict[str, int] = {}
        for step in steps_for_candidate:
            status = _normalize_status(_node_payload(step).get("status"))
            step_status_counts[status] = step_status_counts.get(status, 0) + 1

        run_payload = _node_payload(run_node)
        run_status = run_status_from_step_counts(step_status_counts)
        if run_status == "idle":
            run_status = normalize_run_status(
                run_payload.get("status")
                or run_payload.get("run_status")
                or run_payload.get("state")
            )

        activity_keys: list[str] = []
        if run_node:
            activity_keys.append(_created_sort_key(run_node)[0])
        activity_keys.extend(_created_sort_key(step)[0] for step in steps_for_candidate)
        latest_activity_key = max(activity_keys) if activity_keys else ""

        candidates.append(
            {
                "candidate_key": candidate_key,
                "run_id": None if candidate_key == "__unscoped__" else candidate_key,
                "run_node": run_node,
                "steps": steps_for_candidate,
                "step_status_counts": step_status_counts,
                "status": run_status,
                "inactive": run_is_inactive(run_payload),
                "latest_activity_key": latest_activity_key,
                "run_created_key": _created_sort_key(run_node)[0] if run_node else "",
                "selection_source": (
                    "run_node"
                    if run_node
                    else ("unscoped_steps" if candidate_key == "__unscoped__" else "step_run_id")
                ),
            }
        )

    if not candidates:
        return {
            "current_candidate_key": "",
            "current_run_id": None,
            "current_run_node": None,
            "current_run_status": "idle",
            "current_run_inactive": False,
            "current_run_steps": [],
            "current_run_step_status_counts": {},
            "current_run_selection_source": None,
            "stale_queued_step_count": 0,
            "step_run_id_by_step_id": step_run_id_by_step_id,
            "global_step_status_counts": global_step_status_counts,
            "candidates": [],
        }

    candidates.sort(
        key=lambda item: (
            str(item.get("latest_activity_key") or ""),
            1 if not item.get("inactive") else 0,
            run_status_priority(str(item.get("status") or "idle")),
            str(item.get("run_created_key") or ""),
            str(item.get("run_id") or ""),
        )
    )
    current = candidates[-1]
    current_candidate_key = str(current.get("candidate_key") or "")
    stale_queued_step_count = 0
    for step in step_nodes:
        status = _normalize_status(_node_payload(step).get("status"))
        if status != "queued":
            continue
        step_candidate_key = step_run_id_by_step_id.get(str(getattr(step, "id", "") or "")) or "__unscoped__"
        if step_candidate_key != current_candidate_key:
            stale_queued_step_count += 1

    return {
        "current_candidate_key": current_candidate_key,
        "current_run_id": current.get("run_id"),
        "current_run_node": current.get("run_node"),
        "current_run_status": str(current.get("status") or "idle"),
        "current_run_inactive": bool(current.get("inactive")),
        "current_run_steps": current.get("steps") or [],
        "current_run_step_status_counts": current.get("step_status_counts") or {},
        "current_run_selection_source": current.get("selection_source"),
        "stale_queued_step_count": stale_queued_step_count,
        "step_run_id_by_step_id": step_run_id_by_step_id,
        "global_step_status_counts": global_step_status_counts,
        "candidates": candidates,
    }


def infer_current_run_id(nodes: Iterable[Any], edges: Iterable[Any]) -> str | None:
    scope = resolve_current_runtime_scope(nodes, edges)
    return str(scope.get("current_run_id") or "").strip() or None


def filter_nodes_for_run(
    nodes: Iterable[Any],
    edges: Iterable[Any],
    *,
    run_id: str | None,
) -> list[Any]:
    clean_run_id = str(run_id or "").strip()
    nodes_list = list(nodes)
    if not clean_run_id:
        return nodes_list

    step_run_id_by_step_id = build_step_run_id_index(nodes_list, edges)
    scoped: list[Any] = []

    for node in nodes_list:
        node_type = str(getattr(node, "type", "") or "")
        node_id = str(getattr(node, "id", "") or "")
        payload = _node_payload(node)

        if node_type == "Run":
            if node_id == clean_run_id:
                scoped.append(node)
            continue

        if node_type == "Step":
            step_run_id = step_run_id_by_step_id.get(node_id)
            if step_run_id == clean_run_id:
                scoped.append(node)
                continue
            payload_run_id = str(payload.get("run_id") or "").strip()
            if payload_run_id == clean_run_id:
                scoped.append(node)
            continue

        payload_run_id = str(payload.get("run_id") or "").strip()
        if payload_run_id == clean_run_id:
            scoped.append(node)

    return scoped


def resolve_run_scoped_nodes(
    *,
    nodes: Iterable[Any],
    edges: Iterable[Any],
    run_id: str | None = None,
) -> dict[str, Any]:
    nodes_list = list(nodes)
    edges_list = list(edges)
    scope = resolve_current_runtime_scope(nodes_list, edges_list)
    target_run_id = str(run_id or "").strip() or str(scope.get("current_run_id") or "").strip() or None
    scoped_nodes = (
        filter_nodes_for_run(nodes_list, edges_list, run_id=target_run_id)
        if target_run_id
        else nodes_list
    )
    return {
        "run_id": target_run_id,
        "nodes": scoped_nodes,
        "scope": scope,
    }
