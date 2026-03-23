export type SkillPackage = {
  id: string
  slug?: string | null
  name?: string | null
  version?: string | null
  description?: string | null
  category?: string | null
  capability_tags?: string[]
  compatible_roles?: string[]
  instructions_ref?: string | null
  resource_refs?: string[]
  utility_refs?: string[]
  visibility?: string | null
  status?: string | null
  source?: string | null
}

export type AttachedSkillSummary = {
  skill_id: string
  skill_name?: string | null
  load_level?: string | null
  selected_by?: string | null
  selection_reason?: string | null
  status?: string | null
  role_count?: number
}

export type StructuredRuntimeValue =
  | string
  | number
  | boolean
  | Record<string, unknown>
  | unknown[]

export type TaskInterpretation = {
  summary?: string | null
  items?: string[]
  [key: string]: unknown
}

export type CapabilitySlotSpec = {
  slot_id?: string | null
  role_id?: string | null
  display_label?: string | null
  label?: string | null
  name?: string | null
  preset_id?: string | null
  synthesized?: boolean
  selection_reason?: string | null
  capabilities?: string[]
  [key: string]: unknown
}

export type SupervisorRuntime = {
  interaction_mode?: string | null
  mode?: string | null
  kind?: string | null
  strategy?: string | null
  instance_id?: string | null
  authority_profile_id?: string | null
  user_visible?: boolean
  enabled?: boolean
  [key: string]: unknown
}

export type CollaborationCell = {
  cell_id?: string | null
  pattern?: string | null
  kind?: string | null
  display_label?: string | null
  member_instance_ids?: string[]
  member_labels?: string[]
  report_back_to_instance_id?: string | null
  report_back_to_label?: string | null
  decision_mode?: string | null
  selection_reason?: string | null
  max_rounds?: number | null
  topology?: string | null
  termination?: StructuredRuntimeValue | null
  termination_summary?: string | null
  termination_rule?: StructuredRuntimeValue | null
  [key: string]: unknown
}

export type AuthorityGraphEntry = {
  authority_id?: string | null
  runtime_instance_id?: string | null
  authority_profile_id?: string | null
  managed_by?: string | null
  scope?: string | null
  allowed_actions?: string[]
  denied_actions?: string[]
  restricted_actions?: string[]
  approval_required_for?: string[]
  tool_allowlist?: string[]
  [key: string]: unknown
}

export type ExecutionCheckpoint = {
  checkpoint_id?: string | null
  kind?: string | null
  label?: string | null
  stage?: string | null
  status?: string | null
  human_interrupt_allowed?: boolean
  requires_human?: boolean
  approval_required?: boolean
  requires_approval?: boolean
  blocking?: boolean
  trigger_after_instances?: string[]
  trigger_after_labels?: string[]
  supervisor_decision?: StructuredRuntimeValue | null
  supervisor_decision_summary?: string | null
  completion_signal?: StructuredRuntimeValue | null
  completion_signal_summary?: string | null
  selection_reason?: string | null
  [key: string]: unknown
}

export type RuntimeAgentWithSkills = {
  runtime_instance_id?: string | null
  instance_id?: string | null
  role_label?: string | null
  role_id?: string | null
  slot_id?: string | null
  slot_label?: string | null
  template_id?: string | null
  preset_id?: string | null
  authority_profile_id?: string | null
  scope_id?: string | null
  visibility_mode?: string | null
  grant_labels?: string[]
  scope_token_estimate?: number | null
  provider?: string | null
  model?: string | null
  runtime_status?: string | null
  attached_skills?: AttachedSkillSummary[]
  attached_skill_ids?: string[]
  context_pack_id?: string | null
  source?: string | null
  source_key?: string | null
  source_path?: string | null
  agent_id?: string | null
  name?: string | null
  display_label?: string | null
  selection_reason?: string | null
  synthesized?: boolean
  enabled?: boolean
  configured_only?: boolean
  config_state?: string | null
  team_name?: string | null
  composition_mode?: string | null
  proposal_mode?: string | null
  purpose?: string | null
  context_policy?: Record<string, unknown> | null
  context_policy_summary?: string | null
  context_types?: string[]
  publish_targets?: string[]
  query_template?: string | null
  shortcut_eligible?: boolean | null
  shortcut_max_recent_turns?: number | null
  only_for_followups?: boolean
  interaction_contract?: Record<string, unknown> | null
}

