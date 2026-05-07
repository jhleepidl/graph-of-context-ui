import React from 'react'
import { previewThreadTeamPublishCandidate } from '../../api'
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
  threadId?: string | null
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


function summarizePublishReadiness(summary: Record<string, unknown>): string {
  const owner = cleanText(summary.final_owner || '(unset)')
  const finalStateRaw = cleanText(summary.final_answer_publish_state || '') || (summary.final_answer_publish_ok === false ? 'blocked' : 'ready')
  const artifactStateRaw = cleanText(summary.artifact_publish_state || '') || (summary.artifact_publish_ok === false ? 'blocked' : 'ready')
  const finalState = `final ${finalStateRaw}`
  const artifactState = `artifact ${artifactStateRaw}`
  return `owner=${owner} · ${finalState} · ${artifactState}`
}

type TeamPublishCandidatePreview = {
  candidate?: Record<string, any>
  review?: {
    summary?: Record<string, any>
    promote_to_rules?: Array<Record<string, any> | string>
    promote_to_roles?: Array<Record<string, any>>
    publish_as_knowledge_pack?: Array<Record<string, any>>
    keep_private?: Array<Record<string, any>>
    publish_schema_only?: Array<Record<string, any>>
    warnings?: string[]
  }
}

function candidateCount(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : Number(value || 0) || 0
}

function previewItemLabel(item: unknown): string {
  const row = asObject(item)
  return cleanText(row.text || row.label || row.title || row.name || row.surface_id || item)
}

