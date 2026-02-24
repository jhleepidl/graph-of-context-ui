import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api'
import Timeline from './components/Timeline'
import GraphPanel from './components/GraphPanel'
import ActiveContext from './components/ActiveContext'
import RunPanel from './components/RunPanel'
import SearchPanel from './components/SearchPanel'
import CopyToChatGPTPanel from './components/CopyToChatGPTPanel'
import NodeDetailModal from './components/NodeDetailModal'

export default function App() {
  const [threads, setThreads] = useState<any[]>([])
  const [threadId, setThreadId] = useState<string | null>(null)

  const [ctxSets, setCtxSets] = useState<any[]>([])
  const [ctxId, setCtxId] = useState<string | null>(null)

  const [nodes, setNodes] = useState<any[]>([])
  const [edges, setEdges] = useState<any[]>([])
  const [activeIds, setActiveIds] = useState<string[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [detailNodeId, setDetailNodeId] = useState<string | null>(null)
  const switchSeqRef = useRef(0)

  const nodesById = useMemo(() => new Map(nodes.map(n => [n.id, n])), [nodes])
  const activeNodes = useMemo(() => activeIds.map((id) => nodesById.get(id)).filter(Boolean), [activeIds, nodesById])
  const selectedFoldIds = useMemo(() => selectedIds.filter((id) => nodesById.get(id)?.type === 'Fold'), [selectedIds, nodesById])
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

  async function toggleActive(nodeId: string, nextActive: boolean) {
    if (!ctxId) return
    if (nextActive) await api.activate(ctxId, [nodeId])
    else await api.deactivate(ctxId, [nodeId])
    await reloadAll()
  }

  async function reorderActive(nodeIds: string[]) {
    if (!ctxId) return
    try {
      await api.reorderActive(ctxId, nodeIds)
      setActiveIds(nodeIds)
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
    // MVP UX: 원본 off, fold on
    await api.deactivate(ctxId, ids)
    await api.activate(ctxId, [res.fold_id])
    setSelectedIds([res.fold_id])
    await reloadAll()
  }

  async function activateNodeIds(nodeIds: string[]) {
    if (!ctxId || nodeIds.length === 0) return
    await api.activate(ctxId, nodeIds)
    await reloadAll()
  }

  async function deactivateNodeIds(nodeIds: string[]) {
    if (!ctxId || nodeIds.length === 0) return
    await api.deactivate(ctxId, nodeIds)
    await reloadAll()
  }

  async function foldSelected() {
    await foldNodeIds(selectedIds)
  }

  async function unfoldFold(foldId: string) {
    if (!ctxId) return
    const out = await api.unfold(ctxId, foldId)
    if (Array.isArray(out?.members) && out.members.length > 0) {
      setSelectedIds(out.members)
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


  async function activateSelected() {
    await activateNodeIds(selectedIds)
  }

  async function unfoldSelectedFolds() {
    if (!ctxId) return
    if (selectedFoldIds.length === 0) return
    for (const foldId of selectedFoldIds) {
      await api.unfold(ctxId, foldId)
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

  return (
    <div className="wrap">
      <div className="col">
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

      <div className="col">
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

      <div className="col">
        <ActiveContext
          activeIds={activeIds}
          nodesById={nodesById}
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

        <hr />
        <CopyToChatGPTPanel
          activeNodes={activeNodes}
          threadId={threadId}
          ctxId={ctxId}
          onAfterMutation={async () => {
            await reloadAll()
          }}
        />

        <hr />

        <RunPanel onRun={async (msg) => {
          if (!ctxId) return ''
          const out = await api.run(ctxId, msg)
          await reloadAll()
          return out.response_text || ''
        }} />
      </div>
    </div>
  )
}
