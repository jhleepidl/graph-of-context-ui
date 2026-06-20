from __future__ import annotations

import json
import re
from typing import Any

from sqlmodel import Session, select

from app.models import AgentPackageRecord, Thread, utcnow


def _clean(value: Any = '', max_len: int = 2000) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text[:max_len]


def _id(value: Any = '', fallback: str = 'room_package') -> str:
    text = _clean(value or fallback, 180).lower()
    clean = re.sub(r'[^a-z0-9가-힣._:-]+', '_', text).strip('_')
    return clean or fallback


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


_PRIVATE_KEY_RE = re.compile(
    r'(credential|secret|token|password|api[_-]?key|provider[_-]?state|runtime[_-]?log|chat[_-]?history|transcript|raw[_-]?message|conversation[_-]?turn|private[_-]?memory|memory[_-]?content|artifact[_-]?content|upload[_-]?content|health[_-]?record|portfolio[_-]?holding|personal[_-]?note)',
    re.I,
)


def _strip_private(value: Any, depth: int = 0) -> Any:
    if depth > 12:
        return None
    if isinstance(value, list):
        out = []
        for item in value:
            cleaned = _strip_private(item, depth + 1)
            if cleaned is not None:
                out.append(cleaned)
        return out
    if not isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    for key, raw in value.items():
        if _PRIVATE_KEY_RE.search(str(key)):
            continue
        cleaned = _strip_private(raw, depth + 1)
        if cleaned is not None:
            out[key] = cleaned
    return out


def _package_payload(body: dict[str, Any]) -> dict[str, Any]:
    for key in ('package', 'room_package', 'roomPackage'):
        if isinstance(body.get(key), dict):
            return _as_dict(body.get(key))
    return body


def _unique_strings(values: Any, *, limit: int = 64) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in _as_list(values):
        text = _clean(raw, 180)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


def sanitize_room_package(raw: dict[str, Any]) -> dict[str, Any]:
    pkg = _strip_private(_package_payload(_as_dict(raw))) or {}
    package_id = _id(pkg.get('package_id') or pkg.get('packageId') or pkg.get('id') or pkg.get('title') or 'shared_room_package')
    memory = _as_dict(pkg.get('memory_schema') or pkg.get('memorySchema'))
    context = _as_dict(pkg.get('context_policy') or pkg.get('contextPolicy'))
    prompt = _as_dict(pkg.get('prompt_policy') or pkg.get('promptPolicy'))
    approval = _as_dict(pkg.get('approval_policy') or pkg.get('approvalPolicy') or pkg.get('autonomy_policy') or pkg.get('autonomyPolicy'))
    agents = _unique_strings(pkg.get('agents') or pkg.get('agent_roles') or pkg.get('agentRoles'), limit=32)
    examples = []
    for item in _as_list(pkg.get('examples') or pkg.get('interaction_examples') or pkg.get('interactionExamples'))[:24]:
        row = _as_dict(item)
        user = _clean(row.get('user') or row.get('input') or '', 500)
        room = _clean(row.get('room') or row.get('output') or row.get('response') or '', 700)
        if user or room:
            examples.append({'user': user, 'room': room})
    return {
        **pkg,
        'kind': 'shared_room_package_v1',
        'schema_version': 1,
        'package_id': package_id,
        'title': _clean(pkg.get('title') or pkg.get('name') or package_id, 160) or package_id,
        'description': _clean(pkg.get('description') or pkg.get('purpose') or '', 2000),
        'visibility': _id(pkg.get('visibility') or 'private_review', 'private_review'),
        'status': _id(pkg.get('status') or pkg.get('publish_state') or 'candidate', 'candidate'),
        'version': _clean(pkg.get('version') or '0.1.0', 40) or '0.1.0',
        'license': _clean(pkg.get('license') or 'unlicensed', 80) or 'unlicensed',
        'domain_label': _id(pkg.get('domain_label') or pkg.get('domainLabel') or pkg.get('domain') or 'general_workbench', 'general_workbench'),
        'agents': agents,
        'default_depth': _id(pkg.get('default_depth') or pkg.get('defaultDepth') or 'ask', 'ask'),
        'memory_schema': {
            **memory,
            'object_types': _unique_strings(memory.get('object_types') or memory.get('objectTypes') or pkg.get('memory_object_types') or [], limit=96),
            'private_memory_export': 'never_by_default',
            'copies_private_memory': False,
        },
        'prompt_policy': prompt,
        'context_policy': {
            **context,
            'shared_package_copies_private_memory': False,
            'private_memory': context.get('private_memory') or context.get('privateMemory') or 'least_privilege',
            'cross_room_memory': context.get('cross_room_memory') or context.get('crossRoomMemory') or 'ask_before_use',
        },
        'approval_policy': approval,
        'examples': examples,
        'tags': _unique_strings(pkg.get('tags') or [], limit=32),
        'safety_report': {
            **_as_dict(pkg.get('safety_report') or pkg.get('safetyReport')),
            'clone_safe': True,
            'copies_private_memory': False,
            'credentials_copied': False,
            'provider_state_copied': False,
            'private_files_copied': False,
        },
        'install_policy': {
            **_as_dict(pkg.get('install_policy') or pkg.get('installPolicy')),
            'private_memory': 'fresh_on_install',
            'credentials': 'never_copy',
            'user_must_approve_memory_import': True,
        },
    }


def room_package_to_row(row: AgentPackageRecord) -> dict[str, Any]:
    payload = sanitize_room_package(_loads(row.package_json, {}))
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


