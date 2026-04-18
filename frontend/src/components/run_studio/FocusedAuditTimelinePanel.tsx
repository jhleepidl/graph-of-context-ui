import React from 'react'
import { type RunStudioAuditTimeline, type RunStudioAuditTimelineEvent } from './types'

type Props = {
  auditTimeline: RunStudioAuditTimeline | null
  onFocusNode?: (nodeId: string) => void
  onOpenNode?: (nodeId: string) => void
  onFocusTrace?: (nodeIds: string[]) => void
  onOpenTrace?: (nodeIds: string[]) => void
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : String(value || '').trim()
}

function uniqueIds(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  values.forEach((value) => {
    const clean = cleanText(value)
    if (!clean || seen.has(clean)) return
    seen.add(clean)
    out.push(clean)
  })
  return out
}

function formatTimestamp(value?: string | null): string {
  const clean = cleanText(value)
  if (!clean) return 'unknown time'
  const parsed = new Date(clean)
  if (Number.isNaN(parsed.getTime())) return clean
  return parsed.toLocaleString()
}

function eventTitle(event: RunStudioAuditTimelineEvent): string {
  const category = cleanText(event.category)
  if (category === 'participant_signal') return cleanText(event.title || 'Participant signal')
  if (category === 'participant_digest') return cleanText(event.title || 'Folded participant digest')
  if (category === 'planning_motif') return cleanText(event.title || 'Planner motif selection')
  if (category === 'channel_verifier') return cleanText(event.title || 'Experiment channel verifier')
  if (category === 'channel_promotion') return cleanText(event.title || 'Channel promotion applied')
  return cleanText(event.title || event.category || 'timeline event')
}


