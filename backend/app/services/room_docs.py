from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models import RoomUsageEventRecord, Thread


def _clean(value: Any = '', max_len: int = 1000) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text[:max_len]


def _loads(raw: str | None, default: Any) -> Any:
    try:
        parsed = json.loads(raw or '')
        return parsed if parsed is not None else default
    except Exception:
        return default


def _slug(value: Any = '', fallback: str = 'note') -> str:
    text = _clean(value or fallback, 120).lower()
    text = re.sub(r'[^a-z0-9가-힣._:-]+', '-', text).strip('-')
    return text or fallback


def _date_of(value: Any = '') -> str:
    raw = _clean(value, 80)
    if re.match(r'^\d{4}-\d{2}-\d{2}', raw):
        return raw[:10]
    try:
        if raw.endswith('Z'):
            raw = raw[:-1] + '+00:00'
        return datetime.fromisoformat(raw).date().isoformat()
    except Exception:
        return datetime.now(timezone.utc).date().isoformat()


def _category(event: dict[str, Any]) -> str:
    payload = event.get('payload') if isinstance(event.get('payload'), dict) else {}
    hay = ' '.join([
        _clean(event.get('event_type'), 120),
        _clean(event.get('command'), 120),
        _clean(payload.get('goal'), 300),
        _clean(event.get('domain_label'), 120),
    ]).lower()
    if re.search(r'room|preset|package|profile|evolution|composition', hay):
        return 'room-setting'
    if re.search(r'memory|remember|correction|correct', hay):
        return 'memory-governance'
    if re.search(r'skill|tool|artifact|file|test|build|patch|code|구현|패치|테스트', hay):
        return 'execution-skill'
    if re.search(r'loop|team|agent|council|handoff|topology', hay):
        return 'agent-topology'
    if re.search(r'research|paper|논문|실험|evaluation|benchmark', hay):
        return 'research-work'
    return 'operations'


def _event_title(event: dict[str, Any]) -> str:
    payload = event.get('payload') if isinstance(event.get('payload'), dict) else {}
    command = _clean(event.get('command'), 80)
    event_type = _clean(event.get('event_type') or 'room_event', 80)
    goal = _clean(payload.get('goal'), 100)
    return ' · '.join([part for part in [command or event_type, goal] if part]) or event_type


def _room_usage_event_to_doc_event(row: RoomUsageEventRecord) -> dict[str, Any]:
    payload = _loads(row.payload_json, {})
    return {
        'id': row.id,
        'created_at': row.created_at.isoformat() if row.created_at else '',
        'event_type': row.event_type,
        'command': row.command,
        'domain_label': row.domain_label,
        'run_id': row.run_id,
        'chat_id': row.chat_id,
        'payload': payload if isinstance(payload, dict) else {},
    }


def _build_actions(events: list[dict[str, Any]], limit: int = 40) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for idx, event in enumerate(events[-limit:]):
        date = _date_of(event.get('created_at'))
        category = _category(event)
        title = _event_title(event)
        actions.append({
            'kind': 'room_doc_action_entry_v1',
            'path': f'action/{date}-{_slug(category)}-{idx + 1:02d}.md',
            'date': date,
            'category': category,
            'title': title,
            'summary': _clean((event.get('payload') or {}).get('goal') or title, 240),
            'event_type': event.get('event_type') or '',
            'command': event.get('command') or '',
            'provenance': {
                'event_id': event.get('id'),
                'created_at': event.get('created_at'),
                'run_id': event.get('run_id'),
                'copies_raw_transcript': False,
            },
        })
    actions.reverse()
    return actions


