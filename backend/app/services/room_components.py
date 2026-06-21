from __future__ import annotations

import json
import re
from typing import Any


def _clean(value: Any = '', max_len: int = 2000, *, lower: bool = False) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    text = text[:max_len]
    return text.lower() if lower else text


def _id(value: Any = '', fallback: str = 'component') -> str:
    text = _clean(value or fallback, 180, lower=True)
    clean = re.sub(r'[^a-z0-9가-힣._:-]+', '_', text).strip('_')
    return clean or fallback


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _unique_strings(values: Any, *, limit: int = 64, lower: bool = False) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in _as_list(values):
        text = _clean(raw, 220, lower=lower)
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    return out


_PRIVATE_KEY_RE = re.compile(
    r'(credential|secret|token|password|api[_-]?key|provider[_-]?state|runtime[_-]?log|chat[_-]?history|transcript|raw[_-]?message|conversation[_-]?turn|private[_-]?memory[_-]?content|memory[_-]?content|artifact[_-]?content|upload[_-]?content|health[_-]?record|portfolio[_-]?holding|personal[_-]?note|source[_-]?file|raw[_-]?file)',
    re.I,
)


COMPONENT_TYPES = {
    'agent': 'agent_card',
    'memory_schema': 'memory_schema_card',
    'prompt_policy': 'prompt_policy_card',
    'context_policy': 'context_policy_card',
    'approval_policy': 'approval_policy_card',
    'evaluation': 'evaluation_criteria_card',
    'interaction_guide': 'interaction_guide_card',
}


def strip_private_component_fields(value: Any, depth: int = 0) -> Any:
    if depth > 12:
        return None
    if isinstance(value, list):
        return [item for item in (strip_private_component_fields(v, depth + 1) for v in value) if item is not None]
    if not isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    for key, raw in value.items():
        if _PRIVATE_KEY_RE.search(str(key)):
            continue
        cleaned = strip_private_component_fields(raw, depth + 1)
        if cleaned is not None:
            out[key] = cleaned
    return out


def _component_id(kind: str, value: Any, fallback: str) -> str:
    return f"{kind}:{_id(value or fallback, fallback)}"


def normalize_agent_card(raw: Any, *, source_package_id: str = '', domain_label: str = '') -> dict[str, Any]:
    row = {'id': raw, 'role': raw, 'title': raw} if isinstance(raw, str) else _as_dict(raw)
    role = _id(row.get('role') or row.get('role_id') or row.get('id') or row.get('agent_id') or row.get('title') or row.get('name') or 'agent', 'agent')
    card = {
        'kind': 'room_component_v1',
        'component_type': COMPONENT_TYPES['agent'],
        'component_id': _component_id(COMPONENT_TYPES['agent'], row.get('id') or row.get('agent_id') or role, role),
        'local_id': role,
        'source_package_id': source_package_id,
        'domain_label': domain_label,
        'title': _clean(row.get('title') or row.get('name') or role, 120),
        'role': role,
        'description': _clean(row.get('description') or row.get('summary') or '', 1200),
        'instructions': _clean(row.get('instructions') or row.get('prompt') or row.get('base_prompt') or '', 2000),
        'input_contract': _as_dict(row.get('input_contract') or row.get('inputContract')),
        'output_contract': _as_dict(row.get('output_contract') or row.get('outputContract')),
        'memory_access': {
            **_as_dict(row.get('memory_access') or row.get('memoryAccess')),
            'read_private_source_room_memory': False,
            'read_target_room_projection': True,
            'write_memory_directly': False,
            'allow_propose_update': True,
            'reads': _unique_strings(row.get('reads') or row.get('memory_reads') or row.get('memoryReads') or [], limit=48, lower=True),
            'proposes_updates': _unique_strings(row.get('proposes_updates') or row.get('proposesUpdates') or row.get('memory_writes') or row.get('memoryWrites') or [], limit=48, lower=True),
        },
        'tool_policy': {
            **_as_dict(row.get('tool_policy') or row.get('toolPolicy')),
            'allowed_tools': _unique_strings(row.get('allowed_tools') or row.get('allowedTools') or row.get('tools') or [], limit=32, lower=True),
            'external_side_effects': row.get('external_side_effects') or row.get('externalSideEffects') or 'approval_required',
        },
        'install_policy': {
            **_as_dict(row.get('install_policy') or row.get('installPolicy')),
            'default_scope': row.get('default_scope') or row.get('defaultScope') or 'borrow_single_attempt',
            'can_borrow': row.get('can_borrow') is not False,
            'can_install_resident': row.get('can_install_resident') is not False,
            'can_fork': row.get('can_fork') is not False,
        },
        'tags': _unique_strings(row.get('tags') or [domain_label, role], limit=32, lower=True),
    }
    return strip_private_component_fields(card)


