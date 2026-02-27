from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlmodel import SQLModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid4().hex


class Thread(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    service_id: str = Field(default="default", index=True)
    title: str = Field(default="Untitled")
    created_at: datetime = Field(default_factory=utcnow)


class Service(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str = Field(index=True)
    api_key_hash: str
    status: str = Field(default="active", index=True)  # active | revoked
    created_at: datetime = Field(default_factory=utcnow, index=True)


class ServiceRequest(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    name: str
    status: str = Field(default="pending", index=True)  # pending | approved | rejected
    requester_ip: Optional[str] = Field(default=None, index=True)
    approved_service_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    approved_at: Optional[datetime] = Field(default=None, index=True)


class Node(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    type: str = Field(index=True)  # Message | ToolCall | ToolResult | Artifact | Run | Fold | Resource | ...
    text: Optional[str] = None
    payload_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)


class Edge(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    from_id: str = Field(index=True)
    to_id: str = Field(index=True)
    type: str = Field(index=True)  # NEXT | REPLY_TO | INVOKES | RETURNS | USES | IN_RUN | FOLDS | USED_IN_RUN | HAS_PART | NEXT_PART | SPLIT_FROM | DEPENDS
    payload_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)


class ContextSet(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    name: str = Field(default="default")
    active_node_ids_json: str = Field(default="[]")
    version: int = Field(default=0, index=True)
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class ContextSetVersion(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    context_set_id: str = Field(index=True)
    thread_id: str = Field(index=True)
    version: int = Field(index=True)
    reason: str = Field(default="update", index=True)
    active_node_ids_json: str = Field(default="[]")
    changed_node_ids_json: str = Field(default="[]")
    meta_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)


class NodeEmbedding(SQLModel, table=True):
    __tablename__ = "node_embeddings"
    node_id: str = Field(primary_key=True)
    thread_id: str = Field(index=True)
    dim: int = Field(default=0)
    embedding_json: str = Field(default="[]")  # JSON list[float] (normalized)
    updated_at: datetime = Field(default_factory=utcnow, index=True)
