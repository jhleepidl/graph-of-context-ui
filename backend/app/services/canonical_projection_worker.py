from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from sqlmodel import Session, select

from app.models import RuntimeProposal, Thread
from app.services.canonical_projection import build_local_projection
from app.services.proposals import list_runtime_proposals


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(value: Any = "", max_len: int = 12000) -> str:
    return " ".join(str(value or "").split())[:max_len]


def build_projection_worker_prompt(rows: list[RuntimeProposal]) -> str:
    items = [
        {
            "projection_id": row.canonical_projection_id,
            "proposal_id": row.proposal_id,
            "object_type": row.proposal_kind,
            "original_language": row.source_original_language,
            "text_original": _clean(row.source_original_text or row.summary, 1200),
        }
        for row in rows
    ]
    return "\n".join([
        "You are a canonical projection worker for Graph-of-Context.",
        "Convert each source item into concise English canonical text for internal routing, policy matching, and semantic indexing.",
        "Do not overwrite original text. Preserve negations, approval boundaries, stop conditions, dates, identifiers, and risk constraints.",
        "Return JSON only: {\"projections\":[{\"projection_id\":\"...\",\"canonical_text_en\":\"...\",\"confidence\":0.0-1.0}]}",
        str({"items": items}),
    ])


def _projection_by_id(updates: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in updates or []:
        if not isinstance(row, dict):
            continue
        pid = _clean(row.get("projection_id") or row.get("projectionId") or row.get("canonical_projection_id") or "", 300)
        if pid:
            out[pid] = row
    return out


def process_runtime_proposal_projections(
    session: Session,
    thread: Thread,
    *,
    projections: list[dict[str, Any]] | None = None,
    limit: int = 50,
    actor: str = "goc_projection_worker",
    allow_local_retry: bool = True,
) -> dict[str, Any]:
    stmt = (
        select(RuntimeProposal)
        .where(RuntimeProposal.thread_id == thread.id)
        .where(RuntimeProposal.canonical_projection_status == "pending_model_projection")
        .order_by(RuntimeProposal.updated_at.asc())
        .limit(max(1, min(int(limit or 50), 500)))
    )
    rows = list(session.exec(stmt).all())
    updates = _projection_by_id(projections or [])
    processed: list[dict[str, Any]] = []
    ready = 0
    skipped = 0
    for row in rows:
        update = updates.get(row.canonical_projection_id) or updates.get(row.proposal_id) or {}
        canonical = _clean(update.get("canonical_text_en") or update.get("canonicalTextEn") or update.get("text") or "")
        method = _clean(update.get("projection_method") or update.get("method") or "model_projection", 80)
        confidence_raw = update.get("confidence", update.get("projection_confidence", 0.85))
        try:
            confidence = float(confidence_raw)
        except Exception:
            confidence = 0.85
        if not canonical and allow_local_retry:
            local = build_local_projection(row.source_original_text or row.summary, original_language=row.source_original_language, object_type=row.proposal_kind)
            canonical = _clean(local.get("canonical_text_en") or "")
            method = _clean(local.get("projection_method") or "local_projection_retry", 80)
            confidence = float(local.get("projection_confidence") or 0.0)
        if not canonical:
            skipped += 1
            processed.append({"proposal_id": row.proposal_id, "projection_id": row.canonical_projection_id, "status": "pending_model_projection", "ok": False})
            continue
        row.canonical_text_en = canonical
        row.canonical_projection_status = "ready"
        row.projection_method = method or "model_projection"
        row.projection_confidence = max(0.0, min(1.0, confidence))
        row.updated_at = _now()
        session.add(row)
        ready += 1
        processed.append({"proposal_id": row.proposal_id, "projection_id": row.canonical_projection_id, "status": "ready", "ok": True, "method": row.projection_method})
    if ready:
        session.commit()
    return {
        "ok": True,
        "worker": "canonical_projection_worker_v1",
        "actor": actor,
        "processed_count": len(processed),
        "ready_count": ready,
        "skipped_count": skipped,
        "processed": processed,
        "prompt": build_projection_worker_prompt(rows),
        "inbox": list_runtime_proposals(session, thread, include_closed=False, limit=limit),
    }