def summarize_room_packages(items: list[dict[str, Any]]) -> dict[str, Any]:
    by_domain: dict[str, int] = {}
    by_status: dict[str, int] = {}
    clone_safe = 0
    for item in items:
        pkg = _as_dict(item.get('package'))
        by_domain[pkg.get('domain_label') or 'general_workbench'] = by_domain.get(pkg.get('domain_label') or 'general_workbench', 0) + 1
        by_status[item.get('status') or 'candidate'] = by_status.get(item.get('status') or 'candidate', 0) + 1
        if not item.get('copies_private_memory'):
            clone_safe += 1
    return {'package_count': len(items), 'by_domain': by_domain, 'by_status': by_status, 'clone_safe_count': clone_safe}


def upsert_thread_room_package(session: Session, thread: Thread, payload: dict[str, Any], *, source: str = 'ddalggak') -> dict[str, Any]:
    pkg = sanitize_room_package(payload)
    package_id = pkg['package_id']
    existing = session.exec(select(AgentPackageRecord).where(AgentPackageRecord.thread_id == thread.id, AgentPackageRecord.package_id == package_id)).first()
    row = existing or AgentPackageRecord(thread_id=thread.id, package_id=package_id)
    row.run_id = _clean(payload.get('run_id') or payload.get('runId') or pkg.get('run_id') or pkg.get('runId') or '', 160) or row.run_id
    row.title = pkg['title']
    row.description = pkg['description']
    row.visibility = pkg['visibility']
    row.status = pkg['status']
    row.source = _clean(source or 'ddalggak', 120)
    source_payload = _as_dict(pkg.get('source'))
    row.source_thread_id = _clean(source_payload.get('thread_id') or source_payload.get('threadId') or '', 160)
    row.source_chat_id = _clean(source_payload.get('chat_id') or source_payload.get('chatId') or '', 160)
    row.agent_count = len(_as_list(pkg.get('agents')))
    row.skill_count = len(_as_list(pkg.get('skill_refs') or pkg.get('skillRefs')))
    row.rule_count = len(_as_list(pkg.get('runtime_rules') or pkg.get('runtimeRules')))
    row.copies_private_memory = False
    row.package_json = _dumps(pkg)
    row.updated_at = utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return {'ok': True, 'package': room_package_to_row(row)}


def list_thread_room_packages(session: Session, thread: Thread, *, limit: int = 100) -> dict[str, Any]:
    stmt = select(AgentPackageRecord).where(AgentPackageRecord.thread_id == thread.id)
    rows = list(session.exec(stmt.order_by(AgentPackageRecord.updated_at.desc()).limit(max(1, min(int(limit or 100), 500)))))
    items = [room_package_to_row(row) for row in rows if _loads(row.package_json, {}).get('kind') == 'shared_room_package_v1']
    return {'ok': True, 'thread_id': thread.id, 'summary': summarize_room_packages(items), 'items': items}


def list_public_room_library(session: Session, *, query: str = '', limit: int = 100) -> dict[str, Any]:
    q = _clean(query, 200).lower()
    stmt = select(AgentPackageRecord).order_by(AgentPackageRecord.updated_at.desc()).limit(max(1, min(int(limit or 100) * 4, 1000)))
    items: list[dict[str, Any]] = []
    for row in list(session.exec(stmt)):
        payload = _loads(row.package_json, {})
        if payload.get('kind') != 'shared_room_package_v1':
            continue
        if row.visibility not in {'public', 'unlisted'} and payload.get('visibility') not in {'public', 'unlisted'}:
            continue
        item = room_package_to_row(row)
        pkg = _as_dict(item.get('package'))
        if q:
            haystack = ' '.join([
                item.get('package_id') or '', item.get('title') or '', item.get('description') or '',
                pkg.get('domain_label') or '', ' '.join(_as_list(pkg.get('tags'))), ' '.join(_as_list(pkg.get('agents'))),
            ]).lower()
            if q not in haystack:
                continue
        items.append(item)
        if len(items) >= max(1, min(int(limit or 100), 500)):
            break
    return {'ok': True, 'summary': summarize_room_packages(items), 'items': items, 'query': q}


def get_public_room_package(session: Session, package_id: str) -> dict[str, Any] | None:
    clean_id = _id(package_id, '')
    if not clean_id:
        return None
    rows = list(session.exec(select(AgentPackageRecord).where(AgentPackageRecord.package_id == clean_id).order_by(AgentPackageRecord.updated_at.desc()).limit(20)))
    for row in rows:
        payload = _loads(row.package_json, {})
        if payload.get('kind') != 'shared_room_package_v1':
            continue
        if row.visibility in {'public', 'unlisted'} or payload.get('visibility') in {'public', 'unlisted'}:
            return room_package_to_row(row)
    return None


def build_room_package_fork_preview(package: dict[str, Any], *, title: str | None = None) -> dict[str, Any]:
    pkg = sanitize_room_package(package.get('package') if isinstance(package.get('package'), dict) else package)
    new_title = _clean(title or f"{pkg['title']} Fork", 160)
    fork_id = f"{_id(new_title)}_{utcnow().strftime('%Y%m%d%H%M%S')}"
    forked = sanitize_room_package({
        **pkg,
        'package_id': fork_id,
        'title': new_title,
        'visibility': 'private_review',
        'status': 'candidate',
        'lineage': {
            **_as_dict(pkg.get('lineage')),
            'parent_package_id': pkg['package_id'],
            'forked_from': pkg['package_id'],
        },
    })
    return {'ok': True, 'package': forked, 'install_policy': forked.get('install_policy') or {}, 'context_policy': forked.get('context_policy') or {}}
