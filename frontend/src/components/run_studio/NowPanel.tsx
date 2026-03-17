import React from 'react'
import {
  type CheckpointProjection,
  type CollaborationProjection,
  type OrchestrationProjection,
  type RunStudioAgentTeam,
  type RunStudioSummary,
  type TeamViewProjection,
  type ControlPlaneSummaryProjection,
} from './types'

type Props = {
  summary: RunStudioSummary | null
  controlPlaneSummary?: ControlPlaneSummaryProjection | null
  team?: RunStudioAgentTeam | null
  teamView?: TeamViewProjection | null
  orchestration?: OrchestrationProjection | null
  collaboration?: CollaborationProjection | null
  checkpoints?: CheckpointProjection | null
}

function statusClass(status: string): string {
  const clean = status.trim().toLowerCase()
  if (clean === 'running') return 'runStudioStatus--running'
  if (clean === 'queued') return 'runStudioStatus--queued'
  if (clean === 'blocked' || clean === 'error') return 'runStudioStatus--blocked'
  if (clean === 'done') return 'runStudioStatus--done'
  return 'runStudioStatus--idle'
}

export default function NowPanel({
  summary,
  team,
  teamView,
  orchestration,
  collaboration,
  checkpoints,
  controlPlaneSummary,
}: Props) {
  const now = summary?.now
  const task = now?.task
  const state = now?.state
  const authority = state?.runtime_authority || summary?.runtime_authority || summary?.current_run_skills?.runtime_authority
  const status = String(state?.current_run_status || state?.run_status || 'idle')
  const blocked = Boolean(state?.current_blocked ?? state?.blocked)
  const blockedReason = String(state?.current_blocked_reason || state?.blocked_reason || '').trim()
  const pendingApproval = Boolean(state?.current_pending_approval ?? state?.pending_approval)
  const pendingApprovalCount = Number(state?.current_pending_approval_count ?? state?.pending_approval_count ?? 0)
  const stepStatusCounts = state?.current_run_step_status_counts || state?.step_status_counts || {}
  const globalStepStatusCounts = state?.step_status_counts || {}
  const stepCount = Object.values(stepStatusCounts).reduce((acc, value) => acc + Number(value || 0), 0)
  const staleQueuedStepCount = Number(state?.stale_queued_step_count || 0)
  const currentRunId = String(state?.current_run_id || '').trim()
  const currentRunInactive = Boolean(state?.current_run_inactive)
  const mode = controlPlaneSummary?.mode || String(authority?.mode || state?.mode || summary?.mode || 'standalone')
  const degradedMode = controlPlaneSummary?.degradedMode ?? Boolean(authority?.degraded_mode ?? state?.degraded_mode ?? summary?.degraded_mode)
  const fallbackReason = controlPlaneSummary?.fallbackReason || String(authority?.fallback_reason || state?.fallback_reason || summary?.fallback_reason || '').trim()
  const planSource = controlPlaneSummary?.planSource || String(authority?.plan_source || state?.plan_source || summary?.plan_source || 'local')
  const contextSource = controlPlaneSummary?.contextSource || String(authority?.context_source || state?.context_source || summary?.context_source || 'local')
  const teamSource = controlPlaneSummary?.teamSource || String(
    authority?.conversation_team_source || state?.conversation_team_source || summary?.conversation_team_source || 'local',
  )
  const skillSource = controlPlaneSummary?.skillSource || String(
    authority?.skill_catalog_source || state?.skill_catalog_source || summary?.skill_catalog_source || 'local',
  )
  const scopeProjection = summary?.current_run_skills?.scope_projection || summary?.scope_projection
  const legacyTeamItems = team?.items || []
  const runtimeTeamCount = controlPlaneSummary?.runtimeAgentCount ?? teamView?.count ?? legacyTeamItems.filter((item) => String(item.source || '') === 'runtime_snapshot').length
  const collaborationCount = controlPlaneSummary?.collaborationCount ?? collaboration?.count ?? collaboration?.items?.length ?? 0
  const checkpointCount = controlPlaneSummary?.checkpointCount ?? Number(checkpoints?.counts?.total || checkpoints?.items?.length || 0)
  const scopeMode = String(controlPlaneSummary?.scopeMode || scopeProjection?.context_runtime_mode || "shared_memory")
  const scopeCount = Number(controlPlaneSummary?.scopeCount || scopeProjection?.count || 0)
  const legacyContextPackCount = Number(controlPlaneSummary?.legacyContextPackCount || scopeProjection?.legacy_context_pack_count || 0)
  const legacyContextPacksEnabled = Boolean(controlPlaneSummary?.legacyContextPacksEnabled || scopeProjection?.legacy_context_packs_enabled)
  const supervisorEnabled = controlPlaneSummary?.supervisorEnabled ?? Boolean(
    orchestration?.supervisor_enabled ||
    orchestration?.supervisor_mode ||
    orchestration?.supervisor_runtime?.interaction_mode ||
    orchestration?.supervisor_runtime?.mode ||
    orchestration?.supervisor_runtime?.instance_id ||
    orchestration?.supervisor_edges?.length,
  )

  let executionHint = 'No execution step detected yet'
  if (pendingApproval) {
    executionHint = 'Waiting for approval before execution continues'
  } else if (currentRunInactive) {
    executionHint = 'Latest run is inactive or superseded; no active execution step detected'
  } else if (stepCount === 0 && staleQueuedStepCount > 0) {
    executionHint = 'No current execution step detected. Older queued work exists in prior runs'
  } else if (stepCount === 0 && status === 'queued') {
    executionHint = 'Run is queued, but no execution step has started yet'
  } else if (stepCount === 0 && runtimeTeamCount > 0) {
    executionHint = 'Team assembled, but execution has not started yet'
  } else if (status === 'running' || status === 'queued') {
    executionHint = 'Execution started'
  } else if (status === 'done' && stepCount > 0) {
    executionHint = 'Execution completed'
  } else if (stepCount > 0) {
    executionHint = 'Execution steps detected'
  }
  if (supervisorEnabled) {
    executionHint += ' with supervisor coordination'
  }
  if (degradedMode) {
    executionHint = `Degraded fallback active${fallbackReason ? `: ${fallbackReason}` : ''}`
  }

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Now</h3>
        <div className="row" style={{ marginBottom: 0 }}>
          <span className={`pill runStudioStatus ${statusClass(status)}`}>run: {status}</span>
          {blocked && <span className="pill runStudioStatus runStudioStatus--blocked">blocked</span>}
          {pendingApproval && (
            <span className="pill runStudioStatus runStudioStatus--queued">
              pending approval{pendingApprovalCount > 1 ? ` (${pendingApprovalCount})` : ''}
            </span>
          )}
        </div>
      </div>

      <div className="runStudioWarning">
        <b>Team / Execution Hint:</b> {executionHint}
      </div>

      <div className="runStudioNowGrid">
        <div className="runStudioNowItem">
          <div className="muted">Current Task</div>
          <div>{task?.current_task || '-'}</div>
        </div>
        <div className="runStudioNowItem">
          <div className="muted">Current Objective</div>
          <div>{task?.current_objective || '-'}</div>
        </div>
        <div className="runStudioNowItem">
          <div className="muted">Current Step</div>
          <div>{task?.current_step || '-'}</div>
          <div className="muted">status: {task?.current_step_status || 'unknown'}</div>
        </div>
        <div className="runStudioNowItem">
          <div className="muted">Latest User Request</div>
          <div>{task?.latest_user_message_text || '-'}</div>
        </div>
      </div>

      {blocked && (
        <div className="runStudioWarning">
          <b>Blocked:</b> {blockedReason || 'No blocked reason was provided.'}
        </div>
      )}

      <div className="runStudioMetaRow">
        <span className="pill">mode: {mode}</span>
        <span className="pill">plan: {planSource}</span>
        <span className="pill">context: {contextSource}</span>
        <span className="pill">team: {teamSource}</span>
        <span className="pill">skills: {skillSource}</span>
        <span className="pill">runtime agents: {runtimeTeamCount}</span>
        <span className="pill">scope mode: {scopeMode}</span>
        <span className="pill">scopes: {scopeCount}</span>
        {legacyContextPackCount > 0 && <span className="pill">legacy packs: {legacyContextPackCount}</span>}
        {legacyContextPacksEnabled && <span className="pill">legacy packs active</span>}
        <span className="pill">collaboration: {collaborationCount}</span>
        <span className="pill">checkpoints: {checkpointCount}</span>
        {orchestration?.parallel_group_count ? (
          <span className="pill">parallel groups: {orchestration.parallel_group_count}</span>
        ) : null}
        {supervisorEnabled && <span className="pill">supervisor enabled</span>}
        {degradedMode && <span className="pill">degraded fallback</span>}
        <span className="pill">active context: {state?.active_context_count ?? 0}</span>
        {currentRunId && <span className="pill">current run: {currentRunId.slice(0, 8)}</span>}
        {staleQueuedStepCount > 0 && <span className="pill">older queued hidden: {staleQueuedStepCount}</span>}
        {Object.entries(stepStatusCounts).map(([key, count]) => (
          <span key={key} className="pill">{key}: {count}</span>
        ))}
        {Object.keys(stepStatusCounts).length === 0 && Object.entries(globalStepStatusCounts).map(([key, count]) => (
          <span key={`all-${key}`} className="pill">all {key}: {count}</span>
        ))}
      </div>
      {degradedMode && fallbackReason && (
        <div className="runStudioWarning">
          <b>Fallback reason:</b> {fallbackReason}
        </div>
      )}
    </section>
  )
}
