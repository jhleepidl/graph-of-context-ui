from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

from fastapi import APIRouter, HTTPException, Query, Request
from sqlmodel import Session, select

from app.auth import (
    generate_service_key,
    hash_service_key,
    mint_ui_bearer_token,
    require_admin_principal,
    require_service_key_principal,
)
from app.db import engine
from app.models import Service, ServiceRequest
from app.schemas import MintUiTokenRequest, ServiceRequestCreate

router = APIRouter(prefix="/api", tags=["service_auth"])

_RATE_WINDOW_SEC = 3600
_RATE_MAX_PER_IP = 5
_request_hits: dict[str, list[int]] = defaultdict(list)
_rate_lock = Lock()


def _check_service_request_rate_limit(ip: str) -> None:
    now = int(time.time())
    with _rate_lock:
        hits = _request_hits[ip]
        floor = now - _RATE_WINDOW_SEC
        hits[:] = [x for x in hits if x >= floor]
        if len(hits) >= _RATE_MAX_PER_IP:
            raise HTTPException(429, "too many service requests from this IP")
        hits.append(now)


@router.post("/service_requests")
def create_service_request(body: ServiceRequestCreate, request: Request):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    description = (body.description or "").strip() or None

    requester_ip = request.client.host if request.client and request.client.host else "unknown"
    _check_service_request_rate_limit(requester_ip)

    row = ServiceRequest(name=name, description=description, requester_ip=requester_ip)
    with Session(engine) as s:
        s.add(row)
        s.commit()
        s.refresh(row)
        return {
            "ok": True,
            "service_request": row.model_dump(),
        }


@router.get("/admin/service_requests")
def list_service_requests(status: str | None = Query(default=None)):
    require_admin_principal()
    with Session(engine) as s:
        query = select(ServiceRequest).order_by(ServiceRequest.created_at.desc(), ServiceRequest.id.desc())
        if status:
            status_clean = status.strip().lower()
            if status_clean not in {"pending", "approved", "rejected"}:
                raise HTTPException(400, "status must be pending|approved|rejected")
            query = query.where(ServiceRequest.status == status_clean)
        rows = s.exec(query).all()
        return {"ok": True, "items": [r.model_dump() for r in rows]}


@router.get("/admin/services")
def list_services():
    require_admin_principal()
    with Session(engine) as s:
        rows = s.exec(
            select(Service)
            .order_by(Service.created_at.desc(), Service.id.desc())
        ).all()
        return {"ok": True, "items": [r.model_dump() for r in rows]}


@router.post("/admin/service_requests/{request_id}/approve")
def approve_service_request(request_id: str):
    require_admin_principal()
    with Session(engine) as s:
        req = s.get(ServiceRequest, request_id)
        if not req:
            raise HTTPException(404, "service request not found")
        if req.status != "pending":
            raise HTTPException(400, f"service request is already {req.status}")

        service = Service(name=req.name, status="active", api_key_hash="")
        s.add(service)
        s.flush()

        raw_key = generate_service_key(service.id)
        service.api_key_hash = hash_service_key(raw_key)
        req.status = "approved"
        req.approved_service_id = service.id
        req.approved_at = service.created_at

        s.add(service)
        s.add(req)
        s.commit()
        s.refresh(service)
        s.refresh(req)

        return {
            "ok": True,
            "service": {
                "id": service.id,
                "name": service.name,
                "status": service.status,
                "created_at": service.created_at,
            },
            "api_key": raw_key,
            "service_request": req.model_dump(),
        }


@router.post("/admin/services/{service_id}/revoke")
def revoke_service(service_id: str):
    require_admin_principal()
    with Session(engine) as s:
        service = s.get(Service, service_id)
        if not service:
            raise HTTPException(404, "service not found")
        service.status = "revoked"
        s.add(service)
        s.commit()
        return {"ok": True, "service_id": service.id, "status": service.status}


@router.post("/admin/services/{service_id}/rotate")
def rotate_service_key(service_id: str):
    return _rotate_service_key(service_id)


@router.post("/admin/services/{service_id}/rotate_key")
def rotate_service_key_compat(service_id: str):
    return _rotate_service_key(service_id)


def _rotate_service_key(service_id: str):
    require_admin_principal()
    with Session(engine) as s:
        service = s.get(Service, service_id)
        if not service:
            raise HTTPException(404, "service not found")
        if service.status != "active":
            raise HTTPException(400, "service is not active")

        raw_key = generate_service_key(service.id)
        service.api_key_hash = hash_service_key(raw_key)
        s.add(service)
        s.commit()
        return {"ok": True, "service_id": service.id, "api_key": raw_key}


@router.post("/service/mint_ui_token")
def mint_ui_token(body: MintUiTokenRequest):
    principal = require_service_key_principal()
    token, exp = mint_ui_bearer_token(principal.service_id or "", body.ttl_sec)
    return {"ok": True, "token": token, "exp": exp, "service_id": principal.service_id}
