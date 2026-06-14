import React, { useState } from 'react'
import { api } from '../../api'
import { type TeamSelectionCandidateFeature, type TeamSelectionDataset, type TeamSelectionDatasetRow } from './types'

type Props = {
  threadId?: string | null
  teamSelection: TeamSelectionDataset | null
  onLoadDetail?: () => void
  onActionComplete?: () => void
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

const WORK_DEPTH_PRESETS: Record<string, Record<string, unknown>> = {
  instant: {
    work_depth: 'instant',
    work_depth_label: 'Single Agent',
    work_mode: 'quick_answer',
    label: 'Quick Answer',
    context_depth: 'minimal',
    loop_budget: 0,
    stop_condition: 'answer_ready',
    review_policy: 'none',
    memory_mode: 'none',
    goc_mode: 'optional',
  },
  team: {
    work_depth: 'team',
    work_depth_label: 'Agent Team',
    work_mode: 'team_review',
    label: 'Team Review',
    context_depth: 'projected',
    loop_budget: 1,
    stop_condition: 'review_complete',
    review_policy: 'required',
    memory_mode: 'package',
    goc_mode: 'recommended',
  },
  loop: {
    work_depth: 'loop',
    work_depth_label: 'Agent Loop',
    work_mode: 'project_task',
    label: 'Project Task',
    context_depth: 'workspace',
    loop_budget: 3,
    stop_condition: 'stage_complete_or_approval_required',
    review_policy: 'required',
    memory_mode: 'package',
    goc_mode: 'required',
  },
}

function depthForWorkMode(mode: unknown): string {
  const clean = cleanText(mode).toLowerCase()
  if (clean === 'quick_answer' || clean === 'assisted_task' || clean === 'instant' || clean === 'single_agent') return 'instant'
  if (clean === 'team_review' || clean === 'team' || clean === 'agent_team') return 'team'
  if (clean === 'project_task' || clean === 'research_campaign' || clean === 'customize' || clean === 'loop' || clean === 'agent_loop') return 'loop'
  return ''
}

function normalizeWorkMode(value: unknown): Record<string, unknown> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const row = value as Record<string, unknown>
    const depth = cleanText(row.work_depth || row.depth || depthForWorkMode(row.work_mode || row.mode) || 'team') || 'team'
    const preset = WORK_DEPTH_PRESETS[depth] || WORK_DEPTH_PRESETS.team
    const mode = cleanText(row.work_mode || row.mode || preset.work_mode) || cleanText(preset.work_mode)
    return { ...preset, ...row, work_depth: depth, work_mode: mode }
  }
  const depth = cleanText(depthForWorkMode(value) || value || 'team') || 'team'
  const preset = WORK_DEPTH_PRESETS[depth] || WORK_DEPTH_PRESETS.team
  return { ...preset }
}

function workModeContextPolicy(workMode: Record<string, unknown>, base: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    ...base,
    work_depth: workMode.work_depth,
    work_mode: workMode.work_mode,
    context_depth: workMode.context_depth,
    loop_budget: workMode.loop_budget,
    stop_condition: workMode.stop_condition,
    review_policy: workMode.review_policy,
    memory_mode: workMode.memory_mode,
    goc_mode: workMode.goc_mode,
  }
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



function renderUserIntent(candidate: TeamSelectionCandidateFeature | null | undefined) {
  const intent = candidate?.user_orchestration_intent
  const advisory = candidate?.skeleton_advisory
  const teamIntent = cleanText(intent?.team_intent || advisory?.user_team_intent || '')
  if (!teamIntent || teamIntent === 'neutral') return null
  const style = cleanText(intent?.team_style || advisory?.user_team_style || 'team')
  const required = intent?.required_roles || advisory?.missing_user_required_roles || []
  return (
    <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
      <span className="pill">user team: {teamIntent}</span>
      {style && <span className="pill">style: {style}</span>}
      {typeof advisory?.user_intent_match === 'boolean' && <span className="pill">intent: {advisory.user_intent_match ? 'matched' : 'mismatch'}</span>}
      {required.length > 0 && <span className="pill">user roles: {required.join(', ')}</span>}
      {typeof advisory?.user_requested_overhead_discount === 'number' && advisory.user_requested_overhead_discount > 0 && (
        <span className="pill">user-requested overhead</span>
      )}
    </div>
  )
}



