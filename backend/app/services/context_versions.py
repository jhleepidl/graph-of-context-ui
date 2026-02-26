from __future__ import annotations

from typing import Any, Iterable, List, Optional

from sqlmodel import Session, select

from app.models import ContextSet, ContextSetVersion, utcnow
from app.services.graph import jdump, jload


def _ordered_unique(ids: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for nid in ids:
        if not isinstance(nid, str) or not nid or nid in seen:
            continue
        seen.add(nid)
        out.append(nid)
    return out


def snapshot_context_set(
    session: Session,
    cs: ContextSet,
    *,
    reason: str,
    changed_node_ids: Optional[List[str]] = None,
    meta: Optional[dict[str, Any]] = None,
) -> ContextSetVersion:
    """Append a versioned snapshot after the caller mutates `cs.active_node_ids_json`."""
    active_ids = _ordered_unique(jload(cs.active_node_ids_json or "[]", []))
    if active_ids != jload(cs.active_node_ids_json or "[]", []):
        cs.active_node_ids_json = jdump(active_ids)

    latest = session.exec(
        select(ContextSetVersion)
        .where(ContextSetVersion.context_set_id == cs.id)
        .order_by(ContextSetVersion.version.desc())
        .limit(1)
    ).first()
    next_version = (int(latest.version) if latest else -1) + 1

    cs.version = next_version
    cs.updated_at = utcnow()

    row = ContextSetVersion(
        context_set_id=cs.id,
        thread_id=cs.thread_id,
        version=next_version,
        reason=reason,
        active_node_ids_json=cs.active_node_ids_json,
        changed_node_ids_json=jdump(_ordered_unique(changed_node_ids or [])),
        meta_json=jdump(meta or {}),
    )
    session.add(cs)
    session.add(row)
    return row
