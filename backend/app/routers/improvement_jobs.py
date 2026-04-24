from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlmodel import Session

from app.db import engine
from app.models import Thread
from app.schemas import ImprovementJobCreateRequest, ImprovementJobReportRequest
from app.services.improvement_jobs import (
    create_improvement_job,
    find_improvement_job_node,
    list_improvement_job_nodes,
    list_improvement_job_reports,
    record_improvement_job_report,
    serialize_node,
)
from app.tenant import require_thread_access, require_thread_write_access

router = APIRouter(prefix='/api/threads', tags=['improvement_jobs'])


@router.get('/{thread_id}/improvement_jobs')
def list_thread_improvement_jobs(thread_id: str):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        items = [serialize_node(node) for node in list_improvement_job_nodes(session, thread_id=thread_id)]
        return {
            'ok': True,
            'thread_id': thread_id,
            'items': items,
            'count': len(items),
        }


@router.post('/{thread_id}/improvement_jobs')
def create_thread_improvement_job(thread_id: str, body: ImprovementJobCreateRequest):
    with Session(engine) as session:
        thread = require_thread_write_access(session, thread_id)
        node = create_improvement_job(
            session,
            thread=thread,
            title=body.title or f'Improve {body.target_repo}',
            target_repo=body.target_repo,
            instruction=body.instruction,
            target_runtime=body.target_runtime or 'forge',
            requested_by=body.requested_by,
            workspace_root=body.workspace_root,
            related_run_ids=body.related_run_ids,
            related_history_streams=body.related_history_streams,
            related_candidate_ids=body.related_candidate_ids,
            labels=body.labels,
            meta=body.meta,
            job_id=body.job_id,
        )
        session.commit()
        session.refresh(node)
        return {
            'ok': True,
            'thread_id': thread.id,
            'job': serialize_node(node),
        }


@router.get('/{thread_id}/improvement_jobs/{job_id}')
def get_thread_improvement_job(thread_id: str, job_id: str):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        job_node = find_improvement_job_node(session, thread_id=thread_id, job_id=job_id)
        if not job_node:
            raise HTTPException(404, 'improvement job not found')
        reports = [serialize_node(node) for node in list_improvement_job_reports(session, thread_id=thread_id, job_id=job_id)]
        return {
            'ok': True,
            'thread_id': thread_id,
            'job': serialize_node(job_node),
            'reports': reports,
            'report_count': len(reports),
        }


@router.post('/{thread_id}/improvement_jobs/{job_id}/report')
def report_thread_improvement_job(thread_id: str, job_id: str, body: ImprovementJobReportRequest):
    with Session(engine) as session:
        thread = require_thread_write_access(session, thread_id)
        job_node = find_improvement_job_node(session, thread_id=thread.id, job_id=job_id)
        if not job_node:
            raise HTTPException(404, 'improvement job not found')
        report_node = record_improvement_job_report(
            session,
            thread=thread,
            job_node=job_node,
            kind=body.kind,
            title=body.title,
            summary=body.summary,
            preview_text=body.preview_text,
            phase=body.phase,
            status=body.status,
            payload=body.payload,
            metrics=body.metrics,
            labels=body.labels,
        )
        session.commit()
        session.refresh(job_node)
        session.refresh(report_node)
        return {
            'ok': True,
            'thread_id': thread.id,
            'job': serialize_node(job_node),
            'report': serialize_node(report_node),
        }