export type TeamBlueprintSummary = {
  source?: string | null
  blueprint_id?: string | null
  title?: string | null
  task_archetype?: string | null
  description?: string | null
  topology_pattern?: string | null
  execution_pattern?: string | null
  capability_status?: string | null
  required_tool_count?: number | null
  optional_tool_count?: number | null
  missing_required_tool_count?: number | null
  missing_optional_tool_count?: number | null
  missing_required_tools?: string[]
  missing_optional_tools?: string[]
  memory_surface_count?: number | null
  memory_contract_enforcement?: {
    read_scope?: string | null
    write_scope?: string | null
    publish_scope?: string | null
    final_publish_rule?: string | null
    artifact_publish_rule?: string | null
  } | null
  publish_contract_readiness?: {
    final_owner?: string | null
    final_owner_id?: string | null
    final_owner_missing?: boolean | null
    final_answer_publish_ok?: boolean | null
    final_answer_publish_state?: string | null
    artifact_publish_ok?: boolean | null
    artifact_publish_state?: string | null
    artifact_publishers?: string[]
    artifact_publisher_ids?: string[]
  } | null
  memory_map?: Array<{
    surface_id?: string | null
    file_name?: string | null
    load_policy?: string | null
    write_policy?: string | null
    target_roles?: string[]
    semantic_slots?: string[]
  }>
}

export type RuntimeAgentInstanceV2 = RuntimeAgentWithSkills & {
  display_label?: string | null
  role_label?: string | null
  role_id?: string | null
  slot_id?: string | null
  slot_label?: string | null
  preset_id?: string | null
  synthesized?: boolean
  selection_reason?: string | null
  context_pack_id?: string | null
  authority_profile_id?: string | null
}

export type TeamViewProjection = {
  items?: RuntimeAgentInstanceV2[]
  count?: number
  preset_count?: number
  synthesized_count?: number
  blueprint_summary?: TeamBlueprintSummary | null
}

export type ScopeProjection = {
  context_runtime_mode?: string | null
  legacy_context_pack_count?: number
  legacy_context_packs_enabled?: boolean
  legacy_context_strategy?: string | null
  scope_first_ready?: boolean
  scope_projection_note?: string | null
  items?: Array<{
    scope_id?: string | null
    runtime_instance_id?: string | null
    slot_id?: string | null
    display_label?: string | null
    visibility_mode?: string | null
    context_types?: string[]
    memory_grants?: Record<string, unknown>
    grant_labels?: string[]
    selection_reason?: string | null
    context_set_id?: string | null
    token_estimate?: number | null
    scope_version?: number | null
    active_node_ids?: string[]
    active_node_count?: number | null
    active_type_labels?: string[]
    visibility_rationale?: string | null
    compiler?: string | null
    authoritative_scope?: boolean
    empty_scope?: boolean
    soft_budget_exceeded?: boolean
    selection_strategy?: string | null
    selection_summary?: string | null
    matched_query_terms?: string[]
    matched_context_types?: string[]
    seed_node_count?: number | null
    candidate_node_count?: number | null
    positive_candidate_count?: number | null
    rejected_positive_node_ids?: string[]
    selection_confidence?: string | null
    truncated?: boolean
  }>
  count?: number
  grant_counts?: Record<string, number>
  visibility_counts?: Record<string, number>
}

