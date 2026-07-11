import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../../api'

type EvalRun = {
  evaluation_id?: string
  suite?: string
  status?: string
  total_run_count?: number
  passed_run_count?: number
  failed_run_count?: number
  recommendation_variant_id?: string | null
  recommendation_runtime_signature?: string | null
  finished_at?: string | null
}

type Variant = {
  runtime_signature?: string
  harness_variant_id?: string
  provider?: string | null
  model?: string | null
  reasoning_effort?: string | null
  latest_cli_version?: string | null
  evaluation_count?: number
  run_count?: number
  success_rate?: number
  average_score?: number
  average_duration_ms?: number
}

export default function HarnessEvaluationPanel() {
  const [runs, setRuns] = useState<EvalRun[]>([])
  const [variants, setVariants] = useState<Variant[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const [runData, variantData] = await Promise.all([
        api.harnessEvaluationRuns({ limit: 8 }),
        api.harnessEvaluationVariants({ limit: 500 }),
      ])
      setRuns(Array.isArray(runData?.items) ? runData.items : [])
      setVariants(Array.isArray(variantData?.items) ? variantData.items : [])
    } catch (nextError: any) {
      setError(String(nextError?.message || nextError || 'Failed to load harness evaluations'))
      setRuns([])
      setVariants([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])
  const top = useMemo(() => variants.slice(0, 5), [variants])

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Harness evaluation</h3>
          <div className="muted">Live CLI scenarios compare provider, model, reasoning effort, CLI version and prompt variant. Results never auto-promote a production prompt.</div>
        </div>
        <button type="button" onClick={() => void load()} disabled={loading}>{loading ? 'Refreshing…' : 'Refresh'}</button>
      </div>
      {error && <div className="runStudioWarning"><b>Evaluation data unavailable:</b> {error}</div>}
      {!error && runs.length === 0 && <div className="muted">No Live Scenario Lab result has been ingested yet.</div>}
      {top.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <b>Variant leaderboard</b>
          <div className="timeline" style={{ marginTop: 6 }}>
            {top.map((row) => (
              <div key={String(row.runtime_signature || row.harness_variant_id)} className="timelineItem">
                <div><b>{row.harness_variant_id || 'unknown variant'}</b></div>
                <div className="runStudioMetaRow" style={{ marginTop: 4 }}>
                  <span className="pill">success: {((row.success_rate || 0) * 100).toFixed(1)}%</span>
                  <span className="pill">score: {(row.average_score || 0).toFixed(3)}</span>
                  <span className="pill">runs: {row.run_count || 0}</span>
                  <span className="pill">{row.provider || 'provider'} / {row.reasoning_effort || 'default'}</span>
                </div>
                <div className="muted">{row.model || 'provider default model'} · {row.latest_cli_version || 'CLI version not recorded'} · avg {Math.round(row.average_duration_ms || 0)} ms</div>
              </div>
            ))}
          </div>
        </div>
      )}
      {runs.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <b>Recent evaluation runs</b>
          <div className="timeline" style={{ marginTop: 6 }}>
            {runs.map((row) => (
              <div key={String(row.evaluation_id)} className="timelineItem">
                <div><b>{row.evaluation_id}</b> · {row.status || 'completed'}</div>
                <div className="muted">{row.suite || 'live'} · {row.passed_run_count || 0}/{row.total_run_count || 0} passed{row.recommendation_variant_id ? ` · recommended ${row.recommendation_variant_id}` : ''}{row.recommendation_runtime_signature ? ` · ${row.recommendation_runtime_signature}` : ''}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  )
}
