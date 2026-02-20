import React from 'react'

type Props = {
  nodes: any[]
  activeIds: string[]
  onToggle: (nodeId: string, nextActive: boolean) => void
}

export default function Timeline({ nodes, activeIds, onToggle }: Props) {
  const active = new Set(activeIds)
  const sorted = [...nodes].sort((a, b) => (a.created_at < b.created_at ? -1 : 1))

  function handleDragStart(e: React.DragEvent<HTMLDivElement>, nodeId: string) {
    e.dataTransfer.setData('application/x-goc-node-id', nodeId)
    e.dataTransfer.setData('text/plain', nodeId)
    e.dataTransfer.effectAllowed = 'copyMove'
    ;(window as any).__goc_drag_node_id = nodeId
  }

  function handleDragEnd() {
    ;(window as any).__goc_drag_node_id = ''
  }

  return (
    <div>
      <h3>Timeline</h3>
      {sorted.map(n => (
        <div
          key={n.id}
          className="card"
          draggable
          onDragStart={(e) => handleDragStart(e, n.id)}
          onDragEnd={handleDragEnd}
          title="드래그해서 Active Context에 추가 가능"
        >
          <div className="muted">{n.created_at}</div>
          <div><span className="pill">{n.type}</span> {(n.text || '').slice(0, 160).replace(/\n/g, ' ')}</div>
          <div className="row" style={{ marginTop: 6 }}>
            <label>
              <input
                type="checkbox"
                checked={active.has(n.id)}
                onChange={(e) => onToggle(n.id, e.target.checked)}
              /> Active
            </label>
          </div>
        </div>
      ))}
    </div>
  )
}
