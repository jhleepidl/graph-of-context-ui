from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models import ContextSet, Node, Thread
from app.services.context_versions import snapshot_context_set
from app.services.graph import add_edge, get_last_node


REPORT_RESOURCE_KINDS = {
    "repo_snapshot",
    "code_diff",
    "test_report",
    "canary_result",
    "promotion_decision",
    "patch_plan",
    "runtime_event",
    "llm_trace_summary",
}



def _clean_text(value: Any, max_len: int = 1200) -> str:
    return str(value or '').strip()[:max_len]



def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}



def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []



def _jdump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)



def _node_payload(node: Node | None) -> dict[str, Any]:
    if not node:
        return {}
    try:
        raw = json.loads(node.payload_json or '{}')
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}



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



def _append_event_log(payload: dict[str, Any], event: dict[str, Any], *, max_items: int = 20) -> None:
    log = [item for item in _as_list(payload.get('event_log')) if isinstance(item, dict)]
    log.append(event)
    payload['event_log'] = log[-max_items:]



def _update_latest_report(payload: dict[str, Any], *, kind: str, node_id: str, summary: str, phase: str, status: str, metrics: dict[str, Any]) -> None:
    latest = _as_dict(payload.get('latest_reports'))
    latest[kind] = {
        'node_id': node_id,
        'summary': summary or None,
        'phase': phase or None,
        'status': status or None,
        'metrics': metrics or {},
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }
    payload['latest_reports'] = latest



def _bump_report_count(payload: dict[str, Any], kind: str) -> None:
    counts = _as_dict(payload.get('report_counts'))
    counts[kind] = int(counts.get(kind) or 0) + 1
    payload['report_counts'] = counts



def _create_resource_node(
    session: Session,
    *,
    thread: Thread,
    context_set: ContextSet,
    payload: dict[str, Any],
    text: str,
) -> Node:
    resource_kind = _clean_text(payload.get('resource_kind') or 'resource', 96) or 'resource'
    last = get_last_node(session, thread.id)
    node = Node(
        thread_id=thread.id,
        type='Resource',
        text=text,
        payload_json=_jdump(payload),
    )
    session.add(node)
    session.flush()
    if last and last.id != node.id:
        session.add(add_edge(thread.id, last.id, node.id, 'NEXT'))
    _activate_node_in_context_set(session, context_set=context_set, node_id=node.id, resource_kind=resource_kind)
    return node



def create_improvement_job(
    session: Session,
    *,
    thread: Thread,
    title: str,
    target_repo: str,
    instruction: str,
    target_runtime: str = 'forge',
    requested_by: str | None = None,
    workspace_root: str | None = None,
    related_run_ids: list[str] | None = None,
    related_history_streams: list[str] | None = None,
    related_candidate_ids: list[str] | None = None,
    labels: list[str] | None = None,
    meta: dict[str, Any] | None = None,
    job_id: str | None = None,
) -> Node:
    context_set = _load_or_create_first_context_set(session, thread_id=thread.id)
    clean_job_id = _clean_text(job_id or '', 128) or f'improve_{uuid4().hex[:12]}'
    payload = {
        'name': _clean_text(title, 160) or f'Improve {target_repo}',
        'title': _clean_text(title, 160) or f'Improve {target_repo}',
        'summary': _clean_text(instruction, 320) or None,
        'resource_kind': 'improvement_job',
        'board_visible': True,
        'job_id': clean_job_id,
        'improvement_job_id': clean_job_id,
        'improvement_target': _clean_text(target_repo, 64) or 'unknown',
        'target_runtime': _clean_text(target_runtime, 64) or 'forge',
        'instruction': _clean_text(instruction, 4000),
        'requested_by': _clean_text(requested_by, 160) or None,
        'workspace_root': _clean_text(workspace_root, 400) or None,
        'phase': 'created',
        'status': 'created',
        'report_counts': {},
        'latest_reports': {},
        'related_run_ids': [_clean_text(v, 128) for v in (related_run_ids or []) if _clean_text(v, 128)],
        'related_history_streams': [_clean_text(v, 128) for v in (related_history_streams or []) if _clean_text(v, 128)],
        'related_candidate_ids': [_clean_text(v, 128) for v in (related_candidate_ids or []) if _clean_text(v, 128)],
        'tags': [_clean_text(v, 64) for v in (labels or []) if _clean_text(v, 64)][:12],
        'meta': _as_dict(meta),
        'source': 'improvement_runtime',
        'privacy_class': 'structured_internal',
        'shareability': 'private_only',
        'learning_excluded': True,
        'promotion_blocked': True,
    }
    _append_event_log(payload, {
        'at': datetime.now(timezone.utc).isoformat(),
        'kind': 'job_created',
        'phase': 'created',
        'status': 'created',
        'summary': _clean_text(instruction, 240) or 'improvement job created',
    })
    return _create_resource_node(
        session,
        thread=thread,
        context_set=context_set,
        payload=payload,
        text=_clean_text(instruction, 12000) or f'Improve {target_repo}',
    )



