import { type Dispatch, type SetStateAction, useCallback } from 'react'
import { api } from '../api'
import { type WorkspaceMainTab } from './useWorkspaceTabs'

type Args = {
  nodesById: Map<string, any>
  setWorkspaceMainTab: (tab: WorkspaceMainTab) => void
  setSelectedIds: Dispatch<SetStateAction<string[]>>
  setDetailNodeId: Dispatch<SetStateAction<string | null>>
  activateNodeIds: (nodeIds: string[]) => Promise<void>
  reloadAll: (nextThreadId?: string, nextCtxId?: string) => Promise<void>
  threadId: string | null
  ctxId: string | null
}

export function useRunStudioActions({
  nodesById,
  setWorkspaceMainTab,
  setSelectedIds,
  setDetailNodeId,
  activateNodeIds,
  reloadAll,
  threadId,
  ctxId,
}: Args) {
  const normalizeGraphTargetIds = useCallback((rawIds: string[]) => {
    return rawIds
      .map((id) => String(id || '').trim())
      .filter((id, index, arr) => id && arr.indexOf(id) === index)
      .filter((id) => nodesById.has(id))
  }, [nodesById])

  const focusNodesInGraph = useCallback((rawIds: string[]) => {
    const ids = normalizeGraphTargetIds(rawIds)
    if (ids.length === 0) return
    setWorkspaceMainTab('graph')
    setSelectedIds(ids)
  }, [normalizeGraphTargetIds, setSelectedIds, setWorkspaceMainTab])

  const openNodesInGraph = useCallback((rawIds: string[]) => {
    const ids = normalizeGraphTargetIds(rawIds)
    if (ids.length === 0) return
    setWorkspaceMainTab('graph')
    setSelectedIds(ids)
    setDetailNodeId(ids[0])
  }, [normalizeGraphTargetIds, setDetailNodeId, setSelectedIds, setWorkspaceMainTab])

  const focusNodeInGraph = useCallback((nodeId: string) => {
    const clean = String(nodeId || '').trim()
    if (!clean) return
    focusNodesInGraph([clean])
  }, [focusNodesInGraph])

  const openNodeInGraph = useCallback((nodeId: string) => {
    const clean = String(nodeId || '').trim()
    if (!clean) return
    openNodesInGraph([clean])
  }, [openNodesInGraph])

  const addNodeToActiveFromStudio = useCallback(async (nodeId: string) => {
    const clean = String(nodeId || '').trim()
    if (!clean) return
    await activateNodeIds([clean])
  }, [activateNodeIds])

  const pinNodeFromStudio = useCallback(async (nodeId: string, level: 'required' | 'preferred') => {
    const clean = String(nodeId || '').trim()
    if (!clean) return
    try {
      await api.pinNode(clean, level)
      await reloadAll(threadId || undefined, ctxId || undefined)
    } catch (error) {
      console.error('failed to pin node from run studio', error)
    }
  }, [ctxId, reloadAll, threadId])

  return {
    focusNodesInGraph,
    openNodesInGraph,
    focusNodeInGraph,
    openNodeInGraph,
    addNodeToActiveFromStudio,
    pinNodeFromStudio,
  }
}