export type VisibilityProjection = {
  items?: Array<{
    edge_id?: string | null
    from_scope_id?: string | null
    to_scope_id?: string | null
    from_label?: string | null
    to_label?: string | null
    relation?: string | null
  }>
  count?: number
  relation_counts?: Record<string, number>
}

export type WhyThisTeamProjection = {
  blueprint_summary?: TeamBlueprintSummary | null
  selection_explanations?: Array<Record<string, unknown>>
  slot_reasons?: Array<{
    slot_id?: string | null
    role_id?: string | null
    display_label?: string | null
    reason?: string | null
  }>
  agent_reasons?: Array<{
    runtime_instance_id?: string | null
    display_label?: string | null
    reason?: string | null
  }>
  conversation_preferences?: Record<string, unknown> | null
  preset_count?: number
  synthesized_count?: number
}

export type OrchestrationProjection = {
  mode?: string | null
  parallel_groups?: Array<{
    group_id?: string | null
    label?: string | null
    member_instance_ids?: string[]
    member_labels?: string[]
    [key: string]: unknown
  }>
  sequential_after?: Record<string, string[]>
  supervisor_runtime?: SupervisorRuntime
  supervisor_mode?: string | null
  supervisor_enabled?: boolean
  supervisor_edges?: Array<Record<string, unknown>>
  checkpoint_count?: number
  checkpoint_status_counts?: Record<string, number>
  parallel_group_count?: number
  sequential_dependency_count?: number
  supervisor_edge_count?: number
}

export type CollaborationProjection = {
  items?: CollaborationCell[]
  counts?: Record<string, number>
  count?: number
}

export type AuthorityProjection = {
  items?: Array<{
    runtime_instance_id?: string | null
    display_label?: string | null
    authority_profile_id?: string | null
    managed_by?: string | null
    allowed_actions?: string[]
    denied_actions?: string[]
    restricted_actions?: string[]
    approval_required_for?: string[]
    tool_allowlist?: string[]
    graph_entry_count?: number
  }>
  graph?: AuthorityGraphEntry[]
  count?: number
  graph_count?: number
}

export type CheckpointProjection = {
  items?: ExecutionCheckpoint[]
  counts?: Record<string, number>
}

export type ContextPackSummary = {
  context_pack_id?: string | null
  scope?: string | null
  target_runtime_agent_instance_id?: string | null
  shared_items_count?: number
  role_specific_items_count?: number
  skill_items?: Array<{
    skill_id: string
    load_level?: string | null
    count?: number
  }>
  missing_items?: unknown[]
  conflicts?: unknown[]
  source?: string | null
  run_id?: string | null
  node_id?: string | null
  node_type?: string | null
}

export type SkillUsageEventSummary = {
  skill_id: string
  skill_name?: string | null
  event_type?: string | null
  timestamp?: string | null
  payload_summary?: string | null
  source?: string | null
  run_id?: string | null
  node_id?: string | null
  node_type?: string | null
  runtime_instance_id?: string | null
  selection_reason?: string | null
  load_level?: string | null
}

export type RuntimeAuthorityProjection = {
  mode?: 'standalone' | 'goc'
  plan_source?: 'local' | 'goc' | 'local_fallback'
  context_source?: 'local' | 'goc'
  agent_catalog_source?: 'local' | 'goc'
  conversation_team_source?: 'local' | 'goc'
  skill_catalog_source?: 'local' | 'goc' | 'mixed'
  degraded_mode?: boolean
  fallback_reason?: string | null
}

export type PlanningBoundaryProjection = {
  status?: string | null
  managed_by?: string | null
  run_id?: string | null
  plan_source?: string | null
  mode?: string | null
  degraded_mode?: boolean
  fallback_reason?: string | null
  stages?: Array<{
    stage?: string | null
    status?: string | null
    managed_by?: string | null
  }>
  ready_for_goc_control_plane?: boolean
  ready_for_goc_planner?: boolean
  future_capabilities?: string[]
}

