import React from 'react'
import { type CollaborationProjection } from './types'

type Props = {
  collaboration: CollaborationProjection | null
}

export default function CollaborationPanel({ collaboration }: Props) {
  const items = collaboration?.items || []
  const counts = collaboration?.counts || {}

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Collaboration</h3>
        <div className="runStudioMetaRow">
          <span className="pill">cells: {collaboration?.count ?? items.length}</span>
          {Object.entries(counts).map(([kind, count]) => (
            <span key={kind} className="pill">{kind}: {count}</span>
          ))}
        </div>
      </div>

      <div className="runStudioList">
        {items.map((cell, index) => (
          <article key={`${cell.cell_id || cell.kind || 'cell'}:${index}`} className="runStudioListItem">
            <div className="row" style={{ marginBottom: 4 }}>
              <span className="pill">{cell.display_label || cell.kind || cell.cell_id || 'collaboration cell'}</span>
              {cell.decision_mode && <span className="pill">decision: {cell.decision_mode}</span>}
              {typeof cell.max_rounds === 'number' && <span className="pill">rounds: {cell.max_rounds}</span>}
            </div>
            {(cell.member_labels?.length || cell.member_instance_ids?.length) ? (
              <div className="muted">
                members: {(cell.member_labels && cell.member_labels.length > 0 ? cell.member_labels : cell.member_instance_ids || []).join(' | ')}
              </div>
            ) : (
              <div className="muted">members: not specified</div>
            )}
            {(cell.topology || cell.termination_rule) && (
              <div className="muted">
                {cell.topology ? `topology: ${cell.topology}` : 'topology: runtime-managed'}
                {cell.termination_rule ? ` | terminate: ${cell.termination_rule}` : ''}
              </div>
            )}
            {cell.selection_reason && <div className="muted">reason: {cell.selection_reason}</div>}
          </article>
        ))}

        {items.length === 0 && (
          <div className="muted">No explicit collaboration cells were emitted for this run. Older payloads continue to render without this section failing.</div>
        )}
      </div>
    </section>
  )
}
