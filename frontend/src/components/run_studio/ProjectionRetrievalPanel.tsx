import React from 'react'
import { type RunStudioProjectionRetrieval } from './types'

type Props = {
  projectionRetrieval: RunStudioProjectionRetrieval | null
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : String(value || '').trim()
}

function formatTimestamp(value?: string | null): string {
  const clean = cleanText(value)
  if (!clean) return 'unknown time'
  const parsed = new Date(clean)
  if (Number.isNaN(parsed.getTime())) return clean
  return parsed.toLocaleString()
}

export default function ProjectionRetrievalPanel({ projectionRetrieval }: Props) {
  const summary = projectionRetrieval?.summary || null
  const items = projectionRetrieval?.items || []
  const plannerSystem = projectionRetrieval?.planner_system_paths || []
  const counts = projectionRetrieval?.counts || {}
  const visibilityCounts = projectionRetrieval?.visibility_relation_counts || {}

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Projection Retrieval Coverage</h3>
          <div className="muted">Focused run coverage across scope-first runtime specs, memory projections, and planner/system retrieval paths.</div>
        </div>
      </div>

      {!projectionRetrieval && <div className="muted">Focused run bundle has not been loaded yet.</div>}

      {projectionRetrieval && (
        <>
          <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
            {summary?.status && <span className="pill">status: {cleanText(summary.status)}</span>}
            {summary?.context_source && <span className="pill">context: {cleanText(summary.context_source)}</span>}
            <span className="pill">roles: {counts.roles ?? items.length}</span>
            <span className="pill">authoritative: {counts.authoritative_roles ?? 0}</span>
            <span className="pill">missing: {counts.missing_projection_roles ?? 0}</span>
            <span className="pill">blocked-only: {counts.blocked_only_roles ?? 0}</span>
            {typeof summary?.scope_first_ready === 'boolean' && <span className="pill">scope-first: {summary.scope_first_ready ? 'ready' : 'no'}</span>}
            {typeof summary?.projection_authoritative === 'boolean' && <span className="pill">authoritative runtime: {summary.projection_authoritative ? 'yes' : 'partial'}</span>}
          </div>

          {(summary?.coverage_note || summary?.scope_projection_note) && (
            <div className="muted" style={{ marginBottom: 10 }}>
              {summary?.coverage_note && <div>{cleanText(summary.coverage_note)}</div>}
              {summary?.scope_projection_note && <div>scope note: {cleanText(summary.scope_projection_note)}</div>}
            </div>
          )}

          <div className="runStudioMetaRow" style={{ marginBottom: 10 }}>
            {plannerSystem.length > 0 && <span className="pill">planner/system roles: {plannerSystem.length}</span>}
            {(counts.planner_system_authoritative_roles ?? 0) > 0 && <span className="pill">planner/system authoritative: {counts.planner_system_authoritative_roles}</span>}
            {(counts.planner_system_missing_roles ?? 0) > 0 && <span className="pill">planner/system missing: {counts.planner_system_missing_roles}</span>}
            {Object.entries(visibilityCounts).map(([key, value]) => <span key={key} className="pill">{key}: {value}</span>)}
          </div>

          {items.length === 0 ? (
            <div className="muted">No projection retrieval coverage rows were materialized for this run.</div>
          ) : (
            <div className="runStudioAgentCardGrid">
              {items.slice(0, 8).map((item, index) => (
                <article key={`${cleanText(item.runtime_instance_id) || cleanText(item.role_id) || index}`} className="runStudioAgentCard">
                  <div className="runStudioAgentCardHeader">
                    <div>
                      <div className="runStudioAgentCardTitle">{cleanText(item.display_label || item.role_id || 'runtime agent')}</div>
                      <div className="muted">{cleanText(item.role_id || item.runtime_instance_id || item.scope_id || 'unknown')}</div>
                    </div>
                    <div className="runStudioMetaRow">
                      {item.status && <span className="runStudioStatusChip runStudioStatus--idle">{cleanText(item.status)}</span>}
                      {item.projection_authoritative && <span className="runStudioStatusChip runStudioStatus--success">authoritative</span>}
                    </div>
                  </div>
                  <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                    <span className="pill">active nodes: {item.active_node_count ?? 0}</span>
                    <span className="pill">visible: {item.visible_node_count ?? 0}</span>
                    <span className="pill">blocked: {item.blocked_node_count ?? 0}</span>
                    {item.visibility_mode && <span className="pill">visibility: {cleanText(item.visibility_mode)}</span>}
                  </div>
                  {(item.grant_labels || []).length > 0 && (
                    <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                      {(item.grant_labels || []).map((grant) => <span key={grant} className="pill">grant: {grant}</span>)}
                    </div>
                  )}
                  {item.selection_summary && <div className="muted">{cleanText(item.selection_summary)}</div>}
                  {item.projection_created_at && <div className="muted" style={{ marginTop: 8 }}>projection: {formatTimestamp(item.projection_created_at)}</div>}
                  {item.fallback_reason && <div className="runStudioWarning" style={{ marginTop: 8 }}>fallback: {cleanText(item.fallback_reason)}</div>}
                </article>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  )
}