export type RunStudioNow = {
  task?: {
    current_task?: string | null
    current_objective?: string | null
    current_step?: string | null
    current_step_id?: string | null
    current_step_status?: string | null
    latest_user_message_id?: string | null
    latest_user_message_text?: string | null
  }
  state?: {
    run_status?: string | null
    blocked?: boolean
    blocked_reason?: string | null
    current_blocked?: boolean
    current_blocked_reason?: string | null
    pending_approval?: boolean
    pending_approval_count?: number
    current_pending_approval?: boolean
    current_pending_approval_count?: number
    active_context_count?: number
    step_status_counts?: Record<string, number>
    current_run_step_status_counts?: Record<string, number>
    current_run_id?: string | null
    current_run_status?: string | null
    current_run_inactive?: boolean
    current_run_selection_source?: string | null
    current_run_step_count?: number
    stale_queued_step_count?: number
    runtime_authority?: RuntimeAuthorityProjection
    mode?: 'standalone' | 'goc'
    plan_source?: 'local' | 'goc' | 'local_fallback'
    context_source?: 'local' | 'goc'
    agent_catalog_source?: 'local' | 'goc'
    conversation_team_source?: 'local' | 'goc'
    skill_catalog_source?: 'local' | 'goc' | 'mixed'
    degraded_mode?: boolean
    fallback_reason?: string | null
  }
  current_run?: {
    id?: string | null
    node_id?: string | null
    created_at?: string | null
    status?: string | null
    inactive?: boolean
    selection_source?: string | null
    step_count?: number
    stale_queued_step_count?: number
    runtime_authority?: RuntimeAuthorityProjection
    mode?: 'standalone' | 'goc'
    plan_source?: 'local' | 'goc' | 'local_fallback'
    context_source?: 'local' | 'goc'
    agent_catalog_source?: 'local' | 'goc'
    conversation_team_source?: 'local' | 'goc'
    skill_catalog_source?: 'local' | 'goc' | 'mixed'
    degraded_mode?: boolean
    fallback_reason?: string | null
  }
  pending_approval_items?: Array<{
    id: string
    type: string
    text?: string | null
    created_at?: string | null
  }>
  current_pending_approval_items?: Array<{
    id: string
    type: string
    text?: string | null
    created_at?: string | null
  }>
  latest_run?: {
    id?: string | null
    created_at?: string | null
    summary?: string | null
  }
  updated_at?: string | null
}

