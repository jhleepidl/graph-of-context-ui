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

export type ExecutableTeamDefinitionSummary = {
  member_count?: number | null
  participant_count?: number | null
  role_ids?: string[]
  executable_ready?: boolean | null
  executable_readiness?: {
    ready?: boolean | null
    runtime_bound?: boolean | null
    admission_status?: string | null
    decision?: string | null
  } | null
  topology_contract?: {
    pattern?: string | null
    execution_pattern?: string | null
    edge_count?: number | null
    [key: string]: unknown
  } | null
  interaction_topology_contract?: {
    pattern?: string | null
    execution_pattern?: string | null
    edge_count?: number | null
    [key: string]: unknown
  } | null
  memory_contract?: {
    surface_count?: number | null
    writable_surface_count?: number | null
    final_answer_surface_ready?: boolean | null
    acl_count?: number | null
    publish_capable_roles?: string[]
    [key: string]: unknown
  } | null
  memory_governance_policy?: {
    surface_count?: number | null
    shared_surface_count?: number | null
    private_surface_count?: number | null
    acl_count?: number | null
    publish_surface_ids?: string[]
    [key: string]: unknown
  } | null
  capability_contract?: Record<string, unknown> | null
  [key: string]: unknown
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
  runtime_bound?: boolean | null
  admission_status?: string | null
  admission_decision?: string | null
  blocking_reason_codes?: string[]
  degrade_reason_codes?: string[]
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
  executable_definition?: ExecutableTeamDefinitionSummary | null
  memory_acl_summary?: Array<{
    role_id?: string | null
    read_scope_mode?: string | null
    write_scope_mode?: string | null
    publish_scope_mode?: string | null
    read_surface_ids?: string[]
    write_surface_ids?: string[]
    publish_surface_ids?: string[]
    can_publish_final_answer?: boolean | null
    can_publish_artifact_index?: boolean | null
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





export type MemoryImportIntentFeature = {
  import_intent?: string | null
  topic?: string | null
  target_team?: string | null
  projection_profile?: string | null
  mode?: string | null
  scope?: string | null
  previous_result_policy?: string | null
  fork_policy?: string | null
  permissions?: Record<string, unknown> | null
  reason_codes?: string[]
}


export type WorkModeFeature = {
  work_mode?: string | null
  label?: string | null
  agents_hint?: string | null
  context_depth?: string | null
  team_skeleton?: string | null
  loop_budget?: string | number | null
  stop_condition?: string | null
  review_policy?: string | null
  memory_mode?: string | null
  goc_mode?: string | null
  explicit?: boolean | null
  reason_codes?: string[]
}

export type TaskAttemptPlanFeature = {
  task_id?: string | null
  attempt_id?: string | null
  parent_attempt_id?: string | null
  run_mode?: string | null
  retry_reason?: string | null
  reason_codes?: string[]
  target_team?: string | null
  previous_result_policy?: string | null
  context_policy?: Record<string, unknown> | null
  work_mode?: WorkModeFeature | null
  cycle_policy?: Record<string, unknown> | null
  memory_import?: MemoryImportIntentFeature | null
  goc?: Record<string, unknown> | null
}

export type UserOrchestrationIntentFeature = {
  team_intent?: string | null
  team_style?: string | null
  required_roles?: string[]
  min_team_size?: number | null
  debt_policy?: string | null
  reason_codes?: string[]
}

export type SkeletonAdvisoryFeature = {
  status?: string | null
  source?: string | null
  utility_label?: string | null
  debt_label?: string | null
  frontier_needed?: string | null
  capacity_gaps?: string[]
  warnings?: string[]
  confidence?: number | null
  fused_utility?: number | null
  base_utility?: number | null
  learned_delta?: number | null
  advisory_mode?: string | null
  user_intent_match?: boolean | null
  user_intent_bonus?: number | null
  user_requested_overhead_discount?: number | null
  user_team_intent?: string | null
  user_team_style?: string | null
  missing_user_required_roles?: string[]
  task_attempt_match?: boolean | null
  attempt_intent_bonus?: number | null
  run_mode?: string | null
  retry_reason?: string | null
  target_team?: string | null
  previous_result_policy?: string | null
  memory_import_intent?: string | null
  memory_import_profile?: string | null
  work_mode?: string | null
  work_mode_match?: boolean | null
  work_mode_reason?: string | null
  work_mode_bonus?: number | null
  loop_budget?: string | number | null
  stop_condition?: string | null
  review_policy?: string | null
  memory_mode?: string | null
  goc_mode?: string | null
}

export type TeamSelectionCandidateFeature = {
  template_id?: string | null
  title?: string | null
  task_archetype?: string | null
  score?: number | null
  semantic_score?: number | null
  topology_pattern?: string | null
  participant_count?: number | null
  edge_count?: number | null
  surface_count?: number | null
  shared_surface_count?: number | null
  final_answer_surface_ready?: boolean | null
  append_only_surface_count?: number | null
  member_count?: number | null
  role_ids?: string[]
  ready?: boolean | null
  runtime_bound?: boolean | null
  admission_status?: string | null
  blocking_reason_codes?: string[]
  degrade_reason_codes?: string[]
  feature_score_breakdown?: Record<string, number>
  skeleton_advisory?: SkeletonAdvisoryFeature | null
  user_orchestration_intent?: UserOrchestrationIntentFeature | null
  user_intent_satisfaction?: Record<string, unknown> | null
  task_attempt_plan?: TaskAttemptPlanFeature | null
  work_mode?: WorkModeFeature | null
  work_mode_satisfaction?: Record<string, unknown> | null
  task_attempt_satisfaction?: Record<string, unknown> | null
  memory_import_intent?: MemoryImportIntentFeature | null
  target_team?: string | null
  previous_result_policy?: string | null
  rationale?: string[]
}

export type TeamSelectionDatasetRow = {
  event_id?: string | null
  thread_id?: string | null
  run_id?: string | null
  task_text?: string | null
  task_archetype?: string | null
  selected_blueprint_id?: string | null
  selected_candidate_found?: boolean
  selected_candidate_source?: string | null
  selected_candidate_rank?: number | null
  recommendation_alignment?: string | null
  candidate_count?: number
  training_eligible?: boolean
  exclusion_reasons?: string[]
  selected_score?: number | null
  selected_topology_pattern?: string | null
  selected_memory_surface_count?: number | null
  selected_final_answer_surface_ready?: boolean | null
  selected_member_count?: number | null
  selected_role_ids?: string[]
  selected_ready?: boolean | null
  selected_runtime_bound?: boolean | null
  selected_blocking_reason_codes?: string[]
  selected_degrade_reason_codes?: string[]
  candidate_features?: TeamSelectionCandidateFeature[]
  recommended_candidates?: TeamSelectionCandidateFeature[]
  top_recommended_candidate?: TeamSelectionCandidateFeature | null
  recommendation_gap?: number | null
  task_attempt_plan?: TaskAttemptPlanFeature | null
  work_mode?: WorkModeFeature | null
  memory_import_intent?: MemoryImportIntentFeature | null
  input_features?: Record<string, unknown>
  selected_features?: TeamSelectionCandidateFeature | null
  outcome_labels?: {
    success?: boolean
    quality_score?: number | null
    artifact_quality?: number | null
    token_cost?: number | null
    latency_ms?: number | null
    human_override?: boolean
    human_override_reason?: string | null
    recovery_count?: number | null
    approval_friction?: number | null
    memory_fit_failure?: boolean
  } | null
  success?: boolean
  quality_score?: number | null
  artifact_quality?: number | null
  token_cost?: number | null
  latency_ms?: number | null
  human_override?: boolean
  human_override_reason?: string | null
  recovery_count?: number | null
  approval_friction?: number | null
  memory_fit_failure?: boolean
  created_at?: string | null
}

export type TeamSelectionOutcomeSample = {
  event_id?: string | null
  run_id?: string | null
  created_at?: string | null
  selected_blueprint_id?: string | null
  recommendation_alignment?: string | null
  success?: boolean
  artifact_quality?: number | null
  recommendation_gap?: number | null
  training_eligible?: boolean
  exclusion_reasons?: string[]
}

export type TeamSelectionDataset = {
  kind?: string | null
  schema_version?: number | null
  count?: number
  eligible_count?: number
  excluded_count?: number
  archetype_counts?: Record<string, number>
  success_counts?: Record<string, number>
  exclusion_reason_counts?: Record<string, number>
  selection_outcome_summary?: {
    alignment_counts?: Record<string, number>
    success_rate_by_alignment?: Record<string, number>
    average_artifact_quality_by_alignment?: Record<string, number>
    average_recommendation_gap_by_alignment?: Record<string, number | null>
    human_override_count?: number
    memory_fit_failure_count?: number
    advisory_status_counts?: Record<string, number>
    advisory_debt_counts?: Record<string, number>
    advisory_capacity_gap_counts?: Record<string, number>
    attempt_run_mode_counts?: Record<string, number>
    memory_import_profile_counts?: Record<string, number>
    work_mode_counts?: Record<string, number>
    work_mode_review_policy_counts?: Record<string, number>
    alignment_event_samples?: Record<string, TeamSelectionOutcomeSample[]>
  } | null
  rows?: TeamSelectionDatasetRow[]
}

export type TaskAttemptRecord = {
  id?: string | null
  thread_id?: string | null
  task_id?: string | null
  attempt_id?: string | null
  parent_attempt_id?: string | null
  run_id?: string | null
  run_mode?: string | null
  status?: string | null
  target_team?: string | null
  previous_result_policy?: string | null
  work_mode?: string | null
  review_policy?: string | null
  memory_projection_profile?: string | null
  memory_package_id?: string | null
  task_text?: string | null
  context_policy?: Record<string, unknown> | null
  memory_package?: Record<string, unknown> | null
  candidate_snapshot?: Record<string, unknown> | null
  result?: Record<string, unknown> | null
  lineage?: Record<string, unknown> | null
  launch?: Record<string, unknown> | null
  meta?: Record<string, unknown> | null
  events?: Array<Record<string, unknown>>
  promoted_at?: string | null
  archived_at?: string | null
  launched_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type MemoryLifecycleEvent = {
  id?: string | null
  thread_id?: string | null
  node_id?: string | null
  surface_id?: string | null
  event_type?: string | null
  event_title?: string | null
  from_status?: string | null
  to_status?: string | null
  actor?: string | null
  source?: string | null
  summary?: string | null
  metadata?: Record<string, unknown> | null
  created_run_id?: string | null
  created_at?: string | null
  related_edge_ids?: string[]
  related_conflict_ids?: string[]
  supporting_memory_node_ids?: string[]
  supporting_claim_node_ids?: string[]
  supporting_evidence_node_ids?: string[]
}

export type MemoryNodeDrilldown = {
  node_id?: string | null
  surface_id?: string | null
  node_type?: string | null
  status?: string | null
  trust_tier?: string | null
  confidence?: number | null
  owner_agent_id?: string | null
  owner_role_id?: string | null
  created_run_id?: string | null
  content_preview?: string | null
  provenance_fingerprint?: string | null
  visibility_reason?: string | null
  blocked_reason?: string | null
  lifecycle_event_count?: number
  latest_lifecycle_event?: MemoryLifecycleEvent | null
  lifecycle_status_path?: string[]
}

export type MemoryProjectionDetail = {
  projection_id?: string | null
  run_id?: string | null
  agent_id?: string | null
  role_id?: string | null
  summary?: {
    role_id?: string | null
    agent_id?: string | null
    visible_surface_count?: number
    blocked_surface_count?: number
    visible_node_count?: number
    blocked_node_count?: number
    visible_surface_ids?: string[]
    blocked_surface_ids?: string[]
    surface_reason_map?: Record<string, string>
    node_reason_map?: Record<string, string>
  } | null
  visible_surface_ids?: string[]
  blocked_surface_ids?: string[]
  visible_node_ids?: string[]
  blocked_node_ids?: string[]
  visible_nodes?: MemoryNodeDrilldown[]
  blocked_nodes?: MemoryNodeDrilldown[]
  created_at?: string | null
}

export type ConflictHistoryEvent = {
  event_type?: string | null
  status?: string | null
  previous_status?: string | null
  actor?: string | null
  source?: string | null
  created_at?: string | null
  summary?: string | null
  merge_note?: string | null
  winning_node_id?: string | null
  losing_node_ids?: string[]
  rationale_codes?: string[]
  supporting_claim_node_ids?: string[]
  supporting_evidence_node_ids?: string[]
  supporting_memory_node_ids?: string[]
  history?: ConflictHistoryEvent[]
  history_count?: number
  latest_history_event?: ConflictHistoryEvent | null
  merge_history?: ConflictHistoryEvent[]
  merge_history_count?: number
  latest_merge_event?: ConflictHistoryEvent | null
}

export type MemoryEdgeDetail = {
  id?: string | null
  edge_type?: string | null
  edge_type_title?: string | null
  from_node_id?: string | null
  to_node_id?: string | null
  from_surface_id?: string | null
  to_surface_id?: string | null
  status?: string | null
  rationale?: string | null
  created_run_id?: string | null
  created_at?: string | null
  updated_at?: string | null
  from_node_type?: string | null
  to_node_type?: string | null
  from_node_preview?: string | null
  to_node_preview?: string | null
  from_owner_role_id?: string | null
  to_owner_role_id?: string | null
  provenance_fingerprint?: string | null
  evidence_node_ids?: string[]
  supporting_claim_node_ids?: string[]
  supporting_memory_node_ids?: string[]
}

export type MemoryConflictDetail = {
  id?: string | null
  surface_id?: string | null
  created_at?: string | null
  updated_at?: string | null
  left_node_id?: string | null
  right_node_id?: string | null
  status?: string | null
  reason?: string | null
  conflict_key?: string | null
  left_trust_tier?: string | null
  right_trust_tier?: string | null
  left_confidence?: number | null
  right_confidence?: number | null
  left_provenance_fingerprint?: string | null
  right_provenance_fingerprint?: string | null
  resolution_status?: string | null
  winning_node_id?: string | null
  losing_node_ids?: string[]
  resolution_summary?: string | null
  resolution_rationale_codes?: string[]
  supporting_claim_node_ids?: string[]
  supporting_evidence_node_ids?: string[]
  supporting_memory_node_ids?: string[]
  history?: ConflictHistoryEvent[]
  history_count?: number
  latest_history_event?: ConflictHistoryEvent | null
  merge_history?: ConflictHistoryEvent[]
  merge_history_count?: number
  latest_merge_event?: ConflictHistoryEvent | null
}


export type MemoryBrowserNode = {
  id?: string | null
  surface_id?: string | null
  node_type?: string | null
  status?: string | null
  owner_agent_id?: string | null
  owner_role_id?: string | null
  trust_tier?: string | null
  created_run_id?: string | null
  created_at?: string | null
  updated_at?: string | null
  preview?: string | null
  content?: Record<string, unknown> | null
  provenance?: Record<string, unknown> | null
  confidence?: number | null
}

export type MemoryBrowserSurface = {
  surface_id?: string | null
  title?: string | null
  semantic_kind?: string | null
  visibility_scope?: string | null
  write_mode?: string | null
  policy?: Record<string, unknown> | null
  node_count?: number
  status_counts?: Record<string, number>
  node_type_counts?: Record<string, number>
  owner_role_counts?: Record<string, number>
  nodes?: MemoryBrowserNode[]
}

export type MemoryBrowser = {
  schema_version?: string | null
  thread_id?: string | null
  filters?: Record<string, unknown> | null
  summary?: {
    surface_count?: number
    node_count?: number
    status_counts?: Record<string, number>
    node_type_counts?: Record<string, number>
    owner_role_counts?: Record<string, number>
    trust_tier_counts?: Record<string, number>
  } | null
  surfaces?: MemoryBrowserSurface[]
}

export type RunStudioMemoryGraph = {
  projections?: MemoryProjectionDetail[]
  projection_count?: number
  edges?: MemoryEdgeDetail[]
  edge_count?: number
  edge_type_counts?: Record<string, number>
  lifecycle_events?: MemoryLifecycleEvent[]
  lifecycle_event_count?: number
  lifecycle_event_type_counts?: Record<string, number>
  conflicts?: MemoryConflictDetail[]
  browser?: MemoryBrowser | null
  conflict_count?: number
  conflict_status_counts?: Record<string, number>
  conflict_reason_counts?: Record<string, number>
}


export type MemoryTopologySurface = {
  id?: string | null
  surface_id?: string | null
  title?: string | null
  kind?: string | null
  semantic_kind?: string | null
  visibility_scope?: string | null
  write_mode?: string | null
  readers?: string[]
  writers?: string[]
  steward?: string[]
  path?: string | null
  lens?: string | null
  promotion_policy?: string | null
  [key: string]: unknown
}

export type MemoryTopologyGrant = {
  agent_id?: string | null
  role?: string | null
  provider?: string | null
  read?: string[]
  write?: string[]
  lens?: string | null
  write_mode?: string | null
  [key: string]: unknown
}

export type MemoryTopologyMaintenanceAction = {
  action?: string | null
  target?: string | null
  reason?: string | null
  candidate_only?: boolean
  destructive?: boolean
  [key: string]: unknown
}

export type RunStudioMemoryTopology = {
  schema_version?: string | null
  source?: string | null
  snapshot_id?: string | null
  run_id?: string | null
  mode?: string | null
  state?: string | null
  stress?: { score?: number; reasons?: string[]; components?: Record<string, number>; [key: string]: unknown } | null
  stress_score?: number | null
  selection_reason?: string[]
  stats?: Record<string, unknown>
  surfaces?: MemoryTopologySurface[]
  surface_count?: number
  surface_kind_counts?: Record<string, number>
  agent_grants?: Record<string, MemoryTopologyGrant>
  agent_grant_count?: number
  maintenance?: {
    generated_at?: string | null
    idle_safe?: boolean
    destructive_changes?: boolean
    actions?: MemoryTopologyMaintenanceAction[]
    [key: string]: unknown
  } | null
  maintenance_action_count?: number
  idle_safe?: boolean
  destructive_changes?: boolean
  events?: Array<Record<string, unknown>>
  event_count?: number
  created_at?: string | null
  updated_at?: string | null
  fallback?: boolean
}


export type MemoryDemandEvent = {
  id?: string | null
  run_id?: string | null
  query?: string | null
  reason?: string | null
  demand_reasons?: string[]
  sources?: string[]
  item_count?: number
  agent_id?: string | null
  role_id?: string | null
  retrieval_mode?: string | null
  classifier?: string | null
  confidence?: number | null
  source_types?: string[]
  surface_ids?: string[]
  router_memory_plan?: Record<string, unknown> | null
  source?: string | null
  matching?: Record<string, unknown> | null
  created_at?: string | null
  event?: Record<string, unknown>
}

export type RunStudioMemoryDemand = {
  schema_version?: string | null
  thread_id?: string | null
  run_id?: string | null
  event_count?: number
  events?: MemoryDemandEvent[]
  reason_counts?: Record<string, number>
  source_counts?: Record<string, number>
  retrieval_mode_counts?: Record<string, number>
  classifier_counts?: Record<string, number>
  source_type_counts?: Record<string, number>
  surface_counts?: Record<string, number>
  agent_counts?: Record<string, number>
  latest_query?: string | null
  latest_at?: string | null
  preflight_semantics?: {
    goal?: string | null
    runtime_contract?: string | null
    matching_note?: string | null
    [key: string]: unknown
  } | null
  empty?: boolean
}

export type RunStudioTraceScope = {
  run_id?: string | null
  scope?: string | null
  node_ids?: string[]
  edge_ids?: string[]
  node_count?: number
  edge_count?: number
  run_node_id?: string | null
  anchor_node_id?: string | null
  step_node_ids?: string[]
  step_count?: number
  evidence_node_ids?: string[]
  evidence_node_count?: number
  memory_node_ids?: string[]
  memory_node_count?: number
}


export type RunStudioCrossReferences = {
  run_id?: string | null
  scope?: string | null
  anchor_node_id?: string | null
  claim_links?: Array<{
    claim_node_id: string
    claim_node_type?: string | null
    claim_text?: string | null
    related_memory_node_ids?: string[]
    related_memory_edge_ids?: string[]
    related_conflict_ids?: string[]
    related_evidence_node_ids?: string[]
    related_lifecycle_event_ids?: string[]
    compare_node_ids?: string[]
    trace_anchor_related?: boolean
    selected_in_context?: boolean
    pinned?: boolean
    score?: number
  }>
  memory_links?: Array<{
    memory_node_id: string
    surface_id?: string | null
    node_type?: string | null
    status?: string | null
    owner_role_id?: string | null
    projection_role_ids?: string[]
    visible_projection_count?: number
    blocked_projection_count?: number
    related_claim_node_ids?: string[]
    related_conflict_ids?: string[]
    related_edge_ids?: string[]
    related_lifecycle_event_ids?: string[]
    trace_anchor_related?: boolean
  }>
  edge_links?: Array<{
    edge_id: string
    edge_type?: string | null
    edge_type_title?: string | null
    from_node_id?: string | null
    to_node_id?: string | null
    from_surface_id?: string | null
    to_surface_id?: string | null
    status?: string | null
    rationale?: string | null
    created_run_id?: string | null
    created_at?: string | null
    updated_at?: string | null
    from_node_type?: string | null
    to_node_type?: string | null
    from_node_preview?: string | null
    to_node_preview?: string | null
    from_owner_role_id?: string | null
    to_owner_role_id?: string | null
    provenance_fingerprint?: string | null
    evidence_node_ids?: string[]
    supporting_claim_node_ids?: string[]
    supporting_memory_node_ids?: string[]
    related_memory_node_ids?: string[]
    related_claim_node_ids?: string[]
    related_conflict_ids?: string[]
    related_lifecycle_event_ids?: string[]
    trace_anchor_related?: boolean
  }>
  conflict_links?: Array<{
    conflict_id: string
    surface_id?: string | null
    status?: string | null
    reason?: string | null
    node_ids?: string[]
    winning_node_id?: string | null
    losing_node_ids?: string[]
    resolution_summary?: string | null
    resolution_rationale_codes?: string[]
    supporting_claim_node_ids?: string[]
    supporting_evidence_node_ids?: string[]
    supporting_memory_node_ids?: string[]
    history?: ConflictHistoryEvent[]
    history_count?: number
    latest_history_event?: ConflictHistoryEvent | null
    merge_history?: ConflictHistoryEvent[]
    merge_history_count?: number
    latest_merge_event?: ConflictHistoryEvent | null
    suggested_resolution?: {
      winning_node_id?: string | null
      losing_node_ids?: string[]
      summary?: string | null
      rationale_codes?: string[]
      supporting_claim_node_ids?: string[]
      supporting_evidence_node_ids?: string[]
      supporting_memory_node_ids?: string[]
      top_claim_node_id?: string | null
      top_claim_text?: string | null
    } | null
    related_claim_node_ids?: string[]
    related_memory_node_ids?: string[]
    related_edge_ids?: string[]
    related_lifecycle_event_ids?: string[]
    trace_anchor_related?: boolean
  }>
  lifecycle_links?: Array<{
    event_id: string
    event_type?: string | null
    event_title?: string | null
    node_id?: string | null
    surface_id?: string | null
    from_status?: string | null
    to_status?: string | null
    actor?: string | null
    source?: string | null
    summary?: string | null
    created_run_id?: string | null
    created_at?: string | null
    supporting_memory_node_ids?: string[]
    supporting_claim_node_ids?: string[]
    supporting_evidence_node_ids?: string[]
    related_claim_node_ids?: string[]
    related_evidence_node_ids?: string[]
    related_conflict_ids?: string[]
    related_edge_ids?: string[]
    trace_anchor_related?: boolean
  }>
  counts?: Record<string, number>
  anchor_related?: {
    claim_node_ids?: string[]
    memory_node_ids?: string[]
    edge_ids?: string[]
    conflict_ids?: string[]
    lifecycle_event_ids?: string[]
  } | null
}

export type RunStudioAuditTimelineEvent = {
  event_id: string
  timestamp?: string | null
  category?: string | null
  title?: string | null
  summary?: string | null
  status?: string | null
  run_id?: string | null
  selection_event_id?: string | null
  projection_id?: string | null
  conflict_id?: string | null
  claim_node_id?: string | null
  memory_node_id?: string | null
  primary_node_id?: string | null
  related_node_ids?: string[]
  trace_node_ids?: string[]
  trace_anchor_related?: boolean
  rationale_codes?: string[]
  badges?: string[]
  metadata?: Record<string, unknown> | null
}

export type RunStudioAuditTimeline = {
  run_id?: string | null
  scope?: string | null
  selection_event_id?: string | null
  anchor_node_id?: string | null
  started_at?: string | null
  ended_at?: string | null
  count?: number
  category_counts?: Record<string, number>
  status_counts?: Record<string, number>
  linked_summary?: {
    team_synthesis_mode?: string | null
    execution_mode?: string | null
    execution_mode_reasons?: string[]
    execution_mode_signals?: Record<string, unknown> | null
    execution_quality_signals?: Record<string, unknown> | null
    execution_mode_history_tail?: Array<Record<string, unknown>>
    task_type?: string | null
    deliverable_type?: string | null
    task_family_key?: string | null
    task_family_mode_hint?: Record<string, unknown> | null
    selected_motif_ids?: string[]
    motif_feedback_run_count?: number | null
    motif_channel?: string | null
    participant_signal_count?: number | null
    participant_digest_count?: number | null
    participant_kind_counts?: Record<string, number>
    participant_labels?: string[]
    channel_verifier_count?: number | null
    channel_promotion_count?: number | null
    latest_overall_recommendation?: string | null
    motif_compare?: Record<string, unknown> | null
    participant_policy_compare?: Record<string, unknown> | null
    promoted_motif_ids?: string[]
    rolled_back_motif_ids?: string[]
    participant_policy_snapshot?: Record<string, unknown> | null
  } | null
  items?: RunStudioAuditTimelineEvent[]
}

export type RunStudioProjectionRetrievalItem = {
  runtime_instance_id?: string | null
  role_id?: string | null
  display_label?: string | null
  scope_id?: string | null
  visibility_mode?: string | null
  grant_labels?: string[]
  active_node_count?: number
  authoritative_scope?: boolean
  empty_scope?: boolean
  scope_context_set_id?: string | null
  selection_summary?: string | null
  selection_confidence?: string | null
  projection_id?: string | null
  projection_created_at?: string | null
  visible_node_count?: number
  blocked_node_count?: number
  visible_surface_ids?: string[]
  blocked_surface_ids?: string[]
  status?: string | null
  projection_authoritative?: boolean
  traceable_in_memory_graph?: boolean
  context_source?: string | null
  degraded_mode?: boolean
  fallback_reason?: string | null
}

export type RunStudioProjectionRetrieval = {
  run_id?: string | null
  scope?: string | null
  summary?: {
    status?: string | null
    projection_authoritative?: boolean
    scope_first_ready?: boolean
    context_runtime_mode?: string | null
    context_source?: string | null
    degraded_mode?: boolean
    fallback_reason?: string | null
    coverage_note?: string | null
    scope_projection_note?: string | null
    visibility_relation_count?: number
  } | null
  counts?: Record<string, number>
  items?: RunStudioProjectionRetrievalItem[]
  planner_system_paths?: RunStudioProjectionRetrievalItem[]
  visibility_relation_counts?: Record<string, number>
  runtime_authority?: RuntimeAuthorityProjection
}


export type RunStudioGraphCompressionCluster = {
  cluster_id: string
  cluster_type?: string | null
  label?: string | null
  headline?: string | null
  status?: string | null
  claim_node_ids?: string[]
  evidence_node_ids?: string[]
  memory_node_ids?: string[]
  edge_ids?: string[]
  lifecycle_event_ids?: string[]
  conflict_ids?: string[]
  role_ids?: string[]
  surface_ids?: string[]
  representative_claim_node_ids?: string[]
  representative_evidence_node_ids?: string[]
  representative_memory_node_ids?: string[]
  representative_edge_ids?: string[]
  representative_lifecycle_event_ids?: string[]
  support_frontier_node_ids?: string[]
  conflict_frontier_ids?: string[]
  decision_path_event_ids?: string[]
  omitted_memory_node_ids?: string[]
  rendered_summary?: string | null
  reexpand_handles?: {
    claim_node_ids?: string[]
    evidence_node_ids?: string[]
    memory_node_ids?: string[]
    edge_ids?: string[]
    lifecycle_event_ids?: string[]
    conflict_ids?: string[]
    trace_anchor_related?: boolean
  } | null
}

export type RunStudioGraphCompressionRoleView = {
  role_id?: string | null
  display_label?: string | null
  projection_id?: string | null
  status?: string | null
  visible_cluster_ids?: string[]
  blocked_cluster_ids?: string[]
  core_claim_node_ids?: string[]
  support_frontier_node_ids?: string[]
  conflict_frontier_ids?: string[]
  decision_path_event_ids?: string[]
  rendered_context?: string | null
  reexpand_handles?: {
    memory_node_ids?: string[]
    cluster_ids?: string[]
  } | null
}

export type RunStudioHarnessSummary = {
  schema_version?: string | null
  spec_hash?: string | null
  name?: string | null
  description?: string | null
  tags?: string[]
  visibility?: string | null
  shareable?: boolean
  exportable?: boolean
  compression_enabled?: boolean
  role_delivery?: Record<string, string>
  resolved_role_delivery?: Record<string, {
    requested_role_id?: string | null
    effective_role_id?: string | null
    delivery_mode?: string | null
    appendix_enabled?: boolean
    appendix_char_budget_ratio?: number
    budget_tier?: string | null
    risk_level?: string | null
  }>
  delivery_policy?: {
    default_delivery_mode?: string | null
    appendix_char_budget_ratio?: number
    default_budget_tier?: string | null
    default_risk_level?: string | null
    projection_appendix_enabled_by_default?: boolean
    normalize_orchestration_roles_to_operator?: boolean
  } | null
  audit_flags?: Record<string, boolean>
  updated_at?: string | null
}

export type RunStudioHarnessSpec = {
  schema_version?: string | null
  metadata?: Record<string, unknown> | null
  projection_policy?: Record<string, unknown> | null
  compression_policy?: Record<string, unknown> | null
  tool_policy?: Record<string, unknown> | null
  approval_policy?: Record<string, unknown> | null
  audit_policy?: Record<string, unknown> | null
  sharing?: Record<string, unknown> | null
}

export type RunStudioGraphCompression = {
  run_id?: string | null
  scope?: string | null
  anchor_node_id?: string | null
  summary?: {
    compression_mode?: string | null
    cluster_count?: number
    role_view_count?: number
    core_claim_count?: number
    support_frontier_count?: number
    conflict_frontier_count?: number
    decision_path_count?: number
    omitted_cluster_count?: number
    unresolved_conflict_count?: number
    compression_note?: string | null
  } | null
  counts?: Record<string, number>
  clusters?: RunStudioGraphCompressionCluster[]
  role_views?: RunStudioGraphCompressionRoleView[]
  omitted_clusters?: Array<{
    cluster_id?: string | null
    cluster_type?: string | null
    reason?: string | null
    memory_node_count?: number
  }>
}

export type RunStudioRunBundle = {
  run_id?: string | null
  scope?: string | null
  context_set_id?: string | null
  evidence?: RunStudioEvidence | null
  context_packs?: RunStudioContextPacks | null
  skill_usage?: RunStudioSkillUsage | null
  memory_graph?: RunStudioMemoryGraph | null
  memory_topology?: RunStudioMemoryTopology | null
  memory_demand?: RunStudioMemoryDemand | null
  trace_scope?: RunStudioTraceScope | null
  cross_references?: RunStudioCrossReferences | null
  projection_retrieval?: RunStudioProjectionRetrieval | null
  audit_timeline?: RunStudioAuditTimeline | null
  graph_native_compression?: RunStudioGraphCompression | null
  harness_spec?: RunStudioHarnessSpec | null
  harness_summary?: RunStudioHarnessSummary | null
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
  run_id?: string | null
  scope?: string | null
  active_context_count?: number
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
