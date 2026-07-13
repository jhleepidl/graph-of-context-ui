import React, { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, getStoredAdminKey, getStoredBearerToken, setStoredBearerToken } from '../api'
import RunPanel from '../components/RunPanel'
const Timeline = lazy(() => import('../components/Timeline'))
const GraphPanel = lazy(() => import('../components/GraphPanel'))
const ActiveContext = lazy(() => import('../components/ActiveContext'))
const SearchPanel = lazy(() => import('../components/SearchPanel'))
const CopyToChatGPTPanel = lazy(() => import('../components/CopyToChatGPTPanel'))
const NodeDetailModal = lazy(() => import('../components/NodeDetailModal'))
const ContextInspector = lazy(() => import('../components/ContextInspector'))
const JobSettingsPanel = lazy(() => import('../components/JobSettingsPanel'))
const ExecutionPanel = lazy(() => import('../components/ExecutionPanel'))
const ConversationAgentsPanel = lazy(() => import('../components/ConversationAgentsPanel'))
const CompanionControlHub = lazy(() => import('../components/CompanionControlHub'))
const RunStudioLayout = lazy(() => import('../components/run_studio/RunStudioLayout'))
const ArtifactsPanel = lazy(() => import('../components/run_studio/ArtifactsPanel'))
const BoardPanel = lazy(() => import('../components/BoardPanel'))
import WorkspaceShell from '../components/workspace/WorkspaceShell'
import WorkspaceRouteState from '../components/workspace/WorkspaceRouteState'
import { useRunStudioData } from '../hooks/useRunStudioData'
import { useRunStudioActions } from '../hooks/useRunStudioActions'
import { buildWorkspaceGroup, useWorkspaceThreadSelection } from '../hooks/useWorkspaceThreadSelection'
import { useWorkspaceTabs } from '../hooks/useWorkspaceTabs'
import { usePageVisibility } from '../hooks/usePageVisibility'
import { scoreNodesForRequest, type PriorityBucket } from '../utils/contextPriority'
import { workspacePollDelay } from '../utils/runtimePolling'

const PANEL_WIDTH_STORAGE_KEY = 'goc:panel-widths:v1'
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
type AuthGateState = 'checking' | 'ready' | 'blocked' | 'error'


function WorkspacePanelFallback({ label = '패널을 불러오는 중…' }: { label?: string }) {
  return (
    <div className="card">
      <div className="muted">{label}</div>
    </div>
  )
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function detectMobileLayout(): boolean {
  if (typeof window === 'undefined') return false
  return window.innerWidth <= MOBILE_LAYOUT_BREAKPOINT
}

function readTelegramInitData(): string {
  if (typeof window === 'undefined') return ''
  const tg = (window as any).Telegram
  const webApp = tg?.WebApp
  const initData = typeof webApp?.initData === 'string' ? webApp.initData.trim() : ''
  return initData
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    const raw = (error.message || '').trim()
    if (!raw) return 'Unknown error'
    try {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed === 'object' && typeof (parsed as any).detail === 'string') {
        return String((parsed as any).detail)
      }
    } catch {
      // ignore JSON parse errors
    }
    return raw
  }
  return String(error || 'Unknown error')
}

function graphNodesEqual(a: any[], b: any[]): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i += 1) {
    const left = a[i]
    const right = b[i]
    if (!left || !right) return false
    if (left.id !== right.id) return false
    if (left.type !== right.type) return false
    if ((left.text || '') !== (right.text || '')) return false
    if ((left.payload_json || '') !== (right.payload_json || '')) return false
    if ((left.created_at || '') !== (right.created_at || '')) return false
  }
  return true
}

function graphEdgesEqual(a: any[], b: any[]): boolean {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i += 1) {
    const left = a[i]
    const right = b[i]
    if (!left || !right) return false
    if (left.id !== right.id) return false
    if (left.from_id !== right.from_id || left.to_id !== right.to_id) return false
    if (left.type !== right.type) return false
    if ((left.payload_json || '') !== (right.payload_json || '')) return false
    if ((left.created_at || '') !== (right.created_at || '')) return false
  }
  return true
}

function captureTokenFromHash(): void {
  if (typeof window === 'undefined') return
  const rawHash = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : window.location.hash
  if (!rawHash) return

  const hashParams = new URLSearchParams(rawHash)
  const token = (hashParams.get('token') || '').trim()
  if (!token) return

  setStoredBearerToken(token)
  hashParams.delete('token')
  const nextHash = hashParams.toString()
  const nextUrl = `${window.location.pathname}${window.location.search}${nextHash ? `#${nextHash}` : ''}`
  window.history.replaceState(null, '', nextUrl)
}

