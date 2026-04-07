import React from 'react'
import { type TeamSelectionCandidateFeature, type TeamSelectionDataset, type TeamSelectionDatasetRow } from './types'

type Props = {
  teamSelection: TeamSelectionDataset | null
  onLoadDetail?: () => void
  detailLoading?: boolean
  detailLoaded?: boolean
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : String(value || '').trim()
}

function scoreText(value: unknown): string {
  const num = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(num) ? num.toFixed(1) : '-'
}

function candidateTitle(candidate: TeamSelectionCandidateFeature | null | undefined): string {
  if (!candidate) return 'Unknown candidate'
  return cleanText(candidate.title || candidate.template_id || 'Unknown candidate')
}

function outcomeTone(row: TeamSelectionDatasetRow | null | undefined): string {
  if (!row) return 'runStudioStatus--idle'
  if (row.success) return 'runStudioStatus--done'
  if ((row.training_eligible === false) || (row.memory_fit_failure === true)) return 'runStudioStatus--blocked'
  return 'runStudioStatus--queued'
}

function alignmentLabel(value: string): string {
  const clean = value.trim().toLowerCase()
  if (clean === 'top_pick') return 'selected top recommendation'
  if (clean === 'in_candidates') return 'selected alternative candidate'
  if (clean === 'off_recommendation') return 'selected outside recommendation'
  if (clean === 'selected_snapshot_only') return 'selected snapshot only'
  if (clean === 'no_recommendation') return 'no recommendation'
  return clean || 'alignment unknown'
}

function renderBreakdown(candidate: TeamSelectionCandidateFeature | null | undefined) {
  const entries = Object.entries(candidate?.feature_score_breakdown || {})
    .filter(([, value]) => Number(value || 0) !== 0)
    .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))
  if (entries.length === 0) return <div className="muted">No explicit feature score breakdown emitted.</div>
  return (
    <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
      {entries.map(([key, value]) => (
        <span key={key} className="pill">{key}: {scoreText(value)}</span>
      ))}
    </div>
  )
}

function CandidateCard({
  title,
  candidate,
  highlight,
}: {
  title: string
  candidate: TeamSelectionCandidateFeature | null | undefined
  highlight?: string
}) {
  return (
    <article className="runStudioAgentCard">
      <div className="runStudioAgentCardHeader">
        <div>
          <div className="runStudioAgentCardTitle">{title}</div>
          <div className="muted">{candidateTitle(candidate)}</div>
        </div>
        {highlight ? <span className="runStudioStatusChip runStudioStatus--idle">{highlight}</span> : null}
      </div>
      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
        {candidate?.task_archetype && <span className="pill">{candidate.task_archetype}</span>}
        <span className="pill">score: {scoreText(candidate?.score)}</span>
        {candidate?.topology_pattern && <span className="pill">topology: {candidate.topology_pattern}</span>}
        {typeof candidate?.member_count === 'number' && <span className="pill">members: {candidate.member_count}</span>}
        {typeof candidate?.surface_count === 'number' && <span className="pill">surfaces: {candidate.surface_count}</span>}
        {candidate?.admission_status && <span className="pill">admission: {candidate.admission_status}</span>}
        {candidate?.runtime_bound && <span className="pill">runtime-bound</span>}
        {candidate?.ready && <span className="pill">ready</span>}
      </div>
      {renderBreakdown(candidate)}
      {(candidate?.rationale || []).length > 0 && (
        <ul style={{ margin: '8px 0 0 18px' }}>
          {(candidate?.rationale || []).slice(0, 5).map((entry) => <li key={`${candidate?.template_id || 'candidate'}:${entry}`}>{entry}</li>)}
        </ul>
      )}
      {(candidate?.blocking_reason_codes || []).length > 0 && (
        <div className="muted" style={{ marginTop: 6 }}>blocking: {(candidate?.blocking_reason_codes || []).join(', ')}</div>
      )}
      {(candidate?.degrade_reason_codes || []).length > 0 && (
        <div className="muted" style={{ marginTop: 4 }}>degrade: {(candidate?.degrade_reason_codes || []).join(', ')}</div>
      )}
    </article>
  )
}