export type RunStudioSummary = {
  thread?: {
    id?: string | null
    title?: string | null
    external_ref?: string | null
  }
  context_set?: {
    id?: string | null
    name?: string | null
    active_count?: number
  }
  now?: RunStudioNow
  agent_team?: RunStudioAgentTeam
  projections?: {
    conversation?: {
      message_count?: number
      participant_roles?: string[]
      latest_user_message_id?: string | null
      latest_assistant_message_id?: string | null
      recent_messages?: Array<{
        id: string
        role?: string | null
        text?: string | null
        created_at?: string | null
      }>
    }
    execution?: {
      run_count?: number
      step_count?: number
      tool_count?: number
      artifact_count?: number
      current_step?: {
        id?: string | null
        run_id?: string | null
        status?: string | null
        agent_id?: string | null
        goal?: string | null
      } | null
      recent_runs?: Array<{
        id: string
        status?: string | null
        step_count?: number
      }>
      recent_steps?: Array<{
        id: string
        status?: string | null
        agent_id?: string | null
        goal?: string | null
      }>
    }
    memory_context?: {
      context_node_count?: number
      core_count?: number
      supporting_count?: number
      execution_count?: number
      selected_count?: number
      pinned_count?: number
      conflict_count?: number
      support_count?: number
      reference_count?: number
      core_items?: Array<{
        id: string
        type?: string | null
        text?: string | null
        selected?: boolean
        pinned?: boolean
      }>
      supporting_items?: Array<{
        id: string
        type?: string | null
        text?: string | null
        selected?: boolean
        pinned?: boolean
      }>
      execution_items?: Array<{
        id: string
        type?: string | null
        text?: string | null
        selected?: boolean
      }>
      recent_items?: Array<{
        id: string
        type?: string | null
        text?: string | null
        selected?: boolean
        pinned?: boolean
      }>
    }
  }
  context_decisions_counts?: Record<string, number>
  evidence_counts?: Record<string, number>
  skill_counts?: Record<string, number>
  current_run_skills?: {
    run_id?: string | null
    attached_skills?: AttachedSkillSummary[]
    runtime_agents?: RuntimeAgentInstanceV2[]
    skill_packages?: SkillPackage[]
    context_packs?: ContextPackSummary[]
    skill_usage?: SkillUsageEventSummary[]
    task_interpretation?: TaskInterpretation | null
    execution_insights?: {
      execution_pattern?: string | null
      selection?: {
        selected?: string[]
        suppressed?: string[]
        planner_facts?: string[]
      }
      execution?: {
        planned_agent_count?: number
        observed_agent_count?: number
        participation_pct?: number
        planned_agents?: string[]
        observed_agents?: string[]
        missing_agents?: string[]
        extra_agents?: string[]
        participation_by_role?: string[]
      }
      overlays?: string[]
    } | null
    execution_feedback?: {
      updated_at?: string | null
      run_count?: number
      patterns?: Array<{
        execution_pattern?: string | null
        run_count?: number
        avg_participation_pct?: number
        avg_planned_agents?: number
        avg_observed_agents?: number
        avg_missing_agents?: number
        completion_rate_pct?: number
        recommendation?: string | null
        reason?: string | null
      }>
      overlays?: Array<{
        overlay_id?: string | null
        title?: string | null
        run_count?: number
        prompt_count?: number
        avg_participation_pct?: number
        avg_overlay_tokens?: number
        avg_overlay_share_pct?: number
        recommendation?: string | null
        reason?: string | null
      }>
      recommended_patterns?: Array<{
        execution_pattern?: string | null
        run_count?: number
        avg_participation_pct?: number
        completion_rate_pct?: number
        recommendation?: string | null
        reason?: string | null
      }>
      discouraged_patterns?: Array<{
        execution_pattern?: string | null
        run_count?: number
        avg_participation_pct?: number
        completion_rate_pct?: number
        recommendation?: string | null
        reason?: string | null
      }>
      recommended_overlays?: Array<{
        overlay_id?: string | null
        title?: string | null
        run_count?: number
        avg_participation_pct?: number
        avg_overlay_tokens?: number
        avg_overlay_share_pct?: number
        recommendation?: string | null
        reason?: string | null
      }>
      discouraged_overlays?: Array<{
        overlay_id?: string | null
        title?: string | null
        run_count?: number
        avg_participation_pct?: number
        avg_overlay_tokens?: number
        avg_overlay_share_pct?: number
        recommendation?: string | null
        reason?: string | null
      }>
    } | null
    team_view?: TeamViewProjection
    why_this_team?: WhyThisTeamProjection
    scope_projection?: ScopeProjection
    visibility_projection?: VisibilityProjection
    orchestration?: OrchestrationProjection
    collaboration?: CollaborationProjection
    authority?: AuthorityProjection
    checkpoints?: CheckpointProjection
    lineage?: {
      role_skill_links?: Array<{
        runtime_instance_id?: string | null
        role_label?: string | null
        skill_id?: string | null
        skill_name?: string | null
        load_level?: string | null
        selected_by?: string | null
        selection_reason?: string | null
      }>
      skill_context_links?: Array<{
        context_pack_id?: string | null
        target_runtime_agent_instance_id?: string | null
        scope?: string | null
        skill_id?: string | null
        load_level?: string | null
        count?: number
      }>
      skill_evidence_links?: Array<{
        skill_id?: string | null
        event_type?: string | null
        from_node_id?: string | null
        to_node_id?: string | null
        to_node_type?: string | null
        edge_type?: string | null
      }>
      counts?: Record<string, number>
    }
    counts?: Record<string, number>
    updated_at?: string | null
    planning_boundary?: PlanningBoundaryProjection
    runtime_authority?: RuntimeAuthorityProjection
    mode?: 'standalone' | 'goc'
    plan_source?: 'local' | 'goc' | 'local_fallback'
    context_source?: 'local' | 'goc'
    agent_catalog_source?: 'local' | 'goc'
    conversation_team_source?: 'local' | 'goc'
    skill_catalog_source?: 'local' | 'goc' | 'mixed'
    degraded_mode?: boolean
    fallback_reason?: string | null
  }
  team_view?: TeamViewProjection
  why_this_team?: WhyThisTeamProjection
  scope_projection?: ScopeProjection
  visibility_projection?: VisibilityProjection
  orchestration?: OrchestrationProjection
  collaboration?: CollaborationProjection
  authority?: AuthorityProjection
  checkpoints?: CheckpointProjection
  planning_boundary?: PlanningBoundaryProjection
  runtime_authority?: RuntimeAuthorityProjection
  mode?: 'standalone' | 'goc'
  plan_source?: 'local' | 'goc' | 'local_fallback'
  context_source?: 'local' | 'goc'
  agent_catalog_source?: 'local' | 'goc'
  conversation_team_source?: 'local' | 'goc'
  skill_catalog_source?: 'local' | 'goc' | 'mixed'
  degraded_mode?: boolean
  fallback_reason?: string | null
  graph_counts?: Record<string, number>
  updated_at?: string | null
}

