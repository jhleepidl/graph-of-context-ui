import React from 'react'
import { type RunStudioEvidence } from './types'

type Props = {
  evidence: RunStudioEvidence | null
  onOpenNode?: (nodeId: string) => void
  onFocusNode?: (nodeId: string) => void
  onOpenTrace?: (nodeIds: string[]) => void
  onFocusTrace?: (nodeIds: string[]) => void
  onAddToActive?: (nodeId: string) => void
  onPinNode?: (nodeId: string, level: 'required' | 'preferred') => void
}

export default function EvidencePanel({
  evidence,
  onOpenNode,
  onFocusNode,
  onOpenTrace,
  onFocusTrace,
  onAddToActive,
  onPinNode,
}: Props) {
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
              {onFocusNode && <button className="tiny" onClick={() => onFocusNode(item.claim_node_id)}>Focus</button>}
              {onOpenNode && <button className="tiny" onClick={() => onOpenNode(item.claim_node_id)}>Detail</button>}
              {!item.selected_in_context && onAddToActive && (
                <button className="tiny" onClick={() => onAddToActive(item.claim_node_id)}>Include</button>
              )}
              {!item.pinned && onPinNode && (
                <button className="tiny" onClick={() => onPinNode(item.claim_node_id, 'preferred')}>Pin</button>
              )}
              {item.related_node_ids && item.related_node_ids.length > 1 && onOpenTrace && (
                <>
                  <button className="tiny" onClick={() => onOpenTrace(item.related_node_ids || [])}>Trace</button>
                </>
              )}
              {item.related_node_ids && item.related_node_ids.length > 1 && !onOpenTrace && onFocusTrace && (
                <button className="tiny" onClick={() => onFocusTrace(item.related_node_ids || [])}>Focus trace</button>
              )}
              {(item.conflict_node_ids?.length || 0) > 0 && onOpenTrace && (
                <button className="tiny" onClick={() => onOpenTrace([item.claim_node_id, ...(item.conflict_node_ids || [])])}>Compare</button>
              )}
              {item.selected_in_context && <span className="pill">selected</span>}
              {item.pinned && <span className="pill">pinned {item.pin_level || ''}</span>}
              {(item.evidence_nodes?.length || 0) > 0 && <span className="pill">evidence {item.evidence_nodes?.length}</span>}
              {(item.conflict_node_ids?.length || 0) > 0 && <span className="pill">conflicts {item.conflict_node_ids?.length}</span>}
              {typeof item.score === 'number' && <span className="pill">score {item.score.toFixed(2)}</span>}
            </div>
            <div>{item.claim_text || item.claim_node_id}</div>
            {item.evidence_nodes && item.evidence_nodes.length > 0 && (
              <div className="runStudioMetaRow">
                {item.evidence_nodes.slice(0, 3).map((eNode) => (
                  <React.Fragment key={eNode.id}>
                    {onOpenNode && (
                      <button className="tiny" onClick={() => onOpenNode(eNode.id)}>
                        {eNode.type || 'Node'} {eNode.id.slice(0, 6)}
                      </button>
                    )}
                    {!onOpenNode && onFocusNode && (
                      <button className="tiny" onClick={() => onFocusNode(eNode.id)}>
                        {eNode.type || 'Node'} {eNode.id.slice(0, 6)}
                      </button>
                    )}
                  </React.Fragment>
                ))}
              </div>
            )}
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