def list_improvement_job_nodes(session: Session, *, thread_id: str) -> list[Node]:
    nodes = session.exec(
        select(Node)
        .where(Node.thread_id == thread_id, Node.type == 'Resource')
        .order_by(Node.created_at.desc(), Node.id.desc())
    ).all()
    return [node for node in nodes if _node_payload(node).get('resource_kind') == 'improvement_job']



def find_improvement_job_node(session: Session, *, thread_id: str, job_id: str) -> Node | None:
    clean_job_id = _clean_text(job_id, 128)
    if not clean_job_id:
        return None
    for node in list_improvement_job_nodes(session, thread_id=thread_id):
        payload = _node_payload(node)
        if _clean_text(payload.get('job_id'), 128) == clean_job_id:
            return node
    return None



def list_improvement_job_reports(session: Session, *, thread_id: str, job_id: str) -> list[Node]:
    clean_job_id = _clean_text(job_id, 128)
    if not clean_job_id:
        return []
    nodes = session.exec(
        select(Node)
        .where(Node.thread_id == thread_id, Node.type == 'Resource')
        .order_by(Node.created_at.desc(), Node.id.desc())
    ).all()
    out: list[Node] = []
    for node in nodes:
        payload = _node_payload(node)
        if _clean_text(payload.get('improvement_job_id'), 128) != clean_job_id:
            continue
        if _clean_text(payload.get('resource_kind'), 64) == 'improvement_job':
            continue
        out.append(node)
    return out



def record_improvement_job_report(
    session: Session,
    *,
    thread: Thread,
    job_node: Node,
    kind: str,
    title: str | None = None,
    summary: str | None = None,
    preview_text: str | None = None,
    phase: str | None = None,
    status: str | None = None,
    payload: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    labels: list[str] | None = None,
) -> Node:
    clean_kind = _clean_text(kind, 96)
    if clean_kind not in REPORT_RESOURCE_KINDS:
        raise HTTPException(400, f'unsupported report kind: {clean_kind or "unknown"}')
    job_payload = _node_payload(job_node)
    context_set = _load_or_create_first_context_set(session, thread_id=thread.id)
    clean_phase = _clean_text(phase or job_payload.get('phase') or 'reported', 96) or 'reported'
    clean_status = _clean_text(status or job_payload.get('status') or 'in_progress', 96) or 'in_progress'
    clean_title = _clean_text(title or f'{clean_kind.replace("_", " ").title()} · {job_payload.get("job_id")}', 160)
    clean_summary = _clean_text(summary or preview_text or clean_kind, 400)
    report_payload = {
        'name': clean_title,
        'title': clean_title,
        'summary': clean_summary or None,
        'resource_kind': clean_kind,
        'board_visible': True,
        'improvement_job_id': _clean_text(job_payload.get('job_id'), 128),
        'job_id': _clean_text(job_payload.get('job_id'), 128),
        'improvement_target': _clean_text(job_payload.get('improvement_target'), 64),
        'target_runtime': _clean_text(job_payload.get('target_runtime'), 64),
        'phase': clean_phase,
        'status': clean_status,
        'metrics': _as_dict(metrics),
        'payload': _as_dict(payload),
        'tags': [_clean_text(v, 64) for v in (labels or []) if _clean_text(v, 64)][:12],
        'source': 'improvement_runtime',
        'privacy_class': 'structured_internal',
        'shareability': 'private_only',
        'learning_excluded': True,
        'promotion_blocked': True,
    }
    report_text = _clean_text(preview_text, 16000)
    if not report_text:
        report_text = _jdump(_as_dict(payload))[:16000]
    report_node = _create_resource_node(
        session,
        thread=thread,
        context_set=context_set,
        payload=report_payload,
        text=report_text or clean_summary,
    )

    job_payload['phase'] = clean_phase
    job_payload['status'] = clean_status
    job_payload['summary'] = _clean_text(clean_summary or job_payload.get('summary'), 320) or None
    _bump_report_count(job_payload, clean_kind)
    _update_latest_report(job_payload, kind=clean_kind, node_id=report_node.id, summary=clean_summary, phase=clean_phase, status=clean_status, metrics=_as_dict(metrics))
    _append_event_log(job_payload, {
        'at': datetime.now(timezone.utc).isoformat(),
        'kind': clean_kind,
        'phase': clean_phase,
        'status': clean_status,
        'summary': clean_summary or clean_kind,
        'report_node_id': report_node.id,
    })
    if clean_kind == 'code_diff':
        job_payload['last_patch_status'] = clean_status
    elif clean_kind == 'test_report':
        job_payload['last_test_status'] = clean_status
    elif clean_kind == 'canary_result':
        job_payload['last_canary_status'] = clean_status
    elif clean_kind == 'promotion_decision':
        job_payload['last_promotion_status'] = clean_status
    elif clean_kind == 'llm_trace_summary':
        job_payload['last_llm_trace_status'] = clean_status
    job_node.payload_json = _jdump(job_payload)
    session.add(job_node)
    session.flush()
    return report_node



def serialize_node(node: Node) -> dict[str, Any]:
    return {
        **node.model_dump(),
        'payload': _node_payload(node),
    }
