from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import HarnessEvaluationRun, HarnessEvaluationVariantResult


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _arr(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, limit: int = 500) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _dt(value: Any) -> datetime | None:
    text = _text(value, 100)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load_json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except Exception:
        return fallback


def serialize_harness_evaluation_run(row: HarnessEvaluationRun, *, include_payload: bool = False) -> dict[str, Any]:
    payload = {
        "evaluation_id": row.evaluation_id,
        "suite": row.suite,
        "status": row.status,
        "scenario_count": row.scenario_count,
        "total_run_count": row.total_run_count,
        "passed_run_count": row.passed_run_count,
        "failed_run_count": row.failed_run_count,
        "recommendation_variant_id": row.recommendation_variant_id or None,
        "recommendation_runtime_signature": row.recommendation_runtime_signature or None,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "ingested_at": row.ingested_at.isoformat() if row.ingested_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if include_payload:
        payload["payload"] = _load_json(row.payload_json, {})
    return payload


def serialize_harness_variant_result(row: HarnessEvaluationVariantResult) -> dict[str, Any]:
    return {
        "evaluation_id": row.evaluation_id,
        "runtime_signature": row.runtime_signature,
        "harness_variant_id": row.harness_variant_id,
        "harness_variant_hash": row.harness_variant_hash or None,
        "provider": row.provider or None,
        "model": row.model or None,
        "reasoning_effort": row.reasoning_effort or None,
        "cli_version": row.cli_version or None,
        "run_count": row.run_count,
        "passed_run_count": row.passed_run_count,
        "failed_run_count": row.failed_run_count,
        "success_rate": row.success_rate,
        "average_score": row.average_score,
        "average_duration_ms": row.average_duration_ms,
        "ingested_at": row.ingested_at.isoformat() if row.ingested_at else None,
    }


def ingest_harness_evaluation(session: Session, payload: dict[str, Any]) -> tuple[HarnessEvaluationRun, list[HarnessEvaluationVariantResult], bool]:
    body = _obj(payload)
    evaluation_id = _text(body.get("evaluation_id"), 200)
    if not evaluation_id:
        raise HTTPException(400, "evaluation_id is required")
    row = session.exec(select(HarnessEvaluationRun).where(HarnessEvaluationRun.evaluation_id == evaluation_id)).first()
    created = row is None
    if row is None:
        row = HarnessEvaluationRun(evaluation_id=evaluation_id)
        session.add(row)
    recommendation = _obj(body.get("recommendation"))
    row.suite = _text(body.get("suite"), 160) or "live"
    row.status = _text(body.get("status"), 80) or "completed"
    row.scenario_count = _int(body.get("scenario_count"))
    row.total_run_count = _int(body.get("total_run_count"))
    row.passed_run_count = _int(body.get("passed_run_count"))
    row.failed_run_count = _int(body.get("failed_run_count"))
    row.recommendation_variant_id = _text(recommendation.get("harness_variant_id"), 240)
    row.recommendation_runtime_signature = _text(recommendation.get("runtime_signature"), 800)
    row.payload_json = _json(body)
    row.started_at = _dt(body.get("started_at"))
    row.finished_at = _dt(body.get("finished_at"))
    row.updated_at = datetime.now(timezone.utc)
    session.flush()

    variants: list[HarnessEvaluationVariantResult] = []
    for item in _arr(body.get("variant_results")):
        variant = _obj(item)
        variant_id = _text(variant.get("harness_variant_id"), 240)
        if not variant_id:
            continue
        runtime_signature = _text(variant.get("runtime_signature"), 800) or "|".join([
            variant_id,
            _text(variant.get("provider"), 80) or "unknown-provider",
            _text(variant.get("model"), 200) or "provider-default",
            _text(variant.get("reasoning_effort"), 80) or "provider-default",
            _text(variant.get("cli_version"), 300) or "unknown-cli",
        ])
        result = session.exec(
            select(HarnessEvaluationVariantResult).where(
                HarnessEvaluationVariantResult.evaluation_id == evaluation_id,
                HarnessEvaluationVariantResult.runtime_signature == runtime_signature,
            )
        ).first()
        if result is None:
            result = HarnessEvaluationVariantResult(evaluation_id=evaluation_id, runtime_signature=runtime_signature, harness_variant_id=variant_id)
            session.add(result)
        result.runtime_signature = runtime_signature
        result.harness_variant_id = variant_id
        result.harness_variant_hash = _text(variant.get("harness_variant_hash"), 128)
        result.provider = _text(variant.get("provider"), 80)
        result.model = _text(variant.get("model"), 200)
        result.reasoning_effort = _text(variant.get("reasoning_effort"), 80)
        result.cli_version = _text(variant.get("cli_version"), 300)
        result.run_count = _int(variant.get("run_count"))
        result.passed_run_count = _int(variant.get("passed_run_count"))
        result.failed_run_count = _int(variant.get("failed_run_count"))
        result.success_rate = _float(variant.get("success_rate"))
        result.average_score = _float(variant.get("average_score"))
        result.average_duration_ms = _float(variant.get("average_duration_ms"))
        result.payload_json = _json(variant)
        variants.append(result)
    session.flush()
    return row, variants, created


def list_harness_evaluation_runs(session: Session, *, limit: int = 30) -> list[HarnessEvaluationRun]:
    cap = max(1, min(int(limit or 30), 200))
    return list(session.exec(select(HarnessEvaluationRun).order_by(HarnessEvaluationRun.ingested_at.desc()).limit(cap)).all())


def get_harness_evaluation_run(session: Session, evaluation_id: str) -> HarnessEvaluationRun:
    row = session.exec(select(HarnessEvaluationRun).where(HarnessEvaluationRun.evaluation_id == _text(evaluation_id, 200))).first()
    if not row:
        raise HTTPException(404, "harness evaluation not found")
    return row


def list_variant_results(session: Session, *, limit: int = 500) -> list[HarnessEvaluationVariantResult]:
    cap = max(1, min(int(limit or 500), 2000))
    return list(session.exec(select(HarnessEvaluationVariantResult).order_by(HarnessEvaluationVariantResult.ingested_at.desc()).limit(cap)).all())


def aggregate_variant_performance(rows: list[HarnessEvaluationVariantResult]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row.runtime_signature or "|".join([row.harness_variant_id, row.provider or "unknown-provider", row.model or "provider-default", row.reasoning_effort or "provider-default", row.cli_version or "unknown-cli"])
        current = grouped.setdefault(key, {
            "runtime_signature": key,
            "harness_variant_id": row.harness_variant_id,
            "provider": row.provider or None,
            "model": row.model or None,
            "reasoning_effort": row.reasoning_effort or None,
            "latest_cli_version": row.cli_version or None,
            "evaluation_count": 0,
            "run_count": 0,
            "passed_run_count": 0,
            "weighted_score": 0.0,
            "weighted_duration_ms": 0.0,
            "latest_ingested_at": row.ingested_at.isoformat() if row.ingested_at else None,
        })
        count = max(0, row.run_count)
        current["evaluation_count"] += 1
        current["run_count"] += count
        current["passed_run_count"] += max(0, row.passed_run_count)
        current["weighted_score"] += row.average_score * count
        current["weighted_duration_ms"] += row.average_duration_ms * count
    out = []
    for current in grouped.values():
        run_count = current.pop("run_count")
        passed = current.pop("passed_run_count")
        weighted_score = current.pop("weighted_score")
        weighted_duration = current.pop("weighted_duration_ms")
        out.append({
            **current,
            "run_count": run_count,
            "passed_run_count": passed,
            "success_rate": (passed / run_count) if run_count else 0.0,
            "average_score": (weighted_score / run_count) if run_count else 0.0,
            "average_duration_ms": (weighted_duration / run_count) if run_count else 0.0,
        })
    return sorted(out, key=lambda item: (-item["success_rate"], -item["average_score"], item["average_duration_ms"]))
