from __future__ import annotations

from typing import Any

from sqlmodel import Session

from app.services.resolved_runtime import resolve_conversation_team


def build_conversation_team_projection(
    session: Session,
    *,
    thread_id: str,
    nodes: list[Any],
) -> dict[str, Any]:
    return resolve_conversation_team(session, thread_id=thread_id, nodes=nodes).as_payload()