def _living_docs(thread: Thread, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    domains = sorted({event.get('domain_label') or 'general_workbench' for event in events})
    event_types = defaultdict(int)
    for event in events:
        event_types[event.get('event_type') or 'room_event'] += 1
    return [
        {
            'kind': 'room_living_doc_v1',
            'path': 'docs/room-setting.md',
            'category': 'room-setting',
            'title': 'Room setting and package lineage',
            'summary': f'GoC generated room-setting document for {thread.title}.',
            'sections': [
                {'heading': 'Thread', 'items': [f'title: {thread.title}', f'id: {thread.id}']},
                {'heading': 'Observed domains', 'items': domains or ['(none)']},
            ],
        },
        {
            'kind': 'room_living_doc_v1',
            'path': 'docs/memory-hierarchy.md',
            'category': 'memory-governance',
            'title': 'Memory hierarchy and governance',
            'summary': 'Memory is reviewed room state, not raw transcript dumping.',
            'sections': [
                {'heading': 'Policy', 'items': ['raw events are evidence', 'memory candidates require review', 'GoC browser should expose provenance and status']},
            ],
        },
        {
            'kind': 'room_living_doc_v1',
            'path': 'docs/topology-learning.md',
            'category': 'agent-topology',
            'title': 'Topology learning and dataset export',
            'summary': 'Tracks communication topology choices and outcome labels for later router/evaluator training.',
            'sections': [
                {'heading': 'Observed event types', 'items': [f'{k}: {v}' for k, v in sorted(event_types.items())] or ['(none)']},
                {'heading': 'Guardrail', 'items': ['trained routers may suggest but not directly mutate room state']},
            ],
        },
    ]


def _render_doc(doc: dict[str, Any]) -> str:
    lines = [f"# {doc.get('title') or doc.get('path')}", '', _clean(doc.get('summary'), 1000), '']
    for section in doc.get('sections') or []:
        if not isinstance(section, dict):
            continue
        lines += [f"## {section.get('heading') or 'Section'}", '']
        for item in section.get('items') or []:
            lines.append(f'- {item}')
        lines.append('')
    return '\n'.join(lines).strip() + '\n'


def build_room_docs_browser(session: Session, thread: Thread, *, limit: int = 200) -> dict[str, Any]:
    n = max(1, min(int(limit or 200), 1000))
    rows = list(session.exec(
        select(RoomUsageEventRecord)
        .where(RoomUsageEventRecord.thread_id == thread.id)
        .order_by(RoomUsageEventRecord.created_at.desc())
        .limit(n)
    ))
    events = [_room_usage_event_to_doc_event(row) for row in reversed(rows)]
    actions = _build_actions(events, limit=min(n, 80))
    docs = _living_docs(thread, events)
    date_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    category_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for action in actions:
        date_groups[action['date']].append(action)
        category_groups[action['category']].append(action)
    for doc in docs:
        category_groups[doc['category']].append(doc)

    files = [
        {
            'path': 'AGENTS.md',
            'kind': 'agent_manifest',
            'category': 'operations',
            'title': 'AGENTS.md',
            'summary': 'Room-level agent instructions and document policy.',
            'content': '# AGENTS.md\n\nUse `moc-structure.md`, then `moc-by-date.md` or `moc-by-category.md`. Treat docs as materialized views with provenance.\n',
        },
        {
            'path': 'moc-structure.md',
            'kind': 'moc',
            'category': 'operations',
            'title': 'MOC Structure',
            'summary': 'Recommended document navigation flow.',
            'content': '# MOC Structure\n\n1. AGENTS.md\n2. moc-by-date.md\n3. moc-by-category.md\n4. docs/*\n5. action/*\n',
        },
        {
            'path': 'moc-by-date.md',
            'kind': 'moc',
            'category': 'operations',
            'title': 'MOC by Date',
            'summary': 'Chronological index of action notes.',
            'content': '# MOC by Date\n\n' + '\n'.join([f"## {date}\n" + '\n'.join([f"- [{item.get('title')}]({item.get('path')}) · {item.get('category')}" for item in items]) for date, items in sorted(date_groups.items(), reverse=True)]),
        },
        {
            'path': 'moc-by-category.md',
            'kind': 'moc',
            'category': 'operations',
            'title': 'MOC by Category',
            'summary': 'Category index for docs and action notes.',
            'content': '# MOC by Category\n\n' + '\n'.join([f"## {cat}\n" + '\n'.join([f"- [{item.get('title')}]({item.get('path')})" for item in items]) for cat, items in sorted(category_groups.items())]),
        },
    ]
    for doc in docs:
        files.append({**doc, 'kind': 'living_doc', 'content': _render_doc(doc)})
    for action in actions:
        content = '\n'.join([
            f"# {action['title']}",
            '',
            f"- date: {action['date']}",
            f"- category: {action['category']}",
            f"- event_type: {action['event_type']}",
            f"- command: {action['command']}",
            '- raw transcript copied: false',
            '',
            '## Summary',
            action['summary'],
        ])
        files.append({**action, 'kind': 'action_note', 'content': content})
    by_category = {cat: len(items) for cat, items in category_groups.items()}
    return {
        'schema_version': 'goc.room_docs_browser/v1',
        'thread_id': thread.id,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'summary': {
            'file_count': len(files),
            'action_count': len(actions),
            'doc_count': len(docs),
            'event_count': len(events),
            'by_category': by_category,
        },
        'navigation': ['AGENTS.md', 'moc-structure.md', 'moc-by-date.md', 'moc-by-category.md', 'docs/*', 'action/*'],
        'files': files,
    }
