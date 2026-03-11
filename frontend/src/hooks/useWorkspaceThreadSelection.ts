import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'

const WORKSPACE_STORAGE_KEY = 'goc:selected-workspace:v1'

export type WorkspaceGroup = {
  key: string
  label: string
  chatId: number | string | null
  threadIds: string[]
}

function readStoredWorkspaceKey(): string {
  if (typeof window === 'undefined') return ''
  try {
    return (window.localStorage.getItem(WORKSPACE_STORAGE_KEY) || '').trim()
  } catch {
    return ''
  }
}

function parseThreadMetaJson(thread: any): Record<string, any> {
  const raw = thread?.meta_json
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    return raw as Record<string, any>
  }
  if (typeof raw === 'string' && raw.trim()) {
    try {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed as Record<string, any>
      }
    } catch {
      // ignore malformed meta_json
    }
  }
  return {}
}

export function buildWorkspaceGroup(thread: any): WorkspaceGroup {
  const meta = parseThreadMetaJson(thread)
  const telegram = meta.telegram && typeof meta.telegram === 'object' ? meta.telegram : null
  const chatId = telegram ? (telegram.chat_id ?? null) : null
  if (chatId !== null && chatId !== undefined && String(chatId).trim() !== '') {
    const title = typeof telegram?.title === 'string' ? telegram.title.trim() : ''
    return {
      key: `telegram:${String(chatId)}`,
      label: title ? `${title} (${chatId})` : `Chat ${chatId}`,
      chatId,
      threadIds: [thread.id],
    }
  }
  return {
    key: 'ungrouped',
    label: 'Ungrouped',
    chatId: null,
    threadIds: [thread.id],
  }
}

function readDeepLinkSelection(): { threadId: string | null; ctxId: string | null } {
  if (typeof window === 'undefined') {
    return { threadId: null, ctxId: null }
  }
  const params = new URLSearchParams(window.location.search)
  const threadId = (params.get('thread') || '').trim() || null
  const ctxId = (params.get('ctx') || '').trim() || null
  return { threadId, ctxId }
}

export function useWorkspaceThreadSelection() {
  const [threads, setThreads] = useState<any[]>([])
  const [workspaceKey, setWorkspaceKey] = useState<string>(() => readStoredWorkspaceKey())
  const [threadId, setThreadId] = useState<string | null>(null)
  const [threadResolutionNotice, setThreadResolutionNotice] = useState<string>('')

  const initialDeepLink = useMemo(() => readDeepLinkSelection(), [])

  const workspaceGroups = useMemo<WorkspaceGroup[]>(() => {
    const byKey = new Map<string, WorkspaceGroup>()
    for (const thread of threads) {
      const group = buildWorkspaceGroup(thread)
      const existing = byKey.get(group.key)
      if (!existing) {
        byKey.set(group.key, group)
        continue
      }
      existing.threadIds.push(thread.id)
      if (existing.label === `Chat ${String(existing.chatId)}` && group.label) {
        existing.label = group.label
      }
    }
    const groups = Array.from(byKey.values())
    groups.sort((a, b) => {
      if (a.key === 'ungrouped') return 1
      if (b.key === 'ungrouped') return -1
      return a.label.localeCompare(b.label)
    })
    return groups
  }, [threads])

  const visibleThreads = useMemo(() => {
    if (!workspaceKey) return threads
    const group = workspaceGroups.find((item) => item.key === workspaceKey)
    if (!group) return threads
    const idSet = new Set(group.threadIds)
    return threads.filter((thread) => idSet.has(thread.id))
  }, [threads, workspaceGroups, workspaceKey])

  useEffect(() => {
    if (workspaceGroups.length === 0) return
    const exists = workspaceKey && workspaceGroups.some((group) => group.key === workspaceKey)
    if (exists) return
    if (threadId) {
      const currentThread = threads.find((thread) => thread.id === threadId)
      if (currentThread) {
        setWorkspaceKey(buildWorkspaceGroup(currentThread).key)
        return
      }
    }
    setWorkspaceKey(workspaceGroups[0].key)
  }, [workspaceGroups, workspaceKey, threadId, threads])

  useEffect(() => {
    try {
      if (workspaceKey) {
        window.localStorage.setItem(WORKSPACE_STORAGE_KEY, workspaceKey)
      } else {
        window.localStorage.removeItem(WORKSPACE_STORAGE_KEY)
      }
    } catch {
      // ignore localStorage errors
    }
  }, [workspaceKey])

  const loadThreads = useCallback(async (preferredThreadId?: string | null): Promise<string | null> => {
    const requestedThreadId = (preferredThreadId || '').trim()
    let ts = await api.threads()
    setThreads(ts)

    if (requestedThreadId) {
      if (ts.some((t) => t.id === requestedThreadId)) {
        setThreadResolutionNotice('')
        return requestedThreadId
      }

      try {
        const directThread = await api.thread(requestedThreadId)
        if (directThread && directThread.id === requestedThreadId) {
          if (!ts.some((t) => t.id === requestedThreadId)) {
            ts = [directThread, ...ts]
            setThreads(ts)
          }
          setThreadResolutionNotice('')
          return requestedThreadId
        }
      } catch {
        // handled below with explicit non-fallback notice
      }

      setThreadResolutionNotice(
        `Requested thread (${requestedThreadId}) was not found or is unavailable. No fallback thread was auto-selected.`,
      )
      return null
    }

    let tid = ts[0]?.id
    if (threadId && ts.some((t) => t.id === threadId)) {
      tid = threadId
    } else if (workspaceKey) {
      const inWorkspace = ts.find((t) => buildWorkspaceGroup(t).key === workspaceKey)
      if (inWorkspace) tid = inWorkspace.id
    }
    if (!tid) {
      const t = await api.createThread('Demo Thread')
      tid = t.id
      const refreshed = await api.threads()
      setThreads(refreshed)
    }

    setThreadResolutionNotice('')
    return tid
  }, [threadId, workspaceKey])

  const setWorkspaceKeyForThread = useCallback((targetThreadId: string) => {
    const nextThread = threads.find((thread) => thread.id === targetThreadId)
    if (!nextThread) return
    setWorkspaceKey(buildWorkspaceGroup(nextThread).key)
  }, [threads])

  return {
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
  }
}
