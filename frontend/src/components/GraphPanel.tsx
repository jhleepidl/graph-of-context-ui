import React, { useCallback, useEffect, useMemo, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Connection,
  Edge,
  Handle,
  NodeProps,
  Node as RFNode,
  Edge as RFEdge,
  Position,
  ReactFlowInstance,
  useNodesState,
  useEdgesState,
} from 'reactflow'
import 'reactflow/dist/style.css'

type Props = {
  nodes: any[]
  edges: any[]
  activeNodeIds: string[]
  selectedNodeIds?: string[]
  onSelectionChange: (ids: string[]) => void
  onNodeClick?: (nodeId: string) => void
  onCreateEdge?: (sourceId: string, targetId: string, edgeType: string) => void | Promise<void>
  onDeleteEdges?: (edgeIds: string[]) => void | Promise<void>
  onDeleteNodes?: (nodeIds: string[]) => void | Promise<void>
}

type GraphNodeData = {
  id: string
  typeLabel: string
  role?: string
  text: string
  createdAt?: string
  active: boolean
}

function previewText(text: string, max = 80): string {
  const compact = (text || '').replace(/\s+/g, ' ').trim()
  return compact.length > max ? `${compact.slice(0, max)}...` : compact
}

function GraphNode({ data }: NodeProps<GraphNodeData>) {
  function handleDragStart(e: React.DragEvent<HTMLDivElement>) {
    e.dataTransfer.setData('application/x-goc-node-id', data.id)
    e.dataTransfer.setData('text/plain', data.id)
    e.dataTransfer.effectAllowed = 'copyMove'
    ;(window as any).__goc_drag_node_id = data.id
  }

  function handleDragEnd() {
    ;(window as any).__goc_drag_node_id = ''
  }

  return (
    <div
      className={`graphNodeCard nopan ${data.active ? 'isActive' : ''}`}
      draggable
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      title="드래그해서 Active Context로 추가"
    >
      <Handle type="target" position={Position.Top} className="graphHandle" onDragStart={(e) => e.preventDefault()} />
      <div className="graphNodeTitle">
        <span className="pill">{data.typeLabel}{data.role ? `/${data.role}` : ''}</span>
        {data.active && <span className="pill">ACTIVE</span>}
      </div>
      <div className="graphNodeSnippet">{previewText(data.text)}</div>
      <div className="graphNodeMeta">{data.createdAt || ''}</div>
      <div className="graphNodeDragToActive">
        Active로 드래그
      </div>
      <Handle type="source" position={Position.Bottom} className="graphHandle" onDragStart={(e) => e.preventDefault()} />
    </div>
  )
}

function edgePriority(t: string): number {
  if (t === 'NEXT') return 0
  if (t === 'REPLY_TO') return 1
  if (t === 'IN_RUN') return 2
  if (t === 'USED_IN_RUN') return 3
  if (t === 'FOLDS') return 4
  if (t === 'HAS_PART') return 5
  if (t === 'NEXT_PART') return 6
  if (t === 'SPLIT_FROM') return 7
  return 8
}

function edgeStyle(edgeType: string): { stroke: string; strokeWidth: number; strokeDasharray?: string } {
  if (edgeType === 'NEXT') return { stroke: '#4b5563', strokeWidth: 2 }
  if (edgeType === 'REPLY_TO') return { stroke: '#60a5fa', strokeWidth: 1.6, strokeDasharray: '4 4' }
  if (edgeType === 'IN_RUN') return { stroke: '#0ea5e9', strokeWidth: 1.5, strokeDasharray: '3 4' }
  if (edgeType === 'USED_IN_RUN') return { stroke: '#f59e0b', strokeWidth: 1.5, strokeDasharray: '3 4' }
  if (edgeType === 'FOLDS') return { stroke: '#10b981', strokeWidth: 1.5 }
  if (edgeType === 'HAS_PART') return { stroke: '#7c3aed', strokeWidth: 1.6 }
  if (edgeType === 'NEXT_PART') return { stroke: '#a855f7', strokeWidth: 1.4, strokeDasharray: '4 3' }
  if (edgeType === 'SPLIT_FROM') return { stroke: '#ec4899', strokeWidth: 1.3, strokeDasharray: '3 4' }
  return { stroke: '#9ca3af', strokeWidth: 1.4 }
}

