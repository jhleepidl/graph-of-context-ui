import {
  type AttachedSkillSummary,
  type AuthorityProjection,
  type CheckpointProjection,
  type CollaborationProjection,
  type ExecutionCheckpoint,
  type OrchestrationProjection,
  type RunStudioAgentTeam,
  type RunStudioContextPacks,
  type RunStudioSkillUsage,
  type RunStudioSummary,
  type RuntimeAgentInstanceV2,
  type RuntimeAgentWithSkills,
  type ScopeProjection,
  type StructuredRuntimeValue,
  type TeamViewProjection,
  type WhyThisTeamProjection,
  type ControlPlaneSummaryProjection,
  type SkillAttachmentOverviewProjection,
  type AgentSkillAttachmentProjection,
} from './types'

function cleanText(value: unknown): string | null {
  if (typeof value !== 'string') {
    return value == null ? null : String(value).trim() || null
  }
  const clean = value.trim()
  return clean || null
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => cleanText(item))
    .filter((item): item is string => Boolean(item))
}

function uniqueStrings(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  values.forEach((value) => {
    const clean = cleanText(value)
    if (!clean || seen.has(clean)) return
    seen.add(clean)
    out.push(clean)
  })
  return out
}

function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : fallback
  }
  return fallback
}

function asBoolean(value: unknown): boolean {
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return value !== 0
  if (typeof value === 'string') {
    const clean = value.trim().toLowerCase()
    if (['1', 'true', 'yes', 'y', 'on'].includes(clean)) return true
    if (['0', 'false', 'no', 'n', 'off'].includes(clean)) return false
  }
  return false
}

function parseJsonish(value: unknown): unknown {
  if (typeof value !== 'string') return value
  const clean = value.trim()
  if (!clean) return null
  if (!clean.startsWith('{') && !clean.startsWith('[')) return value
  try {
    return JSON.parse(clean)
  } catch {
    return value
  }
}

function normalizeStructuredValue(value: unknown): StructuredRuntimeValue | null {
  const parsed = parseJsonish(value)
  if (parsed == null) return null
  if (typeof parsed === 'string') return cleanText(parsed)
  if (typeof parsed === 'number' || typeof parsed === 'boolean') return parsed
  if (Array.isArray(parsed)) return parsed
  if (typeof parsed === 'object') return { ...(parsed as Record<string, unknown>) }
  return null
}

function scalarSummary(value: unknown): string | null {
  if (typeof value === 'string') return cleanText(value)
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : null
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return null
}

function structuredSummary(value: unknown): string | null {
  const normalized = normalizeStructuredValue(value)
  const scalar = scalarSummary(normalized)
  if (scalar != null) return scalar

  if (Array.isArray(normalized)) {
    const parts = normalized
      .slice(0, 3)
      .map((item) => structuredSummary(item))
      .filter((item): item is string => Boolean(item))
    if (parts.length > 0) return `${parts.join(', ')}${normalized.length > 3 ? '...' : ''}`
    return normalized.length > 0 ? `${normalized.length} items` : null
  }

  if (normalized && typeof normalized === 'object') {
    const mapping = normalized as Record<string, unknown>
    for (const key of ['summary', 'label', 'name', 'title', 'description', 'message']) {
      const summary = scalarSummary(mapping[key])
      if (summary) return summary
    }

    const parts: string[] = []
    for (const key of ['condition', 'decision', 'signal', 'mode', 'status', 'type', 'kind', 'rule', 'event', 'action']) {
      if (!(key in mapping)) continue
      const summary = structuredSummary(mapping[key])
      if (summary) parts.push(`${key}: ${summary}`)
      if (parts.length >= 3) break
    }
    if (parts.length > 0) return parts.join(' | ')

    for (const [key, raw] of Object.entries(mapping)) {
      const summary = scalarSummary(raw) || structuredSummary(raw)
      if (summary) parts.push(`${key}: ${summary}`)
      if (parts.length >= 3) break
    }
    return parts.length > 0 ? parts.join(' | ') : null
  }

  return null
}

function skillLoadRank(loadLevel?: string | null): number {
  const clean = String(loadLevel || '').trim().toLowerCase()
  if (clean === 'resources') return 3
  if (clean === 'instructions') return 2
  if (clean === 'metadata_only') return 1
  return 0
}

function mergeAttachedSkills(primary?: AttachedSkillSummary[], secondary?: AttachedSkillSummary[]): AttachedSkillSummary[] {
  const merged = new Map<string, AttachedSkillSummary>()

  ;[...(primary || []), ...(secondary || [])].forEach((skill) => {
    const skillId = cleanText(skill?.skill_id)
    if (!skillId) return
    const current = merged.get(skillId)
    if (!current) {
      merged.set(skillId, { ...skill, skill_id: skillId })
      return
    }
    const next: AttachedSkillSummary = { ...current }
    if (skillLoadRank(skill.load_level) >= skillLoadRank(current.load_level)) {
      next.load_level = skill.load_level || current.load_level
    }
    next.skill_name = cleanText(skill.skill_name) || cleanText(current.skill_name) || current.skill_name
    next.selected_by = cleanText(skill.selected_by) || cleanText(current.selected_by) || current.selected_by
    next.selection_reason = cleanText(skill.selection_reason) || cleanText(current.selection_reason) || current.selection_reason
    next.status = cleanText(skill.status) || cleanText(current.status) || current.status
    next.role_count = Math.max(asNumber(current.role_count), asNumber(skill.role_count), 0) || undefined
    merged.set(skillId, next)
  })

  return Array.from(merged.values()).sort((a, b) => {
    const aName = String(a.skill_name || a.skill_id || '').toLowerCase()
    const bName = String(b.skill_name || b.skill_id || '').toLowerCase()
    return aName.localeCompare(bName)
  })
}

