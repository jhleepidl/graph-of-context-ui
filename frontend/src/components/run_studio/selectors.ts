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
  type TeamViewProjection,
  type WhyThisTeamProjection,
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
    display_label: cleanText(agent.display_label || agent.name || agent.role_label || agent.agent_id),
    name: cleanText(agent.name || agent.display_label || agent.role_label || agent.agent_id),
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
  const rawItems = (rawProjection?.items || []).map((item) => normalizeRuntimeAgent(item))
  const legacyTeamItems = (selectEffectiveAgentTeam(summary, detail)?.items || []).map((item) => fromLegacyTeamItem(item))
  const legacyRuntimeAgents = (runSkills?.runtime_agents || []).map((item) => fromLegacyRuntimeAgent(item))
  const items = mergeRuntimeAgents(rawItems, [...legacyRuntimeAgents, ...legacyTeamItems])

  if (!rawProjection && items.length === 0) return null

  const presetCount = rawProjection?.preset_count ?? items.filter((item) => Boolean(cleanText(item.preset_id))).length
  const synthesizedCount = rawProjection?.synthesized_count ?? items.filter((item) => Boolean(item.synthesized)).length

  return {
    items,
    count: rawProjection?.count ?? items.length,
    preset_count: presetCount,
    synthesized_count: synthesizedCount,
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
    selection_explanations: rawProjection?.selection_explanations || [],
    slot_reasons: rawProjection?.slot_reasons?.length ? rawProjection.slot_reasons : derivedSlotReasons,
    agent_reasons: rawProjection?.agent_reasons?.length ? rawProjection.agent_reasons : derivedAgentReasons,
    conversation_preferences: rawProjection?.conversation_preferences || null,
    preset_count: rawProjection?.preset_count ?? teamView?.preset_count ?? 0,
    synthesized_count: rawProjection?.synthesized_count ?? teamView?.synthesized_count ?? 0,
  }
}

export function selectEffectiveOrchestration(summary: RunStudioSummary | null): OrchestrationProjection | null {
  const rawProjection = summary?.orchestration || currentRunSkills(summary)?.orchestration || null
  if (!rawProjection) {
    return {
      mode: 'runtime_managed',
      parallel_groups: [],
      sequential_after: {},
      supervisor_runtime: {},
      supervisor_mode: null,
      supervisor_edges: [],
      parallel_group_count: 0,
      sequential_dependency_count: 0,
      supervisor_edge_count: 0,
    }
  }

  const parallelGroups = rawProjection.parallel_groups || []
  const sequentialAfter = rawProjection.sequential_after || {}
  const supervisorEdges = rawProjection.supervisor_edges || []

  return {
    ...rawProjection,
    mode: cleanText(rawProjection.mode) || 'runtime_managed',
    parallel_groups: parallelGroups,
    sequential_after: sequentialAfter,
    supervisor_runtime: rawProjection.supervisor_runtime || {},
    supervisor_mode:
      cleanText(rawProjection.supervisor_mode) ||
      cleanText(rawProjection.supervisor_runtime?.mode) ||
      cleanText(rawProjection.supervisor_runtime?.kind) ||
      null,
    supervisor_edges: supervisorEdges,
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

  const items = rawProjection.items || []
  const counts = rawProjection.counts || items.reduce<Record<string, number>>((acc, item) => {
    const kind = cleanText(item.kind) || 'collaboration'
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
      restricted_actions: [],
      approval_required_for: [],
      graph_entry_count: 0,
    }))

  const rawItems = rawProjection?.items || []
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
      restricted_actions: uniqueStrings([...(current?.restricted_actions || []), ...(item.restricted_actions || [])]),
      approval_required_for: uniqueStrings([
        ...(current?.approval_required_for || []),
        ...(item.approval_required_for || []),
      ]),
      graph_entry_count: Math.max(asNumber(current?.graph_entry_count), asNumber(item.graph_entry_count)),
    })
  })

  if (!rawProjection && mergedItemsMap.size === 0) return null

  return {
    items: Array.from(mergedItemsMap.values()),
    graph: rawProjection?.graph || [],
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
    syntheticItems.push({
      checkpoint_id: 'legacy-pending-approval',
      kind: 'approval',
      label: 'Pending user approval',
      status: 'pending',
      requires_approval: true,
      blocking: true,
    })
  }

  const items = rawItems.length > 0 ? rawItems : syntheticItems
  if (!rawProjection && items.length === 0) return null

  const counts = rawProjection?.counts || {
    total: items.length,
    human_interrupts: items.filter((item) => asBoolean(item.requires_human)).length,
    approval_required: items.filter((item) => asBoolean(item.requires_approval)).length,
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
