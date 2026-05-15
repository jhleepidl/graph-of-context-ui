import React, { useEffect, useState } from 'react'
import { api } from '../../api'

type Props = {
  threadId?: string | null
  summary?: any | null
}

function clean(value: unknown, fallback = '—'): string {
  const text = typeof value === 'string' ? value.trim() : String(value || '').trim()
  return text || fallback
}

export default function AgentPackagesPanel({ threadId, summary }: Props) {
  const [detail, setDetail] = useState<any | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const overview = detail?.summary || summary?.agent_package_summary || {}
  const items = Array.isArray(detail?.items) ? detail.items : (summary?.agent_package_summary?.recent || [])

  const load = async () => {
    const cleanThread = (threadId || '').trim()
    if (!cleanThread) return
    setLoading(true)
    setError('')
    try {
      setDetail(await api.agentPackages(cleanThread, 80))
    } catch (e: any) {
      setError(e?.message || String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setDetail(null)
    setError('')
  }, [threadId])

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Agent Packages</h3>
          <div className="muted">Exported/publish-candidate agent packages. Private memory and credentials should never be copied on clone.</div>
        </div>
        <button onClick={load} disabled={loading || !threadId}>{loading ? 'Loading...' : 'Load packages'}</button>
      </div>
      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
        <span className="pill">packages: {overview.package_count ?? 0}</span>
        <span className="pill">clone-safe: {overview.clone_safe_count ?? 0}</span>
      </div>
      {error && <div className="runStudioWarning">{error}</div>}
      {items.length ? (
        <div className="runStudioQuickList">
          {items.slice(0, 6).map((item: any, index: number) => (
            <div key={item.package_id || index} className="runStudioQuickListItem">
              <div className="runStudioQuickListHeader">
                <span className="runStudioQuickListTitle">{clean(item.title || item.package_id)}</span>
                <span className="muted">{clean(item.status)}</span>
              </div>
              <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
                <span className="pill">agents: {item.agent_count ?? 0}</span>
                <span className="pill">visibility: {clean(item.visibility)}</span>
                <span className="pill">private memory: {item.copies_private_memory ? 'copies' : 'fresh on clone'}</span>
              </div>
              <div className="muted" style={{ marginTop: 6 }}>{clean(item.package_id)}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="muted">No agent package has been synced yet. Use /agents export or /agents publish-candidate in ddalggak.</div>
      )}
    </section>
  )
}
