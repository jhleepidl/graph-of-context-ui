from __future__ import annotations

import json
import re
from typing import Any

from sqlmodel import Session, select

from app.models import AgentPackageRecord, Thread, utcnow


def _clean(value: Any = '', max_len: int = 2000) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text[:max_len]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _loads(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or '')
    except Exception:
        return default


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _package_payload(body: dict[str, Any]) -> dict[str, Any]:
    if isinstance(body.get('package'), dict):
        return _as_dict(body.get('package'))
    return body


def _count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if value is None:
        return 0
    return 1


def _package_id(pkg: dict[str, Any]) -> str:
    return _clean(pkg.get('package_id') or pkg.get('packageId') or pkg.get('id') or '', 200)


def _to_dict(row: AgentPackageRecord) -> dict[str, Any]:
    payload = _loads(row.package_json, {})
    return {
        'id': row.id,
        'thread_id': row.thread_id,
        'run_id': row.run_id,
        'package_id': row.package_id,
        'title': row.title,
        'description': row.description,
        'visibility': row.visibility,
        'status': row.status,
        'source': row.source,
        'source_thread_id': row.source_thread_id,
        'source_chat_id': row.source_chat_id,
        'agent_count': row.agent_count,
        'skill_count': row.skill_count,
        'rule_count': row.rule_count,
        'copies_private_memory': row.copies_private_memory,
        'package': payload,
        'created_at': row.created_at.isoformat(),
        'updated_at': row.updated_at.isoformat(),
    }


def summarize_agent_packages(rows: list[AgentPackageRecord]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    clone_safe = 0
    for row in rows:
        by_status[row.status] = by_status.get(row.status, 0) + 1
        if not row.copies_private_memory:
            clone_safe += 1
    return {'package_count': len(rows), 'by_status': by_status, 'clone_safe_count': clone_safe}


def upsert_agent_package(session: Session, thread: Thread, payload: dict[str, Any], *, source: str = 'ddalggak') -> dict[str, Any]:
    body = _as_dict(payload)
    pkg = _package_payload(body)
    package_id = _package_id(pkg)
    if not package_id:
        raise ValueError('package_id is required')
    source_payload = _as_dict(pkg.get('source'))
    memory_contract = _as_dict(pkg.get('memory_contract') or pkg.get('memoryContract'))
    clone_policy = _as_dict(pkg.get('clone_policy') or pkg.get('clonePolicy'))
    existing = session.exec(select(AgentPackageRecord).where(AgentPackageRecord.thread_id == thread.id, AgentPackageRecord.package_id == package_id)).first()
    row = existing or AgentPackageRecord(thread_id=thread.id, package_id=package_id)
    row.run_id = _clean(body.get('run_id') or body.get('runId') or pkg.get('run_id') or pkg.get('runId') or '', 160) or row.run_id
    row.title = _clean(pkg.get('title') or pkg.get('display_name') or package_id, 300)
    row.description = _clean(pkg.get('description') or '', 2000)
    row.visibility = _clean(pkg.get('visibility') or body.get('visibility') or row.visibility or 'private_review', 100)
    row.status = _clean(pkg.get('status') or body.get('status') or row.status or 'candidate', 100)
    row.source = _clean(body.get('source') or pkg.get('source_system') or source or 'ddalggak', 120)
    row.source_thread_id = _clean(source_payload.get('thread_id') or source_payload.get('threadId') or '', 160)
    row.source_chat_id = _clean(source_payload.get('chat_id') or source_payload.get('chatId') or '', 160)
    row.agent_count = _count(pkg.get('agents'))
    row.skill_count = _count(pkg.get('skill_refs') or pkg.get('skillRefs'))
    row.rule_count = _count(pkg.get('rule_refs') or pkg.get('ruleRefs'))
    row.copies_private_memory = bool(memory_contract.get('copies_private_memory') or clone_policy.get('private_memory') == 'copy')
    row.package_json = _dumps(pkg)
    row.updated_at = utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return {'ok': True, 'package': _to_dict(row)}


def list_agent_packages(session: Session, thread: Thread, *, include_public: bool = True, limit: int = 100) -> dict[str, Any]:
    stmt = select(AgentPackageRecord).where(AgentPackageRecord.thread_id == thread.id)
    rows = list(session.exec(stmt.order_by(AgentPackageRecord.updated_at.desc()).limit(max(1, min(int(limit or 100), 500)))))
    return {'ok': True, 'thread_id': thread.id, 'summary': summarize_agent_packages(rows), 'items': [_to_dict(row) for row in rows]}
