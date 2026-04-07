from __future__ import annotations
from datetime import datetime
from typing import Any, List, Literal, Optional
from pydantic import BaseModel, Field
from sqlmodel import SQLModel


class ThreadCreate(BaseModel):
    title: Optional[str] = None
    service_id: Optional[str] = None  # admin-only override
    external_ref: Optional[str] = None
    meta_json: Optional[dict[str, Any]] = None


class ThreadEnsureRequest(BaseModel):
    external_ref: str
    title: Optional[str] = None
    service_id: Optional[str] = None  # admin-only override
    meta_json: Optional[dict[str, Any]] = None


class ThreadRead(BaseModel):
    id: str
    service_id: str
    title: str
    external_ref: Optional[str] = None
    meta_json: dict[str, Any]
    created_at: datetime


class MessageCreate(BaseModel):
    role: str  # user | assistant
    text: str
    reply_to: Optional[str] = None


class ResourceNodeCreate(BaseModel):
    name: str
    summary: Optional[str] = None
    resource_kind: str = "file"  # file | link | image | table | doc | code | other
    mime_type: Optional[str] = None
    uri: Optional[str] = None
    source: Literal["chatgpt_upload", "manual", "link", "unknown"] = "chatgpt_upload"
    attach_to: Optional[str] = None
    context_set_id: Optional[str] = None
    auto_activate: bool = True
    raw_text: Optional[str] = None
    payload_json: Optional[dict[str, Any]] = None
    text_mode: Optional[Literal["formatted", "plain"]] = None


class ContextSetCreate(BaseModel):
    thread_id: str
    name: str = "default"


class CloneContextSetRequest(BaseModel):
    name: Optional[str] = None
    meta: Optional[dict[str, Any]] = None


class ActivateNodes(BaseModel):
    node_ids: List[str]


class FoldCreate(BaseModel):
    thread_id: str
    member_node_ids: List[str]
    title: Optional[str] = None


class RunCreate(BaseModel):
    context_set_id: str
    user_message: str


class SearchResponseItem(BaseModel):
    node_id: str
    score: float
    node_type: str
    snippet: str


class NodePositionUpdate(BaseModel):
    id: str
    x: float
    y: float


class NodeLayoutUpdate(BaseModel):
    positions: List[NodePositionUpdate]


class EdgeCreate(BaseModel):
    from_id: str
    to_id: str
    type: str = "NEXT"


class NodeConnectFrom(BaseModel):
    node_id: str
    edge_type: str = "NEXT"


class NodeCreate(BaseModel):
    type: str
    text: Optional[str] = None
    payload_json: Optional[dict[str, Any]] = None
    connect_from: Optional[Literal["last"] | NodeConnectFrom] = None


class NodeCreateResponse(BaseModel):
    id: str
    thread_id: str
    type: str
    text: Optional[str] = None
    payload_json: str
    created_at: datetime


class ActiveOrderUpdate(BaseModel):
    node_ids: List[str]


class ChatGPTImportRequest(BaseModel):
    raw_text: str
    context_set_id: Optional[str] = None
    reply_to: Optional[str] = None
    source: Literal["chatgpt_web", "unknown"] = "unknown"
    auto_activate: Optional[bool] = None


class TokenEstimateRequest(BaseModel):
    text: str
    model: Optional[str] = None


SplitStrategy = Literal["auto", "tagged", "heading", "bullets", "paragraph", "sentences", "custom"]


class SplitNodeRequest(BaseModel):
    strategy: SplitStrategy = "auto"
    custom_text: Optional[str] = None
    child_type: Optional[str] = None
    context_set_id: Optional[str] = None
    replace_in_active: bool = False
    inherit_reply_to: bool = True
    target_chars: Optional[int] = 900
    max_chars: Optional[int] = 2000


class NodePatchRequest(BaseModel):
    text: Optional[str] = None
    payload_json: Optional[str | dict[str, Any]] = None


class NodePinRequest(BaseModel):
    level: Optional[Literal["required", "preferred"]] = None


class ServiceRequestCreate(BaseModel):
    name: str
    description: Optional[str] = None


class PublishRequestCreate(BaseModel):
    source_node_id: str


class MintUiTokenRequest(BaseModel):
    ttl_sec: Optional[int] = None


class SplitNodeResponse(BaseModel):
    ok: bool = True
    parent_id: str
    created_ids: List[str]
    strategy_used: str


class HierarchyPreviewRequest(BaseModel):
    context_set_id: Optional[str] = None
    node_ids: Optional[List[str]] = None
    max_leaf_size: int = 6


class UnfoldRequest(BaseModel):
    closure_edge_types: Optional[List[str]] = None
    closure_direction: Literal["out", "in", "both"] = "out"
    max_closure_nodes: Optional[int] = None
    replace_only_fold: bool = True
    include_explain: bool = True


