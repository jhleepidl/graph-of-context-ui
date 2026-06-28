from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.services.claude_compatible_events import (
    build_claude_compatible_room_event,
    claude_event_to_room_usage_event,
    import_claude_compatible_manifest_preview,
    validate_claude_compatible_room_event,
)

router = APIRouter(prefix="/api/claude-compatible", tags=["claude-compatible"])


class ClaudeCompatibleEventRequest(BaseModel):
    source: str = "claude_code"
    project_root: str = ""
    project_id: str = ""
    room_id: str = ""
    user_id: str = ""
    session_id: str = ""
    event_type: str = ""
    action: str = ""
    tool_name: str = ""
    manifest_type: str = ""
    manifest_filename: str = ""
    subagent_name: str = ""
    skill_name: str = ""
    task_archetype: str = ""
    routing_depth: str = ""
    outcome: dict = {}
    metadata: dict = {}
    accepted: bool | None = None
    user_corrected: bool | None = None


class ClaudeManifestImportRequest(BaseModel):
    filename: str = "CLAUDE.md"
    content: str
    source: str = "claude_compatible_api"


@router.post("/events/preview")
def preview_claude_compatible_event(body: ClaudeCompatibleEventRequest):
    event = build_claude_compatible_room_event(body.model_dump())
    ok, reason = validate_claude_compatible_room_event(event)
    if not ok:
        raise HTTPException(400, reason)
    return {
        "kind": "claude_compatible_event_preview_v1",
        "event": event,
        "room_usage_event": claude_event_to_room_usage_event(event),
        "validated": True,
    }


@router.post("/manifests/import-preview")
def preview_claude_compatible_manifest(body: ClaudeManifestImportRequest):
    if not body.content.strip():
        raise HTTPException(400, "content is required")
    return import_claude_compatible_manifest_preview(body.filename, body.content, source=body.source)