export default function TeamRecommendationPanel({
  teamSelection,
  onLoadDetail,
  detailLoading,
  detailLoaded,
}: Props) {
  const rows = teamSelection?.rows || []
  const latest = rows[0] || null
  const recommended = latest?.recommended_candidates || []
  const selected = latest?.selected_features || null
  const topRecommended = latest?.top_recommended_candidate || recommended[0] || null

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Team Recommendation Quality</h3>
          <div className="muted">Selected-vs-recommended comparison, recommendation rationale, and dataset exclusion status for the most recent team-selection traces.</div>
        </div>
        {!detailLoaded && onLoadDetail && (
          <button onClick={onLoadDetail} disabled={detailLoading}>
            {detailLoading ? 'Loading...' : 'Load detail'}
          </button>
        )}
      </div>

      {!detailLoaded && !detailLoading && (
        <div className="muted">Load recent team-selection traces to inspect recommendation alignment and training-data exclusions.</div>
      )}

      {detailLoaded && (
        <>
          <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
            <span className="pill">events: {teamSelection?.count || 0}</span>
            <span className="pill">eligible: {teamSelection?.eligible_count || 0}</span>
            <span className="pill">excluded: {teamSelection?.excluded_count || 0}</span>
            {Object.entries(teamSelection?.exclusion_reason_counts || {}).map(([reason, count]) => (
              <span key={reason} className="pill">{reason}: {count}</span>
            ))}
          </div>

          {!latest && <div className="muted">No team-selection events have been recorded for this thread yet.</div>}

          {latest && (
            <div className="runStudioTeamGroupList">
              <section className="runStudioTeamGroup">
                <div className="runStudioTeamGroupHeader">
                  <div className="runStudioExecutionLaneTitle">Most recent decision</div>
                  <span className={`runStudioStatusChip ${outcomeTone(latest)}`}>{latest.success ? 'success' : (latest.training_eligible === false ? 'excluded' : 'recorded')}</span>
                </div>
                <div className="muted" style={{ marginBottom: 8 }}>{cleanText(latest.task_text || '(no task text)')}</div>
                <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                  {latest.task_archetype && <span className="pill">archetype: {latest.task_archetype}</span>}
                  {latest.recommendation_alignment && <span className="pill">{alignmentLabel(latest.recommendation_alignment)}</span>}
                  {typeof latest.selected_candidate_rank === 'number' && <span className="pill">selected rank: {latest.selected_candidate_rank}</span>}
                  {typeof latest.recommendation_gap === 'number' && <span className="pill">score gap: {scoreText(latest.recommendation_gap)}</span>}
                  {latest.human_override && <span className="pill">human override</span>}
                  {latest.memory_fit_failure && <span className="pill">memory-fit failure</span>}
                </div>
                {latest.training_eligible === false && (
                  <div className="runStudioWarning" style={{ marginBottom: 8 }}>
                    <b>Excluded from training.</b> {(latest.exclusion_reasons || []).join(', ') || 'Unknown reason'}
                  </div>
                )}
                {!!cleanText(latest.human_override_reason) && (
                  <div className="muted" style={{ marginBottom: 8 }}>override reason: {latest.human_override_reason}</div>
                )}
                <div className="runStudioAgentCardGrid">
                  <CandidateCard title="Selected team" candidate={selected} highlight={latest.selected_candidate_found ? 'used' : 'missing'} />
                  <CandidateCard title="Top recommendation" candidate={topRecommended} highlight={topRecommended && selected && cleanText(topRecommended.template_id) === cleanText(selected.template_id) ? 'matched' : 'recommended'} />
                </div>
              </section>

              <section className="runStudioTeamGroup">
                <div className="runStudioTeamGroupHeader">
                  <div className="runStudioExecutionLaneTitle">Top recommended candidates</div>
                  <div className="muted">{recommended.length}</div>
                </div>
                {recommended.length === 0 ? (
                  <div className="muted">No recommendation candidates were stored for this event.</div>
                ) : (
                  <div className="runStudioAgentCardGrid">
                    {recommended.slice(0, 3).map((candidate, index) => (
                      <CandidateCard
                        key={`${candidate.template_id || candidate.title || 'candidate'}:${index}`}
                        title={`Rank ${index + 1}`}
                        candidate={candidate}
                        highlight={index === 0 ? 'top' : undefined}
                      />
                    ))}
                  </div>
                )}
              </section>
            </div>
          )}
        </>
      )}
    </section>
  )
}
