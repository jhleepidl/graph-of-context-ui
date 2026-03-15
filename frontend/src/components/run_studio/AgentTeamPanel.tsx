import React from 'react'
import {
  selectDominantSkills,
  selectTeamViewFlags,
} from './selectors'
import {
  type CollaborationProjection,
  type OrchestrationProjection,
  type RunStudioAgentTeam,
  type TeamViewProjection,
} from './types'

type Props = {
  teamView: TeamViewProjection | null
  legacyTeam: RunStudioAgentTeam | null
  orchestration: OrchestrationProjection | null
  collaboration: CollaborationProjection | null
}

function runtimeClass(status: string): string {
  const clean = status.trim().toLowerCase()
  if (clean === 'running') return 'runStudioStatus--running'
  if (clean === 'queued') return 'runStudioStatus--queued'
  if (clean === 'error' || clean === 'blocked') return 'runStudioStatus--blocked'
  if (clean === 'done') return 'runStudioStatus--done'
  return 'runStudioStatus--idle'
}

export default function AgentTeamPanel({
  teamView,
  legacyTeam,
  orchestration,
  collaboration,
}: Props) {
  const items = teamView?.items || []
  const authority = legacyTeam?.runtime_authority
  const runtimeCount = teamView?.count ?? items.length
  const presetCount = teamView?.preset_count ?? items.filter((item) => item.preset_id).length
  const synthesizedCount = teamView?.synthesized_count ?? items.filter((item) => item.synthesized).length
  const parallelGroupCount = orchestration?.parallel_group_count ?? orchestration?.parallel_groups?.length ?? 0
  const collaborationCount = collaboration?.count ?? collaboration?.items?.length ?? 0
  const supervisorEnabled = Boolean(
    orchestration?.supervisor_mode ||
    orchestration?.supervisor_edges?.length ||
    orchestration?.supervisor_runtime?.mode ||
    orchestration?.supervisor_runtime?.instance_id,
  )
  const { reviewerPresent, synthesizerPresent } = selectTeamViewFlags(teamView)
  const degradedMode = Boolean(authority?.degraded_mode ?? legacyTeam?.degraded_mode)
  const fallbackReason = String(authority?.fallback_reason || legacyTeam?.fallback_reason || '').trim()
  const runtimeSnapshotCount = (legacyTeam?.items || []).filter((item) => item.source === 'runtime_snapshot').length
  const threadTeamCount = (legacyTeam?.items || []).filter((item) => item.source === 'conversation_membership').length
  const inferredCount = (legacyTeam?.items || []).filter((item) => item.source === 'inferred_from_steps').length

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Team View</h3>
        <div className="runStudioMetaRow">
          <span className="pill">runtime: {runtimeCount}</span>
          <span className="pill">preset-backed: {presetCount}</span>
          <span className="pill">synthesized: {synthesizedCount}</span>
          <span className="pill">parallel groups: {parallelGroupCount}</span>
          <span className="pill">collaboration cells: {collaborationCount}</span>
          {reviewerPresent && <span className="pill">reviewer present</span>}
          {synthesizerPresent && <span className="pill">synthesizer present</span>}
          {supervisorEnabled && <span className="pill">supervisor enabled</span>}
        </div>
      </div>

      {degradedMode && fallbackReason && (
        <div className="runStudioWarning">
          <b>Fallback reason:</b> {fallbackReason}
        </div>
      )}

      {items.length === 0 && (
        <div className="muted">
          No runtime team projection is visible yet. Legacy team detail will appear after execution emits runtime members.
        </div>
      )}

      {items.length > 0 && (
        <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
          {runtimeSnapshotCount > 0 && <span className="pill">runtime snapshot: {runtimeSnapshotCount}</span>}
          {threadTeamCount > 0 && <span className="pill">thread team fallback: {threadTeamCount}</span>}
          {inferredCount > 0 && <span className="pill">inferred fallback: {inferredCount}</span>}
        </div>
      )}

      <div className="runStudioList">
        {items.map((item, index) => {
          const dominantSkills = selectDominantSkills(item)
          const fallbackSkillIds = (item.attached_skill_ids || []).slice(0, 3)
          const skillChips = dominantSkills.length > 0
            ? dominantSkills.map((skill) => skill.skill_name || skill.skill_id)
            : fallbackSkillIds
          const roleBits = [item.role_label, item.role_id].filter(Boolean)
          const slotBits = [item.slot_label, item.slot_id].filter(Boolean)
          const status = String(item.runtime_status || 'idle')

          return (
            <article
              key={`${item.runtime_instance_id || item.agent_id || item.display_label || 'runtime-agent'}:${index}`}
              className="runStudioListItem"
            >
              <div className="row" style={{ marginBottom: 6 }}>
                <b>{item.display_label || item.role_label || item.agent_id || 'runtime agent'}</b>
                <span className={`pill runStudioStatus ${runtimeClass(status)}`}>{status}</span>
                {item.preset_id && <span className="pill">preset: {item.preset_id}</span>}
                {!item.preset_id && item.synthesized && <span className="pill">synthesized</span>}
                {item.authority_profile_id && <span className="pill">authority: {item.authority_profile_id}</span>}
              </div>

              {roleBits.length > 0 && <div className="muted">role: {roleBits.join(' / ')}</div>}
              {slotBits.length > 0 && <div className="muted">slot: {slotBits.join(' / ')}</div>}
              {(item.provider || item.model) && (
                <div className="muted">
                  model: {item.provider || '-'} / {item.model || '-'}
                </div>
              )}
              {item.context_pack_id && <div className="muted">context pack: {item.context_pack_id}</div>}
              {item.runtime_instance_id && <div className="muted">runtime instance: {item.runtime_instance_id}</div>}
              {item.selection_reason && <div className="muted">selection: {item.selection_reason}</div>}

              {skillChips.length > 0 && (
                <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
                  {skillChips.map((skill) => (
                    <span key={`${item.runtime_instance_id || item.agent_id || 'runtime'}:${skill}`} className="pill">
                      {skill}
                    </span>
                  ))}
                </div>
              )}
            </article>
          )
        })}
      </div>
    </section>
  )
}
