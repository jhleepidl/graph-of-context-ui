import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
  SelectionMode,
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
  onNodeOpenDetail?: (nodeId: string) => void
  onCreateEdge?: (sourceId: string, targetId: string, edgeType: string) => void | Promise<void>
  onDeleteEdges?: (edgeIds: string[]) => void | Promise<void>
  onDeleteNodes?: (nodeIds: string[]) => void | Promise<void>
  onFoldSelected?: (nodeIds: string[]) => void | Promise<void>
  onActivateNodes?: (nodeIds: string[]) => void | Promise<void>
  onDeactivateNodes?: (nodeIds: string[]) => void | Promise<void>
  onCommitUnfold?: (foldId: string) => void | Promise<void>
  onSaveLayout?: (positions: Array<{ id: string; x: number; y: number }>) => void | Promise<void>
  layoutScopeKey?: string | null
}

type GraphNodeData = {
  id: string
  typeLabel: string
  role?: string
  text: string
  createdAt?: string
  active: boolean
  toneClass?: string
  expandedFold?: boolean
  expandedMember?: boolean
  pendingLinkSource?: boolean
  layoutEditable?: boolean
}

type ViewportState = {
  x: number
  y: number
  zoom: number
}

type Bounds = {
  minX: number
  minY: number
  maxX: number
  maxY: number
  centerX: number
  centerY: number
}

const LEGACY_EDGE_TYPE_OPTIONS = ['NEXT', 'REPLY_TO', 'ATTACHED_TO', 'REFERENCES', 'RELATED', 'SUPPORTS', 'IN_RUN', 'USED_IN_RUN', 'FOLDS', 'HAS_PART', 'NEXT_PART', 'SPLIT_FROM', 'INVOKES', 'RETURNS', 'USES']
const LINK_EDGE_TYPE_OPTIONS = ['RELATED', 'REPLY_TO', 'SUPPORTS', 'REFERENCES', 'ATTACHED_TO']
const nodeTypes = { contextNode: GraphNode }

function shortId(id: string): string {
  return id.slice(0, 6)
}

function previewText(text: string, max = 80): string {
  const compact = (text || '').replace(/\s+/g, ' ').trim()
  return compact.length > max ? `${compact.slice(0, max)}...` : compact
}

