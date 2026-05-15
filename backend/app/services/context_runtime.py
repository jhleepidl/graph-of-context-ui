from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlmodel import Session, select

from app.models import ContextProjectionEvent, ContextWriteMetricEvent, HandoffDeltaEvent, Thread, utcnow


def _jdump(value: Any) -> str:
    try:
        return json.dumps(value if value is not None else {}, ensure_ascii=False)
    except Exception:
        return "{}"


def _jload(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = _clean(value)
    if not text:
        return utcnow()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return utcnow()


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _stable_id(prefix: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return f"{prefix}_{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]}"


def _projection_to_dict(row: ContextProjectionEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "projection_id": row.projection_id,
        "snapshot_id": row.snapshot_id,
        "run_id": row.run_id,
        "agent_id": row.agent_id,
        "role_id": row.role_id,
        "task_type": row.task_type,
        "model_node": row.model_node,
        "cache_hit": row.cache_hit,
        "compile_ms": row.compile_ms,
        "context_tokens": row.context_tokens,
        "selected_atom_count": row.selected_atom_count,
        "selected_link_count": row.selected_link_count,
        "handoff_count": row.handoff_count,
        "goal_hash": row.goal_hash,
        "payload": _jload(row.payload_json, {}),
        "created_at": row.created_at.isoformat(),
    }


def _write_to_dict(row: ContextWriteMetricEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "event_id": row.event_id,
        "run_id": row.run_id,
        "projection_id": row.projection_id,
        "snapshot_id": row.snapshot_id,
        "status": row.status,
        "batch_size": row.batch_size,
        "committed": row.committed,
        "proposals": row.proposals,
        "conflicts": row.conflicts,
        "operation_append_ms": row.operation_append_ms,
        "payload": _jload(row.payload_json, {}),
        "created_at": row.created_at.isoformat(),
    }


def _handoff_to_dict(row: HandoffDeltaEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "handoff_id": row.handoff_id,
        "run_id": row.run_id,
        "from_agent": row.from_agent,
        "to_agent": row.to_agent,
        "handoff_type": row.handoff_type,
        "snapshot_id": row.snapshot_id,
        "projection_id": row.projection_id,
        "delta_tokens": row.delta_tokens,
        "summary": row.summary,
        "delta": _jload(row.delta_json, {}),
        "payload": _jload(row.payload_json, {}),
        "created_at": row.created_at.isoformat(),
    }


def summarize_context_runtime(projections: list[ContextProjectionEvent], writes: list[ContextWriteMetricEvent], handoffs: list[HandoffDeltaEvent]) -> dict[str, Any]:
    projection_count = len(projections)
    cache_hits = sum(1 for row in projections if row.cache_hit)
    total_compile = sum(int(row.compile_ms or 0) for row in projections)
    total_context_tokens = sum(int(row.context_tokens or 0) for row in projections)
    total_delta_tokens = sum(int(row.delta_tokens or 0) for row in handoffs)
    total_write_ms = sum(int(row.operation_append_ms or 0) for row in writes)
    total_committed = sum(int(row.committed or 0) for row in writes)
    total_proposals = sum(int(row.proposals or 0) for row in writes)
    total_conflicts = sum(int(row.conflicts or 0) for row in writes)
    by_role: dict[str, int] = {}
    by_task: dict[str, int] = {}
    for row in projections:
        if row.role_id:
            by_role[row.role_id] = by_role.get(row.role_id, 0) + 1
        if row.task_type:
            by_task[row.task_type] = by_task.get(row.task_type, 0) + 1
    return {
        "kind": "context_runtime_summary_v1",
        "projection_count": projection_count,
        "projection_cache_hit_rate": round(cache_hits / projection_count, 4) if projection_count else 0.0,
        "avg_compile_ms": round(total_compile / projection_count, 2) if projection_count else 0.0,
        "total_context_tokens": total_context_tokens,
        "avg_context_tokens": round(total_context_tokens / projection_count, 2) if projection_count else 0.0,
        "handoff_count": len(handoffs),
        "total_handoff_delta_tokens": total_delta_tokens,
        "avg_handoff_delta_tokens": round(total_delta_tokens / len(handoffs), 2) if handoffs else 0.0,
        "write_batch_count": len(writes),
        "committed_writes": total_committed,
        "proposal_writes": total_proposals,
        "conflict_writes": total_conflicts,
        "avg_operation_append_ms": round(total_write_ms / len(writes), 2) if writes else 0.0,
        "by_role": by_role,
        "by_task_type": by_task,
    }


def list_context_runtime(session: Session, thread: Thread, *, run_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    clean_run = _clean(run_id) or None
    max_rows = max(1, min(int(limit or 100), 1000))
    projection_stmt = select(ContextProjectionEvent).where(ContextProjectionEvent.thread_id == thread.id)
    write_stmt = select(ContextWriteMetricEvent).where(ContextWriteMetricEvent.thread_id == thread.id)
    handoff_stmt = select(HandoffDeltaEvent).where(HandoffDeltaEvent.thread_id == thread.id)
    if clean_run:
        projection_stmt = projection_stmt.where(ContextProjectionEvent.run_id == clean_run)
        write_stmt = write_stmt.where(ContextWriteMetricEvent.run_id == clean_run)
        handoff_stmt = handoff_stmt.where(HandoffDeltaEvent.run_id == clean_run)
    projections = list(session.exec(projection_stmt.order_by(ContextProjectionEvent.created_at.desc()).limit(max_rows)))
    writes = list(session.exec(write_stmt.order_by(ContextWriteMetricEvent.created_at.desc()).limit(max_rows)))
    handoffs = list(session.exec(handoff_stmt.order_by(HandoffDeltaEvent.created_at.desc()).limit(max_rows)))
    return {
        "ok": True,
        "kind": "context_runtime_view_v1",
        "thread_id": thread.id,
        "run_id": clean_run,
        "summary": summarize_context_runtime(projections, writes, handoffs),
        "projections": [_projection_to_dict(row) for row in projections],
        "write_metrics": [_write_to_dict(row) for row in writes],
        "handoffs": [_handoff_to_dict(row) for row in handoffs],
    }


def _extract_projection_events(body: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("projection_events", "context_projection_events", "projections"):
        if isinstance(body.get(key), list):
            return [row for row in body.get(key) if isinstance(row, dict)]
    if isinstance(body.get("projection"), dict):
        return [body.get("projection")]
    if _clean(body.get("projection_id")) or _clean(body.get("kind")) == "context_projection_metric_v1":
        return [body]
    return []


def _extract_write_metrics(body: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("write_metrics", "context_write_metrics", "writes"):
        if isinstance(body.get(key), list):
            return [row for row in body.get(key) if isinstance(row, dict)]
    if isinstance(body.get("write_metric"), dict):
        return [body.get("write_metric")]
    if _clean(body.get("kind")) == "context_write_metric_v1" or _clean(body.get("batch_id")):
        return [body]
    return []


def _extract_handoffs(body: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("handoff_deltas", "handoffs", "handoff_events"):
        if isinstance(body.get(key), list):
            rows.extend(row for row in body.get(key) if isinstance(row, dict))
    for key in ("handoff_metrics", "context_handoff_metrics"):
        if isinstance(body.get(key), list):
            rows.extend(row for row in body.get(key) if isinstance(row, dict))
    if isinstance(body.get("handoff"), dict):
        rows.append(body.get("handoff"))
    if _clean(body.get("handoff_id")) or _clean(body.get("kind")) in {"agent_handoff_delta_v1", "context_handoff_metric_v1"}:
        rows.append(body)
    return rows


def upsert_context_runtime(session: Session, thread: Thread, body: dict[str, Any], *, source: str = "ddalggak") -> dict[str, Any]:
    run_id = _clean(body.get("run_id")) or None
    saved_projections: list[ContextProjectionEvent] = []
    saved_writes: list[ContextWriteMetricEvent] = []
    saved_handoffs: list[HandoffDeltaEvent] = []

    for raw in _extract_projection_events(body):
        proj_id = _clean(raw.get("projection_id")) or _stable_id("proj", raw)
        existing = session.exec(select(ContextProjectionEvent).where(ContextProjectionEvent.thread_id == thread.id).where(ContextProjectionEvent.projection_id == proj_id)).first()
        row_data = {
            "thread_id": thread.id,
            "run_id": _clean(raw.get("run_id")) or run_id,
            "projection_id": proj_id,
            "snapshot_id": _clean(raw.get("snapshot_id")),
            "agent_id": _clean(raw.get("agent_id")),
            "role_id": _clean(raw.get("role_id") or raw.get("role")),
            "task_type": _clean(raw.get("task_type")),
            "model_node": _clean(raw.get("model_node")),
            "cache_hit": _bool(raw.get("cache_hit")),
            "compile_ms": _int(raw.get("compile_ms")),
            "context_tokens": _int(raw.get("context_tokens") or raw.get("compiled_tokens") or raw.get("token_estimate")),
            "selected_atom_count": _int(raw.get("selected_atom_count")),
            "selected_link_count": _int(raw.get("selected_link_count")),
            "handoff_count": _int(raw.get("handoff_count")),
            "goal_hash": _clean(raw.get("goal_hash")),
            "payload_json": _jdump({**raw, "source": source}),
            "created_at": _parse_dt(raw.get("timestamp") or raw.get("created_at")),
            "ingested_at": utcnow(),
        }
        if existing:
            for key, value in row_data.items():
                setattr(existing, key, value)
            saved_projections.append(existing)
        else:
            row = ContextProjectionEvent(**row_data)
            session.add(row)
            saved_projections.append(row)

    for raw in _extract_write_metrics(body):
        event_id = _clean(raw.get("event_id") or raw.get("id") or raw.get("batch_id")) or _stable_id("write", raw)
        existing = session.exec(select(ContextWriteMetricEvent).where(ContextWriteMetricEvent.thread_id == thread.id).where(ContextWriteMetricEvent.event_id == event_id)).first()
        row_data = {
            "thread_id": thread.id,
            "run_id": _clean(raw.get("run_id")) or run_id,
            "event_id": event_id,
            "projection_id": _clean(raw.get("projection_id")),
            "snapshot_id": _clean(raw.get("snapshot_id")),
            "status": _clean(raw.get("status")),
            "batch_size": _int(raw.get("batch_size") or raw.get("write_intent_batch_size") or raw.get("total")),
            "committed": _int(raw.get("committed")),
            "proposals": _int(raw.get("proposals")),
            "conflicts": _int(raw.get("conflicts")),
            "operation_append_ms": _int(raw.get("operation_append_ms") or raw.get("append_ms")),
            "payload_json": _jdump({**raw, "source": source}),
            "created_at": _parse_dt(raw.get("timestamp") or raw.get("created_at")),
            "ingested_at": utcnow(),
        }
        if existing:
            for key, value in row_data.items():
                setattr(existing, key, value)
            saved_writes.append(existing)
        else:
            row = ContextWriteMetricEvent(**row_data)
            session.add(row)
            saved_writes.append(row)

    for raw in _extract_handoffs(body):
        delta = raw.get("delta") if isinstance(raw.get("delta"), dict) else {}
        handoff_id = _clean(raw.get("handoff_id") or raw.get("id")) or _stable_id("handoff", raw)
        existing = session.exec(select(HandoffDeltaEvent).where(HandoffDeltaEvent.thread_id == thread.id).where(HandoffDeltaEvent.handoff_id == handoff_id)).first()
        row_data = {
            "thread_id": thread.id,
            "run_id": _clean(raw.get("run_id")) or run_id,
            "handoff_id": handoff_id,
            "from_agent": _clean(raw.get("from_agent") or raw.get("from")),
            "to_agent": _clean(raw.get("to_agent") or raw.get("to")),
            "handoff_type": _clean(raw.get("handoff_type") or raw.get("type") or "agent_delta"),
            "snapshot_id": _clean(raw.get("snapshot_id")),
            "projection_id": _clean(raw.get("projection_id") or delta.get("projection_id")),
            "delta_tokens": _int(raw.get("delta_tokens")),
            "summary": _clean(raw.get("summary") or delta.get("output_summary")),
            "delta_json": _jdump(delta),
            "payload_json": _jdump({**raw, "source": source}),
            "created_at": _parse_dt(raw.get("timestamp") or raw.get("created_at")),
            "ingested_at": utcnow(),
        }
        if existing:
            for key, value in row_data.items():
                setattr(existing, key, value)
            saved_handoffs.append(existing)
        else:
            row = HandoffDeltaEvent(**row_data)
            session.add(row)
            saved_handoffs.append(row)

    session.commit()
    return {
        "ok": True,
        "kind": "context_runtime_ingest_result_v1",
        "source": source,
        "projections_upserted": len(saved_projections),
        "write_metrics_upserted": len(saved_writes),
        "handoffs_upserted": len(saved_handoffs),
        "summary": summarize_context_runtime(saved_projections, saved_writes, saved_handoffs),
    }
