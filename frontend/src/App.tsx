import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import Timeline from './components/Timeline'
import GraphPanel from './components/GraphPanel'
import ActiveContext from './components/ActiveContext'
import RunPanel from './components/RunPanel'
import SearchPanel from './components/SearchPanel'
import CopyToChatGPTPanel from './components/CopyToChatGPTPanel'
import NodeDetailModal from './components/NodeDetailModal'
import ContextInspector from './components/ContextInspector'
import { scoreNodesForRequest, type PriorityBucket } from './utils/contextPriority'

const PANEL_WIDTH_STORAGE_KEY = 'goc:panel-widths:v1'
const RIGHT_PANEL_TAB_STORAGE_KEY = 'goc:right-panel-tab:v1'
const MOBILE_SECTION_STORAGE_KEY = 'goc:mobile-section:v1'
const LEFT_PANEL_MIN_WIDTH = 260
const RIGHT_PANEL_MIN_WIDTH = 300
const CENTER_PANEL_MIN_WIDTH = 520
const RESIZER_WIDTH = 10
const MOBILE_LAYOUT_BREAKPOINT = 820

type ResizeHandle = 'left' | 'right'
type ResizeSession = {
  handle: ResizeHandle
  startX: number
  startLeftWidth: number
  startRightWidth: number
  wrapWidth: number
}
type MobileSection = 'left' | 'center' | 'right'
type RightPanelTab = 'inspector' | 'prompt' | 'run'

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function detectMobileLayout(): boolean {
  if (typeof window === 'undefined') return false
  return window.innerWidth <= MOBILE_LAYOUT_BREAKPOINT
}

function readStoredRightPanelTab(): RightPanelTab {
  if (typeof window === 'undefined') return 'inspector'
  try {
    const raw = window.localStorage.getItem(RIGHT_PANEL_TAB_STORAGE_KEY)
    if (raw === 'inspector' || raw === 'prompt' || raw === 'run') return raw
  } catch {
    // ignore storage failures
  }
  return 'inspector'
}

function readStoredMobileSection(): MobileSection {
  if (typeof window === 'undefined') return 'center'
  try {
    const raw = window.localStorage.getItem(MOBILE_SECTION_STORAGE_KEY)
    if (raw === 'left' || raw === 'center' || raw === 'right') return raw
  } catch {
    // ignore storage failures
  }
  return 'center'
}

