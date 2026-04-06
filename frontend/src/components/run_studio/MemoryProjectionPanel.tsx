import React from 'react'
import { api } from '../../api'
import { type RunStudioMemoryGraph, type MemoryConflictDetail, type MemoryNodeDrilldown } from './types'

type Props = {
  memoryGraph: RunStudioMemoryGraph | null
  onLoadDetail?: () => void
  detailLoading?: boolean
  detailLoaded?: boolean
  onRefresh?: () => void
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : String(value || '').trim()
}

function conflictTone(status: string): string {
  const clean = status.trim().toLowerCase()
  if (clean === 'pending') return 'runStudioStatus--blocked'
  if (clean === 'resolved' || clean === 'merged' || clean === 'accepted') return 'runStudioStatus--done'
  return 'runStudioStatus--idle'
}

async function resolveQuickly(conflict: MemoryConflictDetail, onRefresh?: () => void) {
  const conflictId = cleanText(conflict.id)
  if (!conflictId) return
  const winner = cleanText(conflict.right_node_id || conflict.left_node_id)
  const loser = cleanText(conflict.left_node_id && conflict.left_node_id !== winner ? conflict.left_node_id : '')
  try {
    await api.resolveMemoryConflict(conflictId, {
      status: 'resolved',
      winning_node_id: winner || null,
      losing_node_ids: loser ? [loser] : [],
      summary: 'Resolved from Run Studio quick action',
    })
    onRefresh?.()
  } catch (error) {
    console.error('failed to resolve memory conflict', error)
  }
}

function renderNodeDrilldown(title: string, nodes: MemoryNodeDrilldown[] | undefined, blocked = false) {
  const items = nodes || []
  return (
    <div style={{ marginTop: 10 }}>
      <div className="runStudioExecutionLaneTitle" style={{ marginBottom: 6 }}>{title}</div>
      {items.length === 0 ? (
        <div className="muted">No nodes.</div>
      ) : (
        <div className="runStudioAgentCardGrid">
          {items.slice(0, 8).map((node) => (
            <article key={node.node_id || `${node.surface_id}-${node.content_preview}`} className="runStudioAgentCard">
              <div className="runStudioAgentCardHeader">
                <div>
                  <div className="runStudioAgentCardTitle">{cleanText(node.node_id || node.surface_id || 'node')}</div>
                  <div className="muted">{cleanText(node.node_type || 'note')} · {cleanText(node.surface_id || 'surface')}</div>
                </div>
                <span className={`runStudioStatusChip ${blocked ? 'runStudioStatus--blocked' : 'runStudioStatus--idle'}`}>{cleanText(node.status || (blocked ? 'blocked' : 'visible'))}</span>
              </div>
              <div className="muted" style={{ marginBottom: 8 }}>{cleanText(node.content_preview || '(no preview)')}</div>
              <div className="runStudioMetaRow">
                {node.trust_tier && <span className="pill">trust: {node.trust_tier}</span>}
                {typeof node.confidence === 'number' && <span className="pill">conf: {Number(node.confidence).toFixed(2)}</span>}
                {node.owner_role_id && <span className="pill">role: {node.owner_role_id}</span>}
                {blocked && node.blocked_reason && <span className="pill">blocked: {node.blocked_reason}</span>}
              </div>
              {node.provenance_fingerprint && <div className="muted" style={{ marginTop: 6 }}>prov: {node.provenance_fingerprint}</div>}
            </article>
          ))}
        </div>
      )}
    </div>
  )
}

