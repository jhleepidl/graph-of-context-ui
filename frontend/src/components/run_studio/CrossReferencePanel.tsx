import React from 'react'
import { api } from '../../api'
import { type RunStudioCrossReferences, type ConflictHistoryEvent } from './types'

type Props = {
  crossReferences: RunStudioCrossReferences | null
  onFocusNode?: (nodeId: string) => void
  onOpenNode?: (nodeId: string) => void
  onFocusTrace?: (nodeIds: string[]) => void
  onOpenTrace?: (nodeIds: string[]) => void
  onRefresh?: () => void
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : String(value || '').trim()
}

function uniqueNodeIds(values: Array<string | null | undefined>): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  values.forEach((value) => {
    const clean = cleanText(value)
    if (!clean || seen.has(clean)) return
    seen.add(clean)
    out.push(clean)
  })
  return out
}

async function resolveWithSuggestedBasis(item: NonNullable<RunStudioCrossReferences['conflict_links']>[number], onRefresh?: () => void) {
  const conflictId = cleanText(item.conflict_id)
  const suggested = item.suggested_resolution || null
  const winner = cleanText(item.winning_node_id || suggested?.winning_node_id)
  const loserIds = uniqueNodeIds([
    ...(item.losing_node_ids || []),
    ...(suggested?.losing_node_ids || []),
  ]).filter((nodeId) => nodeId && nodeId !== winner)
  if (!conflictId || !winner) return
  await api.resolveMemoryConflict(conflictId, {
    status: 'resolved',
    winning_node_id: winner || null,
    losing_node_ids: loserIds,
    summary: cleanText(item.resolution_summary || suggested?.summary) || 'Resolved from cross-reference panel',
    rationale_codes: uniqueNodeIds([
      ...(item.resolution_rationale_codes || []),
      ...(suggested?.rationale_codes || []),
    ]),
    supporting_claim_node_ids: uniqueNodeIds([
      ...(item.supporting_claim_node_ids || []),
      ...(suggested?.supporting_claim_node_ids || []),
    ]),
    supporting_evidence_node_ids: uniqueNodeIds([
      ...(item.supporting_evidence_node_ids || []),
      ...(suggested?.supporting_evidence_node_ids || []),
    ]),
    supporting_memory_node_ids: uniqueNodeIds([
      ...(item.supporting_memory_node_ids || []),
      ...(suggested?.supporting_memory_node_ids || []),
    ]),
    resolved_by: 'operator',
    resolution_source: 'cross_reference_panel',
    merge_note: 'Resolved from the cross-reference panel using the suggested basis',
  })
  onRefresh?.()
}



