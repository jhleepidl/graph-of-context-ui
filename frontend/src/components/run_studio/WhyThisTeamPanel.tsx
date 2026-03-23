import React from 'react'
import {
  selectTeamDiversitySummary,
  selectTeamViewFlags,
} from './selectors'
import {
  type TeamViewProjection,
  type WhyThisTeamProjection,
} from './types'

type Props = {
  teamView: TeamViewProjection | null
  whyThisTeam: WhyThisTeamProjection | null
}

function roleBucketCount(teamView: TeamViewProjection | null, pattern: RegExp): number {
  return (teamView?.items || []).filter((item) =>
    pattern.test([item.display_label, item.role_label, item.slot_label].filter(Boolean).join(' ').toLowerCase()),
  ).length
}

export default function WhyThisTeamPanel({ teamView, whyThisTeam }: Props) {
  const selectionExplanations = whyThisTeam?.selection_explanations || []
  const slotReasons = whyThisTeam?.slot_reasons || []
  const agentReasons = whyThisTeam?.agent_reasons || []
  const diversityNotes = selectTeamDiversitySummary(teamView)
  const { reviewerPresent, synthesizerPresent } = selectTeamViewFlags(teamView)
  const researcherCount = roleBucketCount(teamView, /research|analyst|retriev|evidence/)
  const builderCount = roleBucketCount(teamView, /build|writer|synth|compose|final/)
  const presetCount = whyThisTeam?.preset_count ?? teamView?.preset_count ?? 0
  const synthesizedCount = whyThisTeam?.synthesized_count ?? teamView?.synthesized_count ?? 0
  const preferenceEntries = Object.entries(whyThisTeam?.conversation_preferences || {})

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Why this team?</h3>
        <div className="runStudioMetaRow">
          <span className="pill">explanations: {selectionExplanations.length}</span>
          <span className="pill">slot reasons: {slotReasons.length}</span>
          <span className="pill">agent reasons: {agentReasons.length}</span>
          <span className="pill">preset-backed: {presetCount}</span>
          <span className="pill">synthesized: {synthesizedCount}</span>
        </div>
      </div>

      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
        {reviewerPresent && <span className="pill">reviewer choice visible</span>}
        {synthesizerPresent && <span className="pill">synthesizer choice visible</span>}
        {researcherCount > 1 && <span className="pill">multiple researchers: {researcherCount}</span>}
        {builderCount > 1 && <span className="pill">multiple builders: {builderCount}</span>}
      </div>

      {diversityNotes.length > 0 && (
        <div className="runStudioList" style={{ marginBottom: 8 }}>
          {diversityNotes.map((note) => (
            <div key={note} className="runStudioInlineSubItem">
              <div className="muted">{note}</div>
            </div>
          ))}
        </div>
      )}

      {preferenceEntries.length > 0 && (
        <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
          {preferenceEntries.map(([key, value]) => (
            <span key={String(key)} className="pill">{String(key)}: {String(value)}</span>
          ))}
        </div>
      )}

      <div className="runStudioList">
        {selectionExplanations.map((explanation, index) => (
          <article key={`explanation:${index}`} className="runStudioListItem">
            <div className="row" style={{ marginBottom: 4 }}>
              {Boolean(explanation.slot_id) && <span className="pill">slot: {String(explanation.slot_id)}</span>}
              {Boolean(explanation.role_id) && <span className="pill">role: {String(explanation.role_id)}</span>}
            </div>
            <div>{String(explanation.text || explanation.summary || explanation.reason || '') || 'No explanation text provided.'}</div>
          </article>
        ))}

        {slotReasons.map((reason, index) => (
          <article key={`slot:${reason.slot_id || index}`} className="runStudioListItem">
            <div className="row" style={{ marginBottom: 4 }}>
              <span className="pill">{reason.display_label || reason.slot_id || 'slot'}</span>
              {reason.role_id && <span className="pill">role: {reason.role_id}</span>}
            </div>
            <div className="muted">{reason.reason || 'No slot-level reason provided.'}</div>
          </article>
        ))}

        {selectionExplanations.length === 0 && slotReasons.length === 0 && agentReasons.map((reason, index) => (
          <article key={`agent:${reason.runtime_instance_id || index}`} className="runStudioListItem">
            <div className="row" style={{ marginBottom: 4 }}>
              <span className="pill">{reason.display_label || reason.runtime_instance_id || 'runtime agent'}</span>
            </div>
            <div className="muted">{reason.reason || 'No agent-level reason provided.'}</div>
          </article>
        ))}

        {selectionExplanations.length === 0 && slotReasons.length === 0 && agentReasons.length === 0 && (
          <div className="muted">No explicit team-selection rationale was emitted. Legacy payloads still render runtime agents safely.</div>
        )}
      </div>
    </section>
  )
}