function virtualEdgeStyle(edgeType: string): { stroke: string; strokeWidth: number; strokeDasharray?: string; opacity: number } {
  const base = edgeStyle(edgeType)
  return {
    ...base,
    opacity: 0.72,
    strokeDasharray: base.strokeDasharray || '2 4',
  }
}

function roleFromNode(n: any): string {
  if (n.type !== 'Message') return ''
  try {
    const payload = JSON.parse(n.payload_json || '{}')
    return payload?.role || ''
  } catch (_) {
    return ''
  }
}

function payloadPretty(s: string | undefined): string {
  try {
    return JSON.stringify(JSON.parse(s || '{}'), null, 2)
  } catch (_) {
    return s || '{}'
  }
}

function mergeNodePositions(prev: RFNode[], next: RFNode[]): RFNode[] {
  const prevById = new Map(prev.map((n) => [n.id, n]))
  return next.map((n) => {
    const p = prevById.get(n.id)
    if (!p) return n
    return {
      ...n,
      selected: p.selected,
    }
  })
}

const EDGE_TYPE_OPTIONS = ['NEXT', 'REPLY_TO', 'IN_RUN', 'USED_IN_RUN', 'FOLDS', 'HAS_PART', 'NEXT_PART', 'SPLIT_FROM', 'INVOKES', 'RETURNS', 'USES']
const nodeTypes = { contextNode: GraphNode }

