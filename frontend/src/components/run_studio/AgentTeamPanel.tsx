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
          return (
            <article key={`${item.agent_id}:${index}`} className="runStudioListItem">
              <div className="row" style={{ marginBottom: 6 }}>
                <b>{item.name || item.agent_id}</b>
                <span className={`pill runStudioStatus ${runtimeClass(status)}`}>{status}</span>
                {!item.enabled && <span className="pill">disabled</span>}
                {typeof item.order_index === 'number' && <span className="pill">#{item.order_index + 1}</span>}
              </div>
              <div className="muted">agent_id: {item.agent_id}</div>
              {item.description && <div className="muted">{item.description}</div>}
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
