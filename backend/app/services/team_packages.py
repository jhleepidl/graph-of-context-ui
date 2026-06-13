from __future__ import annotations

import json
import re
from typing import Any

from sqlmodel import Session, select

from app.models import AgentPackageRecord, Thread, utcnow


def _clean(value: Any = '', max_len: int = 2000) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text[:max_len]


def _id(value: Any = '', fallback: str = 'team_package') -> str:
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


def _package_payload(body: dict[str, Any]) -> dict[str, Any]:
    for key in ('package', 'team_package', 'teamPackage'):
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


def _sanitize_agent(raw: Any, index: int) -> dict[str, Any]:
    row = _as_dict(raw)
    agent_id = _id(row.get('agent_id') or row.get('id') or row.get('name') or f'agent_{index + 1}', f'agent_{index + 1}')
    return {
        'agent_id': agent_id,
        'name': _clean(row.get('name') or row.get('display_name') or row.get('displayName') or agent_id, 120),
        'role': _id(row.get('role') or 'agent', 'agent'),
        'purpose': _clean(row.get('purpose') or row.get('description') or '', 500),
    }


_PRIVATE_KEY_RE = re.compile(r'(credential|secret|token|password|api[_-]?key|provider[_-]?state|runtime[_-]?log|chat[_-]?history|transcript|raw[_-]?message|conversation[_-]?turn|private[_-]?memory|memory[_-]?node|memory[_-]?content|artifact[_-]?content|upload[_-]?content)', re.I)


def _strip_private(value: Any, depth: int = 0) -> Any:
    if depth > 12:
        return None
    if isinstance(value, list):
        return [_strip_private(item, depth + 1) for item in value if _strip_private(item, depth + 1) is not None]
    if not isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    for key, raw in value.items():
        if _PRIVATE_KEY_RE.search(str(key)):
            continue
        next_value = _strip_private(raw, depth + 1)
        if next_value is not None:
            out[key] = next_value
    return out


def sanitize_team_package(raw: dict[str, Any]) -> dict[str, Any]:
    pkg = _package_payload(_as_dict(raw))
    package_id = _id(pkg.get('package_id') or pkg.get('packageId') or pkg.get('id') or pkg.get('title') or 'shared_team_package')
    memory = _as_dict(pkg.get('memory_contract') or pkg.get('memoryContract'))
    clone_policy = _as_dict(pkg.get('clone_policy') or pkg.get('clonePolicy'))
    team_seed = _strip_private(_as_dict(pkg.get('team_seed') or pkg.get('teamSeed') or _as_dict(pkg.get('team_contract')).get('team_config'))) or {}
    required_surfaces = []
    for item in _as_list(memory.get('required_surfaces') or memory.get('surfaces'))[:32]:
        row = _as_dict(item)
        surface_id = _id(row.get('surface_id') or row.get('surfaceId') or row.get('id') or row.get('label'), '')
        if not surface_id:
            continue
        content_policy = _id(row.get('content_policy') or row.get('contentPolicy') or 'schema_only', 'schema_only')
        if content_policy == 'exclude':
            continue
        required_surfaces.append({
            'surface_id': surface_id,
            'label': _clean(row.get('label') or row.get('title') or surface_id, 160),
            'content_policy': content_policy,
        })
    optional_knowledge_packs = []
    for item in _as_list(memory.get('optional_knowledge_packs') or memory.get('optionalKnowledgePacks'))[:32]:
        row = _as_dict(item)
        surface_id = _id(row.get('surface_id') or row.get('id') or row.get('title'), '')
        if not surface_id:
            continue
        optional_knowledge_packs.append({
            'surface_id': surface_id,
            'title': _clean(row.get('title') or row.get('label') or surface_id, 180),
            'install_default': 'ask',
            'refresh_on_clone': True,
        })
    private_exclusions = []
    for item in _as_list(memory.get('private_exclusions') or memory.get('privateExclusions'))[:32]:
        row = _as_dict(item)
        surface_id = _id(row.get('surface_id') or row.get('id') or row.get('label'), '')
        if not surface_id:
            continue
        private_exclusions.append({
            'surface_id': surface_id,
            'label': _clean(row.get('label') or row.get('title') or surface_id, 160),
            'reason': _clean(row.get('reason') or 'private memory excluded', 300),
        })
    return {
        **pkg,
        'kind': 'shared_team_package_v1',
        'schema_version': 1,
        'package_id': package_id,
        'title': _clean(pkg.get('title') or package_id, 160) or package_id,
        'description': _clean(pkg.get('description') or '', 2000),
        'visibility': _id(pkg.get('visibility') or 'private_review', 'private_review'),
        'status': _id(pkg.get('status') or pkg.get('publish_state') or 'candidate', 'candidate'),
        'version': _clean(pkg.get('version') or '0.1.0', 40) or '0.1.0',
        'license': _clean(pkg.get('license') or 'unlicensed', 80) or 'unlicensed',
        'tags': _unique_strings(pkg.get('tags') or [], limit=16),
        'agents': [_sanitize_agent(agent, index) for index, agent in enumerate(_as_list(pkg.get('agents'))[:24])],
        'runtime_rules': [_clean(rule, 800) for rule in _as_list(pkg.get('runtime_rules') or pkg.get('runtimeRules')) if _clean(rule, 800)][:32],
        'memory_contract': {
            **memory,
            'copies_private_memory': False,
            'initial_mode': 'fresh_private_on_clone',
            'publish_memory_content_by_default': False,
            'required_surfaces': required_surfaces,
            'optional_knowledge_packs': optional_knowledge_packs,
            'private_exclusions': private_exclusions,
        },
        'clone_policy': {
            **clone_policy,
            'private_memory': 'fresh_on_clone',
            'credential_binding': 'never_copy',
            'provider_state': 'never_copy',
            'runtime_logs': 'never_copy',
        },
        'team_seed': team_seed,
        'safety_report': {
            **_as_dict(pkg.get('safety_report') or pkg.get('safetyReport')),
            'clone_safe': True,
            'copies_private_memory': False,
            'credentials_copied': False,
            'provider_state_copied': False,
        },
    }


