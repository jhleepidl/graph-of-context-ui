from __future__ import annotations

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.services.static_project_manifest import (
    build_room_package_candidate,
    build_static_manifest_context_block,
    parse_project_manifest,
)

router = APIRouter(prefix="/api/project-manifests", tags=["project-manifests"])


class ProjectManifestImportRequest(BaseModel):
    filename: str = "CLAUDE.md"
    content: str
    source: str = "api_import"


@router.post("/import-preview")
def import_project_manifest_preview(body: ProjectManifestImportRequest):
    if not body.content.strip():
        raise HTTPException(400, "content is required")
    manifest = parse_project_manifest(body.filename, body.content, source=body.source)
    return {
        "kind": "project_manifest_import_preview_v1",
        "manifest": manifest,
        "room_package_candidate": build_room_package_candidate(manifest),
        "static_context_block": build_static_manifest_context_block(manifest),
    }
