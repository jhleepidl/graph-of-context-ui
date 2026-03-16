import React from 'react'
import {
  selectDominantSkills,
  selectTeamViewFlags,
} from './selectors'
import {
  type CollaborationProjection,
  type OrchestrationProjection,
  type RunStudioAgentTeam,
  type RuntimeAgentInstanceV2,
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

function laneLabel(roleId: string): string {
  const clean = String(roleId || '').trim().toLowerCase()
  if (clean === 'researcher') return 'Research lanes'
  if (clean === 'reviewer') return 'Review gate'
  if (clean === 'synthesizer') return 'Final synthesis'
  if (clean === 'builder') return 'Build lane'
  if (clean === 'operator') return 'Runtime ops'
  return 'Runtime agents'
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
    orchestration?.supervisor_enabled ||
    orchestration?.supervisor_mode ||
    orchestration?.supervisor_runtime?.interaction_mode ||
    orchestration?.supervisor_edges?.length ||
    orchestration?.supervisor_runtime?.mode ||
    orchestration?.supervisor_runtime?.instance_id,
  )
  const { reviewerPresent, synthesizerPresent } = selectTeamViewFlags(teamView)
  const degradedMode = Boolean(authority?.degraded_mode ?? legacyTeam?.degraded_mode)
  const fallbackReason = String(authority?.fallback_reason || legacyTeam?.fallback_reason || '').trim()

  const grouped = new Map<string, RuntimeAgentInstanceV2[]>()
  items.forEach((item) => {
    const role = String(item.role_id || item.role_label || 'runtime').trim().toLowerCase() || 'runtime'
    if (!grouped.has(role)) grouped.set(role, [])
    grouped.get(role)!.push(item)
  })
  const orderedGroups = Array.from(grouped.entries()).sort((a, b) => {
    const order = ['researcher', 'builder', 'reviewer', 'synthesizer', 'operator']
    return (order.indexOf(a[0]) === -1 ? 99 : order.indexOf(a[0])) - (order.indexOf(b[0]) === -1 ? 99 : order.indexOf(b[0]))
  })

  return (
    <section className="card runStudioPanel runStudioTeamPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3 style={{ margin: 0 }}>Runtime Agents</h3>
          <div className="muted">Preset-backed or synthesized workers that currently make up the team.</div>
        </div>
        <div className="runStudioMetaRow">
          <span className="pill">runtime agents: {runtimeCount}</span>
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
          No runtime agents are visible yet. Legacy team detail will appear after execution emits runtime members.
        </div>
      )}

      <div className="runStudioTeamGroupList">
        {orderedGroups.map(([role, roleItems]) => (
          <section key={role} className="runStudioTeamGroup">
            <div className="runStudioTeamGroupHeader">
              <div className="runStudioExecutionLaneTitle">{laneLabel(role)}</div>
              <div className="muted">{roleItems.length} agent{roleItems.length === 1 ? '' : 's'}</div>
            </div>
            <div className="runStudioAgentCardGrid">
              {roleItems.map((item, index) => {
                const dominantSkills = selectDominantSkills(item)
                const fallbackSkillIds = (item.attached_skill_ids || []).slice(0, 4)
                const skillChips = dominantSkills.length > 0
                  ? dominantSkills.map((skill) => skill.skill_name || skill.skill_id)
                  : fallbackSkillIds
                const status = String(item.runtime_status || 'idle')
                return (
                  <article
                    key={`${item.runtime_instance_id || item.agent_id || item.display_label || 'runtime-agent'}:${index}`}
                    className="runStudioAgentCard"
                  >
                    <div className="row" style={{ marginBottom: 6 }}>
                      <b>{item.display_label || item.role_label || item.agent_id || 'runtime agent'}</b>
                      <span className={`pill runStudioStatus ${runtimeClass(status)}`}>{status}</span>
                    </div>
                    <div className="runStudioMetaRow" style={{ marginBottom: 6 }}>
                      {item.preset_id && <span className="pill">preset-backed</span>}
                      {!item.preset_id && item.synthesized && <span className="pill">synthesized</span>}
                      {item.slot_label && <span className="pill">slot: {item.slot_label}</span>}
                      {!item.slot_label && item.slot_id && <span className="pill">slot: {item.slot_id}</span>}
                    </div>
                    <div className="muted">role: {item.role_label || item.role_id || '-'}</div>
                    {item.selection_reason && <div className="muted">selection: {item.selection_reason}</div>}
                    {item.authority_profile_id && <div className="muted">authority: {item.authority_profile_id}</div>}
                    {(item.provider || item.model) && <div className="muted">model: {item.provider || '-'} / {item.model || '-'}</div>}
                    {skillChips.length > 0 && (
                      <div className="runStudioMetaRow" style={{ marginTop: 8 }}>
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
        ))}
      </div>
    </section>
  )
}
