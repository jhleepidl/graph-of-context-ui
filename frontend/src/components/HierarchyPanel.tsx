import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api'

type HierNode = {
  id: string
  kind: string
  label: string
  size?: number
  node_id?: string
  node_type?: string
  leaf_node_ids?: string[]
  children?: HierNode[]
}

type HierarchyResp = {
  ok: boolean
  root: HierNode
  leaf_layout: Array<{ node_id: string; rank: number; depth: number; cluster_path: string[] }>
  node_depths: Record<string, number>
  stats?: Record<string, any>
}

type Props = {
  threadId: string | null
  ctxId: string | null
  activeIds: string[]
  nodesById: Map<string, any>
  onOpenNode?: (nodeId: string) => void
  onAddManyToActive?: (nodeIds: string[]) => Promise<void> | void
  onFocusNodes?: (nodeIds: string[]) => void
  onHierarchyLayout?: (payload: { leafLayout: any[]; nodeDepths: Record<string, number> } | null) => void
}

function shortLabel(s: string, max = 88): string {
  const c = (s || '').replace(/\s+/g, ' ').trim()
  return c.length > max ? `${c.slice(0, max - 3)}...` : c
}

function kindBadge(kind?: string): string {
  if (!kind) return 'pill--default'
  if (kind.includes('fold')) return 'pill--fold'
  if (kind.includes('split')) return 'pill--assumption'
  if (kind === 'cluster') return 'pill--plan'
  if (kind === 'root') return 'pill--candidate'
  return 'pill--default'
}

export default function HierarchyPanel({
  threadId,
  ctxId,
  activeIds,
  nodesById,
  onOpenNode,
  onAddManyToActive,
  onFocusNodes,
  onHierarchyLayout,
}: Props) {
  const [scope, setScope] = useState<'active' | 'all'>('active')
  const [maxLeafSize, setMaxLeafSize] = useState<number>(6)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [data, setData] = useState<HierarchyResp | null>(null)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({ root: true })
  const [lastFocusIds, setLastFocusIds] = useState<string[]>([])

  const selectedNodeCount = scope === 'active' ? activeIds.length : nodesById.size

  async function refreshHierarchy() {
    if (!threadId) {
      setData(null)
      onHierarchyLayout?.(null)
      return
    }
    setLoading(true)
    setError('')
    try {
      const body: any = { max_leaf_size: maxLeafSize }
      if (scope === 'active') {
        body.node_ids = activeIds
        if (ctxId) body.context_set_id = ctxId
      }
      const resp = await api.hierarchyPreview(threadId, body)
      setData(resp)
      onHierarchyLayout?.({ leafLayout: resp.leaf_layout || [], nodeDepths: resp.node_depths || {} })
      setExpanded((prev) => ({ root: true, ...prev }))
    } catch (e: any) {
      setError(e?.message || String(e))
      setData(null)
      onHierarchyLayout?.(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    // auto-refresh on thread change / active context change (debounced)
    const t = window.setTimeout(() => {
      refreshHierarchy()
    }, 200)
    return () => window.clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId, ctxId, scope, maxLeafSize, activeIds.join('|')])

  useEffect(() => {
    if (!onFocusNodes) return
    onFocusNodes(lastFocusIds)
  }, [lastFocusIds, onFocusNodes])

  const statsLine = useMemo(() => {
    if (!data?.stats) return ''
    const s = data.stats as any
    return `nodes ${s.clustered_nodes ?? '-'} / groups ${s.top_groups ?? '-'} / leaf≤${s.max_leaf_size ?? maxLeafSize}`
  }, [data, maxLeafSize])

  function toggleExpanded(id: string) {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  async function handleAddCluster(nodeIds: string[]) {
    const uniq = Array.from(new Set((nodeIds || []).filter(Boolean)))
    if (!uniq.length) return
    await onAddManyToActive?.(uniq)
  }

  function renderNode(node: HierNode, level = 0): React.ReactNode {
    const isLeaf = node.kind === 'leaf'
    const children = node.children || []
    const hasChildren = children.length > 0
    const isOpen = expanded[node.id] ?? (level < 2)
    const leafIds = Array.from(new Set(node.leaf_node_ids || (node.node_id ? [node.node_id] : [])))
    const activeCount = leafIds.filter((id) => activeIds.includes(id)).length
    const label = isLeaf
      ? (() => {
          const n = node.node_id ? nodesById.get(node.node_id) : null
          const base = n ? `${n.type || 'Node'} · ${(n.text || '').trim().replace(/\s+/g, ' ')}` : node.label
          return shortLabel(base, 96)
        })()
      : shortLabel(node.label || node.kind, 96)

    return (
      <div key={node.id} className="hierRowWrap">
        <div className={`hierRow ${isLeaf ? 'isLeaf' : ''}`} style={{ marginLeft: level * 14 }}>
          <button
            className="hierExpandBtn"
            onClick={() => (hasChildren ? toggleExpanded(node.id) : onOpenNode?.(node.node_id || ''))}
            title={hasChildren ? (isOpen ? '접기' : '펼치기') : '노드 열기'}
          >
            {hasChildren ? (isOpen ? '▾' : '▸') : '•'}
          </button>

          <span className={`pill pillType ${kindBadge(node.kind)}`}>{isLeaf ? (node.node_type || 'Node') : node.kind}</span>
          <span className="hierLabel" title={node.label}>{label}</span>
          {!isLeaf && <span className="pill">size: {node.size ?? leafIds.length}</span>}
          {activeCount > 0 && <span className="pill pillActive">active {activeCount}</span>}

          <div className="hierActions">
            {leafIds.length > 0 && (
              <>
                <button onClick={() => setLastFocusIds(leafIds)}>Focus</button>
                {!isLeaf && <button onClick={() => handleAddCluster(leafIds)}>Add group</button>}
              </>
            )}
            {isLeaf && node.node_id && <button onClick={() => onOpenNode?.(node.node_id!)}>Open</button>}
          </div>
        </div>
        {hasChildren && isOpen && <div>{children.map((c) => renderNode(c, level + 1))}</div>}
      </div>
    )
  }

  return (
    <div>
      <h3>Hierarchy (Vector + Graph)</h3>
      <div className="card" style={{ marginBottom: 10 }}>
        <div className="row" style={{ marginBottom: 6 }}>
          <label className="muted">Scope</label>
          <select value={scope} onChange={(e) => setScope(e.target.value as any)}>
            <option value="active">active context</option>
            <option value="all">whole thread</option>
          </select>
          <label className="muted">Leaf cap</label>
          <select value={String(maxLeafSize)} onChange={(e) => setMaxLeafSize(Number(e.target.value) || 6)}>
            {[4, 6, 8, 12].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
          <button onClick={refreshHierarchy} disabled={loading || !threadId}>Refresh</button>
          <button onClick={() => setLastFocusIds([])} disabled={!lastFocusIds.length}>Clear focus</button>
        </div>
        <div className="muted">선택 범위: {selectedNodeCount} nodes {statsLine ? `· ${statsLine}` : ''}</div>
        <div className="muted">Folding/Splitting은 원본 그래프 수정, Hierarchy는 view-only projection입니다.</div>
        {loading && <div className="muted">계층 구조 계산 중...</div>}
        {error && <div className="muted" style={{ color: '#dc2626' }}>{error}</div>}
      </div>

      {!data && !loading && <div className="muted">계층 구조가 없습니다.</div>}
      {data?.root && <div className="hierTree card">{renderNode(data.root, 0)}</div>}
    </div>
  )
}