def team_package_to_row(row: AgentPackageRecord) -> dict[str, Any]:
    payload = sanitize_team_package(_loads(row.package_json, {}))
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


def upsert_thread_team_package(session: Session, thread: Thread, payload: dict[str, Any], *, source: str = 'ddalggak') -> dict[str, Any]:
    pkg = sanitize_team_package(payload)
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
    row.rule_count = len(_as_list(pkg.get('runtime_rules')))
    row.copies_private_memory = False
    row.package_json = _dumps(pkg)
    row.updated_at = utcnow()
    session.add(row)
    session.commit()
    session.refresh(row)
    return {'ok': True, 'package': team_package_to_row(row)}


def list_thread_team_packages(session: Session, thread: Thread, *, limit: int = 100) -> dict[str, Any]:
    stmt = select(AgentPackageRecord).where(AgentPackageRecord.thread_id == thread.id)
    rows = list(session.exec(stmt.order_by(AgentPackageRecord.updated_at.desc()).limit(max(1, min(int(limit or 100), 500)))))
    items = [team_package_to_row(row) for row in rows if _loads(row.package_json, {}).get('kind') == 'shared_team_package_v1']
    return {'ok': True, 'thread_id': thread.id, 'summary': summarize_team_packages(items), 'items': items}


def summarize_team_packages(items: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_visibility: dict[str, int] = {}
    clone_safe = 0
    for item in items:
        by_status[item.get('status') or 'candidate'] = by_status.get(item.get('status') or 'candidate', 0) + 1
        by_visibility[item.get('visibility') or 'private_review'] = by_visibility.get(item.get('visibility') or 'private_review', 0) + 1
        if not item.get('copies_private_memory'):
            clone_safe += 1
    return {'package_count': len(items), 'by_status': by_status, 'by_visibility': by_visibility, 'clone_safe_count': clone_safe}


def list_public_team_library(session: Session, *, query: str = '', limit: int = 100) -> dict[str, Any]:
    q = _clean(query, 200).lower()
    stmt = select(AgentPackageRecord).order_by(AgentPackageRecord.updated_at.desc()).limit(max(1, min(int(limit or 100) * 4, 1000)))
    rows = list(session.exec(stmt))
    items: list[dict[str, Any]] = []
    for row in rows:
        payload = _loads(row.package_json, {})
        if payload.get('kind') != 'shared_team_package_v1':
            continue
        if row.visibility not in {'public', 'unlisted'} and payload.get('visibility') not in {'public', 'unlisted'}:
            continue
        item = team_package_to_row(row)
        if q:
            haystack = ' '.join([
                item.get('package_id') or '',
                item.get('title') or '',
                item.get('description') or '',
                ' '.join(_as_list(_as_dict(item.get('package')).get('tags'))),
                ' '.join(f"{agent.get('role')} {agent.get('name')} {agent.get('purpose')}" for agent in _as_list(_as_dict(item.get('package')).get('agents'))),
            ]).lower()
            if q not in haystack:
                continue
        items.append(item)
        if len(items) >= max(1, min(int(limit or 100), 500)):
            break
    return {'ok': True, 'summary': summarize_team_packages(items), 'items': items, 'query': q}


def get_public_team_package(session: Session, package_id: str) -> dict[str, Any] | None:
    clean_id = _id(package_id, '')
    if not clean_id:
        return None
    rows = list(session.exec(select(AgentPackageRecord).where(AgentPackageRecord.package_id == clean_id).order_by(AgentPackageRecord.updated_at.desc()).limit(20)))
    for row in rows:
        payload = _loads(row.package_json, {})
        if payload.get('kind') != 'shared_team_package_v1':
            continue
        if row.visibility in {'public', 'unlisted'} or payload.get('visibility') in {'public', 'unlisted'}:
            return team_package_to_row(row)
    return None


def build_team_package_fork_preview(package: dict[str, Any], *, title: str | None = None) -> dict[str, Any]:
    pkg = sanitize_team_package(package.get('package') if isinstance(package.get('package'), dict) else package)
    new_title = _clean(title or f"{pkg['title']} Fork", 160)
    fork_id = f"{_id(new_title)}_{utcnow().strftime('%Y%m%d%H%M%S')}"
    forked = sanitize_team_package({
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
    return {'ok': True, 'package': forked, 'install_policy': forked.get('install_policy') or {}, 'clone_policy': forked.get('clone_policy') or {}}
