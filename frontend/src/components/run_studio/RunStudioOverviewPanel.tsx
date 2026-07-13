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

function compact(value: unknown, max = 180, fallback = '아직 현재 목표가 없습니다.'): string {
  const text = clean(value, '')
  if (!text) return fallback
  return text.length > max ? `${text.slice(0, Math.max(1, max - 1))}…` : text
}

function statusLabel(status: string): string {
  const value = status.toLowerCase()
  if (['running', 'active', 'working', 'routing', 'executing'].includes(value)) return '진행 중'
  if (['blocked', 'failed', 'error'].includes(value)) return '확인 필요'
  if (['done', 'completed'].includes(value)) return '완료'
  return '대기 중'
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
  const currentStep = summary?.projections?.execution?.current_step || null
  const memory = summary?.projections?.memory_context || {}
  const runtimePolicy = (summary as any)?.runtime_policy_summary || {}
  const latestPolicy = runtimePolicy.latest || {}
  const agentRoom = (summary as any)?.agent_room || (summary as any)?.agent_room_summary || {}
  const watch = (summary as any)?.watch_tasks_summary || {}
  const review = (summary as any)?.review_inbox_summary || (summary as any)?.proposal_summary || {}
  const board = (summary as any)?.semantic_board_summary || {}
  const contextRuntime = (summary as any)?.context_runtime_summary || {}
  const models = (summary as any)?.model_catalog_summary || {}

  const currentStatus = clean((now as any)?.state?.current_run_status || (now as any)?.state?.run_status || (now as any)?.state?.status || (now as any)?.status || currentStep?.status, 'idle')
  const currentRunId = clean((now as any)?.state?.current_run_id || currentStep?.run_id, '')
  const currentGoal = compact((now as any)?.state?.goal || currentStep?.goal || agentRoom.current_goal)
  const nextAction = compact(
    (watch as any)?.next_action
      || (currentStep?.status && !['done', 'completed', 'failed'].includes(String(currentStep.status).toLowerCase()) ? currentStep.goal : '')
      || (currentRunId ? `현재 작업 ${currentRunId} 이어가기 또는 확인` : '')
      || (currentGoal !== '아직 현재 목표가 없습니다.' ? '다음에 할 일을 작업방에 알려주세요.' : ''),
    180,
    '목표를 정한 뒤 Telegram 또는 아래 채팅에서 작업을 시작하세요.',
  )

  const reviewCount = pickNumber(review.pending_count, review.open_count, review.count, (summary as any)?.review_count)
  const activeWatchCount = pickNumber(watch.active_count, watch.running_count, watch.count)
  const selectedSourceCount = pickNumber(memory.selected_count, summary?.context_decisions_counts?.selected)
  const pinnedSourceCount = pickNumber(memory.pinned_count, summary?.context_decisions_counts?.pinned)
  const conflictCount = pickNumber(memory.conflict_count, summary?.context_decisions_counts?.conflicting)
  const missingCount = pickNumber(summary?.context_decisions_counts?.missing, (summary as any)?.missing_context_count)
  const ruleCount = pickNumber(board.rule_count, board.runtime_rule_count, (summary as any)?.runtime_rule_count)
  const correctionCount = pickNumber(board.correction_count, (summary as any)?.correction_count, review.correction_count)
  const contextMode = clean(contextRuntime.mode || latestPolicy.context_mode || (summary as any)?.context_mode, '기본')

  const activeAgentCount = pickNumber(controlPlaneSummary?.runtimeAgentCount, teamView?.items?.length, legacyTeam?.items?.length, countArray(agentRoom.default_agents))
  const modelCount = pickNumber(models.node_count, models.count, countArray(models.nodes))
  const collaborationCount = pickNumber(controlPlaneSummary?.collaborationCount, (collaboration as any)?.count, countArray((collaboration as any)?.items))
  const checkpointCount = pickNumber(controlPlaneSummary?.checkpointCount, (checkpoints as any)?.count, countArray((checkpoints as any)?.items))
  const executionPattern = clean(agentRoom.default_workflow || (orchestration as any)?.execution_pattern || (orchestration as any)?.pattern, '자동')
  const attentionCount = reviewCount + conflictCount + missingCount

  return (
    <section className="card runStudioPanel runStudioCommandCenter">
      <div className="runStudioCommandHeader">
        <div>
          <div className="runStudioEyebrow">지금 이 작업방</div>
          <h2>모델이 바뀌어도 작업은 이어집니다.</h2>
          <div className="muted">현재 목표와 다음 행동만 먼저 보여줍니다. 자료, 규칙, 실행 기술 정보는 필요할 때 펼쳐보세요.</div>
        </div>
        <div className="runStudioCommandActions">
          <button onClick={onRefresh} disabled={Boolean(loading)}>{loading ? '새로고침 중…' : '새로고침'}</button>
        </div>
      </div>

      <div className="roomNowGrid">
        <article className={`roomNowCard ${attentionCount > 0 || ['blocked', 'error', 'failed'].includes(currentStatus.toLowerCase()) ? 'needsAttention' : ''}`}>
          <div className="roomNowCardLabel">현재 목표</div>
          <div className="roomNowCardStatus">{statusLabel(currentStatus)}</div>
          <div className="roomNowCardText">{currentGoal}</div>
          {currentRunId && <div className="muted">작업 ID: {currentRunId}</div>}
        </article>
        <article className="roomNowCard">
          <div className="roomNowCardLabel">다음에 할 일</div>
          <div className="roomNowCardStatus">{activeWatchCount > 0 ? '이어가기' : '준비됨'}</div>
          <div className="roomNowCardText">{nextAction}</div>
          {attentionCount > 0 && <div className="roomNowAttention">확인할 항목 {attentionCount}개</div>}
        </article>
      </div>

      <details className="roomOverviewDetails">
        <summary>작업방 상태 더 보기</summary>
        <div className="roomOverviewDetailsGrid">
          <div><b>참고 자료</b><span>사용 중 {selectedSourceCount} · 고정 {pinnedSourceCount} · 빠짐 {missingCount} · 충돌 {conflictCount}</span></div>
          <div><b>기억과 규칙</b><span>규칙 {ruleCount} · 수정 지시 {correctionCount} · 확인 필요 {reviewCount}</span></div>
          <div><b>정보 사용 방식</b><span>{contextMode}</span></div>
          <div><b>기술 정보</b><span>Agent {activeAgentCount} · 모델 {modelCount} · 방식 {executionPattern} · 전달 {collaborationCount} · 점검 {checkpointCount}</span></div>
        </div>
      </details>
    </section>
  )
}
