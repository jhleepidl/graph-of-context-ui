import { useCallback, useState } from 'react'
import { api } from '../api'
import {
  type RunStudioAgentTeam,
  type RunStudioContextDecisions,
  type RunStudioEvidence,
  type RunStudioSummary,
} from '../components/run_studio/types'

type RefreshOptions = {
  silent?: boolean
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
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const clear = useCallback(() => {
    setSummary(null)
    setAgentTeam(null)
    setContextDecisions(null)
    setEvidence(null)
    setError('')
    setLoading(false)
  }, [])

  const refresh = useCallback(async (threadId?: string | null, contextSetId?: string | null, options?: RefreshOptions) => {
    const tId = (threadId || '').trim()
    const cId = (contextSetId || '').trim()
    if (!tId) {
      clear()
      return
    }

    const silent = Boolean(options?.silent)
    if (!silent) setLoading(true)
    setError('')
    try {
      const [nextSummary, nextTeam, nextDecisions, nextEvidence] = await Promise.all([
        api.runStudioSummary(tId, cId || undefined),
        api.runStudioAgentTeam(tId),
        api.runStudioContextDecisions(tId, cId || undefined),
        api.runStudioEvidence(tId, cId || undefined),
      ])
      setSummary(nextSummary)
      setAgentTeam(nextTeam)
      setContextDecisions(nextDecisions)
      setEvidence(nextEvidence)
    } catch (refreshError) {
      setError(toErrorMessage(refreshError))
    } finally {
      if (!silent) setLoading(false)
    }
  }, [clear])

  return {
    summary,
    agentTeam,
    contextDecisions,
    evidence,
    loading,
    error,
    refresh,
    clear,
  }
}
