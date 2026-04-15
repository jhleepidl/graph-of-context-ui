import React from 'react'
import { type RunStudioGraphCompression } from './types'

type Props = {
  graphCompression: RunStudioGraphCompression | null
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : String(value || '').trim()
}

export default function GraphCompressionPanel({ graphCompression }: Props) {
  const summary = graphCompression?.summary || null
  const clusters = graphCompression?.clusters || []
  const roleViews = graphCompression?.role_views || []
  const omitted = graphCompression?.omitted_clusters || []

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Graph-Native Compression</h3>
          <div className="muted">Role-conditioned partial graph reduction that preserves support frontier, conflict frontier, decision spine, and re-expand handles.</div>
        </div>
      </div>

      {!graphCompression && <div className="muted">Focused run bundle has not been loaded yet.</div>}

      {graphCompression && (
        <>
          <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
            {summary?.compression_mode && <span className="pill">mode: {cleanText(summary.compression_mode)}</span>}
            <span className="pill">clusters: {summary?.cluster_count ?? clusters.length}</span>
            <span className="pill">role views: {summary?.role_view_count ?? roleViews.length}</span>
            <span className="pill">core claims: {summary?.core_claim_count ?? 0}</span>
            <span className="pill">support frontier: {summary?.support_frontier_count ?? 0}</span>
            <span className="pill">open conflicts: {summary?.unresolved_conflict_count ?? 0}</span>
            {graphCompression.anchor_node_id && <span className="pill">anchor: {graphCompression.anchor_node_id}</span>}
          </div>

          {summary?.compression_note && <div className="muted" style={{ marginBottom: 10 }}>{cleanText(summary.compression_note)}</div>}

          {roleViews.length > 0 && (
            <div style={{ display: 'grid', gap: 10, marginBottom: 12 }}>
              {roleViews.map((view, index) => (
                <article key={`${cleanText(view.role_id) || index}`} className="runStudioAgentCard">
                  <div className="runStudioAgentCardHeader">
                    <div>
                      <div className="runStudioAgentCardTitle">{cleanText(view.display_label || view.role_id || 'role view')}</div>
                      <div className="muted">{cleanText(view.role_id || view.projection_id || 'unknown')}</div>
                    </div>
                    <div className="runStudioMetaRow">
                      {view.status && <span className="pill">{cleanText(view.status)}</span>}
                      <span className="pill">visible clusters: {(view.visible_cluster_ids || []).length}</span>
                      {(view.blocked_cluster_ids || []).length > 0 && <span className="pill">blocked clusters: {(view.blocked_cluster_ids || []).length}</span>}
                    </div>
                  </div>
                  {(view.core_claim_node_ids || []).length > 0 && (
                    <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                      <span className="pill">claims: {(view.core_claim_node_ids || []).length}</span>
                      <span className="pill">support nodes: {(view.support_frontier_node_ids || []).length}</span>
                      {(view.conflict_frontier_ids || []).length > 0 && <span className="pill">conflicts: {(view.conflict_frontier_ids || []).length}</span>}
                    </div>
                  )}
                  {view.rendered_context ? (
                    <pre style={{ whiteSpace: 'pre-wrap', margin: 0, fontFamily: 'inherit', fontSize: 13 }}>{view.rendered_context}</pre>
                  ) : (
                    <div className="muted">No compressed context was materialized for this role.</div>
                  )}
                </article>
              ))}
            </div>
          )}

          {clusters.length > 0 && (
            <div className="runStudioAgentCardGrid">
              {clusters.slice(0, 8).map((cluster) => (
                <article key={cluster.cluster_id} className="runStudioAgentCard">
                  <div className="runStudioAgentCardHeader">
                    <div>
                      <div className="runStudioAgentCardTitle">{cleanText(cluster.label || cluster.headline || cluster.cluster_id)}</div>
                      <div className="muted">{cleanText(cluster.cluster_type || 'cluster')}</div>
                    </div>
                    <div className="runStudioMetaRow">
                      {cluster.status && <span className="pill">{cleanText(cluster.status)}</span>}
                      {(cluster.role_ids || []).length > 0 && <span className="pill">roles: {(cluster.role_ids || []).length}</span>}
                    </div>
                  </div>
                  {cluster.rendered_summary && <div className="muted" style={{ marginBottom: 8 }}>{cleanText(cluster.rendered_summary)}</div>}
                  <div className="runStudioMetaRow">
                    {(cluster.representative_claim_node_ids || []).length > 0 && <span className="pill">claims: {(cluster.representative_claim_node_ids || []).length}</span>}
                    {(cluster.representative_memory_node_ids || []).length > 0 && <span className="pill">memory: {(cluster.representative_memory_node_ids || []).length}</span>}
                    {(cluster.conflict_frontier_ids || []).length > 0 && <span className="pill">conflicts: {(cluster.conflict_frontier_ids || []).length}</span>}
                    {(cluster.decision_path_event_ids || []).length > 0 && <span className="pill">decision path: {(cluster.decision_path_event_ids || []).length}</span>}
                  </div>
                </article>
              ))}
            </div>
          )}

          {omitted.length > 0 && <div className="muted" style={{ marginTop: 10 }}>Omitted clusters: {omitted.length}</div>}
        </>
      )}
    </section>
  )
}