def normalize_memory_schema_card(raw: Any, *, source_package_id: str = '', domain_label: str = '') -> dict[str, Any]:
    row = _as_dict(raw)
    title = _clean(row.get('title') or f'{domain_label or "room"} memory schema', 120)
    card = {
        'kind': 'room_component_v1',
        'component_type': COMPONENT_TYPES['memory_schema'],
        'component_id': _component_id(COMPONENT_TYPES['memory_schema'], row.get('id') or title, 'memory_schema'),
        'local_id': _id(row.get('id') or 'memory_schema', 'memory_schema'),
        'source_package_id': source_package_id,
        'domain_label': domain_label,
        'title': title,
        'description': _clean(row.get('description') or '', 1000),
        'object_types': _unique_strings(row.get('object_types') or row.get('objectTypes') or row.get('objects') or [], limit=96, lower=True),
        'schemas': _as_dict(row.get('schemas') or row.get('object_schemas') or row.get('objectSchemas')),
        'retention_policy': _clean(row.get('retention_policy') or row.get('retentionPolicy') or 'room_local_by_default', 200),
        'export_policy': {
            'copies_private_memory': False,
            'private_memory_export': 'never_by_default',
        },
        'agent_read_policy': _as_dict(row.get('agent_read_policy') or row.get('agentReadPolicy')),
        'agent_write_policy': {
            **_as_dict(row.get('agent_write_policy') or row.get('agentWritePolicy')),
            'direct_write': False,
            'proposal_only': True,
        },
        'tags': _unique_strings(row.get('tags') or [domain_label, 'memory'], limit=32, lower=True),
    }
    return strip_private_component_fields(card)


def normalize_policy_card(kind: str, raw: Any, *, source_package_id: str = '', domain_label: str = '', title: str = '') -> dict[str, Any]:
    row = _as_dict(raw)
    local = _id(row.get('id') or title or kind, kind)
    return strip_private_component_fields({
        'kind': 'room_component_v1',
        'component_type': kind,
        'component_id': _component_id(kind, row.get('id') or title or local, local),
        'local_id': local,
        'source_package_id': source_package_id,
        'domain_label': domain_label,
        'title': _clean(row.get('title') or title or local, 120),
        'description': _clean(row.get('description') or '', 1000),
        'policy': row.get('policy') if isinstance(row.get('policy'), dict) else row,
        'reusable': row.get('reusable') is not False,
        'tags': _unique_strings(row.get('tags') or [domain_label, kind], limit=32, lower=True),
    })


