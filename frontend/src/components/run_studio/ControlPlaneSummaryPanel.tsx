import React from 'react'
import { type ControlPlaneSummaryProjection, type SkillAttachmentOverviewProjection } from './types'

type Props = {
  summary: ControlPlaneSummaryProjection | null
  skillOverview?: SkillAttachmentOverviewProjection | null
}

const statCards = (summary: ControlPlaneSummaryProjection, skillOverview?: SkillAttachmentOverviewProjection | null) => [
  ['Supervisor', summary.supervisorEnabled ? (summary.supervisorMode || 'enabled') : 'disabled'],
  ['Runtime agents', String(summary.runtimeAgentCount)],
  ['Parallel groups', String(summary.parallelGroupCount)],
  ['Collaboration cells', String(summary.collaborationCount)],
  ['Checkpoints', String(summary.checkpointCount)],
  ['Preset-backed', String(summary.presetCount)],
  ['Synthesized', String(summary.synthesizedCount)],
  ['Attached skills', String(skillOverview?.total_unique_skills || 0)],
  ['Review / synthesis', `${summary.reviewerPresent ? 'reviewer' : 'no reviewer'} · ${summary.synthesizerPresent ? 'synthesizer' : 'no synthesizer'}`],
]

export default function ControlPlaneSummaryPanel({ summary, skillOverview }: Props) {
  if (!summary) return null
  const topSkills = (skillOverview?.top_skills || []).slice(0, 8)

  return (
    <section className="card runStudioPanel runStudioHeroPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3 style={{ margin: 0 }}>Control Plane Summary</h3>
          <div className="muted">This run is being interpreted as a structured runtime: slots, runtime agents, orchestration, checkpoints, and skill attachment.</div>
        </div>
        <div className="runStudioMetaRow" style={{ marginBottom: 0 }}>
          <span className="pill">mode: {summary.mode}</span>
          <span className="pill">plan: {summary.planSource}</span>
          <span className="pill">context: {summary.contextSource}</span>
          <span className="pill">team: {summary.teamSource}</span>
          <span className="pill">skills: {summary.skillSource}</span>
        </div>
      </div>

      <div className="runStudioHeroStatsGrid">
        {statCards(summary, skillOverview).map(([label, value]) => (
          <div key={label} className="runStudioHeroStatCard">
            <div className="muted">{label}</div>
            <div className="runStudioHeroStatValue">{value}</div>
          </div>
        ))}
      </div>

      {topSkills.length > 0 && (
        <div className="runStudioHeroSkillStrip">
          <div className="muted" style={{ marginBottom: 6 }}>Most attached skills across the current runtime team</div>
          <div className="runStudioMetaRow">
            {topSkills.map((skill) => (
              <span key={skill.skill_id} className="pill runStudioSkillPill runStudioSkillPill--prominent">
                {skill.skill_name} · {skill.count}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="runStudioMetaRow runStudioHeroBadges">
        {summary.supervisorEnabled && <span className="pill">supervisor active</span>}
        {summary.legacyFallback && <span className="pill">legacy fallback</span>}
        {summary.degradedMode && <span className="pill">degraded mode</span>}
        {summary.reviewerPresent && <span className="pill">reviewer present</span>}
        {summary.synthesizerPresent && <span className="pill">synthesizer present</span>}
        {(skillOverview?.agents_with_skills || 0) > 0 && <span className="pill">agents with skills: {skillOverview?.agents_with_skills}</span>}
      </div>

      {summary.fallbackReason && (
        <div className="runStudioWarning"><b>Fallback reason:</b> {summary.fallbackReason}</div>
      )}
    </section>
  )
}
