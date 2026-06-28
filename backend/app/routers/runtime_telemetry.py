from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.runtime_telemetry import (
    build_runtime_telemetry_event,
    summarize_runtime_telemetry,
    validate_runtime_telemetry_event,
)

router = APIRouter(prefix="/api", tags=["runtime-telemetry"])


class RuntimeTelemetryIngestRequest(BaseModel):
    run_id: str = ""
    room_id: str = ""
    turn_id: str = ""
    provider: str = ""
    api: str = ""
    model: str = ""
    usage: dict[str, Any] = {}
    prompt_chars: int = 0
    output_chars: int = 0
    latency_ms: int = 0
    route: dict[str, Any] = {}
    context: dict[str, Any] = {}
    room_memory_trials: dict[str, Any] = {}
    outcome: dict[str, Any] = {}
    pricing: dict[str, Any] = {}
    trace: dict[str, Any] = {}
    source: str = "goc_runtime_telemetry_api"


class RuntimeTelemetrySummaryRequest(BaseModel):
    events: list[dict[str, Any]]


@router.post("/threads/{thread_id}/runtime-telemetry")
def ingest_thread_runtime_telemetry(thread_id: str, body: RuntimeTelemetryIngestRequest):
    event = build_runtime_telemetry_event(
        thread_id=thread_id,
        room_id=body.room_id,
        run_id=body.run_id,
        turn_id=body.turn_id,
        provider=body.provider,
        api=body.api,
        model=body.model,
        usage=body.usage,
        prompt_chars=body.prompt_chars,
        output_chars=body.output_chars,
        latency_ms=body.latency_ms,
        route=body.route,
        context=body.context,
        room_memory_trials=body.room_memory_trials,
        outcome=body.outcome,
        pricing=body.pricing,
        trace=body.trace,
        source=body.source,
    )
    ok, reason = validate_runtime_telemetry_event(event)
    if not ok:
        raise HTTPException(400, reason)
    return {
        "kind": "runtime_telemetry_ingest_preview_v1",
        "accepted": True,
        "persisted": False,
        "event": event,
    }


@router.post("/runtime-telemetry/summary-preview")
def runtime_telemetry_summary_preview(body: RuntimeTelemetrySummaryRequest):
    return summarize_runtime_telemetry(body.events)