export default function MemoryProjectionPanel({
  memoryGraph,
  onLoadDetail,
  detailLoading,
  detailLoaded,
  onRefresh,
}: Props) {
  const projections = memoryGraph?.projections || []
  const conflicts = memoryGraph?.conflicts || []

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Memory Projections</h3>
          <div className="muted">
            Agent-scoped visibility and conflict state for the governed context graph.
          </div>
        </div>
        {!detailLoaded && onLoadDetail && (
          <button onClick={onLoadDetail} disabled={detailLoading}>
            {detailLoading ? 'Loading...' : 'Load detail'}
          </button>
        )}
        {detailLoaded && onRefresh && (
          <button onClick={onRefresh} disabled={detailLoading}>
            {detailLoading ? 'Refreshing...' : 'Refresh detail'}
          </button>
        )}
      </div>

      {!detailLoaded && !detailLoading && (
        <div className="muted">Load recent memory projections and conflicts to inspect role-scoped context exposure.</div>
      )}

      {detailLoaded && (
        <>
          <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
            <span className="pill">projections: {memoryGraph?.projection_count || 0}</span>
            <span className="pill">conflicts: {memoryGraph?.conflict_count || 0}</span>
            {Object.entries(memoryGraph?.conflict_status_counts || {}).map(([status, count]) => (
              <span className="pill" key={status}>{status}: {count}</span>
            ))}
            {Object.entries(memoryGraph?.conflict_reason_counts || {}).map(([reason, count]) => (
              <span className="pill" key={reason}>{reason}: {count}</span>
            ))}
          </div>

          <div className="runStudioTeamGroupList">
            <section className="runStudioTeamGroup">
              <div className="runStudioTeamGroupHeader">
                <div className="runStudioExecutionLaneTitle">Recent projections</div>
                <div className="muted">{projections.length}</div>
              </div>
              {projections.length === 0 ? (
                <div className="muted">No projection snapshots have been stored yet.</div>
              ) : (
                <div className="runStudioAgentCardGrid">
                  {projections.map((projection) => (
                    <article key={projection.projection_id || `${projection.agent_id}-${projection.created_at}`} className="runStudioAgentCard" style={{ gridColumn: '1 / -1' }}>
                      <div className="runStudioAgentCardHeader">
                        <div>
                          <div className="runStudioAgentCardTitle">{cleanText(projection.role_id || projection.agent_id || 'projection')}</div>
                          <div className="muted">agent {cleanText(projection.agent_id || '(unset)')}</div>
                        </div>
                        <span className="runStudioStatusChip runStudioStatus--idle">{cleanText(projection.created_at || '') || 'snapshot'}</span>
                      </div>
                      <div className="runStudioMetaRow">
                        <span className="pill">visible surfaces: {projection.summary?.visible_surface_count || 0}</span>
                        <span className="pill">blocked surfaces: {projection.summary?.blocked_surface_count || 0}</span>
                        <span className="pill">visible nodes: {projection.summary?.visible_node_count || 0}</span>
                        <span className="pill">blocked nodes: {projection.summary?.blocked_node_count || 0}</span>
                      </div>
                      {!!(projection.visible_surface_ids || []).length && (
                        <div className="muted" style={{ marginTop: 6 }}>visible surfaces: {(projection.visible_surface_ids || []).join(', ')}</div>
                      )}
                      {!!(projection.blocked_surface_ids || []).length && (
                        <div className="muted" style={{ marginTop: 4 }}>blocked surfaces: {(projection.blocked_surface_ids || []).join(', ')}</div>
                      )}
                      {renderNodeDrilldown('Visible nodes', projection.visible_nodes)}
                      {renderNodeDrilldown('Blocked nodes', projection.blocked_nodes, true)}
                    </article>
                  ))}
                </div>
              )}
            </section>

            <section className="runStudioTeamGroup">
              <div className="runStudioTeamGroupHeader">
                <div className="runStudioExecutionLaneTitle">Memory conflicts</div>
                <div className="muted">{conflicts.length}</div>
              </div>
              {conflicts.length === 0 ? (
                <div className="muted">No memory conflicts detected in the recent view.</div>
              ) : (
                <div className="runStudioAgentCardGrid">
                  {conflicts.map((conflict) => (
                    <article key={conflict.id || `${conflict.left_node_id}-${conflict.right_node_id}`} className="runStudioAgentCard">
                      <div className="runStudioAgentCardHeader">
                        <div>
                          <div className="runStudioAgentCardTitle">{cleanText(conflict.surface_id || 'surface')}</div>
                          <div className="muted">{cleanText(conflict.left_node_id)} ↔ {cleanText(conflict.right_node_id)}</div>
                        </div>
                        <span className={`runStudioStatusChip ${conflictTone(cleanText(conflict.status || 'idle'))}`}>{cleanText(conflict.status || 'pending')}</span>
                      </div>
                      <div className="muted" style={{ marginBottom: 8 }}>{cleanText(conflict.reason || 'conflicting memory writes')}</div>
                      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                        {conflict.conflict_key && <span className="pill">key: {conflict.conflict_key}</span>}
                        {conflict.left_trust_tier && <span className="pill">L trust: {conflict.left_trust_tier}</span>}
                        {conflict.right_trust_tier && <span className="pill">R trust: {conflict.right_trust_tier}</span>}
                        {typeof conflict.left_confidence === 'number' && <span className="pill">L conf: {Number(conflict.left_confidence).toFixed(2)}</span>}
                        {typeof conflict.right_confidence === 'number' && <span className="pill">R conf: {Number(conflict.right_confidence).toFixed(2)}</span>}
                      </div>
                      {(conflict.left_provenance_fingerprint || conflict.right_provenance_fingerprint) && (
                        <div className="muted" style={{ marginBottom: 8 }}>
                          prov: {cleanText(conflict.left_provenance_fingerprint || '-')} ↔ {cleanText(conflict.right_provenance_fingerprint || '-')}
                        </div>
                      )}
                      {(conflict.winning_node_id || (conflict.losing_node_ids || []).length > 0) && (
                        <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                          {conflict.winning_node_id && <span className="pill">winner: {conflict.winning_node_id}</span>}
                          {(conflict.losing_node_ids || []).map((nodeId) => <span className="pill" key={nodeId}>loser: {nodeId}</span>)}
                        </div>
                      )}
                      {cleanText(conflict.status || '').toLowerCase() === 'pending' && (
                        <button onClick={() => resolveQuickly(conflict, onRefresh)}>Resolve (keep latest)</button>
                      )}
                    </article>
                  ))}
                </div>
              )}
            </section>
          </div>
        </>
      )}
    </section>
  )
}
