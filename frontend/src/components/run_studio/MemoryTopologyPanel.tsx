import React from 'react'
import { type RunStudioMemoryTopology, type MemoryTopologyGrant, type MemoryTopologyMaintenanceAction, type MemoryTopologySurface } from './types'

type Props = {
  topology: RunStudioMemoryTopology | null
  onLoadDetail?: () => void
  detailLoading?: boolean
  detailLoaded?: boolean
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : String(value || '').trim()
}

function numberText(value: unknown, digits = 2): string {
  const n = Number(value)
  if (!Number.isFinite(n)) return '0'
  return n.toFixed(digits)
}

function listText(values: unknown, fallback = '—'): string {
  if (!Array.isArray(values) || values.length === 0) return fallback
  return values.map((value) => cleanText(value)).filter(Boolean).join(', ') || fallback
}

function surfaceId(surface: MemoryTopologySurface): string {
  return cleanText(surface.id || surface.surface_id || 'surface')
}

function grantRows(grants?: Record<string, MemoryTopologyGrant>): MemoryTopologyGrant[] {
  if (!grants || typeof grants !== 'object') return []
  return Object.entries(grants)
    .map(([key, value]) => ({ ...value, agent_id: value?.agent_id || key }))
    .filter((row) => cleanText(row.agent_id || row.role))
}

function actionRows(actions?: MemoryTopologyMaintenanceAction[]): MemoryTopologyMaintenanceAction[] {
  return Array.isArray(actions) ? actions.filter(Boolean).slice(0, 8) : []
}

export default function MemoryTopologyPanel({ topology, onLoadDetail, detailLoading, detailLoaded }: Props) {
  const mode = cleanText(topology?.mode || 'unknown')
  const stress = topology?.stress_score ?? topology?.stress?.score ?? 0
  const surfaces = Array.isArray(topology?.surfaces) ? topology?.surfaces || [] : []
  const grants = grantRows(topology?.agent_grants)
  const actions = actionRows(topology?.maintenance?.actions)
  const reasons = Array.isArray(topology?.stress?.reasons) && topology?.stress?.reasons?.length
    ? topology?.stress?.reasons
    : topology?.selection_reason || []
  const fallback = Boolean(topology?.fallback)

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Adaptive Memory Topology</h3>
          <div className="muted">Runtime-selected memory mode, surface split/merge plan, and per-agent read/write grants.</div>
        </div>
        {onLoadDetail && !detailLoaded && (
          <button onClick={onLoadDetail} disabled={detailLoading}>{detailLoading ? 'Loading...' : 'Load detail'}</button>
        )}
      </div>

      {!topology ? (
        <div className="muted">No memory topology snapshot has been loaded yet.</div>
      ) : (
        <>
          <div className="runStudioMetaRow" style={{ marginBottom: 10 }}>
            <span className="pill">mode: {mode}</span>
            <span className="pill">stress: {numberText(stress)}</span>
            <span className="pill">surfaces: {topology.surface_count ?? surfaces.length}</span>
            <span className="pill">agent grants: {topology.agent_grant_count ?? grants.length}</span>
            <span className="pill">idle safe: {topology.idle_safe === false ? 'no' : 'yes'}</span>
            {fallback && <span className="pill">fallback estimate</span>}
            {topology.source && <span className="pill">source: {cleanText(topology.source)}</span>}
          </div>

          {reasons.length > 0 && <div className="muted" style={{ marginBottom: 10 }}>Reasons: {listText(reasons)}</div>}

          <div className="runStudioGrid runStudioGrid--bottom">
            <section className="runStudioInlineSection">
              <div className="runStudioExecutionLaneTitle" style={{ marginBottom: 6 }}>Surfaces</div>
              {surfaces.length === 0 ? (
                <div className="muted">No explicit surfaces. The runtime is likely using ephemeral or compact shared memory.</div>
              ) : (
                <div className="runStudioQuickList">
                  {surfaces.slice(0, 8).map((surface) => (
                    <div className="runStudioQuickListItem" key={surfaceId(surface)}>
                      <div className="runStudioQuickListHeader">
                        <span className="runStudioQuickListTitle">{surfaceId(surface)}</span>
                        <span className="pill">{cleanText(surface.kind || surface.semantic_kind || 'memory')}</span>
                      </div>
                      <div className="muted">readers: {listText(surface.readers)} · writers: {listText(surface.writers)} · steward: {listText(surface.steward)}</div>
                      {surface.lens && <div className="muted">lens: {cleanText(surface.lens)}</div>}
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="runStudioInlineSection">
              <div className="runStudioExecutionLaneTitle" style={{ marginBottom: 6 }}>Agent grants</div>
              {grants.length === 0 ? (
                <div className="muted">No per-agent grants recorded yet. Shared memory is used as the safe default.</div>
              ) : (
                <div className="runStudioQuickList">
                  {grants.slice(0, 8).map((grant) => (
                    <div className="runStudioQuickListItem" key={cleanText(grant.agent_id || grant.role)}>
                      <div className="runStudioQuickListHeader">
                        <span className="runStudioQuickListTitle">{cleanText(grant.agent_id || grant.role || 'agent')}</span>
                        {grant.role && <span className="pill">role: {cleanText(grant.role)}</span>}
                      </div>
                      <div className="muted">read: {listText(grant.read)} · write: {listText(grant.write)} · mode: {cleanText(grant.write_mode || 'contracted')}</div>
                      {grant.lens && <div className="muted">lens: {cleanText(grant.lens)}</div>}
                    </div>
                  ))}
                </div>
              )}
            </section>
          </div>

          <div style={{ marginTop: 12 }}>
            <div className="runStudioExecutionLaneTitle" style={{ marginBottom: 6 }}>Idle maintenance plan</div>
            {actions.length === 0 ? (
              <div className="muted">No idle maintenance actions are currently recommended.</div>
            ) : (
              <div className="runStudioMetaRow">
                {actions.map((action, index) => (
                  <span className="pill" key={`${cleanText(action.action || 'action')}-${index}`}>
                    {cleanText(action.action || 'maintenance')}{action.candidate_only ? ' · candidate' : ''}
                  </span>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </section>
  )
}