def summarize_components(components: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    reusable_agents = 0
    for component in components:
        ctype = component.get('component_type') or 'unknown'
        counts[ctype] = counts.get(ctype, 0) + 1
        if ctype == COMPONENT_TYPES['agent'] and _as_dict(component.get('install_policy')).get('can_borrow') is not False:
            reusable_agents += 1
    return {
        'total_components': len(components),
        'component_counts': counts,
        'reusable_agent_count': reusable_agents,
        'private_memory_copied': False,
    }


def build_room_components(package: dict[str, Any]) -> dict[str, Any]:
    pkg = _as_dict(package)
    package_id = _id(pkg.get('package_id') or pkg.get('packageId') or pkg.get('id') or pkg.get('title') or 'room_package', 'room_package')
    domain_label = _id(pkg.get('domain_label') or pkg.get('domainLabel') or pkg.get('domain') or 'general_workbench', 'general_workbench')
    raw_components = _as_dict(pkg.get('components') or pkg.get('component_library') or pkg.get('componentLibrary'))
    agent_rows = _as_list(raw_components.get('agents') or raw_components.get('agent_cards') or raw_components.get('agentCards'))
    if not agent_rows:
        agent_rows = _as_list(pkg.get('agent_cards') or pkg.get('agentCards')) or _unique_strings(pkg.get('agents') or pkg.get('agent_roles') or pkg.get('agentRoles') or [], limit=32, lower=True)
    agents = [normalize_agent_card(agent, source_package_id=package_id, domain_label=domain_label) for agent in agent_rows]
    memory_schema = normalize_memory_schema_card(raw_components.get('memory_schema') or raw_components.get('memorySchema') or pkg.get('memory_schema') or pkg.get('memorySchema'), source_package_id=package_id, domain_label=domain_label)
    prompt_policy = normalize_policy_card(COMPONENT_TYPES['prompt_policy'], raw_components.get('prompt_policy') or raw_components.get('promptPolicy') or pkg.get('prompt_policy') or pkg.get('promptPolicy'), source_package_id=package_id, domain_label=domain_label, title='Prompt policy')
    context_policy = normalize_policy_card(COMPONENT_TYPES['context_policy'], raw_components.get('context_policy') or raw_components.get('contextPolicy') or pkg.get('context_policy') or pkg.get('contextPolicy'), source_package_id=package_id, domain_label=domain_label, title='Context firewall policy')
    approval_policy = normalize_policy_card(COMPONENT_TYPES['approval_policy'], raw_components.get('approval_policy') or raw_components.get('approvalPolicy') or pkg.get('approval_policy') or pkg.get('approvalPolicy') or pkg.get('autonomy_policy') or pkg.get('autonomyPolicy'), source_package_id=package_id, domain_label=domain_label, title='Approval policy')
    evaluation_rows = _as_list(raw_components.get('evaluation_criteria') or raw_components.get('evaluationCriteria') or pkg.get('evaluation_criteria') or pkg.get('evaluationCriteria'))
    evaluation = [normalize_policy_card(COMPONENT_TYPES['evaluation'], row, source_package_id=package_id, domain_label=domain_label, title=f'Evaluation {idx + 1}') for idx, row in enumerate(evaluation_rows)] or [normalize_policy_card(COMPONENT_TYPES['evaluation'], {}, source_package_id=package_id, domain_label=domain_label, title='Evaluation criteria')]
    interaction_guide = normalize_policy_card(COMPONENT_TYPES['interaction_guide'], {'examples': _as_list(pkg.get('examples') or pkg.get('interaction_examples') or pkg.get('interactionExamples')), 'default_depth': pkg.get('default_depth') or pkg.get('defaultDepth')}, source_package_id=package_id, domain_label=domain_label, title='Interaction guide')
    flat = [*agents, memory_schema, prompt_policy, context_policy, approval_policy, *evaluation, interaction_guide]
    return {
        'kind': 'room_component_library_v1',
        'package_id': package_id,
        'domain_label': domain_label,
        'agents': agents,
        'memory_schema': memory_schema,
        'prompt_policy': prompt_policy,
        'context_policy': context_policy,
        'approval_policy': approval_policy,
        'evaluation_criteria': evaluation,
        'interaction_guide': interaction_guide,
        'components': flat,
        'summary': summarize_components(flat),
    }


def augment_room_package_with_components(package: dict[str, Any]) -> dict[str, Any]:
    pkg = strip_private_component_fields(_as_dict(package)) or {}
    library = build_room_components(pkg)
    return {
        **pkg,
        'component_model': 'composable_room_components_v1',
        'components': library,
        'composition_policy': {
            **_as_dict(pkg.get('composition_policy') or pkg.get('compositionPolicy')),
            'shareable_units': ['agent_card', 'memory_schema_card', 'prompt_policy_card', 'context_policy_card', 'approval_policy_card', 'evaluation_criteria_card'],
            'private_memory_copied': False,
            'borrowed_agents_receive_projected_context_only': True,
            'borrowed_agents_write_policy': 'proposal_only',
            'source_room_private_memory': 'never_read_by_default',
            'lineage_required': True,
        },
    }


def find_agent_card(package: dict[str, Any], agent_id: str) -> dict[str, Any] | None:
    key = _id(agent_id, 'agent')
    library = build_room_components(package)
    for agent in library.get('agents', []):
        if _id(agent.get('local_id') or agent.get('role') or agent.get('title'), 'agent') == key:
            return agent
        if _id(str(agent.get('component_id', '')).split(':')[-1], 'agent') == key:
            return agent
    return None


def create_borrowed_agent_invocation(*, source_room_package: dict[str, Any] | None = None, source_room_package_id: str = '', agent_id: str = '', target_room_id: str = '', target_room_package_id: str = '', scope: str = 'single_attempt', context_projection: str = 'target_room_task_projection', reason: str = '') -> dict[str, Any] | None:
    source = _as_dict(source_room_package)
    source_id = _id(source_room_package_id or source.get('package_id') or source.get('packageId') or source.get('title') or 'source_room', 'source_room')
    agent = find_agent_card(source, agent_id) if source else normalize_agent_card(agent_id or 'borrowed_agent', source_package_id=source_id)
    if not agent:
        return None
    return strip_private_component_fields({
        'kind': 'borrowed_agent_invocation_v1',
        'source_room_package_id': source_id,
        'source_component_id': agent.get('component_id'),
        'agent_id': agent.get('local_id') or agent.get('role') or _id(agent_id, 'agent'),
        'agent_title': agent.get('title') or agent_id,
        'target_room_id': str(target_room_id or 'current_room'),
        'target_room_package_id': _id(target_room_package_id or 'current_room_package', 'current_room_package'),
        'scope': scope,
        'context_projection': context_projection,
        'reason': _clean(reason, 800),
        'memory_access': {
            'read_source_private_memory': False,
            'read_target_project_memory': True,
            'write_memory': False,
            'allow_propose_update': True,
            'reads': _as_list(_as_dict(agent.get('memory_access')).get('reads')),
            'proposes_updates': _as_list(_as_dict(agent.get('memory_access')).get('proposes_updates')),
        },
        'approval_policy': 'target_room_owner_approves_merge_or_install',
        'lineage': {
            'borrowed_from_package': source_id,
            'borrowed_component_id': agent.get('component_id'),
            'copied_private_memory': False,
        },
    })


def list_package_components(package_items: list[dict[str, Any]], *, query: str = '', limit: int = 200) -> dict[str, Any]:
    q = _clean(query, 200, lower=True)
    components: list[dict[str, Any]] = []
    for item in package_items:
        pkg = _as_dict(item.get('package') if isinstance(item.get('package'), dict) else item)
        library = build_room_components(pkg)
        for component in library['components']:
            row = {
                **component,
                'package_id': library['package_id'],
                'package_title': pkg.get('title') or pkg.get('name') or library['package_id'],
                'package_visibility': pkg.get('visibility') or item.get('visibility') or 'private_review',
            }
            if q:
                haystack = ' '.join([
                    str(row.get('component_id') or ''), str(row.get('local_id') or ''), str(row.get('title') or ''),
                    str(row.get('description') or ''), str(row.get('domain_label') or ''), ' '.join(_as_list(row.get('tags'))),
                ]).lower()
                if q not in haystack:
                    continue
            components.append(row)
            if len(components) >= limit:
                return {'ok': True, 'summary': summarize_components(components), 'items': components, 'query': q}
    return {'ok': True, 'summary': summarize_components(components), 'items': components, 'query': q}


_BORROW_ROLE_PATTERNS = [
    ('canon_reviewer', [r'canon|continuity|character|캐릭터|설정|모순|말투|팬픽|소설|줄거리']),
    ('continuity_checker', [r'continuity|timeline|plot hole|모순|타임라인|복선|설정']),
    ('security_reviewer', [r'security|auth|credential|권한|보안|인증']),
    ('verifier', [r'test|verify|검증|테스트|재현']),
    ('novelty_critic', [r'novelty|related work|논문|새로움|기여|관련 연구']),
    ('risk_reviewer', [r'risk|finance|stock|리스크|주식|투자']),
]


def recommend_borrowed_agents(*, task_text: str = '', package_items: list[dict[str, Any]] | None = None, target_room_id: str = '', target_room_package_id: str = '', limit: int = 8) -> dict[str, Any]:
    text = _clean(task_text, 4000, lower=True)
    recs: list[dict[str, Any]] = []
    for item in package_items or []:
        pkg = _as_dict(item.get('package') if isinstance(item.get('package'), dict) else item)
        library = build_room_components(pkg)
        for agent in library['agents']:
            role = agent.get('local_id') or agent.get('role') or ''
            matched = False
            for expected, patterns in _BORROW_ROLE_PATTERNS:
                if expected not in role:
                    continue
                if any(re.search(pattern, text, re.I) for pattern in patterns):
                    matched = True
                    break
            if not matched:
                haystack = ' '.join([str(role), str(agent.get('title') or ''), str(agent.get('description') or ''), ' '.join(_as_list(agent.get('tags')))]).lower()
                matched = bool(text and haystack and any(len(tok) > 3 and tok in text for tok in re.split(r'[^a-z0-9가-힣]+', haystack) if tok))
            if not matched:
                continue
            invocation = create_borrowed_agent_invocation(source_room_package=pkg, agent_id=role, target_room_id=target_room_id, target_room_package_id=target_room_package_id, reason=f'task matches reusable agent role {role}')
            if invocation:
                recs.append({'score': 0.75, 'agent': agent, 'invocation': invocation, 'package_id': library['package_id'], 'title': pkg.get('title') or pkg.get('name') or library['package_id']})
                if len(recs) >= limit:
                    return {'ok': True, 'items': recs, 'count': len(recs)}
    return {'ok': True, 'items': recs, 'count': len(recs)}
