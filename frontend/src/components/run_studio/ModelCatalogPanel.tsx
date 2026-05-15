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

export default function ModelCatalogPanel({ threadId, runId, summary }: Props) {
  const [nodes, setNodes] = useState<any | null>(null)
  const [usage, setUsage] = useState<any | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const overview = summary?.model_catalog_summary || {}
  const nodeItems = Array.isArray(nodes?.items) ? nodes.items : (overview.recent_nodes || [])
  const usageSummary = usage?.summary || overview

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [nextNodes, nextUsage] = await Promise.all([
        api.modelNodes(undefined, 100),
        api.modelUsage(threadId || undefined, runId || undefined, 100),
      ])
      setNodes(nextNodes)
      setUsage(nextUsage)
    } catch (e: any) {
      setError(e?.message || String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setNodes(null)
    setUsage(null)
    setError('')
  }, [threadId, runId])

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Model Catalog</h3>
          <div className="muted">Available model nodes and recent token usage used for routing agent roles.</div>
        </div>
        <button onClick={load} disabled={loading}>{loading ? 'Loading...' : 'Load catalog'}</button>
      </div>
      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
        <span className="pill">nodes: {overview.node_count ?? nodes?.summary?.node_count ?? 0}</span>
        <span className="pill">private context: {overview.private_context_allowed_count ?? nodes?.summary?.private_context_allowed_count ?? 0}</span>
        <span className="pill">usage events: {usageSummary.usage_event_count ?? usageSummary.event_count ?? 0}</span>
        <span className="pill">tokens: {usageSummary.total_tokens ?? 0}</span>
      </div>
      {error && <div className="runStudioWarning">{error}</div>}
      {nodeItems.length ? (
        <div className="runStudioQuickList">
          {nodeItems.slice(0, 8).map((item: any, index: number) => (
            <div key={item.node_id || index} className="runStudioQuickListItem">
              <div className="runStudioQuickListHeader">
                <span className="runStudioQuickListTitle">{clean(item.model || item.node_id)}</span>
                <span className="muted">{clean(item.provider)}</span>
              </div>
              <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
                <span className="pill">cost: {clean(item.cost_tier)}</span>
                <span className="pill">latency: {clean(item.latency_tier)}</span>
                <span className="pill">quality: {clean(item.quality_tier)}</span>
                <span className="pill">privacy: {clean(item.privacy_tier)}</span>
                {item.allow_private_context ? <span className="pill">private context ok</span> : null}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="muted">No model catalog has been synced yet. ddalggak can refresh Gemini/Codex daily and discover Ollama nodes.</div>
      )}
    </section>
  )
}
