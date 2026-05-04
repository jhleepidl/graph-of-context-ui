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
  type RunStudioMemoryTopology,
  type RunStudioMemoryDemand,
  type RunStudioRunBundle,
  type RunStudioCrossReferences,
  type RunStudioTraceScope,
  type RunStudioAuditTimeline,
  type RunStudioProjectionRetrieval,
  type RunStudioGraphCompression,
  type RunStudioHarnessSpec,
  type RunStudioHarnessSummary,
  type TeamSelectionDataset,
} from '../components/run_studio/types'

type RefreshOptions = {
  silent?: boolean
  includeLoadedDetails?: boolean
}

type DetailKey = 'agentTeam' | 'contextDecisions' | 'evidence' | 'contextPacks' | 'skillUsage' | 'memoryGraph' | 'memoryTopology' | 'memoryDemand' | 'traceScope' | 'teamSelection'

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
  memoryTopology: false,
  memoryDemand: false,
  traceScope: false,
  teamSelection: false,
}

function cleanText(value?: string | null): string {
  return String(value || '').trim()
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    const raw = cleanText(error.message)
    if (!raw) return 'Unknown error'
    try {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed === 'object' && typeof (parsed as { detail?: unknown }).detail === 'string') {
        return String((parsed as { detail: string }).detail)
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
  const [memoryTopology, setMemoryTopology] = useState<RunStudioMemoryTopology | null>(null)
  const [memoryDemand, setMemoryDemand] = useState<RunStudioMemoryDemand | null>(null)
  const [traceScope, setTraceScope] = useState<RunStudioTraceScope | null>(null)
  const [crossReferences, setCrossReferences] = useState<RunStudioCrossReferences | null>(null)
  const [auditTimeline, setAuditTimeline] = useState<RunStudioAuditTimeline | null>(null)
  const [projectionRetrieval, setProjectionRetrieval] = useState<RunStudioProjectionRetrieval | null>(null)
  const [graphCompression, setGraphCompression] = useState<RunStudioGraphCompression | null>(null)
  const [harnessSpec, setHarnessSpec] = useState<RunStudioHarnessSpec | null>(null)
  const [harnessSummary, setHarnessSummary] = useState<RunStudioHarnessSummary | null>(null)
  const [teamSelection, setTeamSelection] = useState<TeamSelectionDataset | null>(null)
  const [detailLoaded, setDetailLoaded] = useState<DetailState>(EMPTY_DETAIL_STATE)
  const [detailLoading, setDetailLoading] = useState<DetailState>(EMPTY_DETAIL_STATE)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [focusedRunId, setFocusedRunId] = useState<string | null>(null)
  const [focusedEventId, setFocusedEventId] = useState<string | null>(null)
  const [focusedEventLabel, setFocusedEventLabel] = useState<string>('')

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
      if (!loaded.agentTeam) markDetailLoaded('agentTeam', true)
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
    setMemoryTopology(null)
    setMemoryDemand(null)
    setTraceScope(null)
    setCrossReferences(null)
    setAuditTimeline(null)
    setProjectionRetrieval(null)
    setGraphCompression(null)
    setHarnessSpec(null)
    setHarnessSummary(null)
    setTeamSelection(null)
    setDetailLoaded(EMPTY_DETAIL_STATE)
    setDetailLoading(EMPTY_DETAIL_STATE)
    setError('')
    setLoading(false)
    setFocusedRunId(null)
    setFocusedEventId(null)
    setFocusedEventLabel('')
  }, [])

  const runDetailRequest = useCallback(async <T,>(
    key: DetailKey,
    request: () => Promise<T>,
    setter: (value: T) => void,
    options?: LoadDetailOptions,
  ): Promise<T | null> => {
    markDetailLoading(key, true)
    if (!options?.silent) setError('')
    try {
      const value = await request()
      setter(value)
      markDetailLoaded(key, true)
      return value
    } catch (detailError) {
      if (!options?.silent) setError(toErrorMessage(detailError))
      return null
    } finally {
      markDetailLoading(key, false)
    }
  }, [markDetailLoaded, markDetailLoading])

  const loadAgentTeam = useCallback(async (threadId?: string | null, options?: LoadDetailOptions) => {
    const tId = cleanText(threadId)
    if (!tId) return null
    return runDetailRequest('agentTeam', () => api.runStudioAgentTeam(tId), setAgentTeam, options)
  }, [runDetailRequest])

  const loadContextDecisions = useCallback(async (threadId?: string | null, contextSetId?: string | null, options?: LoadDetailOptions) => {
    const tId = cleanText(threadId)
    if (!tId) return null
    const cId = cleanText(contextSetId) || undefined
    return runDetailRequest('contextDecisions', () => api.runStudioContextDecisions(tId, cId), setContextDecisions, options)
  }, [runDetailRequest])

  const loadEvidence = useCallback(async (threadId?: string | null, contextSetId?: string | null, runId?: string | null, options?: LoadDetailOptions) => {
    const tId = cleanText(threadId)
    if (!tId) return null
    const cId = cleanText(contextSetId) || undefined
    const rId = cleanText(runId) || undefined
    return runDetailRequest('evidence', () => api.runStudioEvidence(tId, cId, rId), setEvidence, options)
  }, [runDetailRequest])

  const loadContextPacks = useCallback(async (threadId?: string | null, runId?: string | null, options?: LoadDetailOptions) => {
    const tId = cleanText(threadId)
    if (!tId) return null
    const rId = cleanText(runId) || undefined
    return runDetailRequest('contextPacks', () => api.runStudioContextPacks(tId, rId), setContextPacks, options)
  }, [runDetailRequest])

  const loadMemoryGraph = useCallback(async (threadId?: string | null, runId?: string | null, options?: LoadDetailOptions) => {
    const tId = cleanText(threadId)
    if (!tId) return null
    const rId = cleanText(runId) || undefined
    return runDetailRequest('memoryGraph', () => api.runStudioMemoryGraph(tId, rId), setMemoryGraph, options)
  }, [runDetailRequest])

  const loadMemoryTopology = useCallback(async (threadId?: string | null, runId?: string | null, options?: LoadDetailOptions) => {
    const tId = cleanText(threadId)
    if (!tId) return null
    const rId = cleanText(runId) || undefined
    return runDetailRequest('memoryTopology', () => api.runStudioMemoryTopology(tId, rId), setMemoryTopology, options)
  }, [runDetailRequest])

  const loadMemoryDemand = useCallback(async (threadId?: string | null, runId?: string | null, options?: LoadDetailOptions) => {
    const tId = cleanText(threadId)
    if (!tId) return null
    const rId = cleanText(runId) || undefined
    return runDetailRequest('memoryDemand', () => api.runStudioMemoryDemand(tId, rId), setMemoryDemand, options)
  }, [runDetailRequest])

  const loadTraceScope = useCallback(async (threadId?: string | null, runId?: string | null, options?: LoadDetailOptions) => {
    const tId = cleanText(threadId)
    if (!tId) return null
    const rId = cleanText(runId) || undefined
    return runDetailRequest('traceScope', () => api.runStudioTraceScope(tId, rId), setTraceScope, options)
  }, [runDetailRequest])

  const loadTeamSelection = useCallback(async (threadId?: string | null, options?: LoadDetailOptions) => {
    const tId = cleanText(threadId)
    if (!tId) return null
    return runDetailRequest('teamSelection', () => api.exportTeamSelectionDataset(tId, 20, 'json'), setTeamSelection, options)
  }, [runDetailRequest])

  const loadSkillUsage = useCallback(async (threadId?: string | null, runId?: string | null, options?: LoadDetailOptions) => {
    const tId = cleanText(threadId)
    if (!tId) return null
    const rId = cleanText(runId) || undefined
    return runDetailRequest('skillUsage', () => api.runStudioSkillUsage(tId, rId), setSkillUsage, options)
  }, [runDetailRequest])


  const applyRunBundle = useCallback((bundle: RunStudioRunBundle | null) => {
    if (!bundle) return bundle
    if (bundle.evidence) {
      setEvidence(bundle.evidence)
      markDetailLoaded('evidence', true)
    }
    if (bundle.context_packs) {
      setContextPacks(bundle.context_packs)
      markDetailLoaded('contextPacks', true)
    }
    if (bundle.skill_usage) {
      setSkillUsage(bundle.skill_usage)
      markDetailLoaded('skillUsage', true)
    }
    if (bundle.memory_graph) {
      setMemoryGraph(bundle.memory_graph)
      markDetailLoaded('memoryGraph', true)
    }
    if (bundle.memory_topology) {
      setMemoryTopology(bundle.memory_topology)
      markDetailLoaded('memoryTopology', true)
    }
    if (bundle.memory_demand) {
      setMemoryDemand(bundle.memory_demand)
      markDetailLoaded('memoryDemand', true)
    }
    if (bundle.trace_scope) {
      setTraceScope(bundle.trace_scope)
      markDetailLoaded('traceScope', true)
    }
    if (bundle.cross_references) {
      setCrossReferences(bundle.cross_references)
    }
    if (bundle.projection_retrieval) {
      setProjectionRetrieval(bundle.projection_retrieval)
    }
    if (bundle.audit_timeline) {
      setAuditTimeline(bundle.audit_timeline)
    }
    if (bundle.graph_native_compression) {
      setGraphCompression(bundle.graph_native_compression)
    }
    if (bundle.harness_spec) {
      setHarnessSpec(bundle.harness_spec)
    }
    if (bundle.harness_summary) {
      setHarnessSummary(bundle.harness_summary)
    }
    return bundle
  }, [markDetailLoaded])

  const loadRunBundle = useCallback(async (threadId?: string | null, contextSetId?: string | null, runId?: string | null, options?: LoadDetailOptions) => {
    const tId = cleanText(threadId)
    if (!tId) return null
    const cId = cleanText(contextSetId) || undefined
    const rId = cleanText(runId) || undefined
    const bundleKeys: DetailKey[] = ['evidence', 'contextPacks', 'skillUsage', 'memoryGraph', 'memoryTopology', 'memoryDemand', 'traceScope']
    bundleKeys.forEach((key) => markDetailLoading(key, true))
    if (!options?.silent) setError('')
    try {
      const bundle = await api.runStudioRunBundle(tId, cId, rId)
      return applyRunBundle(bundle)
    } catch (detailError) {
      if (!options?.silent) setError(toErrorMessage(detailError))
      return null
    } finally {
      bundleKeys.forEach((key) => markDetailLoading(key, false))
    }
  }, [applyRunBundle, markDetailLoading])

  const focusRunDrilldown = useCallback(async (
    threadId?: string | null,
    contextSetId?: string | null,
    runId?: string | null,
    eventMeta?: { eventId?: string | null; label?: string | null },
    options?: LoadDetailOptions,
  ) => {
    const tId = cleanText(threadId)
    const cId = cleanText(contextSetId) || undefined
    const rId = cleanText(runId)
    if (!tId || !rId) return null

    const sameFocusedRun = cleanText(focusedRunId) === rId
    const detailBundleAlreadyLoaded = detailLoaded.evidence && detailLoaded.contextPacks && detailLoaded.skillUsage && detailLoaded.memoryGraph && detailLoaded.memoryTopology && detailLoaded.memoryDemand && detailLoaded.traceScope
    setFocusedRunId(rId)
    setFocusedEventId(cleanText(eventMeta?.eventId) || null)
    setFocusedEventLabel(cleanText(eventMeta?.label))
    if (sameFocusedRun && detailBundleAlreadyLoaded) {
      return {
        evidence,
        contextPacks,
        skillUsage,
        memoryGraph,
        memory_topology: memoryTopology,
        memory_demand: memoryDemand,
        traceScope,
        cross_references: crossReferences,
        projection_retrieval: projectionRetrieval,
        audit_timeline: auditTimeline,
        graph_native_compression: graphCompression,
        harness_spec: harnessSpec,
        harness_summary: harnessSummary,
      }
    }

    return await loadRunBundle(tId, cId, rId, options)
  }, [auditTimeline, contextPacks, detailLoaded.contextPacks, detailLoaded.evidence, detailLoaded.memoryGraph, detailLoaded.memoryTopology, detailLoaded.memoryDemand, detailLoaded.skillUsage, detailLoaded.traceScope, evidence, focusedRunId, loadRunBundle, memoryGraph, memoryTopology, memoryDemand, skillUsage, traceScope, crossReferences, projectionRetrieval, graphCompression, harnessSpec, harnessSummary])

  const clearRunDrilldown = useCallback(async (threadId?: string | null, contextSetId?: string | null, options?: LoadDetailOptions) => {
    const hadFocusedRun = !!cleanText(focusedRunId)
    setFocusedRunId(null)
    setFocusedEventId(null)
    setFocusedEventLabel('')
    const tId = cleanText(threadId)
    if (!tId || !hadFocusedRun) return null
    const cId = cleanText(contextSetId) || undefined
    const fallbackRunId = cleanText(summary?.current_run_skills?.run_id) || undefined
    const silent = options?.silent ?? true
    const shouldReloadBundle = detailLoaded.evidence || detailLoaded.contextPacks || detailLoaded.skillUsage || detailLoaded.memoryGraph || detailLoaded.memoryTopology || detailLoaded.memoryDemand || detailLoaded.traceScope
    if (shouldReloadBundle) await loadRunBundle(tId, cId, fallbackRunId, { silent })
    return fallbackRunId || null
  }, [detailLoaded, focusedRunId, loadRunBundle, summary])

  const refresh = useCallback(async (threadId?: string | null, contextSetId?: string | null, options?: RefreshOptions) => {
    const tId = cleanText(threadId)
    const cId = cleanText(contextSetId) || undefined
    if (!tId) {
      clear()
      return
    }

    const silent = Boolean(options?.silent)
    const includeLoadedDetails = Boolean(options?.includeLoadedDetails)

    if (!silent) setLoading(true)
    setError('')

    try {
      const nextSummary = await api.runStudioSummary(tId, cId)
      const loadedSnapshot = detailLoaded
      applySummary(nextSummary, loadedSnapshot)

      if (includeLoadedDetails) {
        const summaryRunId = cleanText(nextSummary?.current_run_skills?.run_id) || undefined
        const effectiveRunId = cleanText(focusedRunId || summaryRunId) || undefined
        const tasks: Promise<unknown>[] = []
        if (loadedSnapshot.contextDecisions) tasks.push(loadContextDecisions(tId, cId, { silent: true }))
        if (loadedSnapshot.evidence || loadedSnapshot.contextPacks || loadedSnapshot.skillUsage || loadedSnapshot.memoryGraph || loadedSnapshot.memoryTopology || loadedSnapshot.memoryDemand || loadedSnapshot.traceScope) {
          tasks.push(loadRunBundle(tId, cId, effectiveRunId, { silent: true }))
        }
        if (loadedSnapshot.teamSelection) tasks.push(loadTeamSelection(tId, { silent: true }))
        if (loadedSnapshot.agentTeam && !nextSummary?.agent_team) tasks.push(loadAgentTeam(tId, { silent: true }))
        if (tasks.length > 0) await Promise.all(tasks)
      }
    } catch (refreshError) {
      setError(toErrorMessage(refreshError))
    } finally {
      if (!silent) setLoading(false)
    }
  }, [applySummary, clear, detailLoaded, focusedRunId, loadAgentTeam, loadContextDecisions, loadRunBundle, loadTeamSelection])

  const derivedRunId = useMemo(() => cleanText(summary?.current_run_skills?.run_id) || null, [summary])

  return {
    summary,
    agentTeam,
    contextDecisions,
    evidence,
    contextPacks,
    skillUsage,
    memoryGraph,
    memoryTopology,
    memoryDemand,
    traceScope,
    crossReferences,
    projectionRetrieval,
    graphCompression,
    harnessSpec,
    harnessSummary,
    auditTimeline,
    teamSelection,
    detailLoaded,
    detailLoading,
    derivedRunId,
    focusedRunId,
    focusedEventId,
    focusedEventLabel,
    loading,
    error,
    refresh,
    clear,
    loadAgentTeam,
    loadContextDecisions,
    loadEvidence,
    loadContextPacks,
    loadSkillUsage,
    loadRunBundle,
    loadMemoryGraph,
    loadMemoryTopology,
    loadMemoryDemand,
    loadTraceScope,
    loadTeamSelection,
    focusRunDrilldown,
    clearRunDrilldown,
  }
}
