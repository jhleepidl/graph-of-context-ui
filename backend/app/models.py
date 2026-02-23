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
    title: str = Field(default="Untitled")
    created_at: datetime = Field(default_factory=utcnow)

class Node(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    type: str = Field(index=True)  # Message | ToolCall | ToolResult | Artifact | Run | Fold
    text: Optional[str] = None
    payload_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)

class Edge(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    from_id: str = Field(index=True)
    to_id: str = Field(index=True)
    type: str = Field(index=True)  # NEXT | REPLY_TO | INVOKES | RETURNS | USES | IN_RUN | FOLDS | USED_IN_RUN | HAS_PART | NEXT_PART | SPLIT_FROM
    payload_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)

class ContextSet(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    name: str = Field(default="default")
    active_node_ids_json: str = Field(default="[]")
    created_at: datetime = Field(default_factory=utcnow)

class NodeEmbedding(SQLModel, table=True):
    __tablename__ = "node_embeddings"
    node_id: str = Field(primary_key=True)
    thread_id: str = Field(index=True)
    dim: int = Field(default=0)
    embedding_json: str = Field(default="[]")  # JSON list[float] (normalized)
    updated_at: datetime = Field(default_factory=utcnow, index=True)