export default function GraphPanel({
  nodes,
  edges,
  activeNodeIds,
  selectedNodeIds = [],
  onSelectionChange,
  onNodeClick,
  onCreateEdge,
  onDeleteEdges,
  onDeleteNodes,
}: Props) {
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState([])
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState([])
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null)
  const [newEdgeType, setNewEdgeType] = useState('NEXT')
  const [showFoldMembers, setShowFoldMembers] = useState(false)
  const [zoom, setZoom] = useState(1)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [lockedPanX, setLockedPanX] = useState<number | null>(null)
  const autoDetailByZoom = zoom >= 1.6
  const nodesById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes])
  const selectedNode = selectedNodeId ? nodesById.get(selectedNodeId) : null

  const visibleNodeIds = useMemo(() => {
    if (showFoldMembers || autoDetailByZoom) {
      return new Set(nodes.map((n) => n.id))
    }
    const foldIds = new Set(nodes.filter((n) => n.type === 'Fold').map((n) => n.id))
    const hidden = new Set<string>()
    for (const e of edges) {
      if (e.type === 'FOLDS' && foldIds.has(e.from_id)) {
        hidden.add(e.to_id)
      }
    }
    const out = new Set<string>()
    for (const n of nodes) {
      if (!hidden.has(n.id)) out.add(n.id)
    }
    return out
  }, [nodes, edges, showFoldMembers, autoDetailByZoom])

  const desiredNodes = useMemo(() => {
    const ordered = [...nodes]
      .filter((n) => visibleNodeIds.has(n.id))
      .sort((a, b) => {
      const av = a.created_at || ''
      const bv = b.created_at || ''
      if (av < bv) return -1
      if (av > bv) return 1
      return (a.id || '').localeCompare(b.id || '')
    })
    return ordered.map((n: any, i: number) => {
      const active = activeNodeIds.includes(n.id)
      const x = 240
      const y = 80 + i * 130
      return {
        id: n.id,
        type: 'contextNode',
        position: { x, y },
        draggable: false,
        data: {
          id: n.id,
          typeLabel: n.type,
          role: roleFromNode(n),
          text: n.text || '',
          createdAt: n.created_at,
          active,
        },
        style: {
          width: 230,
        }
      }
    })
  }, [nodes, activeNodeIds, visibleNodeIds])

  const desiredEdges = useMemo(() => {
    const hideFoldMembers = !(showFoldMembers || autoDetailByZoom)
    const nodeIds = visibleNodeIds
    const sortedEdges = [...edges].sort((a: any, b: any) => {
      const p = edgePriority(a.type) - edgePriority(b.type)
      if (p !== 0) return p
      const av = a.created_at || ''
      const bv = b.created_at || ''
      if (av < bv) return -1
      if (av > bv) return 1
      return (a.id || '').localeCompare(b.id || '')
    })

    if (!hideFoldMembers) {
      return sortedEdges
        .filter((e: any) => nodeIds.has(e.from_id) && nodeIds.has(e.to_id))
        .map((e: any) => ({
          id: e.id,
          source: e.from_id,
          target: e.to_id,
          type: 'smoothstep',
          label: e.type,
          style: edgeStyle(e.type),
          deletable: true,
          selectable: true,
        }))
    }

    const memberToFold = new Map<string, string>()
    for (const e of edges) {
      if (e.type !== 'FOLDS') continue
      if (!memberToFold.has(e.to_id)) {
        memberToFold.set(e.to_id, e.from_id)
      }
    }

    const projectNodeId = (id: string): string | null => {
      if (nodeIds.has(id)) return id
      const foldId = memberToFold.get(id)
      if (foldId && nodeIds.has(foldId)) return foldId
      return null
    }

    const out: any[] = []
    const virtualMap = new Map<string, { source: string; target: string; type: string; count: number; created_at: string }>()

    for (const e of sortedEdges) {
      if (e.type === 'FOLDS') continue

      const source = projectNodeId(e.from_id)
      const target = projectNodeId(e.to_id)
      if (!source || !target) continue
      if (source === target) continue

      const redirected = source !== e.from_id || target !== e.to_id
      if (!redirected) {
        out.push({
          id: e.id,
          source,
          target,
          type: 'smoothstep',
          label: e.type,
          style: edgeStyle(e.type),
          deletable: true,
          selectable: true,
        })
        continue
      }

      const key = `${source}|${target}|${e.type}`
      const prev = virtualMap.get(key)
      if (!prev) {
        virtualMap.set(key, {
          source,
          target,
          type: e.type,
          count: 1,
          created_at: e.created_at || '',
        })
      } else {
        prev.count += 1
        if ((e.created_at || '') < prev.created_at) {
          prev.created_at = e.created_at || prev.created_at
        }
      }
    }

    for (const [key, v] of virtualMap.entries()) {
      const label = v.count > 1 ? `${v.type} x${v.count}` : v.type
      out.push({
        id: `virtual:${key}`,
        source: v.source,
        target: v.target,
        type: 'smoothstep',
        label,
        style: virtualEdgeStyle(v.type),
        deletable: false,
        selectable: false,
      })
    }

    return out
  }, [visibleNodeIds, edges, showFoldMembers, autoDetailByZoom])

  useEffect(() => {
    setRfNodes((prev) => mergeNodePositions(prev, desiredNodes as RFNode[]))
  }, [desiredNodes, setRfNodes])

  useEffect(() => {
    setRfEdges(desiredEdges as RFEdge[])
  }, [desiredEdges, setRfEdges])

  const graphSignature = useMemo(
    () => nodes.map((n: any) => n.id).sort().join(','),
    [nodes]
  )

  useEffect(() => {
    if (!rfInstance || !rfNodes.length) return
    rfInstance.fitView({ padding: 0.2, duration: 0 })
    const v = rfInstance.getViewport()
    setLockedPanX(v.x)
  }, [rfInstance, graphSignature])

  const handleMove = useCallback((_evt: any, viewport: { x: number; y: number; zoom: number }) => {
    setZoom(viewport.zoom)
    if (!rfInstance || lockedPanX == null) return
    if (Math.abs(viewport.x - lockedPanX) > 0.5) {
      rfInstance.setViewport({ x: lockedPanX, y: viewport.y, zoom: viewport.zoom }, { duration: 0 })
    }
  }, [rfInstance, lockedPanX])

  const handleSelectionChange = useCallback((sel: { nodes?: { id: string }[] } | null | undefined) => {
    const ids = (sel?.nodes || []).map((n) => n.id)
    onSelectionChange(ids)
  }, [onSelectionChange])

  const handleNodeClick = useCallback((_evt: any, node: any) => {
    setSelectedNodeId(node?.id || null)
    if (onNodeClick && node?.id) {
      onNodeClick(node.id)
    }
  }, [onNodeClick])

  const handlePaneClick = useCallback(() => {
    setSelectedNodeId(null)
  }, [])

  const handleConnect = useCallback((conn: Connection) => {
    if (!onCreateEdge) return
    if (!conn.source || !conn.target) return
    if (conn.source === conn.target) return
    onCreateEdge(conn.source, conn.target, newEdgeType)
  }, [newEdgeType, onCreateEdge])

  const handleEdgesDelete = useCallback((deletedEdges: Edge[]) => {
    if (!onDeleteEdges) return
    const ids = deletedEdges
      .map((e) => e.id)
      .filter((id): id is string => Boolean(id) && !id.startsWith('virtual:'))
    if (ids.length === 0) return
    onDeleteEdges(ids)
  }, [onDeleteEdges])

  const handleDeleteSelectedNodes = useCallback(() => {
    if (!onDeleteNodes) return
    if (selectedNodeIds.length === 0) return
    const ok = window.confirm(`선택한 ${selectedNodeIds.length}개 노드를 삭제할까요? 연결된 edge도 함께 삭제됩니다.`)
    if (!ok) return
    onDeleteNodes(selectedNodeIds)
  }, [onDeleteNodes, selectedNodeIds])

  return (
    <div className="graphWrap">
      <div className="graphTools">
        <span className="muted">새 Edge Type</span>
        <select value={newEdgeType} onChange={(e) => setNewEdgeType(e.target.value)}>
          {EDGE_TYPE_OPTIONS.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <button onClick={() => setShowFoldMembers((v) => !v)}>
          {showFoldMembers ? 'Fold 멤버 숨기기' : 'Fold 상세 보기'}
        </button>
        <button
          className="danger"
          onClick={handleDeleteSelectedNodes}
          disabled={selectedNodeIds.length === 0}
          title={selectedNodeIds.length === 0 ? '삭제할 노드를 먼저 선택하세요.' : '선택 노드 삭제'}
        >
          Delete selected nodes ({selectedNodeIds.length})
        </button>
        <span className="muted">Zoom {zoom.toFixed(2)} {autoDetailByZoom ? '(자동 상세)' : ''}</span>
        <span className="muted">노드 카드 드래그: Active 추가 / 핸들 드래그: edge 추가 / edge 선택 후 Delete: 삭제 / 드래그 선택: Fold 대상 선택</span>
        <span className="muted">Fold 축약 상태에서는 멤버의 외부 연결이 Fold 노드로 자동 연결되어 표시됩니다.</span>
      </div>
      {selectedNode && (
        <div className="graphDetail">
          <div><b>{selectedNode.type}</b> <span className="muted">({selectedNode.id.slice(0, 6)})</span></div>
          <div className="muted">{selectedNode.created_at}</div>
          <pre>{selectedNode.text || '(empty)'}</pre>
          <pre>{payloadPretty(selectedNode.payload_json)}</pre>
        </div>
      )}
      <div className="graphCanvas">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodesDraggable={false}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onInit={setRfInstance}
        onMove={handleMove}
        onSelectionChange={handleSelectionChange}
        onNodeClick={handleNodeClick}
        onPaneClick={handlePaneClick}
        onConnect={handleConnect}
        onEdgesDelete={handleEdgesDelete}
        deleteKeyCode={['Backspace', 'Delete']}
      >
        <Background />
        <MiniMap />
        <Controls />
      </ReactFlow>
      </div>
    </div>
  )
}
