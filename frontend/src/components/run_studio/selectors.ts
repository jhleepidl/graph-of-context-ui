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
  }
}
