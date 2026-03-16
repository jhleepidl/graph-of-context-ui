import React from 'react'
import { type RunStudioAgentTeam, type RunStudioSummary } from './types'
import { selectEffectiveAgentTeam, selectSkillAttachmentOverview } from './selectors'

type Props = {
  summary: RunStudioSummary | null
  team: RunStudioAgentTeam | null
}

export default function AttachedSkillsPanel({ summary, team }: Props) {
  const effectiveTeam = selectEffectiveAgentTeam(summary, team)
  const overview = selectSkillAttachmentOverview(summary, effectiveTeam)
  const agents = overview.agents
  const topSkills = overview.top_skills.slice(0, 10)

  return (
    <section className="card runStudioPanel runStudioSkillAttachmentPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3 style={{ margin: 0 }}>Skill Attachment</h3>
          <div className="muted">Shows how attached skills are distributed across the current runtime agents.</div>
        </div>
        <div className="runStudioMetaRow">
          <span className="pill">agents: {agents.length}</span>
          <span className="pill">agents with skills: {overview.agents_with_skills}</span>
          <span className="pill">unique skills: {overview.total_unique_skills}</span>
          <span className="pill">agent-skill links: {overview.total_agent_skill_links}</span>
        </div>
      </div>

      {topSkills.length > 0 && (
        <div className="runStudioSkillAttachmentSummary">
          <div className="muted" style={{ marginBottom: 6 }}>Top attached skills across the team</div>
          <div className="runStudioMetaRow">
            {topSkills.map((skill) => (
              <span key={skill.skill_id} className="pill runStudioSkillPill runStudioSkillPill--prominent">
                {skill.skill_name} · {skill.count}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="runStudioSkillAttachmentGrid">
        {agents.map((agent) => {
          const skillRows = (agent.attached_skills || []).map((skill) => ({
            id: skill.skill_id,
            name: skill.skill_name || skill.skill_id,
            level: skill.load_level || 'metadata_only',
            selectedBy: skill.selected_by || null,
          }))
          const fallbackRows = skillRows.length > 0
            ? skillRows
            : (agent.attached_skill_ids || []).map((skillId) => ({ id: skillId, name: skillId, level: 'metadata_only', selectedBy: null }))
          return (
            <article key={agent.runtime_instance_id || agent.display_label} className="runStudioSkillAttachmentCard">
              <div className="row" style={{ marginBottom: 6 }}>
                <b>{agent.display_label}</b>
                <span className="pill">{agent.role_label}</span>
                {agent.preset_id && <span className="pill">preset</span>}
                {!agent.preset_id && agent.synthesized && <span className="pill">synthesized</span>}
              </div>
              <div className="muted">slot: {agent.slot_label || '-'}</div>
              {agent.authority_profile_id && <div className="muted">authority: {agent.authority_profile_id}</div>}
              <div className="runStudioSkillStack" style={{ marginTop: 8 }}>
                {fallbackRows.length > 0 ? fallbackRows.map((skill) => (
                  <div key={`${agent.runtime_instance_id || agent.display_label}:${skill.id}`} className="runStudioSkillRow">
                    <span className="runStudioSkillName">{skill.name}</span>
                    <div className="runStudioMetaRow" style={{ justifyContent: 'flex-end' }}>
                      <span className="pill">{skill.level}</span>
                      {skill.selectedBy && <span className="pill">by: {skill.selectedBy}</span>}
                    </div>
                  </div>
                )) : <div className="muted">No attached skills emitted for this agent.</div>}
              </div>
            </article>
          )
        })}
      </div>

      {agents.length === 0 && (
        <div className="muted">No dominant skills are visible yet for this run scope.</div>
      )}
    </section>
  )
}
