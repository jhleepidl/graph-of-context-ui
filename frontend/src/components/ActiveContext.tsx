import React from 'react'
import {
  priorityBucketLabel,
  priorityBucketPillClass,
  scoreNodesForRequest,
  type NodePriorityScore,
} from '../utils/contextPriority'

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
  allNodes?: any[]
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

export default function ActiveContext({ activeIds, nodesById, allNodes = [], onRemove, onUnfold, onAdd, onReorder, onOpenNode, partCountByParent }: Props) {
  const [orderedIds, setOrderedIds] = React.useState<string[]>(activeIds)
  const [draggingId, setDraggingId] = React.useState<string | null>(null)
  const [hoverIndex, setHoverIndex] = React.useState<number | null>(null)
  const [priorityQuery, setPriorityQuery] = React.useState('')
  const [sortMode, setSortMode] = React.useState<'manual' | 'priority'>('manual')
  const [showPriorityMeta, setShowPriorityMeta] = React.useState(false)

  React.useEffect(() => {
    setOrderedIds(activeIds)
  }, [activeIds])

  const activeNodes = React.useMemo(() => {
    return orderedIds
      .map((id) => nodesById.get(id))
      .filter((n): n is any => Boolean(n?.id))
  }, [orderedIds, nodesById])

  const priorityCorpusNodes = React.useMemo(() => {
    const base = (allNodes && allNodes.length > 0 ? allNodes : activeNodes)
      .filter((n: any) => Boolean(n?.id))
    const seen = new Set<string>()
    return base.filter((n: any) => {
      if (seen.has(n.id)) return false
      seen.add(n.id)
      return true
    })
  }, [allNodes, activeNodes])

  const activeScoreById = React.useMemo(() => {
    const scored = scoreNodesForRequest(priorityCorpusNodes, priorityQuery)
    const byId = new Map<string, NodePriorityScore>()
    for (const s of scored) {
      if (orderedIds.includes(s.node.id)) byId.set(s.node.id, s)
    }
    return byId
  }, [priorityCorpusNodes, priorityQuery, orderedIds])

  const prioritySortedIds = React.useMemo(() => {
    return [...orderedIds].sort((a, b) => {
      const as = activeScoreById.get(a)
      const bs = activeScoreById.get(b)
      if (!as && !bs) return 0
      if (!as) return 1
      if (!bs) return -1
      if (as.bucket !== bs.bucket) {
        const rank = (bucket: NodePriorityScore['bucket']) => (bucket === 'must' ? 3 : bucket === 'recommended' ? 2 : bucket === 'optional' ? 1 : 0)
        return rank(bs.bucket) - rank(as.bucket)
      }
      return bs.priority - as.priority
    })
  }, [orderedIds, activeScoreById])

  const visibleIds = sortMode === 'priority' ? prioritySortedIds : orderedIds

  async function applyPriorityOrdering() {
    if (sortMode !== 'priority') return
    if (prioritySortedIds.length === 0) return
    setOrderedIds(prioritySortedIds)
    await onReorder(prioritySortedIds)
    setSortMode('manual')
  }

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
      <div className="muted" style={{ marginBottom: 8 }}>카드 클릭으로 팝업이 열리지 않습니다. 버튼으로 상세/분할, 드래그로 순서 변경.</div>
      <div className="row" style={{ marginBottom: 8 }}>
        <span className="muted">View</span>
        <button className={sortMode === 'manual' ? 'primary' : ''} onClick={() => setSortMode('manual')}>Manual order</button>
        <button className={sortMode === 'priority' ? 'primary' : ''} onClick={() => setSortMode('priority')}>Priority order</button>
        {sortMode === 'priority' && (
          <>
            <input
              value={priorityQuery}
              onChange={(e) => setPriorityQuery(e.target.value)}
              placeholder="요청/질문 기준으로 우선순위 정렬"
              style={{ flex: 1, minWidth: 180, padding: 6, borderRadius: 10, border: '1px solid #d1d5db' }}
            />
            <button onClick={() => setShowPriorityMeta((v) => !v)}>
              {showPriorityMeta ? 'Hide scores' : 'Show scores'}
            </button>
            <button onClick={applyPriorityOrdering}>Apply priority to Active</button>
          </>
        )}
      </div>
      <div
        className="dropZone addZone"
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDropToAppend}
      >
        Timeline/Graph에서 여기로 드래그하면 Active에 추가
      </div>
      {visibleIds.length === 0 && <div className="muted">선택된 노드가 없습니다.</div>}
      {visibleIds.length > 0 && sortMode === 'manual' && (
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
      {visibleIds.map((id, idx) => {
        const n = nodesById.get(id)
        if (!n) return null
        const nextIdx = idx + 1
        const score = activeScoreById.get(id)
        return (
          <React.Fragment key={id}>
            <div
              className={`card ${draggingId === id ? 'dragging' : ''}`}
              draggable={sortMode === 'manual'}
              onDragStart={sortMode === 'manual' ? (e) => handleDragStart(e, id) : undefined}
              onDragEnd={sortMode === 'manual' ? handleDragEnd : undefined}
              title="드래그해서 순서 재배치 가능"
            >
              <div className="muted">{n.created_at}</div>
              <div>
                <span className={`pill pillType ${pillClassForType(n.type)}`}>{n.type}</span>
                {partCountByParent[id] > 0 && <span className="pill">parts: {partCountByParent[id]}</span>}
                {sortMode === 'priority' && score && (
                  <>
                    <span className={`pill ${priorityBucketPillClass(score.bucket)}`}>{priorityBucketLabel(score.bucket)}</span>
                    {showPriorityMeta && <span className="pill">P {Math.round(score.priority * 100)}%</span>}
                  </>
                )}
                {(n.text || '').slice(0, 220)}
              </div>
              {sortMode === 'priority' && showPriorityMeta && score && score.reasons.length > 0 && (
                <div className="muted" style={{ marginTop: 6 }}>{score.reasons.join(' · ')}</div>
              )}
              <div className="row" style={{ marginTop: 6 }}>
                <button className="danger" onClick={(e) => { e.stopPropagation(); onRemove(id) }}>Remove</button>
                {n.type === 'Fold' && <button onClick={(e) => { e.stopPropagation(); onUnfold(id) }}>Unfold</button>}
                <button onClick={(e) => { e.stopPropagation(); onOpenNode(id) }}>Detail / Split</button>
              </div>
            </div>
            {sortMode === 'manual' && (
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
            )}
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
