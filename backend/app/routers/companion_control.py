from __future__ import annotations

from fastapi import APIRouter

from app.services.companion_control import get_companion_control_manifest

router = APIRouter(prefix="/api/companion-control", tags=["companion-control"])


@router.get("/manifest")
def companion_control_manifest():
    """Return the web-facing companion/context control surface manifest.

    The first GoC integration is intentionally read-only: it gives the web UI
    enough structure to present a simplified Companion Hub while durable runtime
    writes continue through the Telegram/DdalGgak command surface. This avoids
    silently creating project memory from an over-eager web form.
    """
    return get_companion_control_manifest()