export default function WorkspaceApp() {
  const wrapRef = useRef<HTMLDivElement | null>(null)
  const pageVisible = usePageVisibility()
  const [authGateState, setAuthGateState] = useState<AuthGateState>('checking')
  const [authGateMessage, setAuthGateMessage] = useState<string>('')
  const {
    workspaceMainTab,
    setWorkspaceMainTab,
    rightPanelTab,
    setRightPanelTab,
    mobileSection,
    setMobileSection,
    workspaceMainTabLabel,
  } = useWorkspaceTabs()
  const {
    summary: runStudioSummary,
    agentTeam: runStudioAgentTeam,
    contextDecisions: runStudioContextDecisions,
    evidence: runStudioEvidence,
    contextPacks: runStudioContextPacks,
    skillUsage: runStudioSkillUsage,
    memoryGraph: runStudioMemoryGraph,
    memoryTopology: runStudioMemoryTopology,
    memoryDemand: runStudioMemoryDemand,
    traceScope: runStudioTraceScope,
    crossReferences: runStudioCrossReferences,
    auditTimeline: runStudioAuditTimeline,
    projectionRetrieval: runStudioProjectionRetrieval,
    graphCompression: runStudioGraphCompression,
    harnessSpec: runStudioHarnessSpec,
    harnessSummary: runStudioHarnessSummary,
    teamSelection: runStudioTeamSelection,
    detailLoaded: runStudioDetailLoaded,
    detailLoading: runStudioDetailLoading,
    focusedRunId: runStudioFocusedRunId,
    focusedEventId: runStudioFocusedEventId,
    focusedEventLabel: runStudioFocusedEventLabel,
    loading: runStudioLoading,
    error: runStudioError,
    refresh: refreshRunStudio,
    clear: clearRunStudio,
    loadAgentTeam: loadRunStudioAgentTeam,
    loadContextDecisions: loadRunStudioContextDecisions,
    loadEvidence: loadRunStudioEvidence,
    loadContextPacks: loadRunStudioContextPacks,
    loadSkillUsage: loadRunStudioSkillUsage,
    loadMemoryGraph: loadRunStudioMemoryGraph,
    loadMemoryTopology: loadRunStudioMemoryTopology,
    loadMemoryDemand: loadRunStudioMemoryDemand,
    loadTraceScope: loadRunStudioTraceScope,
    loadTeamSelection: loadRunStudioTeamSelection,
    focusRunDrilldown: focusRunStudioDrilldown,
    clearRunDrilldown: clearRunStudioDrilldown,
  } = useRunStudioData()
  const runStudioStatus = String(
    runStudioSummary?.now?.state?.current_run_status
      || runStudioSummary?.projections?.execution?.current_step?.status
      || '',
  ).trim().toLowerCase()
  const runStudioActive = ['active', 'running', 'queued', 'accepted', 'working'].includes(runStudioStatus)
  const {
    threads,
    setThreads,
    workspaceKey,
    setWorkspaceKey,
    threadId,
    setThreadId,
    threadResolutionNotice,
    setThreadResolutionNotice,
    workspaceGroups,
    visibleThreads,
    initialDeepLink,
    loadThreads,
    setWorkspaceKeyForThread,
  } = useWorkspaceThreadSelection()

  const [ctxSets, setCtxSets] = useState<any[]>([])
  const [ctxId, setCtxId] = useState<string | null>(null)

  const [nodes, setNodes] = useState<any[]>([])
  const [edges, setEdges] = useState<any[]>([])
  const [activeIds, setActiveIds] = useState<string[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [detailNodeId, setDetailNodeId] = useState<string | null>(null)
  const [executionFocusNodeId, setExecutionFocusNodeId] = useState<string | null>(null)
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
    await refreshRunStudio(tId, cId, { silent: true, includeLoadedDetails: true })
  }

  async function loadCtxSets(tid: string, preferredCtxId?: string | null) {
    const sets = await api.ctxSets(tid)
    let nextSets = sets
    let cid = sets[0]?.id
    if (preferredCtxId && sets.some((c) => c.id === preferredCtxId)) {
      cid = preferredCtxId
    }
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
    setExecutionFocusNodeId(null)
    setCompiledInfo(null)
    setContextVersions([])
    setVersionDiff(null)
    setPlannerResult(null)
    clearRunStudio()
  }

  async function switchThread(nextThreadId: string, preferredCtxId?: string | null) {
    if (!nextThreadId) return
    const seq = ++switchSeqRef.current

    setThreadResolutionNotice('')
    setThreadId(nextThreadId)
    setWorkspaceKeyForThread(nextThreadId)
    clearThreadScopedState()

    try {
      const { sets, cid } = await loadCtxSets(nextThreadId, preferredCtxId)
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
      await refreshRunStudio(nextThreadId, cid, { silent: true, includeLoadedDetails: true })
    } catch (e) {
      console.error('failed to switch thread', e)
    }
  }

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setAuthGateState('checking')
      setAuthGateMessage('')
      captureTokenFromHash()

      const adminKey = getStoredAdminKey()
      if (adminKey) {
        if (cancelled) return
        setAuthGateState('ready')
        const tid = await loadThreads(initialDeepLink.threadId)
        if (cancelled) return
        if (!tid) {
          setThreadId(null)
          clearThreadScopedState()
          return
        }
        await switchThread(tid, initialDeepLink.ctxId)
        return
      }

      let token = getStoredBearerToken()
      if (!token) {
        const initData = readTelegramInitData()
        if (!initData) {
          if (!cancelled) {
            setAuthGateState('blocked')
          }
          return
        }
        try {
          const out = await api.telegramWebAppLogin({ init_data: initData })
          const nextToken = (out?.token || '').trim()
          if (!nextToken) {
            throw new Error('telegram login response missing token')
          }
          setStoredBearerToken(nextToken)
          token = nextToken
        } catch (error) {
          if (!cancelled) {
            setAuthGateState('error')
            setAuthGateMessage(toErrorMessage(error))
          }
          return
        }
      }

      if (!token || cancelled) return
      setAuthGateState('ready')
      const tid = await loadThreads(initialDeepLink.threadId)
      if (cancelled) return
      if (!tid) {
        setThreadId(null)
        clearThreadScopedState()
        return
      }
      await switchThread(tid, initialDeepLink.ctxId)
    })()
    return () => {
      cancelled = true
    }
  }, [initialDeepLink])

  useEffect(() => {
    try {
      window.localStorage.setItem(PANEL_WIDTH_STORAGE_KEY, JSON.stringify(panelWidths))
    } catch {
      // ignore localStorage errors
    }
  }, [panelWidths])

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
    const session = resizeSession

    function handleMouseMove(evt: MouseEvent) {
      const dx = evt.clientX - session.startX
      const totalResizerWidth = RESIZER_WIDTH * 2

      if (session.handle === 'left') {
        const maxLeft = session.wrapWidth - session.startRightWidth - CENTER_PANEL_MIN_WIDTH - totalResizerWidth
        const upper = Math.max(LEFT_PANEL_MIN_WIDTH, maxLeft)
        const nextLeft = Math.round(clamp(session.startLeftWidth + dx, LEFT_PANEL_MIN_WIDTH, upper))
        setPanelWidths((prev) => (prev.left === nextLeft ? prev : { ...prev, left: nextLeft }))
        return
      }

      const maxRight = session.wrapWidth - session.startLeftWidth - CENTER_PANEL_MIN_WIDTH - totalResizerWidth
      const upper = Math.max(RIGHT_PANEL_MIN_WIDTH, maxRight)
      const nextRight = Math.round(clamp(session.startRightWidth - dx, RIGHT_PANEL_MIN_WIDTH, upper))
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

  useEffect(() => {
    if (workspaceMainTab !== 'run_studio' && workspaceMainTab !== 'raw_trace') return
    if (!threadId) return

    let cancelled = false
    let timer: number | null = null
    let pollCount = 0

    const schedule = (delay: number) => {
      if (cancelled) return
      timer = window.setTimeout(() => void poll(), delay)
    }

    const poll = async () => {
      if (cancelled) return
      pollCount += 1
      try {
        if (workspaceMainTab === 'raw_trace') {
          const g = await api.graph(threadId)
          if (cancelled) return
          const nextNodes = Array.isArray(g?.nodes) ? g.nodes : []
          const nextEdges = Array.isArray(g?.edges) ? g.edges : []
          setNodes((prev) => (graphNodesEqual(prev, nextNodes) ? prev : nextNodes))
          setEdges((prev) => (graphEdgesEqual(prev, nextEdges) ? prev : nextEdges))
        } else {
          const includeLoadedDetails = pollCount === 1 || (runStudioActive ? pollCount % 3 === 0 : pollCount % 6 === 0)
          await refreshRunStudio(threadId, ctxId || undefined, { silent: pollCount > 1, includeLoadedDetails })
        }
      } catch (e) {
        console.error('workspace refresh failed', e)
      } finally {
        if (!cancelled) {
          schedule(workspacePollDelay({ active: runStudioActive, visible: pageVisible, rawTrace: workspaceMainTab === 'raw_trace' }))
        }
      }
    }

    void poll()
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [workspaceMainTab, threadId, ctxId, pageVisible, runStudioActive, refreshRunStudio])

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
  const showRightPanel = workspaceMainTab === 'graph' && (!isMobileLayout || mobileSection === 'right')

  async function toggleActive(nodeId: string, nextActive: boolean) {
    if (!ctxId) return
    if (nextActive) {
      const out = await api.activate(ctxId, [nodeId])
      if (Array.isArray(out?.active_node_ids)) {
        setActiveIds(out.active_node_ids)
        await refreshContextInspector(ctxId)
        await refreshRunStudio(threadId || undefined, ctxId, { silent: true, includeLoadedDetails: true })
        return
      }
    } else {
      const out = await api.deactivate(ctxId, [nodeId])
      if (Array.isArray(out?.active_node_ids)) {
        setActiveIds(out.active_node_ids)
        await refreshContextInspector(ctxId)
        await refreshRunStudio(threadId || undefined, ctxId, { silent: true, includeLoadedDetails: true })
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
      await refreshRunStudio(threadId || undefined, ctxId, { silent: true, includeLoadedDetails: true })
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
      await refreshRunStudio(threadId || undefined, ctxId, { silent: true, includeLoadedDetails: true })
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
      await refreshRunStudio(threadId || undefined, ctxId, { silent: true, includeLoadedDetails: true })
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
      await refreshRunStudio(threadId || undefined, ctxId, { silent: true, includeLoadedDetails: true })
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
      await Promise.all(nodeIds.map((nodeId) => api.deleteNodeById(nodeId)))
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
      await refreshRunStudio(threadId || undefined, ctxId, { silent: true, includeLoadedDetails: true })
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
        setWorkspaceKey(buildWorkspaceGroup(created).key)
        await switchThread(created.id)
        return
      }

      const nextInWorkspace = ts.find((t) => buildWorkspaceGroup(t).key === workspaceKey)
      if (nextInWorkspace) {
        await switchThread(nextInWorkspace.id)
        return
      }
      setWorkspaceKey(buildWorkspaceGroup(ts[0]).key)
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
  const {
    focusNodesInGraph,
    openNodesInGraph,
    focusNodeInGraph,
    openNodeInGraph,
    addNodeToActiveFromStudio,
    pinNodeFromStudio,
  } = useRunStudioActions({
    nodesById,
    setWorkspaceMainTab,
    setSelectedIds,
    setDetailNodeId,
    activateNodeIds,
    reloadAll,
    threadId,
    ctxId,
  })


  const openRawTraceNodeFromStudio = useCallback((nodeId: string) => {
    const clean = String(nodeId || '').trim()
    if (!clean || !nodesById.has(clean)) return
    setExecutionFocusNodeId(clean)
    setWorkspaceMainTab('raw_trace')
  }, [nodesById, setWorkspaceMainTab])

  const leftPanelContent = (
    <aside className="roomSidebar" aria-label="작업방 탐색">
      {threadResolutionNotice && (
        <div className="runStudioWarning roomSidebarNotice">
          <b>Deep-link notice:</b> {threadResolutionNotice}
        </div>
      )}

      <header className="roomSidebarHeader">
        <div>
          <div className="runStudioEyebrow">작업방</div>
          <h2>내 작업 공간</h2>
        </div>
        <button
          className="primary roomSidebarNewButton"
          onClick={async () => {
            const t = await api.createThread('New Room')
            const ts = await api.threads()
            setThreads(ts)
            setWorkspaceKey(buildWorkspaceGroup(t).key)
            await switchThread(t.id)
          }}
        >
          + 새 작업방
        </button>
      </header>

      <label className="roomSidebarWorkspacePicker">
        <span>작업 공간</span>
        <select
          value={workspaceKey}
          onChange={async (e) => {
            const nextWorkspaceKey = e.target.value
            setWorkspaceKey(nextWorkspaceKey)
            const nextGroup = workspaceGroups.find((group) => group.key === nextWorkspaceKey)
            if (!nextGroup || nextGroup.threadIds.length === 0) return
            if (threadId && nextGroup.threadIds.includes(threadId)) return
            await switchThread(nextGroup.threadIds[0])
          }}
        >
          {workspaceGroups.map((group) => (
            <option key={group.key} value={group.key}>
              {group.label} ({group.threadIds.length})
            </option>
          ))}
        </select>
      </label>

      <div className="roomSidebarList" role="list" aria-label="작업 공간의 작업방">
        {visibleThreads.length === 0 && <div className="roomSidebarEmpty">이 작업 공간에는 아직 작업방이 없습니다.</div>}
        {visibleThreads.map((t) => {
          const selected = t.id === threadId
          return (
            <button
              type="button"
              role="listitem"
              key={t.id}
              className={`roomSidebarItem ${selected ? 'isActive' : ''}`}
              onClick={() => void switchThread(t.id)}
            >
              <span className="roomSidebarItemMark" aria-hidden="true" />
              <span className="roomSidebarItemText">
                <b>{t.title || '이름 없는 작업방'}</b>
                <small>{t.id.slice(0, 8)}</small>
              </span>
            </button>
          )
        })}
      </div>

      {threadId && (
        <div className="roomSidebarSelectedTools">
          <div className="roomSidebarSelectedHeading">
            <span>선택한 작업방</span>
            <button className="dangerText" onClick={handleDeleteCurrentThread}>삭제</button>
          </div>

          <label>
            <span>사용할 정보</span>
            <select value={ctxId || ''} onChange={async (e) => {
              const nextCtxId = e.target.value
              setCtxId(nextCtxId)
              if (threadId && nextCtxId) await reloadAll(threadId, nextCtxId)
            }}>
              {ctxSets.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </label>

          <div className="roomSidebarToolRow">
            <button onClick={async () => {
              const name = prompt('새 정보 설정의 이름을 입력하세요.', '다른 자료 범위')
              if (!name) return
              const created = await api.createCtx(threadId, name)
              const sets = await api.ctxSets(threadId)
              setCtxSets(sets)
              setCtxId(created.id)
              await reloadAll(threadId, created.id)
            }}>새 정보 설정</button>
            <button onClick={() => void reloadAll()}>다시 불러오기</button>
          </div>

          <button
            className="roomSidebarAgentLink"
            onClick={() => {
              const suffix = ctxId ? `&ctx=${encodeURIComponent(ctxId)}` : ''
              const target = `/agents?thread=${encodeURIComponent(threadId)}${suffix}`
              window.history.pushState(null, '', target)
              window.dispatchEvent(new Event('popstate'))
            }}
          >
            AI 구성 열기 (고급)
          </button>
        </div>
      )}

      <details className="roomSidebarDetails">
        <summary>작업방 기억 검색</summary>
        <Suspense fallback={<WorkspacePanelFallback label="검색 패널을 불러오는 중…" />}>
          <SearchPanel
            onSearch={async (q) => {
              if (!threadId || !q) return []
              const r = await api.search(threadId, q, 10)
              return r.results || []
            }}
            onActivate={async (nodeId) => { await toggleActive(nodeId, true) }}
          />
        </Suspense>
      </details>

      <details className="roomSidebarDetails">
        <summary>변경 기록 찾아보기</summary>
        <Suspense fallback={<WorkspacePanelFallback label="타임라인을 불러오는 중…" />}>
          <Timeline
            nodes={nodes}
            activeIds={activeIds}
            onToggle={toggleActive}
            onOpenNode={(id) => setDetailNodeId(id)}
            partCountByParent={partCountByParent}
          />
        </Suspense>
      </details>

      {selectedIds.length > 0 && (
        <button className="roomSidebarFoldButton" onClick={foldSelected}>
          Fold {selectedIds.length} selected nodes
        </button>
      )}
    </aside>
  )

  const centerPanelContent = (
    <>
      {!threadId && (
        <div className="card">
          <div className="runStudioWarning">
            <b>No thread selected.</b> {threadResolutionNotice || 'Select a thread to open its Room state.'}
          </div>
        </div>
      )}

      <WorkspaceRouteState
        workspaceMainTab={workspaceMainTab}
        setWorkspaceMainTab={setWorkspaceMainTab}
      />

      {workspaceMainTab === 'companion' && (
        <Suspense fallback={<WorkspacePanelFallback label="Room Home을 불러오는 중…" />}>
          <CompanionControlHub threadId={threadId} />
        </Suspense>
      )}

      {workspaceMainTab === 'run_studio' && (
        <Suspense fallback={<WorkspacePanelFallback label="Room Work를 불러오는 중…" />}>
          <RunStudioLayout
          threadId={threadId}
          summary={runStudioSummary}
          team={runStudioAgentTeam}
          decisions={runStudioContextDecisions}
          evidence={runStudioEvidence}
          contextPacks={runStudioContextPacks}
          skillUsage={runStudioSkillUsage}
          memoryGraph={runStudioMemoryGraph}
          memoryTopology={runStudioMemoryTopology}
          memoryDemand={runStudioMemoryDemand}
          traceScope={runStudioTraceScope}
          crossReferences={runStudioCrossReferences}
          auditTimeline={runStudioAuditTimeline}
          projectionRetrieval={runStudioProjectionRetrieval}
          graphCompression={runStudioGraphCompression}
          harnessSpec={runStudioHarnessSpec}
          harnessSummary={runStudioHarnessSummary}
          teamSelection={runStudioTeamSelection}
          detailLoaded={runStudioDetailLoaded}
          detailLoading={runStudioDetailLoading}
          loading={runStudioLoading}
          error={runStudioError}
          onRefresh={() => {
            void refreshRunStudio(threadId || undefined, ctxId || undefined, { includeLoadedDetails: true })
          }}
          onLoadAgentTeam={() => {
            void loadRunStudioAgentTeam(threadId || undefined)
          }}
          onLoadContextDecisions={() => {
            void loadRunStudioContextDecisions(threadId || undefined, ctxId || undefined)
          }}
          onLoadEvidence={() => {
            void loadRunStudioEvidence(threadId || undefined, ctxId || undefined, runStudioFocusedRunId || undefined)
          }}
          onLoadContextPacks={() => {
            const currentRunId = runStudioFocusedRunId || runStudioSummary?.current_run_skills?.run_id
            void loadRunStudioContextPacks(threadId || undefined, currentRunId || undefined)
          }}
          onLoadSkillUsage={() => {
            const currentRunId = runStudioFocusedRunId || runStudioSummary?.current_run_skills?.run_id
            void loadRunStudioSkillUsage(threadId || undefined, currentRunId || undefined)
          }}
          onLoadMemoryGraph={() => {
            const currentRunId = runStudioFocusedRunId || runStudioSummary?.current_run_skills?.run_id
            void loadRunStudioMemoryGraph(threadId || undefined, currentRunId || undefined)
          }}
          onLoadMemoryTopology={() => {
            const currentRunId = runStudioFocusedRunId || runStudioSummary?.current_run_skills?.run_id
            void loadRunStudioMemoryTopology(threadId || undefined, currentRunId || undefined)
          }}
          onLoadMemoryDemand={() => {
            const currentRunId = runStudioFocusedRunId || runStudioSummary?.current_run_skills?.run_id
            void loadRunStudioMemoryDemand(threadId || undefined, currentRunId || undefined)
          }}
          onLoadTraceScope={() => {
            const currentRunId = runStudioFocusedRunId || runStudioSummary?.current_run_skills?.run_id
            void loadRunStudioTraceScope(threadId || undefined, currentRunId || undefined)
          }}
          onLoadTeamSelection={() => {
            void loadRunStudioTeamSelection(threadId || undefined)
          }}
          onInspectTeamSelectionEvent={(row) => {
            void focusRunStudioDrilldown(
              threadId || undefined,
              ctxId || undefined,
              row?.run_id || undefined,
              { eventId: row?.event_id || undefined, label: row?.run_id || row?.event_id || undefined },
            )
          }}
          onClearRunDrilldown={() => {
            void clearRunStudioDrilldown(threadId || undefined, ctxId || undefined)
          }}
          focusedRunId={runStudioFocusedRunId}
          focusedEventId={runStudioFocusedEventId}
          focusedEventLabel={runStudioFocusedEventLabel}
          onOpenGraph={() => setWorkspaceMainTab('graph')}
          onOpenRawTrace={() => setWorkspaceMainTab('raw_trace')}
          onOpenRawTraceNode={openRawTraceNodeFromStudio}
          onOpenAdvanced={() => setWorkspaceMainTab('advanced')}
          onFocusNode={focusNodeInGraph}
          onOpenNode={openNodeInGraph}
          onFocusTrace={focusNodesInGraph}
          onOpenTrace={openNodesInGraph}
          onAddToActive={addNodeToActiveFromStudio}
          onPinNode={pinNodeFromStudio}
          />
        </Suspense>
      )}

      {workspaceMainTab === 'board' && (
        <Suspense fallback={<WorkspacePanelFallback label="Board를 불러오는 중…" />}>
          <BoardPanel threadId={threadId} />
        </Suspense>
      )}

      {workspaceMainTab === 'raw_trace' && (
        <Suspense fallback={<WorkspacePanelFallback label="실행 트레이스를 불러오는 중…" />}>
          <ExecutionPanel
          threadId={threadId}
          nodes={nodes}
          edges={edges}
          focusNodeId={executionFocusNodeId}
          onOpenOldGraph={(nodeId) => {
            setWorkspaceMainTab('graph')
            if (nodeId) setSelectedIds([nodeId])
          }}
          />
        </Suspense>
      )}

      {workspaceMainTab === 'artifacts' && (
        <Suspense fallback={<WorkspacePanelFallback label="결과물 패널을 불러오는 중…" />}>
          <ArtifactsPanel nodes={nodes} activeIds={activeIds} />
        </Suspense>
      )}

      {workspaceMainTab === 'advanced' && (
        <div className="runStudioAdvancedGrid">
          <div>
            <Suspense fallback={<WorkspacePanelFallback label="Active Context를 불러오는 중…" />}>
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
            </Suspense>
          </div>
          <div>
            <div className="card rightPanelTabs">
              <div className="row" style={{ marginBottom: 8 }}>
                <button className={rightPanelTab === 'prompt' ? 'primary' : ''} onClick={() => setRightPanelTab('prompt')}>Prompt Builder</button>
                <button className={rightPanelTab === 'run' ? 'primary' : ''} onClick={() => setRightPanelTab('run')}>Run</button>
                <button className={rightPanelTab === 'job_settings' ? 'primary' : ''} onClick={() => setRightPanelTab('job_settings')}>Job Settings</button>
                <button className={rightPanelTab === 'conversation_agents' ? 'primary' : ''} onClick={() => setRightPanelTab('conversation_agents')}>Thread Team Config</button>
                <button className={rightPanelTab === 'inspector' ? 'primary' : ''} onClick={() => setRightPanelTab('inspector')}>Inspector</button>
              </div>
              <div className="muted">
                {rightPanelTab === 'prompt' && 'Copy/Paste, context suggestion, token budgeting, resource notes'}
                {rightPanelTab === 'run' && 'Run query with current active context'}
                {rightPanelTab === 'job_settings' && 'Edit agent_set/tool_set for current thread'}
                {rightPanelTab === 'conversation_agents' && 'Configure thread team defaults (setup only; actual runtime team appears in Room Work)'}
                {rightPanelTab === 'inspector' && 'Compiled context and version/planner diagnostics'}
              </div>
            </div>

            {rightPanelTab === 'prompt' && (
              <Suspense fallback={<WorkspacePanelFallback label="Prompt Builder를 불러오는 중…" />}>
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
              </Suspense>
            )}

            {rightPanelTab === 'run' && (
              <RunPanel onRun={async (msg) => {
                if (!ctxId) return ''
                const out = await api.run(ctxId, msg)
                await reloadAll()
                return out.response_text || ''
              }} />
            )}

            {rightPanelTab === 'job_settings' && (
              <Suspense fallback={<WorkspacePanelFallback label="Job Settings를 불러오는 중…" />}>
                <JobSettingsPanel
                threadId={threadId}
                threads={threads}
                onAfterSave={async () => {
                  await reloadAll(threadId || undefined, ctxId || undefined)
                }}
                />
              </Suspense>
            )}

            {rightPanelTab === 'conversation_agents' && (
              <Suspense fallback={<WorkspacePanelFallback label="Thread Team Config를 불러오는 중…" />}>
                <ConversationAgentsPanel threadId={threadId} />
              </Suspense>
            )}

            {rightPanelTab === 'inspector' && (
              <Suspense fallback={<WorkspacePanelFallback label="Inspector를 불러오는 중…" />}>
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
              </Suspense>
            )}
          </div>
        </div>
      )}

      {workspaceMainTab === 'graph' && (
        <>
          <div className="card selectionActionBar">
            <div className="row" style={{ marginBottom: 6 }}>
              <b>Graph Actions</b>
              <span className="pill">selected: {selectedIds.length}</span>
              {selectedFoldIds.length > 0 && <span className="pill pill--fold">folds: {selectedFoldIds.length}</span>}
            </div>
            <div className="row" style={{ marginBottom: 0 }}>
              <button onClick={foldSelected} disabled={selectedIds.length < 2}>Fold selected</button>
              <button onClick={() => selectedIds.length === 1 && setDetailNodeId(selectedIds[0])} disabled={selectedIds.length !== 1}>Open detail / split</button>
              <button onClick={unfoldSelectedFolds} disabled={selectedFoldIds.length === 0 || !ctxId}>Unfold selected folds</button>
              <button onClick={activateSelected} disabled={selectedIds.length === 0 || !ctxId}>Add selected to Active</button>
              <button onClick={() => setSelectedIds([])} disabled={selectedIds.length === 0}>Clear selection</button>
            </div>
          </div>
          <div className="graphWorkspace">
            <Suspense fallback={<WorkspacePanelFallback label="그래프를 불러오는 중…" />}>
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
            </Suspense>
            {detailNodeId && (
              <Suspense fallback={<WorkspacePanelFallback label="노드 상세를 불러오는 중…" />}>
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
              </Suspense>
            )}
          </div>
        </>
      )}
    </>
  )

  const rightPanelContent = workspaceMainTab === 'graph' ? (
    <>
      <Suspense fallback={<WorkspacePanelFallback label="Active Context를 불러오는 중…" />}>
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
      </Suspense>

      <div className="card rightPanelTabs">
        <div className="row" style={{ marginBottom: 8 }}>
          <button
            className={(rightPanelTab !== 'conversation_agents') ? 'primary' : ''}
            onClick={() => setRightPanelTab('inspector')}
          >
            Inspector
          </button>
          <button
            className={rightPanelTab === 'conversation_agents' ? 'primary' : ''}
            onClick={() => setRightPanelTab('conversation_agents')}
          >
            Thread Team Config
          </button>
        </div>
        <div className="muted">
          {(rightPanelTab === 'conversation_agents')
            ? 'Configure thread team defaults (setup only)'
            : 'Compiled context, version diff, and planner diagnostics'}
        </div>
      </div>

      {rightPanelTab === 'conversation_agents' ? (
        <Suspense fallback={<WorkspacePanelFallback label="Thread Team Config를 불러오는 중…" />}>
          <ConversationAgentsPanel threadId={threadId} />
        </Suspense>
      ) : (
        <Suspense fallback={<WorkspacePanelFallback label="Inspector를 불러오는 중…" />}>
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
        </Suspense>
      )}
    </>
  ) : null

  if (authGateState !== 'ready') {
    const isChecking = authGateState === 'checking'
    const isBlocked = authGateState === 'blocked'
    const title = isChecking ? 'Signing in...' : isBlocked ? 'Telegram Login Required' : 'Telegram Login Failed'
    return (
      <div className="routePage">
        <div className="routeCard" style={{ maxWidth: 720 }}>
          <h3 style={{ marginTop: 0 }}>{title}</h3>
          {isChecking && (
            <p className="muted" style={{ fontSize: 14 }}>
              Checking auth token and Telegram WebApp session.
            </p>
          )}
          {isBlocked && (
            <div className="muted" style={{ fontSize: 14 }}>
              <p style={{ marginTop: 0, marginBottom: 8 }}>로그인 정보를 찾을 수 없습니다. 아래 방법으로 접속해 주세요.</p>
              <ol style={{ marginTop: 0, marginBottom: 0, paddingLeft: 18 }}>
                <li>Telegram에서 Open GoC (Mini App) 버튼으로 열면 자동 로그인됩니다(HTTPS 필요).</li>
                <li>브라우저로 열려면 봇에서 /context로 받은 Browser 링크(토큰 포함)를 사용하세요.</li>
              </ol>
            </div>
          )}
          {!isChecking && !isBlocked && (
            <p className="muted" style={{ fontSize: 14 }}>
              {`인증에 실패했습니다. ${authGateMessage || ''}`.trim()}
            </p>
          )}
          {!isChecking && (
            <div className="row">
              <button onClick={() => window.location.reload()}>Retry</button>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <WorkspaceShell
      isMobileLayout={isMobileLayout}
      mobileSection={mobileSection}
      setMobileSection={setMobileSection}
      workspaceMainTab={workspaceMainTab}
      workspaceMainTabLabel={workspaceMainTabLabel}
      wrapRef={wrapRef}
      wrapStyle={wrapStyle}
      showLeftPanel={showLeftPanel}
      showCenterPanel={showCenterPanel}
      showRightPanel={showRightPanel}
      onStartLeftResize={(evt) => startPanelResize('left', evt)}
      onStartRightResize={(evt) => startPanelResize('right', evt)}
      leftContent={leftPanelContent}
      centerContent={centerPanelContent}
      rightContent={rightPanelContent}
    />
  )
}