class UnfoldPlanRequest(BaseModel):
    query: str
    top_k: int = 8
    max_candidates: int = 16
    budget_tokens: int = 1200
    closure_edge_types: Optional[List[str]] = None
    closure_direction: Literal["out", "in", "both"] = "both"
    max_closure_nodes: Optional[int] = 12


class ApplyUnfoldPlanRequest(BaseModel):
    seed_node_ids: List[str]
    budget_tokens: int = 1200
    closure_edge_types: Optional[List[str]] = None
    closure_direction: Literal["out", "in", "both"] = "both"
    max_closure_nodes: Optional[int] = 12
    include_explain: bool = True


class RebuildActivePolicy(BaseModel):
    recent_user_messages: int = 6
    recent_assistant_messages: int = 6
    recent_steps: int = 10
    recent_artifacts: int = 5
    exclude_resource_kinds: List[str] = Field(default_factory=lambda: ["job_config", "tracking_append"])
    include_pinned: bool = True


class RebuildActiveRequest(BaseModel):
    policy: RebuildActivePolicy = Field(default_factory=RebuildActivePolicy)


AgentVisibility = Literal["private", "unlisted", "public"]


class AgentCreateRequest(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = ""
    instruction: str = ""
    tools: List[str] = Field(default_factory=list)
    model: str = ""
    visibility: AgentVisibility = "private"


class AgentPatchRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    instruction: Optional[str] = None
    tools: Optional[List[str]] = None
    model: Optional[str] = None
    visibility: Optional[AgentVisibility] = None


class AgentForkRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    instruction: Optional[str] = None
    tools: Optional[List[str]] = None
    model: Optional[str] = None
    visibility: AgentVisibility = "private"
    reason: Optional[str] = None
    purpose: Optional[str] = None
    scope: Optional[dict[str, Any]] = None
    scope_node_ids: Optional[List[str]] = None
    source_surface_ids: Optional[List[str]] = None
    publish_surface_ids: Optional[List[str]] = None
    source_thread_id: Optional[str] = None
    source_run_id: Optional[str] = None
    rejoin_strategy: Optional[str] = None


class AgentRejoinRequest(BaseModel):
    target_agent_id: Optional[str] = None
    summary: Optional[str] = None
    publish_surface_ids: Optional[List[str]] = None
    artifact_ids: Optional[List[str]] = None
    include_recent_outputs: bool = True


class AgentArchiveRequest(BaseModel):
    archived: bool = True


class AgentBootstrapDefaultsRequest(BaseModel):
    thread_id: Optional[str] = None
    add_to_conversation: bool = Field(
        default=False,
        description="When true, add installed default private copies as explicit conversation membership.",
    )


class ConversationEnsureRequest(BaseModel):
    thread_id: str
    bootstrap_defaults: bool = Field(
        default=False,
        description="Install default/private copies for the conversation owner without creating explicit membership.",
    )
    add_to_conversation: bool = Field(
        default=False,
        description="Seed explicit conversation membership from the bootstrapped default copies.",
    )


class ConversationAgentCreateRequest(BaseModel):
    agent_id: str
    enabled: bool = True
    order_index: Optional[int] = None
    overrides_json: Optional[dict[str, Any]] = None


class ConversationAgentPatchRequest(BaseModel):
    enabled: Optional[bool] = None
    order_index: Optional[int] = None
    overrides_json: Optional[dict[str, Any]] = None


class ConversationAgentReorderRequest(BaseModel):
    agent_ids: List[str]


class RuntimeTeamViewItem(BaseModel):
    runtime_instance_id: Optional[str] = None
    display_label: Optional[str] = None
    slot_id: Optional[str] = None
    slot_label: Optional[str] = None
    role_id: Optional[str] = None
    role_label: Optional[str] = None
    preset_id: Optional[str] = None
    synthesized: bool = False
    selection_reason: Optional[str] = None
    attached_skill_ids: List[str] = Field(default_factory=list)
    context_pack_id: Optional[str] = None
    runtime_status: Optional[str] = None
    authority_profile_id: Optional[str] = None


class RuntimeTeamViewProjection(BaseModel):
    items: List[RuntimeTeamViewItem] = Field(default_factory=list)
    count: int = 0
    preset_count: int = 0
    synthesized_count: int = 0


class WhyThisTeamProjection(BaseModel):
    selection_explanations: List[dict[str, Any]] = Field(default_factory=list)
    slot_reasons: List[dict[str, Any]] = Field(default_factory=list)
    agent_reasons: List[dict[str, Any]] = Field(default_factory=list)
    conversation_preferences: Optional[dict[str, Any]] = None
    preset_count: int = 0
    synthesized_count: int = 0


class OrchestrationProjection(BaseModel):
    mode: str = "runtime_managed"
    parallel_groups: List[dict[str, Any]] = Field(default_factory=list)
    sequential_after: dict[str, List[str]] = Field(default_factory=dict)
    supervisor_runtime: dict[str, Any] = Field(default_factory=dict)
    supervisor_mode: Optional[str] = None
    supervisor_enabled: bool = False
    supervisor_edges: List[dict[str, Any]] = Field(default_factory=list)
    checkpoint_count: int = 0
    checkpoint_status_counts: dict[str, int] = Field(default_factory=dict)
    parallel_group_count: int = 0
    sequential_dependency_count: int = 0
    supervisor_edge_count: int = 0


class CollaborationProjection(BaseModel):
    items: List[dict[str, Any]] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    count: int = 0


class RuntimeAuthorityProjection(BaseModel):
    items: List[dict[str, Any]] = Field(default_factory=list)
    graph: List[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    graph_count: int = 0


class CheckpointsProjection(BaseModel):
    items: List[dict[str, Any]] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class RunCapabilityProjection(BaseModel):
    run_id: Optional[str] = None
    runtime_agents: List[dict[str, Any]] = Field(default_factory=list)
    attached_skills: List[dict[str, Any]] = Field(default_factory=list)
    skill_packages: List[dict[str, Any]] = Field(default_factory=list)
    context_packs: List[dict[str, Any]] = Field(default_factory=list)
    skill_usage: List[dict[str, Any]] = Field(default_factory=list)
    lineage: dict[str, Any] = Field(default_factory=dict)
    task_interpretation: Optional[dict[str, Any]] = None
    team_view: RuntimeTeamViewProjection = Field(default_factory=RuntimeTeamViewProjection)
    why_this_team: WhyThisTeamProjection = Field(default_factory=WhyThisTeamProjection)
    orchestration: OrchestrationProjection = Field(default_factory=OrchestrationProjection)
    collaboration: CollaborationProjection = Field(default_factory=CollaborationProjection)
    authority: RuntimeAuthorityProjection = Field(default_factory=RuntimeAuthorityProjection)
    checkpoints: CheckpointsProjection = Field(default_factory=CheckpointsProjection)
    counts: dict[str, int] = Field(default_factory=dict)
    planning_boundary: Optional[dict[str, Any]] = None


class ConversationTeamConfigRequest(BaseModel):
    team_config: dict[str, Any]




class TeamManifestValidateRequest(BaseModel):
    manifest: dict[str, Any]
    apply_state: Optional[Literal["active", "pending"]] = "active"


class TeamManifestInstallRequest(BaseModel):
    manifest: dict[str, Any]
    apply_state: Optional[Literal["active", "pending"]] = "active"


class TeamManifestDiffRequest(BaseModel):
    manifest: dict[str, Any]
    apply_state: Optional[Literal["active", "pending"]] = "active"


class ConversationTeamAgentContextPolicyPatchRequest(BaseModel):
    team_state: str
    agent_id: str
    visibility_mode: Optional[str] = None
    grants: List[str] = Field(default_factory=list)
    context_types: List[str] = Field(default_factory=list)
    publish_targets: List[str] = Field(default_factory=list)
    query_template: Optional[str] = None
    soft_tokens: Optional[int] = None
    hard_tokens: Optional[int] = None

class ConversationTeamConfigRead(BaseModel):
    thread_id: str
    conversation_id: str
    status: str = "none"
    composition_mode: str = "structured"
    proposal_mode: str = "suggest"
    active_team: dict[str, Any] = Field(default_factory=dict)
    pending_team: dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[datetime] = None


class MemorySurfaceCreateRequest(SQLModel):
    surface_id: str
    title: str | None = None
    semantic_kind: str | None = None
    visibility_scope: str | None = None
    write_mode: str | None = None
    policy: dict[str, Any] | None = None


class MemoryNodeCreateRequest(SQLModel):
    surface_id: str
    node_type: str | None = None
    owner_agent_id: str | None = None
    owner_role_id: str | None = None
    content: dict[str, Any] | None = None
    provenance: dict[str, Any] | None = None
    trust_tier: str | None = None
    status: str | None = None
    created_run_id: str | None = None


class MemoryProjectionRequest(SQLModel):
    role_id: str | None = None
    agent_id: str | None = None
    run_id: str | None = None
    include_surface_ids: list[str] | None = None
    exclude_surface_ids: list[str] | None = None




class MemoryConflictResolveRequest(SQLModel):
    status: str | None = None
    winning_node_id: str | None = None
    losing_node_ids: list[str] | None = None
    summary: str | None = None
    rationale_codes: list[str] | None = None
    supporting_claim_node_ids: list[str] | None = None
    supporting_evidence_node_ids: list[str] | None = None
    supporting_memory_node_ids: list[str] | None = None
    resolved_by: str | None = None
    resolution_source: str | None = None
    merge_note: str | None = None

class TeamRecommendationRequest(SQLModel):
    task_text: str
    limit: int | None = 3


class TeamSelectionRecordRequest(SQLModel):
    run_id: str | None = None
    task_text: str
    selected_blueprint_id: str | None = None
    recommendation: dict[str, Any] | None = None
    outcome: dict[str, Any] | None = None
