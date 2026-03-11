import React from 'react'
import { type RunStudioAgentTeam } from './types'

type Props = {
  team: RunStudioAgentTeam | null
}

function sourceLabel(source: string): string {
  const clean = source.trim().toLowerCase()
  if (clean === 'runtime_snapshot') return 'runtime team'
  if (clean === 'conversation_membership') return 'thread team'
  if (clean === 'inferred_from_steps') return 'inferred from steps'
  return clean || 'unknown'
}

function runtimeClass(status: string): string {
  const clean = status.trim().toLowerCase()
  if (clean === 'running') return 'runStudioStatus--running'
  if (clean === 'queued') return 'runStudioStatus--queued'
  if (clean === 'error' || clean === 'blocked') return 'runStudioStatus--blocked'
  if (clean === 'done') return 'runStudioStatus--done'
  return 'runStudioStatus--idle'
}

export default function AgentTeamPanel({ team }: Props) {
  const items = team?.items || []
  const runtimeCount = items.filter((item) => String(item.source || '') === 'runtime_snapshot').length
  const threadTeamCount = items.filter((item) => String(item.source || '') === 'conversation_membership').length
  const inferredCount = items.filter((item) => String(item.source || '') === 'inferred_from_steps').length
  const rolesWithSkillsCount = items.filter((item) => (item.attached_skills || []).length > 0).length

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Agent Team</h3>
        <div className="runStudioMetaRow">
          <span className="pill">active: {team?.active_count ?? 0}</span>
          <span className="pill">runtime: {runtimeCount}</span>
          <span className="pill">thread team: {threadTeamCount}</span>
          <span className="pill">inferred: {inferredCount}</span>
          <span className="pill">with skills: {rolesWithSkillsCount}</span>
        </div>
      </div>

      {items.length === 0 && (
        <div className="muted">No thread team is configured yet. Runtime members appear only after execution emits team snapshots or step agents.</div>
      )}
      {items.length > 0 && runtimeCount === 0 && (
        <div className="muted" style={{ marginBottom: 8 }}>
          Runtime team snapshot not detected yet. This list currently reflects thread team configuration and/or inferred step agents.
        </div>
      )}

      <div className="runStudioList">
        {items.map((item, index) => {
          const status = String(item.runtime_status || 'idle')
          const source = String(item.source || 'unknown')
          return (
            <article key={`${item.agent_id}:${index}`} className="runStudioListItem">
              <div className="row" style={{ marginBottom: 6 }}>
                <b>{item.name || item.role_label || item.agent_id}</b>
                <span className={`pill runStudioStatus ${runtimeClass(status)}`}>{status}</span>
                <span className="pill">{sourceLabel(source)}</span>
                {!item.enabled && <span className="pill">disabled</span>}
                {typeof item.order_index === 'number' && <span className="pill">#{item.order_index + 1}</span>}
                {item.ephemeral && <span className="pill">ephemeral</span>}
              </div>
              <div className="muted">agent_id: {item.agent_id}</div>
              {item.source_key && <div className="muted">source_key: {item.source_key}</div>}
              {item.source_path && item.source_path !== item.source_key && (
                <div className="muted">source_path: {item.source_path}</div>
              )}
              {item.runtime_instance_id && <div className="muted">runtime_instance: {item.runtime_instance_id}</div>}
              {item.role_label && <div className="muted">role: {item.role_label}</div>}
              {(item.template_id || item.provider || item.model) && (
                <div className="muted">
                  template: {item.template_id || '-'} | provider: {item.provider || '-'} | model: {item.model || '-'}
                </div>
              )}
              {item.context_pack_id && <div className="muted">context pack: {item.context_pack_id}</div>}
              {item.attached_skills && item.attached_skills.length > 0 && (
                <div className="runStudioList" style={{ marginTop: 6 }}>
                  {item.attached_skills.slice(0, 6).map((skill) => (
                    <div key={skill.skill_id} className="runStudioInlineSubItem">
                      <div className="row" style={{ marginBottom: 4 }}>
                        <span className="pill">{skill.skill_name || skill.skill_id}</span>
                        <span className="pill">load: {skill.load_level || 'metadata_only'}</span>
                        {skill.selected_by && <span className="pill">by: {skill.selected_by}</span>}
                        {skill.status && <span className="pill">{skill.status}</span>}
                      </div>
                      {skill.selection_reason && <div className="muted">{skill.selection_reason}</div>}
                    </div>
                  ))}
                </div>
              )}
              {item.description && <div className="muted">{item.description}</div>}
              {item.capability_tags && item.capability_tags.length > 0 && (
                <div className="runStudioMetaRow">
                  {item.capability_tags.slice(0, 5).map((tag) => (
                    <span key={tag} className="pill">{tag}</span>
                  ))}
                </div>
              )}
              {item.responsibilities && item.responsibilities.length > 0 && (
                <div className="runStudioMetaRow">
                  {item.responsibilities.slice(0, 4).map((role) => (
                    <span key={role} className="pill">{role}</span>
                  ))}
                </div>
              )}
            </article>
          )
        })}
      </div>
    </section>
  )
}
