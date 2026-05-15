import React, { useEffect, useState } from 'react'
import { api } from '../../api'

type Props = {
  threadId?: string | null
  runId?: string | null
  summary?: any | null
}

function clean(value: unknown, fallback = '—'): string {
  const text = typeof value === 'string' ? value.trim() : String(value || '').trim()
  return text || fallback
}

function num(value: unknown): string {
  const n = Number(value || 0)
  if (!Number.isFinite(n)) return '0'
  if (Math.abs(n) >= 1000) return n.toLocaleString()
  return String(Math.round(n * 100) / 100)
}

function percent(value: unknown): string {
  const n = Number(value || 0)
  if (!Number.isFinite(n)) return '0%'
  return `${Math.round(n * 100)}%`
}

function time(value?: string | null): string {
  const text = clean(value, '')
  if (!text) return ''
  const d = new Date(text)
  return Number.isNaN(d.getTime()) ? text : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function MiniMetric({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="runStudioMetricTile">
      <div className="runStudioMetricValue">{value}</div>
      <div className="runStudioMetricLabel">{label}</div>
      {hint && <div className="muted" style={{ marginTop: 2 }}>{hint}</div>}
    </div>
  )
}

export default function ContextRuntimePanel({ threadId, runId, summary }: Props) {
  const [detail, setDetail] = useState<any | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const fallback = summary?.context_runtime_summary || {}
  const view = detail || null
  const s = view?.summary || fallback || {}
  const projections = Array.isArray(view?.projections) ? view.projections : Array.isArray(fallback?.recent_projections) ? fallback.recent_projections : []
  const handoffs = Array.isArray(view?.handoffs) ? view.handoffs : Array.isArray(fallback?.recent_handoffs) ? fallback.recent_handoffs : []
  const writes = Array.isArray(view?.write_metrics) ? view.write_metrics : []

  const load = async () => {
    const cleanThread = (threadId || '').trim()
    if (!cleanThread) return
    setLoading(true)
    setError('')
    try {
      setDetail(await api.contextRuntime(cleanThread, runId || undefined, 120))
    } catch (e: any) {
      setError(e?.message || String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setDetail(null)
    setError('')
  }, [threadId, runId])

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Context Runtime</h3>
          <div className="muted">Compiled projections, typed handoff deltas, and batched writeback metrics from ddalggak.</div>
        </div>
        <button onClick={load} disabled={loading || !threadId}>{loading ? 'Loading...' : 'Load runtime'}</button>
      </div>

      <div className="runStudioMetricGrid runStudioMetricGrid--compact" style={{ marginBottom: 10 }}>
        <MiniMetric label="projections" value={num(s.projection_count)} />
        <MiniMetric label="cache hit" value={percent(s.projection_cache_hit_rate)} />
        <MiniMetric label="avg compile" value={`${num(s.avg_compile_ms)}ms`} />
        <MiniMetric label="avg ctx tokens" value={num(s.avg_context_tokens)} />
        <MiniMetric label="handoffs" value={num(s.handoff_count)} />
        <MiniMetric label="writes" value={num(s.committed_writes || s.write_batch_count)} hint={s.proposal_writes || s.conflict_writes ? `${num(s.proposal_writes)} proposals · ${num(s.conflict_writes)} conflicts` : undefined} />
      </div>

      {error && <div className="runStudioWarning">{error}</div>}

      <div className="runStudioGrid runStudioGrid--bottom">
        <div className="runStudioQuickList">
          <div className="runStudioQuickListHeader" style={{ marginBottom: 6 }}>
            <span className="runStudioQuickListTitle">Recent projections</span>
            <span className="muted">snapshot → prompt</span>
          </div>
          {projections.length ? projections.slice(0, 5).map((row: any, index: number) => (
            <div key={`${row.projection_id || index}`} className="runStudioQuickListItem">
              <div className="runStudioQuickListHeader">
                <span className="runStudioQuickListTitle">{clean(row.role_id || row.role || row.agent_id || 'agent')} · {clean(row.task_type, 'task')}</span>
                <span className="muted">{time(row.created_at)}</span>
              </div>
              <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
                <span className="pill">{clean(row.snapshot_id || 'ctx')}</span>
                <span className="pill">{row.cache_hit ? 'cache hit' : 'compiled'}</span>
                <span className="pill">{num(row.compile_ms)}ms</span>
                <span className="pill">{num(row.context_tokens)} tok</span>
                <span className="pill">atoms {num(row.selected_atom_count)}</span>
              </div>
              {row.model_node && <div className="muted" style={{ marginTop: 4 }}>model: {clean(row.model_node)}</div>}
            </div>
          )) : <div className="muted">No projection events have been synced yet.</div>}
        </div>

        <div className="runStudioQuickList">
          <div className="runStudioQuickListHeader" style={{ marginBottom: 6 }}>
            <span className="runStudioQuickListTitle">Typed handoffs</span>
            <span className="muted">agent delta</span>
          </div>
          {handoffs.length ? handoffs.slice(0, 5).map((row: any, index: number) => (
            <div key={`${row.handoff_id || index}`} className="runStudioQuickListItem">
              <div className="runStudioQuickListHeader">
                <span className="runStudioQuickListTitle">{clean(row.from_agent || 'agent')} → {clean(row.to_agent || 'next')}</span>
                <span className="muted">{time(row.created_at)}</span>
              </div>
              <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
                <span className="pill">{clean(row.handoff_type || 'delta')}</span>
                <span className="pill">{num(row.delta_tokens)} tok</span>
                {row.snapshot_id && <span className="pill">{clean(row.snapshot_id)}</span>}
              </div>
              {row.summary && <div className="muted" style={{ marginTop: 4 }}>{clean(row.summary)}</div>}
            </div>
          )) : <div className="muted">No typed handoff deltas have been synced yet.</div>}
        </div>
      </div>

      {writes.length > 0 && (
        <div className="runStudioQuickList" style={{ marginTop: 10 }}>
          <div className="runStudioQuickListHeader" style={{ marginBottom: 6 }}>
            <span className="runStudioQuickListTitle">Batched writeback</span>
            <span className="muted">intent → operation/proposal</span>
          </div>
          {writes.slice(0, 4).map((row: any, index: number) => (
            <div key={`${row.event_id || index}`} className="runStudioQuickListItem">
              <div className="runStudioMetaRow">
                <span className="pill">batch {num(row.batch_size)}</span>
                <span className="pill">committed {num(row.committed)}</span>
                <span className="pill">proposals {num(row.proposals)}</span>
                <span className="pill">conflicts {num(row.conflicts)}</span>
                <span className="pill">append {num(row.operation_append_ms)}ms</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
