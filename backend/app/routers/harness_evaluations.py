from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session, select

from app.auth import get_current_principal, require_service_key_principal
from app.db import engine
from app.models import HarnessEvaluationVariantResult
from app.services.harness_evaluations import (
    aggregate_variant_performance,
    get_harness_evaluation_run,
    ingest_harness_evaluation,
    list_harness_evaluation_runs,
    list_variant_results,
    serialize_harness_evaluation_run,
    serialize_harness_variant_result,
)

router = APIRouter(prefix="/api/evaluations/harness", tags=["harness-evaluations"])


class HarnessEvaluationIngestRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    evaluation_id: str
    suite: str = "live"
    status: str = "completed"
    scenario_count: int = 0
    total_run_count: int = 0
    passed_run_count: int = 0
    failed_run_count: int = 0
    variant_results: list[dict[str, Any]] = []
    recommendation: dict[str, Any] | None = None
    started_at: str | None = None
    finished_at: str | None = None
    runs: list[dict[str, Any]] = []


@router.post("/runs/ingest")
def ingest_run(body: HarnessEvaluationIngestRequest):
    require_service_key_principal()
    payload = body.model_dump()
    with Session(engine) as session:
        row, variants, created = ingest_harness_evaluation(session, payload)
        session.commit()
        session.refresh(row)
        return {
            "created": created,
            "evaluation": serialize_harness_evaluation_run(row),
            "variant_results": [serialize_harness_variant_result(item) for item in variants],
        }


@router.get("/runs")
def list_runs(limit: int = 30):
    get_current_principal()
    with Session(engine) as session:
        rows = list_harness_evaluation_runs(session, limit=limit)
        return {"count": len(rows), "items": [serialize_harness_evaluation_run(row) for row in rows]}


@router.get("/runs/{evaluation_id}")
def read_run(evaluation_id: str):
    get_current_principal()
    with Session(engine) as session:
        row = get_harness_evaluation_run(session, evaluation_id)
        variants = list(session.exec(
            select(HarnessEvaluationVariantResult).where(HarnessEvaluationVariantResult.evaluation_id == row.evaluation_id)
        ).all())
        return {
            "evaluation": serialize_harness_evaluation_run(row, include_payload=True),
            "variant_results": [serialize_harness_variant_result(item) for item in variants],
        }


@router.get("/variants")
def read_variant_performance(limit: int = 500):
    get_current_principal()
    with Session(engine) as session:
        rows = list_variant_results(session, limit=limit)
        items = aggregate_variant_performance(rows)
        return {"count": len(items), "items": items, "promotion_policy": "evaluation_only_no_auto_promotion"}
