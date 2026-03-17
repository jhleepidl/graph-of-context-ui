import React from 'react'
import { type VisibilityProjection } from './types'

type Props = {
  visibilityProjection: VisibilityProjection | null
}

export default function VisibilityPanel({ visibilityProjection }: Props) {
  const items = visibilityProjection?.items || []
  const relationCounts = visibilityProjection?.relation_counts || {}

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3 style={{ margin: 0 }}>Visibility Links</h3>
          <div className="muted">Upstream summary-only links and scope-to-scope visibility edges.</div>
        </div>
        <div className="runStudioMetaRow">
          <span className="pill">edges: {visibilityProjection?.count ?? items.length}</span>
          {Object.entries(relationCounts).map(([key, value]) => (
            <span key={`relation-${key}`} className="pill">{key}: {value}</span>
          ))}
        </div>
      </div>

      {items.length === 0 ? (
        <div className="muted">No visibility graph edges are available yet.</div>
      ) : (
        <div className="runStudioSkillStack">
          {items.map((item, index) => (
            <div key={`${item.edge_id || 'edge'}:${index}`} className="runStudioSkillRow">
              <div>
                <div><b>{item.from_label || item.from_scope_id || 'scope'}</b> → <b>{item.to_label || item.to_scope_id || 'scope'}</b></div>
                <div className="muted">{item.relation || 'visible_to'}</div>
              </div>
              <span className="pill">{item.relation || 'visible_to'}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
