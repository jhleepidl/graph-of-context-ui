import {
  type RunStudioAgentTeam,
  type RunStudioContextPacks,
  type RunStudioSkillUsage,
  type RunStudioSummary,
} from './types'

export function selectEffectiveAgentTeam(summary: RunStudioSummary | null, detail: RunStudioAgentTeam | null): RunStudioAgentTeam | null {
  if (detail) return detail
  return summary?.agent_team || null
}

export function selectEffectiveContextPacks(summary: RunStudioSummary | null, detail: RunStudioContextPacks | null): RunStudioContextPacks | null {
  if (detail) return detail
  const runSkills = summary?.current_run_skills
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
  const runSkills = summary?.current_run_skills
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
