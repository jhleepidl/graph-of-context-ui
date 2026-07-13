import React from 'react'
import { type RunStudioContextDecisions } from './types'

type Props = {
  decisions: RunStudioContextDecisions | null
  onOpenNode?: (nodeId: string) => void
  onFocusNode?: (nodeId: string) => void
  onPinNode?: (nodeId: string, level: 'required' | 'preferred') => void
  onExcludeNode?: (source: string) => void
}

export default function ContextDecisionPanel({
  decisions,
  onOpenNode,
  onFocusNode,
  onPinNode,
  onExcludeNode,
}: Props) {
  const selected = decisions?.selected || []
  const pinned = decisions?.pinned || []
  const excluded = decisions?.excluded || []
  const counts = decisions?.counts || {}

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Context Decisions</h3>
        <div className="runStudioMetaRow">
          <span className="pill">selected: {counts.selected ?? selected.length}</span>
          <span className="pill">pinned: {counts.pinned ?? pinned.length}</span>
          <span className="pill">excluded: {counts.excluded ?? excluded.length}</span>
          <span className="pill">missing: {counts.missing ?? 0}</span>
          <span className="pill">conflicts: {counts.conflicting ?? 0}</span>
        </div>
      </div>

      <div className="runStudioDualList">
        <div>
          <div className="muted" style={{ marginBottom: 6 }}>Selected / Pinned</div>
          <div className="runStudioList">
            {selected.slice(0, 10).map((item) => (
              <article key={item.id} className="runStudioListItem">
                <div className="row" style={{ marginBottom: 4 }}>
                  <span className="pill">{item.type || 'Node'}</span>
                  {item.pinned && <span className="pill">pinned {item.pin_level || ''}</span>}
                  {item.target_node_id && onFocusNode && (
                    <>
                      <button className="tiny" onClick={() => onFocusNode(item.target_node_id || item.id)}>Focus</button>
                    </>
                  )}
                  {item.target_node_id && onOpenNode && <button className="tiny" onClick={() => onOpenNode(item.target_node_id || item.id)}>Detail</button>}
                  {!item.pinned && item.target_node_id && onPinNode && (
                    <button className="tiny" onClick={() => onPinNode(item.target_node_id || item.id, 'preferred')}>Pin</button>
                  )}
                  {onExcludeNode && (
                    <button className="tiny" onClick={() => onExcludeNode(item.text || item.target_node_id || item.id)}>Exclude</button>
                  )}
                </div>
                <div>{item.text || item.id}</div>
              </article>
            ))}
            {selected.length === 0 && <div className="muted">No selected context nodes.</div>}
          </div>
        </div>

        <div>
          <div className="muted" style={{ marginBottom: 6 }}>Excluded From Compiled</div>
          <div className="runStudioList">
            {excluded.slice(0, 8).map((item) => (
              <article key={item.id} className="runStudioListItem">
                <div className="row" style={{ marginBottom: 4 }}>
                  <span className="pill">{item.type || 'Node'}</span>
                  {!item.pinned && item.target_node_id && onPinNode && (
                    <button className="tiny" onClick={() => onPinNode(item.target_node_id || item.id, 'preferred')}>Pin</button>
                  )}
                  {item.target_node_id && onFocusNode && <button className="tiny" onClick={() => onFocusNode(item.target_node_id || item.id)}>Focus</button>}
                  {item.target_node_id && onOpenNode && <button className="tiny" onClick={() => onOpenNode(item.target_node_id || item.id)}>Detail</button>}
                </div>
                <div>{item.text || item.id}</div>
                <div className="muted">{item.reason || ''}</div>
              </article>
            ))}
            {excluded.length === 0 && <div className="muted">No currently excluded parent placeholders.</div>}
          </div>
        </div>
      </div>
    </section>
  )
}
