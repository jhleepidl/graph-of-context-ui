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
import {
  humanizeExecutionPattern,
  humanizeModel,
  humanizePayload,
  humanizeSkill,
  humanizeVisibility,
  roleLabel,
} from './teamPresentation'

type Props = {
  teamView: TeamViewProjection | null
  legacyTeam: RunStudioAgentTeam | null
  orchestration: OrchestrationProjection | null
  collaboration: CollaborationProjection | null
}

type TeamContractSummary = {
  state: 'active' | 'pending'
  teamName: string
  compositionMode: string
  proposalMode: string
  agentCount: number
  executionPattern: string
  finalOwner: string
  shortcutEnabled: boolean | null
  maxRecentTurns: number | null
  reviewerVisibility: string
  synthesizerVisibility: string
  handoffs: Array<{ from?: string; to?: string; payload?: string }>
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : String(value || '').trim()
}

function asObject(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function toArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}

function runtimeClass(status: string): string {
  const clean = status.trim().toLowerCase()
  if (clean === 'running') return 'runStudioStatus--running'
  if (clean === 'queued') return 'runStudioStatus--queued'
  if (clean === 'error' || clean === 'blocked') return 'runStudioStatus--blocked'
  if (clean === 'done') return 'runStudioStatus--done'
  if (clean === 'configured' || clean === 'ready') return 'runStudioStatus--queued'
  return 'runStudioStatus--idle'
}

function laneLabel(roleId: string): string {
  const clean = String(roleId || '').trim().toLowerCase()
  if (clean === 'researcher') return '조사 레인'
  if (clean === 'reviewer') return '검토 게이트'
  if (clean === 'synthesizer') return '최종 정리'
  if (clean === 'builder') return '구현 레인'
  if (clean === 'operator') return '운영 레인'
  return 'Runtime agents'
}

