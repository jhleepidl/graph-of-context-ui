import React from 'react'
import { type RunStudioAgentTeam } from './types'

type Props = {
  team: RunStudioAgentTeam | null
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

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Agent Team</h3>
        <span className="pill">active: {team?.active_count ?? 0}</span>
      </div>

      {items.length === 0 && (
        <div className="muted">No configured conversation team yet. Runtime roles will appear after step execution.</div>
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
                <span className="pill">{source}</span>
                {!item.enabled && <span className="pill">disabled</span>}
                {typeof item.order_index === 'number' && <span className="pill">#{item.order_index + 1}</span>}
                {item.ephemeral && <span className="pill">ephemeral</span>}
              </div>
              <div className="muted">agent_id: {item.agent_id}</div>
              {item.runtime_instance_id && <div className="muted">runtime_instance: {item.runtime_instance_id}</div>}
              {item.role_label && <div className="muted">role: {item.role_label}</div>}
              {(item.template_id || item.provider || item.model) && (
                <div className="muted">
                  template: {item.template_id || '-'} | provider: {item.provider || '-'} | model: {item.model || '-'}
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
