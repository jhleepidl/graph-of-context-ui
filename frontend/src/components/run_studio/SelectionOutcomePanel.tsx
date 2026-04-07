import { useEffect, useMemo, useState } from 'react'
import type { TeamSelectionDataset, TeamSelectionDatasetRow } from './types'

type Props = {
  teamSelection: TeamSelectionDataset | null
  onInspectEvent?: (row: TeamSelectionDatasetRow) => void
  onClearInspect?: () => void
  inspectedRunId?: string | null
  inspectedEventId?: string | null
}

function pct(value?: number | null): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return `${Math.round(value * 100)}%`
}

function num(value?: number | null, digits = 2): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  return value.toFixed(digits)
}

function cleanText(value: unknown): string {
  return String(value || '').trim()
}

function eventLabel(row: TeamSelectionDatasetRow | null | undefined, index: number): string {
  const runId = cleanText(row?.run_id)
  const eventId = cleanText(row?.event_id)
  if (runId) return runId
  if (eventId) return eventId
  return `event-${index + 1}`
}

export default function SelectionOutcomePanel({ teamSelection, onInspectEvent, onClearInspect, inspectedRunId, inspectedEventId }: Props) {
  const summary = teamSelection?.selection_outcome_summary || null
  const alignmentCounts = Object.entries(summary?.alignment_counts || {}).sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))
  const successRates = summary?.success_rate_by_alignment || {}
  const avgQuality = summary?.average_artifact_quality_by_alignment || {}
  const avgGap = summary?.average_recommendation_gap_by_alignment || {}
  const rows = useMemo(() => (teamSelection?.rows || []).slice(0, 8), [teamSelection])
  const [selectedEventId, setSelectedEventId] = useState<string>('')

  useEffect(() => {
    const first = rows[0]
    const nextId = cleanText(first?.event_id || first?.run_id)
    setSelectedEventId((prev) => prev || nextId)
  }, [rows])

  const selectedRow = useMemo(() => {
    if (!rows.length) return null
    if (!selectedEventId) return rows[0]
    return rows.find((row) => cleanText(row.event_id || row.run_id) === selectedEventId) || rows[0]
  }, [rows, selectedEventId])

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Selection vs Outcome Analytics</h3>
          <div className="muted">Outcome patterns by recommendation alignment, with drill-down into recent run/event decisions.</div>
        </div>
      </div>

      {!summary && <div className="muted">Load team-selection detail to inspect alignment-driven outcome analytics.</div>}

      {summary && (
        <>
          <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
            <span className="pill">events: {teamSelection?.count || 0}</span>
            <span className="pill">eligible: {teamSelection?.eligible_count || 0}</span>
            <span className="pill">human override: {summary.human_override_count || 0}</span>
            <span className="pill">memory-fit failure: {summary.memory_fit_failure_count || 0}</span>
          </div>

          {alignmentCounts.length === 0 ? (
            <div className="muted">No aligned outcome rows are available yet.</div>
          ) : (
            <div className="runStudioAgentCardGrid" style={{ marginBottom: 12 }}>
              {alignmentCounts.map(([alignment, count]) => (
                <article key={alignment} className="runStudioAgentCard">
                  <div className="runStudioExecutionLaneTitle">{alignment}</div>
                  <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                    <span className="pill">count: {count}</span>
                    <span className="pill">success: {pct(successRates[alignment])}</span>
                    <span className="pill">artifact quality: {num(avgQuality[alignment])}</span>
                    <span className="pill">gap: {num(avgGap[alignment])}</span>
                  </div>
                  {!!(summary.alignment_event_samples?.[alignment] || []).length && (
                    <div className="muted">
                      sample events: {(summary.alignment_event_samples?.[alignment] || [])
                        .map((sample) => cleanText(sample.run_id || sample.event_id))
                        .filter(Boolean)
                        .join(', ')}
                    </div>
                  )}
                </article>
              ))}
            </div>
          )}

          <section className="runStudioTeamGroup">
            <div className="runStudioTeamGroupHeader">
              <div className="runStudioExecutionLaneTitle">Recent team-selection events</div>
              <div className="muted">{rows.length}</div>
            </div>
            {rows.length === 0 ? (
              <div className="muted">No recent team-selection events were stored.</div>
            ) : (
              <div className="runStudioAgentCardGrid" style={{ marginBottom: 12 }}>
                {rows.map((row, index) => {
                  const key = cleanText(row.event_id || row.run_id) || `row-${index}`
                  const active = selectedRow ? cleanText(selectedRow.event_id || selectedRow.run_id) === key : index === 0
                  return (
                    <button
                      key={key}
                      type="button"
                      className="runStudioAgentCard"
                      onClick={() => {
                        setSelectedEventId(key)
                        if (cleanText(row.run_id)) onInspectEvent?.(row)
                      }}
                      style={{ textAlign: 'left', border: active ? '1px solid var(--accent, #6b7cff)' : undefined }}
                    >
                      <div className="runStudioExecutionLaneTitle">{eventLabel(row, index)}</div>
                      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                        {row.recommendation_alignment && <span className="pill">{row.recommendation_alignment}</span>}
                        {String(row.run_id || '').trim() && String(row.run_id || '').trim() === String(inspectedRunId || '').trim() && <span className="pill">inspecting run</span>}
                        {String(row.event_id || '').trim() && String(row.event_id || '').trim() === String(inspectedEventId || '').trim() && <span className="pill">selected event</span>}
                        <span className="pill">{row.success ? 'success' : 'failure'}</span>
                        {typeof row.selected_candidate_rank === 'number' && <span className="pill">rank: {row.selected_candidate_rank}</span>}
                        {typeof row.recommendation_gap === 'number' && <span className="pill">gap: {num(row.recommendation_gap)}</span>}
                      </div>
                      <div className="muted">{cleanText(row.selected_blueprint_id || row.selected_features?.template_id || '(no selected blueprint)')}</div>
                    </button>
                  )
                })}
              </div>
            )}

            {selectedRow && (
              <article className="runStudioAgentCard">
                <div className="runStudioTeamGroupHeader">
                  <div className="runStudioExecutionLaneTitle">Event detail</div>
                  <div className="muted">{eventLabel(selectedRow, 0)}</div>
                </div>
                <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                  {selectedRow.task_archetype && <span className="pill">archetype: {selectedRow.task_archetype}</span>}
                  {selectedRow.recommendation_alignment && <span className="pill">alignment: {selectedRow.recommendation_alignment}</span>}
                  <span className="pill">success: {selectedRow.success ? 'yes' : 'no'}</span>
                  <span className="pill">artifact quality: {num(selectedRow.artifact_quality)}</span>
                  <span className="pill">approval friction: {num(selectedRow.approval_friction)}</span>
                  <span className="pill">recovery: {selectedRow.recovery_count ?? '—'}</span>
                </div>
                <div className="muted" style={{ marginBottom: 8 }}>{cleanText(selectedRow.task_text || '(no task text)')}</div>
                <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                  <span className="pill">selected: {cleanText(selectedRow.selected_blueprint_id || selectedRow.selected_features?.template_id || '(missing)')}</span>
                  <span className="pill">top recommended: {cleanText(selectedRow.top_recommended_candidate?.template_id || '(none)')}</span>
                  {typeof selectedRow.recommendation_gap === 'number' && <span className="pill">gap: {num(selectedRow.recommendation_gap)}</span>}
                </div>
                <div className="row" style={{ marginBottom: 8 }}>
                  <button
                    type="button"
                    onClick={() => onInspectEvent?.(selectedRow)}
                    disabled={!cleanText(selectedRow.run_id)}
                  >
                    {cleanText(selectedRow.run_id) && cleanText(selectedRow.run_id) === cleanText(inspectedRunId) ? 'Inspecting this run' : 'Inspect related run'}
                  </button>
                  {cleanText(inspectedRunId) && onClearInspect && (
                    <button type="button" className="tiny" onClick={() => onClearInspect()}>
                      Clear drill-down
                    </button>
                  )}
                </div>
                {selectedRow.training_eligible === false && (
                  <div className="runStudioWarning" style={{ marginBottom: 8 }}>
                    <b>Excluded from training.</b> {(selectedRow.exclusion_reasons || []).join(', ') || 'Unknown reason'}
                  </div>
                )}
                {!!cleanText(selectedRow.human_override_reason) && (
                  <div className="muted" style={{ marginBottom: 8 }}>override reason: {selectedRow.human_override_reason}</div>
                )}
                {selectedRow.memory_fit_failure && (
                  <div className="muted" style={{ marginBottom: 8 }}>memory-fit failure was recorded for this event.</div>
                )}
              </article>
            )}
          </section>
        </>
      )}
    </section>
  )
}
