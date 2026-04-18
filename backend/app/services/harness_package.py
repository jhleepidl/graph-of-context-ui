from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session

from app.models import Thread
from app.services.graph import load_thread_graph
from app.services.harness_spec import build_harness_summary, get_thread_harness_spec
from app.services.skill_registry import list_skill_registry
from app.services.team_manifest import export_thread_team_manifest

HARNESS_PACKAGE_SCHEMA_VERSION = 'openharness.package/v1'
RUN_TRACE_SCHEMA_VERSION = 'openharness.run_trace/v1'
RUN_SYNC_SCHEMA_VERSION = 'openharness.run_sync/v1'


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: Any, *, max_len: int = 256, lower: bool = False) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    clipped = text[:max_len]
    return clipped.lower() if lower else clipped


def _clean_id(value: Any, *, max_len: int = 128) -> str:
    import re
    text = _clean_text(value, max_len=max_len, lower=True)
    text = re.sub(r'[^a-z0-9_.-]+', '_', text)
    return text.strip('_')


def _clean_list(value: Any, *, limit: int = 24, max_len: int = 64, lower: bool = False) -> list[str]:
    items = value if isinstance(value, list) else ([value] if isinstance(value, str) else [])
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        clean = _clean_text(item, max_len=max_len, lower=lower)
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
        if len(out) >= limit:
            break
    return out


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha1(encoded.encode('utf-8')).hexdigest()[:16]


def _package_id(thread: Thread, harness_summary: dict[str, Any]) -> str:
    base = _clean_id(harness_summary.get('name') or thread.title or thread.id, max_len=96)
    return base or _clean_id(thread.id, max_len=96) or 'openharness_package'


def _hashable_package_payload(payload: dict[str, Any]) -> dict[str, Any]:
    row = dict(payload or {})
    metadata = dict((row.get('metadata') or {}))
    return {
        'schema_version': row.get('schema_version') or HARNESS_PACKAGE_SCHEMA_VERSION,
        'kind': row.get('kind') or 'openharness_package',
        'metadata': {
            'name': _clean_text(metadata.get('name'), max_len=160) or 'OpenHarness Package',
            'description': _clean_text(metadata.get('description'), max_len=512) or None,
            'visibility': _clean_text(metadata.get('visibility'), max_len=64, lower=True) or 'workspace',
            'tags': _clean_list(metadata.get('tags') or [], limit=16, max_len=48, lower=True),
        },
        'compatibility': dict(row.get('compatibility') or {}),
        'sharing': dict(row.get('sharing') or {}),
        'execution_binding': dict(row.get('execution_binding') or {}),
        'trace_contract': dict(row.get('trace_contract') or {}),
        'sync_contract': dict(row.get('sync_contract') or {}),
        'runtime_policy': dict(row.get('runtime_policy') or {}),
        'harness_spec': dict(row.get('harness_spec') or {}),
        'harness_summary': dict(row.get('harness_summary') or {}),
        'team_manifest': dict(row.get('team_manifest') or {}),
        'skill_packages': list(row.get('skill_packages') or []),
    }




def _build_harness_runtime_policy(*, harness_spec: dict[str, Any], harness_summary: dict[str, Any], team_manifest: dict[str, Any]) -> dict[str, Any]:
    team = dict((team_manifest or {}).get('team') or {})
    runtime_execution = dict(team.get('runtime_execution') or team.get('runtimeExecution') or (team_manifest or {}).get('runtime_execution') or {})
    delivery = dict(harness_summary.get('delivery_policy') or {})
    return {
        'schema_version': 'openharness.runtime_policy/v1',
        'delivery_policy': {
            'default_delivery_mode': _clean_text(delivery.get('default_delivery_mode'), max_len=64, lower=True) or 'compression_plus_appendix',
            'appendix_char_budget_ratio': float(delivery.get('appendix_char_budget_ratio') if delivery.get('appendix_char_budget_ratio') is not None else 0.35),
            'default_budget_tier': _clean_text(delivery.get('default_budget_tier'), max_len=32, lower=True) or 'medium',
            'default_risk_level': _clean_text(delivery.get('default_risk_level'), max_len=32, lower=True) or 'standard',
            'projection_appendix_enabled_by_default': delivery.get('projection_appendix_enabled_by_default') is not False,
        },
        'resolved_role_delivery': dict(harness_summary.get('resolved_role_delivery') or {}),
        'audit_flags': dict(harness_summary.get('audit_flags') or {}),
        'tool_policy': dict((harness_spec or {}).get('tool_policy') or {}),
        'approval_policy': dict((harness_spec or {}).get('approval_policy') or {}),
        'runtime_execution': runtime_execution,
    }

