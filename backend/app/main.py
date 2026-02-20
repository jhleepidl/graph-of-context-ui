from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from app.routers.threads import router as threads_router
from app.routers.messages import router as messages_router
from app.routers.context_sets import router as ctx_router
from app.routers.folds import router as folds_router
from app.routers.runs import router as runs_router
from app.routers.search import router as search_router

app = FastAPI(title="Graph-of-Context MVP API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # MVP only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def _startup():
    init_db()

app.include_router(threads_router)
app.include_router(messages_router)
app.include_router(ctx_router)
app.include_router(folds_router)
app.include_router(runs_router)
app.include_router(search_router)
