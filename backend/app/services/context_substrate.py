from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models import ContextSubstrateOperation, ContextSubstrateSnapshot, Thread, utcnow


def _jdump(value: Any) -> str:
    try:
        return json.dumps(value if value is not None else {}, ensure_ascii=False)
    except Exception:
        return "{}"


def _jload(value: str, default: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return default


def _clean(value: Any) -> str:
    return str(value or "").strip()


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


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _operation_to_dict(row: ContextSubstrateOperation) -> dict[str, Any]:
    payload = _jload(row.operation_json, {})
    return {
        "id": row.id,
        "operation_id": row.operation_id,
        "op": row.op,
        "version": row.version,
        "status": row.status,
        "lane": row.lane,
        "commit_mode": row.commit_mode,
        "actor": row.actor,
        "run_id": row.run_id,
        "created_at": row.created_at.isoformat(),
        "operation": payload,
    }


def _snapshot_to_dict(row: ContextSubstrateSnapshot) -> dict[str, Any]:
    manifest = _jload(row.manifest_json, {})
    snapshot = _jload(row.snapshot_json, {})
    return {
        "id": row.id,
        "snapshot_id": row.snapshot_id,
        "version": row.version,
        "atom_count": row.atom_count,
        "link_count": row.link_count,
        "run_id": row.run_id,
        "created_at": row.created_at.isoformat(),
        "manifest": manifest,
        "snapshot": snapshot,
    }


def summarize_context_substrate(snapshots: list[ContextSubstrateSnapshot], operations: list[ContextSubstrateOperation]) -> dict[str, Any]:
    latest = snapshots[0] if snapshots else None
    status_counts: dict[str, int] = {}
    lane_counts: dict[str, int] = {}
    for op in operations:
        status_counts[op.status] = status_counts.get(op.status, 0) + 1
        lane_counts[op.lane] = lane_counts.get(op.lane, 0) + 1
    return {
        "kind": "context_substrate_summary_v1",
        "snapshot_count": len(snapshots),
        "operation_count": len(operations),
        "latest_snapshot_id": latest.snapshot_id if latest else None,
        "latest_version": latest.version if latest else 0,
        "atom_count": latest.atom_count if latest else 0,
        "link_count": latest.link_count if latest else 0,
        "status_counts": status_counts,
        "lane_counts": lane_counts,
    }


def list_context_substrate(session: Session, thread: Thread, *, run_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    clean_run = _clean(run_id) or None
    max_rows = max(1, min(int(limit or 100), 1000))
    snap_stmt = select(ContextSubstrateSnapshot).where(ContextSubstrateSnapshot.thread_id == thread.id)
    op_stmt = select(ContextSubstrateOperation).where(ContextSubstrateOperation.thread_id == thread.id)
    if clean_run:
        snap_stmt = snap_stmt.where(ContextSubstrateSnapshot.run_id == clean_run)
        op_stmt = op_stmt.where(ContextSubstrateOperation.run_id == clean_run)
    snapshots = list(session.exec(snap_stmt.order_by(ContextSubstrateSnapshot.version.desc()).limit(max_rows)))
    operations = list(session.exec(op_stmt.order_by(ContextSubstrateOperation.version.desc(), ContextSubstrateOperation.created_at.desc()).limit(max_rows)))
    return {
        "ok": True,
        "kind": "context_substrate_view_v1",
        "thread_id": thread.id,
        "summary": summarize_context_substrate(snapshots, operations),
        "snapshots": [_snapshot_to_dict(row) for row in snapshots],
        "operations": [_operation_to_dict(row) for row in operations],
    }


def _extract_operations(body: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(body.get("operations"), list):
        return [row for row in body.get("operations") if isinstance(row, dict)]
    if isinstance(body.get("operation"), dict):
        return [body.get("operation")]
    if _clean(body.get("op") or body.get("operation_id") or body.get("id")):
        return [body]
    return []


def _extract_snapshots(body: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(body.get("snapshots"), list):
        return [row for row in body.get("snapshots") if isinstance(row, dict)]
    if isinstance(body.get("snapshot"), dict):
        return [body.get("snapshot")]
    if _clean(body.get("snapshot_id")):
        return [body]
    return []


def upsert_context_substrate(session: Session, thread: Thread, body: dict[str, Any], *, source: str = "ddalggak") -> dict[str, Any]:
    run_id = _clean(body.get("run_id")) or None
    saved_operations: list[ContextSubstrateOperation] = []
    saved_snapshots: list[ContextSubstrateSnapshot] = []

    for raw in _extract_operations(body):
        op_id = _clean(raw.get("operation_id") or raw.get("id")) or f"op_{len(saved_operations) + 1}"
        existing = session.exec(select(ContextSubstrateOperation).where(ContextSubstrateOperation.thread_id == thread.id).where(ContextSubstrateOperation.operation_id == op_id)).first()
        row_data = {
            "thread_id": thread.id,
            "run_id": _clean(raw.get("run_id")) or run_id,
            "operation_id": op_id,
            "op": _clean(raw.get("op") or raw.get("operation") or "operation"),
            "version": int(raw.get("version") or 0),
            "status": _clean(raw.get("status") or "committed"),
            "lane": _clean(raw.get("lane") or "normal"),
            "commit_mode": _clean(raw.get("commit_mode") or "auto"),
            "actor": _clean(raw.get("actor") or "runtime"),
            "operation_json": _jdump(raw),
            "created_at": _parse_dt(raw.get("timestamp") or raw.get("created_at")),
            "ingested_at": utcnow(),
        }
        if existing:
            for key, value in row_data.items():
                setattr(existing, key, value)
            saved_operations.append(existing)
        else:
            row = ContextSubstrateOperation(**row_data)
            session.add(row)
            saved_operations.append(row)

    for raw in _extract_snapshots(body):
        snapshot_id = _clean(raw.get("snapshot_id") or raw.get("id")) or "ctx_000000"
        existing = session.exec(select(ContextSubstrateSnapshot).where(ContextSubstrateSnapshot.thread_id == thread.id).where(ContextSubstrateSnapshot.snapshot_id == snapshot_id)).first()
        atoms = _as_list(raw.get("atoms"))
        links = _as_list(raw.get("links"))
        manifest = body.get("manifest") if isinstance(body.get("manifest"), dict) else raw.get("manifest") if isinstance(raw.get("manifest"), dict) else {}
        row_data = {
            "thread_id": thread.id,
            "run_id": _clean(raw.get("run_id")) or run_id,
            "snapshot_id": snapshot_id,
            "version": int(raw.get("version") or manifest.get("latest_version") or 0),
            "atom_count": int(raw.get("atom_count") or len(atoms) or manifest.get("atom_count") or 0),
            "link_count": int(raw.get("link_count") or len(links) or manifest.get("link_count") or 0),
            "manifest_json": _jdump(manifest),
            "snapshot_json": _jdump(raw),
            "created_at": _parse_dt(raw.get("created_at")),
            "ingested_at": utcnow(),
        }
        if existing:
            for key, value in row_data.items():
                setattr(existing, key, value)
            saved_snapshots.append(existing)
        else:
            row = ContextSubstrateSnapshot(**row_data)
            session.add(row)
            saved_snapshots.append(row)

    session.commit()
    return {
        "ok": True,
        "kind": "context_substrate_ingest_result_v1",
        "source": source,
        "snapshots_upserted": len(saved_snapshots),
        "operations_upserted": len(saved_operations),
        "summary": summarize_context_substrate(saved_snapshots, saved_operations),
    }
