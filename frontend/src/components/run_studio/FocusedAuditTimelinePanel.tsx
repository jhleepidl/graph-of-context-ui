import React from 'react'
import { type RunStudioAuditTimeline, type RunStudioAuditTimelineEvent } from './types'

type Props = {
  auditTimeline: RunStudioAuditTimeline | null
  onFocusNode?: (nodeId: string) => void
  onOpenNode?: (nodeId: string) => void
  onFocusTrace?: (nodeIds: string[]) => void
  onOpenTrace?: (nodeIds: string[]) => void
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : String(value || '').trim()
}

function uniqueIds(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  values.forEach((value) => {
    const clean = cleanText(value)
    if (!clean || seen.has(clean)) return
    seen.add(clean)
    out.push(clean)
  })
  return out
}

function formatTimestamp(value?: string | null): string {
  const clean = cleanText(value)
  if (!clean) return 'unknown time'
  const parsed = new Date(clean)
  if (Number.isNaN(parsed.getTime())) return clean
  return parsed.toLocaleString()
}

function eventTitle(event: RunStudioAuditTimelineEvent): string {
  return cleanText(event.title || event.category || 'timeline event')
}

function renderMetadata(metadata: Record<string, unknown> | null | undefined) {
  if (!metadata) return null
  const entries = Object.entries(metadata).filter(([, value]) => {
    if (value == null) return false
    if (Array.isArray(value)) return value.length > 0
    if (typeof value === 'string') return cleanText(value).length > 0
    return true
  }).slice(0, 4)
  if (!entries.length) return null
  return (
    <div className="muted" style={{ marginTop: 8 }}>
      {entries.map(([key, value], index) => {
        const rendered = Array.isArray(value) ? value.map((item) => cleanText(item)).filter(Boolean).join(', ') : cleanText(value)
        if (!rendered) return null
        return <div key={`${key}-${index}`}>{key}: {rendered}</div>
      })}
    </div>
  )
}

export default function FocusedAuditTimelinePanel({ auditTimeline, onFocusNode, onOpenNode, onFocusTrace, onOpenTrace }: Props) {
  const items = auditTimeline?.items || []
  const categoryCounts = auditTimeline?.category_counts || {}
  const statusCounts = auditTimeline?.status_counts || {}

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Unified Audit Timeline</h3>
          <div className="muted">Chronological view across selection, execution trace, evidence, memory projection, memory edges, and conflict resolution.</div>
        </div>
      </div>

      {!auditTimeline && <div className="muted">Focused run bundle has not been loaded yet.</div>}

      {auditTimeline && (
        <>
          <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
            <span className="pill">events: {auditTimeline.count ?? items.length}</span>
            {auditTimeline.selection_event_id && <span className="pill">selection event: {auditTimeline.selection_event_id}</span>}
            {auditTimeline.anchor_node_id && <span className="pill">anchor: {auditTimeline.anchor_node_id}</span>}
            {auditTimeline.started_at && <span className="pill">start: {formatTimestamp(auditTimeline.started_at)}</span>}
            {auditTimeline.ended_at && <span className="pill">end: {formatTimestamp(auditTimeline.ended_at)}</span>}
          </div>

          <div className="runStudioMetaRow" style={{ marginBottom: 10 }}>
            {Object.entries(categoryCounts).map(([key, count]) => <span key={key} className="pill">{key}: {count}</span>)}
            {Object.entries(statusCounts).slice(0, 6).map(([key, count]) => <span key={`status-${key}`} className="pill">{key}: {count}</span>)}
          </div>

          {items.length === 0 ? (
            <div className="muted">No timeline events were materialized for this run yet.</div>
          ) : (
            <div style={{ display: 'grid', gap: 10 }}>
              {items.map((event, index) => {
                const primaryNodeId = cleanText(event.primary_node_id)
                const traceNodeIds = uniqueIds(event.trace_node_ids || event.related_node_ids || [])
                const relatedNodeIds = uniqueIds(event.related_node_ids || [])
                const badges = (event.badges || []).map((badge) => cleanText(badge)).filter(Boolean)
                const rationaleCodes = (event.rationale_codes || []).map((code) => cleanText(code)).filter(Boolean)
                return (
                  <article key={cleanText(event.event_id) || `timeline-${index}`} className="runStudioAgentCard">
                    <div className="runStudioAgentCardHeader">
                      <div>
                        <div className="runStudioAgentCardTitle">{eventTitle(event)}</div>
                        <div className="muted">{formatTimestamp(event.timestamp)}</div>
                      </div>
                      <div className="runStudioMetaRow">
                        {event.category && <span className="pill">{cleanText(event.category)}</span>}
                        {event.status && <span className="pill">status: {cleanText(event.status)}</span>}
                        {event.trace_anchor_related && <span className="pill">anchor-related</span>}
                      </div>
                    </div>

                    {cleanText(event.summary) && <div className="muted" style={{ marginBottom: 8 }}>{cleanText(event.summary)}</div>}

                    {(badges.length > 0 || rationaleCodes.length > 0) && (
                      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                        {badges.map((badge) => <span key={badge} className="pill">{badge}</span>)}
                        {rationaleCodes.map((code) => <span key={`r-${code}`} className="pill">reason: {code}</span>)}
                      </div>
                    )}

                    <div className="row">
                      {primaryNodeId && onFocusNode && <button className="tiny" onClick={() => onFocusNode(primaryNodeId)}>Focus primary node</button>}
                      {primaryNodeId && onOpenNode && <button className="tiny" onClick={() => onOpenNode(primaryNodeId)}>Open node</button>}
                      {traceNodeIds.length > 1 && onFocusTrace && <button className="tiny" onClick={() => onFocusTrace(traceNodeIds)}>Focus related trace</button>}
                      {traceNodeIds.length > 1 && onOpenTrace && <button className="tiny" onClick={() => onOpenTrace(traceNodeIds)}>Open related trace</button>}
                    </div>

                    {relatedNodeIds.length > 0 && <div className="muted" style={{ marginTop: 8 }}>related nodes: {relatedNodeIds.join(', ')}</div>}
                    {renderMetadata(event.metadata || null)}
                  </article>
                )
              })}
            </div>
          )}
        </>
      )}
    </section>
  )
}
