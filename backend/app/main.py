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
from app.db import init_db
from app.config import get_env
from app.routers.threads import router as threads_router
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

app = FastAPI(title="Graph-of-Context MVP API")

_cors_origins_raw = (get_env("GOC_CORS_ALLOW_ORIGINS", "*") or "*").strip()
if _cors_origins_raw == "*":
    _cors_allow_origins = ["*"]
else:
    _cors_allow_origins = [x.strip() for x in _cors_origins_raw.split(",") if x.strip()]
if not _cors_allow_origins:
    _cors_allow_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS" or not request.url.path.startswith("/api"):
        return await call_next(request)

    is_public_service_request = request.method == "POST" and request.url.path == "/api/service_requests"
    if is_public_service_request:
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

    token = set_current_principal(principal)
    try:
        return await call_next(request)
    finally:
        reset_current_principal(token)


@app.on_event("startup")
def _startup():
    ensure_auth_config()
    init_db()

app.include_router(threads_router)
app.include_router(messages_router)
app.include_router(ctx_router)
app.include_router(folds_router)
app.include_router(runs_router)
app.include_router(search_router)
app.include_router(imports_router)
app.include_router(tokens_router)
app.include_router(nodes_router)
app.include_router(service_auth_router)

app.include_router(hierarchy_router)