function summarizeTeamContracts(teamConfig: RunStudioAgentTeam['team_config'] | undefined): TeamContractSummary[] {
  const summaries: TeamContractSummary[] = []
  ;(['active', 'pending'] as const).forEach((state) => {
    const team = asObject(teamConfig?.[`${state}_team` as 'active_team' | 'pending_team'])
    if (Object.keys(team).length === 0) return
    const interactionSpec = asObject(team.interaction_spec)
    const shortcutPolicy = asObject(team.shortcut_policy)
    const handoffs = toArray<Record<string, unknown>>(interactionSpec.handoffs).slice(0, 6).map((handoff) => ({
      from: cleanText(handoff.from) || undefined,
      to: cleanText(handoff.to) || undefined,
      payload: humanizePayload(handoff.payload) || undefined,
    }))
    const maxRecentTurnsRaw = shortcutPolicy.max_recent_turns
    const maxRecentTurns = typeof maxRecentTurnsRaw === 'number'
      ? maxRecentTurnsRaw
      : (typeof maxRecentTurnsRaw === 'string' && maxRecentTurnsRaw.trim() ? Number(maxRecentTurnsRaw) : null)
    summaries.push({
      state,
      teamName: cleanText(team.team_name || `${state} team`) || `${state} team`,
      compositionMode: cleanText(team.composition_mode || teamConfig?.composition_mode || 'structured') || 'structured',
      proposalMode: cleanText(team.proposal_mode || teamConfig?.proposal_mode || '-') || '-',
      agentCount: toArray(team.agents).length,
      executionPattern: humanizeExecutionPattern(interactionSpec.execution_pattern),
      finalOwner: cleanText(interactionSpec.final_answer_owner) || '-',
      shortcutEnabled: shortcutPolicy.enabled == null ? null : Boolean(shortcutPolicy.enabled),
      maxRecentTurns: Number.isFinite(maxRecentTurns as number) ? Number(maxRecentTurns) : null,
      reviewerVisibility: humanizeVisibility(asObject(interactionSpec.policies).reviewer_visibility),
      synthesizerVisibility: humanizeVisibility(asObject(interactionSpec.policies).synthesizer_visibility),
      handoffs,
    })
  })
  return summaries
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
  const configuredOnlyCount = items.filter((item) => item.configured_only).length
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
  const teamContracts = summarizeTeamContracts(legacyTeam?.team_config)

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
          <div className="muted">Runtime team, configured team proposal, and per-agent context policy summarized together.</div>
        </div>
        <div className="runStudioMetaRow">
          <span className="pill">runtime agents: {runtimeCount}</span>
          <span className="pill">preset-backed: {presetCount}</span>
          <span className="pill">synthesized: {synthesizedCount}</span>
          {configuredOnlyCount > 0 && <span className="pill">configured only: {configuredOnlyCount}</span>}
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

      {teamContracts.length > 0 && (
        <div className="runStudioAgentCardGrid" style={{ marginBottom: 12 }}>
          {teamContracts.map((contract) => (
            <section key={contract.state} className="runStudioPanelSubcard">
              <div className="row" style={{ marginBottom: 6 }}>
                <b>{contract.state === 'active' ? 'Active team contract' : 'Pending team proposal'}</b>
                <span className="pill">{contract.state}</span>
              </div>
              <div className="muted">team: {contract.teamName}</div>
              <div className="muted">구성 방식: {contract.compositionMode}</div>
              <div className="muted">제안 모드: {contract.proposalMode}</div>
              <div className="muted">agent 수: {contract.agentCount}</div>
              <div className="muted">흐름: {contract.executionPattern}</div>
              <div className="muted">최종 답변 담당: {contract.finalOwner}</div>
              <div className="muted">검토자 입력: {contract.reviewerVisibility}</div>
              <div className="muted">최종 정리자 입력: {contract.synthesizerVisibility}</div>
              {contract.shortcutEnabled != null && (
                <div className="muted">
                  shortcut 후속응답: {contract.shortcutEnabled ? '켜짐' : '꺼짐'}
                  {contract.maxRecentTurns != null ? ` · 최근 ${contract.maxRecentTurns}턴` : ''}
                </div>
              )}
              {contract.handoffs.length > 0 && (
                <div className="muted" style={{ marginTop: 6 }}>
                  {contract.handoffs.map((handoff, index) => (
                    <div key={`${contract.state}-handoff-${index}`}>{handoff.from || '-'} → {handoff.to || '-'} · {handoff.payload || '요약'}</div>
                  ))}
                </div>
              )}
            </section>
          ))}
        </div>
      )}

      {items.length === 0 && (
        <div className="muted">
          No runtime or configured agents are visible yet. Once `/team create` or execution emits team data, cards will appear here.
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
                const explicitSkills = (item.attached_skills || []).map((skill) => ({
                  name: skill.skill_name || skill.skill_id,
                  level: skill.load_level || 'metadata_only',
                }))
                const fallbackSkillIds = (item.attached_skill_ids || []).slice(0, 6).map((skillId) => ({
                  name: skillId,
                  level: 'metadata_only',
                }))
                const skillChips = explicitSkills.length > 0 ? explicitSkills : fallbackSkillIds
                const highlightSkills = dominantSkills.length > 0
                  ? dominantSkills.map((skill) => humanizeSkill(skill.skill_name || skill.skill_id))
                  : skillChips.slice(0, 3).map((skill) => humanizeSkill(skill.name))
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
                      {item.configured_only && <span className="pill">configured only</span>}
                      {item.config_state && <span className="pill">{item.config_state}</span>}
                      {item.team_name && <span className="pill">team: {item.team_name}</span>}
                      {item.slot_label && <span className="pill">slot: {item.slot_label}</span>}
                      {!item.slot_label && item.slot_id && <span className="pill">slot: {item.slot_id}</span>}
                      {item.scope_id && <span className="pill">scope: {item.scope_id}</span>}
                      {item.visibility_mode && <span className="pill">{humanizeVisibility(item.visibility_mode)}</span>}
                      {item.shortcut_eligible === true && <span className="pill">shortcut reply</span>}
                      {item.only_for_followups && <span className="pill">follow-up only</span>}
                    </div>
                    <div className="muted">역할: {roleLabel(item.role_label || item.role_id || '-')}</div>
                    {item.selection_reason && <div className="muted">선정 이유: {item.selection_reason}</div>}
                    {item.purpose && item.purpose !== item.selection_reason && <div className="muted">맡은 일: {item.purpose}</div>}
                    {item.authority_profile_id && <div className="muted">authority: {item.authority_profile_id}</div>}
                    {(item.provider || item.model) && <div className="muted">모델: {humanizeModel(item.provider, item.model)}</div>}
                    {typeof item.scope_token_estimate === 'number' && <div className="muted">scope budget est: {item.scope_token_estimate}</div>}
                    {item.query_template && <div className="muted">scope query: {item.query_template}</div>}
                    {item.context_policy_summary && <div className="muted">context policy: {item.context_policy_summary}</div>}

                    {(item.grant_labels || []).length > 0 && (
                      <div className="runStudioAgentSkillSection">
                        <div className="runStudioAgentSkillSectionLabel">Granted memory</div>
                        <div className="runStudioMetaRow">
                          {(item.grant_labels || []).map((grant) => (
                            <span key={`${item.runtime_instance_id || item.agent_id || 'runtime'}:grant:${grant}`} className="pill">
                              {grant}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {(item.context_types || []).length > 0 && (
                      <div className="runStudioAgentSkillSection">
                        <div className="runStudioAgentSkillSectionLabel">Context types</div>
                        <div className="runStudioMetaRow">
                          {(item.context_types || []).map((entry) => (
                            <span key={`${item.runtime_instance_id || item.agent_id || 'runtime'}:ctx:${entry}`} className="pill">{entry}</span>
                          ))}
                        </div>
                      </div>
                    )}

                    {(item.publish_targets || []).length > 0 && (
                      <div className="runStudioAgentSkillSection">
                        <div className="runStudioAgentSkillSectionLabel">Publishes</div>
                        <div className="runStudioMetaRow">
                          {(item.publish_targets || []).map((entry) => (
                            <span key={`${item.runtime_instance_id || item.agent_id || 'runtime'}:publish:${entry}`} className="pill">{entry}</span>
                          ))}
                        </div>
                      </div>
                    )}

                    {highlightSkills.length > 0 && (
                      <div className="runStudioAgentSkillSection">
                        <div className="runStudioAgentSkillSectionLabel">Skill profile</div>
                        <div className="runStudioMetaRow">
                          {highlightSkills.map((skill) => (
                            <span key={`${item.runtime_instance_id || item.agent_id || 'runtime'}:highlight:${skill}`} className="pill runStudioSkillPill runStudioSkillPill--prominent">
                              {skill}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {skillChips.length > 0 ? (
                      <div className="runStudioAgentSkillSection">
                        <div className="runStudioAgentSkillSectionLabel">Attached skills</div>
                        <div className="runStudioSkillStack">
                          {skillChips.map((skill) => (
                            <div key={`${item.runtime_instance_id || item.agent_id || 'runtime'}:${skill.name}:${skill.level}`} className="runStudioSkillRow">
                              <span className="runStudioSkillName">{humanizeSkill(skill.name)}</span>
                              <span className="pill">{skill.level}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div className="runStudioAgentSkillSection">
                        <div className="runStudioAgentSkillSectionLabel">Attached skills</div>
                        <div className="muted">No attached skill projection was emitted for this runtime agent.</div>
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