function renderTimelineEvents(events: ConflictHistoryEvent[] | undefined, title: string) {
  const items = Array.isArray(events) ? events.filter(Boolean).slice(-3).reverse() : []
  if (!items.length) return null
  return (
    <div style={{ marginTop: 8 }}>
      <div className="runStudioExecutionLaneTitle" style={{ marginBottom: 6 }}>{title}</div>
      <div style={{ display: 'grid', gap: 8 }}>
        {items.map((event, index) => (
          <div key={`${cleanText(event.created_at || event.event_type || 'evt')}-${index}`} className="runStudioInlineList">
            <div className="runStudioMetaRow" style={{ marginBottom: 4 }}>
              {event.event_type && <span className="pill">{cleanText(event.event_type)}</span>}
              {event.status && <span className="pill">status: {cleanText(event.status)}</span>}
              {event.actor && <span className="pill">actor: {cleanText(event.actor)}</span>}
              {event.created_at && <span className="pill">{cleanText(event.created_at)}</span>}
            </div>
            {event.summary && <div className="muted">{cleanText(event.summary)}</div>}
            {event.merge_note && <div className="muted">merge note: {cleanText(event.merge_note)}</div>}
          </div>
        ))}
      </div>
    </div>
  )
}
export default function CrossReferencePanel({
  crossReferences,
  onFocusNode,
  onOpenNode,
  onFocusTrace,
  onOpenTrace,
  onRefresh,
}: Props) {
  const claimLinks = crossReferences?.claim_links || []
  const conflictLinks = crossReferences?.conflict_links || []
  const memoryLinks = crossReferences?.memory_links || []
  const counts = crossReferences?.counts || {}
  const anchorNodeId = cleanText(crossReferences?.anchor_node_id)
  const anchorRelated = crossReferences?.anchor_related || null

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Cross-reference Layer</h3>
          <div className="muted">Connects selected evidence claims, memory projections, and memory conflicts inside the focused run.</div>
        </div>
      </div>

      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
        <span className="pill">claim links: {counts.claim_links ?? claimLinks.length}</span>
        <span className="pill">memory links: {counts.memory_links ?? memoryLinks.length}</span>
        <span className="pill">conflict links: {counts.conflict_links ?? conflictLinks.length}</span>
        <span className="pill">claims↔memory: {counts.claims_with_memory_links ?? 0}</span>
        <span className="pill">claims↔conflicts: {counts.claims_with_conflicts ?? 0}</span>
        <span className="pill">rationales: {counts.conflicts_with_resolution_rationale ?? 0}</span>
        <span className="pill">suggested: {counts.conflicts_with_suggested_resolution ?? 0}</span>
        <span className="pill">history: {counts.conflicts_with_history ?? 0}</span>
        <span className="pill">merge timeline: {counts.conflicts_with_merge_history ?? 0}</span>
        {anchorNodeId && <span className="pill">anchor: {anchorNodeId}</span>}
      </div>

      {anchorRelated && (
        <div className="runStudioMetaRow" style={{ marginBottom: 10 }}>
          {(anchorRelated.claim_node_ids || []).length > 0 && <span className="pill">anchor claims: {(anchorRelated.claim_node_ids || []).length}</span>}
          {(anchorRelated.memory_node_ids || []).length > 0 && <span className="pill">anchor memory: {(anchorRelated.memory_node_ids || []).length}</span>}
          {(anchorRelated.conflict_ids || []).length > 0 && <span className="pill">anchor conflicts: {(anchorRelated.conflict_ids || []).length}</span>}
        </div>
      )}

      <div className="runStudioTeamGroupList">
        <section className="runStudioTeamGroup">
          <div className="runStudioTeamGroupHeader">
            <div className="runStudioExecutionLaneTitle">Top claim links</div>
            <div className="muted">{claimLinks.length}</div>
          </div>
          {claimLinks.length === 0 ? (
            <div className="muted">No cross-linked claims were found for this run.</div>
          ) : (
            <div className="runStudioAgentCardGrid">
              {claimLinks.slice(0, 6).map((item) => {
                const compareNodeIds = uniqueNodeIds([
                  item.claim_node_id,
                  ...(item.compare_node_ids || []),
                ])
                return (
                  <article key={item.claim_node_id} className="runStudioAgentCard">
                    <div className="runStudioAgentCardHeader">
                      <div>
                        <div className="runStudioAgentCardTitle">{cleanText(item.claim_node_type || 'Claim')}</div>
                        <div className="muted">{cleanText(item.claim_node_id)}</div>
                      </div>
                      {item.trace_anchor_related && <span className="runStudioStatusChip runStudioStatus--idle">anchor-related</span>}
                    </div>
                    <div className="muted" style={{ marginBottom: 8 }}>{cleanText(item.claim_text || '(no claim text)')}</div>
                    <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                      <span className="pill">memory: {(item.related_memory_node_ids || []).length}</span>
                      <span className="pill">conflicts: {(item.related_conflict_ids || []).length}</span>
                      {(item.related_evidence_node_ids || []).length > 0 && <span className="pill">evidence: {(item.related_evidence_node_ids || []).length}</span>}
                    </div>
                    <div className="row">
                      {onFocusNode && <button className="tiny" onClick={() => onFocusNode(item.claim_node_id)}>Focus claim</button>}
                      {onOpenNode && <button className="tiny" onClick={() => onOpenNode(item.claim_node_id)}>Detail</button>}
                      {compareNodeIds.length > 1 && onFocusTrace && <button className="tiny" onClick={() => onFocusTrace(compareNodeIds)}>Focus linked trace</button>}
                      {compareNodeIds.length > 1 && onOpenTrace && <button className="tiny" onClick={() => onOpenTrace(compareNodeIds)}>Compare linked nodes</button>}
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </section>

        <section className="runStudioTeamGroup">
          <div className="runStudioTeamGroupHeader">
            <div className="runStudioExecutionLaneTitle">Conflict ↔ claim links</div>
            <div className="muted">{conflictLinks.length}</div>
          </div>
          {conflictLinks.length === 0 ? (
            <div className="muted">No linked memory conflicts were found for this run.</div>
          ) : (
            <div className="runStudioAgentCardGrid">
              {conflictLinks.slice(0, 6).map((item) => {
                const compareNodeIds = uniqueNodeIds(item.node_ids || [])
                const suggested = item.suggested_resolution || null
                const rationaleSummary = cleanText(item.resolution_summary || suggested?.summary)
                const rationaleCodes = uniqueNodeIds([
                  ...(item.resolution_rationale_codes || []),
                  ...(suggested?.rationale_codes || []),
                ])
                return (
                  <article key={item.conflict_id} className="runStudioAgentCard">
                    <div className="runStudioAgentCardHeader">
                      <div>
                        <div className="runStudioAgentCardTitle">{cleanText(item.surface_id || 'surface')}</div>
                        <div className="muted">{cleanText(item.conflict_id)}</div>
                      </div>
                      <span className="runStudioStatusChip runStudioStatus--blocked">{cleanText(item.status || 'pending')}</span>
                    </div>
                    <div className="muted" style={{ marginBottom: 8 }}>{cleanText(item.reason || 'memory conflict')}</div>
                    <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                      <span className="pill">claims: {(item.related_claim_node_ids || []).length}</span>
                      <span className="pill">memory nodes: {(item.related_memory_node_ids || []).length}</span>
                      <span className="pill">pair size: {(item.node_ids || []).length}</span>
                      {(item.supporting_evidence_node_ids || suggested?.supporting_evidence_node_ids || []).length > 0 && <span className="pill">evidence basis: {(item.supporting_evidence_node_ids || suggested?.supporting_evidence_node_ids || []).length}</span>}
                      {!!(item.history_count || 0) && <span className="pill">history events: {item.history_count}</span>}
                      {!!(item.merge_history_count || 0) && <span className="pill">merge events: {item.merge_history_count}</span>}
                    </div>
                    {!!rationaleSummary && (
                      <div className="muted" style={{ marginBottom: 8 }}>
                        rationale: {rationaleSummary}
                      </div>
                    )}
                    {rationaleCodes.length > 0 && (
                      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                        {rationaleCodes.slice(0, 5).map((code) => <span className="pill" key={code}>{code}</span>)}
                      </div>
                    )}
                    {(item.winning_node_id || suggested?.winning_node_id) && (
                      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                        <span className="pill">winner: {cleanText(item.winning_node_id || suggested?.winning_node_id)}</span>
                        {uniqueNodeIds([...(item.losing_node_ids || []), ...(suggested?.losing_node_ids || [])]).map((nodeId) => <span className="pill" key={nodeId}>loser: {nodeId}</span>)}
                      </div>
                    )}
                    {suggested?.top_claim_text && (
                      <div className="muted" style={{ marginBottom: 8 }}>
                        linked claim: {cleanText(suggested.top_claim_text)}
                      </div>
                    )}
                    {renderTimelineEvents(item.history, 'Conflict timeline')}
                    {renderTimelineEvents(item.merge_history, 'Merge / resolution timeline')}
                    <div className="row">
                      {compareNodeIds.length > 0 && onFocusTrace && <button className="tiny" onClick={() => onFocusTrace(compareNodeIds)}>Focus conflict pair</button>}
                      {compareNodeIds.length > 0 && onOpenTrace && <button className="tiny" onClick={() => onOpenTrace(compareNodeIds)}>Open conflict detail</button>}
                      {cleanText(item.status || '').toLowerCase() === 'pending' && suggested?.winning_node_id && (
                        <button className="tiny" onClick={() => { void resolveWithSuggestedBasis(item, onRefresh) }}>
                          Resolve with suggested basis
                        </button>
                      )}
                    </div>
                  </article>
                )
              })}
            </div>
          )}
        </section>
      </div>
    </section>
  )
}
