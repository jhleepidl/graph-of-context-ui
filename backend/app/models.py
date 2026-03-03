from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import UniqueConstraint
from sqlmodel import SQLModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid4().hex


class Thread(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    service_id: str = Field(default="default", index=True)
    title: str = Field(default="Untitled")
    external_ref: Optional[str] = Field(default=None, index=True)
    meta_json: str = Field(default="{}")
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
    description: Optional[str] = None
    status: str = Field(default="pending", index=True)  # pending | approved | rejected
    requester_ip: Optional[str] = Field(default=None, index=True)
    approved_service_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    approved_at: Optional[datetime] = Field(default=None, index=True)


class AgentPublishRequest(SQLModel, table=True):
    id: str = Field(default_factory=new_id, primary_key=True)
    service_id: str = Field(index=True)
    source_node_id: str = Field(index=True)
    status: str = Field(default="pending", index=True)  # pending | approved | rejected
    created_at: datetime = Field(default_factory=utcnow, index=True)
    decided_at: Optional[datetime] = Field(default=None, index=True)
    decided_by: Optional[str] = None
    public_node_id: Optional[str] = Field(default=None, index=True)
    blueprint_id: Optional[str] = Field(default=None, index=True)


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


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("telegram_user_id", name="uq_users_telegram_user_id"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    telegram_user_id: str = Field(index=True)
    username: Optional[str] = Field(default=None, index=True)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language_code: Optional[str] = None
    is_bot: bool = Field(default=False)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)
    last_login_at: datetime = Field(default_factory=utcnow, index=True)


class Agent(SQLModel, table=True):
    __tablename__ = "agents"

    id: str = Field(default_factory=new_id, primary_key=True)
    owner_user_id: str = Field(index=True)
    service_id: str = Field(default="default", index=True)
    name: str = Field(index=True)
    description: str = Field(default="")
    system_prompt: str = Field(default="")
    instruction: str = Field(default="")
    tools_json: str = Field(default="[]")
    model: str = Field(default="")
    visibility: str = Field(default="private", index=True)  # private | unlisted | public
    source_agent_id: Optional[str] = Field(default=None, index=True)
    system_key: Optional[str] = Field(default=None, index=True)
    is_system_default: bool = Field(default=False, index=True)
    is_archived: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class AgentRevision(SQLModel, table=True):
    __tablename__ = "agent_revisions"
    __table_args__ = (UniqueConstraint("agent_id", "revision", name="uq_agent_revisions_agent_revision"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    agent_id: str = Field(index=True)
    revision: int = Field(index=True)
    snapshot_json: str = Field(default="{}")
    created_by_user_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class Conversation(SQLModel, table=True):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("thread_id", name="uq_conversations_thread_id"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    owner_user_id: str = Field(index=True)
    service_id: str = Field(default="default", index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class ConversationAgent(SQLModel, table=True):
    __tablename__ = "conversation_agents"
    __table_args__ = (UniqueConstraint("conversation_id", "agent_id", name="uq_conversation_agents_conversation_agent"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    conversation_id: str = Field(index=True)
    agent_id: str = Field(index=True)
    enabled: bool = Field(default=True, index=True)
    order_index: int = Field(default=0, index=True)
    overrides_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)
