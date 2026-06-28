from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any


FORBIDDEN_KEYS = {
    'text',
    'raw_text',
    'rawText',
    'body',
    'content',
    'message',
    'prompt',
    'answer',
    'response',
    'transcript',
    'attachment_bytes',
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _hash(value: str) -> str:
    return hashlib.sha256(str(value or '').encode('utf-8')).hexdigest()[:24]


def _strip_raw(value: Any) -> Any:
    if isinstance(value, list):
        return [_strip_raw(item) for item in value]
    if not isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    for key, raw in value.items():
        lower = str(key).lower()
        if key in FORBIDDEN_KEYS or lower in FORBIDDEN_KEYS:
            continue
        if 'transcript' in lower or 'attachment_bytes' in lower:
            continue
        out[key] = _strip_raw(raw)
    return out


def build_room_memory_goc_event(
    *,
    thread_id: str = '',
    room_id: str = '',
    route: dict[str, Any] | None = None,
    evolution_snapshot: dict[str, Any] | None = None,
    ranking_snapshot: dict[str, Any] | None = None,
    outcome: dict[str, Any] | None = None,
    source: str = 'goc_backend',
) -> dict[str, Any]:
    route_row = _as_dict(route)
    snapshot = _as_dict(evolution_snapshot)
    aggregate = _as_dict(snapshot.get('aggregate'))
    counts = _as_dict(aggregate.get('counts'))
    discovery = _as_dict(snapshot.get('skill_discovery'))
    trial_plan = _as_dict(snapshot.get('room_memory_trial_plan') or discovery.get('room_memory_schema_trial_plan'))
    event = {
        'kind': 'room_memory_goc_event_v1',
        'ts': datetime.now(timezone.utc).isoformat(),
        'source': source,
        'ids': {
            'thread_id_hash': _hash(thread_id),
            'room_id_hash': _hash(room_id or thread_id),
        },
        'routing': _strip_raw({
            'depth': route_row.get('depth') or route_row.get('work_mode') or '',
            'execution_shape': route_row.get('execution_shape') or '',
            'reason_codes': _as_list(route_row.get('reason_codes'))[:20],
        }),
        'room_evolution': _strip_raw({
            'maturity': snapshot.get('maturity') or '',
            'top_object_types': [str(_as_dict(row).get('id') or '') for row in _as_list(aggregate.get('top_objects'))[:12] if _as_dict(row).get('id')],
            'counts': {
                'total_events': counts.get('total_events') or 0,
                'preference': counts.get('preference') or 0,
                'observation_event': counts.get('observation_event') or 0,
                'aggregate_query': counts.get('aggregate_query') or 0,
                'correction': counts.get('correction') or 0,
                'database_need': counts.get('database_need') or 0,
            },
        }),
        'room_memory_trials': _strip_raw({
            'candidate_object_types': _as_list(trial_plan.get('candidate_object_types'))[:12],
            'treatments': _as_list(trial_plan.get('treatments'))[:12],
            'probe_count': len(_as_list(_as_dict(discovery.get('probe_suite')).get('probes'))),
        }),
        'ranking': _strip_raw(ranking_snapshot or {}),
        'outcome': _strip_raw(outcome or {}),
        'privacy': {
            'includes_raw_text': False,
            'includes_private_memory_content': False,
            'includes_uploaded_file_content': False,
            'ids_are_hashed': True,
        },
    }
    return event


def validate_room_memory_goc_event(event: dict[str, Any]) -> tuple[bool, str]:
    encoded = json.dumps(event, ensure_ascii=False)
    for key in FORBIDDEN_KEYS:
        if f'"{key}"' in encoded:
            return False, f'forbidden_key:{key}'
    privacy = _as_dict(event.get('privacy'))
    if privacy.get('includes_raw_text') is True:
        return False, 'raw_text_marked_present'
    if privacy.get('includes_private_memory_content') is True:
        return False, 'private_memory_marked_present'
    return True, ''