function renderWorkMode(workMode: any) {
  if (!workMode) return null
  const mode = cleanText(workMode.work_mode || workMode.mode || '')
  if (!mode) return null
  return (
    <div className="runStudioWarning" style={{ marginTop: 8 }}>
      <div><b>Task Depth</b> <span className="muted">3 entry points: single agent, agent team, or bounded loop.</span></div>
      <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
        {workMode.work_depth && <span className="pill">depth: {cleanText(workMode.work_depth)}</span>}
        <span className="pill">preset: {mode}</span>
        {workMode.context_depth && <span className="pill">context: {cleanText(workMode.context_depth)}</span>}
        {workMode.loop_budget !== undefined && workMode.loop_budget !== null && <span className="pill">loop: {cleanText(workMode.loop_budget)}</span>}
        {workMode.stop_condition && <span className="pill">stop: {cleanText(workMode.stop_condition)}</span>}
        {workMode.review_policy && <span className="pill">review: {cleanText(workMode.review_policy)}</span>}
        {workMode.memory_mode && <span className="pill">memory: {cleanText(workMode.memory_mode)}</span>}
        {workMode.goc_mode && <span className="pill">GoC: {cleanText(workMode.goc_mode)}</span>}
      </div>
      {(workMode.reason_codes || []).length > 0 && <div className="muted" style={{ marginTop: 4 }}>mode signals: {(workMode.reason_codes || []).join(', ')}</div>}
    </div>
  )
}

function renderMemoryImport(memory: any) {
  if (!memory || memory.import_intent === 'none') return null
  return (
    <div className="runStudioWarning" style={{ marginTop: 8 }}>
      <div><b>Imported memory package</b> <span className="muted">({cleanText(memory.mode || 'snapshot')} · {cleanText(memory.projection_profile || 'general')})</span></div>
      <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
        <span className="pill">memory: {cleanText(memory.import_intent || 'suggested')}</span>
        <span className="pill">topic: {cleanText(memory.topic || 'current_topic')}</span>
        <span className="pill">scope: {cleanText(memory.scope || 'project')}</span>
        <span className="pill">target: {cleanText(memory.target_team || 'general')}</span>
        <span className="pill">prev: {cleanText(memory.previous_result_policy || 'optional')}</span>
        {memory?.permissions?.read_only !== false && <span className="pill">read-only</span>}
        {memory?.permissions?.allow_propose_update !== false && <span className="pill">updates by proposal</span>}
      </div>
      {(memory.reason_codes || []).length > 0 && <div className="muted" style={{ marginTop: 4 }}>reason: {(memory.reason_codes || []).join(', ')}</div>}
    </div>
  )
}

function renderTaskAttempt(plan: any) {
  if (!plan) return null
  const memory = plan.memory_import || null
  const policy = plan.context_policy || {}
  const show = cleanText(plan.run_mode || 'new') !== 'new' || cleanText(plan.target_team || 'general') !== 'general' || memory?.import_intent !== 'none'
  if (!show) return null
  return (
    <div className="runStudioWarning" style={{ marginTop: 8 }}>
      <div><b>Task Attempt Studio</b> <span className="muted">branch/retry context should be controlled in GoC, not by append-only chat tail.</span></div>
      <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
        <span className="pill">run: {cleanText(plan.run_mode || 'new')}</span>
        {plan.retry_reason && <span className="pill">reason: {plan.retry_reason}</span>}
        <span className="pill">target: {cleanText(plan.target_team || 'general')}</span>
        <span className="pill">prev result: {cleanText(plan.previous_result_policy || 'optional')}</span>
        {plan.goc?.recommended && <span className="pill">open in GoC</span>}
      </div>
      <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
        {policy.include_original_user_request && <span className="pill">original request</span>}
        {policy.include_user_feedback && <span className="pill">user feedback</span>}
        {policy.include_previous_result ? <span className="pill">previous result included</span> : <span className="pill">previous result isolated</span>}
        {policy.include_previous_result_summary && <span className="pill">previous summary only</span>}
        {policy.include_memory_package && <span className="pill">memory package</span>}
        {!policy.include_full_chat_tail && <span className="pill">no full chat tail</span>}
      </div>
      {(plan.reason_codes || []).length > 0 && <div className="muted" style={{ marginTop: 4 }}>attempt signals: {(plan.reason_codes || []).join(', ')}</div>}
      {renderMemoryImport(memory)}
    </div>
  )
}