export type RunStudioAgentTeam = {
  conversation_id?: string | null
  snapshot_node_id?: string | null
  snapshot_node_type?: string | null
  snapshot_source_key?: string | null
  snapshot_source_path?: string | null
  items?: Array<RuntimeAgentWithSkills & {
    membership_id?: string
    agent_id: string
    runtime_instance_id?: string | null
    name?: string | null
    role_label?: string | null
    template_id?: string | null
    provider?: string | null
    enabled?: boolean
    order_index?: number | null
    runtime_status?: string | null
    status_counts?: Record<string, number>
    responsibilities?: string[]
    capability_tags?: string[]
    ephemeral?: boolean
    description?: string | null
    model?: string | null
    visibility?: string | null
    source?: string | null
    source_key?: string | null
    source_path?: string | null
    snapshot_node_id?: string | null
    snapshot_node_type?: string | null
    attached_skills?: AttachedSkillSummary[]
    context_pack_id?: string | null
  }>
  configured_items?: RuntimeAgentInstanceV2[]
  configured_scope_items?: NonNullable<ScopeProjection['items']>
  skill_packages?: SkillPackage[]
  active_count?: number
  updated_at?: string | null
  runtime_authority?: RuntimeAuthorityProjection
  mode?: 'standalone' | 'goc'
  plan_source?: 'local' | 'goc' | 'local_fallback'
  context_source?: 'local' | 'goc'
  agent_catalog_source?: 'local' | 'goc'
  conversation_team_source?: 'local' | 'goc'
  skill_catalog_source?: 'local' | 'goc' | 'mixed'
  degraded_mode?: boolean
  fallback_reason?: string | null
  team_config?: {
    status?: string | null
    composition_mode?: string | null
    proposal_mode?: string | null
    active_team?: Record<string, unknown>
    pending_team?: Record<string, unknown>
  }
}