export default function App() {
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const [threads, setThreads] = useState<any[]>([])
  const [threadId, setThreadId] = useState<string | null>(null)

  const [ctxSets, setCtxSets] = useState<any[]>([])
  const [ctxId, setCtxId] = useState<string | null>(null)

  const [nodes, setNodes] = useState<any[]>([])
  const [edges, setEdges] = useState<any[]>([])
  const [activeIds, setActiveIds] = useState<string[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [detailNodeId, setDetailNodeId] = useState<string | null>(null)
  const [compiledInfo, setCompiledInfo] = useState<any | null>(null)
  const [contextVersions, setContextVersions] = useState<any[]>([])
  const [versionDiff, setVersionDiff] = useState<any | null>(null)
  const [plannerResult, setPlannerResult] = useState<any | null>(null)
  const switchSeqRef = useRef(0)
  const [panelWidths, setPanelWidths] = useState<{ left: number; right: number }>(() => {
    try {
      const raw = window.localStorage.getItem(PANEL_WIDTH_STORAGE_KEY)
      if (!raw) return { left: 360, right: 360 }
      const parsed = JSON.parse(raw)
      const left = Number(parsed?.left)
      const right = Number(parsed?.right)
      return {
        left: Number.isFinite(left) ? Math.round(left) : 360,
        right: Number.isFinite(right) ? Math.round(right) : 360,
      }
    } catch {
      return { left: 360, right: 360 }
    }
  })
  const [resizeSession, setResizeSession] = useState<ResizeSession | null>(null)
  const [rightPanelTab, setRightPanelTab] = useState<RightPanelTab>(() => readStoredRightPanelTab())
  const [mobileSection, setMobileSection] = useState<MobileSection>(() => readStoredMobileSection())
  const [isMobileLayout, setIsMobileLayout] = useState<boolean>(() => detectMobileLayout())

  const nodesById = useMemo(() => new Map(nodes.map(n => [n.id, n])), [nodes])
  const activeNodes = useMemo(() => activeIds.map((id) => nodesById.get(id)).filter(Boolean), [activeIds, nodesById])
  const selectedFoldIds = useMemo(() => selectedIds.filter((id) => nodesById.get(id)?.type === 'Fold'), [selectedIds, nodesById])
  const graphPriorityBucketById = useMemo(() => {
    const scored = scoreNodesForRequest(nodes, '')
    const activeSet = new Set(activeIds)
    const byId = new Map<string, PriorityBucket>()
    for (const score of scored) {
      if (!activeSet.has(score.node.id)) continue
      byId.set(score.node.id, score.bucket)
    }
    return byId
  }, [nodes, activeIds])
  const partCountByParent = useMemo(() => {
    const out: Record<string, number> = {}
    for (const e of edges) {
      if (e.type !== 'HAS_PART') continue
      out[e.from_id] = (out[e.from_id] || 0) + 1
    }
    return out
  }, [edges])
  const isSameIdSet = useCallback((a: string[], b: string[]) => {
    if (a.length !== b.length) return false
    const as = new Set(a)
    for (const id of b) {
      if (!as.has(id)) return false
    }
    return true
  }, [])

  const handleSelectionChange = useCallback((ids: string[]) => {
    setSelectedIds((prev) => (isSameIdSet(prev, ids) ? prev : ids))
  }, [isSameIdSet])

  async function refreshContextInspector(nextCtxId?: string) {
    const cId = nextCtxId || ctxId
    if (!cId) {
      setCompiledInfo(null)
      setContextVersions([])
      setVersionDiff(null)
      setPlannerResult(null)
      return
    }
    const [compiled, versions] = await Promise.all([
      api.ctxCompiled(cId, true),
      api.ctxVersions(cId, 20),
    ])
    setCompiledInfo(compiled)
    setContextVersions(versions?.versions || [])
  }

  async function reloadGraph(nextThreadId?: string) {
    const tId = nextThreadId || threadId
    if (!tId) return
    const g = await api.graph(tId)
    setNodes(g.nodes)
    setEdges(g.edges)
  }

  async function reloadAll(nextThreadId?: string, nextCtxId?: string) {
    const tId = nextThreadId || threadId
    const cId = nextCtxId || ctxId
    if (!tId) return
    await reloadGraph(tId)
    if (!cId) return

    const ctx = await api.ctx(cId)
    setActiveIds(ctx.active_node_ids || [])
    await refreshContextInspector(cId)
  }

  async function loadThreads() {
    const ts = await api.threads()
    setThreads(ts)
    let tid = ts[0]?.id
    if (!tid) {
      const t = await api.createThread('Demo Thread')
      tid = t.id
      const refreshed = await api.threads()
      setThreads(refreshed)
    }
    return tid
  }

  async function loadCtxSets(tid: string) {
    const sets = await api.ctxSets(tid)
    let nextSets = sets
    let cid = sets[0]?.id
    if (!cid) {
      const cs = await api.createCtx(tid, 'default')
      nextSets = [...sets, cs]
      cid = cs.id
    }
    return { sets: nextSets, cid }
  }

  function clearThreadScopedState() {
    setCtxSets([])
    setCtxId(null)
    setNodes([])
    setEdges([])
    setActiveIds([])
    setSelectedIds([])
    setDetailNodeId(null)
    setCompiledInfo(null)
    setContextVersions([])
    setVersionDiff(null)
    setPlannerResult(null)
  }

  async function switchThread(nextThreadId: string) {
    if (!nextThreadId) return
    const seq = ++switchSeqRef.current

    setThreadId(nextThreadId)
    clearThreadScopedState()

    try {
      const { sets, cid } = await loadCtxSets(nextThreadId)
      if (switchSeqRef.current !== seq) return

      setCtxSets(sets)
      setCtxId(cid)

      const g = await api.graph(nextThreadId)
      if (switchSeqRef.current !== seq) return
      setNodes(g.nodes)
      setEdges(g.edges)

      const ctx = await api.ctx(cid)
      if (switchSeqRef.current !== seq) return
      setActiveIds(ctx.active_node_ids || [])
      const [compiled, versions] = await Promise.all([
        api.ctxCompiled(cid, true),
        api.ctxVersions(cid, 20),
      ])
      if (switchSeqRef.current !== seq) return
      setCompiledInfo(compiled)
      setContextVersions(versions?.versions || [])
    } catch (e) {
      console.error('failed to switch thread', e)
    }
  }

  useEffect(() => {
    (async () => {
      const tid = await loadThreads()
      await switchThread(tid)
    })()
  }, [])

  useEffect(() => {
    try {
      window.localStorage.setItem(PANEL_WIDTH_STORAGE_KEY, JSON.stringify(panelWidths))
    } catch {
      // ignore localStorage errors
    }
  }, [panelWidths])

  useEffect(() => {
    try {
      window.localStorage.setItem(RIGHT_PANEL_TAB_STORAGE_KEY, rightPanelTab)
    } catch {
      // ignore localStorage errors
    }
  }, [rightPanelTab])

  useEffect(() => {
    try {
      window.localStorage.setItem(MOBILE_SECTION_STORAGE_KEY, mobileSection)
    } catch {
      // ignore localStorage errors
    }
  }, [mobileSection])

  useEffect(() => {
    function handleResize() {
      setIsMobileLayout(detectMobileLayout())
    }
    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  useEffect(() => {
    if (!resizeSession) return

    function handleMouseMove(evt: MouseEvent) {
      const dx = evt.clientX - resizeSession.startX
      const totalResizerWidth = RESIZER_WIDTH * 2

      if (resizeSession.handle === 'left') {
        const maxLeft = resizeSession.wrapWidth - resizeSession.startRightWidth - CENTER_PANEL_MIN_WIDTH - totalResizerWidth
        const upper = Math.max(LEFT_PANEL_MIN_WIDTH, maxLeft)
        const nextLeft = Math.round(clamp(resizeSession.startLeftWidth + dx, LEFT_PANEL_MIN_WIDTH, upper))
        setPanelWidths((prev) => (prev.left === nextLeft ? prev : { ...prev, left: nextLeft }))
        return
      }

      const maxRight = resizeSession.wrapWidth - resizeSession.startLeftWidth - CENTER_PANEL_MIN_WIDTH - totalResizerWidth
      const upper = Math.max(RIGHT_PANEL_MIN_WIDTH, maxRight)
      const nextRight = Math.round(clamp(resizeSession.startRightWidth - dx, RIGHT_PANEL_MIN_WIDTH, upper))
      setPanelWidths((prev) => (prev.right === nextRight ? prev : { ...prev, right: nextRight }))
    }

    function handleMouseUp() {
      setResizeSession(null)
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    document.body.classList.add('isResizingPanels')

    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
      document.body.classList.remove('isResizingPanels')
    }
  }, [resizeSession])

  const startPanelResize = useCallback((handle: ResizeHandle, evt: React.MouseEvent<HTMLDivElement>) => {
    const wrap = wrapRef.current
    if (!wrap) return
    const rect = wrap.getBoundingClientRect()
    setResizeSession({
      handle,
      startX: evt.clientX,
      startLeftWidth: panelWidths.left,
      startRightWidth: panelWidths.right,
      wrapWidth: rect.width,
    })
    evt.preventDefault()
  }, [panelWidths])

  const wrapStyle = useMemo<React.CSSProperties>(() => {
    return {
      ['--left-panel-width' as any]: `${panelWidths.left}px`,
      ['--right-panel-width' as any]: `${panelWidths.right}px`,
    }
  }, [panelWidths])
  const showLeftPanel = !isMobileLayout || mobileSection === 'left'
  const showCenterPanel = !isMobileLayout || mobileSection === 'center'
  const showRightPanel = !isMobileLayout || mobileSection === 'right'

  async function toggleActive(nodeId: string, nextActive: boolean) {
    if (!ctxId) return
    if (nextActive) {
      const out = await api.activate(ctxId, [nodeId])
      if (Array.isArray(out?.active_node_ids)) {
        setActiveIds(out.active_node_ids)
        await refreshContextInspector(ctxId)
        return
      }
    } else {
      const out = await api.deactivate(ctxId, [nodeId])
      if (Array.isArray(out?.active_node_ids)) {
        setActiveIds(out.active_node_ids)
        await refreshContextInspector(ctxId)
        return
      }
    }
    await reloadAll()
  }

  async function reorderActive(nodeIds: string[]) {
    if (!ctxId) return
    try {
      await api.reorderActive(ctxId, nodeIds)
      setActiveIds(nodeIds)
      await refreshContextInspector(ctxId)
    } catch (e) {
      console.error('failed to reorder active nodes', e)
      await reloadAll()
    }
  }

  async function foldNodeIds(ids: string[]) {
    if (!threadId || !ctxId) return
    if (ids.length < 2) {
      alert('그래프에서 2개 이상 노드를 선택하세요.')
      return
    }
    const res = await api.fold(threadId, ids, 'Fold')
    await api.deactivate(ctxId, ids)
    await api.activate(ctxId, [res.fold_id])
    setSelectedIds([res.fold_id])
    await reloadAll()
  }

  async function activateNodeIds(nodeIds: string[]) {
    if (!ctxId || nodeIds.length === 0) return
    const out = await api.activate(ctxId, nodeIds)
    if (Array.isArray(out?.active_node_ids)) {
      setActiveIds(out.active_node_ids)
      await refreshContextInspector(ctxId)
      return
    }
    await reloadAll()
  }

  async function deactivateNodeIds(nodeIds: string[]) {
    if (!ctxId || nodeIds.length === 0) return
    const out = await api.deactivate(ctxId, nodeIds)
    if (Array.isArray(out?.active_node_ids)) {
      setActiveIds(out.active_node_ids)
      await refreshContextInspector(ctxId)
      return
    }
    await reloadAll()
  }

  async function foldSelected() {
    await foldNodeIds(selectedIds)
  }

  async function unfoldFold(foldId: string) {
    if (!ctxId) return
    const out = await api.unfold(ctxId, foldId, {
      closure_edge_types: ['FOLDS', 'DEPENDS', 'HAS_PART', 'SPLIT_FROM', 'REFERENCES'],
      closure_direction: 'both',
      max_closure_nodes: 16,
      replace_only_fold: true,
      include_explain: true,
    })
    if (Array.isArray(out?.members) && out.members.length > 0) {
      setSelectedIds(out.members)
    }
    if (Array.isArray(out?.active_node_ids)) {
      setActiveIds(out.active_node_ids)
      await refreshContextInspector(ctxId)
      return
    }
    await reloadAll()
  }

  async function handleCreateEdge(sourceId: string, targetId: string, edgeType: string) {
    if (!threadId) return
    try {
      await api.createEdge(threadId, sourceId, targetId, edgeType)
      await reloadGraph(threadId)
    } catch (e) {
      console.error('failed to create edge', e)
    }
  }

  async function handleDeleteEdges(edgeIds: string[]) {
    if (!threadId || edgeIds.length === 0) return
    try {
      await Promise.all(edgeIds.map((edgeId) => api.deleteEdge(threadId, edgeId)))
      await reloadGraph(threadId)
    } catch (e) {
      console.error('failed to delete edges', e)
    }
  }

  async function handleDeleteNodes(nodeIds: string[]) {
    if (!threadId || nodeIds.length === 0) return
    try {
      await Promise.all(nodeIds.map((nodeId) => api.deleteNode(threadId, nodeId)))
      setSelectedIds([])
      if (detailNodeId && nodeIds.includes(detailNodeId)) {
        setDetailNodeId(null)
      }
      await reloadAll(threadId, ctxId || undefined)
    } catch (e) {
      console.error('failed to delete nodes', e)
      await reloadAll(threadId, ctxId || undefined)
    }
  }

  const saveGraphLayoutPositions = useCallback(async (positions: Array<{ id: string; x: number; y: number }>) => {
    if (!threadId) return
    await api.saveNodeLayout(threadId, positions)
  }, [threadId])

  const replaceActiveContext = useCallback(async (nextNodeIds: string[]) => {
    if (!ctxId) return
    const deduped = nextNodeIds.filter((id, idx) => id && nextNodeIds.indexOf(id) === idx)
    try {
      const current = activeIds
      const nextSet = new Set(deduped)
      const currentSet = new Set(current)
      const toRemove = current.filter((id) => !nextSet.has(id))
      const toAdd = deduped.filter((id) => !currentSet.has(id))

      if (toRemove.length > 0) {
        const out = await api.deactivate(ctxId, toRemove)
        if (Array.isArray(out?.active_node_ids)) {
          setActiveIds(out.active_node_ids)
        }
      }

      if (toAdd.length > 0) {
        const out = await api.activate(ctxId, toAdd)
        if (Array.isArray(out?.active_node_ids)) {
          setActiveIds(out.active_node_ids)
        }
      }

      await api.reorderActive(ctxId, deduped)
      setActiveIds(deduped)
      await refreshContextInspector(ctxId)
    } catch (e) {
      console.error('failed to replace active context', e)
      await reloadAll()
    }
  }, [ctxId, activeIds])

  async function activateSelected() {
    await activateNodeIds(selectedIds)
  }

  async function unfoldSelectedFolds() {
    if (!ctxId) return
    if (selectedFoldIds.length === 0) return
    for (const foldId of selectedFoldIds) {
      await api.unfold(ctxId, foldId, {
        closure_edge_types: ['FOLDS', 'DEPENDS', 'HAS_PART', 'SPLIT_FROM', 'REFERENCES'],
        closure_direction: 'both',
        max_closure_nodes: 16,
        replace_only_fold: true,
        include_explain: true,
      })
    }
    setSelectedIds([])
    await reloadAll()
  }

  async function handleDeleteCurrentThread() {
    if (!threadId) return
    const cur = threads.find((t) => t.id === threadId)
    const label = cur ? `${cur.title} (${cur.id.slice(0, 6)})` : threadId.slice(0, 6)
    const ok = window.confirm(`현재 thread를 삭제할까요?\n${label}`)
    if (!ok) return

    try {
      await api.deleteThread(threadId)
      const ts = await api.threads()
      setThreads(ts)

      if (ts.length === 0) {
        const created = await api.createThread('New Thread')
        const refreshed = await api.threads()
        setThreads(refreshed)
        await switchThread(created.id)
        return
      }

      await switchThread(ts[0].id)
    } catch (e) {
      console.error('failed to delete thread', e)
      alert('Thread 삭제에 실패했습니다.')
    }
  }

  async function loadVersionDiff(fromVersion: number, toVersion: number) {
    if (!ctxId) return
    const diff = await api.ctxVersionDiff(ctxId, fromVersion, toVersion)
    setVersionDiff(diff)
  }

  async function previewPlanner(query: string, budgetTokens: number) {
    if (!ctxId) return
    const result = await api.previewUnfoldPlan(ctxId, {
      query,
      budget_tokens: budgetTokens,
      top_k: 8,
      max_candidates: 16,
      closure_edge_types: ['DEPENDS', 'HAS_PART', 'SPLIT_FROM', 'REFERENCES'],
      closure_direction: 'both',
      max_closure_nodes: 12,
    })
    setPlannerResult(result)
  }

  async function applyPlannerSeeds(seedIds: string[], budgetTokens: number) {
    if (!ctxId || seedIds.length === 0) return
    const result = await api.applyUnfoldPlan(ctxId, {
      seed_node_ids: seedIds,
      budget_tokens: budgetTokens,
      closure_edge_types: ['DEPENDS', 'HAS_PART', 'SPLIT_FROM', 'REFERENCES'],
      closure_direction: 'both',
      max_closure_nodes: 12,
      include_explain: true,
    })
    if (Array.isArray(result?.active_node_ids)) {
      setActiveIds(result.active_node_ids)
    }
    setPlannerResult(null)
    await reloadAll()
  }

  return (
    <div className="appShell">
      {isMobileLayout && (
        <div className="mobileSectionTabs card">
          <div className="row" style={{ marginBottom: 0 }}>
            <button className={mobileSection === 'center' ? 'primary' : ''} onClick={() => setMobileSection('center')}>
              Graph
            </button>
            <button className={mobileSection === 'left' ? 'primary' : ''} onClick={() => setMobileSection('left')}>
              Threads
            </button>
            <button className={mobileSection === 'right' ? 'primary' : ''} onClick={() => setMobileSection('right')}>
              Context
            </button>
          </div>
        </div>
      )}
      <div className="wrap" ref={wrapRef} style={wrapStyle}>
      <div className={`col col-left ${showLeftPanel ? '' : 'isMobileHidden'}`}>
        <div className="row">
          <button onClick={async () => {
            const t = await api.createThread('New Thread')
            const ts = await api.threads()
            setThreads(ts)
            await switchThread(t.id)
          }}>New Thread</button>
          <button className="danger" onClick={handleDeleteCurrentThread} disabled={!threadId}>Delete Thread</button>

          <select value={threadId || ''} onChange={async (e) => {
            await switchThread(e.target.value)
          }} style={{ flex: 1, padding: 6, borderRadius: 10, border: '1px solid #e5e7eb' }}>
            {threads.map(t => (
              <option key={t.id} value={t.id}>{t.title} ({t.id.slice(0,6)})</option>
            ))}
          </select>
        </div>

        <div className="row">
          <select value={ctxId || ''} onChange={async (e) => {
            const nextCtxId = e.target.value
            setCtxId(nextCtxId)
            if (threadId && nextCtxId) {
              await reloadAll(threadId, nextCtxId)
            }
          }} style={{ flex: 1, padding: 6, borderRadius: 10, border: '1px solid #e5e7eb' }}>
            {ctxSets.map(c => (
              <option key={c.id} value={c.id}>{c.name} ({c.id.slice(0,6)})</option>
            ))}
          </select>
          <button onClick={async () => {
            if (!threadId) return
            const name = prompt('ContextSet name?', 'alt')
            if (!name) return
            const created = await api.createCtx(threadId, name)
            const sets = await api.ctxSets(threadId)
            setCtxSets(sets)
            setCtxId(created.id)
            await reloadAll(threadId, created.id)
          }}>New ContextSet</button>
        </div>

        <div className="row">
          <button onClick={foldSelected}>Fold selected</button>
          <button onClick={() => reloadAll()}>Reload</button>
        </div>

        <SearchPanel
          onSearch={async (q) => {
            if (!threadId || !q) return []
            const r = await api.search(threadId, q, 10)
            return r.results || []
          }}
          onActivate={async (nodeId) => {
            await toggleActive(nodeId, true)
          }}
        />

        <Timeline
          nodes={nodes}
          activeIds={activeIds}
          onToggle={toggleActive}
          onOpenNode={(id) => setDetailNodeId(id)}
          partCountByParent={partCountByParent}
        />
      </div>

      {!isMobileLayout && (
        <div
          className="panelResizer"
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize left panel"
          onMouseDown={(evt) => startPanelResize('left', evt)}
        />
      )}

      <div className={`col col-center ${showCenterPanel ? '' : 'isMobileHidden'}`}>
        <div className="card selectionActionBar">
          <div className="row" style={{ marginBottom: 6 }}>
            <b>Fallback Actions</b>
            <span className="pill">selected: {selectedIds.length}</span>
            {selectedFoldIds.length > 0 && <span className="pill pill--fold">folds: {selectedFoldIds.length}</span>}
          </div>
          <div className="row" style={{ marginBottom: 0 }}>
            <button onClick={foldSelected} disabled={selectedIds.length < 2} title={selectedIds.length < 2 ? '그래프에서 2개 이상 선택하세요.' : '선택 노드를 Fold로 묶기'}>Fold selected</button>
            <button onClick={() => selectedIds.length === 1 && setDetailNodeId(selectedIds[0])} disabled={selectedIds.length !== 1} title={selectedIds.length === 1 ? '선택 노드 상세/분할' : '노드를 1개 선택하세요.'}>Open detail / split</button>
            <button onClick={unfoldSelectedFolds} disabled={selectedFoldIds.length === 0 || !ctxId} title={selectedFoldIds.length ? '선택 Fold 노드를 펼쳐 Active에 반영' : 'Fold 노드를 선택하세요.'}>Unfold selected folds</button>
            <button onClick={activateSelected} disabled={selectedIds.length === 0 || !ctxId}>Add selected to Active</button>
            <button onClick={() => setSelectedIds([])} disabled={selectedIds.length === 0}>Clear selection</button>
          </div>
          <div className="muted" style={{ marginTop: 6 }}>
            그래프 위 컨텍스트 메뉴가 기본 동선이며, 이 영역은 보조 동작입니다.
          </div>
        </div>
        <div className="graphWorkspace">
          <GraphPanel
            nodes={nodes}
            edges={edges}
            activeNodeIds={activeIds}
            selectedNodeIds={selectedIds}
            onSelectionChange={handleSelectionChange}
            onNodeOpenDetail={(id) => setDetailNodeId(id)}
            onCreateEdge={handleCreateEdge}
            onDeleteEdges={handleDeleteEdges}
            onDeleteNodes={handleDeleteNodes}
            onFoldSelected={foldNodeIds}
            onActivateNodes={activateNodeIds}
            onDeactivateNodes={deactivateNodeIds}
            onCommitUnfold={unfoldFold}
            onSaveLayout={saveGraphLayoutPositions}
            layoutScopeKey={threadId}
            priorityBucketByNodeId={graphPriorityBucketById}
          />
          {detailNodeId && (
            <NodeDetailModal
              nodeId={detailNodeId}
              threadId={threadId}
              ctxId={ctxId}
              mode="drawer"
              onClose={() => setDetailNodeId(null)}
              onAfterMutation={async () => {
                await reloadAll()
              }}
            />
          )}
        </div>
        <div className="muted" style={{ marginTop: 8 }}>
          그래프에서 직접 선택/단축키/컨텍스트 액션으로 Fold·Unfold·Split·Activate·Link를 수행하세요.
        </div>
      </div>

      {!isMobileLayout && (
        <div
          className="panelResizer"
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize right panel"
          onMouseDown={(evt) => startPanelResize('right', evt)}
        />
      )}

      <div className={`col col-right ${showRightPanel ? '' : 'isMobileHidden'}`}>
        <ActiveContext
          activeIds={activeIds}
          nodesById={nodesById}
          allNodes={nodes}
          onOpenNode={(id) => setDetailNodeId(id)}
          partCountByParent={partCountByParent}
          onAdd={async (id) => {
            await toggleActive(id, true)
          }}
          onReorder={reorderActive}
          onRemove={async (id) => {
            await toggleActive(id, false)
          }}
          onUnfold={unfoldFold}
        />

        <div className="card rightPanelTabs">
          <div className="row" style={{ marginBottom: 8 }}>
            <button className={rightPanelTab === 'inspector' ? 'primary' : ''} onClick={() => setRightPanelTab('inspector')}>Inspector</button>
            <button className={rightPanelTab === 'prompt' ? 'primary' : ''} onClick={() => setRightPanelTab('prompt')}>Prompt Builder</button>
            <button className={rightPanelTab === 'run' ? 'primary' : ''} onClick={() => setRightPanelTab('run')}>Run</button>
          </div>
          <div className="muted">
            {rightPanelTab === 'inspector' && 'Compiled context, version diff, recovery planner'}
            {rightPanelTab === 'prompt' && 'Copy/Paste, context suggestion, token budget, resource notes'}
            {rightPanelTab === 'run' && 'Run query with current Active Context'}
          </div>
        </div>

        {rightPanelTab === 'inspector' && (
          <ContextInspector
            compiledText={compiledInfo?.compiled_text || ''}
            excludedParentIds={compiledInfo?.explain?.excluded_parent_ids || []}
            keptNodeIds={compiledInfo?.explain?.kept_node_ids || []}
            versions={contextVersions}
            versionDiff={versionDiff}
            plannerResult={plannerResult}
            nodesById={nodesById}
            onRefresh={async () => {
              await refreshContextInspector()
            }}
            onLoadDiff={loadVersionDiff}
            onPlan={previewPlanner}
            onApplySeeds={applyPlannerSeeds}
          />
        )}

        {rightPanelTab === 'prompt' && (
          <CopyToChatGPTPanel
            activeNodes={activeNodes}
            allNodes={nodes}
            edges={edges}
            threadId={threadId}
            ctxId={ctxId}
            onAfterMutation={async () => {
              await reloadAll()
            }}
            onReplaceActive={replaceActiveContext}
          />
        )}

        {rightPanelTab === 'run' && (
          <RunPanel onRun={async (msg) => {
            if (!ctxId) return ''
            const out = await api.run(ctxId, msg)
            await reloadAll()
            return out.response_text || ''
          }} />
        )}
      </div>
    </div>
    </div>
  )
}