function renderSkeletonAdvisory(candidate: TeamSelectionCandidateFeature | null | undefined) {
  const advisory = candidate?.skeleton_advisory
  if (!advisory) return null
  const gaps = advisory.capacity_gaps || []
  const warnings = advisory.warnings || []
  return (
    <div className="runStudioWarning" style={{ marginTop: 8 }}>
      <div><b>Skeleton advisory</b> <span className="muted">({cleanText(advisory.status || 'unknown')}{advisory.advisory_mode ? ` · ${advisory.advisory_mode}` : ''})</span></div>
      <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
        {advisory.utility_label && <span className="pill">fit: {advisory.utility_label}</span>}
        {advisory.debt_label && <span className="pill">debt: {advisory.debt_label}</span>}
        {advisory.frontier_needed && <span className="pill">frontier: {advisory.frontier_needed}</span>}
        {typeof advisory.fused_utility === 'number' && <span className="pill">fused: {scoreText(advisory.fused_utility)}</span>}
        {typeof advisory.learned_delta === 'number' && <span className="pill">Δlearned: {scoreText(advisory.learned_delta)}</span>}
        {typeof advisory.user_intent_bonus === 'number' && advisory.user_intent_bonus !== 0 && <span className="pill">user intent Δ: {scoreText(advisory.user_intent_bonus)}</span>}
      </div>
      {gaps.length > 0 && <div className="muted" style={{ marginTop: 4 }}>capacity gaps: {gaps.join(', ')}</div>}
      {warnings.length > 0 && <div className="muted" style={{ marginTop: 4 }}>warnings: {warnings.join(', ')}</div>}
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
      {renderUserIntent(candidate)}
      {renderWorkMode(candidate?.work_mode || candidate?.task_attempt_plan?.work_mode)}
      {renderTaskAttempt(candidate?.task_attempt_plan)}
      {renderMemoryImport(candidate?.memory_import_intent)}
      {renderSkeletonAdvisory(candidate)}
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


function candidateTargetTeam(candidate: TeamSelectionCandidateFeature | null | undefined, fallback: string): string {
  const target = cleanText(candidate?.target_team || candidate?.task_attempt_plan?.target_team || fallback)
  return target || 'general'
}

function taskIdForRow(row: TeamSelectionDatasetRow | null | undefined): string | null {
  const fromPlan = cleanText(row?.task_attempt_plan?.task_id)
  if (fromPlan) return fromPlan
  const eventId = cleanText(row?.event_id)
  if (eventId) return `trace_${eventId}`
  return null
}

function attemptIdForRow(row: TeamSelectionDatasetRow | null | undefined): string | null {
  return cleanText(row?.task_attempt_plan?.attempt_id) || null
}

function buildAttemptBody({
  threadId,
  row,
  candidate,
  runMode,
  workModeOverride,
}: {
  threadId: string
  row: TeamSelectionDatasetRow
  candidate: TeamSelectionCandidateFeature | null | undefined
  runMode: 'retry' | 'branch' | 'parallel_branch' | 'new'
  workModeOverride?: Record<string, unknown> | null
}): Record<string, unknown> {
  const plan: any = row.task_attempt_plan || {}
  const memory = candidate?.memory_import_intent || row.memory_import_intent || plan.memory_import || null
  const workMode = normalizeWorkMode(workModeOverride || candidate?.work_mode || row.work_mode || plan.work_mode || null)
  const taskId = taskIdForRow(row) || undefined
  const parentAttemptId = cleanText(plan.attempt_id || row.run_id || '') || undefined
  return {
    thread_id: threadId,
    task_id: taskId,
    parent_attempt_id: parentAttemptId,
    run_id: row.run_id || undefined,
    run_mode: runMode,
    target_team: candidateTargetTeam(candidate, cleanText(plan.target_team || 'general')),
    previous_result_policy: cleanText(plan.previous_result_policy || (runMode === 'new' ? 'optional' : 'exclude')),
    work_mode: workMode || undefined,
    review_policy: cleanText(workMode.review_policy || ''),
    task_text: row.task_text || undefined,
    context_policy: workModeContextPolicy(workMode, plan.context_policy || {
      include_original_user_request: true,
      include_user_feedback: true,
      include_previous_result: runMode === 'new',
      include_full_chat_tail: false,
      include_memory_package: Boolean(memory && (memory as any).import_intent !== 'none'),
    }),
    memory_import: memory || undefined,
    memory_projection_profile: cleanText((memory as any)?.projection_profile || workMode.memory_projection_profile || candidate?.memory_import_intent?.projection_profile || 'general'),
    selected_blueprint_id: cleanText(candidate?.template_id || row.selected_blueprint_id || ''),
    candidate_snapshot: candidate || undefined,
    recommendation_event_id: row.event_id || undefined,
    source_run_id: row.run_id || undefined,
    meta: {
      source: 'goc_team_recommendation_panel',
      recommendation_alignment: row.recommendation_alignment || null,
      selected_candidate_rank: row.selected_candidate_rank || null,
    },
  }
}

function WorkModeSelector({
  value,
  onChange,
}: {
  value: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
}) {
  const depth = cleanText(value.work_depth || depthForWorkMode(value.work_mode) || 'team') || 'team'
  const setMode = (nextDepth: string) => onChange(normalizeWorkMode({ ...WORK_DEPTH_PRESETS[nextDepth], explicit: true, reason_codes: ['goc_work_depth_selector'] }))
  const patch = (key: string, nextValue: unknown) => onChange(normalizeWorkMode({ ...value, [key]: nextValue, explicit: true, reason_codes: ['goc_work_depth_selector'] }))
  return (
    <div className="runStudioWarning" style={{ marginTop: 8 }}>
      <div><b>Task Depth selector</b> <span className="muted">Choose one of three user-facing depths; internal presets stay available as templates.</span></div>
      <div className="runStudioMetaRow" style={{ marginTop: 8 }}>
        <label className="muted">
          depth{' '}
          <select value={depth} onChange={(event) => setMode(event.target.value)}>
            {Object.keys(WORK_DEPTH_PRESETS).map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label className="muted">
          loop{' '}
          <input
            style={{ width: 90 }}
            value={cleanText(value.loop_budget ?? '')}
            onChange={(event) => patch('loop_budget', /^\d+$/.test(event.target.value) ? Number(event.target.value) : event.target.value)}
          />
        </label>
        <label className="muted">
          stop{' '}
          <input style={{ width: 180 }} value={cleanText(value.stop_condition || '')} onChange={(event) => patch('stop_condition', event.target.value)} />
        </label>
        <label className="muted">
          review{' '}
          <select value={cleanText(value.review_policy || 'optional')} onChange={(event) => patch('review_policy', event.target.value)}>
            {['none', 'optional', 'required', 'stage_gate'].map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label className="muted">
          memory{' '}
          <select value={cleanText(value.memory_mode || 'light')} onChange={(event) => patch('memory_mode', event.target.value)}>
            {['none', 'light', 'package', 'structured'].map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
      </div>
      <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
        <span className="pill">context: {cleanText(value.context_depth || '-')}</span>
        <span className="pill">GoC: {cleanText(value.goc_mode || '-')}</span>
        <span className="pill">bounded cycles only</span>
      </div>
    </div>
  )
}

function TaskAttemptActionPanel({
  threadId,
  row,
  selected,
  topRecommended,
  onActionComplete,
}: {
  threadId?: string | null
  row: TeamSelectionDatasetRow | null
  selected: TeamSelectionCandidateFeature | null | undefined
  topRecommended: TeamSelectionCandidateFeature | null | undefined
  onActionComplete?: () => void
}) {
  const [busyAction, setBusyAction] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [selectedWorkMode, setSelectedWorkMode] = useState<Record<string, unknown>>(() => normalizeWorkMode(selected?.work_mode || row?.work_mode || row?.task_attempt_plan?.work_mode || null))

  const run = async (label: string, work: () => Promise<any>) => {
    setBusyAction(label)
    setMessage('')
    setError('')
    try {
      const result = await work()
      const attemptId = cleanText(result?.attempt?.attempt_id || result?.attempt_id || '')
      setMessage(attemptId ? `${label} recorded: ${attemptId}` : `${label} recorded.`)
      onActionComplete?.()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err || 'Action failed'))
    } finally {
      setBusyAction('')
    }
  }

  const cleanThreadId = cleanText(threadId)
  if (!cleanThreadId || !row) return null
  const currentAttemptId = attemptIdForRow(row)
  const taskId = taskIdForRow(row)
  const canUseExistingAttempt = Boolean(currentAttemptId)

  return (
    <div className="runStudioWarning" style={{ marginBottom: 10 }}>
      <div><b>Task Attempt write actions</b> <span className="muted">Record branch/retry/launch/promote decisions as structured GoC control-plane state.</span></div>
      <WorkModeSelector value={selectedWorkMode} onChange={setSelectedWorkMode} />
      <div className="runStudioMetaRow" style={{ marginTop: 8 }}>
        <button
          disabled={Boolean(busyAction)}
          onClick={() => run('Retry attempt', () => api.createTaskAttempt(buildAttemptBody({ threadId: cleanThreadId, row, candidate: selected, runMode: 'retry', workModeOverride: selectedWorkMode })))}
        >
          Create retry
        </button>
        <button
          disabled={Boolean(busyAction)}
          onClick={() => run('Branch attempt', () => api.createTaskAttempt(buildAttemptBody({ threadId: cleanThreadId, row, candidate: topRecommended || selected, runMode: 'branch', workModeOverride: selectedWorkMode })))}
        >
          Create branch from top team
        </button>
        <button
          disabled={Boolean(busyAction)}
          onClick={() => run('Create + launch branch', async () => {
            const created = await api.createTaskAttempt(buildAttemptBody({ threadId: cleanThreadId, row, candidate: topRecommended || selected, runMode: 'branch', workModeOverride: selectedWorkMode }))
            const attemptId = cleanText(created?.attempt?.attempt_id)
            if (!attemptId) return created
            return api.launchTaskAttempt(attemptId, { actor: 'goc', overrides: { source: 'team_recommendation_panel' } })
          })}
        >
          Create + launch
        </button>
        <button
          disabled={Boolean(busyAction) || !canUseExistingAttempt}
          title={canUseExistingAttempt ? 'Save the selected Work Mode/depth onto the current attempt.' : 'No attempt_id was recorded in the latest trace.'}
          onClick={() => currentAttemptId && run('Save work mode', () => api.updateTaskAttempt(currentAttemptId, {
            actor: 'goc',
            work_mode: selectedWorkMode,
            review_policy: cleanText(selectedWorkMode.review_policy || ''),
            context_policy: workModeContextPolicy(selectedWorkMode, (row.task_attempt_plan as any)?.context_policy || {}),
            meta: { source: 'goc_work_mode_selector' },
          }))}
        >
          Save work mode
        </button>
        <button
          disabled={Boolean(busyAction) || !canUseExistingAttempt}
          title={canUseExistingAttempt ? 'Launch the attempt recorded in the runtime trace.' : 'No attempt_id was recorded in the latest trace.'}
          onClick={() => currentAttemptId && run('Launch current attempt', () => api.launchTaskAttempt(currentAttemptId, { actor: 'goc' }))}
        >
          Launch current
        </button>
        <button
          disabled={Boolean(busyAction) || !canUseExistingAttempt}
          title={canUseExistingAttempt ? 'Promote the attempt recorded in the runtime trace.' : 'No attempt_id was recorded in the latest trace.'}
          onClick={() => currentAttemptId && run('Promote current attempt', () => api.promoteTaskAttempt(currentAttemptId, { actor: 'goc', summary: 'Promoted from TeamRecommendationPanel', supersede_siblings: true }))}
        >
          Promote current
        </button>
        <button
          disabled={Boolean(busyAction) || !canUseExistingAttempt}
          onClick={() => currentAttemptId && run('Archive current attempt', () => api.archiveTaskAttempt(currentAttemptId, { actor: 'goc', reason: 'Archived from TeamRecommendationPanel' }))}
        >
          Archive current
        </button>
      </div>
      <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
        {taskId && <span className="pill">task: {taskId}</span>}
        {currentAttemptId ? <span className="pill">current attempt: {currentAttemptId}</span> : <span className="pill">current attempt: not recorded</span>}
        <span className="pill">selected depth: {cleanText(selectedWorkMode.work_depth || '-')}</span>
        {busyAction && <span className="pill">working: {busyAction}</span>}
      </div>
      {message && <div className="muted" style={{ marginTop: 6 }}>{message}</div>}
      {error && <div className="runStudioWarning" style={{ marginTop: 8 }}><b>Action failed.</b> {error}</div>}
    </div>
  )
}

export default function TeamRecommendationPanel({
  threadId,
  teamSelection,
  onLoadDetail,
  onActionComplete,
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
            {Object.entries((teamSelection?.selection_outcome_summary as any)?.advisory_status_counts || {}).map(([status, count]) => (
              <span key={`advisory:${status}`} className="pill">advisory {status}: {String(count)}</span>
            ))}
            {Object.entries((teamSelection?.selection_outcome_summary as any)?.attempt_run_mode_counts || {}).map(([mode, count]) => (
              <span key={`attempt:${mode}`} className="pill">attempt {mode}: {String(count)}</span>
            ))}
            {Object.entries((teamSelection?.selection_outcome_summary as any)?.work_mode_counts || {}).map(([mode, count]) => (
              <span key={`work-mode:${mode}`} className="pill">work mode {mode}: {String(count)}</span>
            ))}
            {Object.entries((teamSelection?.selection_outcome_summary as any)?.work_mode_review_policy_counts || {}).map(([policy, count]) => (
              <span key={`work-review:${policy}`} className="pill">review {policy}: {String(count)}</span>
            ))}
            {Object.entries((teamSelection?.selection_outcome_summary as any)?.memory_import_profile_counts || {}).map(([profile, count]) => (
              <span key={`memory:${profile}`} className="pill">memory {profile}: {String(count)}</span>
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
                {renderWorkMode(latest.work_mode || latest.task_attempt_plan?.work_mode)}
                {renderTaskAttempt(latest.task_attempt_plan)}
                {renderMemoryImport(latest.memory_import_intent)}
                {latest.training_eligible === false && (
                  <div className="runStudioWarning" style={{ marginBottom: 8 }}>
                    <b>Excluded from training.</b> {(latest.exclusion_reasons || []).join(', ') || 'Unknown reason'}
                  </div>
                )}
                <TaskAttemptActionPanel
                  threadId={threadId}
                  row={latest}
                  selected={selected}
                  topRecommended={topRecommended}
                  onActionComplete={onActionComplete || onLoadDetail}
                />
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
