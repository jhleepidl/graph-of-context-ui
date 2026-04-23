from __future__ import annotations

from sqlmodel import Session, select

from app.models import ContextSet, Thread
from app.services.context_versions import snapshot_context_set
from app.tenant import PUBLIC_SERVICE_ID

PUBLIC_LIBRARY_TITLE = "agents:library"
PUBLIC_SKILL_LIBRARY_TITLE = "skills:library"


def ensure_public_library_thread(session: Session) -> tuple[Thread, ContextSet]:
    thread = session.exec(
        select(Thread)
        .where(Thread.service_id == PUBLIC_SERVICE_ID, Thread.title == PUBLIC_LIBRARY_TITLE)
        .order_by(Thread.created_at.asc(), Thread.id.asc())
        .limit(1)
    ).first()
    if not thread:
        thread = Thread(title=PUBLIC_LIBRARY_TITLE, service_id=PUBLIC_SERVICE_ID)
        session.add(thread)
        session.flush()

    context_set = session.exec(
        select(ContextSet)
        .where(ContextSet.thread_id == thread.id)
        .order_by(ContextSet.created_at.asc(), ContextSet.id.asc())
        .limit(1)
    ).first()
    if not context_set:
        context_set = ContextSet(thread_id=thread.id, name="default")
        session.add(context_set)
        session.flush()
        snapshot_context_set(
            session,
            context_set,
            reason="create",
            meta={
                "name": context_set.name,
                "thread_id": thread.id,
                "service_id": PUBLIC_SERVICE_ID,
                "is_public_library": True,
            },
        )

    return thread, context_set


def ensure_public_skill_library_thread(session: Session) -> tuple[Thread, ContextSet]:
    thread = session.exec(
        select(Thread)
        .where(Thread.service_id == PUBLIC_SERVICE_ID, Thread.title == PUBLIC_SKILL_LIBRARY_TITLE)
        .order_by(Thread.created_at.asc(), Thread.id.asc())
        .limit(1)
    ).first()
    if not thread:
        thread = Thread(title=PUBLIC_SKILL_LIBRARY_TITLE, service_id=PUBLIC_SERVICE_ID)
        session.add(thread)
        session.flush()

    context_set = session.exec(
        select(ContextSet)
        .where(ContextSet.thread_id == thread.id)
        .order_by(ContextSet.created_at.asc(), ContextSet.id.asc())
        .limit(1)
    ).first()
    if not context_set:
        context_set = ContextSet(thread_id=thread.id, name="default")
        session.add(context_set)
        session.flush()
        snapshot_context_set(
            session,
            context_set,
            reason="create",
            meta={
                "name": context_set.name,
                "thread_id": thread.id,
                "service_id": PUBLIC_SERVICE_ID,
                "is_public_library": True,
                "library_kind": "skill_package",
            },
        )

    return thread, context_set
