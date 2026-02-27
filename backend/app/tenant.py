from __future__ import annotations

from fastapi import HTTPException
from sqlmodel import Session

from app.auth import get_current_principal
from app.models import ContextSet, Node, Thread


def current_service_id() -> str:
    principal = get_current_principal()
    if principal.role == "admin":
        raise HTTPException(400, "admin principal is not bound to a single service_id")
    if not principal.service_id:
        raise HTTPException(401, "service scope is missing")
    return principal.service_id


def current_tenant() -> str:
    # Legacy alias kept to minimize router churn.
    return current_service_id()


def _check_thread_scope(thread: Thread) -> Thread:
    principal = get_current_principal()
    if principal.role == "admin":
        return thread
    if not principal.service_id:
        raise HTTPException(401, "service scope is missing")
    if thread.service_id != principal.service_id:
        # Hide service boundary behind a not-found response.
        raise HTTPException(404, "thread not found")
    return thread


def require_thread_access(session: Session, thread_id: str) -> Thread:
    thread = session.get(Thread, thread_id)
    if not thread:
        raise HTTPException(404, "thread not found")
    return _check_thread_scope(thread)


def require_context_set_access(session: Session, context_set_id: str) -> ContextSet:
    context_set = session.get(ContextSet, context_set_id)
    if not context_set:
        raise HTTPException(404, "context set not found")
    require_thread_access(session, context_set.thread_id)
    return context_set


def require_node_access(session: Session, node_id: str) -> Node:
    node = session.get(Node, node_id)
    if not node:
        raise HTTPException(404, "node not found")
    require_thread_access(session, node.thread_id)
    return node
