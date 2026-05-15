import React from 'react'
import type { RunStudioAgentTeam, RunStudioSummary } from './types'
import type { ControlPlaneSummaryProjection, TeamViewProjection, OrchestrationProjection, CollaborationProjection, CheckpointProjection } from './types'

type Props = {
  summary: RunStudioSummary | null
  controlPlaneSummary: ControlPlaneSummaryProjection | null
  teamView?: TeamViewProjection | null
  legacyTeam?: RunStudioAgentTeam | null
  orchestration?: OrchestrationProjection | null
  collaboration?: CollaborationProjection | null
  checkpoints?: CheckpointProjection | null
  loading?: boolean
  onRefresh: () => void
}

function clean(value: unknown, fallback = '—'): string {
  const text = typeof value === 'string' ? value.trim() : String(value ?? '').trim()
  return text || fallback
}

function countArray(value: unknown): number {
  return Array.isArray(value) ? value.length : 0
}

function pickNumber(...values: unknown[]): number {
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) return value
  }
  return 0
}

function compactGoal(value: unknown): string {
  const text = clean(value, '')
  if (!text) return 'No active goal has been synced yet.'
  return text.length > 180 ? `${text.slice(0, 177)}…` : text
}

export default function RunStudioOverviewPanel({
  summary,
  controlPlaneSummary,
  teamView,
  legacyTeam,
  orchestration,
  collaboration,
  checkpoints,
  loading,
  onRefresh,
}: Props) {
  const now = summary?.now || {}
  const runtimePolicy = (summary as any)?.runtime_policy_summary || {}
  const latestPolicy = runtimePolicy.latest || {}
  const agentRoom = (summary as any)?.agent_room || (summary as any)?.agent_room_summary || {}
  const watch = (summary as any)?.watch_tasks_summary || {}
  const review = (summary as any)?.review_inbox_summary || (summary as any)?.proposal_summary || {}
  const packages = (summary as any)?.agent_package_summary || {}
  const board = (summary as any)?.semantic_board_summary || {}
  const models = (summary as any)?.model_catalog_summary || {}
  const usage = (summary as any)?.model_usage_summary || models?.usage || {}

  const activeAgentCount = pickNumber(
    controlPlaneSummary?.runtimeAgentCount,
    teamView?.items?.length,
    legacyTeam?.items?.length,
    countArray(agentRoom.default_agents),
  )
  const checkpointCount = pickNumber(controlPlaneSummary?.checkpointCount, (checkpoints as any)?.count, countArray((checkpoints as any)?.items))
  const collaborationCount = pickNumber(controlPlaneSummary?.collaborationCount, (collaboration as any)?.count, countArray((collaboration as any)?.items))
  const reviewCount = pickNumber(review.pending_count, review.open_count, review.count, (summary as any)?.review_count)
  const watchCount = pickNumber(watch.active_count, watch.running_count, watch.count)
  const packageCount = pickNumber(packages.package_count, packages.count)
  const boardCardCount = pickNumber(board.card_count, board.count)
  const modelCount = pickNumber(models.node_count, models.count, countArray(models.nodes))
  const totalTokens = pickNumber(usage.total_tokens, models.total_tokens)

  const currentStatus = clean((now as any)?.state?.status || (now as any)?.status || (summary?.projections?.execution?.current_step?.status), 'idle')
  const currentRunId = clean((now as any)?.state?.current_run_id || (summary?.projections?.execution?.current_step?.run_id), 'no active run')
  const currentGoal = compactGoal((now as any)?.state?.goal || (summary?.projections?.execution?.current_step?.goal) || (agentRoom.current_goal))
  const workflow = clean(agentRoom.default_workflow || (orchestration as any)?.execution_pattern || (orchestration as any)?.pattern || latestPolicy.execution_mode, 'not configured')
  const writePolicy = clean(latestPolicy.workspace_write || runtimePolicy.workspace_write || 'not resolved')
  const manualFallback = clean(latestPolicy.legacy_manual_fallback || runtimePolicy.legacy_manual_fallback || (runtimePolicy.legacy_manual_fallback_disabled_count ? 'disabled' : 'not resolved'))

  const attentionTone = reviewCount > 0 || currentStatus === 'blocked' || currentStatus === 'error' ? 'needs-attention' : 'ok'

  return (
    <section className="card runStudioPanel runStudioCommandCenter">
      <div className="runStudioCommandHeader">
        <div>
          <div className="runStudioEyebrow">Operator view</div>
          <h2>What matters right now</h2>
          <div className="muted">A compact cockpit for the active agent room. Detailed memory, model, package, and trace surfaces are one step deeper.</div>
        </div>
        <div className="runStudioCommandActions">
          <button onClick={onRefresh} disabled={Boolean(loading)}>{loading ? 'Refreshing…' : 'Refresh'}</button>
        </div>
      </div>

      <div className="runStudioHeroSummaryGrid">
        <div className={`runStudioHeroSummaryCard runStudioHeroSummaryCard--${attentionTone}`}>
          <div className="runStudioHeroSummaryLabel">Run status</div>
          <div className="runStudioHeroSummaryValue">{currentStatus}</div>
          <div className="muted">{currentRunId}</div>
          <div className="runStudioHeroGoal">{currentGoal}</div>
        </div>
        <div className="runStudioHeroSummaryCard">
          <div className="runStudioHeroSummaryLabel">Agent room</div>
          <div className="runStudioHeroSummaryValue">{activeAgentCount} agents</div>
          <div className="muted">workflow: {workflow}</div>
          <div className="runStudioMetaRow" style={{ marginTop: 8 }}>
            <span className="pill">handoffs: {collaborationCount}</span>
            <span className="pill">checks: {checkpointCount}</span>
          </div>
        </div>
        <div className="runStudioHeroSummaryCard">
          <div className="runStudioHeroSummaryLabel">Needs attention</div>
          <div className="runStudioHeroSummaryValue">{reviewCount}</div>
          <div className="muted">pending reviews / approvals</div>
          <div className="runStudioMetaRow" style={{ marginTop: 8 }}>
            <span className="pill">watch tasks: {watchCount}</span>
            <span className="pill">write: {writePolicy}</span>
          </div>
        </div>
        <div className="runStudioHeroSummaryCard">
          <div className="runStudioHeroSummaryLabel">Models & reuse</div>
          <div className="runStudioHeroSummaryValue">{modelCount} models</div>
          <div className="muted">tokens: {totalTokens || '—'}</div>
          <div className="runStudioMetaRow" style={{ marginTop: 8 }}>
            <span className="pill">packages: {packageCount}</span>
            <span className="pill">board: {boardCardCount}</span>
            <span className="pill">manual fallback: {manualFallback}</span>
          </div>
        </div>
      </div>
    </section>
  )
}
