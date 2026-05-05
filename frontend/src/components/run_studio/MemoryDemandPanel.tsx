import React from 'react'
import { type MemoryDemandEvent, type RunStudioMemoryDemand } from './types'

type Props = {
  demand: RunStudioMemoryDemand | null
  onLoadDetail?: () => void
  detailLoading?: boolean
  detailLoaded?: boolean
}

function safeStringify(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (value === null || typeof value === 'undefined') return ''
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function cleanText(value: unknown): string {
  return safeStringify(value).trim()
}

function isNonEmptyText(value: string): value is string {
  return value.length > 0
}

function listText(values: unknown, fallback = '—'): string {
  if (!Array.isArray(values) || values.length === 0) return fallback
  return values.map((value) => cleanText(value)).filter(isNonEmptyText).join(', ') || fallback
}

function topCounts(counts?: Record<string, number>, limit = 5): Array<[string, number]> {
  if (!counts || typeof counts !== 'object') return []
  return Object.entries(counts)
    .filter(([key]) => cleanText(key))
    .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0) || a[0].localeCompare(b[0]))
    .slice(0, limit)
}

function eventLabel(event: MemoryDemandEvent): string {
  return cleanText(event.agent_id || event.role_id || event.reason || 'preflight')
}

function matchingStrategy(event: MemoryDemandEvent): string {
  return cleanText(event.matching?.strategy)
}

function formatTime(value?: string | null): string {
  const clean = cleanText(value)
  if (!clean) return ''
  const parsed = new Date(clean)
  if (Number.isNaN(parsed.getTime())) return clean
  return parsed.toLocaleString()
}

export default function MemoryDemandPanel({ demand, onLoadDetail, detailLoading, detailLoaded }: Props) {
  const events = Array.isArray(demand?.events) ? demand?.events || [] : []
  const reasonCounts = topCounts(demand?.reason_counts)
  const sourceCounts = topCounts(demand?.source_counts)
  const retrievalCounts = topCounts(demand?.retrieval_mode_counts)
  const classifierCounts = topCounts(demand?.classifier_counts)
  const sourceTypeCounts = topCounts(demand?.source_type_counts)
  const surfaceCounts = topCounts(demand?.surface_counts)
  const empty = !demand || Boolean(demand.empty) || events.length === 0

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Memory Demand Preflight</h3>
          <div className="muted">Question-derived memory retrieval before an agent claims that prior context is unknown.</div>
        </div>
        {onLoadDetail && !detailLoaded && (
          <button onClick={onLoadDetail} disabled={detailLoading}>{detailLoading ? 'Loading...' : 'Load detail'}</button>
        )}
      </div>

      {!demand ? (
        <div className="muted">No memory demand snapshot has been loaded yet.</div>
      ) : (
        <>
          <div className="runStudioMetaRow" style={{ marginBottom: 10 }}>
            <span className="pill">events: {demand.event_count ?? events.length}</span>
            {demand.run_id && <span className="pill">run: {cleanText(demand.run_id)}</span>}
            {demand.latest_at && <span className="pill">latest: {formatTime(demand.latest_at)}</span>}
            {retrievalCounts.map(([key, count]) => <span className="pill" key={key}>{key}: {count}</span>)}
            {classifierCounts.map(([key, count]) => <span className="pill" key={`clf-${key}`}>classifier {key}: {count}</span>)}
          </div>

          {demand.preflight_semantics?.runtime_contract && (
            <div className="runStudioInfo" style={{ marginBottom: 10 }}>
              {cleanText(demand.preflight_semantics.runtime_contract)}
            </div>
          )}

          {demand.preflight_semantics?.matching_note && (
            <div className="muted" style={{ marginBottom: 10 }}>
              Matching: {cleanText(demand.preflight_semantics.matching_note)}
            </div>
          )}

          {reasonCounts.length > 0 && (
            <div className="runStudioMetaRow" style={{ marginBottom: 10 }}>
              {reasonCounts.map(([key, count]) => <span className="pill" key={key}>{key}: {count}</span>)}
            </div>
          )}

          {sourceTypeCounts.length > 0 && (
            <div className="muted" style={{ marginBottom: 10 }}>
              Source types: {sourceTypeCounts.map(([key, count]) => `${key} (${count})`).join(', ')}
            </div>
          )}

          {surfaceCounts.length > 0 && (
            <div className="muted" style={{ marginBottom: 10 }}>
              Surfaces: {surfaceCounts.map(([key, count]) => `${key} (${count})`).join(', ')}
            </div>
          )}

          {sourceCounts.length > 0 && (
            <div className="muted" style={{ marginBottom: 10 }}>
              Sources: {sourceCounts.map(([key, count]) => `${key} (${count})`).join(', ')}
            </div>
          )}

          {empty ? (
            <div className="muted">No preflight retrieval events recorded yet. The runtime may not have pushed memory demand events for this thread/run.</div>
          ) : (
            <div className="runStudioQuickList">
              {events.slice(0, 8).map((event, index) => (
                <div className="runStudioQuickListItem" key={cleanText(event.id) || `${eventLabel(event)}-${index}`}>
                  <div className="runStudioQuickListHeader">
                    <span className="runStudioQuickListTitle">{eventLabel(event)}</span>
                    <span className="pill">items: {event.item_count ?? 0}</span>
                    {event.retrieval_mode && <span className="pill">{cleanText(event.retrieval_mode)}</span>}
                    {event.classifier && <span className="pill">classifier: {cleanText(event.classifier)}</span>}
                    {typeof event.confidence === 'number' && <span className="pill">conf: {event.confidence.toFixed(2)}</span>}
                  </div>
                  {event.query && <div><b>Query:</b> {cleanText(event.query)}</div>}
                  <div className="muted">demand: {listText(event.demand_reasons)} · source types: {listText(event.source_types)} · surfaces: {listText(event.surface_ids)}</div>
                  <div className="muted">sources: {listText(event.sources)}</div>
                  {event.router_memory_plan && Object.keys(event.router_memory_plan).length > 0 && (
                    <div className="muted">router plan: {cleanText(event.router_memory_plan).slice(0, 260)}</div>
                  )}
                  {matchingStrategy(event) && <div className="muted">strategy: {matchingStrategy(event)}</div>}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  )
}
