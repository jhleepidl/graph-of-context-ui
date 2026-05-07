import React, { useEffect, useState } from 'react'
import { applyThreadWatchTaskAction, listThreadWatchTasks } from '../../api'

type WatchTask = {
  id?: string
  contract_id?: string
  workflow_kind?: string
  status?: string
  goal?: string
  current_iteration?: number
  min_iterations?: number
  max_iterations?: number
  required_passes?: string[]
  approval_boundary?: boolean
  stop_conditions?: string[]
  iterations?: Array<Record<string, any>>
}

type Payload = {
  ok?: boolean
  active_task?: WatchTask | null
  tasks?: WatchTask[]
}

type Props = {
  threadId?: string | null
}

function clip(value: unknown, max = 180): string {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  return text.length > max ? `${text.slice(0, max)}…` : text
}

function formatIteration(row: Record<string, any>): string {
  const event = String(row.event || '').trim() || 'event'
  const status = String(row.status || '').trim() || 'recorded'
  const iteration = row.iteration ?? '?'
  const reason = String(row.stop_reason || row.summary || '').trim()
  return `#${iteration} · ${event} · ${status}${reason ? ` · ${clip(reason, 80)}` : ''}`
}

export default function WatchTasksPanel({ threadId }: Props) {
  const [payload, setPayload] = useState<Payload | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [busyAction, setBusyAction] = useState('')

  const load = async () => {
    if (!threadId) return
    setLoading(true)
    setError('')
    try {
      setPayload(await listThreadWatchTasks(threadId, 20))
    } catch (e: any) {
      setError(e?.message || String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [threadId])

  const task = payload?.active_task || null
  const applyAction = async (action: string) => {
    if (!threadId || !task?.id) return
    setBusyAction(action)
    setError('')
    try {
      await applyThreadWatchTaskAction(threadId, task.id, { action, actor: 'goc_ui' })
      await load()
    } catch (e: any) {
      setError(e?.message || String(e))
    } finally {
      setBusyAction('')
    }
  }

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Watch / Loop Tasks</h3>
          <div className="muted">Bounded continuous loops, iteration state, approval pauses, and stop-condition progress.</div>
        </div>
        <div className="row" style={{ marginBottom: 0 }}>
          <button onClick={load} disabled={!threadId || loading}>{loading ? 'Loading...' : 'Refresh'}</button>
        </div>
      </div>
      {!threadId && <div className="muted">Open a thread to inspect watch tasks.</div>}
      {error && <div className="runStudioWarning">{error}</div>}
      {threadId && !loading && !task && <div className="muted">No active watch task recorded yet.</div>}
      {task && (
        <div>
          <div className="runStudioMetaRow">
            <span className="pill">{task.status || 'unknown'}</span>
            <span className="pill">{task.workflow_kind || 'workflow'}</span>
            <span className="pill">iteration {task.current_iteration ?? 0}/{task.max_iterations ?? '?'}</span>
            {task.approval_boundary && <span className="pill">approval boundary</span>}
          </div>
          <p style={{ marginTop: 8 }}>{clip(task.goal, 260) || 'No goal summary recorded.'}</p>
          <div className="muted">Required passes: {(task.required_passes || []).join(' → ') || '(none)'}</div>
          <div className="muted">Stop conditions: {(task.stop_conditions || []).join(', ') || '(none)'}</div>
          <div className="row" style={{ marginTop: 10 }}>
            <button onClick={() => applyAction('pause')} disabled={!!busyAction || task.status === 'paused'}>{busyAction === 'pause' ? 'Pausing...' : 'Pause'}</button>
            <button onClick={() => applyAction('resume')} disabled={!!busyAction || task.status === 'active'}>{busyAction === 'resume' ? 'Resuming...' : 'Resume'}</button>
            <button onClick={() => applyAction('stop')} disabled={!!busyAction || task.status === 'stopped'}>{busyAction === 'stop' ? 'Stopping...' : 'Stop'}</button>
          </div>
          <div style={{ marginTop: 12 }}>
            <b>Recent iterations</b>
            {(task.iterations || []).length === 0 ? (
              <div className="muted">No iterations recorded yet.</div>
            ) : (
              <ul>
                {(task.iterations || []).slice(-8).reverse().map((row, idx) => (
                  <li key={`${row.id || idx}`}>{formatIteration(row)}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
