from __future__ import annotations

import json
import re
from typing import Any

from sqlmodel import Session, select

from app.models import RoomUsageEventRecord, Thread
from app.services.room_learning import build_room_learning_snapshot


def _clean(value: Any = '', max_len: int = 1000) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text[:max_len]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _loads(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or '')
    except Exception:
        return default


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def room_usage_event_to_row(row: RoomUsageEventRecord) -> dict[str, Any]:
    payload = _loads(row.payload_json, {})
    return {
        'id': row.id,
        'thread_id': row.thread_id,
        'run_id': row.run_id,
        'chat_id': row.chat_id,
        'user_id': row.user_id,
        'event_type': row.event_type,
        'command': row.command,
        'domain_label': row.domain_label,
        'recommended_approach': row.recommended_approach,
        'suggested_action': row.suggested_action,
        'payload': payload,
        'created_at': row.created_at.isoformat(),
    }


def record_room_usage_event(session: Session, thread: Thread, body: dict[str, Any]) -> dict[str, Any]:
    payload = _as_dict(body.get('event') or body)
    room = _as_dict(payload.get('room'))
    rec = _as_dict(payload.get('recommendation'))
    row = RoomUsageEventRecord(
        thread_id=thread.id,
        run_id=_clean(payload.get('run_id') or payload.get('runId') or '', 160) or None,
        chat_id=_clean(payload.get('chat_id') or payload.get('chatId') or room.get('room_id') or '', 160),
        user_id=_clean(payload.get('user_id') or payload.get('userId') or '', 160),
        event_type=_clean(payload.get('event_type') or payload.get('eventType') or 'room_event', 120),
        command=_clean(payload.get('command') or '', 120),
        domain_label=_clean(room.get('domain_label') or payload.get('domain_label') or 'general_workbench', 160),
        recommended_approach=_clean(rec.get('recommended') or '', 160),
        suggested_action=_clean(rec.get('action') or '', 160),
        payload_json=_dumps(payload),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return {'ok': True, 'event': room_usage_event_to_row(row)}


def list_room_usage_events(session: Session, thread: Thread, *, limit: int = 200) -> dict[str, Any]:
    n = max(1, min(int(limit or 200), 1000))
    rows = list(session.exec(
        select(RoomUsageEventRecord)
        .where(RoomUsageEventRecord.thread_id == thread.id)
        .order_by(RoomUsageEventRecord.created_at.desc())
        .limit(n)
    ))
    items = [room_usage_event_to_row(row) for row in rows]
    return {'ok': True, 'thread_id': thread.id, 'summary': summarize_room_usage_events(items), 'items': items}


def summarize_room_usage_events(items: list[dict[str, Any]]) -> dict[str, Any]:
    by_event: dict[str, int] = {}
    by_domain: dict[str, int] = {}
    by_approach: dict[str, int] = {}
    for item in items:
        by_event[item.get('event_type') or 'room_event'] = by_event.get(item.get('event_type') or 'room_event', 0) + 1
        by_domain[item.get('domain_label') or 'general_workbench'] = by_domain.get(item.get('domain_label') or 'general_workbench', 0) + 1
        if item.get('recommended_approach'):
            by_approach[item.get('recommended_approach')] = by_approach.get(item.get('recommended_approach'), 0) + 1
    return {
        'event_count': len(items),
        'by_event_type': by_event,
        'by_domain': by_domain,
        'by_recommended_approach': by_approach,
    }


def get_room_learning_snapshot(session: Session, thread: Thread, *, limit: int = 200) -> dict[str, Any]:
    events = list_room_usage_events(session, thread, limit=limit)
    snapshot = build_room_learning_snapshot(events.get('items') or [])
    return {'ok': True, 'thread_id': thread.id, 'snapshot': snapshot}
