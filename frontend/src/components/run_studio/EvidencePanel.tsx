import React from 'react'
import { type RunStudioEvidence } from './types'

type Props = {
  evidence: RunStudioEvidence | null
}

export default function EvidencePanel({ evidence }: Props) {
  const items = evidence?.items || []
  const counts = evidence?.counts || {}

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Evidence</h3>
        <div className="runStudioMetaRow">
          <span className="pill">claims: {counts.claims ?? items.length}</span>
          <span className="pill">supported: {counts.supported ?? 0}</span>
          <span className="pill">uncertain: {counts.with_uncertainty ?? 0}</span>
          <span className="pill">conflicts: {counts.with_conflicts ?? 0}</span>
        </div>
      </div>

      <div className="runStudioList">
        {items.slice(0, 10).map((item) => (
          <article key={item.claim_node_id} className="runStudioListItem">
            <div className="row" style={{ marginBottom: 4 }}>
              <span className="pill">{item.claim_node_type || 'Claim'}</span>
              {item.selected_in_context && <span className="pill">selected</span>}
              {(item.evidence_nodes?.length || 0) > 0 && <span className="pill">evidence {item.evidence_nodes?.length}</span>}
              {(item.conflict_node_ids?.length || 0) > 0 && <span className="pill">conflicts {item.conflict_node_ids?.length}</span>}
            </div>
            <div>{item.claim_text || item.claim_node_id}</div>
            {item.provenance && item.provenance.length > 0 && (
              <div className="muted">source: {item.provenance.slice(0, 2).join(' | ')}</div>
            )}
            {item.uncertainty && item.uncertainty.length > 0 && (
              <div className="muted">uncertainty: {item.uncertainty.slice(0, 2).join(' | ')}</div>
            )}
          </article>
        ))}
        {items.length === 0 && <div className="muted">No claim/evidence pairs detected yet.</div>}
      </div>
    </section>
  )
}
