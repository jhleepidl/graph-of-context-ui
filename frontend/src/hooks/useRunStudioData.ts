import { useCallback, useMemo, useState } from 'react'
import { api } from '../api'
import {
  type RunStudioAgentTeam,
  type RunStudioContextPacks,
  type RunStudioContextDecisions,
  type RunStudioEvidence,
  type RunStudioSkillUsage,
  type RunStudioSummary,
  type RunStudioMemoryGraph,
} from '../components/run_studio/types'

type RefreshOptions = {
  silent?: boolean
  includeLoadedDetails?: boolean
}

type DetailKey = 'agentTeam' | 'contextDecisions' | 'evidence' | 'contextPacks' | 'skillUsage' | 'memoryGraph'

type DetailState = Record<DetailKey, boolean>

type LoadDetailOptions = {
  silent?: boolean
}

const EMPTY_DETAIL_STATE: DetailState = {
  agentTeam: false,
  contextDecisions: false,
  evidence: false,
  contextPacks: false,
  skillUsage: false,
  memoryGraph: false,
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
      // ignore malformed JSON
    }
    return raw
  }
  return String(error || 'Unknown error')
}

export function useRunStudioData() {
  const [summary, setSummary] = useState<RunStudioSummary | null>(null)
  const [agentTeam, setAgentTeam] = useState<RunStudioAgentTeam | null>(null)
  const [contextDecisions, setContextDecisions] = useState<RunStudioContextDecisions | null>(null)
  const [evidence, setEvidence] = useState<RunStudioEvidence | null>(null)
  const [contextPacks, setContextPacks] = useState<RunStudioContextPacks | null>(null)
  const [skillUsage, setSkillUsage] = useState<RunStudioSkillUsage | null>(null)
  const [memoryGraph, setMemoryGraph] = useState<RunStudioMemoryGraph | null>(null)
  const [detailLoaded, setDetailLoaded] = useState<DetailState>(EMPTY_DETAIL_STATE)
  const [detailLoading, setDetailLoading] = useState<DetailState>(EMPTY_DETAIL_STATE)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const markDetailLoading = useCallback((key: DetailKey, value: boolean) => {
    setDetailLoading((prev) => (prev[key] === value ? prev : { ...prev, [key]: value }))
  }, [])

  const markDetailLoaded = useCallback((key: DetailKey, value: boolean) => {
    setDetailLoaded((prev) => (prev[key] === value ? prev : { ...prev, [key]: value }))
  }, [])

  const applySummary = useCallback((nextSummary: RunStudioSummary | null, loaded: DetailState) => {
    setSummary(nextSummary)

    const summaryAgentTeam = nextSummary?.agent_team || null
    if (summaryAgentTeam) {
      setAgentTeam(summaryAgentTeam)
      if (!loaded.agentTeam) {
        markDetailLoaded('agentTeam', true)
      }
    }
  }, [markDetailLoaded])

  const clear = useCallback(() => {
    setSummary(null)
    setAgentTeam(null)
    setContextDecisions(null)
    setEvidence(null)
    setContextPacks(null)
    setSkillUsage(null)
    setMemoryGraph(null)
    setDetailLoaded(EMPTY_DETAIL_STATE)
    setDetailLoading(EMPTY_DETAIL_STATE)
    setError('')
    setLoading(false)
  }, [])

  const loadAgentTeam = useCallback(async (threadId?: string | null, options?: LoadDetailOptions) => {
    const tId = (threadId || '').trim()
    if (!tId) return null
    markDetailLoading('agentTeam', true)
    if (!options?.silent) setError('')
    try {
      const nextTeam = await api.runStudioAgentTeam(tId)
      setAgentTeam(nextTeam)
      markDetailLoaded('agentTeam', true)
      return nextTeam
    } catch (detailError) {
      if (!options?.silent) setError(toErrorMessage(detailError))
      return null
    } finally {
      markDetailLoading('agentTeam', false)
    }
  }, [markDetailLoaded, markDetailLoading])

  const loadContextDecisions = useCallback(async (threadId?: string | null, contextSetId?: string | null, options?: LoadDetailOptions) => {
    const tId = (threadId || '').trim()
    if (!tId) return null
    const cId = (contextSetId || '').trim()
    markDetailLoading('contextDecisions', true)
    if (!options?.silent) setError('')
    try {
      const nextDecisions = await api.runStudioContextDecisions(tId, cId || undefined)
      setContextDecisions(nextDecisions)
      markDetailLoaded('contextDecisions', true)
      return nextDecisions
    } catch (detailError) {
      if (!options?.silent) setError(toErrorMessage(detailError))
      return null
    } finally {
      markDetailLoading('contextDecisions', false)
    }
  }, [markDetailLoaded, markDetailLoading])

  const loadEvidence = useCallback(async (threadId?: string | null, contextSetId?: string | null, options?: LoadDetailOptions) => {
    const tId = (threadId || '').trim()
    if (!tId) return null
    const cId = (contextSetId || '').trim()
    markDetailLoading('evidence', true)
    if (!options?.silent) setError('')
    try {
      const nextEvidence = await api.runStudioEvidence(tId, cId || undefined)
      setEvidence(nextEvidence)
      markDetailLoaded('evidence', true)
      return nextEvidence
    } catch (detailError) {
      if (!options?.silent) setError(toErrorMessage(detailError))
      return null
    } finally {
      markDetailLoading('evidence', false)
    }
  }, [markDetailLoaded, markDetailLoading])

  const loadContextPacks = useCallback(async (threadId?: string | null, runId?: string | null, options?: LoadDetailOptions) => {
    const tId = (threadId || '').trim()
    if (!tId) return null
    const rId = (runId || '').trim()
    markDetailLoading('contextPacks', true)
    if (!options?.silent) setError('')
    try {
      const nextContextPacks = await api.runStudioContextPacks(tId, rId || undefined)
      setContextPacks(nextContextPacks)
      markDetailLoaded('contextPacks', true)
      return nextContextPacks
    } catch (detailError) {
      if (!options?.silent) setError(toErrorMessage(detailError))
      return null
    } finally {
      markDetailLoading('contextPacks', false)
    }
  }, [markDetailLoaded, markDetailLoading])

  const loadMemoryGraph = useCallback(async (threadId?: string | null, runId?: string | null, options?: LoadDetailOptions) => {
    const tId = (threadId || '').trim()
    if (!tId) return null
    const rId = (runId || '').trim()
    markDetailLoading('memoryGraph', true)
    if (!options?.silent) setError('')
    try {
      const nextMemoryGraph = await api.runStudioMemoryGraph(tId, rId || undefined)
      setMemoryGraph(nextMemoryGraph)
      markDetailLoaded('memoryGraph', true)
      return nextMemoryGraph
    } catch (detailError) {
      if (!options?.silent) setError(toErrorMessage(detailError))
      return null
    } finally {
      markDetailLoading('memoryGraph', false)
    }
  }, [markDetailLoaded, markDetailLoading])

  const loadSkillUsage = useCallback(async (threadId?: string | null, runId?: string | null, options?: LoadDetailOptions) => {
    const tId = (threadId || '').trim()
    if (!tId) return null
    const rId = (runId || '').trim()
    markDetailLoading('skillUsage', true)
    if (!options?.silent) setError('')
    try {
      const nextSkillUsage = await api.runStudioSkillUsage(tId, rId || undefined)
      setSkillUsage(nextSkillUsage)
      markDetailLoaded('skillUsage', true)
      return nextSkillUsage
    } catch (detailError) {
      if (!options?.silent) setError(toErrorMessage(detailError))
      return null
    } finally {
      markDetailLoading('skillUsage', false)
    }
  }, [markDetailLoaded, markDetailLoading])

  const refresh = useCallback(async (threadId?: string | null, contextSetId?: string | null, options?: RefreshOptions) => {
    const tId = (threadId || '').trim()
    const cId = (contextSetId || '').trim()
    if (!tId) {
      clear()
      return
    }

    const silent = Boolean(options?.silent)
    const includeLoadedDetails = Boolean(options?.includeLoadedDetails)

    if (!silent) setLoading(true)
    setError('')

    try {
      const nextSummary = await api.runStudioSummary(tId, cId || undefined)
      const loadedSnapshot = detailLoaded
      applySummary(nextSummary, loadedSnapshot)

      if (includeLoadedDetails) {
        const runId = String(nextSummary?.current_run_skills?.run_id || '').trim() || undefined
        const tasks: Promise<unknown>[] = []
        if (loadedSnapshot.contextDecisions) {
          tasks.push(loadContextDecisions(tId, cId || undefined, { silent: true }))
        }
        if (loadedSnapshot.evidence) {
          tasks.push(loadEvidence(tId, cId || undefined, { silent: true }))
        }
        if (loadedSnapshot.contextPacks) {
          tasks.push(loadContextPacks(tId, runId, { silent: true }))
        }
        if (loadedSnapshot.skillUsage) {
          tasks.push(loadSkillUsage(tId, runId, { silent: true }))
        }
        if (loadedSnapshot.memoryGraph) {
          tasks.push(loadMemoryGraph(tId, runId, { silent: true }))
        }
        if (loadedSnapshot.agentTeam && !nextSummary?.agent_team) {
          tasks.push(loadAgentTeam(tId, { silent: true }))
        }
        if (tasks.length > 0) {
          await Promise.all(tasks)
        }
      }
    } catch (refreshError) {
      setError(toErrorMessage(refreshError))
    } finally {
      if (!silent) setLoading(false)
    }
  }, [applySummary, clear, detailLoaded, loadAgentTeam, loadContextDecisions, loadContextPacks, loadEvidence, loadSkillUsage, loadMemoryGraph])

  const derivedRunId = useMemo(() => {
    return String(summary?.current_run_skills?.run_id || '').trim() || null
  }, [summary])

  return {
    summary,
    agentTeam,
    contextDecisions,
    evidence,
    contextPacks,
    skillUsage,
    memoryGraph,
    detailLoaded,
    detailLoading,
    derivedRunId,
    loading,
    error,
    refresh,
    clear,
    loadAgentTeam,
    loadContextDecisions,
    loadEvidence,
    loadContextPacks,
    loadSkillUsage,
    loadMemoryGraph,
  }
}
