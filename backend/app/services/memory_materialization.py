from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models import MemoryDemandEvent, MemoryMaterializationCandidate, MemoryModule, MemoryModuleRow, MemoryTopologySnapshot, Node, Thread


def _clean(value: Any = "") -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _loads(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return fallback


def _clip(value: Any = "", max_len: int = 220) -> str:
    text = _clean(value)
    return text if len(text) <= max_len else text[: max_len - 1].strip() + "…"


GENERIC_SHAPE_SPECS: list[dict[str, Any]] = [
    {
        "id": "time_series",
        "title": "Time-series memory",
        "table": "time_series_entries",
        "description": "Repeated temporal observations should become a queryable event series when range, trend, missing-entry, or aggregate questions emerge.",
        "evidence": re.compile(r"아침|점심|저녁|간식|야식|식사|먹었|먹은|메뉴|칼로리|영양|단백질|탄수화물|meal|breakfast|lunch|dinner|snack|ate|diet|food", re.I),
        "aggregate": re.compile(r"이번\s*주|지난\s*주|최근|평균|합계|며칠|추세|비율|빠진|거른|count|average|trend|weekly|monthly|summary", re.I),
        "correction": re.compile(r"아까|수정|정정|아니라|추가|취소|빼줘|update|correct|instead|actually", re.I),
        "columns": [
            {"name": "id", "type": "text", "role": "primary_key"},
            {"name": "occurred_at", "type": "datetime", "nullable": True},
            {"name": "series_key", "type": "text", "nullable": True},
            {"name": "subject", "type": "text", "nullable": True},
            {"name": "value_json", "type": "json", "nullable": True},
            {"name": "notes", "type": "text", "nullable": True},
            {"name": "source_ref", "type": "text", "nullable": False},
            {"name": "confidence", "type": "real", "nullable": False},
            {"name": "status", "type": "text", "default": "active"},
        ],
        "operations": ["add_time_series_entry", "update_time_series_entry", "list_time_series_entries", "summarize_time_series", "detect_missing_time_series_entries"],
        "aliases": ["meal_tracking", "habit_tracking", "metric_tracking"],
    },
    {
        "id": "record_collection",
        "title": "Record collection",
        "table": "memory_records",
        "description": "Repeated similarly shaped records should become a typed collection when filtering, totals, categories, or updates matter.",
        "evidence": re.compile(r"지출|결제|샀|구매|영수증|가격|비용|원\b|달러|카드|현금|expense|spent|bought|cost|receipt|price|paid", re.I),
        "aggregate": re.compile(r"합계|총액|평균|카테고리|이번\s*달|지난\s*달|최근|비율|total|average|category|monthly|weekly", re.I),
        "correction": re.compile(r"환불|취소|정정|수정|아니라|refund|cancel|correct|actually", re.I),
        "columns": [
            {"name": "id", "type": "text", "role": "primary_key"},
            {"name": "recorded_at", "type": "datetime", "nullable": True},
            {"name": "record_type", "type": "text", "nullable": True},
            {"name": "title", "type": "text", "nullable": True},
            {"name": "value_json", "type": "json", "nullable": True},
            {"name": "category", "type": "text", "nullable": True},
            {"name": "notes", "type": "text", "nullable": True},
            {"name": "source_ref", "type": "text"},
            {"name": "confidence", "type": "real"},
            {"name": "status", "type": "text", "default": "active"},
        ],
        "operations": ["add_record", "update_record", "list_records", "summarize_records"],
        "aliases": ["expense_tracking"],
    },
    {
        "id": "source_knowledge_base",
        "title": "Sourced knowledge base",
        "table": "sourced_facts",
        "description": "Reusable public or source-backed facts should become a sourced knowledge pack with provenance and freshness rules instead of private memory.",
        "evidence": re.compile(r"학회|컨퍼런스|ICDE|NeurIPS|ICML|CVPR|SIGMOD|VLDB|deadline|submission|registration|venue|CFP|call for papers|conference", re.I),
        "aggregate": re.compile(r"마감|일정|언제|등록|비자|장소|venue|deadline|date|schedule|fee|registration", re.I),
        "correction": re.compile(r"변경|업데이트|최신|바뀌|update|changed|latest|refresh", re.I),
        "columns": [
            {"name": "id", "type": "text", "role": "primary_key"},
            {"name": "topic_key", "type": "text"},
            {"name": "fact_type", "type": "text"},
            {"name": "title", "type": "text"},
            {"name": "value_json", "type": "json"},
            {"name": "source_url", "type": "text", "nullable": True},
            {"name": "retrieved_at", "type": "datetime", "nullable": True},
            {"name": "freshness_ttl_days", "type": "integer", "default": 14},
            {"name": "confidence", "type": "real"},
        ],
        "operations": ["add_sourced_fact", "list_sourced_facts", "refresh_sourced_facts"],
        "publishable": True,
        "freshness_policy": {"refresh_on_clone": True, "ttl_days": 14, "requires_refresh_for": ["deadlines", "prices/fees", "venues/locations", "policy/API/legal/medical/financial facts"]},
        "aliases": ["conference_knowledge"],
    },
    {
        "id": "task_board",
        "title": "Task board",
        "table": "task_items",
        "description": "Repeated TODOs, ownership, deadlines, and status updates should become a task board when progress and accountability matter.",
        "evidence": re.compile(r"TODO|할\s*일|액션|담당|마감|해야|진행|pending|done|blocked|action item|owner|deadline|task", re.I),
        "aggregate": re.compile(r"남은|완료|상태|마감|담당자별|pending|done|status|overdue|by owner", re.I),
        "correction": re.compile(r"완료|취소|변경|수정|미뤄|done|cancel|update|postpone", re.I),
        "columns": [
            {"name": "id", "type": "text", "role": "primary_key"},
            {"name": "title", "type": "text"},
            {"name": "owner", "type": "text", "nullable": True},
            {"name": "status", "type": "text", "default": "pending"},
            {"name": "due_at", "type": "datetime", "nullable": True},
            {"name": "source_ref", "type": "text"},
            {"name": "confidence", "type": "real"},
        ],
        "operations": ["add_task_item", "update_task_item_status", "list_task_items"],
        "aliases": ["action_item_tracking"],
    },
]


def _node_text(node: Node) -> str:
    payload = _loads(node.payload_json, {})
    parts = [node.text or ""]
    if isinstance(payload, dict):
        parts.extend(str(payload.get(k) or "") for k in ("text", "summary", "query", "content"))
    return _clean(" ".join(parts))


def _evidence(session: Session, thread: Thread) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    nodes = session.exec(select(Node).where(Node.thread_id == thread.id).order_by(Node.created_at.desc()).limit(400)).all()
    for node in reversed(nodes):
        text = _node_text(node)
        if text:
            rows.append({"kind": "node", "source": f"node:{node.id}", "text": text, "created_at": node.created_at.isoformat()})
    meta = _loads(thread.meta_json, {})
    for key in ("memory", "summary", "team_blueprint", "team_config"):
        if key in meta:
            rows.append({"kind": "thread_meta", "source": f"thread.meta_json:{key}", "text": json.dumps(meta.get(key), ensure_ascii=False)})
    return rows


def _demands(session: Session, thread: Thread) -> list[dict[str, Any]]:
    rows = session.exec(select(MemoryDemandEvent).where(MemoryDemandEvent.thread_id == thread.id).order_by(MemoryDemandEvent.created_at.desc()).limit(160)).all()
    out = []
    for row in rows:
        out.append({
            "query": row.query or "",
            "text": _clean(" ".join([row.query or "", row.demand_reasons_json or "", row.sources_json or "", row.source_types_json or "", row.surface_ids_json or ""])),
            "source": f"memory_demand:{row.id}",
        })
    return out


def _latest_topology(session: Session, thread: Thread) -> dict[str, Any]:
    snap = session.exec(select(MemoryTopologySnapshot).where(MemoryTopologySnapshot.thread_id == thread.id).order_by(MemoryTopologySnapshot.created_at.desc()).limit(1)).first()
    if not snap:
        return {}
    payload = _loads(snap.topology_json, {})
    if isinstance(payload, dict):
        payload.setdefault("mode", snap.mode)
        payload.setdefault("state", snap.state)
        return payload
    return {"mode": snap.mode, "state": snap.state}


def _score(spec: dict[str, Any], evidence: list[dict[str, Any]], demands: list[dict[str, Any]]) -> dict[str, Any]:
    ev = [r for r in evidence if spec["evidence"].search(r.get("text") or "")]
    query_rows = [r for r in demands if spec["evidence"].search((r.get("text") or r.get("query") or ""))]
    aggregate_rows = [r for r in demands if spec["aggregate"].search((r.get("text") or r.get("query") or ""))]
    correction_rows = [r for r in evidence if spec["correction"].search(r.get("text") or "")]
    public_rows = [r for r in ev if re.search(r"https?://|official|public|source|url|공식", r.get("text") or "", re.I)]
    repetition = min(1.0, len(ev) / 10)
    query_pressure = min(1.0, (len(query_rows) + len(aggregate_rows) * 1.8) / 6)
    correction_pressure = min(1.0, len(correction_rows) / 5)
    public_pressure = min(1.0, len(public_rows) / 3) if spec.get("publishable") else 0.0
    score = min(1.0, repetition * .42 + query_pressure * .36 + correction_pressure * .14 + public_pressure * .08)
    reasons = []
    if repetition >= .35: reasons.append("repeated_shape_memory")
    if query_pressure >= .25: reasons.append("aggregate_or_range_queries_detected")
    if correction_pressure >= .2: reasons.append("updates_or_retractions_detected")
    if public_pressure >= .2: reasons.append("public_source_knowledge_candidate")
    return {"evidence_rows": ev, "query_rows": query_rows, "aggregate_rows": aggregate_rows, "correction_rows": correction_rows, "public_rows": public_rows, "score": round(score, 3), "reasons": reasons}


def _meal_type(text: str) -> str | None:
    low = text.lower()
    if re.search(r"아침|breakfast", low): return "breakfast"
    if re.search(r"점심|lunch", low): return "lunch"
    if re.search(r"저녁|dinner", low): return "dinner"
    if re.search(r"간식|snack", low): return "snack"
    if "야식" in low: return "late_night"
    return None


def _meal_foods(text: str) -> list[str]:
    raw = _clean(text)
    match = re.search(r"(?:아침|점심|저녁|간식|야식|breakfast|lunch|dinner|snack)[^\n。.!?]*(?:먹었|먹은|ate|had)?([^\n。.!?]*)", raw, re.I)
    fragment = match.group(0) if match else raw
    fragment = re.sub(r"^(아침|점심|저녁|간식|야식|breakfast|lunch|dinner|snack)(은|는|으로|에)?", "", fragment, flags=re.I)
    fragment = re.sub(r"먹었어|먹었다|먹은|먹었|ate|had", "", fragment, flags=re.I)
    fragment = re.sub(r"그리고|랑|와|과|및|plus|and", ",", fragment, flags=re.I)
    return [_clean(x) for x in re.split(r"[,/、，]+", fragment) if _clean(x)][:8]


def _backfill(spec: dict[str, Any], evidence_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if spec["id"] != "meal_tracking":
        return [{"id": f"{spec['id']}_{i+1}", "source_ref": row.get("source"), "preview": _clip(row.get("text"), 180), "confidence": .55, "review_state": "needs_review"} for i, row in enumerate(evidence_rows[:12])]
    rows = []
    for i, row in enumerate(evidence_rows[:80]):
        text = row.get("text") or ""
        meal_type = _meal_type(text)
        foods = _meal_foods(text)
        if not meal_type and not foods:
            continue
        confidence = round(.52 + (.14 if meal_type else 0) + (.18 if foods else 0), 2)
        rows.append({"id": f"meal_preview_{i+1}", "eaten_at": row.get("created_at"), "meal_type": meal_type, "foods": foods, "notes": "" if foods else _clip(text, 180), "source_ref": row.get("source"), "confidence": confidence, "review_state": "high_confidence" if confidence >= .75 else "needs_review"})
    return rows[:24]


def _sql(table: str, columns: list[dict[str, Any]]) -> str:
    safe_table = re.sub(r"[^a-zA-Z0-9_]", "", table)
    defs = []
    for col in columns:
        name = re.sub(r"[^a-zA-Z0-9_]", "", str(col.get("name") or ""))
        if not name:
            continue
        typ = str(col.get("type") or "text").upper()
        flags = []
        if col.get("role") == "primary_key": flags.append("PRIMARY KEY")
        if col.get("nullable") is False: flags.append("NOT NULL")
        defs.append(f"  {name} {typ}{(' ' + ' '.join(flags)) if flags else ''}")
    return "CREATE TABLE IF NOT EXISTS " + safe_table + " (\n" + ",\n".join(defs) + "\n);"


def _recommendation(score: float, backfill_rows: list[dict[str, Any]]) -> str:
    high = len([r for r in backfill_rows if float(r.get("confidence") or 0) >= .75])
    if score >= .72 and high >= 8:
        return "create_shadow_table"
    if score >= .55:
        return "create_typed_jsonl_first"
    if score >= .32:
        return "watch_and_continue_markdown"
    return "no_action"


def _candidate(spec: dict[str, Any], scored: dict[str, Any]) -> dict[str, Any]:
    back = _backfill(spec, scored["evidence_rows"])
    rec = _recommendation(scored["score"], back)
    return {
        "candidate_id": f"{spec['id']}_{int(datetime.now(timezone.utc).timestamp())}",
        "shape_id": spec["id"],
        "domain": spec["id"],
        "legacy_domain_aliases": spec.get("aliases", []),
        "title": spec["title"],
        "description": spec["description"],
        "materialization_score": scored["score"],
        "recommendation": rec,
        "reasons": scored["reasons"],
        "signal_counts": {"evidence": len(scored["evidence_rows"]), "domain_queries": len(scored["query_rows"]), "shape_queries": len(scored["query_rows"]), "aggregate_queries": len(scored["aggregate_rows"]), "corrections": len(scored["correction_rows"]), "public_sources": len(scored["public_rows"])},
        "proposed_store": "sqlite_shadow_table" if rec == "create_shadow_table" else ("typed_jsonl_event_log" if rec == "create_typed_jsonl_first" else "markdown_with_watch"),
        "proposed_schema": {"table": spec["table"], "columns": spec["columns"], "create_table_sql": _sql(spec["table"], spec["columns"])},
        "proposed_operations": [{"name": n, "kind": "runtime_safe_operation"} for n in spec["operations"]],
        "backfill_preview": {"total_candidates": len(back), "high_confidence": len([r for r in back if float(r.get("confidence") or 0) >= .75]), "needs_review": len([r for r in back if float(r.get("confidence") or 0) < .75]), "rows": back[:12]},
        "source_preview": [{"source": r.get("source"), "kind": r.get("kind"), "text": _clip(r.get("text"), 180)} for r in scored["evidence_rows"][:6]],
        "safety": {"safe_automatic_steps": ["candidate_preview", "schema_draft", "backfill_dry_run", "shadow_table_plan"], "approval_required_for": ["canonical_write_path", "raw_memory_deletion", "public_publish", "generated_code_execution"], "generated_code_execution": False, "raw_memory_deletion": False, "canonical_memory_switch": False},
        "publish_policy": ({"publishable_as": "sourced_knowledge_pack", "raw_private_memory_included": False, "freshness_policy": spec.get("freshness_policy", {"refresh_on_clone": True})} if spec.get("publishable") else {"publishable_as": "private_memory_module_only", "raw_private_memory_included": False}),
    }


def build_memory_materialization_preview(session: Session, thread: Thread, *, min_score: float = .28, max_candidates: int = 6) -> dict[str, Any]:
    evidence = _evidence(session, thread)
    demands = _demands(session, thread)
    topology = _latest_topology(session, thread)
    candidates = []
    for spec in GENERIC_SHAPE_SPECS:
        scored = _score(spec, evidence, demands)
        if scored["score"] >= min_score or len(scored["evidence_rows"]) >= 4 or len(scored["aggregate_rows"]) >= 1:
            candidates.append(_candidate(spec, scored))
    candidates.sort(key=lambda r: float(r.get("materialization_score") or 0), reverse=True)
    candidates = candidates[: max(1, int(max_candidates or 6))]
    return {
        "kind": "goc_memory_materialization_preview",
        "schema_version": 2,
        "thread_id": thread.id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "detector": {"kind": "generic_memory_shape_detector", "shape_ids": [spec["id"] for spec in GENERIC_SHAPE_SPECS]},
        "inventory": {"evidence_items": len(evidence), "demand_queries": len(demands), "memory_topology_mode": topology.get("mode") if isinstance(topology, dict) else None},
        "summary": {"candidate_count": len(candidates), "shadow_table_candidates": len([c for c in candidates if c.get("recommendation") == "create_shadow_table"]), "typed_jsonl_candidates": len([c for c in candidates if c.get("recommendation") == "create_typed_jsonl_first"]), "watchlist_candidates": len([c for c in candidates if c.get("recommendation") == "watch_and_continue_markdown"]), "publishable_knowledge_candidates": len([c for c in candidates if c.get("publish_policy", {}).get("publishable_as") == "sourced_knowledge_pack"])},
        "candidates": candidates,
        "next_steps": ["Review generic shape, schema and backfill preview before enabling write functions.", "Create shadow tables only until the user or policy approves canonical writes.", "Keep source memory as provenance; do not delete raw memory automatically."] if candidates else ["Keep compact markdown memory for now.", "Continue collecting usage signals until a repeated queryable memory shape emerges."],
    }



def _safe_id(value: Any = "") -> str:
    text = re.sub(r"[^a-zA-Z0-9_:-]+", "_", _clean(value).lower()).strip("_")
    return text or "memory_module"


def save_memory_materialization_candidates(session: Session, thread: Thread, *, min_score: float = .28, max_candidates: int = 6) -> dict[str, Any]:
    """Persist the current preview as reviewable candidate records without enabling writes."""
    preview = build_memory_materialization_preview(session, thread, min_score=min_score, max_candidates=max_candidates)
    saved: list[dict[str, Any]] = []
    for candidate in preview.get("candidates") or []:
        record = MemoryMaterializationCandidate(
            thread_id=thread.id,
            domain=_clean(candidate.get("shape_id") or candidate.get("domain")),
            title=_clean(candidate.get("title")),
            status="candidate",
            score=float(candidate.get("materialization_score") or 0.0),
            recommendation=_clean(candidate.get("recommendation")),
            candidate_json=json.dumps(candidate, ensure_ascii=False),
        )
        session.add(record)
        session.flush()
        saved.append({"id": record.id, "domain": record.domain, "title": record.title, "score": record.score, "recommendation": record.recommendation, "status": record.status})
    session.commit()
    preview["saved_candidates"] = saved
    preview["summary"]["saved_candidate_count"] = len(saved)
    return preview


def list_memory_materialization_candidates(session: Session, thread: Thread, *, limit: int = 20) -> dict[str, Any]:
    rows = session.exec(
        select(MemoryMaterializationCandidate)
        .where(MemoryMaterializationCandidate.thread_id == thread.id)
        .order_by(MemoryMaterializationCandidate.created_at.desc())
        .limit(max(1, min(int(limit or 20), 100)))
    ).all()
    out = []
    for row in rows:
        out.append({
            "id": row.id,
            "domain": row.domain,
            "title": row.title,
            "status": row.status,
            "score": row.score,
            "recommendation": row.recommendation,
            "candidate": _loads(row.candidate_json, {}),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        })
    return {"kind": "goc_memory_materialization_candidates", "thread_id": thread.id, "candidates": out}


def _candidate_from_body_or_record(session: Session, thread: Thread, body: dict[str, Any]) -> dict[str, Any]:
    candidate = body.get("candidate") if isinstance(body, dict) else None
    if isinstance(candidate, dict) and candidate:
        return candidate
    candidate_id = _clean(body.get("candidate_id") if isinstance(body, dict) else "")
    domain = _clean(body.get("domain") if isinstance(body, dict) else "")
    stmt = select(MemoryMaterializationCandidate).where(MemoryMaterializationCandidate.thread_id == thread.id)
    if candidate_id:
        stmt = stmt.where(MemoryMaterializationCandidate.id == candidate_id)
    elif domain:
        stmt = stmt.where(MemoryMaterializationCandidate.domain == domain).order_by(MemoryMaterializationCandidate.created_at.desc())
    else:
        stmt = stmt.order_by(MemoryMaterializationCandidate.score.desc(), MemoryMaterializationCandidate.created_at.desc())
    record = session.exec(stmt.limit(1)).first()
    if not record:
        preview = build_memory_materialization_preview(session, thread)
        candidates = preview.get("candidates") or []
        if domain:
            wanted = _clean(domain).lower()
            for c in candidates:
                aliases = [_clean(x).lower() for x in (c.get("legacy_domain_aliases") or c.get("aliases") or [])]
                if wanted in {_clean(c.get("domain")).lower(), _clean(c.get("shape_id")).lower(), _clean(c.get("candidate_id")).lower(), _clean(c.get("title")).lower(), *aliases}:
                    return c
        if candidates:
            return candidates[0]
        raise ValueError("no materialization candidate available")
    return _loads(record.candidate_json, {})


def _normalize_schema(candidate: dict[str, Any]) -> dict[str, Any]:
    proposed = candidate.get("proposed_schema") or {}
    table = _safe_id(proposed.get("table") or candidate.get("shape_id") or candidate.get("domain") or "memory_entries")
    cols = []
    for col in proposed.get("columns") or []:
        if not isinstance(col, dict):
            continue
        name = _safe_id(col.get("name"))
        if not name:
            continue
        typ = _clean(col.get("type") or "text").lower()
        if typ not in {"text", "datetime", "date", "json", "integer", "real", "boolean"}:
            typ = "text"
        cols.append({"name": name, "type": typ, "role": col.get("role"), "nullable": col.get("nullable", True), "default": col.get("default")})
    if not any(c.get("name") == "id" for c in cols):
        cols.insert(0, {"name": "id", "type": "text", "role": "primary_key", "nullable": False})
    for name, typ in (("source_ref", "text"), ("confidence", "real"), ("review_state", "text")):
        if not any(c.get("name") == name for c in cols):
            cols.append({"name": name, "type": typ, "nullable": True})
    return {"table": table, "columns": cols, "create_table_sql": proposed.get("create_table_sql") or _sql(table, cols)}


def _row_for_schema(raw: dict[str, Any], schema: dict[str, Any], index: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    raw = raw or {}
    for col in schema.get("columns") or []:
        name = col.get("name")
        if not name:
            continue
        if name in raw:
            out[name] = raw.get(name)
        elif name == "notes" and "preview" in raw:
            out[name] = raw.get("preview")
        elif name == "source_ref" and "source" in raw:
            out[name] = raw.get("source")
        elif "default" in col and col.get("default") is not None:
            out[name] = col.get("default")
        else:
            out[name] = None
    if not out.get("id"):
        out["id"] = _safe_id(raw.get("id") or f"{schema.get('table')}_{index + 1}")
    if raw.get("review_state") and not out.get("review_state"):
        out["review_state"] = raw.get("review_state")
    if raw.get("confidence") is not None and out.get("confidence") is None:
        out["confidence"] = raw.get("confidence")
    return out


def create_shadow_memory_module(session: Session, thread: Thread, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a DB-backed shadow module from a candidate. Does not enable canonical writes."""
    body = body or {}
    candidate = _candidate_from_body_or_record(session, thread, body)
    schema = _normalize_schema(candidate)
    module_id = _safe_id(body.get("module_id") or candidate.get("shape_id") or candidate.get("domain") or schema.get("table"))
    rows = list((candidate.get("backfill_preview") or {}).get("rows") or [])
    operations = []
    for op in candidate.get("proposed_operations") or []:
        if isinstance(op, dict):
            operations.append({**op, "enabled": False, "approval_required": True})
        else:
            operations.append({"name": _safe_id(op), "kind": "runtime_safe_operation", "enabled": False, "approval_required": True})
    now = datetime.now(timezone.utc)
    existing = session.exec(select(MemoryModule).where(MemoryModule.thread_id == thread.id, MemoryModule.module_id == module_id).limit(1)).first()
    if existing:
        module = existing
        module.updated_at = now
        # replace shadow rows on re-create to keep preview deterministic
        old_rows = session.exec(select(MemoryModuleRow).where(MemoryModuleRow.thread_id == thread.id, MemoryModuleRow.module_id == module_id)).all()
        for row in old_rows:
            session.delete(row)
    else:
        module = MemoryModule(thread_id=thread.id, module_id=module_id)
        session.add(module)
    manifest = {
        "kind": "goc_memory_module_manifest",
        "schema_version": 1,
        "module_id": module_id,
        "shape_id": _clean(candidate.get("shape_id") or candidate.get("domain")),
        "domain": _clean(candidate.get("shape_id") or candidate.get("domain")),
        "title": _clean(candidate.get("title") or candidate.get("shape_id") or candidate.get("domain") or module_id),
        "status": "shadow",
        "canonical_memory_switch": False,
        "raw_memory_retained": True,
        "generated_code_execution": False,
        "source_candidate_id": _clean(candidate.get("candidate_id")),
        "materialization_score": float(candidate.get("materialization_score") or 0.0),
        "safety": {"approval_required_for": ["enable_write_operations", "canonical_write_path", "raw_memory_deletion", "public_publish"]},
    }
    shadow_rows = [_row_for_schema(r, schema, i) for i, r in enumerate(rows)]
    review_count = 0
    high_count = 0
    module.domain = manifest["domain"]
    module.title = manifest["title"]
    module.status = "shadow"
    module.table_name = schema.get("table") or ""
    module.schema_json = json.dumps(schema, ensure_ascii=False)
    module.operations_json = json.dumps(operations, ensure_ascii=False)
    module.manifest_json = json.dumps(manifest, ensure_ascii=False)
    module.row_count = len(shadow_rows)
    module.review_count = 0
    module.high_confidence_count = 0
    session.flush()
    for i, raw in enumerate(shadow_rows):
        confidence = float(raw.get("confidence") or 0.0)
        review_state = _clean(raw.get("review_state") or ("high_confidence" if confidence >= .75 else "needs_review"))
        if review_state == "high_confidence" or confidence >= .75:
            high_count += 1
        else:
            review_count += 1
        session.add(MemoryModuleRow(
            thread_id=thread.id,
            module_id=module_id,
            row_key=_clean(raw.get("id") or f"row_{i + 1}"),
            status="shadow",
            review_state=review_state,
            row_json=json.dumps(raw, ensure_ascii=False),
            source_ref=_clean(raw.get("source_ref")),
            confidence=confidence,
        ))
    module.review_count = review_count
    module.high_confidence_count = high_count
    module.row_count = len(shadow_rows)
    record_id = _clean(body.get("candidate_id"))
    if record_id:
        record = session.get(MemoryMaterializationCandidate, record_id)
        if record:
            record.status = "shadow_created"
            record.updated_at = now
    session.commit()
    session.refresh(module)
    return _module_payload(session, module, include_rows=True)


def _module_payload(session: Session, module: MemoryModule, *, include_rows: bool = False, row_limit: int = 24) -> dict[str, Any]:
    payload = {
        "id": module.id,
        "thread_id": module.thread_id,
        "module_id": module.module_id,
        "domain": module.domain,
        "title": module.title,
        "status": module.status,
        "table_name": module.table_name,
        "schema": _loads(module.schema_json, {}),
        "operations": _loads(module.operations_json, []),
        "manifest": _loads(module.manifest_json, {}),
        "row_count": module.row_count,
        "review_count": module.review_count,
        "high_confidence_count": module.high_confidence_count,
        "created_at": module.created_at.isoformat() if module.created_at else None,
        "updated_at": module.updated_at.isoformat() if module.updated_at else None,
    }
    if include_rows:
        rows = session.exec(
            select(MemoryModuleRow)
            .where(MemoryModuleRow.thread_id == module.thread_id, MemoryModuleRow.module_id == module.module_id)
            .order_by(MemoryModuleRow.created_at.asc())
            .limit(max(1, min(int(row_limit or 24), 200)))
        ).all()
        payload["rows"] = [{
            "id": r.id,
            "row_key": r.row_key,
            "status": r.status,
            "review_state": r.review_state,
            "row": _loads(r.row_json, {}),
            "source_ref": r.source_ref,
            "confidence": r.confidence,
        } for r in rows]
    return payload


def list_memory_modules(session: Session, thread: Thread, *, include_rows: bool = False) -> dict[str, Any]:
    rows = session.exec(select(MemoryModule).where(MemoryModule.thread_id == thread.id).order_by(MemoryModule.updated_at.desc()).limit(100)).all()
    return {"kind": "goc_memory_modules", "thread_id": thread.id, "modules": [_module_payload(session, row, include_rows=include_rows) for row in rows]}
