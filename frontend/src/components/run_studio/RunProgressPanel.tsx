import React, { useMemo } from 'react'
import type { RunStudioAuditTimeline, RunStudioSummary } from './types'

function cleanText(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

function statusClass(status: string): string {
  const clean = status.toLowerCase()
  if (clean === 'done' || clean === 'completed' || clean === 'ok' || clean === 'success') return 'runStudioStatus--done'
  if (clean === 'running' || clean === 'active' || clean === 'in_progress') return 'runStudioStatus--running'
  if (clean === 'queued' || clean === 'pending' || clean === 'waiting') return 'runStudioStatus--queued'
  if (clean === 'blocked' || clean === 'error' || clean === 'failed') return 'runStudioStatus--blocked'
  return 'runStudioStatus--idle'
}

function formatWhen(value: string): string {
  if (!value) return '-'
  const ts = Date.parse(value)
  if (!Number.isFinite(ts)) return value
  return new Date(ts).toLocaleString()
}

function friendlyLane(raw: unknown): string {
  const lane = cleanText(raw).toLowerCase()
  if (lane === 'fast') return 'fast lane'
  if (lane === 'work') return 'work lane'
  if (lane === 'deep') return 'deep lane'
  return cleanText(raw) || '-'
}

type PhaseState = 'done' | 'active' | 'upcoming'

type Props = {
  summary: RunStudioSummary | null
  auditTimeline: RunStudioAuditTimeline | null
}

export default function RunProgressPanel({ summary, auditTimeline }: Props) {
  const now = summary?.now
  const task = now?.task
  const state = now?.state
  const projections = summary?.projections?.execution
  const status = cleanText(state?.current_run_status || state?.run_status || summary?.current_run_skills?.task_interpretation?.status || 'idle') || 'idle'
  const currentRunId = cleanText(state?.current_run_id || summary?.current_run_skills?.run_id)
  const executionLane = cleanText(auditTimeline?.linked_summary?.execution_lane || summary?.current_run_skills?.task_interpretation?.execution_lane || summary?.current_run_skills?.task_interpretation?.executionLane)
  const currentStep = cleanText(task?.current_step || projections?.current_step?.goal)
  const currentStepStatus = cleanText(task?.current_step_status || projections?.current_step?.status || status)
  const latestRequest = cleanText(task?.latest_user_message_text || summary?.projections?.conversation?.recent_messages?.[0]?.text)
  const counts = state?.current_run_step_status_counts || state?.step_status_counts || {}
  const doneCount = Number((counts as Record<string, number>)['done'] || (counts as Record<string, number>)['completed'] || (counts as Record<string, number>)['success'] || 0)
  const runningCount = Number((counts as Record<string, number>)['running'] || (counts as Record<string, number>)['active'] || (counts as Record<string, number>)['in_progress'] || 0)
  const queuedCount = Number((counts as Record<string, number>)['queued'] || (counts as Record<string, number>)['pending'] || 0)
  const totalSteps = Math.max(Number(state?.current_run_step_count || 0), doneCount + runningCount + queuedCount)
  const progressPct = useMemo(() => {
    if (status === 'done') return 100
    if (totalSteps > 0) return Math.max(5, Math.min(95, Math.round((doneCount / totalSteps) * 100)))
    if (status === 'running') return 55
    if (status === 'queued') return 20
    return 0
  }, [doneCount, status, totalSteps])
  const pendingApproval = Boolean(state?.current_pending_approval || state?.pending_approval)
  const blocked = Boolean(state?.current_blocked || state?.blocked)
  const reviewActive = pendingApproval || blocked
  const planningReady = Boolean(currentRunId || summary?.current_run_skills?.task_interpretation || summary?.current_run_skills?.runtime_agents?.length)
  const executeStarted = totalSteps > 0 || status === 'running' || status === 'done' || status === 'queued'
  const phases: Array<{ label: string; state: PhaseState; helper: string }> = [
    { label: 'Request', state: latestRequest ? 'done' : 'active', helper: latestRequest ? 'user goal captured' : 'waiting for request context' },
    { label: 'Plan', state: planningReady ? (executeStarted ? 'done' : 'active') : 'upcoming', helper: planningReady ? 'team / skill routing resolved' : 'planning not materialized yet' },
    { label: 'Execute', state: executeStarted ? (status === 'done' ? 'done' : 'active') : 'upcoming', helper: currentStep || 'no execution step yet' },
    { label: 'Review', state: reviewActive ? 'active' : (status === 'done' ? 'done' : 'upcoming'), helper: blocked ? 'blocked by gate' : pendingApproval ? 'awaiting approval' : (status === 'done' ? 'finalized' : 'not reached') },
  ]
  const recentEvents = (auditTimeline?.items || []).slice(0, 4).map((row) => ({
    id: cleanText((row as any)?.event_id || (row as any)?.id),
    title: cleanText((row as any)?.title || (row as any)?.label || (row as any)?.category || 'event'),
    status: cleanText((row as any)?.status || ''),
    at: cleanText((row as any)?.created_at || (row as any)?.timestamp || ''),
  }))

  return (
    <section className="card runStudioPanel runProgressPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Progress Overview</h3>
          <div className="muted">A simpler view of what the system is doing now, what was finished, and what still blocks completion.</div>
        </div>
        <div className="row" style={{ marginBottom: 0 }}>
          <span className={`pill runStudioStatus ${statusClass(status)}`}>run: {status}</span>
          {executionLane && <span className="pill">lane: {friendlyLane(executionLane)}</span>}
          {currentRunId && <span className="pill">run id: {currentRunId.slice(0, 8)}</span>}
        </div>
      </div>

      <div className="progressMeter">
        <div className="progressMeterBar"><div className="progressMeterFill" style={{ width: `${progressPct}%` }} /></div>
        <div className="muted">{progressPct}% · done {doneCount} / total {totalSteps || 0} · running {runningCount} · queued {queuedCount}{executionLane ? ` · ${friendlyLane(executionLane)}` : ''}</div>
      </div>

      <div className="phaseRail">
        {phases.map((phase, index) => (
          <div key={phase.label} className={`phaseItem phaseItem--${phase.state}`}>
            <div className="phaseIndex">{index + 1}</div>
            <div>
              <div><b>{phase.label}</b></div>
              <div className="muted">{phase.helper}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="runProgressGrid">
        <div className="runProgressCard">
          <div className="muted">Latest user request</div>
          <div>{latestRequest || '-'}</div>
        </div>
        <div className="runProgressCard">
          <div className="muted">Current step</div>
          <div>{currentStep || '-'}</div>
          <div className="muted">status: {currentStepStatus || 'unknown'}</div>
        </div>
        <div className="runProgressCard">
          <div className="muted">Next gate</div>
          <div>{blocked ? 'Resolve blocker' : pendingApproval ? 'Approval required' : status === 'done' ? 'Completed' : 'Continue execution'}</div>
        </div>
        <div className="runProgressCard">
          <div className="muted">Recent activity</div>
          {recentEvents.length > 0 ? recentEvents.map((event) => (
            <div key={`${event.id}:${event.at}`} style={{ marginBottom: 6 }}>
              <div><b>{event.title}</b>{event.status ? ` · ${event.status}` : ''}</div>
              <div className="muted">{formatWhen(event.at)}</div>
            </div>
          )) : <div>-</div>}
        </div>
      </div>
    </section>
  )
}
