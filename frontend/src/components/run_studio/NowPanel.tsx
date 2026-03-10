import React from 'react'
import { type RunStudioAgentTeam, type RunStudioSummary } from './types'

type Props = {
  summary: RunStudioSummary | null
  team?: RunStudioAgentTeam | null
}

function statusClass(status: string): string {
  const clean = status.trim().toLowerCase()
  if (clean === 'running') return 'runStudioStatus--running'
  if (clean === 'queued') return 'runStudioStatus--queued'
  if (clean === 'blocked' || clean === 'error') return 'runStudioStatus--blocked'
  if (clean === 'done') return 'runStudioStatus--done'
  return 'runStudioStatus--idle'
}

export default function NowPanel({ summary, team }: Props) {
  const now = summary?.now
  const task = now?.task
  const state = now?.state
  const status = String(state?.run_status || 'idle')
  const blocked = Boolean(state?.blocked)
  const pendingApproval = Boolean(state?.pending_approval)
  const stepStatusCounts = state?.step_status_counts || {}
  const stepCount = Object.values(stepStatusCounts).reduce((acc, value) => acc + Number(value || 0), 0)
  const teamItems = team?.items || []
  const runtimeTeamCount = teamItems.filter((item) => String(item.source || '') === 'runtime_snapshot').length

  let executionHint = 'No execution step detected yet'
  if (pendingApproval) {
    executionHint = 'Waiting for approval before execution continues'
  } else if (stepCount === 0 && runtimeTeamCount > 0) {
    executionHint = 'Team updated, but no execution step detected yet'
  } else if (stepCount === 0 && teamItems.length > 0) {
    executionHint = 'Thread team configured, but no execution step detected yet'
  } else if (status === 'running' || status === 'queued') {
    executionHint = 'Execution started'
  } else if (status === 'done' && stepCount > 0) {
    executionHint = 'Execution completed'
  } else if (stepCount > 0) {
    executionHint = 'Execution steps detected'
  }

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Now</h3>
        <div className="row" style={{ marginBottom: 0 }}>
          <span className={`pill runStudioStatus ${statusClass(status)}`}>run: {status}</span>
          {blocked && <span className="pill runStudioStatus runStudioStatus--blocked">blocked</span>}
          {pendingApproval && <span className="pill runStudioStatus runStudioStatus--queued">pending approval</span>}
        </div>
      </div>

      <div className="runStudioWarning">
        <b>Team / Execution Hint:</b> {executionHint}
      </div>

      <div className="runStudioNowGrid">
        <div className="runStudioNowItem">
          <div className="muted">Current Task</div>
          <div>{task?.current_task || '-'}</div>
        </div>
        <div className="runStudioNowItem">
          <div className="muted">Current Objective</div>
          <div>{task?.current_objective || '-'}</div>
        </div>
        <div className="runStudioNowItem">
          <div className="muted">Current Step</div>
          <div>{task?.current_step || '-'}</div>
          <div className="muted">status: {task?.current_step_status || 'unknown'}</div>
        </div>
        <div className="runStudioNowItem">
          <div className="muted">Latest User Request</div>
          <div>{task?.latest_user_message_text || '-'}</div>
        </div>
      </div>

      {blocked && (
        <div className="runStudioWarning">
          <b>Blocked:</b> {state?.blocked_reason || 'No blocked reason was provided.'}
        </div>
      )}

      <div className="runStudioMetaRow">
        <span className="pill">active context: {state?.active_context_count ?? 0}</span>
        {Object.entries(stepStatusCounts).map(([key, count]) => (
          <span key={key} className="pill">{key}: {count}</span>
        ))}
      </div>
    </section>
  )
}
