import React from 'react'
import { type RunStudioAgentTeam, type RunStudioSummary } from './types'
import { selectEffectiveAgentTeam } from './selectors'

type Props = {
  summary: RunStudioSummary | null
  team: RunStudioAgentTeam | null
}

export default function AttachedSkillsPanel({ summary, team }: Props) {
  const effectiveTeam = selectEffectiveAgentTeam(summary, team)
  const currentRunSkills = summary?.current_run_skills
  const aggregatedSkills = currentRunSkills?.attached_skills || []
  const roleSkillLinks = currentRunSkills?.lineage?.role_skill_links || []

  const fallbackRoleSkills = (effectiveTeam?.items || [])
    .flatMap((item) =>
      (item.attached_skills || []).map((skill) => ({
        runtime_instance_id: item.runtime_instance_id || null,
        role_label: item.role_label || item.name || item.agent_id,
        skill_id: skill.skill_id,
        skill_name: skill.skill_name || skill.skill_id,
        load_level: skill.load_level || 'metadata_only',
        selected_by: skill.selected_by || null,
        selection_reason: skill.selection_reason || null,
      })),
    )

  const effectiveRoleLinks = roleSkillLinks.length > 0 ? roleSkillLinks : fallbackRoleSkills

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Attached Skills</h3>
        <div className="runStudioMetaRow">
          <span className="pill">skills: {aggregatedSkills.length}</span>
          <span className="pill">role links: {effectiveRoleLinks.length}</span>
        </div>
      </div>

      {aggregatedSkills.length > 0 && (
        <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
          {aggregatedSkills.slice(0, 10).map((skill) => (
            <span key={skill.skill_id} className="pill">
              {skill.skill_name || skill.skill_id}
              {skill.load_level ? ` (${skill.load_level})` : ''}
            </span>
          ))}
        </div>
      )}

      <div className="runStudioList">
        {effectiveRoleLinks.slice(0, 14).map((link, index) => (
          <article key={`${link.runtime_instance_id || link.role_label || 'role'}:${link.skill_id || 'skill'}:${index}`} className="runStudioListItem">
            <div className="row" style={{ marginBottom: 4 }}>
              <span className="pill">{link.role_label || link.runtime_instance_id || 'runtime role'}</span>
              <span className="pill">{link.skill_name || link.skill_id}</span>
              <span className="pill">load: {link.load_level || 'metadata_only'}</span>
              {link.selected_by && <span className="pill">by: {link.selected_by}</span>}
            </div>
            {link.selection_reason && <div className="muted">reason: {link.selection_reason}</div>}
          </article>
        ))}
        {effectiveRoleLinks.length === 0 && (
          <div className="muted">No attached skills are visible yet for this run scope.</div>
        )}
      </div>
    </section>
  )
}
