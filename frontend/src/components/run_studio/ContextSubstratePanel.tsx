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

function time(value?: string | null): string {
  const text = clean(value, '')
  if (!text) return ''
  const d = new Date(text)
  return Number.isNaN(d.getTime()) ? text : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function ContextSubstratePanel({ threadId, runId, summary }: Props) {
  const [detail, setDetail] = useState<any | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const fallback = summary?.context_substrate_summary || {}
  const view = detail || null
  const s = view?.summary || fallback || {}
  const operations = Array.isArray(view?.operations) ? view.operations : Array.isArray(fallback?.recent) ? fallback.recent : []

  const load = async () => {
    const cleanThread = (threadId || '').trim()
    if (!cleanThread) return
    setLoading(true)
    setError('')
    try {
      setDetail(await api.contextSubstrate(cleanThread, runId || undefined, 80))
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
          <h3>Context Substrate</h3>
          <div className="muted">MVCC snapshots and append-only context operations that feed Board/RDB/VDB/prompt materializations.</div>
        </div>
        <button onClick={load} disabled={loading || !threadId}>{loading ? 'Loading...' : 'Load substrate'}</button>
      </div>
      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
        <span className="pill">snapshot: {clean(s.latest_snapshot_id || s.snapshot_id || 'ctx_000000')}</span>
        <span className="pill">version: {s.latest_version ?? s.version ?? 0}</span>
        <span className="pill">atoms: {s.atom_count ?? 0}</span>
        <span className="pill">links: {s.link_count ?? 0}</span>
        <span className="pill">ops: {s.operation_count ?? 0}</span>
      </div>
      {error && <div className="runStudioWarning">{error}</div>}
      {operations.length ? (
        <div className="runStudioQuickList">
          {operations.slice(0, 8).map((row: any, index: number) => {
            const op = row.operation || row
            return (
              <div key={`${op.operation_id || op.id || index}`} className="runStudioQuickListItem">
                <div className="runStudioQuickListHeader">
                  <span className="runStudioQuickListTitle">{clean(op.op || row.op || 'operation')}</span>
                  <span className="muted">{time(op.created_at || row.created_at)}</span>
                </div>
                <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
                  <span className="pill">lane: {clean(op.lane || row.lane)}</span>
                  <span className="pill">status: {clean(op.status || row.status)}</span>
                  <span className="pill">mode: {clean(op.commit_mode || row.commit_mode)}</span>
                  <span className="pill">v{op.version ?? row.version ?? 0}</span>
                </div>
                {(op.actor || row.actor) && <div className="muted" style={{ marginTop: 4 }}>actor: {clean(op.actor || row.actor)}</div>}
              </div>
            )
          })}
        </div>
      ) : (
        <div className="muted">No context operations have been synced yet.</div>
      )}
    </section>
  )
}
