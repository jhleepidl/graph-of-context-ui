from __future__ import annotations
from fastapi import FastAPI
from fastapi import HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth import (
    Principal,
    ensure_auth_config,
    reset_current_principal,
    resolve_principal,
    set_current_principal,
)
from app.db import dispose_engine, init_db, ping_db
from app.config import get_env
from app.routers.threads import router as threads_router, legacy_router as threads_legacy_router
from app.routers.messages import router as messages_router
from app.routers.context_sets import router as ctx_router
from app.routers.folds import router as folds_router
from app.routers.runs import router as runs_router
from app.routers.search import router as search_router
from app.routers.imports import router as imports_router
from app.routers.tokens import router as tokens_router
from app.routers.nodes import router as nodes_router
from app.routers.hierarchy import router as hierarchy_router
from app.routers.service_auth import router as service_auth_router
from app.routers.publish_requests import router as publish_requests_router
from app.routers.telegram_auth import router as telegram_auth_router
from app.routers.agents import router as agents_router
from app.routers.skills import router as skills_router
from app.routers.memory_graphs import router as memory_graphs_router
from app.routers.boards import router as boards_router
from app.routers.improvement_jobs import router as improvement_jobs_router
from app.services.users import upsert_user_by_telegram_id

app = FastAPI(title="Graph-of-Context MVP API")

_cors_origins_raw = (get_env("GOC_CORS_ALLOW_ORIGINS", "*") or "*").strip()
if _cors_origins_raw == "*":
    _cors_allow_origins = ["*"]
else:
    _cors_allow_origins = [x.strip() for x in _cors_origins_raw.split(",") if x.strip()]
if not _cors_allow_origins:
    _cors_allow_origins = ["*"]

_cors_allow_credentials = _cors_allow_origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS" or not request.url.path.startswith("/api"):
        return await call_next(request)

    normalized_path = request.url.path.rstrip("/") or "/"
    is_public_service_request = request.method == "POST" and normalized_path == "/api/service_requests"
    is_public_telegram_webapp_login = request.method == "POST" and normalized_path == "/api/auth/telegram/webapp"
    if is_public_service_request or is_public_telegram_webapp_login:
        token = set_current_principal(Principal(role="anonymous", service_id=None))
        try:
            return await call_next(request)
        finally:
            reset_current_principal(token)

    try:
        principal = resolve_principal(
            request.headers.get("X-Admin-Key"),
            request.headers.get("Authorization"),
        )
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    if principal.role == "service":
        acting_telegram_user_id = (
            request.headers.get("X-Acting-Telegram-User-Id")
            or request.headers.get("X-Acting-Telegram-User")
            or ""
        ).strip()
        if acting_telegram_user_id:
            try:
                acting_user = upsert_user_by_telegram_id(acting_telegram_user_id)
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
            principal = Principal(
                role=principal.role,
                service_id=principal.service_id,
                user_id=acting_user.id,
                telegram_user_id=acting_user.telegram_user_id,
            )

    token = set_current_principal(principal)
    try:
        return await call_next(request)
    finally:
        reset_current_principal(token)


@app.on_event("startup")
def _startup():
    ensure_auth_config()
    init_db()



@app.get("/healthz")
def healthz():
    if not ping_db():
        raise HTTPException(status_code=503, detail="database unavailable")
    return {"ok": True}


@app.on_event("shutdown")
def _shutdown():
    dispose_engine()

app.include_router(threads_router)
app.include_router(threads_legacy_router)
app.include_router(messages_router)
app.include_router(ctx_router)
app.include_router(folds_router)
app.include_router(runs_router)
app.include_router(search_router)
app.include_router(imports_router)
app.include_router(tokens_router)
app.include_router(nodes_router)
app.include_router(service_auth_router)
app.include_router(publish_requests_router)
app.include_router(telegram_auth_router)
app.include_router(agents_router)
app.include_router(skills_router)
app.include_router(memory_graphs_router)
app.include_router(boards_router)
app.include_router(improvement_jobs_router)

app.include_router(hierarchy_router)
