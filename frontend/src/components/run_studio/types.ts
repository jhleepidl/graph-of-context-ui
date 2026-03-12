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

export type RuntimeAgentWithSkills = {
  runtime_instance_id?: string | null
  role_label?: string | null
  template_id?: string | null
  provider?: string | null
  model?: string | null
  runtime_status?: string | null
  attached_skills?: AttachedSkillSummary[]
  context_pack_id?: string | null
  source?: string | null
  source_key?: string | null
  source_path?: string | null
  agent_id?: string | null
  name?: string | null
  enabled?: boolean
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
    runtime_agents?: RuntimeAgentWithSkills[]
    skill_packages?: SkillPackage[]
    context_packs?: ContextPackSummary[]
    skill_usage?: SkillUsageEventSummary[]
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
  items?: Array<{
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
