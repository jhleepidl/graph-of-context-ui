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
    pending_approval?: boolean
    pending_approval_count?: number
    active_context_count?: number
    step_status_counts?: Record<string, number>
  }
  pending_approval_items?: Array<{
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
      selected_count?: number
      pinned_count?: number
      conflict_count?: number
      support_count?: number
      reference_count?: number
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
  graph_counts?: Record<string, number>
  updated_at?: string | null
}

export type RunStudioAgentTeam = {
  conversation_id?: string | null
  items?: Array<{
    membership_id?: string
    agent_id: string
    name?: string | null
    enabled?: boolean
    order_index?: number | null
    runtime_status?: string | null
    status_counts?: Record<string, number>
    responsibilities?: string[]
    description?: string | null
    model?: string | null
    visibility?: string | null
    source?: string | null
  }>
  active_count?: number
  updated_at?: string | null
}

export type RunStudioContextDecisions = {
  context_set_id?: string | null
  context_set_name?: string | null
  selected?: Array<{
    id: string
    type?: string | null
    text?: string | null
    pin_level?: string | null
    pinned?: boolean
  }>
  pinned?: Array<{
    id: string
    type?: string | null
    text?: string | null
    pin_level?: string | null
  }>
  excluded?: Array<{
    id: string
    type?: string | null
    text?: string | null
    reason?: string | null
    child_ids?: string[]
  }>
  missing?: Array<{
    id?: string
    type?: string | null
    text?: string | null
    reason?: string | null
  }>
  conflicting?: Array<{
    edge_id?: string
    type?: string | null
    from_id?: string | null
    to_id?: string | null
    from_text?: string | null
    to_text?: string | null
    reason?: string | null
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
  }>
  counts?: Record<string, number>
  updated_at?: string | null
}