function genericRuntimeLabel(label?: string | null, roleId?: string | null): boolean {
  const cleanLabel = cleanText(label).toLowerCase()
  const cleanRole = cleanText(roleId).toLowerCase()
  if (!cleanLabel) return true
  if (cleanRole && (cleanLabel === cleanRole || cleanLabel === titleCaseIdentifier(cleanRole).toLowerCase())) return true
  return false
}

function titleCaseIdentifier(value?: string | null): string {
  return cleanText(value)
    .replace(/[._-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/\b\w/g, (match) => match.toUpperCase())
}

function friendlyRuntimeLabel(agent: Partial<RuntimeAgentInstanceV2>): string {
  const roleId = cleanText(agent.role_id || agent.role_label).toLowerCase()
  const current = cleanText(agent.display_label || agent.name || agent.role_label || agent.agent_id)
  const slotText = [agent.slot_label, agent.selection_reason].map((value) => cleanText(value).toLowerCase()).filter(Boolean).join(' ')
  if (current && !genericRuntimeLabel(current, roleId)) return current
  const hasAny = (...patterns: string[]) => patterns.some((pattern) => slotText.includes(pattern))
  if (roleId === 'researcher') {
    if (hasAny('filing', 'dart', '10-k', '10q', '공시')) return hasAny('investment', 'market', 'equity', 'stock') ? 'DART Financial Researcher' : 'Filing Researcher'
    if (hasAny('news', 'headline', 'market')) return 'Market News Researcher'
    if (hasAny('evidence', 'citation', 'claim', 'validate')) return 'Evidence Researcher'
    if (hasAny('investment', 'equity', 'stock', 'portfolio')) return 'Investment Researcher'
    return current || 'Task Researcher'
  }
  if (roleId === 'reviewer') {
    if (hasAny('skeptical', 'adversarial', 'stress-test', 'stress test', 'claim', 'citation', 'evidence')) return 'Skeptical Claim Reviewer'
    if (hasAny('regression', 'test', 'qa')) return 'Regression Reviewer'
    if (hasAny('risk', 'contradiction')) return 'Risk Reviewer'
    if (hasAny('implementation', 'code', 'patch', 'refactor')) return 'Implementation Reviewer'
    return current || 'Reviewer'
  }
  if (roleId === 'builder') {
    if (hasAny('notebook')) return 'Notebook Builder'
    if (hasAny('patch', 'refactor')) return 'Patch Builder'
    return 'Implementation Builder'
  }
  if (roleId === 'synthesizer') {
    if (hasAny('investment', 'memo')) return 'Investment Memo Synthesizer'
    if (hasAny('brief')) return 'Briefing Synthesizer'
    if (hasAny('report', 'final output', 'assemble', 'aggregation')) return 'Report Synthesizer'
    return current || 'Synthesizer'
  }
  if (roleId === 'operator') {
    return hasAny('workflow', 'runtime', 'tool') ? 'Workflow Operator' : (current || 'Operator')
  }
  return current || titleCaseIdentifier(roleId) || 'runtime agent'
}

function runtimeAgentKey(agent: Partial<RuntimeAgentInstanceV2>): string {
  return (
    cleanText(agent.runtime_instance_id) ||
    cleanText(agent.instance_id) ||
    cleanText(agent.slot_id) ||
    cleanText(agent.agent_id) ||
    [cleanText(agent.display_label), cleanText(agent.role_label)].filter(Boolean).join(':') ||
    'runtime-agent'
  )
}

function normalizeRuntimeAgent(agent: Partial<RuntimeAgentInstanceV2>): RuntimeAgentInstanceV2 {
  const attachedSkills = mergeAttachedSkills(agent.attached_skills)
  const attachedSkillIds = uniqueStrings([
    ...(agent.attached_skill_ids || []),
    ...attachedSkills.map((skill) => skill.skill_id),
  ])

  return {
    ...agent,
    runtime_instance_id: cleanText(agent.runtime_instance_id || agent.instance_id),
    instance_id: cleanText(agent.instance_id || agent.runtime_instance_id),
    agent_id: cleanText(agent.agent_id),
    display_label: friendlyRuntimeLabel(agent),
    name: cleanText(agent.name || friendlyRuntimeLabel(agent)),
    role_label: cleanText(agent.role_label),
    role_id: cleanText(agent.role_id),
    slot_id: cleanText(agent.slot_id),
    slot_label: cleanText(agent.slot_label),
    preset_id: cleanText(agent.preset_id),
    synthesized: asBoolean(agent.synthesized),
    selection_reason: cleanText(agent.selection_reason),
    template_id: cleanText(agent.template_id),
    provider: cleanText(agent.provider),
    model: cleanText(agent.model),
    runtime_status: cleanText(agent.runtime_status) || 'idle',
    context_pack_id: cleanText(agent.context_pack_id),
    source: cleanText(agent.source),
    source_key: cleanText(agent.source_key),
    source_path: cleanText(agent.source_path),
    authority_profile_id: cleanText(agent.authority_profile_id),
    attached_skills: attachedSkills,
    attached_skill_ids: attachedSkillIds,
    enabled: agent.enabled ?? true,
    configured_only: asBoolean((agent as RuntimeAgentWithSkills).configured_only),
    config_state: cleanText((agent as RuntimeAgentWithSkills).config_state),
    team_name: cleanText((agent as RuntimeAgentWithSkills).team_name),
    composition_mode: cleanText((agent as RuntimeAgentWithSkills).composition_mode),
    proposal_mode: cleanText((agent as RuntimeAgentWithSkills).proposal_mode),
    purpose: cleanText((agent as RuntimeAgentWithSkills).purpose),
    context_policy: (normalizeStructuredValue((agent as RuntimeAgentWithSkills).context_policy) as Record<string, unknown> | null) || null,
    context_policy_summary: cleanText((agent as RuntimeAgentWithSkills).context_policy_summary),
    context_types: stringList((agent as RuntimeAgentWithSkills).context_types || []),
    publish_targets: stringList((agent as RuntimeAgentWithSkills).publish_targets || []),
    query_template: cleanText((agent as RuntimeAgentWithSkills).query_template),
    grant_labels: uniqueStrings((agent as RuntimeAgentWithSkills).grant_labels || []),
    shortcut_eligible: (agent as RuntimeAgentWithSkills).shortcut_eligible == null ? null : asBoolean((agent as RuntimeAgentWithSkills).shortcut_eligible),
    shortcut_max_recent_turns: (agent as RuntimeAgentWithSkills).shortcut_max_recent_turns == null ? null : asNumber((agent as RuntimeAgentWithSkills).shortcut_max_recent_turns),
    only_for_followups: asBoolean((agent as RuntimeAgentWithSkills).only_for_followups),
    interaction_contract: (normalizeStructuredValue((agent as RuntimeAgentWithSkills).interaction_contract) as Record<string, unknown> | null) || null,
  }
}

function fromLegacyTeamItem(item: NonNullable<RunStudioAgentTeam['items']>[number]): RuntimeAgentInstanceV2 {
  return normalizeRuntimeAgent({
    ...item,
    display_label: item.display_label || item.name || item.role_label || item.agent_id,
    instance_id: item.instance_id || item.runtime_instance_id,
  })
}

function fromLegacyRuntimeAgent(item: RuntimeAgentWithSkills): RuntimeAgentInstanceV2 {
  return normalizeRuntimeAgent({
    ...item,
    display_label: item.display_label || item.name || item.role_label || item.agent_id,
  })
}

function fromConfiguredTeamItem(item: RuntimeAgentWithSkills): RuntimeAgentInstanceV2 {
  return normalizeRuntimeAgent({
    ...item,
    synthesized: item.synthesized ?? true,
    display_label: item.display_label || item.name || item.role_label || item.agent_id,
  })
}

function mergeRuntimeAgents(
  primary: RuntimeAgentInstanceV2[],
  secondary: RuntimeAgentInstanceV2[],
): RuntimeAgentInstanceV2[] {
  const merged = new Map<string, RuntimeAgentInstanceV2>()

  primary.forEach((agent) => {
    const normalized = normalizeRuntimeAgent(agent)
    merged.set(runtimeAgentKey(normalized), normalized)
  })

  secondary.forEach((agent) => {
    const normalized = normalizeRuntimeAgent(agent)
    const key = runtimeAgentKey(normalized)
    const current = merged.get(key)
    if (!current) {
      merged.set(key, normalized)
      return
    }

    merged.set(
      key,
      normalizeRuntimeAgent({
        ...normalized,
        ...current,
        display_label: cleanText(current.display_label) || cleanText(normalized.display_label),
        name: cleanText(current.name) || cleanText(normalized.name),
        role_label: cleanText(current.role_label) || cleanText(normalized.role_label),
        role_id: cleanText(current.role_id) || cleanText(normalized.role_id),
        slot_id: cleanText(current.slot_id) || cleanText(normalized.slot_id),
        slot_label: cleanText(current.slot_label) || cleanText(normalized.slot_label),
        preset_id: cleanText(current.preset_id) || cleanText(normalized.preset_id),
        synthesized: current.synthesized ?? normalized.synthesized,
        selection_reason: cleanText(current.selection_reason) || cleanText(normalized.selection_reason),
        template_id: cleanText(current.template_id) || cleanText(normalized.template_id),
        provider: cleanText(current.provider) || cleanText(normalized.provider),
        model: cleanText(current.model) || cleanText(normalized.model),
        runtime_status: cleanText(current.runtime_status) || cleanText(normalized.runtime_status),
        context_pack_id: cleanText(current.context_pack_id) || cleanText(normalized.context_pack_id),
        authority_profile_id: cleanText(current.authority_profile_id) || cleanText(normalized.authority_profile_id),
        source: cleanText(current.source) || cleanText(normalized.source),
        source_key: cleanText(current.source_key) || cleanText(normalized.source_key),
        source_path: cleanText(current.source_path) || cleanText(normalized.source_path),
        attached_skills: mergeAttachedSkills(current.attached_skills, normalized.attached_skills),
        attached_skill_ids: uniqueStrings([
          ...(current.attached_skill_ids || []),
          ...(normalized.attached_skill_ids || []),
        ]),
        enabled: current.enabled ?? normalized.enabled,
      }),
    )
  })

  return Array.from(merged.values()).sort((a, b) => {
    const aLabel = String(a.display_label || a.role_label || a.agent_id || '').toLowerCase()
    const bLabel = String(b.display_label || b.role_label || b.agent_id || '').toLowerCase()
    return aLabel.localeCompare(bLabel)
  })
}

function normalizeSupervisorRuntime(raw: OrchestrationProjection['supervisor_runtime'] | null | undefined) {
  const runtime = raw || {}
  return {
    ...runtime,
    interaction_mode:
      cleanText(runtime.interaction_mode) ||
      cleanText(runtime.mode) ||
      cleanText(runtime.kind) ||
      cleanText(runtime.strategy),
    mode:
      cleanText(runtime.mode) ||
      cleanText(runtime.interaction_mode) ||
      cleanText(runtime.kind) ||
      cleanText(runtime.strategy),
    kind: cleanText(runtime.kind),
    strategy: cleanText(runtime.strategy),
    instance_id: cleanText(runtime.instance_id),
    authority_profile_id: cleanText(runtime.authority_profile_id),
    user_visible:
      runtime.user_visible == null ? undefined : asBoolean(runtime.user_visible),
    enabled:
      runtime.enabled == null ? undefined : asBoolean(runtime.enabled),
  }
}

function normalizeCollaborationCell(item: NonNullable<CollaborationProjection['items']>[number]) {
  const pattern = cleanText(item.pattern) || cleanText(item.kind) || 'collaboration'
  const termination = normalizeStructuredValue(item.termination ?? item.termination_rule)
  const terminationSummary =
    cleanText(item.termination_summary) ||
    structuredSummary(termination)
  return {
    ...item,
    cell_id: cleanText(item.cell_id),
    pattern,
    kind: cleanText(item.kind) || pattern,
    display_label: cleanText(item.display_label),
    member_instance_ids: stringList(item.member_instance_ids),
    member_labels: stringList(item.member_labels),
    report_back_to_instance_id: cleanText(item.report_back_to_instance_id),
    report_back_to_label: cleanText(item.report_back_to_label),
    decision_mode: cleanText(item.decision_mode),
    selection_reason: cleanText(item.selection_reason),
    max_rounds: item.max_rounds == null ? null : asNumber(item.max_rounds),
    topology: cleanText(item.topology),
    termination,
    termination_summary: terminationSummary,
    termination_rule: termination,
  }
}

function normalizeAuthorityItem(item: NonNullable<AuthorityProjection['items']>[number]) {
  const denied = uniqueStrings([...(item.denied_actions || []), ...(item.restricted_actions || [])])
  return {
    ...item,
    runtime_instance_id: cleanText(item.runtime_instance_id),
    display_label: cleanText(item.display_label),
    authority_profile_id: cleanText(item.authority_profile_id),
    managed_by: cleanText(item.managed_by),
    allowed_actions: uniqueStrings(item.allowed_actions || []),
    denied_actions: denied,
    restricted_actions: denied,
    approval_required_for: uniqueStrings(item.approval_required_for || []),
    tool_allowlist: uniqueStrings(item.tool_allowlist || []),
    graph_entry_count: asNumber(item.graph_entry_count),
  }
}

function normalizeCheckpoint(item: ExecutionCheckpoint): ExecutionCheckpoint {
  const humanInterruptAllowed =
    item.human_interrupt_allowed == null
      ? item.requires_human == null
        ? undefined
        : asBoolean(item.requires_human)
      : asBoolean(item.human_interrupt_allowed)
  const approvalRequired =
    item.approval_required == null
      ? item.requires_approval == null
        ? undefined
        : asBoolean(item.requires_approval)
      : asBoolean(item.approval_required)

  const supervisorDecision = normalizeStructuredValue(item.supervisor_decision)
  const completionSignal = normalizeStructuredValue(item.completion_signal)
  return {
    ...item,
    checkpoint_id: cleanText(item.checkpoint_id),
    kind: cleanText(item.kind),
    label: cleanText(item.label),
    stage: cleanText(item.stage),
    status: cleanText(item.status) || 'pending',
    human_interrupt_allowed: humanInterruptAllowed,
    requires_human: humanInterruptAllowed,
    approval_required: approvalRequired,
    requires_approval: approvalRequired,
    blocking: item.blocking == null ? undefined : asBoolean(item.blocking),
    trigger_after_instances: stringList(item.trigger_after_instances),
    trigger_after_labels: stringList(item.trigger_after_labels),
    supervisor_decision: supervisorDecision,
    supervisor_decision_summary:
      cleanText(item.supervisor_decision_summary) ||
      structuredSummary(supervisorDecision),
    completion_signal: completionSignal,
    completion_signal_summary:
      cleanText(item.completion_signal_summary) ||
      structuredSummary(completionSignal),
    selection_reason: cleanText(item.selection_reason),
  }
}

function currentRunSkills(summary: RunStudioSummary | null) {
  return summary?.current_run_skills || null
}

export function selectEffectiveAgentTeam(summary: RunStudioSummary | null, detail: RunStudioAgentTeam | null): RunStudioAgentTeam | null {
  if (detail) return detail
  return summary?.agent_team || null
}

export function selectEffectiveTeamView(summary: RunStudioSummary | null, detail: RunStudioAgentTeam | null): TeamViewProjection | null {
  const runSkills = currentRunSkills(summary)
  const rawProjection = summary?.team_view || runSkills?.team_view || null
  const effectiveTeam = selectEffectiveAgentTeam(summary, detail)
  const rawItems = (rawProjection?.items || []).map((item) => normalizeRuntimeAgent(item))
  const legacyTeamItems = (effectiveTeam?.items || []).map((item) => fromLegacyTeamItem(item))
  const configuredTeamItems = (effectiveTeam?.configured_items || []).map((item) => fromConfiguredTeamItem(item))
  const legacyRuntimeAgents = (runSkills?.runtime_agents || []).map((item) => fromLegacyRuntimeAgent(item))
  const items = mergeRuntimeAgents(rawItems, [...legacyRuntimeAgents, ...legacyTeamItems, ...configuredTeamItems])

  if (!rawProjection && items.length === 0) return null

  const presetCount = rawProjection?.preset_count ?? items.filter((item) => Boolean(cleanText(item.preset_id))).length
  const synthesizedCount = rawProjection?.synthesized_count ?? items.filter((item) => Boolean(item.synthesized || item.configured_only)).length

  return {
    items,
    count: rawProjection?.count ?? items.length,
    preset_count: presetCount,
    synthesized_count: synthesizedCount,
    blueprint_summary: rawProjection?.blueprint_summary || runSkills?.team_view?.blueprint_summary || null,
  }
}

export function selectEffectiveScopeProjection(summary: RunStudioSummary | null, detail: RunStudioAgentTeam | null): ScopeProjection | null {
  const rawProjection = currentRunSkills(summary)?.scope_projection || summary?.scope_projection || null
  if (rawProjection && (Number(rawProjection.count || 0) > 0 || (rawProjection.items || []).length > 0)) {
    return rawProjection
  }
  const effectiveTeam = selectEffectiveAgentTeam(summary, detail)
  const configuredItems = effectiveTeam?.configured_scope_items || []
  if (configuredItems.length === 0) return rawProjection

  const grantCounts = configuredItems.reduce<Record<string, number>>((acc, item) => {
    ;(item.grant_labels || []).forEach((grant) => {
      const key = cleanText(grant)
      if (!key) return
      acc[key] = (acc[key] || 0) + 1
    })
    return acc
  }, {})
  const visibilityCounts = configuredItems.reduce<Record<string, number>>((acc, item) => {
    const key = cleanText(item.visibility_mode) || 'configured'
    acc[key] = (acc[key] || 0) + 1
    return acc
  }, {})

  return {
    ...(rawProjection || {}),
    context_runtime_mode: cleanText(rawProjection?.context_runtime_mode) || 'scoped_context',
    items: configuredItems,
    count: configuredItems.length,
    grant_counts: Object.keys(rawProjection?.grant_counts || {}).length > 0 ? rawProjection?.grant_counts || {} : grantCounts,
    visibility_counts: Object.keys(rawProjection?.visibility_counts || {}).length > 0 ? rawProjection?.visibility_counts || {} : visibilityCounts,
    scope_projection_note:
      cleanText(rawProjection?.scope_projection_note) ||
      'Showing configured scope policies from team_config because no runtime materialized scopes are available yet.',
  }
}

export function selectEffectiveWhyThisTeam(
  summary: RunStudioSummary | null,
  detail: RunStudioAgentTeam | null,
): WhyThisTeamProjection | null {
  const rawProjection = summary?.why_this_team || currentRunSkills(summary)?.why_this_team || null
  const teamView = selectEffectiveTeamView(summary, detail)
  if (!rawProjection && !(teamView?.items?.length || 0)) return null

  const derivedAgentReasons = (teamView?.items || [])
    .filter((item) => Boolean(cleanText(item.selection_reason)))
    .map((item) => ({
      runtime_instance_id: item.runtime_instance_id || item.instance_id || null,
      display_label: item.display_label || item.role_label || item.agent_id || null,
      reason: item.selection_reason || null,
    }))

  const seenSlotIds = new Set<string>()
  const derivedSlotReasons = derivedAgentReasons
    .map((item, index) => {
      const source = (teamView?.items || [])[index]
      const slotId = cleanText(source?.slot_id)
      if (!slotId || seenSlotIds.has(slotId)) return null
      seenSlotIds.add(slotId)
      return {
        slot_id: slotId,
        role_id: source?.role_id || null,
        display_label: source?.slot_label || source?.role_label || source?.display_label || null,
        reason: source?.selection_reason || null,
      }
    })
    .filter((item): item is NonNullable<typeof item> => Boolean(item))

  return {
    blueprint_summary: rawProjection?.blueprint_summary || teamView?.blueprint_summary || null,
    selection_explanations: rawProjection?.selection_explanations || [],
    slot_reasons: rawProjection?.slot_reasons?.length ? rawProjection.slot_reasons : derivedSlotReasons,
    agent_reasons: rawProjection?.agent_reasons?.length ? rawProjection.agent_reasons : derivedAgentReasons,
    conversation_preferences: rawProjection?.conversation_preferences || null,
    preset_count: rawProjection?.preset_count ?? teamView?.preset_count ?? 0,
    synthesized_count: rawProjection?.synthesized_count ?? teamView?.synthesized_count ?? 0,
  }
}

export function selectEffectiveOrchestration(
  summary: RunStudioSummary | null,
  teamView?: TeamViewProjection | null,
): OrchestrationProjection | null {
  const rawProjection = summary?.orchestration || currentRunSkills(summary)?.orchestration || null
  const labelsByInstance = new Map(
    (teamView?.items || [])
      .map((item) => [cleanText(item.runtime_instance_id), cleanText(item.display_label)])
      .filter((item): item is [string, string] => Boolean(item[0] && item[1])),
  )
  if (!rawProjection) {
    const supervisorRuntime = normalizeSupervisorRuntime({})
    return {
      mode: 'runtime_managed',
      parallel_groups: [],
      sequential_after: {},
      supervisor_runtime: supervisorRuntime,
      supervisor_mode: null,
      supervisor_enabled: false,
      supervisor_edges: [],
      checkpoint_count: 0,
      checkpoint_status_counts: {},
      parallel_group_count: 0,
      sequential_dependency_count: 0,
      supervisor_edge_count: 0,
    }
  }

  const parallelGroups = (rawProjection.parallel_groups || []).map((group, index) => {
    const memberInstanceIds = stringList(group.member_instance_ids || group.members || group.agents)
    const memberLabels = uniqueStrings([
      ...stringList(group.member_labels || group.memberLabels),
      ...memberInstanceIds.map((memberId) => labelsByInstance.get(memberId) || null),
    ])
    return {
      ...group,
      group_id: cleanText(group.group_id) || `group-${index + 1}`,
      label: cleanText(group.label || group.display_label || group.name),
      member_instance_ids: memberInstanceIds,
      member_labels: memberLabels,
    }
  })
  const sequentialAfter = rawProjection.sequential_after || {}
  const supervisorEdges = (rawProjection.supervisor_edges || []).map((edge) => {
    const fromId = cleanText(edge.from) || cleanText(edge.source) || cleanText(edge.supervisor_id)
    const toId = cleanText(edge.to) || cleanText(edge.target) || cleanText(edge.runtime_instance_id)
    const fromLabel = cleanText(edge.from_label) || (fromId ? labelsByInstance.get(fromId) || null : null)
    const toLabel = cleanText(edge.to_label) || (toId ? labelsByInstance.get(toId) || null : null)
    const edgeSummary =
      cleanText(edge.edge_summary) ||
      (fromId && toId ? `${fromLabel || fromId} -> ${toLabel || toId}` : null)
    return {
      ...edge,
      from: fromId,
      to: toId,
      from_label: fromLabel,
      to_label: toLabel,
      edge_summary: edgeSummary,
    }
  })
  const supervisorRuntime = normalizeSupervisorRuntime(rawProjection.supervisor_runtime)
  const supervisorMode =
    cleanText(rawProjection.supervisor_mode) ||
    cleanText(supervisorRuntime.interaction_mode) ||
    cleanText(supervisorRuntime.mode) ||
    null
  const supervisorEnabled =
    rawProjection.supervisor_enabled == null
      ? Boolean(supervisorMode || supervisorRuntime.instance_id || supervisorEdges.length)
      : asBoolean(rawProjection.supervisor_enabled)

  return {
    ...rawProjection,
    mode: cleanText(rawProjection.mode) || 'runtime_managed',
    parallel_groups: parallelGroups,
    sequential_after: sequentialAfter,
    supervisor_runtime: supervisorRuntime,
    supervisor_mode: supervisorMode,
    supervisor_enabled: supervisorEnabled,
    supervisor_edges: supervisorEdges,
    checkpoint_count: rawProjection.checkpoint_count ?? 0,
    checkpoint_status_counts: rawProjection.checkpoint_status_counts || {},
    parallel_group_count: rawProjection.parallel_group_count ?? parallelGroups.length,
    sequential_dependency_count: rawProjection.sequential_dependency_count ?? Object.keys(sequentialAfter).length,
    supervisor_edge_count: rawProjection.supervisor_edge_count ?? supervisorEdges.length,
  }
}

export function selectEffectiveCollaboration(summary: RunStudioSummary | null): CollaborationProjection | null {
  const rawProjection = summary?.collaboration || currentRunSkills(summary)?.collaboration || null
  if (!rawProjection) {
    return {
      items: [],
      counts: {},
      count: 0,
    }
  }

  const items = (rawProjection.items || []).map((item) => normalizeCollaborationCell(item))
  const counts = rawProjection.counts || items.reduce<Record<string, number>>((acc, item) => {
    const kind = cleanText(item.pattern) || cleanText(item.kind) || 'collaboration'
    acc[kind] = (acc[kind] || 0) + 1
    return acc
  }, {})

  return {
    items,
    counts,
    count: rawProjection.count ?? items.length,
  }
}

export function selectEffectiveAuthority(summary: RunStudioSummary | null, detail: RunStudioAgentTeam | null): AuthorityProjection | null {
  const rawProjection = summary?.authority || currentRunSkills(summary)?.authority || null
  const teamView = selectEffectiveTeamView(summary, detail)
  const fallbackItems = (teamView?.items || [])
    .filter((item) => Boolean(cleanText(item.authority_profile_id)))
    .map((item) => ({
      runtime_instance_id: item.runtime_instance_id || item.instance_id || null,
      display_label: item.display_label || item.role_label || item.agent_id || null,
      authority_profile_id: item.authority_profile_id || null,
      managed_by: null,
      allowed_actions: [],
      denied_actions: [],
      restricted_actions: [],
      approval_required_for: [],
      tool_allowlist: [],
      graph_entry_count: 0,
    }))

  const rawItems = (rawProjection?.items || []).map((item) => normalizeAuthorityItem(item))
  const mergedItemsMap = new Map<string, AuthorityProjection['items'][number]>()
  ;[...rawItems, ...fallbackItems].forEach((item) => {
    const key = cleanText(item.runtime_instance_id) || cleanText(item.display_label) || cleanText(item.authority_profile_id) || 'authority'
    const current = mergedItemsMap.get(key)
    mergedItemsMap.set(key, {
      ...item,
      ...current,
      runtime_instance_id: cleanText(current?.runtime_instance_id) || cleanText(item.runtime_instance_id),
      display_label: cleanText(current?.display_label) || cleanText(item.display_label),
      authority_profile_id: cleanText(current?.authority_profile_id) || cleanText(item.authority_profile_id),
      managed_by: cleanText(current?.managed_by) || cleanText(item.managed_by),
      allowed_actions: uniqueStrings([...(current?.allowed_actions || []), ...(item.allowed_actions || [])]),
      denied_actions: uniqueStrings([
        ...(current?.denied_actions || current?.restricted_actions || []),
        ...(item.denied_actions || item.restricted_actions || []),
      ]),
      restricted_actions: uniqueStrings([
        ...(current?.denied_actions || current?.restricted_actions || []),
        ...(item.denied_actions || item.restricted_actions || []),
      ]),
      approval_required_for: uniqueStrings([
        ...(current?.approval_required_for || []),
        ...(item.approval_required_for || []),
      ]),
      tool_allowlist: uniqueStrings([...(current?.tool_allowlist || []), ...(item.tool_allowlist || [])]),
      graph_entry_count: Math.max(asNumber(current?.graph_entry_count), asNumber(item.graph_entry_count)),
    })
  })

  if (!rawProjection && mergedItemsMap.size === 0) return null

  return {
    items: Array.from(mergedItemsMap.values()),
    graph: (rawProjection?.graph || []).map((entry) => ({
      ...entry,
      authority_id: cleanText(entry.authority_id),
      runtime_instance_id: cleanText(entry.runtime_instance_id),
      authority_profile_id: cleanText(entry.authority_profile_id),
      managed_by: cleanText(entry.managed_by),
      scope: cleanText(entry.scope),
      allowed_actions: uniqueStrings(entry.allowed_actions || []),
      denied_actions: uniqueStrings([...(entry.denied_actions || []), ...(entry.restricted_actions || [])]),
      restricted_actions: uniqueStrings([...(entry.denied_actions || []), ...(entry.restricted_actions || [])]),
      approval_required_for: uniqueStrings(entry.approval_required_for || []),
      tool_allowlist: uniqueStrings(entry.tool_allowlist || []),
    })),
    count: rawProjection?.count ?? mergedItemsMap.size,
    graph_count: rawProjection?.graph_count ?? (rawProjection?.graph || []).length,
  }
}

export function selectEffectiveCheckpoints(summary: RunStudioSummary | null): CheckpointProjection | null {
  const rawProjection = summary?.checkpoints || currentRunSkills(summary)?.checkpoints || null
  const rawItems = rawProjection?.items || []
  const nowState = summary?.now?.state
  const syntheticItems: ExecutionCheckpoint[] = []

  if (rawItems.length === 0 && asBoolean(nowState?.current_pending_approval ?? nowState?.pending_approval)) {
    syntheticItems.push(normalizeCheckpoint({
      checkpoint_id: 'legacy-pending-approval',
      kind: 'approval',
      label: 'Pending user approval',
      status: 'pending',
      approval_required: true,
      requires_approval: true,
      blocking: true,
    }))
  }

  const items = rawItems.length > 0 ? rawItems.map((item) => normalizeCheckpoint(item)) : syntheticItems
  if (!rawProjection && items.length === 0) return null

  const counts = rawProjection?.counts || {
    total: items.length,
    human_interrupts: items.filter((item) => asBoolean(item.human_interrupt_allowed ?? item.requires_human)).length,
    approval_required: items.filter((item) => asBoolean(item.approval_required ?? item.requires_approval)).length,
    blocking: items.filter((item) => asBoolean(item.blocking)).length,
  }

  return {
    items,
    counts,
  }
}

export function selectEffectiveContextPacks(summary: RunStudioSummary | null, detail: RunStudioContextPacks | null): RunStudioContextPacks | null {
  if (detail) return detail
  const runSkills = currentRunSkills(summary)
  if (!runSkills) return null
  const items = runSkills.context_packs || []
  return {
    run_id: runSkills.run_id || null,
    count: items.length,
    items,
    updated_at: runSkills.updated_at || summary?.updated_at || null,
    planning_boundary: runSkills.planning_boundary || summary?.planning_boundary,
    runtime_authority: runSkills.runtime_authority || summary?.runtime_authority,
    mode: runSkills.mode || summary?.mode,
    plan_source: runSkills.plan_source || summary?.plan_source,
    context_source: runSkills.context_source || summary?.context_source,
    agent_catalog_source: runSkills.agent_catalog_source || summary?.agent_catalog_source,
    conversation_team_source: runSkills.conversation_team_source || summary?.conversation_team_source,
    skill_catalog_source: runSkills.skill_catalog_source || summary?.skill_catalog_source,
    degraded_mode: runSkills.degraded_mode ?? summary?.degraded_mode,
    fallback_reason: runSkills.fallback_reason || summary?.fallback_reason || null,
  }
}

export function selectEffectiveSkillUsage(summary: RunStudioSummary | null, detail: RunStudioSkillUsage | null): RunStudioSkillUsage | null {
  if (detail) return detail
  const runSkills = currentRunSkills(summary)
  if (!runSkills) return null
  const items = runSkills.skill_usage || []
  return {
    run_id: runSkills.run_id || null,
    count: items.length,
    items,
    updated_at: runSkills.updated_at || summary?.updated_at || null,
    planning_boundary: runSkills.planning_boundary || summary?.planning_boundary,
    runtime_authority: runSkills.runtime_authority || summary?.runtime_authority,
    mode: runSkills.mode || summary?.mode,
    plan_source: runSkills.plan_source || summary?.plan_source,
    context_source: runSkills.context_source || summary?.context_source,
    agent_catalog_source: runSkills.agent_catalog_source || summary?.agent_catalog_source,
    conversation_team_source: runSkills.conversation_team_source || summary?.conversation_team_source,
    skill_catalog_source: runSkills.skill_catalog_source || summary?.skill_catalog_source,
    degraded_mode: runSkills.degraded_mode ?? summary?.degraded_mode,
    fallback_reason: runSkills.fallback_reason || summary?.fallback_reason || null,
  }
}

export function selectTeamViewFlags(teamView: TeamViewProjection | null) {
  const items = teamView?.items || []
  const textForItem = (item: RuntimeAgentInstanceV2) =>
    [item.display_label, item.role_label, item.slot_label, item.role_id].filter(Boolean).join(' ').toLowerCase()

  const reviewerPresent = items.some((item) => /review|critic|judge|qa|eval/.test(textForItem(item)))
  const synthesizerPresent = items.some((item) => /synth|writer|final|compose|summar/.test(textForItem(item)))

  return {
    reviewerPresent,
    synthesizerPresent,
  }
}

export function selectDominantSkills(agent: RuntimeAgentInstanceV2, maxItems = 3): AttachedSkillSummary[] {
  return [...(agent.attached_skills || [])]
    .sort((a, b) => {
      const loadDiff = skillLoadRank(b.load_level) - skillLoadRank(a.load_level)
      if (loadDiff !== 0) return loadDiff
      return String(a.skill_name || a.skill_id).localeCompare(String(b.skill_name || b.skill_id))
    })
    .slice(0, maxItems)
}

export function selectTeamDiversitySummary(teamView: TeamViewProjection | null): string[] {
  const items = teamView?.items || []
  const roles = new Set(items.map((item) => cleanText(item.role_label || item.slot_label || item.display_label)).filter(Boolean))
  const presets = items.filter((item) => Boolean(cleanText(item.preset_id))).length
  const synthesized = items.filter((item) => Boolean(item.synthesized)).length
  const notes: string[] = []

  if (roles.size > 1) notes.push(`${roles.size} distinct roles in the active team`)
  if (presets > 0) notes.push(`${presets} preset-backed runtime agents`)
  if (synthesized > 0) notes.push(`${synthesized} synthesized runtime agents`)
  if (items.length > 1 && roles.size <= 1) notes.push('multiple agents share similar roles to increase coverage or redundancy')

  return notes
}

export function selectControlPlaneSummary(
  summary: RunStudioSummary | null,
  detail: RunStudioAgentTeam | null,
): ControlPlaneSummaryProjection | null {
  const teamView = selectEffectiveTeamView(summary, detail)
  const orchestration = selectEffectiveOrchestration(summary, teamView)
  const collaboration = selectEffectiveCollaboration(summary)
  const checkpoints = selectEffectiveCheckpoints(summary)
  const authority = summary?.runtime_authority || currentRunSkills(summary)?.runtime_authority || null
  const state = summary?.now?.state || {}

  const mode = cleanText(authority?.mode) || cleanText(state.mode) || cleanText(summary?.mode) || 'standalone'
  const planSource = cleanText(authority?.plan_source) || cleanText(state.plan_source) || cleanText(summary?.plan_source) || 'local'
  const contextSource = cleanText(authority?.context_source) || cleanText(state.context_source) || cleanText(summary?.context_source) || 'local'
  const teamSource = cleanText(authority?.conversation_team_source) || cleanText(state.conversation_team_source) || cleanText(summary?.conversation_team_source) || 'local'
  const skillSource = cleanText(authority?.skill_catalog_source) || cleanText(state.skill_catalog_source) || cleanText(summary?.skill_catalog_source) || 'local'
  const degradedMode = Boolean(authority?.degraded_mode ?? state.degraded_mode ?? summary?.degraded_mode)
  const fallbackReason = cleanText(authority?.fallback_reason) || cleanText(state.fallback_reason) || cleanText(summary?.fallback_reason) || null
  const supervisorMode =
    cleanText(orchestration?.supervisor_mode) ||
    cleanText(orchestration?.supervisor_runtime?.interaction_mode) ||
    cleanText(orchestration?.supervisor_runtime?.mode) ||
    null
  const items = teamView?.items || []
  const runtimeAgentCount = teamView?.count ?? items.length
  const presetCount = teamView?.preset_count ?? items.filter((item) => Boolean(cleanText(item.preset_id))).length
  const synthesizedCount = teamView?.synthesized_count ?? items.filter((item) => Boolean(item.synthesized)).length
  const reviewerPresent = items.some((item) => cleanText(item.role_id || item.role_label) === 'reviewer')
  const synthesizerPresent = items.some((item) => cleanText(item.role_id || item.role_label) === 'synthesizer')
  const collaborationCount = collaboration?.count ?? collaboration?.items?.length ?? 0
  const checkpointCount = Number(checkpoints?.counts?.total || checkpoints?.items?.length || 0)
  const parallelGroupCount = orchestration?.parallel_group_count ?? orchestration?.parallel_groups?.length ?? 0
  const supervisorEnabled = Boolean(
    orchestration?.supervisor_enabled ||
    supervisorMode ||
    orchestration?.supervisor_edges?.length ||
    orchestration?.supervisor_runtime?.instance_id,
  )
  const legacyFallback = !summary?.team_view && !currentRunSkills(summary)?.team_view
  const scopeProjection = selectEffectiveScopeProjection(summary, detail)
  const scopeMode = cleanText(scopeProjection?.context_runtime_mode) || 'shared_memory'
  const scopeCount = Number(scopeProjection?.count || 0)
  const legacyContextPackCount = Number(scopeProjection?.legacy_context_pack_count || 0)
  const legacyContextPacksEnabled = Boolean(scopeProjection?.legacy_context_packs_enabled)
  const legacyContextStrategy = cleanText(scopeProjection?.legacy_context_strategy) || null

  return {
    mode,
    planSource,
    contextSource,
    teamSource,
    skillSource,
    supervisorMode,
    supervisorEnabled,
    runtimeAgentCount,
    parallelGroupCount,
    collaborationCount,
    checkpointCount,
    presetCount,
    synthesizedCount,
    reviewerPresent,
    synthesizerPresent,
    degradedMode,
    fallbackReason,
    legacyFallback,
    scopeMode,
    scopeCount,
    legacyContextPackCount,
    legacyContextPacksEnabled,
    legacyContextStrategy,
  }
}


export function selectSkillAttachmentOverview(
  summary: RunStudioSummary | null,
  detail?: RunStudioAgentTeam | null,
): SkillAttachmentOverviewProjection {
  const teamView = selectEffectiveTeamView(summary, detail)
  const items = teamView?.items || []

  const agents: AgentSkillAttachmentProjection[] = items
    .map((item) => ({
      runtime_instance_id: cleanText(item.runtime_instance_id || item.instance_id || item.agent_id),
      display_label: cleanText(item.display_label) || friendlyRuntimeLabel(item),
      role_label: cleanText(item.role_label) || titleCaseIdentifier(item.role_id) || 'Runtime agent',
      slot_label: cleanText(item.slot_label || item.slot_id),
      authority_profile_id: cleanText(item.authority_profile_id),
      preset_id: cleanText(item.preset_id),
      synthesized: Boolean(item.synthesized),
      attached_skills: mergeAttachedSkills(item.attached_skills),
      attached_skill_ids: uniqueStrings(item.attached_skill_ids || []),
    }))
    .sort((a, b) => a.display_label.localeCompare(b.display_label))

  const skillCounts = new Map<string, { skill_name: string; count: number }>()
  let totalAgentSkillLinks = 0
  let agentsWithSkills = 0

  agents.forEach((agent) => {
    if ((agent.attached_skills || []).length > 0 || (agent.attached_skill_ids || []).length > 0) agentsWithSkills += 1
    ;(agent.attached_skills || []).forEach((skill) => {
      const skillId = cleanText(skill.skill_id)
      if (!skillId) return
      totalAgentSkillLinks += 1
      const current = skillCounts.get(skillId) || { skill_name: cleanText(skill.skill_name) || skillId, count: 0 }
      current.count += 1
      current.skill_name = cleanText(skill.skill_name) || current.skill_name || skillId
      skillCounts.set(skillId, current)
    })
    if ((agent.attached_skills || []).length === 0) {
      ;(agent.attached_skill_ids || []).forEach((skillIdRaw) => {
        const skillId = cleanText(skillIdRaw)
        if (!skillId) return
        totalAgentSkillLinks += 1
        const current = skillCounts.get(skillId) || { skill_name: skillId, count: 0 }
        current.count += 1
        skillCounts.set(skillId, current)
      })
    }
  })

  const top_skills = Array.from(skillCounts.entries())
    .map(([skill_id, value]) => ({ skill_id, skill_name: value.skill_name, count: value.count }))
    .sort((a, b) => (b.count - a.count) || a.skill_name.localeCompare(b.skill_name))

  return {
    agents,
    top_skills,
    total_agent_skill_links: totalAgentSkillLinks,
    total_unique_skills: top_skills.length,
    agents_with_skills: agentsWithSkills,
  }
}