function PublishCandidatePreviewCard({ preview }: { preview: TeamPublishCandidatePreview }) {
  const review = preview.review || {}
  const summary = review.summary || {}
  const candidate = preview.candidate || {}
  const rows: Array<{ label: string; count: number }> = [
    { label: 'rules', count: candidateCount(summary.runtime_rules) },
    { label: 'agents', count: candidateCount(summary.agents) },
    { label: 'knowledge packs', count: candidateCount(summary.optional_knowledge_packs) },
    { label: 'private exclusions', count: candidateCount(summary.private_exclusions) },
    { label: 'schema-only surfaces', count: candidateCount(summary.schema_only_surfaces) },
  ]
  const sections: Array<{ title: string; items?: unknown[]; helper: string }> = [
    { title: 'Promote to Rules', items: review.promote_to_rules, helper: 'Memory that affects behavior becomes explicit runtime guidance.' },
    { title: 'Publish as Knowledge Pack', items: review.publish_as_knowledge_pack, helper: 'Public/reusable memory is install-optional and refreshable on clone.' },
    { title: 'Keep Private', items: review.keep_private, helper: 'User, artifact, upload, credential, or chat-specific memory is not copied.' },
    { title: 'Schema Only', items: review.publish_schema_only, helper: 'Only purpose/read-write contract is published; clone gets fresh memory.' },
  ]

  return (
    <section className="runStudioPanelSubcard" style={{ marginBottom: 12 }}>
      <div className="row" style={{ marginBottom: 6 }}>
        <b>Publish / Clone Preview</b>
        <span className="pill">fresh private memory on clone</span>
        <span className="pill">credentials never copied</span>
      </div>
      <div className="muted" style={{ marginBottom: 8 }}>
        {cleanText(candidate.title) || 'Configured Team'} · public publish candidate review. Raw memory is not copied by default.
      </div>
      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
        {rows.map((row) => <span className="pill" key={row.label}>{row.label}: {row.count}</span>)}
      </div>
      <div className="runStudioGrid runStudioGrid--bottom" style={{ gap: 8 }}>
        {sections.map((section) => {
          const items = Array.isArray(section.items) ? section.items.slice(0, 5) : []
          return (
            <div key={section.title} className="runStudioPanelSubcard" style={{ margin: 0 }}>
              <b>{section.title}</b>
              <div className="muted">{section.helper}</div>
              {items.length > 0 ? (
                <ul style={{ margin: '6px 0 0 18px', padding: 0 }}>
                  {items.map((item, index) => <li key={`${section.title}-${index}`}>{previewItemLabel(item)}</li>)}
                </ul>
              ) : <div className="muted" style={{ marginTop: 6 }}>No items detected.</div>}
            </div>
          )
        })}
      </div>
      {(review.warnings || []).length > 0 && (
        <div className="runStudioWarning" style={{ marginTop: 8 }}>
          {(review.warnings || []).slice(0, 3).map((warning, index) => <div key={`pub-warning-${index}`}>{warning}</div>)}
        </div>
      )}
    </section>
  )
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
  threadId,
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
  const blueprintSummary = teamView?.blueprint_summary || null
  const [publishPreview, setPublishPreview] = React.useState<TeamPublishCandidatePreview | null>(null)
  const [publishPreviewLoading, setPublishPreviewLoading] = React.useState(false)
  const [publishPreviewError, setPublishPreviewError] = React.useState('')
  const loadPublishPreview = React.useCallback(async () => {
    const cleanThreadId = cleanText(threadId)
    if (!cleanThreadId) {
      setPublishPreviewError('Select a GoC thread before previewing publish/clone.')
      return
    }
    setPublishPreviewLoading(true)
    setPublishPreviewError('')
    try {
      const response = await previewThreadTeamPublishCandidate(cleanThreadId, { visibility: 'private_review' })
      setPublishPreview(response as TeamPublishCandidatePreview)
    } catch (error: any) {
      setPublishPreviewError(error?.message || String(error))
    } finally {
      setPublishPreviewLoading(false)
    }
  }, [threadId])

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

      <section className="runStudioPanelSubcard" style={{ marginBottom: 12 }}>
        <div className="row" style={{ marginBottom: 6 }}>
          <b>Team Publish Usability</b>
          <span className="pill">behavior blueprint</span>
          <span className="pill">optional knowledge packs</span>
        </div>
        <div className="muted" style={{ marginBottom: 8 }}>
          Preview what would be published before making it public: roles/rules/team contract are copied, public reusable memory becomes optional knowledge packs, private memory stays private.
        </div>
        <button onClick={loadPublishPreview} disabled={publishPreviewLoading || !threadId}>
          {publishPreviewLoading ? 'Building preview…' : 'Preview publish / clone package'}
        </button>
        {publishPreviewError && <div className="runStudioWarning" style={{ marginTop: 8 }}>{publishPreviewError}</div>}
      </section>

      {publishPreview && <PublishCandidatePreviewCard preview={publishPreview} />}

      {blueprintSummary && (
        <section className="runStudioPanelSubcard" style={{ marginBottom: 12 }}>
          <div className="row" style={{ marginBottom: 6 }}>
            <b>Selected Team Template</b>
            {blueprintSummary.task_archetype && <span className="pill">{blueprintSummary.task_archetype}</span>}
            {blueprintSummary.execution_pattern && <span className="pill">pattern: {blueprintSummary.execution_pattern}</span>}
          </div>
          <div className="muted">template: {cleanText(blueprintSummary.title) || '-'}</div>
          {cleanText(blueprintSummary.source) && <div className="muted">source: {cleanText(blueprintSummary.source)}</div>}
          {cleanText(blueprintSummary.description) && <div className="muted">{cleanText(blueprintSummary.description)}</div>}
          <div className="muted">memory surfaces: {Number(blueprintSummary.memory_surface_count || blueprintSummary.memory_map?.length || 0)}</div>
          {blueprintSummary.memory_contract_enforcement && (
            <>
              <div className="muted">
                memory contract: read={cleanText(blueprintSummary.memory_contract_enforcement.read_scope) || 'hard_role_scoped_local_only'} · write={cleanText(blueprintSummary.memory_contract_enforcement.write_scope) || 'hard_reroute'} · publish={cleanText(blueprintSummary.memory_contract_enforcement.publish_scope) || 'declared_only'}
              </div>
              <div className="muted">
                publish rules: final={cleanText(blueprintSummary.memory_contract_enforcement.final_publish_rule) || 'final_owner_declared_surface_required'} · artifact={cleanText(blueprintSummary.memory_contract_enforcement.artifact_publish_rule) || 'declared_artifact_surface_required'}
              </div>
            </>
          )}
          {blueprintSummary.publish_contract_readiness && (
            <>
              <div className="muted">
                route readiness: {summarizePublishReadiness(blueprintSummary.publish_contract_readiness as Record<string, unknown>)}
              </div>
              <div className="muted">
                final owner publish: {cleanText(blueprintSummary.publish_contract_readiness.final_owner) || '(unset)'} · {cleanText(blueprintSummary.publish_contract_readiness.final_answer_publish_state) || (blueprintSummary.publish_contract_readiness.final_answer_publish_ok === false ? 'blocked' : 'ready')}
              </div>
              <div className="muted">
                artifact publish: {cleanText(blueprintSummary.publish_contract_readiness.artifact_publish_state) || (blueprintSummary.publish_contract_readiness.artifact_publish_ok === false ? 'blocked' : 'ready')}{(blueprintSummary.publish_contract_readiness.artifact_publishers || []).length > 0 ? ` · publishers=${(blueprintSummary.publish_contract_readiness.artifact_publishers || []).join(', ')}` : ''}
              </div>
            </>
          )}
          {cleanText(blueprintSummary.capability_status) && <div className="muted">capability status: {cleanText(blueprintSummary.capability_status)}</div>}
          {(blueprintSummary.runtime_bound != null || cleanText(blueprintSummary.admission_status) || cleanText(blueprintSummary.admission_decision)) && (
            <div className="muted">admission: runtime_bound={blueprintSummary.runtime_bound === true ? 'true' : 'false'} · {cleanText(blueprintSummary.admission_status) || 'unbound'}{cleanText(blueprintSummary.admission_decision) ? ` · ${cleanText(blueprintSummary.admission_decision)}` : ''}</div>
          )}
          {(blueprintSummary.blocking_reason_codes || []).length > 0 && <div className="muted">blocking reasons: {(blueprintSummary.blocking_reason_codes || []).join(', ')}</div>}
          {(blueprintSummary.degrade_reason_codes || []).length > 0 && <div className="muted">degrade reasons: {(blueprintSummary.degrade_reason_codes || []).join(', ')}</div>}
          {(blueprintSummary.required_tool_count != null || blueprintSummary.optional_tool_count != null) && (
            <div className="muted">tools: required={Number(blueprintSummary.required_tool_count || 0)} · optional={Number(blueprintSummary.optional_tool_count || 0)}</div>
          )}
          {(blueprintSummary.missing_required_tools || []).length > 0 && <div className="muted">missing required: {(blueprintSummary.missing_required_tools || []).join(', ')}</div>}
          {(blueprintSummary.missing_optional_tools || []).length > 0 && <div className="muted">missing optional: {(blueprintSummary.missing_optional_tools || []).join(', ')}</div>}
          {blueprintSummary.executable_definition && (
            <>
              <div className="muted">
                executable definition: members={Number(blueprintSummary.executable_definition.member_count || blueprintSummary.executable_definition.participant_count || 0)} · ready={blueprintSummary.executable_definition.executable_ready === true ? 'true' : 'false'}
              </div>
              <div className="muted">
                topology contract: {cleanText(blueprintSummary.executable_definition.topology_contract?.pattern) || 'hybrid'}{cleanText(blueprintSummary.executable_definition.topology_contract?.execution_pattern) ? ` · ${cleanText(blueprintSummary.executable_definition.topology_contract?.execution_pattern)}` : ''} · edges={Number(blueprintSummary.executable_definition.topology_contract?.edge_count || 0)}
              </div>
              <div className="muted">
                memory contract: surfaces={Number(blueprintSummary.executable_definition.memory_contract?.surface_count || 0)} · writable={Number(blueprintSummary.executable_definition.memory_contract?.writable_surface_count || 0)} · final={blueprintSummary.executable_definition.memory_contract?.final_answer_surface_ready === true ? 'ready' : 'missing'}
              </div>
            </>
          )}
          {(blueprintSummary.memory_map || []).length > 0 && (
            <div className="muted" style={{ marginTop: 6 }}>
              {(blueprintSummary.memory_map || []).slice(0, 6).map((surface, index) => (
                <div key={`bp-surface-${index}`}>
                  {cleanText(surface.surface_id || surface.file_name) || 'surface'}
                  {cleanText(surface.load_policy) ? ` · load=${cleanText(surface.load_policy)}` : ''}
                  {cleanText(surface.write_policy) ? ` · write=${cleanText(surface.write_policy)}` : ''}
                </div>
              ))}
            </div>
          )}
          {(blueprintSummary.memory_acl_summary || []).length > 0 && (
            <div className="muted" style={{ marginTop: 6 }}>
              {(blueprintSummary.memory_acl_summary || []).slice(0, 6).map((acl, index) => (
                <div key={`bp-acl-${index}`}>
                  {cleanText(acl.role_id) || 'role'} · read={(acl.read_surface_ids || []).length} · write={(acl.write_surface_ids || []).length} · publish={(acl.publish_surface_ids || []).length}
                </div>
              ))}
            </div>
          )}
        </section>
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
