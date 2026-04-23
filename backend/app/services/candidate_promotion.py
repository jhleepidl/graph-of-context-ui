from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from app.auth import get_current_principal
from app.models import ContextSet, Node, Thread
from app.services.context_versions import snapshot_context_set
from app.services.graph import add_edge, get_last_node
from app.services.learning_policy import is_promotion_candidate_payload
from app.services.public_library import ensure_public_library_thread, ensure_public_skill_library_thread
from app.services.runtime_snapshot import node_payload
from app.services.skill_registry import normalize_skill_package


def _clean_text(value: Any, max_len: int = 512) -> str:
    return str(value or '').strip()[:max_len]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _jdump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _slug(value: Any) -> str:
    raw = _clean_text(value, 256).lower()
    if not raw:
        return 'item'
    slug = re.sub(r'[^a-z0-9]+', '-', raw).strip('-')
    return slug or 'item'


def _load_or_create_first_context_set(session: Session, *, thread_id: str) -> ContextSet:
    context_set = session.exec(
        select(ContextSet)
        .where(ContextSet.thread_id == thread_id)
        .order_by(ContextSet.created_at.asc(), ContextSet.id.asc())
        .limit(1)
    ).first()
    if context_set:
        return context_set
    context_set = ContextSet(thread_id=thread_id, name='default')
    session.add(context_set)
    session.flush()
    snapshot_context_set(
        session,
        context_set,
        reason='create',
        meta={'name': context_set.name, 'thread_id': thread_id},
    )
    return context_set


def _activate_node_in_context_set(session: Session, *, context_set: ContextSet, node_id: str, resource_kind: str) -> None:
    try:
        active_ids = json.loads(context_set.active_node_ids_json or '[]')
    except Exception:
        active_ids = []
    if node_id in active_ids:
        return
    active_ids.append(node_id)
    context_set.active_node_ids_json = _jdump(active_ids)
    snapshot_context_set(
        session,
        context_set,
        reason='add_resource',
        changed_node_ids=[node_id],
        meta={'node_type': 'Resource', 'resource_kind': resource_kind},
    )


def _create_resource_node(
    session: Session,
    *,
    thread: Thread,
    context_set: ContextSet,
    resource_kind: str,
    title: str,
    summary: str,
    document: dict[str, Any],
    origin: dict[str, Any],
    source: str = 'candidate_promotion',
) -> Node:
    payload = {
        'name': title,
        'title': title,
        'summary': summary or None,
        'resource_kind': resource_kind,
        'context_set_id': context_set.id,
        'source': source,
        'board_visible': True,
        'tag': 'RESOURCE',
        'shareability': 'thread_reusable',
        'privacy_class': 'structured_promoted',
        'promotion_status': 'promoted',
        'review_status': 'approved',
        'origin': origin,
    }
    if resource_kind == 'skill_package':
        payload['skill_package'] = document
    elif resource_kind == 'team_blueprint':
        payload['team_blueprint'] = document
    else:
        payload['document'] = document
    last = get_last_node(session, thread.id)
    node = Node(
        thread_id=thread.id,
        type='Resource',
        text=_jdump(document),
        payload_json=_jdump(payload),
    )
    session.add(node)
    session.flush()
    if last and last.id != node.id:
        session.add(add_edge(thread.id, last.id, node.id, 'NEXT'))
    _activate_node_in_context_set(session, context_set=context_set, node_id=node.id, resource_kind=resource_kind)
    return node


