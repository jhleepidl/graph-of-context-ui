from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import UniqueConstraint, Column, Text
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


class AgentForkOperation(SQLModel, table=True):
    __tablename__ = "agent_fork_operations"
    __table_args__ = (UniqueConstraint("forked_agent_id", name="uq_agent_fork_operations_forked_agent"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    source_agent_id: str = Field(index=True)
    forked_agent_id: str = Field(index=True)
    owner_user_id: str = Field(index=True)
    service_id: str = Field(default="default", index=True)
    reason: Optional[str] = Field(default=None)
    purpose: Optional[str] = Field(default=None)
    scope_json: str = Field(default="{}")
    scope_node_ids_json: str = Field(default="[]")
    source_surface_ids_json: str = Field(default="[]")
    publish_surface_ids_json: str = Field(default="[]")
    source_thread_id: Optional[str] = Field(default=None, index=True)
    source_run_id: Optional[str] = Field(default=None, index=True)
    rejoin_strategy: Optional[str] = Field(default=None, index=True)
    rejoin_status: str = Field(default="forked", index=True)
    rejoin_summary: Optional[str] = Field(default=None)
    artifact_ids_json: str = Field(default="[]")
    provenance_json: str = Field(default="{}")
    rejoined_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


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


class ConversationTeamConfig(SQLModel, table=True):
    __tablename__ = "conversation_team_configs"
    __table_args__ = (UniqueConstraint("conversation_id", name="uq_conversation_team_configs_conversation"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    conversation_id: str = Field(index=True)
    thread_id: str = Field(index=True)
    status: str = Field(default="none", index=True)
    active_team_json: str = Field(default="{}")
    pending_team_json: str = Field(default="{}")
    state_json: str = Field(default="{}")
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class ConversationTeamConfigRevision(SQLModel, table=True):
    __tablename__ = "conversation_team_config_revisions"

    id: str = Field(default_factory=new_id, primary_key=True)
    conversation_id: str = Field(index=True)
    thread_id: str = Field(index=True)
    revision_kind: str = Field(default="update", index=True)
    payload_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)


class MemorySurface(SQLModel, table=True):
    __tablename__ = "memory_surfaces"
    __table_args__ = (UniqueConstraint("thread_id", "surface_id", name="uq_memory_surfaces_thread_surface"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    surface_id: str = Field(index=True)
    title: str = Field(default="")
    semantic_kind: str = Field(default="generic", index=True)
    visibility_scope: str = Field(default="shared", index=True)
    write_mode: str = Field(default="shared", index=True)
    policy_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class MemoryNode(SQLModel, table=True):
    __tablename__ = "memory_nodes"

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    surface_id: str = Field(index=True)
    node_type: str = Field(default="note", index=True)
    owner_agent_id: Optional[str] = Field(default=None, index=True)
    owner_role_id: Optional[str] = Field(default=None, index=True)
    content_json: str = Field(default="{}")
    provenance_json: str = Field(default="{}")
    trust_tier: str = Field(default="derived", index=True)
    status: str = Field(default="draft", index=True)
    created_run_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class MemoryProjection(SQLModel, table=True):
    __tablename__ = "memory_projections"

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    agent_id: Optional[str] = Field(default=None, index=True)
    role_id: Optional[str] = Field(default=None, index=True)
    visible_node_ids_json: str = Field(default="[]")
    blocked_node_ids_json: str = Field(default="[]")
    summary_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)




class MemoryTopologySnapshot(SQLModel, table=True):
    __tablename__ = "memory_topology_snapshots"

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    mode: str = Field(default="compact_single", index=True)
    state: str = Field(default="compact_single", index=True)
    stress_score: float = Field(default=0.0, index=True)
    source: str = Field(default="ddalggak", index=True)
    topology_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class MemoryTopologyEvent(SQLModel, table=True):
    __tablename__ = "memory_topology_events"

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    snapshot_id: Optional[str] = Field(default=None, index=True)
    kind: str = Field(default="memory_topology_event", index=True)
    previous_mode: Optional[str] = Field(default=None, index=True)
    next_mode: Optional[str] = Field(default=None, index=True)
    stress_score: float = Field(default=0.0, index=True)
    source: str = Field(default="ddalggak", index=True)
    event_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)


class MemoryDemandEvent(SQLModel, table=True):
    __tablename__ = "memory_demand_events"

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    query: str = Field(default="", index=True)
    reason: str = Field(default="context_preflight", index=True)
    demand_reasons_json: str = Field(default="[]")
    sources_json: str = Field(default="[]")
    item_count: int = Field(default=0, index=True)
    agent_id: Optional[str] = Field(default=None, index=True)
    role_id: Optional[str] = Field(default=None, index=True)
    retrieval_mode: str = Field(default="runtime_preflight", index=True)
    classifier: Optional[str] = Field(default=None, index=True)
    confidence: Optional[float] = Field(default=None, index=True)
    source_types_json: str = Field(default="[]")
    surface_ids_json: str = Field(default="[]")
    source: str = Field(default="ddalggak", index=True)
    event_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)


class MemoryEdge(SQLModel, table=True):
    __tablename__ = "memory_edges"
    __table_args__ = (UniqueConstraint("thread_id", "edge_type", "from_node_id", "to_node_id", name="uq_memory_edges_pair"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    edge_type: str = Field(default="related_to", index=True)
    from_node_id: str = Field(index=True)
    to_node_id: str = Field(index=True)
    from_surface_id: Optional[str] = Field(default=None, index=True)
    to_surface_id: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="active", index=True)
    rationale: str = Field(default="")
    provenance_json: str = Field(default="{}")
    created_run_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class MemoryLifecycleEvent(SQLModel, table=True):
    __tablename__ = "memory_lifecycle_events"

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    node_id: str = Field(index=True)
    surface_id: str = Field(index=True)
    event_type: str = Field(default="node_drafted", index=True)
    from_status: Optional[str] = Field(default=None, index=True)
    to_status: Optional[str] = Field(default=None, index=True)
    actor: Optional[str] = Field(default=None, index=True)
    source: Optional[str] = Field(default=None, index=True)
    summary: str = Field(default="")
    metadata_json: str = Field(default="{}")
    created_run_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)


class MemoryConflict(SQLModel, table=True):
    __tablename__ = "memory_conflicts"
    __table_args__ = (UniqueConstraint("thread_id", "surface_id", "left_node_id", "right_node_id", name="uq_memory_conflicts_pair"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    surface_id: str = Field(index=True)
    left_node_id: str = Field(index=True)
    right_node_id: str = Field(index=True)
    status: str = Field(default="pending", index=True)
    reason: str = Field(default="")
    resolution_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)




class MemoryMaterializationCandidate(SQLModel, table=True):
    __tablename__ = "memory_materialization_candidates"

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    domain: str = Field(default="", index=True)
    title: str = Field(default="")
    status: str = Field(default="candidate", index=True)  # candidate | shadow_created | dismissed | approved
    score: float = Field(default=0.0, index=True)
    recommendation: str = Field(default="", index=True)
    candidate_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class MemoryModule(SQLModel, table=True):
    __tablename__ = "memory_modules"
    __table_args__ = (UniqueConstraint("thread_id", "module_id", name="uq_memory_modules_thread_module"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    module_id: str = Field(index=True)
    domain: str = Field(default="", index=True)
    title: str = Field(default="")
    status: str = Field(default="shadow", index=True)  # shadow | active | archived
    table_name: str = Field(default="", index=True)
    # Avoid shadowing SQLModel/Pydantic .schema_json() while keeping the persisted column name.
    schema_data_json: str = Field(default="{}", sa_column=Column("schema_json", Text, default="{}"))
    operations_json: str = Field(default="[]")
    manifest_json: str = Field(default="{}")
    row_count: int = Field(default=0, index=True)
    review_count: int = Field(default=0, index=True)
    high_confidence_count: int = Field(default=0, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class MemoryModuleRow(SQLModel, table=True):
    __tablename__ = "memory_module_rows"

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    module_id: str = Field(index=True)
    row_key: str = Field(default="", index=True)
    status: str = Field(default="shadow", index=True)
    review_state: str = Field(default="needs_review", index=True)
    row_json: str = Field(default="{}")
    source_ref: str = Field(default="", index=True)
    confidence: float = Field(default=0.0, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class RuntimeProposal(SQLModel, table=True):
    __tablename__ = "runtime_proposals"
    __table_args__ = (UniqueConstraint("thread_id", "proposal_id", name="uq_runtime_proposals_thread_proposal"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    proposal_id: str = Field(index=True)
    proposal_kind: str = Field(default="memory_candidate", index=True)
    title: str = Field(default="")
    summary: str = Field(default="")
    source_original_text: str = Field(default="")
    source_original_language: str = Field(default="", index=True)
    display_text: str = Field(default="")
    canonical_language: str = Field(default="en", index=True)
    canonical_text_en: str = Field(default="")
    canonical_projection_status: str = Field(default="", index=True)
    canonical_projection_id: str = Field(default="", index=True)
    projection_method: str = Field(default="", index=True)
    projection_confidence: float = Field(default=0.0, index=True)
    user_surface_locale: str = Field(default="", index=True)
    risk: str = Field(default="medium", index=True)
    status: str = Field(default="pending_review", index=True)
    source: str = Field(default="runtime", index=True)
    source_id: str = Field(default="", index=True)
    recommended_action: str = Field(default="")
    evidence_status: str = Field(default="", index=True)
    proposal_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class RuntimeCommit(SQLModel, table=True):
    __tablename__ = "runtime_commits"

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    proposal_id: str = Field(default="", index=True)
    action: str = Field(default="commit", index=True)
    status: str = Field(default="committed", index=True)
    actor: str = Field(default="goc", index=True)
    reason: str = Field(default="")
    commit_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)


class WatchTask(SQLModel, table=True):
    __tablename__ = "watch_tasks"
    __table_args__ = (UniqueConstraint("thread_id", "contract_id", name="uq_watch_tasks_thread_contract"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    contract_id: str = Field(index=True)
    workflow_kind: str = Field(default="bounded_continuous_loop", index=True)
    status: str = Field(default="active", index=True)
    goal: str = Field(default="")
    current_iteration: int = Field(default=0, index=True)
    min_iterations: int = Field(default=1, index=True)
    max_iterations: int = Field(default=1, index=True)
    required_passes_json: str = Field(default="[]")
    approval_boundary: bool = Field(default=False, index=True)
    stop_conditions_json: str = Field(default="[]")
    contract_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class WatchIteration(SQLModel, table=True):
    __tablename__ = "watch_iterations"
    __table_args__ = (UniqueConstraint("thread_id", "task_id", "iteration", "event", name="uq_watch_iterations_task_event"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    task_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    iteration: int = Field(default=0, index=True)
    status: str = Field(default="recorded", index=True)
    event: str = Field(default="watch_iteration_event", index=True)
    summary: str = Field(default="")
    stop_reason: str = Field(default="", index=True)
    payload_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)




class AgentActivityEvent(SQLModel, table=True):
    __tablename__ = "agent_activity_events"

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    event_kind: str = Field(default="activity", index=True)  # activity | handoff | policy
    event_type: str = Field(default="agent_event", index=True)
    agent_id: Optional[str] = Field(default=None, index=True)
    role_id: Optional[str] = Field(default=None, index=True)
    from_agent: Optional[str] = Field(default=None, index=True)
    to_agent: Optional[str] = Field(default=None, index=True)
    provider: Optional[str] = Field(default=None, index=True)
    model: Optional[str] = Field(default=None, index=True)
    summary: str = Field(default="")
    decision: str = Field(default="", index=True)
    execution_mode: str = Field(default="", index=True)
    workspace_write: str = Field(default="", index=True)
    artifact_delivery: str = Field(default="", index=True)
    legacy_manual_fallback: str = Field(default="", index=True)
    source: str = Field(default="ddalggak", index=True)
    source_event_id: str = Field(default="", index=True)
    payload_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)
    ingested_at: datetime = Field(default_factory=utcnow, index=True)


class AgentPackageRecord(SQLModel, table=True):
    __tablename__ = "agent_package_records"
    __table_args__ = (UniqueConstraint("thread_id", "package_id", name="uq_agent_package_records_thread_package"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    package_id: str = Field(index=True)
    title: str = Field(default="")
    description: str = Field(default="")
    visibility: str = Field(default="private_review", index=True)
    status: str = Field(default="candidate", index=True)
    source: str = Field(default="ddalggak", index=True)
    source_thread_id: str = Field(default="", index=True)
    source_chat_id: str = Field(default="", index=True)
    agent_count: int = Field(default=0, index=True)
    skill_count: int = Field(default=0, index=True)
    rule_count: int = Field(default=0, index=True)
    copies_private_memory: bool = Field(default=False, index=True)
    package_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class ModelNodeRecord(SQLModel, table=True):
    __tablename__ = "model_node_records"
    __table_args__ = (UniqueConstraint("node_id", name="uq_model_node_records_node"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    node_id: str = Field(index=True)
    provider: str = Field(default="", index=True)
    runtime: str = Field(default="", index=True)
    model: str = Field(default="", index=True)
    status: str = Field(default="available", index=True)
    cost_tier: str = Field(default="unknown", index=True)
    latency_tier: str = Field(default="unknown", index=True)
    quality_tier: str = Field(default="standard", index=True)
    privacy_tier: str = Field(default="unknown", index=True)
    data_boundary: str = Field(default="", index=True)
    allow_private_context: bool = Field(default=False, index=True)
    context_tokens: int = Field(default=0, index=True)
    source: str = Field(default="ddalggak", index=True)
    node_json: str = Field(default="{}")
    last_seen_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class ModelNodeUsageEvent(SQLModel, table=True):
    __tablename__ = "model_node_usage_events"

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: Optional[str] = Field(default=None, index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    node_id: str = Field(default="", index=True)
    provider: str = Field(default="", index=True)
    model: str = Field(default="", index=True)
    agent_id: Optional[str] = Field(default=None, index=True)
    role_id: Optional[str] = Field(default=None, index=True)
    task_kind: str = Field(default="", index=True)
    prompt_tokens: int = Field(default=0, index=True)
    completion_tokens: int = Field(default=0, index=True)
    total_tokens: int = Field(default=0, index=True)
    latency_ms: int = Field(default=0, index=True)
    cost_estimate: float = Field(default=0.0, index=True)
    event_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)


class TeamSelectionEvent(SQLModel, table=True):
    __tablename__ = "team_selection_events"

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    task_text: str = Field(default="")
    selected_blueprint_id: Optional[str] = Field(default=None, index=True)
    recommendation_json: str = Field(default="{}")
    outcome_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)



class TaskAttempt(SQLModel, table=True):
    __tablename__ = "task_attempts"
    __table_args__ = (UniqueConstraint("thread_id", "attempt_id", name="uq_task_attempts_thread_attempt"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    task_id: str = Field(index=True)
    attempt_id: str = Field(index=True)
    parent_attempt_id: Optional[str] = Field(default=None, index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    run_mode: str = Field(default="new", index=True)
    status: str = Field(default="draft", index=True)
    target_team: str = Field(default="general", index=True)
    previous_result_policy: str = Field(default="optional", index=True)
    work_mode: str = Field(default="assisted_task", index=True)
    review_policy: str = Field(default="optional", index=True)
    memory_projection_profile: str = Field(default="general", index=True)
    memory_package_id: Optional[str] = Field(default=None, index=True)
    task_text: str = Field(default="")
    context_policy_json: str = Field(default="{}")
    memory_package_json: str = Field(default="{}")
    candidate_snapshot_json: str = Field(default="{}")
    result_json: str = Field(default="{}")
    lineage_json: str = Field(default="{}")
    launch_json: str = Field(default="{}")
    meta_json: str = Field(default="{}")
    created_by: str = Field(default="goc", index=True)
    promoted_at: Optional[datetime] = Field(default=None, index=True)
    archived_at: Optional[datetime] = Field(default=None, index=True)
    launched_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class TaskAttemptEvent(SQLModel, table=True):
    __tablename__ = "task_attempt_events"

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    task_id: str = Field(index=True)
    attempt_id: str = Field(index=True)
    event_type: str = Field(default="created", index=True)
    actor: str = Field(default="goc", index=True)
    summary: str = Field(default="")
    event_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)


class SemanticBoardCard(SQLModel, table=True):
    __tablename__ = "semantic_board_cards"
    __table_args__ = (UniqueConstraint("thread_id", "card_id", name="uq_semantic_board_cards_thread_card"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    card_id: str = Field(index=True)
    card_type: str = Field(default="memory_card", index=True)
    title: str = Field(default="", index=True)
    status: str = Field(default="candidate", index=True)
    source: str = Field(default="ddalggak", index=True)
    source_ref: str = Field(default="")
    confidence: float = Field(default=0.0, index=True)
    reuse_score: float = Field(default=0.0, index=True)
    tags_json: str = Field(default="[]")
    content_json: str = Field(default="{}")
    scope_json: str = Field(default="{}")
    performance_json: str = Field(default="{}")
    card_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class SemanticBoardLink(SQLModel, table=True):
    __tablename__ = "semantic_board_links"
    __table_args__ = (UniqueConstraint("thread_id", "link_id", name="uq_semantic_board_links_thread_link"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    link_id: str = Field(index=True)
    from_card_id: str = Field(index=True)
    to_card_id: str = Field(index=True)
    link_type: str = Field(default="related_to", index=True)
    status: str = Field(default="active", index=True)
    weight: float = Field(default=0.0, index=True)
    reason: str = Field(default="")
    link_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)
    updated_at: datetime = Field(default_factory=utcnow, index=True)


class SemanticBoardEvent(SQLModel, table=True):
    __tablename__ = "semantic_board_events"

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    event_id: str = Field(default="", index=True)
    event_type: str = Field(default="event", index=True)
    source: str = Field(default="ddalggak", index=True)
    payload_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)
    ingested_at: datetime = Field(default_factory=utcnow, index=True)


class ContextSubstrateSnapshot(SQLModel, table=True):
    __tablename__ = "context_substrate_snapshots"
    __table_args__ = (UniqueConstraint("thread_id", "snapshot_id", name="uq_context_substrate_snapshots_thread_snapshot"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    snapshot_id: str = Field(index=True)
    version: int = Field(default=0, index=True)
    atom_count: int = Field(default=0, index=True)
    link_count: int = Field(default=0, index=True)
    manifest_json: str = Field(default="{}")
    snapshot_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)
    ingested_at: datetime = Field(default_factory=utcnow, index=True)


class ContextSubstrateOperation(SQLModel, table=True):
    __tablename__ = "context_substrate_operations"
    __table_args__ = (UniqueConstraint("thread_id", "operation_id", name="uq_context_substrate_operations_thread_operation"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    operation_id: str = Field(index=True)
    op: str = Field(default="operation", index=True)
    version: int = Field(default=0, index=True)
    status: str = Field(default="committed", index=True)
    lane: str = Field(default="normal", index=True)
    commit_mode: str = Field(default="auto", index=True)
    actor: str = Field(default="runtime", index=True)
    operation_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)
    ingested_at: datetime = Field(default_factory=utcnow, index=True)


class ContextProjectionEvent(SQLModel, table=True):
    __tablename__ = "context_projection_events"
    __table_args__ = (UniqueConstraint("thread_id", "projection_id", name="uq_context_projection_events_thread_projection"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    projection_id: str = Field(index=True)
    snapshot_id: str = Field(default="", index=True)
    agent_id: str = Field(default="", index=True)
    role_id: str = Field(default="", index=True)
    task_type: str = Field(default="", index=True)
    model_node: str = Field(default="", index=True)
    cache_hit: bool = Field(default=False, index=True)
    compile_ms: int = Field(default=0, index=True)
    context_tokens: int = Field(default=0, index=True)
    selected_atom_count: int = Field(default=0, index=True)
    selected_link_count: int = Field(default=0, index=True)
    handoff_count: int = Field(default=0, index=True)
    goal_hash: str = Field(default="", index=True)
    payload_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)
    ingested_at: datetime = Field(default_factory=utcnow, index=True)


class ContextWriteMetricEvent(SQLModel, table=True):
    __tablename__ = "context_write_metric_events"
    __table_args__ = (UniqueConstraint("thread_id", "event_id", name="uq_context_write_metric_events_thread_event"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    event_id: str = Field(index=True)
    projection_id: str = Field(default="", index=True)
    snapshot_id: str = Field(default="", index=True)
    status: str = Field(default="", index=True)
    batch_size: int = Field(default=0, index=True)
    committed: int = Field(default=0, index=True)
    proposals: int = Field(default=0, index=True)
    conflicts: int = Field(default=0, index=True)
    operation_append_ms: int = Field(default=0, index=True)
    payload_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)
    ingested_at: datetime = Field(default_factory=utcnow, index=True)


class HandoffDeltaEvent(SQLModel, table=True):
    __tablename__ = "handoff_delta_events"
    __table_args__ = (UniqueConstraint("thread_id", "handoff_id", name="uq_handoff_delta_events_thread_handoff"),)

    id: str = Field(default_factory=new_id, primary_key=True)
    thread_id: str = Field(index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    handoff_id: str = Field(index=True)
    from_agent: str = Field(default="", index=True)
    to_agent: str = Field(default="", index=True)
    handoff_type: str = Field(default="agent_delta", index=True)
    snapshot_id: str = Field(default="", index=True)
    projection_id: str = Field(default="", index=True)
    delta_tokens: int = Field(default=0, index=True)
    summary: str = Field(default="")
    delta_json: str = Field(default="{}")
    payload_json: str = Field(default="{}")
    created_at: datetime = Field(default_factory=utcnow, index=True)
    ingested_at: datetime = Field(default_factory=utcnow, index=True)
