import React, { useMemo, useState } from 'react'
import { api } from '../../api'
import { type TeamStrategyDataset } from './types'

type Props = {
  threadId?: string | null
  strategyMetrics: TeamStrategyDataset | null
  detailLoaded?: boolean
  detailLoading?: boolean
  onLoad?: () => void
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : String(value || '').trim()
}

function formatPct(value: unknown): string {
  const n = Number(value || 0)
  if (!Number.isFinite(n)) return '0%'
  return `${Math.round(n * 100)}%`
}

function formatNum(value: unknown): string {
  const n = Number(value)
  if (!Number.isFinite(n)) return 'n/a'
  return n.toFixed(1)
}

function triggerDownload(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 500)
}

export default function StrategyMetricsPanel({ threadId, strategyMetrics, detailLoaded, detailLoading, onLoad }: Props) {
  const [downloadState, setDownloadState] = useState<'json' | 'jsonl' | ''>('')
  const summary = strategyMetrics?.summary || null
  const topRows = useMemo(() => (strategyMetrics?.rows || []).slice(0, 5), [strategyMetrics])
  const hasData = Boolean(strategyMetrics && (strategyMetrics.count || 0) > 0)

  const exportDataset = async (format: 'json' | 'jsonl') => {
    const cleanThreadId = cleanText(threadId)
    if (!cleanThreadId) return
    setDownloadState(format)
    try {
      if (format === 'jsonl') {
        const text = await api.exportRunStudioStrategyDataset(cleanThreadId, 200, 'jsonl') as string
        triggerDownload(text, `team_strategy_${cleanThreadId}.jsonl`, 'application/x-ndjson')
      } else {
        const data = await api.exportRunStudioStrategyDataset(cleanThreadId, 200, 'json') as TeamStrategyDataset
        triggerDownload(JSON.stringify(data, null, 2), `team_strategy_${cleanThreadId}.json`, 'application/json')
      }
    } finally {
      setDownloadState('')
    }
  }

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Strategy Metrics Export</h3>
          <div className="muted">Thread-wide view of augment-only vs expand-team decisions, with exportable rows from team config revisions.</div>
        </div>
        <div className="row" style={{ marginBottom: 0 }}>
          {!hasData && <button onClick={onLoad} disabled={detailLoading || !threadId}>{detailLoading ? 'Loading...' : (detailLoaded ? 'Reload metrics' : 'Load metrics')}</button>}
          <button onClick={() => void exportDataset('json')} disabled={!threadId || downloadState !== ''}>{downloadState === 'json' ? 'Exporting...' : 'Export JSON'}</button>
          <button onClick={() => void exportDataset('jsonl')} disabled={!threadId || downloadState !== ''}>{downloadState === 'jsonl' ? 'Exporting...' : 'Export JSONL'}</button>
        </div>
      </div>

      {!hasData && !detailLoading && <div className="muted">Load the dataset to inspect recent strategy decisions in the UI, or export directly.</div>}
      {detailLoading && !hasData && <div className="muted">Loading strategy metrics…</div>}

      {hasData && (
        <>
          <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
            <span className="pill">events: {strategyMetrics?.count || 0}</span>
            <span className="pill">augment-only: {summary?.augment_only_count || 0} ({formatPct(summary?.augment_only_rate)})</span>
            <span className="pill">expand-team: {summary?.expand_team_count || 0} ({formatPct(summary?.expand_team_rate)})</span>
            <span className="pill">pending drafts: {summary?.auto_prepared_draft_count || 0}</span>
            <span className="pill">independent review: {summary?.independent_review_count || 0}</span>
            <span className="pill">persistent split: {summary?.persistent_split_count || 0}</span>
          </div>

          <div className="runStudioGrid runStudioGrid--bottom">
            <div className="runStudioAgentCard">
              <div className="runStudioAgentCardHeader">
                <div>
                  <div className="runStudioAgentCardTitle">Score summary</div>
                  <div className="muted">Average controller signals over exported revisions.</div>
                </div>
              </div>
              <div className="runStudioMetaRow">
                <span className="pill">avg augmentation: {formatNum(summary?.average_augmentation_score)}</span>
                <span className="pill">avg role separation: {formatNum(summary?.average_role_separation_score)}</span>
                {cleanText(summary?.latest_recommendation) && <span className="pill">latest: {cleanText(summary?.latest_recommendation)}</span>}
                {cleanText(summary?.latest_source) && <span className="pill">source: {cleanText(summary?.latest_source)}</span>}
              </div>
            </div>
            <div className="runStudioAgentCard">
              <div className="runStudioAgentCardHeader">
                <div>
                  <div className="runStudioAgentCardTitle">Frequent rationales</div>
                  <div className="muted">Top reasons behind augmentation or team expansion.</div>
                </div>
              </div>
              <div className="runStudioMetaRow">
                {(summary?.top_rationales || []).slice(0, 6).map((item, index) => (
                  <span key={`rationale-${index}`} className="pill">{cleanText(item?.value) || 'unknown'} · {Number(item?.count || 0)}</span>
                ))}
              </div>
              <div className="runStudioMetaRow" style={{ marginTop: 8 }}>
                {(summary?.top_capability_gaps || []).slice(0, 4).map((item, index) => (
                  <span key={`gap-${index}`} className="pill">gap: {cleanText(item?.value) || 'unknown'} · {Number(item?.count || 0)}</span>
                ))}
              </div>
            </div>
          </div>

          <div style={{ display: 'grid', gap: 10, marginTop: 10 }}>
            {topRows.map((row, index) => (
              <article key={cleanText(row.revision_id) || `strategy-row-${index}`} className="runStudioAgentCard">
                <div className="runStudioAgentCardHeader">
                  <div>
                    <div className="runStudioAgentCardTitle">{cleanText(row.recommendation) || 'unknown'} · {cleanText(row.team_name) || cleanText(row.team_state) || 'team'}</div>
                    <div className="muted">{cleanText(row.ts) || cleanText(row.created_at) || 'unknown time'}</div>
                  </div>
                  <div className="runStudioMetaRow">
                    {cleanText(row.source) && <span className="pill">{cleanText(row.source)}</span>}
                    {row.auto_prepared_draft && <span className="pill">pending draft</span>}
                    {row.independent_review_needed && <span className="pill">independent review</span>}
                    {row.persistent_split_needed && <span className="pill">persistent split</span>}
                  </div>
                </div>
                <div className="muted">augmentation {formatNum(row.augmentation_score)} · role separation {formatNum(row.role_separation_score)} · quality gap {formatNum(row.quality?.quality_gap)}</div>
                {cleanText(row.capability_gap_summary) && <div className="muted" style={{ marginTop: 6 }}>Capability gaps: {cleanText(row.capability_gap_summary)}</div>}
                {(row.rationale || []).length > 0 && <div className="muted" style={{ marginTop: 6 }}>Why: {(row.rationale || []).join(', ')}</div>}
              </article>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