export type RunStudioContextDecisions = {
  context_set_id?: string | null
  context_set_name?: string | null
  selected?: Array<{
    id: string
    target_node_id?: string
    type?: string | null
    text?: string | null
    pin_level?: string | null
    pinned?: boolean
  }>
  pinned?: Array<{
    id: string
    target_node_id?: string
    type?: string | null
    text?: string | null
    pin_level?: string | null
  }>
  excluded?: Array<{
    id: string
    target_node_id?: string
    type?: string | null
    text?: string | null
    reason?: string | null
    pin_level?: string | null
    pinned?: boolean
    child_ids?: string[]
  }>
  missing?: Array<{
    id?: string
    target_node_id?: string
    type?: string | null
    text?: string | null
    reason?: string | null
    pin_level?: string | null
    pinned?: boolean
  }>
  conflicting?: Array<{
    edge_id?: string
    type?: string | null
    from_id?: string | null
    to_id?: string | null
    from_text?: string | null
    to_text?: string | null
    reason?: string | null
    related_node_ids?: string[]
  }>
  compiled_kept_node_ids?: string[]
  counts?: Record<string, number>
}

export type RunStudioEvidence = {
  items?: Array<{
    claim_node_id: string
    claim_node_type?: string | null
    claim_text?: string | null
    created_at?: string | null
    selected_in_context?: boolean
    evidence_nodes?: Array<{
      id: string
      type?: string | null
      text?: string | null
      edge_type?: string | null
    }>
    provenance?: string[]
    uncertainty?: string[]
    conflict_node_ids?: string[]
    related_node_ids?: string[]
    pinned?: boolean
    pin_level?: string | null
    score?: number
  }>
  counts?: Record<string, number>
  updated_at?: string | null
}

export type RunStudioContextPacks = {
  run_id?: string | null
  count?: number
  items?: ContextPackSummary[]
  updated_at?: string | null
  planning_boundary?: PlanningBoundaryProjection
  runtime_authority?: RuntimeAuthorityProjection
  mode?: 'standalone' | 'goc'
  plan_source?: 'local' | 'goc' | 'local_fallback'
  context_source?: 'local' | 'goc'
  agent_catalog_source?: 'local' | 'goc'
  conversation_team_source?: 'local' | 'goc'
  skill_catalog_source?: 'local' | 'goc' | 'mixed'
  degraded_mode?: boolean
  fallback_reason?: string | null
}

export type RunStudioSkillUsage = {
  run_id?: string | null
  count?: number
  items?: SkillUsageEventSummary[]
  updated_at?: string | null
  planning_boundary?: PlanningBoundaryProjection
  runtime_authority?: RuntimeAuthorityProjection
  mode?: 'standalone' | 'goc'
  plan_source?: 'local' | 'goc' | 'local_fallback'
  context_source?: 'local' | 'goc'
  agent_catalog_source?: 'local' | 'goc'
  conversation_team_source?: 'local' | 'goc'
  skill_catalog_source?: 'local' | 'goc' | 'mixed'
  degraded_mode?: boolean
  fallback_reason?: string | null
}


export type AgentSkillAttachmentProjection = {
  runtime_instance_id?: string | null
  display_label: string
  role_label: string
  slot_label?: string | null
  authority_profile_id?: string | null
  preset_id?: string | null
  synthesized?: boolean
  attached_skills: AttachedSkillSummary[]
  attached_skill_ids: string[]
}

export type SkillAttachmentOverviewProjection = {
  agents: AgentSkillAttachmentProjection[]
  top_skills: Array<{
    skill_id: string
    skill_name: string
    count: number
  }>
  total_agent_skill_links: number
  total_unique_skills: number
  agents_with_skills: number
}

export type ControlPlaneSummaryProjection = {
  mode: string
  planSource: string
  contextSource: string
  teamSource: string
  skillSource: string
  supervisorMode: string | null
  supervisorEnabled: boolean
  runtimeAgentCount: number
  parallelGroupCount: number
  collaborationCount: number
  checkpointCount: number
  presetCount: number
  synthesizedCount: number
  reviewerPresent: boolean
  synthesizerPresent: boolean
  degradedMode: boolean
  fallbackReason: string | null
  legacyFallback: boolean
  scopeMode: string
  scopeCount: number
  legacyContextPackCount: number
  legacyContextPacksEnabled: boolean
  legacyContextStrategy: string | null
}