def _promote_skill_candidate(candidate_payload: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    normalized_candidate = _as_dict(candidate_payload.get('normalized_candidate'))
    requested = {
        'id': _clean_text(normalized_candidate.get('skill_id') or candidate_payload.get('title') or candidate_payload.get('candidate_key')),
        'name': _clean_text(candidate_payload.get('title') or normalized_candidate.get('skill_id') or 'Promoted skill package'),
        'description': _clean_text(candidate_payload.get('summary')) or None,
        'visibility': 'internal',
        'status': 'active',
        'source': 'candidate_promotion',
        'trust_level': 'review_required',
        'side_effect_level': 'unknown',
    }
    package = normalize_skill_package(requested, source_key='candidate_promotion') or requested
    title = _clean_text(package.get('name') or package.get('id') or 'Promoted skill package', 160)
    summary = _clean_text(package.get('description') or candidate_payload.get('summary') or 'Promoted from board candidate', 320)
    package['promoted_from_candidate'] = {
        'candidate_key': _clean_text(candidate_payload.get('candidate_key')) or None,
        'derived_from_history_title': _clean_text(candidate_payload.get('derived_from_history_title')) or None,
    }
    return title, summary, package


def _build_team_blueprint_document(candidate_payload: dict[str, Any]) -> dict[str, Any]:
    normalized_candidate = _as_dict(candidate_payload.get('normalized_candidate'))
    team_name = _clean_text(normalized_candidate.get('team_name') or normalized_candidate.get('label') or candidate_payload.get('title') or 'Promoted Team', 160) or 'Promoted Team'
    roles = [_clean_text(v, 96) for v in _as_list(normalized_candidate.get('roles')) if _clean_text(v, 96)]
    attached_skill_ids = [_clean_text(v, 128) for v in _as_list(normalized_candidate.get('attached_skill_ids')) if _clean_text(v, 128)]
    source_phase = _clean_text(normalized_candidate.get('source_phase') or 'runtime', 64) or 'runtime'
    agent_count = int(normalized_candidate.get('agent_count') or len(roles) or 1)
    if not roles:
        roles = ['operator'] if agent_count <= 1 else [f'agent_{idx + 1}' for idx in range(agent_count)]
    blueprint_id = f"promoted.team.{_slug(team_name)}.v1"
    agents = []
    for idx, role in enumerate(roles[:max(1, agent_count)]):
        agents.append({
            'agent_id': f'{_slug(role or f"agent-{idx + 1}")}_{idx + 1}',
            'name': role.replace('_', ' ').title() or f'Agent {idx + 1}',
            'role': role,
            'attached_skill_ids': attached_skill_ids if idx == 0 else [],
        })
    participants = [
        {
            'participant_id': agent['agent_id'],
            'role': agent['role'],
            'label': agent['name'],
            'attached_skill_ids': list(agent.get('attached_skill_ids') or []),
        }
        for agent in agents
    ]
    return {
        'kind': 'ddalggak_team_blueprint',
        'version': 1,
        'primary_schema': 'team_blueprint_v1',
        'summary': {
            'source_phase': source_phase,
            'promoted_from_candidate_key': _clean_text(candidate_payload.get('candidate_key')) or None,
            'derived_from_history_title': _clean_text(candidate_payload.get('derived_from_history_title')) or None,
            'review_note': 'Auto-promoted from structured board candidate. Capability and routing details still need human review.',
            'attached_skill_ids': attached_skill_ids,
            'role_ids': roles,
            'agent_count': len(agents),
        },
        'blueprint': {
            'blueprint_id': blueprint_id,
            'title': team_name,
            'description': _clean_text(candidate_payload.get('summary') or f'Promoted from {source_phase} runtime history', 320) or f'Promoted from {source_phase} runtime history',
            'task_archetype': 'general',
            'topology': {
                'pattern': 'single' if len(agents) <= 1 else 'parallel',
                'participants': participants,
                'edges': [],
            },
            'catalog': {
                'tags': ['promoted', 'board-approved', 'raw-history-derived'],
                'good_for': [],
                'bad_for': [],
            },
            'runtime_policy': {
                'runtime_execution': {
                    'mode': 'review_required',
                    'note': 'Derived from runtime observations; review before direct installation.',
                },
            },
            'team_seed': {
                'team_name': team_name,
                'agents': agents,
                'attached_skill_ids': attached_skill_ids,
            },
        },
        'team': {
            'team_name': team_name,
            'agents': agents,
            'attached_skill_ids': attached_skill_ids,
        },
    }


def _promote_team_candidate(candidate_payload: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    document = _build_team_blueprint_document(candidate_payload)
    title = _clean_text((document.get('blueprint') or {}).get('title') or candidate_payload.get('title') or 'Promoted team blueprint', 160)
    summary = _clean_text((document.get('blueprint') or {}).get('description') or candidate_payload.get('summary') or 'Promoted from board candidate', 320)
    return title, summary, document


def approve_board_candidate(
    session: Session,
    *,
    thread: Thread,
    candidate_node: Node,
    publish_to_library: bool = False,
) -> dict[str, Any]:
    candidate_payload = node_payload(candidate_node)
    if not is_promotion_candidate_payload(candidate_payload):
        raise HTTPException(400, 'node is not a promotion candidate')
    if candidate_payload.get('stale') is True:
        raise HTTPException(409, 'stale candidate cannot be approved')

    candidate_kind = _clean_text(candidate_payload.get('candidate_kind') or '', 64)
    if candidate_kind == 'skill_package':
        resource_kind = 'skill_package'
        title, summary, document = _promote_skill_candidate(candidate_payload)
    elif candidate_kind == 'team_blueprint':
        resource_kind = 'team_blueprint'
        title, summary, document = _promote_team_candidate(candidate_payload)
    else:
        raise HTTPException(400, f'unsupported candidate kind: {candidate_kind or "unknown"}')

    principal = get_current_principal()
    if publish_to_library:
        if resource_kind == 'skill_package':
            target_thread, context_set = ensure_public_skill_library_thread(session)
        else:
            target_thread, context_set = ensure_public_library_thread(session)
    else:
        target_thread = thread
        context_set = _load_or_create_first_context_set(session, thread_id=thread.id)

    promoted_node = _create_resource_node(
        session,
        thread=target_thread,
        context_set=context_set,
        resource_kind=resource_kind,
        title=title,
        summary=summary,
        document=document,
        origin={
            'type': 'candidate_promotion',
            'candidate_node_id': candidate_node.id,
            'candidate_key': _clean_text(candidate_payload.get('candidate_key')) or None,
            'source_thread_id': thread.id,
            'promoted_at': datetime.now(timezone.utc).isoformat(),
            'promoted_by_role': principal.role,
            'promoted_by_service_id': _clean_text(principal.service_id) or None,
            'published_to_library': bool(publish_to_library),
        },
        source='candidate_promotion',
    )
    if target_thread.id == thread.id:
        session.add(add_edge(thread.id, candidate_node.id, promoted_node.id, 'PROMOTED_TO'))

    candidate_payload.update({
        'review_status': 'approved',
        'promotion_status': 'promoted',
        'approved_at': datetime.now(timezone.utc).isoformat(),
        'approved_by_role': principal.role,
        'approved_by_service_id': _clean_text(principal.service_id) or None,
        'promoted_node_id': promoted_node.id,
        'promoted_thread_id': target_thread.id,
        'promoted_resource_kind': resource_kind,
        'published_to_library': bool(publish_to_library),
    })
    candidate_node.payload_json = _jdump(candidate_payload)
    session.add(candidate_node)
    return {
        'candidate': candidate_node,
        'candidate_payload': candidate_payload,
        'promoted_node': promoted_node,
        'promoted_resource_kind': resource_kind,
        'target_thread_id': target_thread.id,
        'published_to_library': bool(publish_to_library),
    }
