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

function formatTime(value?: string | null): string {
  const cleanValue = clean(value, '')
  if (!cleanValue) return ''
  const parsed = new Date(cleanValue)
  if (Number.isNaN(parsed.getTime())) return cleanValue
  return parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function AgentActivityPanel({ threadId, runId, summary }: Props) {
  const [detail, setDetail] = useState<any | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const overview = detail?.summary || summary?.agent_activity_summary || {}
  const items = Array.isArray(detail?.items) ? detail.items : (summary?.agent_activity_summary?.recent || [])

  const load = async () => {
    const cleanThread = (threadId || '').trim()
    if (!cleanThread) return
    setLoading(true)
    setError('')
    try {
      setDetail(await api.agentActivity(cleanThread, runId || undefined, 80))
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
          <h3>Agent Activity</h3>
          <div className="muted">Agent starts, handoffs, reviews, and policy events synced from ddalggak.</div>
        </div>
        <button onClick={load} disabled={loading || !threadId}>{loading ? 'Loading...' : 'Load detail'}</button>
      </div>
      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
        <span className="pill">events: {overview.event_count ?? 0}</span>
        <span className="pill">activity: {overview.by_kind?.activity ?? 0}</span>
        <span className="pill">handoff: {overview.by_kind?.handoff ?? 0}</span>
        <span className="pill">policy: {overview.by_kind?.policy ?? 0}</span>
      </div>
      {error && <div className="runStudioWarning">{error}</div>}
      {items.length ? (
        <div className="runStudioQuickList">
          {items.slice(0, 8).map((item: any, index: number) => (
            <div key={item.id || `${item.event_kind}-${index}`} className="runStudioQuickListItem">
              <div className="runStudioQuickListHeader">
                <span className="runStudioQuickListTitle">{clean(item.event_type || item.event_kind)}</span>
                <span className="muted">{formatTime(item.created_at)}</span>
              </div>
              <div className="muted">
                {item.from_agent || item.to_agent ? `${clean(item.from_agent, '?')} → ${clean(item.to_agent, '?')}: ` : ''}
                {clean(item.summary, 'No summary')}
              </div>
              <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
                {item.agent_id || item.role_id ? <span className="pill">agent: {clean(item.agent_id || item.role_id)}</span> : null}
                {item.provider || item.model ? <span className="pill">model: {[item.provider, item.model].filter(Boolean).join(' · ')}</span> : null}
                <span className="pill">{clean(item.event_kind)}</span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="muted">No agent activity has been synced yet.</div>
      )}
    </section>
  )
}
