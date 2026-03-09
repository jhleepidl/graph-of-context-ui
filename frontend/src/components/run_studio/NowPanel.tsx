import React from 'react'
import { type RunStudioSummary } from './types'

type Props = {
  summary: RunStudioSummary | null
}

function statusClass(status: string): string {
  const clean = status.trim().toLowerCase()
  if (clean === 'running') return 'runStudioStatus--running'
  if (clean === 'queued') return 'runStudioStatus--queued'
  if (clean === 'blocked' || clean === 'error') return 'runStudioStatus--blocked'
  if (clean === 'done') return 'runStudioStatus--done'
  return 'runStudioStatus--idle'
}

export default function NowPanel({ summary }: Props) {
  const now = summary?.now
  const task = now?.task
  const state = now?.state
  const status = String(state?.run_status || 'idle')
  const blocked = Boolean(state?.blocked)
  const pendingApproval = Boolean(state?.pending_approval)
  const stepStatusCounts = state?.step_status_counts || {}

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