function renderLinkedSummary(auditTimeline: RunStudioAuditTimeline | null) {
  const linked = auditTimeline?.linked_summary
  if (!linked) return null
  const motifs = (linked.selected_motif_ids || []).map((entry) => cleanText(entry)).filter(Boolean)
  const participantKinds = Object.entries(linked.participant_kind_counts || {}).filter(([, value]) => Number(value || 0) > 0)
  const participantLabels = (linked.participant_labels || []).map((entry) => cleanText(entry)).filter(Boolean)
  const executionReasons = (linked.execution_mode_reasons || []).map((entry) => cleanText(entry)).filter(Boolean)
  const executionSignals = Object.entries(linked.execution_mode_signals || {}).filter(([, value]) => cleanText(value).length > 0)
  const executionQualitySignals = Object.entries(linked.execution_quality_signals || {}).filter(([, value]) => cleanText(value).length > 0)
  const executionModeHistory = (linked.execution_mode_history_tail || []).map((entry) => entry as Record<string, unknown>).filter((entry) => cleanText(entry.mode))
  const taskFamilyHint = (linked.task_family_mode_hint || {}) as Record<string, unknown>
  const motifCompare = (linked.motif_compare || {}) as Record<string, unknown>
  const participantCompare = (linked.participant_policy_compare || {}) as Record<string, unknown>
  const participantSnapshot = (linked.participant_policy_snapshot || {}) as Record<string, unknown>
  const promotedMotifs = (linked.promoted_motif_ids || []).map((entry) => cleanText(entry)).filter(Boolean)
  const rolledBackMotifs = (linked.rolled_back_motif_ids || []).map((entry) => cleanText(entry)).filter(Boolean)
  const hasCompare = cleanText(motifCompare.channel) || cleanText(participantCompare.channel) || cleanText(linked.latest_overall_recommendation) || promotedMotifs.length > 0 || rolledBackMotifs.length > 0 || Object.keys(participantSnapshot).length > 0
  const hasTaskFamily = cleanText(linked.task_family_key) || cleanText(taskFamilyHint.mode || taskFamilyHint.recommended_mode || taskFamilyHint.stable_default_mode)
  const hasData = motifs.length > 0 || participantKinds.length > 0 || participantLabels.length > 0 || cleanText(linked.team_synthesis_mode) || cleanText(linked.execution_mode) || executionReasons.length > 0 || executionSignals.length > 0 || executionQualitySignals.length > 0 || executionModeHistory.length > 0 || hasCompare || hasTaskFamily
  if (!hasData) return null
  return (
    <div className="runStudioAgentCard" style={{ marginBottom: 10 }}>
      <div className="runStudioAgentCardHeader">
        <div>
          <div className="runStudioAgentCardTitle">Planner ↔ Participant Link</div>
          <div className="muted">Selected motifs and folded participant activity for the focused run.</div>
        </div>
        <div className="runStudioMetaRow">
          {cleanText(linked.team_synthesis_mode) && <span className="pill">mode: {cleanText(linked.team_synthesis_mode)}</span>}
          {cleanText(linked.execution_mode) && <span className="pill">execution: {cleanText(linked.execution_mode)}</span>}
          {cleanText(linked.task_family_key) && <span className="pill">task family: {cleanText(linked.task_family_key)}</span>}
          {cleanText(linked.motif_channel) && <span className="pill">motif channel: {cleanText(linked.motif_channel)}</span>}
          {linked.motif_feedback_run_count != null && <span className="pill">feedback runs: {linked.motif_feedback_run_count}</span>}
          {linked.participant_signal_count != null && <span className="pill">signals: {linked.participant_signal_count}</span>}
          {linked.participant_digest_count != null && <span className="pill">digests: {linked.participant_digest_count}</span>}
          {linked.channel_verifier_count != null && <span className="pill">verifiers: {linked.channel_verifier_count}</span>}
          {linked.channel_promotion_count != null && <span className="pill">promotions: {linked.channel_promotion_count}</span>}
          {cleanText(linked.latest_overall_recommendation) && <span className="pill">recommendation: {cleanText(linked.latest_overall_recommendation)}</span>}
        </div>
      </div>
      {motifs.length > 0 && <div className="muted" style={{ marginBottom: 8 }}><b>Selected motifs:</b> {motifs.join(', ')}</div>}
      {participantKinds.length > 0 && (
        <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
          {participantKinds.map(([key, value]) => <span key={key} className="pill">{cleanText(key)}: {Number(value || 0)}</span>)}
        </div>
      )}
      {participantLabels.length > 0 && <div className="muted">Participants involved: {participantLabels.join(', ')}</div>}
      {hasTaskFamily && (
        <div className="muted" style={{ marginTop: 8 }}>
          <div><b>Task family:</b> {cleanText(linked.task_family_key) || 'n/a'}</div>
          {cleanText(taskFamilyHint.mode || taskFamilyHint.recommended_mode || taskFamilyHint.stable_default_mode) && (
            <div>Stable default mode hint: {cleanText(taskFamilyHint.mode || taskFamilyHint.recommended_mode || taskFamilyHint.stable_default_mode)} · confidence {cleanText(taskFamilyHint.confidence)} · samples {cleanText(taskFamilyHint.sample_size)}</div>
          )}
        </div>
      )}
      {(executionReasons.length > 0 || executionSignals.length > 0 || executionQualitySignals.length > 0 || executionModeHistory.length > 0) && (
        <div className="muted" style={{ marginTop: 8 }}>
          {executionReasons.length > 0 && <div><b>Execution mode rationale:</b> {executionReasons.join(', ')}</div>}
          {executionSignals.length > 0 && (
            <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
              {executionSignals.slice(0, 8).map(([key, value]) => <span key={key} className="pill">{cleanText(key)}: {cleanText(value)}</span>)}
            </div>
          )}
          {executionQualitySignals.length > 0 && (
            <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
              {executionQualitySignals.slice(0, 8).map(([key, value]) => <span key={key} className="pill">{cleanText(key)}: {cleanText(value)}</span>)}
            </div>
          )}
          {executionModeHistory.length > 0 && (
            <div style={{ marginTop: 6 }}>
              <b>Recent mode history:</b> {executionModeHistory.map((entry) => `${cleanText(entry.mode)}:${cleanText(entry.status) || 'n/a'} q=${cleanText(entry.quality_health_score)} gap=${cleanText(entry.quality_gap)}`).join(' · ')}
            </div>
          )}
        </div>
      )}
      {hasCompare && (
        <div className="muted" style={{ marginTop: 8 }}>
          <div><b>Channel compare:</b></div>
          {cleanText(motifCompare.channel) && <div>Motif channel: {cleanText(motifCompare.channel)} → {cleanText(motifCompare.next_channel) || cleanText(motifCompare.channel)} ({cleanText(motifCompare.recommendation) || 'n/a'})</div>}
          {cleanText(participantCompare.channel) && <div>Participant policy: {cleanText(participantCompare.channel)} → {cleanText(participantCompare.next_channel) || cleanText(participantCompare.channel)} ({cleanText(participantCompare.recommendation) || 'n/a'})</div>}
          {promotedMotifs.length > 0 && <div>Promoted motifs: {promotedMotifs.join(', ')}</div>}
          {rolledBackMotifs.length > 0 && <div>Rolled back motifs: {rolledBackMotifs.join(', ')}</div>}
          {Object.keys(participantSnapshot).length > 0 && <div>Stable participant snapshot: threshold {cleanText(participantSnapshot.surface_threshold)} · budget {cleanText(participantSnapshot.max_surface_per_turn)} · source {cleanText(participantSnapshot.source_channel)}</div>}
        </div>
      )}
    </div>
  )
}

function renderMetadata(metadata: Record<string, unknown> | null | undefined) {
  if (!metadata) return null
  const entries = Object.entries(metadata).filter(([, value]) => {
    if (value == null) return false
    if (Array.isArray(value)) return value.length > 0
    if (typeof value === 'string') return cleanText(value).length > 0
    return true
  }).slice(0, 6)
  if (!entries.length) return null
  return (
    <div className="muted" style={{ marginTop: 8 }}>
      {entries.map(([key, value], index) => {
        const rendered = Array.isArray(value) ? value.map((item) => cleanText(item)).filter(Boolean).join(', ') : cleanText(value)
        if (!rendered) return null
        return <div key={`${key}-${index}`}>{key}: {rendered}</div>
      })}
    </div>
  )
}