def build_harness_package_payload(session: Session, *, thread: Thread, harness_spec: dict[str, Any] | None = None, harness_summary: dict[str, Any] | None = None, team_manifest: dict[str, Any] | None = None, skill_packages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    harness_spec = dict(harness_spec or get_thread_harness_spec(thread))
    harness_summary = dict(harness_summary or build_harness_summary(harness_spec))
    team_manifest = dict(team_manifest or export_thread_team_manifest(session, thread))
    if skill_packages is None:
        nodes, _edges = load_thread_graph(session, thread.id)
        skill_packages = list_skill_registry(nodes=nodes, include_defaults=True)
    skill_packages = list(skill_packages or [])

    runtime_policy = _build_harness_runtime_policy(harness_spec=harness_spec, harness_summary=harness_summary, team_manifest=team_manifest)

    payload = {
        'schema_version': HARNESS_PACKAGE_SCHEMA_VERSION,
        'kind': 'openharness_package',
        'package_id': _package_id(thread, harness_summary),
        'version': 1,
        'metadata': {
            'name': _clean_text(harness_summary.get('name') or thread.title or 'OpenHarness Package', max_len=160) or 'OpenHarness Package',
            'description': _clean_text(harness_summary.get('description') or 'Harness package exported from GoC.', max_len=512) or 'Harness package exported from GoC.',
            'visibility': _clean_text(harness_summary.get('visibility') or 'workspace', max_len=64, lower=True) or 'workspace',
            'tags': _clean_list(harness_summary.get('tags') or ['harness', 'ddalggak', 'goc'], limit=16, max_len=48, lower=True),
            'thread_id': _clean_text(thread.id, max_len=128) or None,
            'service_id': _clean_text(thread.service_id, max_len=128) or None,
            'source_thread_title': _clean_text(thread.title, max_len=200) or None,
            'exported_at': _utc_iso(),
        },
        'compatibility': {
            'runner': 'ddalggak',
            'observability': 'goc',
            'install_target': _clean_text(((team_manifest.get('compatibility') or {}).get('install_target')), max_len=96, lower=True) or 'thread_team_config',
            'ddalggak': True,
            'goc': True,
        },
        'sharing': {
            'shareable': bool(harness_summary.get('shareable') is not False),
            'exportable': bool(harness_summary.get('exportable') is not False),
        },
        'execution_binding': {
            'runner_mode': 'local_execution',
            'observability_mode': 'goc_sync',
            'install_target': _clean_text(((team_manifest.get('compatibility') or {}).get('install_target')), max_len=96, lower=True) or 'thread_team_config',
        },
        'trace_contract': {
            'schema_version': RUN_TRACE_SCHEMA_VERSION,
            'transport': 'goc_execution_graph',
            'storage': 'runtime_events_jsonl',
        },
        'sync_contract': {
            'schema_version': RUN_SYNC_SCHEMA_VERSION,
            'mode': 'ddalggak_push_goc_observe',
            'direction': 'ddalggak_to_goc',
            'semantics': 'append_only',
        },
        'runtime_policy': runtime_policy,
        'harness_spec': harness_spec,
        'harness_summary': harness_summary,
        'team_manifest': team_manifest,
        'skill_packages': skill_packages,
    }
    payload['package_hash'] = _stable_hash(_hashable_package_payload(payload))
    return payload

