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
  activeIds: string[]
  nodesById: Map<string, any>
  onRemove: (nodeId: string) => void | Promise<void>
  onUnfold: (foldId: string) => void | Promise<void>
  onAdd: (nodeId: string) => void | Promise<void>
  onReorder: (nodeIds: string[]) => void | Promise<void>
  onOpenNode: (nodeId: string) => void
  partCountByParent: Record<string, number>
}

function getDraggedNodeId(e: React.DragEvent): string {
  return (
    e.dataTransfer.getData('application/x-goc-node-id') ||
    e.dataTransfer.getData('text/plain') ||
    ((window as any).__goc_drag_node_id || '')
  ).trim()
}

export default function ActiveContext({ activeIds, nodesById, onRemove, onUnfold, onAdd, onReorder, onOpenNode, partCountByParent }: Props) {
  const [orderedIds, setOrderedIds] = React.useState<string[]>(activeIds)
  const [draggingId, setDraggingId] = React.useState<string | null>(null)
  const [hoverIndex, setHoverIndex] = React.useState<number | null>(null)

  React.useEffect(() => {
    setOrderedIds(activeIds)
  }, [activeIds])

  function clearGlobalDraggedNodeId() {
    ;(window as any).__goc_drag_node_id = ''
  }

  function clearDragState() {
    clearGlobalDraggedNodeId()
    setDraggingId(null)
    setHoverIndex(null)
  }

  async function reorderToIndex(sourceId: string, index: number) {
    if (!orderedIds.includes(sourceId)) return
    const next = orderedIds.filter((id) => id !== sourceId)
    const boundedIndex = Math.max(0, Math.min(index, next.length))
    next.splice(boundedIndex, 0, sourceId)
    setOrderedIds(next)
    await onReorder(next)
  }

  function handleDragStart(e: React.DragEvent<HTMLDivElement>, nodeId: string) {
    setDraggingId(nodeId)
    e.dataTransfer.setData('application/x-goc-node-id', nodeId)
    e.dataTransfer.setData('text/plain', nodeId)
    e.dataTransfer.effectAllowed = 'move'
    ;(window as any).__goc_drag_node_id = nodeId
  }

  function handleDragEnd() {
    clearDragState()
  }

  async function handleDropAtIndex(e: React.DragEvent<HTMLDivElement>, targetIndex: number) {
    e.preventDefault()
    e.stopPropagation()
    const sourceId = getDraggedNodeId(e) || draggingId
    clearDragState()
    if (!sourceId) return
    if (orderedIds.includes(sourceId)) {
      await reorderToIndex(sourceId, targetIndex)
    } else {
      if (!nodesById.has(sourceId)) return
      await onAdd(sourceId)
    }
  }

  async function handleDropToAppend(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    e.stopPropagation()
    const sourceId = getDraggedNodeId(e) || draggingId
    clearDragState()
    if (!sourceId) return
    if (orderedIds.includes(sourceId)) {
      await reorderToIndex(sourceId, orderedIds.length)
    } else {
      if (!nodesById.has(sourceId)) return
      await onAdd(sourceId)
    }
  }

  async function handleDropToRemove(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault()
    e.stopPropagation()
    const sourceId = getDraggedNodeId(e) || draggingId
    clearDragState()
    if (!sourceId) return
    if (!orderedIds.includes(sourceId)) return
    await onRemove(sourceId)
  }

  return (
    <div>
      <h3>Active Context</h3>
      <div
        className="dropZone addZone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDropToAppend}
      >
        Timeline/Graph에서 여기로 드래그하면 Active에 추가
      </div>
      {orderedIds.length === 0 && <div className="muted">선택된 노드가 없습니다.</div>}
      {orderedIds.length > 0 && (
        <div
          className={`activeDropSlot ${hoverIndex === 0 ? 'isHover' : ''}`}
          onDragOver={(e) => {
            e.preventDefault()
            setHoverIndex(0)
          }}
          onDragEnter={(e) => {
            e.preventDefault()
            setHoverIndex(0)
          }}
          onDragLeave={() => {
            if (hoverIndex === 0) setHoverIndex(null)
          }}
          onDrop={(e) => handleDropAtIndex(e, 0)}
          aria-label="active-context-drop-slot-0"
        />
      )}
      {orderedIds.map((id, idx) => {
        const n = nodesById.get(id)
        if (!n) return null
        const nextIdx = idx + 1
        return (
          <React.Fragment key={id}>
            <div
              className={`card ${draggingId === id ? 'dragging' : ''}`}
              draggable
              onClick={() => onOpenNode(id)}
              onDragStart={(e) => handleDragStart(e, id)}
              onDragEnd={handleDragEnd}
              title="드래그해서 순서 재배치 가능"
            >
              <div className="muted">{n.created_at}</div>
              <div>
                <span className={`pill pillType ${pillClassForType(n.type)}`}>{n.type}</span>
                {partCountByParent[id] > 0 && <span className="pill">parts: {partCountByParent[id]}</span>}
                {(n.text || '').slice(0, 220)}
              </div>
              <div className="row" style={{ marginTop: 6 }}>
                <button className="danger" onClick={(e) => { e.stopPropagation(); onRemove(id) }}>Remove</button>
                {n.type === 'Fold' && <button onClick={(e) => { e.stopPropagation(); onUnfold(id) }}>Unfold</button>}
                <button onClick={(e) => { e.stopPropagation(); onOpenNode(id) }}>Replace with parts</button>
              </div>
            </div>
            <div
              className={`activeDropSlot ${hoverIndex === nextIdx ? 'isHover' : ''}`}
              onDragOver={(e) => {
                e.preventDefault()
                setHoverIndex(nextIdx)
              }}
              onDragEnter={(e) => {
                e.preventDefault()
                setHoverIndex(nextIdx)
              }}
              onDragLeave={() => {
                if (hoverIndex === nextIdx) setHoverIndex(null)
              }}
              onDrop={(e) => handleDropAtIndex(e, nextIdx)}
              aria-label={`active-context-drop-slot-${nextIdx}`}
            />
          </React.Fragment>
        )
      })}
      <div
        className="dropZone removeZone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDropToRemove}
      >
        여기로 드롭하면 Active Context에서 제거
      </div>
    </div>
  )
}
