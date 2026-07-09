from __future__ import annotations
import json, re
from datetime import datetime, timezone
from typing import Any
from sqlmodel import Session, select
from app.models import RuntimeCommit, RuntimeProposal, Thread
from app.services.memory_review import build_review_queue
from app.services.canonical_projection import build_projection_payload

CLOSED_STATUSES = {"committed", "auto_committed", "approved", "rejected", "stale", "superseded"}
ACTION_STATUS = {
    "approve": "approved",
    "approved": "approved",
    "reject": "rejected",
    "rejected": "rejected",
    "mark_stale": "stale",
    "stale": "stale",
    "needs_evidence": "needs_evidence",
    "request_evidence": "needs_evidence",
    "trial": "trial_requested",
    "start_trial": "trial_requested",
    "request_trial": "trial_requested",
    "rollback": "rollback_requested",
    "request_rollback": "rollback_requested",
    "commit": "committed",
    "auto_commit": "auto_committed",
    "promote": "approved",
    "merge": "approved",
    "reopen": "pending_review",
}

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _clean(value: Any = "") -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()

def _detect_language(value: Any = "") -> str:
    text = _clean(value)
    if not text:
        return "ko"
    hangul = len(re.findall(r"[가-힣]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if hangul >= 2 and hangul >= max(2, int(latin * 0.15)):
        return "ko"
    if latin >= 8 and hangul == 0:
        return "en"
    if latin >= 12 and latin > hangul * 3:
        return "en"
    return "ko"

def _language_payload(row: dict[str, Any], summary: str, *, object_type: str = "proposal") -> dict[str, Any]:
    return build_projection_payload(row, object_type=object_type, summary=summary)

def _safe_kind(value: Any = "") -> str:
    kind = re.sub(r"[^a-z0-9_:-]+", "_", _clean(value).lower()).strip("_")
    return kind or "memory_candidate"

def _loads(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return fallback

def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)

def _hash(value: str) -> int:
    h = 0
    for ch in value:
        h = ((h << 5) - h + ord(ch)) & 0xFFFFFFFF
    return h

def _risk(value: Any = "") -> str:
    risk = _clean(value).lower()
    return risk if risk in {"low", "medium", "high", "critical"} else "medium"

def _status(value: Any = "") -> str:
    status = _clean(value).lower()
    return status if status in {"pending_review", "review_required", "needs_evidence", "candidate", "trial_requested", "rollback_requested", "approved", "rejected", "stale", "committed", "auto_committed", "superseded", "blocked"} else "pending_review"

def _normalize_proposal(raw: dict[str, Any], *, source: str = "runtime", run_id: str | None = None) -> dict[str, Any]:
    row = raw if isinstance(raw, dict) else {}
    kind = _safe_kind(row.get("proposal_kind") or row.get("kind_label") or row.get("kind") or row.get("type") or "memory_candidate")
    title = _clean(row.get("title") or kind.replace("_", " "))
    summary = _clean(row.get("summary") or row.get("text") or row.get("claim") or row.get("description") or title)
    source_value = _clean(row.get("source") or source or "runtime")
    source_id = _clean(row.get("source_id") or row.get("sourceId") or "")
    proposal_id = _clean(row.get("proposal_id") or row.get("proposalId") or row.get("id"))
    if not proposal_id:
        proposal_id = f"proposal_{kind}_{_hash('|'.join([kind, title, summary, source_value, source_id])):x}"
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    evidence = row.get("evidence") if isinstance(row.get("evidence"), list) else []
    language = _language_payload(row, summary, object_type=kind)
    return {
        "proposal_id": proposal_id,
        "proposal_kind": kind,
        "title": title,
        "summary": summary,
        **language,
        "risk": _risk(row.get("risk")),
        "status": _status(row.get("status")),
        "source": source_value,
        "source_id": source_id,
        "run_id": _clean(row.get("run_id") or row.get("runId") or run_id or "") or None,
        "recommended_action": _clean(row.get("recommended_action") or row.get("action") or "review_in_goc"),
        "evidence_status": _clean(row.get("evidence_status") or row.get("evidenceStatus") or payload.get("evidence_status") or ""),
        "proposal_json": {**row, "payload": payload, "evidence": evidence},
    }

def _proposal_read(row: RuntimeProposal) -> dict[str, Any]:
    payload = _loads(row.proposal_json, {})
    return {
        "id": row.id,
        "proposal_id": row.proposal_id,
        "kind": row.proposal_kind,
        "proposal_kind": row.proposal_kind,
        "title": row.title,
        "summary": row.summary,
        "source_original_text": row.source_original_text,
        "source_original_language": row.source_original_language,
        "display_text": row.display_text,
        "canonical_language": row.canonical_language,
        "canonical_text_en": row.canonical_text_en,
        "canonical_projection_status": row.canonical_projection_status,
        "canonical_projection_id": row.canonical_projection_id,
        "projection_method": row.projection_method,
        "projection_confidence": row.projection_confidence,
        "user_surface_locale": row.user_surface_locale,
        "risk": row.risk,
        "status": row.status,
        "source": row.source,
        "source_id": row.source_id,
        "run_id": row.run_id,
        "recommended_action": row.recommended_action,
        "evidence_status": row.evidence_status,
        "payload": payload.get("payload") if isinstance(payload, dict) else {},
        "evidence": payload.get("evidence") if isinstance(payload, dict) and isinstance(payload.get("evidence"), list) else [],
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }

def summarize_proposals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for row in rows:
        status = _status(row.get("status"))
        kind = _safe_kind(row.get("proposal_kind") or row.get("kind"))
        by_status[status] = by_status.get(status, 0) + 1
        by_kind[kind] = by_kind.get(kind, 0) + 1
    return {
        "proposal_count": len(rows),
        "pending_review_count": len([r for r in rows if _status(r.get("status")) in {"pending_review", "review_required", "needs_evidence", "candidate"}]),
        "high_risk_count": len([r for r in rows if _risk(r.get("risk")) in {"high", "critical"}]),
        "by_status": by_status,
        "by_kind": by_kind,
    }

def upsert_runtime_proposals(session: Session, thread: Thread, proposals: list[dict[str, Any]], *, source: str = "runtime", run_id: str | None = None) -> dict[str, Any]:
    saved: list[dict[str, Any]] = []
    created = 0
    updated = 0
    for raw in proposals:
        p = _normalize_proposal(raw, source=source, run_id=run_id)
        existing = session.exec(select(RuntimeProposal).where(RuntimeProposal.thread_id == thread.id, RuntimeProposal.proposal_id == p["proposal_id"]).limit(1)).first()
        if existing:
            updated += 1
            existing.proposal_kind = p["proposal_kind"] or existing.proposal_kind
            existing.title = p["title"] or existing.title
            existing.summary = p["summary"] or existing.summary
            existing.source_original_text = p["source_original_text"] or existing.source_original_text
            existing.source_original_language = p["source_original_language"] or existing.source_original_language
            existing.display_text = p["display_text"] or existing.display_text
            existing.canonical_language = p["canonical_language"] or existing.canonical_language
            existing.canonical_text_en = p["canonical_text_en"] or existing.canonical_text_en
            existing.canonical_projection_status = p["canonical_projection_status"] or existing.canonical_projection_status
            existing.canonical_projection_id = p.get("canonical_projection_id") or existing.canonical_projection_id
            existing.projection_method = p.get("projection_method") or existing.projection_method
            existing.projection_confidence = float(p.get("projection_confidence") or existing.projection_confidence or 0.0)
            existing.user_surface_locale = p["user_surface_locale"] or existing.user_surface_locale
            existing.risk = p["risk"] or existing.risk
            if existing.status not in CLOSED_STATUSES:
                existing.status = p["status"] or existing.status
            existing.source = p["source"] or existing.source
            existing.source_id = p["source_id"] or existing.source_id
            existing.run_id = p["run_id"] or existing.run_id
            existing.recommended_action = p["recommended_action"] or existing.recommended_action
            existing.evidence_status = p["evidence_status"] or existing.evidence_status
            existing.proposal_json = _dumps(p["proposal_json"])
            existing.updated_at = _now()
            row = existing
        else:
            created += 1
            row = RuntimeProposal(
                thread_id=thread.id,
                run_id=p["run_id"],
                proposal_id=p["proposal_id"],
                proposal_kind=p["proposal_kind"],
                title=p["title"],
                summary=p["summary"],
                source_original_text=p["source_original_text"],
                source_original_language=p["source_original_language"],
                display_text=p["display_text"],
                canonical_language=p["canonical_language"],
                canonical_text_en=p["canonical_text_en"],
                canonical_projection_status=p["canonical_projection_status"],
                canonical_projection_id=p.get("canonical_projection_id") or "",
                projection_method=p.get("projection_method") or "",
                projection_confidence=float(p.get("projection_confidence") or 0.0),
                user_surface_locale=p["user_surface_locale"],
                risk=p["risk"],
                status=p["status"],
                source=p["source"],
                source_id=p["source_id"],
                recommended_action=p["recommended_action"],
                evidence_status=p["evidence_status"],
                proposal_json=_dumps(p["proposal_json"]),
            )
            session.add(row)
        saved.append(_proposal_read(row))
    session.commit()
    for row in saved:
        # updated rows need fresh timestamps after commit, but the important stable fields are already present.
        pass
    return {"ok": True, "created": created, "updated": updated, "summary": summarize_proposals(saved), "proposals": saved}

def list_runtime_proposals(session: Session, thread: Thread, *, status: str | None = None, kind: str | None = None, include_closed: bool = False, limit: int = 100) -> dict[str, Any]:
    stmt = select(RuntimeProposal).where(RuntimeProposal.thread_id == thread.id)
    if status:
        stmt = stmt.where(RuntimeProposal.status == _status(status))
    if kind:
        stmt = stmt.where(RuntimeProposal.proposal_kind == _safe_kind(kind))
    stmt = stmt.order_by(RuntimeProposal.updated_at.desc()).limit(max(1, min(int(limit or 100), 500)))
    rows = [_proposal_read(r) for r in session.exec(stmt).all()]
    if not include_closed:
        rows = [r for r in rows if _status(r.get("status")) not in CLOSED_STATUSES]
    return {"ok": True, "kind": "runtime_proposal_list", "generated_at": _now().isoformat(), "summary": summarize_proposals(rows), "proposals": rows}

def apply_runtime_proposal_action(session: Session, thread: Thread, proposal_id: str, body: dict[str, Any]) -> dict[str, Any]:
    proposal_id = _clean(proposal_id)
    row = session.exec(select(RuntimeProposal).where(RuntimeProposal.thread_id == thread.id, RuntimeProposal.proposal_id == proposal_id).limit(1)).first()
    if not row:
        raise ValueError("proposal not found")
    action = _clean((body or {}).get("action") or (body or {}).get("status") or "approve").lower()
    next_status = ACTION_STATUS.get(action)
    if not next_status:
        raise ValueError(f"unsupported proposal action: {action}")
    reason = _clean((body or {}).get("reason") or "")
    actor = _clean((body or {}).get("actor") or "goc")
    previous = row.status
    row.status = next_status
    row.updated_at = _now()
    payload = {"proposal": _proposal_read(row), "previous_status": previous, "body": body or {}}
    event = RuntimeCommit(thread_id=thread.id, proposal_id=row.proposal_id, action=action, status=next_status, actor=actor, reason=reason, commit_json=_dumps(payload))
    session.add(event)
    session.add(row)
    session.commit()
    session.refresh(row)
    session.refresh(event)
    return {"ok": True, "proposal": _proposal_read(row), "event": {"id": event.id, "proposal_id": event.proposal_id, "action": event.action, "status": event.status, "actor": event.actor, "reason": event.reason, "created_at": event.created_at.isoformat()}}

def build_review_inbox(session: Session, thread: Thread, *, include_detected: bool = True, limit: int = 100) -> dict[str, Any]:
    persisted = list_runtime_proposals(session, thread, include_closed=False, limit=limit).get("proposals") or []
    by_id = {p.get("proposal_id"): p for p in persisted if p.get("proposal_id")}
    detected_summary: dict[str, Any] = {}
    if include_detected:
        try:
            detected = build_review_queue(session, thread)
            detected_summary = detected.get("summary") or {}
            for raw in detected.get("proposals") or []:
                p = _normalize_proposal(raw, source="memory_review")
                if p["proposal_id"] in by_id:
                    continue
                by_id[p["proposal_id"]] = {
                    "proposal_id": p["proposal_id"],
                    "kind": p["proposal_kind"],
                    "proposal_kind": p["proposal_kind"],
                    "title": p["title"],
                    "summary": p["summary"],
                    "risk": p["risk"],
                    "status": p["status"],
                    "source": p["source"],
                    "source_id": p["source_id"],
                    "run_id": p["run_id"],
                    "recommended_action": p["recommended_action"],
                    "evidence_status": p["evidence_status"],
                    "source_original_text": p["source_original_text"],
                    "source_original_language": p["source_original_language"],
                    "display_text": p["display_text"],
                    "canonical_language": p["canonical_language"],
                    "canonical_text_en": p["canonical_text_en"],
                    "canonical_projection_status": p["canonical_projection_status"],
                    "canonical_projection_id": p.get("canonical_projection_id", ""),
                    "projection_method": p.get("projection_method", ""),
                    "projection_confidence": p.get("projection_confidence", 0.0),
                    "user_surface_locale": p["user_surface_locale"],
                    "payload": p["proposal_json"].get("payload") if isinstance(p["proposal_json"], dict) else {},
                    "evidence": p["proposal_json"].get("evidence") if isinstance(p["proposal_json"], dict) else [],
                    "created_at": _now().isoformat(),
                    "updated_at": _now().isoformat(),
                    "ephemeral_detected": True,
                }
        except Exception as exc:
            detected_summary = {"error": str(exc)}
    rows = list(by_id.values())
    rows.sort(key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""), reverse=True)
    rows = rows[: max(1, min(int(limit or 100), 500))]
    return {
        "ok": True,
        "kind": "goc_review_inbox",
        "generated_at": _now().isoformat(),
        "summary": summarize_proposals(rows),
        "persisted_summary": summarize_proposals(persisted),
        "detected_summary": detected_summary,
        "proposals": rows,
        "policy": {
            "principle": "Agent proposes. Runtime commits. GoC reviews.",
            "actions": ["approve", "reject", "trial", "rollback", "mark_stale", "needs_evidence", "commit", "promote", "merge", "reopen"],
            "safe_defaults": ["learned rules remain candidates", "unsupported claims need evidence", "shadow modules are not canonical", "trials are reversible", "write skills require approval"],
        },
    }
