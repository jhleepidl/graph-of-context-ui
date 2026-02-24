import React from 'react'

function pillClassForType(type?: string): string {
  if (type === 'Resource') return 'pill--resource'
  if (type === 'Fold') return 'pill--fold'
  if (type === 'Decision') return 'pill--decision'
  if (type === 'Assumption') return 'pill--assumption'
  if (type === 'Plan') return 'pill--plan'
  if (type === 'ContextCandidate') return 'pill--candidate'
  return 'pill--default'
}

type Props = {
  nodes: any[]
  activeIds: string[]
  onToggle: (nodeId: string, nextActive: boolean) => void
  onOpenNode: (nodeId: string) => void
  partCountByParent: Record<string, number>
}

export default function Timeline({ nodes, activeIds, onToggle, onOpenNode, partCountByParent }: Props) {
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
          <div>
            <span className={`pill pillType ${pillClassForType(n.type)}`}>{n.type}</span>
            {partCountByParent[n.id] > 0 && <span className="pill">parts: {partCountByParent[n.id]}</span>}
            {(n.text || '').slice(0, 160).replace(/\n/g, ' ')}
          </div>
          <div className="row" style={{ marginTop: 6 }}>
            <label>
              <input
                type="checkbox"
                checked={active.has(n.id)}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => onToggle(n.id, e.target.checked)}
              /> Active
            </label>
            <button onClick={(e) => { e.stopPropagation(); onOpenNode(n.id) }}>Detail / Split</button>
          </div>
        </div>
      ))}
    </div>
  )
}