export default function FocusedAuditTimelinePanel({ auditTimeline, onFocusNode, onOpenNode, onFocusTrace, onOpenTrace }: Props) {
  const items = auditTimeline?.items || []
  const categoryCounts = auditTimeline?.category_counts || {}
  const statusCounts = auditTimeline?.status_counts || {}

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Unified Audit Timeline</h3>
          <div className="muted">Chronological view across planning motifs, execution trace, participant signals/digests, evidence, memory projection, memory edges, and conflict resolution.</div>
        </div>
      </div>

      {!auditTimeline && <div className="muted">Focused run bundle has not been loaded yet.</div>}

      {auditTimeline && (
        <>
          <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
            <span className="pill">events: {auditTimeline.count ?? items.length}</span>
            {auditTimeline.selection_event_id && <span className="pill">selection event: {auditTimeline.selection_event_id}</span>}
            {auditTimeline.anchor_node_id && <span className="pill">anchor: {auditTimeline.anchor_node_id}</span>}
            {auditTimeline.started_at && <span className="pill">start: {formatTimestamp(auditTimeline.started_at)}</span>}
            {auditTimeline.ended_at && <span className="pill">end: {formatTimestamp(auditTimeline.ended_at)}</span>}
          </div>

          <div className="runStudioMetaRow" style={{ marginBottom: 10 }}>
            {Object.entries(categoryCounts).map(([key, count]) => <span key={key} className="pill">{key}: {count}</span>)}
            {Object.entries(statusCounts).slice(0, 6).map(([key, count]) => <span key={`status-${key}`} className="pill">{key}: {count}</span>)}
          </div>

          {renderLinkedSummary(auditTimeline)}

          {items.length === 0 ? (
            <div className="muted">No timeline events were materialized for this run yet.</div>
          ) : (
            <div style={{ display: 'grid', gap: 10 }}>
              {items.map((event, index) => {
                const primaryNodeId = cleanText(event.primary_node_id)
                const traceNodeIds = uniqueIds(event.trace_node_ids || event.related_node_ids || [])
                const relatedNodeIds = uniqueIds(event.related_node_ids || [])
                const badges = (event.badges || []).map((badge) => cleanText(badge)).filter(Boolean)
                const rationaleCodes = (event.rationale_codes || []).map((code) => cleanText(code)).filter(Boolean)
                return (
                  <article key={cleanText(event.event_id) || `timeline-${index}`} className="runStudioAgentCard">
                    <div className="runStudioAgentCardHeader">
                      <div>
                        <div className="runStudioAgentCardTitle">{eventTitle(event)}</div>
                        <div className="muted">{formatTimestamp(event.timestamp)}</div>
                      </div>
                      <div className="runStudioMetaRow">
                        {event.category && <span className="pill">{cleanText(event.category)}</span>}
                        {event.status && <span className="pill">status: {cleanText(event.status)}</span>}
                        {event.trace_anchor_related && <span className="pill">anchor-related</span>}
                      </div>
                    </div>

                    {cleanText(event.summary) && <div className="muted" style={{ marginBottom: 8 }}>{cleanText(event.summary)}</div>}
                    {cleanText((event.metadata as Record<string, unknown> | null | undefined)?.digest_block) && (
                      <pre style={{ marginTop: 0, marginBottom: 8, whiteSpace: 'pre-wrap', fontSize: 12, padding: 10, borderRadius: 10, background: '#f8fafc', border: '1px solid #e2e8f0' }}>
                        {cleanText((event.metadata as Record<string, unknown>)?.digest_block)}
                      </pre>
                    )}

                    {(badges.length > 0 || rationaleCodes.length > 0) && (
                      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                        {badges.map((badge) => <span key={badge} className="pill">{badge}</span>)}
                        {rationaleCodes.map((code) => <span key={`r-${code}`} className="pill">reason: {code}</span>)}
                      </div>
                    )}

                    <div className="row">
                      {primaryNodeId && onFocusNode && <button className="tiny" onClick={() => onFocusNode(primaryNodeId)}>Focus primary node</button>}
                      {primaryNodeId && onOpenNode && <button className="tiny" onClick={() => onOpenNode(primaryNodeId)}>Open node</button>}
                      {traceNodeIds.length > 1 && onFocusTrace && <button className="tiny" onClick={() => onFocusTrace(traceNodeIds)}>Focus related trace</button>}
                      {traceNodeIds.length > 1 && onOpenTrace && <button className="tiny" onClick={() => onOpenTrace(traceNodeIds)}>Open related trace</button>}
                    </div>

                    {relatedNodeIds.length > 0 && <div className="muted" style={{ marginTop: 8 }}>related nodes: {relatedNodeIds.join(', ')}</div>}
                    {renderMetadata(event.metadata || null)}
                  </article>
                )
              })}
            </div>
          )}
        </>
      )}
    </section>
  )
}
