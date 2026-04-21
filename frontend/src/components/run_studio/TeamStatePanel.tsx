import React, { useMemo } from 'react'
import { type RunStudioAgentTeam, type RunStudioAuditTimeline, type RunStudioSummary } from './types'
import { humanizeExecutionPattern } from './teamPresentation'

type Props = {
  summary: RunStudioSummary | null
  team: RunStudioAgentTeam | null
  auditTimeline: RunStudioAuditTimeline | null
}

type SignalChip = {
  key: string
  label: string
  value: string
  tone: 'neutral' | 'good' | 'warn' | 'bad'
}

type AdaptiveExpansionMeta = {
  recommendation: string
  rationale: string[]
  augmentationScore: number | null
  augmentationReasons: string[]
  roleSeparationScore: number | null
  roleSeparationReasons: string[]
  independentReviewNeeded: boolean
  persistentSplitNeeded: boolean
  capabilityGapSummary: string
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : String(value || '').trim()
}

function asObject(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function asArray<T = unknown>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}


function asNumber(value: unknown): number | null {
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

function parseAdaptiveExpansionMeta(teamPayload: Record<string, unknown> | null | undefined): AdaptiveExpansionMeta | null {
  const plannerMetadata = asObject(asObject(teamPayload).planner_metadata)
  const adaptive = asObject(plannerMetadata.adaptive_expansion)
  if (Object.keys(adaptive).length === 0) return null
  const augmentation = asObject(adaptive.augmentation)
  const roleSeparation = asObject(adaptive.role_separation)
  return {
    recommendation: cleanText(adaptive.recommendation).toLowerCase(),
    rationale: asArray<string>(adaptive.rationale).map((entry) => cleanText(entry)).filter(Boolean),
    augmentationScore: asNumber(augmentation.score),
    augmentationReasons: asArray<string>(augmentation.reasons).map((entry) => cleanText(entry)).filter(Boolean),
    roleSeparationScore: asNumber(roleSeparation.score),
    roleSeparationReasons: asArray<string>(roleSeparation.reasons).map((entry) => cleanText(entry)).filter(Boolean),
    independentReviewNeeded: roleSeparation.independent_review_needed === true,
    persistentSplitNeeded: roleSeparation.persistent_split_needed === true,
    capabilityGapSummary: cleanText(adaptive.capability_gap_summary),
  }
}

function countTeamMembers(teamPayload: Record<string, unknown> | null | undefined): number {
  const team = asObject(teamPayload)
  const agents = asArray(team.agents)
  if (agents.length > 0) return agents.length
  const participants = asArray(team.participants)
  if (participants.length > 0) return participants.length
  const structure = asObject(team.structure_v2 || team.structure)
  const topology = asObject(structure.topology)
  const nodes = asArray(topology.nodes)
  if (nodes.length > 0) return nodes.length
  return 0
}

function detectPattern(teamPayload: Record<string, unknown> | null | undefined): string {
  const team = asObject(teamPayload)
  const interactionSpec = asObject(team.interaction_spec)
  const structure = asObject(team.structure_v2 || team.structure)
  const topology = asObject(structure.topology)
  return cleanText(
    interactionSpec.execution_pattern
    || interactionSpec.pattern
    || topology.pattern
    || structure.execution_pattern
    || team.execution_pattern,
  )
}

function shortTeamName(teamPayload: Record<string, unknown> | null | undefined, fallback: string): string {
  const team = asObject(teamPayload)
  return cleanText(team.team_name || team.display_name || team.title || fallback) || fallback
}

function friendlyMode(raw: unknown): string {
  const mode = cleanText(raw).toLowerCase()
  if (mode === 'single_compiled') return 'single-agent starter'
  if (mode === 'hybrid_sidecar') return 'hybrid sidecar'
  if (mode === 'multi_motif') return 'multi-agent motif'
  return cleanText(raw) || '-'
}

function friendlyLane(raw: unknown): string {
  const lane = cleanText(raw).toLowerCase()
  if (lane === 'fast') return 'fast lane'
  if (lane === 'work') return 'work lane'
  if (lane === 'deep') return 'deep lane'
  return cleanText(raw) || '-'
}

function buildSignalChip(key: string, value: unknown): SignalChip | null {
  const cleanKey = cleanText(key).toLowerCase()
  const num = Number(value)
  const asPct = (n: number) => `${Math.round(n * 100)}%`

  if (cleanKey === 'participant_pressure' && Number.isFinite(num)) {
    return { key, label: 'participant pressure', value: String(num), tone: num >= 4 ? 'bad' : num >= 2 ? 'warn' : 'neutral' }
  }
  if (cleanKey === 'decomposability_score' && Number.isFinite(num)) {
    return { key, label: 'decomposability', value: String(num), tone: num >= 1.8 ? 'warn' : 'neutral' }
  }
  if (cleanKey === 'augmentation_score' && Number.isFinite(num)) {
    return { key, label: 'augmentation', value: String(num), tone: num >= 1.2 ? 'warn' : 'good' }
  }
  if (cleanKey === 'role_separation_score' && Number.isFinite(num)) {
    return { key, label: 'role separation', value: String(num), tone: num >= 2.6 ? 'warn' : 'neutral' }
  }
  if (cleanKey === 'followup_burden_runs' && Number.isFinite(num)) {
    return { key, label: 'follow-up burden', value: String(num), tone: num >= 1 ? 'warn' : 'good' }
  }
  if (cleanKey === 'quality_gap_runs' && Number.isFinite(num)) {
    return { key, label: 'quality gap runs', value: String(num), tone: num >= 1 ? 'bad' : 'good' }
  }
  if (cleanKey === 'contradiction_pressure_runs' && Number.isFinite(num)) {
    return { key, label: 'contradiction pressure', value: String(num), tone: num >= 2 ? 'bad' : num >= 1 ? 'warn' : 'good' }
  }
  if (cleanKey === 'capability_gap_runs' && Number.isFinite(num)) {
    return { key, label: 'capability gap runs', value: String(num), tone: num >= 1 ? 'bad' : 'good' }
  }
  if (cleanKey === 'failure_streak' && Number.isFinite(num)) {
    return { key, label: 'failure streak', value: String(num), tone: num >= 1 ? 'bad' : 'good' }
  }
  if (cleanKey === 'last_quality_health_score' && Number.isFinite(num)) {
    return { key, label: 'quality health', value: asPct(num), tone: num < 0.55 ? 'bad' : num < 0.7 ? 'warn' : 'good' }
  }
  if (cleanKey === 'quality_health_score' && Number.isFinite(num)) {
    return { key, label: 'current quality', value: asPct(num), tone: num < 0.55 ? 'bad' : num < 0.7 ? 'warn' : 'good' }
  }
  if (cleanKey === 'quality_gap' && Number.isFinite(num)) {
    return { key, label: 'current quality gap', value: String(num), tone: num >= 2 ? 'bad' : num >= 1 ? 'warn' : 'good' }
  }
  if (cleanKey === 'followup_burden' && Number.isFinite(num)) {
    return { key, label: 'current follow-up', value: String(num), tone: num >= 1 ? 'warn' : 'good' }
  }
  if (cleanKey === 'contradiction_pressure' && Number.isFinite(num)) {
    return { key, label: 'current contradiction', value: String(num), tone: num >= 2 ? 'bad' : num >= 1 ? 'warn' : 'good' }
  }
  return null
}

function buildTeamPhase({
  activeCount,
  pendingCount,
  mode,
  teamStatus,
  pendingPattern,
  activePattern,
}: {
  activeCount: number
  pendingCount: number
  mode: string
  teamStatus: string
  pendingPattern: string
  activePattern: string
}) {
  const cleanMode = mode.toLowerCase()
  const cleanStatus = teamStatus.toLowerCase()
  const activeLooksSingle = activeCount <= 1 || activePattern.toLowerCase() === 'single' || cleanMode === 'single_compiled'
  const pendingLooksExpansion = pendingCount > 0 && pendingCount >= Math.max(2, activeCount)
  const activeLooksExpanded = activeCount >= 2 || cleanMode === 'hybrid_sidecar' || cleanMode === 'multi_motif' || activePattern.toLowerCase() === 'hybrid' || pendingPattern.toLowerCase() === 'hybrid'

  if (pendingLooksExpansion) {
    return {
      label: 'pending expansion',
      summary: 'Single-agent 결과를 바탕으로 team 확장안이 준비된 상태입니다.',
      tone: 'runStudioStatus--queued',
      stages: ['done', activeLooksSingle ? 'done' : 'active', 'active', activeLooksExpanded ? 'done' : 'upcoming'] as const,
    }
  }
  if (activeLooksExpanded || cleanStatus === 'active') {
    return {
      label: 'team active',
      summary: '확장된 team이 현재 실행 경로에 반영되어 있습니다.',
      tone: 'runStudioStatus--running',
      stages: ['done', 'done', 'done', 'active'] as const,
    }
  }
  if (activeLooksSingle) {
    return {
      label: 'single-agent starter',
      summary: 'chat은 단일 에이전트로 시작했고, 품질 신호가 커지면 team으로 확장됩니다.',
      tone: 'runStudioStatus--idle',
      stages: ['done', 'active', 'upcoming', 'upcoming'] as const,
    }
  }
  if (cleanStatus === 'none' && activeCount === 0) {
    return {
      label: 'no team materialized',
      summary: '아직 runtime team이 구체화되지 않았습니다.',
      tone: 'runStudioStatus--idle',
      stages: ['active', 'upcoming', 'upcoming', 'upcoming'] as const,
    }
  }
  return {
    label: cleanStatus || 'team state unknown',
    summary: 'Runtime team state가 일부만 보입니다. fallback/legacy 필드 여부를 확인하세요.',
    tone: 'runStudioStatus--queued',
    stages: ['done', 'upcoming', 'upcoming', 'upcoming'] as const,
  }
}

export default function TeamStatePanel({ summary, team, auditTimeline }: Props) {
  const teamConfig = team?.team_config || summary?.agent_team?.team_config || undefined
  const activeTeam = asObject(teamConfig?.active_team)
  const pendingTeam = asObject(teamConfig?.pending_team)
  const activeCount = countTeamMembers(activeTeam)
  const pendingCount = countTeamMembers(pendingTeam)
  const linked = auditTimeline?.linked_summary || null
  const taskInterpretation = asObject(summary?.current_run_skills?.task_interpretation)
  const executionMode = cleanText(linked?.execution_mode || taskInterpretation.execution_mode || taskInterpretation.executionMode)
  const executionLane = cleanText(linked?.execution_lane || taskInterpretation.execution_lane || taskInterpretation.executionLane)
  const executionReasons = asArray<string>(linked?.execution_mode_reasons).map((entry) => cleanText(entry)).filter(Boolean)
  const modeSignals = asObject(linked?.execution_mode_signals)
  const qualitySignals = asObject(linked?.execution_quality_signals)
  const activePattern = detectPattern(activeTeam)
  const pendingPattern = detectPattern(pendingTeam)
  const activeAdaptiveMeta = parseAdaptiveExpansionMeta(activeTeam)
  const pendingAdaptiveMeta = parseAdaptiveExpansionMeta(pendingTeam)
  const phase = buildTeamPhase({
    activeCount,
    pendingCount,
    mode: executionMode,
    teamStatus: cleanText(teamConfig?.status || ''),
    activePattern,
    pendingPattern,
  })

  const signalChips = useMemo(() => {
    const chips: SignalChip[] = []
    const preferredKeys = [
      'participant_pressure',
      'decomposability_score',
      'augmentation_score',
      'role_separation_score',
      'followup_burden_runs',
      'quality_gap_runs',
      'contradiction_pressure_runs',
      'capability_gap_runs',
      'failure_streak',
      'last_quality_health_score',
      'followup_burden',
      'quality_gap',
      'contradiction_pressure',
      'quality_health_score',
    ]
    preferredKeys.forEach((key) => {
      const raw = key in modeSignals ? modeSignals[key] : qualitySignals[key]
      const chip = buildSignalChip(key, raw)
      if (chip) chips.push(chip)
    })
    return chips
  }, [modeSignals, qualitySignals])

  const stages = [
    { label: 'Chat start', state: phase.stages[0] },
    { label: 'Single starter', state: phase.stages[1] },
    { label: 'Pending expansion', state: phase.stages[2] },
    { label: 'Team applied', state: phase.stages[3] },
  ]

  return (
    <section className="card runStudioPanel runStudioTeamStatePanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3 style={{ margin: 0 }}>Team State</h3>
          <div className="muted">Starter single-agent에서 pending expansion, applied team까지의 현재 상태를 한 카드에서 보여줍니다.</div>
        </div>
        <div className="runStudioMetaRow">
          <span className={`pill runStudioStatus ${phase.tone}`}>{phase.label}</span>
          {executionLane && <span className="pill">lane: {friendlyLane(executionLane)}</span>}
          {executionMode && <span className="pill">mode: {friendlyMode(executionMode)}</span>}
          {cleanText(teamConfig?.status) && <span className="pill">config: {cleanText(teamConfig?.status)}</span>}
          {cleanText(teamConfig?.proposal_mode) && <span className="pill">proposal: {cleanText(teamConfig?.proposal_mode)}</span>}
        </div>
      </div>

      <div className="muted" style={{ marginBottom: 10 }}>
        {phase.summary}
        {executionLane ? ` 현재 turn은 ${friendlyLane(executionLane)} 기준으로 라우팅되었습니다.` : ''}
      </div>

      <div className="runStudioStageGrid" style={{ marginBottom: 12 }}>
        {stages.map((stage) => (
          <div key={stage.label} className={`runStudioStageCard runStudioStageCard--${stage.state}`}>
            <div className="runStudioStageEyebrow">stage</div>
            <div className="runStudioStageTitle">{stage.label}</div>
          </div>
        ))}
      </div>

      <div className="runStudioAgentCardGrid" style={{ marginBottom: 12 }}>
        <section className="runStudioAgentCard">
          <div className="runStudioAgentCardHeader">
            <div>
              <div className="runStudioAgentCardTitle">Active contract</div>
              <div className="muted">현재 runtime에 반영된 팀 구성</div>
            </div>
            <div className="runStudioMetaRow">
              <span className="pill">members: {activeCount}</span>
              {activePattern && <span className="pill">pattern: {humanizeExecutionPattern(activePattern)}</span>}
            </div>
          </div>
          <div className="muted">team: {shortTeamName(activeTeam, activeCount > 0 ? 'active team' : 'none')}</div>
          <div className="muted">composition: {cleanText(activeTeam.composition_mode || teamConfig?.composition_mode || '-') || '-'}</div>
          {activeCount === 1 && <div className="muted">현재는 단일 에이전트 starter 상태로 보입니다.</div>}
          {activeCount >= 2 && <div className="muted">현재는 확장된 팀이 실제 runtime 경로에 올라와 있습니다.</div>}
        </section>

        <section className="runStudioAgentCard">
          <div className="runStudioAgentCardHeader">
            <div>
              <div className="runStudioAgentCardTitle">Pending contract</div>
              <div className="muted">검토/적용 전 대기 중인 확장안</div>
            </div>
            <div className="runStudioMetaRow">
              <span className="pill">members: {pendingCount}</span>
              {pendingPattern && <span className="pill">pattern: {humanizeExecutionPattern(pendingPattern)}</span>}
            </div>
          </div>
          <div className="muted">team: {shortTeamName(pendingTeam, pendingCount > 0 ? 'pending team' : 'none')}</div>
          <div className="muted">proposal mode: {cleanText(pendingTeam.proposal_mode || teamConfig?.proposal_mode || '-') || '-'}</div>
          {pendingCount > 0
            ? <div className="muted">현재 pending team이 있으므로 Telegram에서 apply / refine 흐름과 연결됩니다.</div>
            : <div className="muted">아직 pending expansion draft는 없습니다.</div>}
        </section>
      </div>

      {(pendingAdaptiveMeta || activeAdaptiveMeta) && (
        <section className="runStudioAgentCard" style={{ marginBottom: 12 }}>
          <div className="runStudioAgentCardHeader">
            <div>
              <div className="runStudioAgentCardTitle">Strategy controller</div>
              <div className="muted">team 확장 전에 context augmentation과 role separation을 어떻게 비교했는지 보여줍니다.</div>
            </div>
          </div>
          {pendingAdaptiveMeta && (
            <div style={{ marginBottom: activeAdaptiveMeta ? 10 : 0 }}>
              <div className="runStudioMetaRow" style={{ marginBottom: 6 }}>
                <span className="pill">pending recommendation: {pendingAdaptiveMeta.recommendation || '-'}</span>
                {pendingAdaptiveMeta.augmentationScore !== null && <span className="pill">augmentation: {pendingAdaptiveMeta.augmentationScore}</span>}
                {pendingAdaptiveMeta.roleSeparationScore !== null && <span className="pill">role separation: {pendingAdaptiveMeta.roleSeparationScore}</span>}
                {pendingAdaptiveMeta.independentReviewNeeded && <span className="pill">independent review</span>}
                {pendingAdaptiveMeta.persistentSplitNeeded && <span className="pill">persistent split</span>}
              </div>
              {(pendingAdaptiveMeta.roleSeparationReasons.length > 0 || pendingAdaptiveMeta.augmentationReasons.length > 0 || pendingAdaptiveMeta.rationale.length > 0 || pendingAdaptiveMeta.capabilityGapSummary) && (
                <div className="muted">
                  {pendingAdaptiveMeta.rationale.length > 0 && <div><b>pending rationale:</b> {pendingAdaptiveMeta.rationale.join(', ')}</div>}
                  {pendingAdaptiveMeta.roleSeparationReasons.length > 0 && <div><b>role separation:</b> {pendingAdaptiveMeta.roleSeparationReasons.join(', ')}</div>}
                  {pendingAdaptiveMeta.augmentationReasons.length > 0 && <div><b>augmentation:</b> {pendingAdaptiveMeta.augmentationReasons.join(', ')}</div>}
                  {pendingAdaptiveMeta.capabilityGapSummary && <div><b>gaps:</b> {pendingAdaptiveMeta.capabilityGapSummary}</div>}
                </div>
              )}
            </div>
          )}
          {activeAdaptiveMeta && (
            <div>
              <div className="runStudioMetaRow" style={{ marginBottom: 6 }}>
                <span className="pill">active recommendation: {activeAdaptiveMeta.recommendation || '-'}</span>
                {activeAdaptiveMeta.augmentationScore !== null && <span className="pill">augmentation: {activeAdaptiveMeta.augmentationScore}</span>}
                {activeAdaptiveMeta.roleSeparationScore !== null && <span className="pill">role separation: {activeAdaptiveMeta.roleSeparationScore}</span>}
              </div>
              {(activeAdaptiveMeta.roleSeparationReasons.length > 0 || activeAdaptiveMeta.augmentationReasons.length > 0 || activeAdaptiveMeta.rationale.length > 0) && (
                <div className="muted">
                  {activeAdaptiveMeta.rationale.length > 0 && <div><b>active rationale:</b> {activeAdaptiveMeta.rationale.join(', ')}</div>}
                  {activeAdaptiveMeta.roleSeparationReasons.length > 0 && <div><b>role separation:</b> {activeAdaptiveMeta.roleSeparationReasons.join(', ')}</div>}
                  {activeAdaptiveMeta.augmentationReasons.length > 0 && <div><b>augmentation:</b> {activeAdaptiveMeta.augmentationReasons.join(', ')}</div>}
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {(signalChips.length > 0 || executionReasons.length > 0) && (
        <section className="runStudioAgentCard">
          <div className="runStudioAgentCardHeader">
            <div>
              <div className="runStudioAgentCardTitle">Execution signals</div>
              <div className="muted">최근 실행에서 관측된 pressure와 controller 근거입니다.</div>
            </div>
          </div>
          {signalChips.length > 0 && (
            <div className="runStudioMetaRow" style={{ marginBottom: executionReasons.length > 0 ? 8 : 0 }}>
              {signalChips.map((chip) => (
                <span key={chip.key} className={`pill runStudioSignalPill runStudioSignalPill--${chip.tone}`}>{chip.label}: {chip.value}</span>
              ))}
            </div>
          )}
          {executionReasons.length > 0 && (
            <div className="muted">
              <b>Rationale:</b> {executionReasons.join(', ')}
            </div>
          )}
        </section>
      )}
    </section>
  )
}