function nodeToneClass(typeLabel: string, role?: string): string {
  if (typeLabel === 'Resource') return 'tone-resource'
  if (typeLabel === 'Fold') return 'tone-fold'
  if (typeLabel === 'Decision') return 'tone-decision'
  if (typeLabel === 'Assumption') return 'tone-assumption'
  if (typeLabel === 'Plan') return 'tone-plan'
  if (typeLabel === 'ContextCandidate') return 'tone-candidate'
  if (typeLabel === 'Message' && role === 'user') return 'tone-user'
  if (typeLabel === 'Message' && role === 'assistant') return 'tone-assistant'
  return 'tone-default'
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

function readNodeUiPosition(n: any): { x: number; y: number } | null {
  try {
    const payload = JSON.parse(n?.payload_json || '{}')
    const pos = payload?._ui_pos
    const x = Number(pos?.x)
    const y = Number(pos?.y)
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null
    return { x, y }
  } catch (_) {
    return null
  }
}

function payloadPretty(s: string | undefined): string {
  try {
    return JSON.stringify(JSON.parse(s || '{}'), null, 2)
  } catch (_) {
    return s || '{}'
  }
}

function parseEdgeIndex(edge: any): number {
  try {
    const payload = JSON.parse(edge?.payload_json || '{}')
    const n = Number(payload?.index)
    return Number.isFinite(n) ? n : 0
  } catch {
    return 0
  }
}

function edgePriority(t: string): number {
  if (t === 'NEXT') return 0
  if (t === 'REPLY_TO') return 1
  if (t === 'RELATED') return 2
  if (t === 'SUPPORTS') return 3
  if (t === 'REFERENCES') return 4
  if (t === 'ATTACHED_TO') return 5
  if (t === 'IN_RUN') return 6
  if (t === 'USED_IN_RUN') return 7
  if (t === 'FOLDS') return 8
  if (t === 'HAS_PART') return 9
  if (t === 'NEXT_PART') return 10
  if (t === 'SPLIT_FROM') return 11
  return 12
}

function edgeStyle(edgeType: string): { stroke: string; strokeWidth: number; strokeDasharray?: string } {
  if (edgeType === 'NEXT') return { stroke: '#4b5563', strokeWidth: 2 }
  if (edgeType === 'REPLY_TO') return { stroke: '#60a5fa', strokeWidth: 1.6, strokeDasharray: '4 4' }
  if (edgeType === 'RELATED') return { stroke: '#0ea5e9', strokeWidth: 1.6 }
  if (edgeType === 'SUPPORTS') return { stroke: '#22c55e', strokeWidth: 1.6 }
  if (edgeType === 'REFERENCES') return { stroke: '#f97316', strokeWidth: 1.5, strokeDasharray: '5 4' }
  if (edgeType === 'ATTACHED_TO') return { stroke: '#0891b2', strokeWidth: 1.6, strokeDasharray: '6 4' }
  if (edgeType === 'IN_RUN') return { stroke: '#0284c7', strokeWidth: 1.5, strokeDasharray: '3 4' }
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

function viewFoldEdgeStyle(): { stroke: string; strokeWidth: number; strokeDasharray: string; opacity: number } {
  return {
    stroke: '#059669',
    strokeWidth: 1.3,
    strokeDasharray: '4 4',
    opacity: 0.66,
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

function getNodeCenter(nodes: RFNode[]): { x: number; y: number } | null {
  const bounds = getBounds(nodes)
  if (!bounds) return null
  return { x: bounds.centerX, y: bounds.centerY }
}

function getBounds(nodes: RFNode[]): Bounds | null {
  if (!nodes.length) return null

  let minX = Number.POSITIVE_INFINITY
  let minY = Number.POSITIVE_INFINITY
  let maxX = Number.NEGATIVE_INFINITY
  let maxY = Number.NEGATIVE_INFINITY

  for (const n of nodes) {
    const x = n.positionAbsolute?.x ?? n.position.x
    const y = n.positionAbsolute?.y ?? n.position.y
    const width = typeof n.width === 'number' ? n.width : 230
    const height = typeof n.height === 'number' ? n.height : 100

    if (x < minX) minX = x
    if (y < minY) minY = y
    if (x + width > maxX) maxX = x + width
    if (y + height > maxY) maxY = y + height
  }

  if (!Number.isFinite(minX) || !Number.isFinite(minY) || !Number.isFinite(maxX) || !Number.isFinite(maxY)) {
    return null
  }

  return {
    minX,
    minY,
    maxX,
    maxY,
    centerX: (minX + maxX) / 2,
    centerY: (minY + maxY) / 2,
  }
}

function getSelectedBounds(nodes: RFNode[], selectedIds: string[]): Bounds | null {
  if (selectedIds.length === 0) return null
  const selectedSet = new Set(selectedIds)
  const selectedNodes = nodes.filter((n) => selectedSet.has(n.id))
  return getBounds(selectedNodes)
}

function GraphNode({ data }: NodeProps<GraphNodeData>) {
  function handleActiveDragStart(e: React.DragEvent<HTMLButtonElement>) {
    e.stopPropagation()
    e.dataTransfer.setData('application/x-goc-node-id', data.id)
    e.dataTransfer.setData('text/plain', data.id)
    e.dataTransfer.effectAllowed = 'copyMove'
    ;(window as any).__goc_drag_node_id = data.id
  }

  function handleActiveDragEnd() {
    ;(window as any).__goc_drag_node_id = ''
  }

  return (
    <div
      className={`graphNodeCard nopan ${data.active ? 'isActive' : ''} ${data.toneClass || 'tone-default'} ${data.expandedFold ? 'isExpandedFold' : ''} ${data.expandedMember ? 'isExpandedMember' : ''} ${data.pendingLinkSource ? 'isLinkSource' : ''} ${data.layoutEditable ? 'isLayoutEditable' : ''}`}
      title="클릭: 선택 · 더블클릭: 상세/분할 또는 Fold view-unfold · 카드 이동: 노드 드래그 · Active 추가: 아래 버튼 드래그"
    >
      <Handle type="target" position={Position.Top} className="graphHandle" onDragStart={(e) => e.preventDefault()} />
      <span className={`graphNodeActiveDot ${data.active ? 'on' : 'off'}`} />
      {data.pendingLinkSource && <span className="graphNodeLinkSourceBadge">Link source</span>}
      <div className="graphNodeTitle">
        <span className={`pill pillType ${(data.toneClass || 'tone-default').replace('tone-', 'pill--')}`}>{data.typeLabel}{data.role ? `/${data.role}` : ''}</span>
        {data.expandedFold && <span className="pill">view expanded</span>}
        {data.expandedMember && <span className="pill">member</span>}
      </div>
      <div className="graphNodeSnippet">{previewText(data.text)}</div>
      <div className="graphNodeMeta">{data.createdAt || ''}</div>
      <button
        className="graphNodeDragToActive nodrag nopan"
        draggable
        onDragStart={handleActiveDragStart}
        onDragEnd={handleActiveDragEnd}
        onMouseDown={(e) => e.stopPropagation()}
        type="button"
        title="드래그해서 Active Context에 추가"
      >
        + Active로 드래그
      </button>
      <Handle type="source" position={Position.Bottom} className="graphHandle" onDragStart={(e) => e.preventDefault()} />
    </div>
  )
}

export default function GraphPanel({
  nodes,
  edges,
  activeNodeIds,
  selectedNodeIds = [],
  onSelectionChange,
  onNodeOpenDetail,
  onCreateEdge,
  onDeleteEdges,
  onDeleteNodes,
  onFoldSelected,
  onActivateNodes,
  onDeactivateNodes,
  onCommitUnfold,
  onSaveLayout,
  layoutScopeKey,
}: Props) {
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState([])
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState([])
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null)

  const [newEdgeType, setNewEdgeType] = useState('NEXT')
  const [showFoldMembers, setShowFoldMembers] = useState(false)
  const [nodeTypeFilter, setNodeTypeFilter] = useState<'all' | 'resources' | 'non_resources'>('all')
  const [zoom, setZoom] = useState(1)
  const [viewport, setViewport] = useState<ViewportState>({ x: 0, y: 0, zoom: 1 })

  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)

  const [viewExpandedFoldIds, setViewExpandedFoldIds] = useState<string[]>([])
  const [viewExpandedMembersByFoldId, setViewExpandedMembersByFoldId] = useState<Record<string, string[]>>({})

  const [menuOpen, setMenuOpen] = useState(false)
  const [linkPopoverOpen, setLinkPopoverOpen] = useState(false)
  const [linkType, setLinkType] = useState('RELATED')
  const [linkDirection, setLinkDirection] = useState<'ab' | 'ba'>('ab')
  const [pendingLinkSourceId, setPendingLinkSourceId] = useState<string | null>(null)

  const [actionBusy, setActionBusy] = useState(false)
  const [actionError, setActionError] = useState('')
  const [layoutMode, setLayoutMode] = useState<'manual' | 'auto'>('manual')
  const [manualPositionsById, setManualPositionsById] = useState<Record<string, { x: number; y: number }>>({})
  const [layoutSaving, setLayoutSaving] = useState(false)
  const [layoutSaveError, setLayoutSaveError] = useState('')

  const wrapRef = useRef<HTMLDivElement | null>(null)
  const lastZoomRef = useRef<number | null>(null)
  const skipNextMoveRef = useRef(false)
  const layoutSaveTimerRef = useRef<number | null>(null)
  const pendingLayoutPositionsRef = useRef<Array<{ id: string; x: number; y: number }> | null>(null)
  const lastSavedLayoutHashRef = useRef<string>('')
  const initialFitDoneRef = useRef(false)

  const autoDetailByZoom = zoom >= 1.6
  const activeSet = useMemo(() => new Set(activeNodeIds), [activeNodeIds])
  const selectedSet = useMemo(() => new Set(selectedNodeIds), [selectedNodeIds])

  const nodesById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes])
  const selectedNodes = useMemo(() => selectedNodeIds.map((id) => nodesById.get(id)).filter(Boolean), [selectedNodeIds, nodesById])
  const singleSelectedNode = selectedNodes.length === 1 ? selectedNodes[0] : null
  const singleSelectedFoldId = singleSelectedNode && singleSelectedNode.type === 'Fold' ? singleSelectedNode.id : null

  const hasInactiveSelected = useMemo(() => selectedNodeIds.some((id) => !activeSet.has(id)), [selectedNodeIds, activeSet])
  const hasActiveSelected = useMemo(() => selectedNodeIds.some((id) => activeSet.has(id)), [selectedNodeIds, activeSet])

  const foldMembersByFoldId = useMemo(() => {
    const byFold = new Map<string, string[]>()
    const foldEdges = [...edges]
      .filter((e: any) => e.type === 'FOLDS')
      .sort((a: any, b: any) => {
        const ia = parseEdgeIndex(a)
        const ib = parseEdgeIndex(b)
        if (ia !== ib) return ia - ib
        const av = a.created_at || ''
        const bv = b.created_at || ''
        if (av < bv) return -1
        if (av > bv) return 1
        return (a.id || '').localeCompare(b.id || '')
      })

    for (const e of foldEdges) {
      const foldId = e.from_id
      const memberId = e.to_id
      if (!foldId || !memberId) continue
      const arr = byFold.get(foldId) || []
      arr.push(memberId)
      byFold.set(foldId, arr)
    }

    return byFold
  }, [edges])

  const memberToFold = useMemo(() => {
    const out = new Map<string, string>()
    for (const [foldId, members] of foldMembersByFoldId.entries()) {
      for (const memberId of members) {
        if (!out.has(memberId)) {
          out.set(memberId, foldId)
        }
      }
    }
    return out
  }, [foldMembersByFoldId])

  const expandedFoldSet = useMemo(() => new Set(viewExpandedFoldIds), [viewExpandedFoldIds])
  const expandedMemberSet = useMemo(() => {
    const out = new Set<string>()
    for (const foldId of viewExpandedFoldIds) {
      const members = viewExpandedMembersByFoldId[foldId] || foldMembersByFoldId.get(foldId) || []
      for (const memberId of members) out.add(memberId)
    }
    return out
  }, [viewExpandedFoldIds, viewExpandedMembersByFoldId, foldMembersByFoldId])

  useEffect(() => {
    const validFoldIds = new Set(foldMembersByFoldId.keys())

    setViewExpandedFoldIds((prev) => {
      const next = prev.filter((id) => validFoldIds.has(id))
      if (next.length === prev.length && next.every((id, i) => prev[i] === id)) {
        return prev
      }
      return next
    })

    setViewExpandedMembersByFoldId((prev) => {
      let changed = false
      const next: Record<string, string[]> = {}
      for (const foldId of Object.keys(prev)) {
        if (!validFoldIds.has(foldId)) {
          changed = true
          continue
        }
        const members = prev[foldId] || []
        const validMembers = new Set(foldMembersByFoldId.get(foldId) || [])
        const filtered = members.filter((m) => validMembers.has(m))
        if (filtered.length !== members.length) changed = true
        next[foldId] = filtered
      }
      return changed ? next : prev
    })
  }, [foldMembersByFoldId])


  useEffect(() => {
    initialFitDoneRef.current = false
    lastSavedLayoutHashRef.current = ''
    setLayoutSaveError('')
    setManualPositionsById({})
    if (layoutSaveTimerRef.current != null) {
      window.clearTimeout(layoutSaveTimerRef.current)
      layoutSaveTimerRef.current = null
    }
    pendingLayoutPositionsRef.current = null
  }, [layoutScopeKey])

  useEffect(() => {
    setManualPositionsById((prev) => {
      let changed = false
      const next = { ...prev }
      const validIds = new Set(nodes.map((n) => n.id))

      for (const n of nodes) {
        if (next[n.id]) continue
        const uiPos = readNodeUiPosition(n)
        if (!uiPos) continue
        next[n.id] = uiPos
        changed = true
      }

      for (const id of Object.keys(next)) {
        if (validIds.has(id)) continue
        delete next[id]
        changed = true
      }

      return changed ? next : prev
    })
  }, [nodes])

  useEffect(() => {
    return () => {
      if (layoutSaveTimerRef.current != null) {
        window.clearTimeout(layoutSaveTimerRef.current)
        layoutSaveTimerRef.current = null
      }
    }
  }, [])

  const flushQueuedLayoutSave = useCallback(async () => {
    if (!onSaveLayout) return
    const positions = pendingLayoutPositionsRef.current
    if (!positions || positions.length === 0) return

    const hash = positions
      .map((p) => `${p.id}:${Math.round(p.x)}:${Math.round(p.y)}`)
      .sort()
      .join('|')

    if (hash && hash === lastSavedLayoutHashRef.current) {
      pendingLayoutPositionsRef.current = null
      return
    }

    setLayoutSaving(true)
    setLayoutSaveError('')
    try {
      await onSaveLayout(positions)
      lastSavedLayoutHashRef.current = hash
      pendingLayoutPositionsRef.current = null
    } catch (e: any) {
      setLayoutSaveError(e?.message || String(e))
    } finally {
      setLayoutSaving(false)
    }
  }, [onSaveLayout])

  const queueLayoutSave = useCallback((positions: Array<{ id: string; x: number; y: number }>) => {
    if (!onSaveLayout) return
    pendingLayoutPositionsRef.current = positions
    if (layoutSaveTimerRef.current != null) {
      window.clearTimeout(layoutSaveTimerRef.current)
    }
    layoutSaveTimerRef.current = window.setTimeout(() => {
      layoutSaveTimerRef.current = null
      void flushQueuedLayoutSave()
    }, 650)
  }, [onSaveLayout, flushQueuedLayoutSave])

  const saveCurrentLayoutNow = useCallback(() => {
    if (!rfInstance || !onSaveLayout) return
    const positions = rfInstance.getNodes().map((n) => ({
      id: n.id,
      x: n.position.x,
      y: n.position.y,
    }))
    pendingLayoutPositionsRef.current = positions
    if (layoutSaveTimerRef.current != null) {
      window.clearTimeout(layoutSaveTimerRef.current)
      layoutSaveTimerRef.current = null
    }
    void flushQueuedLayoutSave()
  }, [rfInstance, onSaveLayout, flushQueuedLayoutSave])

  useEffect(() => {
    if (selectedNodeIds.length > 0) return
    setMenuOpen(false)
    setLinkPopoverOpen(false)
    setPendingLinkSourceId(null)
  }, [selectedNodeIds])

  const visibleNodeIds = useMemo(() => {
    const passesTypeFilter = (n: any) => {
      if (nodeTypeFilter === 'resources') return n.type === 'Resource'
      if (nodeTypeFilter === 'non_resources') return n.type !== 'Resource'
      return true
    }

    if (showFoldMembers || autoDetailByZoom) {
      return new Set(nodes.filter(passesTypeFilter).map((n) => n.id))
    }

    const out = new Set<string>()
    for (const n of nodes) {
      if (!passesTypeFilter(n)) continue
      const foldId = memberToFold.get(n.id)
      if (!foldId) {
        out.add(n.id)
        continue
      }
      if (expandedFoldSet.has(foldId)) {
        out.add(n.id)
      }
    }
    return out
  }, [nodes, showFoldMembers, autoDetailByZoom, nodeTypeFilter, memberToFold, expandedFoldSet])

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

    const autoPositionById = new Map<string, { x: number; y: number }>()
    for (let i = 0; i < ordered.length; i += 1) {
      autoPositionById.set(ordered[i].id, { x: 250, y: 90 + i * 140 })
    }

    for (const foldId of viewExpandedFoldIds) {
      if (!visibleNodeIds.has(foldId)) continue
      const foldPos = autoPositionById.get(foldId)
      if (!foldPos) continue

      const members = (viewExpandedMembersByFoldId[foldId] || foldMembersByFoldId.get(foldId) || [])
        .filter((memberId) => visibleNodeIds.has(memberId))

      const count = members.length
      if (count === 0) continue

      for (let i = 0; i < count; i += 1) {
        const memberId = members[i]
        const t = count === 1 ? 0.5 : i / (count - 1)
        const angle = (-0.72 + 1.44 * t) * Math.PI * 0.72
        const radius = 180 + Math.floor(i / 6) * 58
        autoPositionById.set(memberId, {
          x: foldPos.x + 300 + Math.cos(angle) * radius * 0.7,
          y: foldPos.y + Math.sin(angle) * radius,
        })
      }
    }

    return ordered.map((n: any) => {
      const role = roleFromNode(n)
      const active = activeSet.has(n.id)
      const expandedFold = expandedFoldSet.has(n.id)
      const expandedMember = expandedMemberSet.has(n.id)

      return {
        id: n.id,
        type: 'contextNode',
        className: `${expandedFold ? 'is-expanded-fold' : ''} ${expandedMember ? 'is-expanded-member' : ''}`.trim(),
        position: (layoutMode === 'manual' ? (manualPositionsById[n.id] || readNodeUiPosition(n)) : null) || autoPositionById.get(n.id) || { x: 250, y: 90 },
        selected: selectedSet.has(n.id),
        draggable: layoutMode === 'manual',
        data: {
          id: n.id,
          typeLabel: n.type,
          role,
          text: n.text || '',
          createdAt: n.created_at,
          active,
          toneClass: nodeToneClass(n.type, role),
          expandedFold,
          expandedMember,
          pendingLinkSource: pendingLinkSourceId === n.id,
          layoutEditable: layoutMode === 'manual',
        },
        style: {
          width: 230,
        },
      }
    })
  }, [nodes, visibleNodeIds, viewExpandedFoldIds, viewExpandedMembersByFoldId, foldMembersByFoldId, activeSet, selectedSet, expandedFoldSet, expandedMemberSet, pendingLinkSourceId, layoutMode, manualPositionsById])

  const desiredEdges = useMemo(() => {
    const collapsedMode = !(showFoldMembers || autoDetailByZoom)
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

    const projectNodeId = (id: string): string | null => {
      if (nodeIds.has(id)) return id
      const foldId = memberToFold.get(id)
      if (foldId && nodeIds.has(foldId)) return foldId
      return null
    }

    const out: any[] = []
    const virtualMap = new Map<string, { source: string; target: string; type: string; count: number; created_at: string }>()

    for (const e of sortedEdges) {
      if (e.type === 'FOLDS') {
        if (collapsedMode) {
          if (expandedFoldSet.has(e.from_id) && nodeIds.has(e.from_id) && nodeIds.has(e.to_id)) {
            out.push({
              id: `view-fold:${e.id}`,
              source: e.from_id,
              target: e.to_id,
              type: 'smoothstep',
              label: 'FOLDS',
              style: viewFoldEdgeStyle(),
              deletable: false,
              selectable: false,
            })
          }
          continue
        }

        if (nodeIds.has(e.from_id) && nodeIds.has(e.to_id)) {
          out.push({
            id: e.id,
            source: e.from_id,
            target: e.to_id,
            type: 'smoothstep',
            label: e.type,
            style: edgeStyle(e.type),
            deletable: true,
            selectable: true,
          })
        }
        continue
      }

      if (!collapsedMode) {
        if (nodeIds.has(e.from_id) && nodeIds.has(e.to_id)) {
          out.push({
            id: e.id,
            source: e.from_id,
            target: e.to_id,
            type: 'smoothstep',
            label: e.type,
            style: edgeStyle(e.type),
            deletable: true,
            selectable: true,
          })
        }
        continue
      }

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
  }, [visibleNodeIds, edges, showFoldMembers, autoDetailByZoom, memberToFold, expandedFoldSet])

  useEffect(() => {
    setRfNodes((prev) => mergeNodePositions(prev, desiredNodes as RFNode[]))
  }, [desiredNodes, setRfNodes])

  useEffect(() => {
    setRfEdges(desiredEdges as RFEdge[])
  }, [desiredEdges, setRfEdges])

  useEffect(() => {
    setRfNodes((prev) => {
      let changed = false
      const next = prev.map((n) => {
        const shouldSelected = selectedSet.has(n.id)
        if (n.selected === shouldSelected) return n
        changed = true
        return { ...n, selected: shouldSelected }
      })
      return changed ? next : prev
    })
  }, [selectedSet, setRfNodes])

  const graphSignature = useMemo(
    () => `${nodes.map((n: any) => n.id).sort().join(',')}|${edges.map((e: any) => e.id).sort().join(',')}`,
    [nodes, edges],
  )

  const fitViewNow = useCallback(() => {
    if (!rfInstance || !rfNodes.length) return
    rfInstance.fitView({ padding: 0.2, duration: 180 })
    const v = rfInstance.getViewport()
    setViewport({ x: v.x, y: v.y, zoom: v.zoom })
    setZoom(v.zoom)
    lastZoomRef.current = v.zoom
  }, [rfInstance, rfNodes.length])

  useEffect(() => {
    if (!rfInstance || !rfNodes.length) return
    if (initialFitDoneRef.current) return
    initialFitDoneRef.current = true
    rfInstance.fitView({ padding: 0.2, duration: 0 })
    const v = rfInstance.getViewport()
    setViewport({ x: v.x, y: v.y, zoom: v.zoom })
    setZoom(v.zoom)
    lastZoomRef.current = v.zoom
  }, [rfInstance, graphSignature, rfNodes.length])

  const selectionBounds = useMemo(() => {
    if (!rfInstance || selectedNodeIds.length === 0) return null
    return getSelectedBounds(rfInstance.getNodes(), selectedNodeIds)
  }, [rfInstance, rfNodes, selectedNodeIds])

  const selectionAnchor = useMemo(() => {
    if (!selectionBounds) return null
    return {
      x: selectionBounds.centerX * viewport.zoom + viewport.x,
      y: selectionBounds.centerY * viewport.zoom + viewport.y,
    }
  }, [selectionBounds, viewport])

  const selectionHull = useMemo(() => {
    if (!selectionBounds || selectedNodeIds.length < 2) return null
    const padding = 14
    const left = selectionBounds.minX * viewport.zoom + viewport.x - padding
    const top = selectionBounds.minY * viewport.zoom + viewport.y - padding
    const width = (selectionBounds.maxX - selectionBounds.minX) * viewport.zoom + padding * 2
    const height = (selectionBounds.maxY - selectionBounds.minY) * viewport.zoom + padding * 2
    return {
      left,
      top,
      width,
      height,
      centerX: left + width / 2,
      centerY: top + height / 2,
    }
  }, [selectionBounds, selectedNodeIds.length, viewport])

  const executeAction = useCallback(async (fn: () => Promise<void> | void) => {
    setActionError('')
    try {
      setActionBusy(true)
      await fn()
    } catch (e: any) {
      setActionError(e?.message || String(e))
    } finally {
      setActionBusy(false)
    }
  }, [])

  const resolveFoldMembers = useCallback((foldId: string): string[] => {
    return [...(foldMembersByFoldId.get(foldId) || [])]
  }, [foldMembersByFoldId])

  const toggleViewUnfold = useCallback((foldId: string) => {
    const members = resolveFoldMembers(foldId)
    setViewExpandedMembersByFoldId((prev) => ({
      ...prev,
      [foldId]: members,
    }))
    setViewExpandedFoldIds((prev) => {
      if (prev.includes(foldId)) {
        return prev.filter((id) => id !== foldId)
      }
      return [...prev, foldId]
    })
  }, [resolveFoldMembers])

  const handleMove = useCallback((_evt: any, nextViewport: { x: number; y: number; zoom: number }) => {
    setZoom(nextViewport.zoom)
    setViewport({ x: nextViewport.x, y: nextViewport.y, zoom: nextViewport.zoom })

    if (skipNextMoveRef.current) {
      skipNextMoveRef.current = false
      lastZoomRef.current = nextViewport.zoom
      return
    }

    if (!rfInstance) return

    const prevZoom = lastZoomRef.current
    const zoomChanged = prevZoom == null || Math.abs(nextViewport.zoom - prevZoom) > 0.0001
    lastZoomRef.current = nextViewport.zoom

    if (zoomChanged) {
      const center = getNodeCenter(rfInstance.getNodes())
      if (center) {
        skipNextMoveRef.current = true
        rfInstance.setCenter(center.x, center.y, { zoom: nextViewport.zoom, duration: 0 })
        const v = rfInstance.getViewport()
        setViewport({ x: v.x, y: v.y, zoom: v.zoom })
      }
    }
  }, [rfInstance])

  const handleNodeDragStop = useCallback((_evt: any, node: any) => {
    if (layoutMode !== 'manual') return
    if (!node?.id) return

    setManualPositionsById((prev) => ({
      ...prev,
      [node.id]: { x: node.position.x, y: node.position.y },
    }))

    if (!rfInstance || !onSaveLayout) return
    const positions = rfInstance.getNodes().map((n) => ({
      id: n.id,
      x: n.position.x,
      y: n.position.y,
    }))
    queueLayoutSave(positions)
  }, [layoutMode, rfInstance, onSaveLayout, queueLayoutSave])

  const handleSelectionChange = useCallback((sel: { nodes?: { id: string }[] } | null | undefined) => {
    const ids = (sel?.nodes || []).map((n) => n.id)
    onSelectionChange(ids)
    if (ids.length > 0) {
      setSelectedNodeId(ids[ids.length - 1])
    }
  }, [onSelectionChange])

  const handleNodeClick = useCallback((evt: any, node: any) => {
    if (!node?.id) return

    wrapRef.current?.focus()
    setSelectedNodeId(node.id)

    if (pendingLinkSourceId && pendingLinkSourceId !== node.id) {
      onSelectionChange([pendingLinkSourceId, node.id])
      setPendingLinkSourceId(null)
      setMenuOpen(false)
      setLinkPopoverOpen(true)
      setLinkDirection('ab')
      return
    }

    const shiftPressed = Boolean(evt?.shiftKey)
    if (shiftPressed) {
      if (selectedSet.has(node.id)) {
        const next = selectedNodeIds.filter((id) => id !== node.id)
        onSelectionChange(next)
      } else {
        onSelectionChange([...selectedNodeIds, node.id])
      }
      return
    }

    onSelectionChange([node.id])
  }, [pendingLinkSourceId, onSelectionChange, selectedSet, selectedNodeIds])

  const handleNodeDoubleClick = useCallback((_evt: any, node: any) => {
    if (!node?.id) return
    const n = nodesById.get(node.id)
    if (n?.type === 'Fold') {
      toggleViewUnfold(node.id)
      return
    }
    if (onNodeOpenDetail) onNodeOpenDetail(node.id)
  }, [nodesById, onNodeOpenDetail, toggleViewUnfold])

  const handlePaneClick = useCallback(() => {
    setSelectedNodeId(null)
    setMenuOpen(false)
    setLinkPopoverOpen(false)
    setPendingLinkSourceId(null)
    onSelectionChange([])
  }, [onSelectionChange])

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
      .filter((id): id is string => Boolean(id) && !id.startsWith('virtual:') && !id.startsWith('view-fold:'))
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

  const handleActivateSelected = useCallback(() => {
    if (!onActivateNodes || selectedNodeIds.length === 0) return
    void executeAction(async () => {
      await onActivateNodes(selectedNodeIds)
      setMenuOpen(false)
    })
  }, [onActivateNodes, selectedNodeIds, executeAction])

  const handleDeactivateSelected = useCallback(() => {
    if (!onDeactivateNodes || selectedNodeIds.length === 0) return
    void executeAction(async () => {
      await onDeactivateNodes(selectedNodeIds)
      setMenuOpen(false)
    })
  }, [onDeactivateNodes, selectedNodeIds, executeAction])

  const handleFoldSelected = useCallback(() => {
    if (!onFoldSelected || selectedNodeIds.length < 2) return
    void executeAction(async () => {
      await onFoldSelected(selectedNodeIds)
      setMenuOpen(false)
    })
  }, [onFoldSelected, selectedNodeIds, executeAction])

  const handleOpenDetail = useCallback(() => {
    if (!onNodeOpenDetail || !singleSelectedNode) return
    onNodeOpenDetail(singleSelectedNode.id)
    setMenuOpen(false)
  }, [onNodeOpenDetail, singleSelectedNode])

  const handleToggleViewUnfoldSelectedFold = useCallback(() => {
    if (!singleSelectedFoldId) return
    toggleViewUnfold(singleSelectedFoldId)
    setMenuOpen(false)
  }, [singleSelectedFoldId, toggleViewUnfold])

  const handleCommitUnfoldSelectedFold = useCallback(() => {
    if (!singleSelectedFoldId || !onCommitUnfold) return
    void executeAction(async () => {
      await onCommitUnfold(singleSelectedFoldId)
      setMenuOpen(false)
    })
  }, [singleSelectedFoldId, onCommitUnfold, executeAction])

  const handleStartLinkFromSingle = useCallback(() => {
    if (!singleSelectedNode) return
    setPendingLinkSourceId(singleSelectedNode.id)
    setMenuOpen(false)
  }, [singleSelectedNode])

  const handleOpenLinkPopover = useCallback(() => {
    if (selectedNodeIds.length !== 2) return
    setLinkDirection('ab')
    setLinkPopoverOpen(true)
    setMenuOpen(false)
  }, [selectedNodeIds.length])

  const handleSubmitLink = useCallback(() => {
    if (!onCreateEdge || selectedNodeIds.length !== 2) return
    const a = selectedNodeIds[0]
    const b = selectedNodeIds[1]
    const sourceId = linkDirection === 'ab' ? a : b
    const targetId = linkDirection === 'ab' ? b : a

    void executeAction(async () => {
      await onCreateEdge(sourceId, targetId, linkType)
      setLinkPopoverOpen(false)
    })
  }, [onCreateEdge, selectedNodeIds, linkDirection, linkType, executeAction])

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement
    if (target && ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName)) {
      return
    }

    const key = e.key.toLowerCase()
    if (key === 'escape') {
      e.preventDefault()
      setMenuOpen(false)
      setLinkPopoverOpen(false)
      setPendingLinkSourceId(null)
      onSelectionChange([])
      return
    }

    if (key === 'enter' && menuOpen && selectedNodeIds.length === 1) {
      e.preventDefault()
      handleOpenDetail()
      return
    }

    if (key === 'f' && selectedNodeIds.length >= 2) {
      e.preventDefault()
      handleFoldSelected()
      return
    }

    if (key === 'u' && singleSelectedFoldId) {
      e.preventDefault()
      handleToggleViewUnfoldSelectedFold()
      return
    }

    if (key === 'a' && selectedNodeIds.length > 0) {
      e.preventDefault()
      handleActivateSelected()
      return
    }

    if (key === 'd' && selectedNodeIds.length === 1) {
      e.preventDefault()
      handleOpenDetail()
      return
    }

    if ((key === 'delete' || key === 'backspace') && selectedNodeIds.length > 0 && onDeleteNodes) {
      e.preventDefault()
      handleDeleteSelectedNodes()
    }
  }, [onSelectionChange, menuOpen, selectedNodeIds, singleSelectedFoldId, onDeleteNodes, handleFoldSelected, handleToggleViewUnfoldSelectedFold, handleActivateSelected, handleOpenDetail, handleDeleteSelectedNodes])

  const selectedPair = selectedNodeIds.length === 2 ? [selectedNodeIds[0], selectedNodeIds[1]] as const : null

  return (
    <div
      className="graphWrap"
      ref={wrapRef}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      onMouseDown={() => wrapRef.current?.focus()}
    >
      <div className="graphTools">
        <button onClick={() => setShowFoldMembers((v) => !v)}>
          {showFoldMembers ? 'Hide Fold Members' : 'Show Fold Members'}
        </button>

        <button
          onClick={() => setLayoutMode((prev) => (prev === 'manual' ? 'auto' : 'manual'))}
          title={layoutMode === 'manual' ? '자동 정렬 모드로 전환' : '수동 배치/저장 모드로 전환'}
        >
          Layout: {layoutMode === 'manual' ? 'Manual' : 'Auto'}
        </button>
        <button onClick={fitViewNow} disabled={!rfNodes.length}>Fit View</button>
        {layoutMode === 'manual' && (
          <button onClick={saveCurrentLayoutNow} disabled={!onSaveLayout || !rfNodes.length || layoutSaving}>
            {layoutSaving ? 'Saving...' : 'Save Layout'}
          </button>
        )}

        <span className="muted">Node Filter</span>
        <select value={nodeTypeFilter} onChange={(e) => setNodeTypeFilter(e.target.value as any)}>
          <option value="all">all</option>
          <option value="resources">resources only</option>
          <option value="non_resources">exclude resources</option>
        </select>

        <span className="muted">Zoom {zoom.toFixed(2)} {autoDetailByZoom ? '(auto detail)' : ''}</span>

        <details className="graphLegacyControls">
          <summary>Legacy edge controls</summary>
          <div className="row" style={{ marginBottom: 0 }}>
            <span className="muted">Edge Type</span>
            <select value={newEdgeType} onChange={(e) => setNewEdgeType(e.target.value)}>
              {LEGACY_EDGE_TYPE_OPTIONS.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </div>
        </details>

        <span className="muted">Click=select, Shift+click=toggle, double-click=detail/fold-view, Space+drag=pan, Esc=clear</span>
        {layoutMode === 'manual' && onSaveLayout && <span className="muted">드래그 후 레이아웃 자동 저장(650ms debounce)</span>}
        {layoutSaveError && <span className="pill graphStatusPill graphStatusPill--error">Layout save failed</span>}
        {layoutSaving && <span className="pill graphStatusPill">Saving layout…</span>}
        {pendingLinkSourceId && <span className="pill">Link source: {shortId(pendingLinkSourceId)} (대상 노드 클릭)</span>}
      </div>

      {selectedNodeId && nodesById.get(selectedNodeId) && (
        <div className="graphDetail">
          <div><b>{nodesById.get(selectedNodeId).type}</b> <span className="muted">({shortId(selectedNodeId)})</span></div>
          <div className="muted">{nodesById.get(selectedNodeId).created_at}</div>
          <pre>{nodesById.get(selectedNodeId).text || '(empty)'}</pre>
          <pre>{payloadPretty(nodesById.get(selectedNodeId).payload_json)}</pre>
        </div>
      )}

      <div className="graphCanvas">
        <ReactFlow
          nodes={rfNodes}
          edges={rfEdges}
          nodesDraggable={layoutMode === 'manual'}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onInit={setRfInstance}
          onMove={handleMove}
          onSelectionChange={handleSelectionChange}
          onNodeClick={handleNodeClick}
          onNodeDoubleClick={handleNodeDoubleClick}
          onNodeDragStop={handleNodeDragStop}
          onPaneClick={handlePaneClick}
          onConnect={handleConnect}
          onEdgesDelete={handleEdgesDelete}
          selectionOnDrag
          selectionMode={SelectionMode.Partial}
          multiSelectionKeyCode={['Shift']}
          panOnDrag
          panActivationKeyCode={['Space']}
          deleteKeyCode={['Backspace', 'Delete']}
        >
          <Background />
          <MiniMap />
          <Controls />
        </ReactFlow>

        {selectionHull && (
          <>
            <div
              className="selectionHull"
              style={{
                left: selectionHull.left,
                top: selectionHull.top,
                width: selectionHull.width,
                height: selectionHull.height,
              }}
            />
            <div
              className="selectionCountBadge"
              style={{
                left: selectionHull.centerX,
                top: selectionHull.centerY,
              }}
            >
              {selectedNodeIds.length} selected
            </div>
          </>
        )}

        {selectionAnchor && selectedNodeIds.length > 0 && (
          <>
            <button
              className="selectionMenuTrigger"
              style={{ left: selectionAnchor.x + 18, top: selectionAnchor.y - 18 }}
              onClick={() => {
                setMenuOpen((v) => !v)
                setLinkPopoverOpen(false)
              }}
              title="Selection actions"
            >
              ●
            </button>

            {menuOpen && (
              <div className="selectionContextMenu" style={{ left: selectionAnchor.x + 52, top: selectionAnchor.y - 20 }}>
                {selectedNodeIds.length === 1 && (
                  <>
                    <button onClick={handleOpenDetail} disabled={!singleSelectedNode}>Open Detail / Split</button>
                    {hasInactiveSelected && <button onClick={handleActivateSelected} disabled={actionBusy}>Activate</button>}
                    {hasActiveSelected && <button onClick={handleDeactivateSelected} disabled={actionBusy}>Deactivate</button>}
                    {singleSelectedFoldId && (
                      <button onClick={handleToggleViewUnfoldSelectedFold}>
                        {expandedFoldSet.has(singleSelectedFoldId) ? 'Fold (view-only) collapse' : 'Unfold (view-only)'}
                      </button>
                    )}
                    {singleSelectedFoldId && (
                      <button onClick={handleCommitUnfoldSelectedFold} disabled={!onCommitUnfold || actionBusy}>Unfold into Active</button>
                    )}
                    <button onClick={handleStartLinkFromSingle}>Start Link</button>
                    <button onClick={() => onSelectionChange([])}>Clear selection</button>
                  </>
                )}

                {selectedNodeIds.length >= 2 && (
                  <>
                    <button onClick={handleFoldSelected} disabled={!onFoldSelected || selectedNodeIds.length < 2 || actionBusy}>Fold selected</button>
                    {hasInactiveSelected && <button onClick={handleActivateSelected} disabled={!onActivateNodes || actionBusy}>Activate selected</button>}
                    {hasActiveSelected && <button onClick={handleDeactivateSelected} disabled={!onDeactivateNodes || actionBusy}>Deactivate selected</button>}
                    <button onClick={handleOpenLinkPopover} disabled={selectedNodeIds.length !== 2}>Link...</button>
                    <button onClick={() => onSelectionChange([])}>Clear selection</button>
                  </>
                )}

                {actionError && <div className="menuError">{actionError}</div>}
              </div>
            )}

            {linkPopoverOpen && selectedPair && (
              <div className="linkPopover" style={{ left: selectionAnchor.x + 52, top: selectionAnchor.y + 112 }}>
                <div className="muted" style={{ marginBottom: 6 }}>Link selected nodes</div>
                <div className="row" style={{ marginBottom: 6 }}>
                  <span className="muted">Edge type</span>
                  <select value={linkType} onChange={(e) => setLinkType(e.target.value)}>
                    {LINK_EDGE_TYPE_OPTIONS.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
                <div className="row" style={{ marginBottom: 6 }}>
                  <span className="muted">Direction</span>
                  <select value={linkDirection} onChange={(e) => setLinkDirection(e.target.value as 'ab' | 'ba')}>
                    <option value="ab">{shortId(selectedPair[0])} → {shortId(selectedPair[1])}</option>
                    <option value="ba">{shortId(selectedPair[1])} → {shortId(selectedPair[0])}</option>
                  </select>
                </div>
                <div className="row" style={{ marginBottom: 0 }}>
                  <button className="primary" onClick={handleSubmitLink} disabled={!onCreateEdge || actionBusy}>Create Link</button>
                  <button onClick={() => setLinkPopoverOpen(false)}>Close</button>
                </div>
                {actionError && <div className="menuError">{actionError}</div>}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
