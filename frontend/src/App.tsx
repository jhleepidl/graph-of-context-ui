import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import Timeline from './components/Timeline'
import GraphPanel from './components/GraphPanel'
import ActiveContext from './components/ActiveContext'
import RunPanel from './components/RunPanel'
import SearchPanel from './components/SearchPanel'
import CopyToChatGPTPanel from './components/CopyToChatGPTPanel'

export default function App() {
  const [threads, setThreads] = useState<any[]>([])
  const [threadId, setThreadId] = useState<string | null>(null)

  const [ctxSets, setCtxSets] = useState<any[]>([])
  const [ctxId, setCtxId] = useState<string | null>(null)

  const [nodes, setNodes] = useState<any[]>([])
  const [edges, setEdges] = useState<any[]>([])
  const [activeIds, setActiveIds] = useState<string[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])

  const nodesById = useMemo(() => new Map(nodes.map(n => [n.id, n])), [nodes])
  const activeNodes = useMemo(() => activeIds.map((id) => nodesById.get(id)).filter(Boolean), [activeIds, nodesById])
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
    }
    setThreadId(tid)
    return tid
  }

  async function loadCtxSets(tid: string) {
    const sets = await api.ctxSets(tid)
    setCtxSets(sets)
    let cid = sets[0]?.id
    if (!cid) {
      const cs = await api.createCtx(tid, 'default')
      cid = cs.id
    }
    setCtxId(cid)
    return cid
  }

  useEffect(() => {
    (async () => {
      const tid = await loadThreads()
      const cid = await loadCtxSets(tid)
      await reloadAll(tid, cid)
    })()
  }, [])

  useEffect(() => {
    if (!threadId) return
    (async () => {
      const cid = await loadCtxSets(threadId)
      await reloadAll(threadId, cid)
    })()
  }, [threadId])

  useEffect(() => {
    if (!threadId || !ctxId) return
    reloadAll(threadId, ctxId)
  }, [ctxId])

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

  async function foldSelected() {
    if (!threadId || !ctxId) return
    const ids = selectedIds
    if (ids.length < 2) {
      alert('그래프에서 2개 이상 노드를 선택하세요.')
      return
    }
    const res = await api.fold(threadId, ids, 'Fold')
    // MVP UX: 원본 off, fold on
    await api.deactivate(ctxId, ids)
    await api.activate(ctxId, [res.fold_id])
    setSelectedIds([])
    await reloadAll()
  }

  async function unfoldFold(foldId: string) {
    if (!ctxId) return
    await api.unfold(ctxId, foldId)
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

  return (
    <div className="wrap">
      <div className="col">
        <div className="row">
          <button onClick={async () => {
            const t = await api.createThread('New Thread')
            const ts = await api.threads()
            setThreads(ts)
            setThreadId(t.id)
          }}>New Thread</button>

          <select value={threadId || ''} onChange={(e) => setThreadId(e.target.value)} style={{ flex: 1, padding: 6, borderRadius: 10, border: '1px solid #e5e7eb' }}>
            {threads.map(t => (
              <option key={t.id} value={t.id}>{t.title} ({t.id.slice(0,6)})</option>
            ))}
          </select>
        </div>

        <div className="row">
          <select value={ctxId || ''} onChange={(e) => setCtxId(e.target.value)} style={{ flex: 1, padding: 6, borderRadius: 10, border: '1px solid #e5e7eb' }}>
            {ctxSets.map(c => (
              <option key={c.id} value={c.id}>{c.name} ({c.id.slice(0,6)})</option>
            ))}
          </select>
          <button onClick={async () => {
            if (!threadId) return
            const name = prompt('ContextSet name?', 'alt')
            if (!name) return
            await api.createCtx(threadId, name)
            await loadCtxSets(threadId)
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

        <Timeline nodes={nodes} activeIds={activeIds} onToggle={toggleActive} />
      </div>

      <div className="col">
        <GraphPanel
          nodes={nodes}
          edges={edges}
          activeNodeIds={activeIds}
          onSelectionChange={handleSelectionChange}
          onCreateEdge={handleCreateEdge}
          onDeleteEdges={handleDeleteEdges}
        />
        <div className="muted" style={{ marginTop: 8 }}>
          그래프에서 드래그 멀티 선택으로 Fold 대상 지정, 핸들 드래그로 Edge 추가/삭제
        </div>
      </div>

      <div className="col">
        <ActiveContext
          activeIds={activeIds}
          nodesById={nodesById}
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
