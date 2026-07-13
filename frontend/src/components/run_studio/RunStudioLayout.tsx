import React, { useMemo, useState } from 'react'
import RunStudioOverviewPanel from './RunStudioOverviewPanel'
import WatchTasksPanel from './WatchTasksPanel'
import ReviewInboxPanel from './ReviewInboxPanel'
import RoomCommandDrawer from './RoomCommandDrawer'
import RoomChatPanel from './RoomChatPanel'
import DisclosureSection from './DisclosureSection'
import RoomDocsPanel from './RoomDocsPanel'
import EvidencePanel from './EvidencePanel'
import MissingContextPanel from './MissingContextPanel'
import ScopeMapPanel from './ScopeMapPanel'
import ScopeGrantPanel from './ScopeGrantPanel'
import ContextDecisionPanel from './ContextDecisionPanel'
import SemanticBoardPanel from './SemanticBoardPanel'
import MemoryRuleSkillReviewPanel from './MemoryRuleSkillReviewPanel'
import CheckpointPanel from './CheckpointPanel'
import RuntimeEventProjectionPanel from './RuntimeEventProjectionPanel'
import FocusedAuditTimelinePanel from './FocusedAuditTimelinePanel'
import DecisionTracePanel from './DecisionTracePanel'
import AgentActivityPanel from './AgentActivityPanel'
import RecipeStarterKitsPanel from './RecipeStarterKitsPanel'
import HarnessEvaluationPanel from './HarnessEvaluationPanel'
import RuntimePolicyPanel from './RuntimePolicyPanel'
import ContextRuntimePanel from './ContextRuntimePanel'
import AgentRoomPanel from './AgentRoomPanel'
import AgentPackagesPanel from './AgentPackagesPanel'
import TeamPackagesPanel from './TeamPackagesPanel'
import AgentTeamPanel from './AgentTeamPanel'
import AttachedSkillsPanel from './AttachedSkillsPanel'
import WhyThisTeamPanel from './WhyThisTeamPanel'
import ExecutionMapPanel from './ExecutionMapPanel'
import CollaborationPanel from './CollaborationPanel'
import AuthorityPanel from './AuthorityPanel'
import OrchestrationPanel from './OrchestrationPanel'
import LegacyFallbackNoticePanel from './LegacyFallbackNoticePanel'
import MemoryTopologyPanel from './MemoryTopologyPanel'
import MemoryDemandPanel from './MemoryDemandPanel'
import MemoryMaterializationPanel from './MemoryMaterializationPanel'
import ContextPackPanel from './ContextPackPanel'
import SkillUsagePanel from './SkillUsagePanel'
import CrossReferencePanel from './CrossReferencePanel'
import ProjectionRetrievalPanel from './ProjectionRetrievalPanel'
import GraphCompressionPanel from './GraphCompressionPanel'
import HarnessSpecPanel from './HarnessSpecPanel'
import AdvancedToolsPanel from './AdvancedToolsPanel'
import VisibilityPanel from './VisibilityPanel'
import {
  type RunStudioAgentTeam,
  type RunStudioContextPacks,
  type RunStudioContextDecisions,
  type RunStudioEvidence,
  type RunStudioSkillUsage,
  type RunStudioSummary,
  type RunStudioMemoryGraph,
  type RunStudioMemoryTopology,
  type RunStudioMemoryDemand,
  type RunStudioTraceScope,
  type RunStudioCrossReferences,
  type RunStudioAuditTimeline,
  type RunStudioProjectionRetrieval,
  type RunStudioGraphCompression,
  type RunStudioHarnessSpec,
  type RunStudioHarnessSummary,
  type TeamSelectionDataset,
  type TeamSelectionDatasetRow,
} from './types'
import {
  selectEffectiveAgentTeam,
  selectEffectiveAuthority,
  selectEffectiveCheckpoints,
  selectEffectiveCollaboration,
  selectEffectiveOrchestration,
  selectEffectiveScopeProjection,
  selectEffectiveTeamView,
  selectEffectiveWhyThisTeam,
  selectControlPlaneSummary,
} from './selectors'

type WorkspaceSection = 'overview' | 'work' | 'sources' | 'rules' | 'review' | 'history' | 'advanced'
type RoomActionKind = 'continue' | 'correct' | 'rule' | 'exclude_source' | 'branch' | 'context_mode'

type DetailState = {
  agentTeam?: boolean
  contextDecisions?: boolean
  evidence?: boolean
  contextPacks?: boolean
  skillUsage?: boolean
  memoryGraph?: boolean
  memoryTopology?: boolean
  memoryDemand?: boolean
  traceScope?: boolean
  teamSelection?: boolean
}

type Props = {
  threadId?: string | null
  summary: RunStudioSummary | null
  team: RunStudioAgentTeam | null
  decisions: RunStudioContextDecisions | null
  evidence: RunStudioEvidence | null
  contextPacks: RunStudioContextPacks | null
  skillUsage: RunStudioSkillUsage | null
  memoryGraph: RunStudioMemoryGraph | null
  memoryTopology: RunStudioMemoryTopology | null
  memoryDemand: RunStudioMemoryDemand | null
  traceScope: RunStudioTraceScope | null
  crossReferences: RunStudioCrossReferences | null
  auditTimeline: RunStudioAuditTimeline | null
  projectionRetrieval: RunStudioProjectionRetrieval | null
  graphCompression: RunStudioGraphCompression | null
  harnessSpec: RunStudioHarnessSpec | null
  harnessSummary: RunStudioHarnessSummary | null
  teamSelection: TeamSelectionDataset | null
  detailLoaded?: DetailState
  detailLoading?: DetailState
  loading: boolean
  error: string
  onRefresh: () => void
  onLoadAgentTeam?: () => void
  onLoadContextDecisions?: () => void
  onLoadEvidence?: () => void
  onLoadContextPacks?: () => void
  onLoadSkillUsage?: () => void
  onLoadMemoryGraph?: () => void
  onLoadMemoryTopology?: () => void
  onLoadMemoryDemand?: () => void
  onLoadTraceScope?: () => void
  onLoadTeamSelection?: () => void
  onInspectTeamSelectionEvent?: (row: TeamSelectionDatasetRow) => void
  onClearRunDrilldown?: () => void
  focusedRunId?: string | null
  focusedEventId?: string | null
  focusedEventLabel?: string | null
  onOpenGraph: () => void
  onOpenRawTrace: () => void
  onOpenRawTraceNode?: (nodeId: string) => void
  onOpenAdvanced: () => void
  onFocusNode?: (nodeId: string) => void
  onOpenNode?: (nodeId: string) => void
  onFocusTrace?: (nodeIds: string[]) => void
  onOpenTrace?: (nodeIds: string[]) => void
  onAddToActive?: (nodeId: string) => void
  onPinNode?: (nodeId: string, level: 'required' | 'preferred') => void
}

const NAV_ITEMS: Array<{ id: WorkspaceSection; label: string; description: string }> = [
  { id: 'overview', label: '지금', description: '목표와 다음 행동' },
  { id: 'work', label: '진행 중', description: '작업과 중간 저장' },
  { id: 'sources', label: '참고 자료', description: '사용할 정보와 제외 항목' },
  { id: 'rules', label: '기억과 규칙', description: '계속 지킬 조건' },
  { id: 'review', label: '확인 필요', description: '승인하거나 보류할 항목' },
  { id: 'history', label: '변경 기록', description: '결정과 실행 흐름' },
  { id: 'advanced', label: '고급 설정', description: 'Agent·모델·진단' },
]

function clean(value: unknown, fallback = ''): string {
  const text = typeof value === 'string' ? value.trim() : String(value || '').trim()
  return text || fallback
}

function num(...values: unknown[]): number {
  for (const value of values) {
    const number = Number(value)
    if (Number.isFinite(number)) return number
  }
  return 0
}

function statusTone(status: string): string {
  const value = status.toLowerCase()
  if (['failed', 'error', 'blocked'].includes(value)) return 'danger'
  if (['running', 'active', 'working', 'routing', 'executing'].includes(value)) return 'active'
  if (['done', 'completed', 'idle', 'ready'].includes(value)) return 'ok'
  return 'neutral'
}

function statusLabel(status: string): string {
  const value = status.toLowerCase()
  if (['failed', 'error', 'blocked'].includes(value)) return '확인 필요'
  if (['running', 'active', 'working', 'routing', 'executing'].includes(value)) return '진행 중'
  if (['done', 'completed'].includes(value)) return '완료'
  return '대기 중'
}

export default function RunStudioLayout(props: Props) {
  const {
    threadId, summary, team, decisions, evidence, contextPacks, skillUsage, memoryTopology, memoryDemand,
    crossReferences, auditTimeline, projectionRetrieval, graphCompression, harnessSpec, harnessSummary,
    detailLoaded, detailLoading, loading, error, onRefresh, onLoadAgentTeam, onLoadContextDecisions,
    onLoadEvidence, onLoadContextPacks, onLoadSkillUsage, onLoadMemoryTopology, onLoadMemoryDemand,
    onOpenGraph, onOpenRawTrace, onOpenAdvanced, onFocusNode, onOpenNode, onFocusTrace, onOpenTrace,
    onPinNode,
  } = props

  const [section, setSection] = useState<WorkspaceSection>('overview')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerAction, setDrawerAction] = useState<RoomActionKind>('correct')
  const [drawerDraft, setDrawerDraft] = useState('')
  const [advancedGroup, setAdvancedGroup] = useState<'runtime' | 'agents' | 'memory' | 'evaluation'>('runtime')

  const effectiveTeam = selectEffectiveAgentTeam(summary, team)
  const teamView = selectEffectiveTeamView(summary, team)
  const whyThisTeam = selectEffectiveWhyThisTeam(summary, team)
  const orchestration = selectEffectiveOrchestration(summary, teamView)
  const scopeProjection = selectEffectiveScopeProjection(summary, effectiveTeam)
  const collaboration = selectEffectiveCollaboration(summary)
  const authority = selectEffectiveAuthority(summary, team)
  const checkpoints = selectEffectiveCheckpoints(summary)
  const controlPlaneSummary = selectControlPlaneSummary(summary, team)
  const visibility = summary?.current_run_skills?.visibility_projection || summary?.visibility_projection || null
  const currentRunId = clean(summary?.now?.state?.current_run_id || summary?.projections?.execution?.current_step?.run_id)
  const currentStatus = clean(summary?.now?.state?.current_run_status || summary?.now?.state?.run_status || summary?.projections?.execution?.current_step?.status, 'idle')
  const reviewCount = num((summary as any)?.review_inbox_summary?.pending_count, (summary as any)?.proposal_summary?.pending_count)
  const conflictCount = num(summary?.context_decisions_counts?.conflicting, summary?.projections?.memory_context?.conflict_count)
  const missingCount = num(summary?.context_decisions_counts?.missing)
  const activeTaskCount = num((summary as any)?.watch_tasks_summary?.active_count, (summary as any)?.watch_tasks_summary?.count)
  const ruleCount = num((summary as any)?.semantic_board_summary?.rule_count, (summary as any)?.correction_count)
  const attentionCount = reviewCount + conflictCount + missingCount
  const externalRef = summary?.thread?.external_ref || ''

  const navBadges = useMemo<Record<WorkspaceSection, number>>(() => ({
    overview: attentionCount,
    work: activeTaskCount,
    sources: conflictCount + missingCount,
    rules: ruleCount,
    review: reviewCount,
    history: num(auditTimeline?.items?.length),
    advanced: 0,
  }), [attentionCount, activeTaskCount, conflictCount, missingCount, ruleCount, reviewCount, auditTimeline])

  function openAction(action: RoomActionKind, draft = '') {
    setDrawerAction(action)
    setDrawerDraft(draft)
    setDrawerOpen(true)
  }

  return (
    <div className="roomWorkspace">
      <header className="roomWorkspaceHeader">
        <div className="roomWorkspaceTitleBlock">
          <div className="runStudioEyebrow">작업방</div>
          <div className="roomWorkspaceTitleRow">
            <h1>{summary?.thread?.title || '이름 없는 작업방'}</h1>
            <span className={`roomStatus roomStatus--${statusTone(currentStatus)}`}>{statusLabel(currentStatus)}</span>
          </div>
          <p>사용 정보: {summary?.context_set?.name || '기본 설정'}{currentRunId ? ` · 작업 ${currentRunId}` : ''}</p>
        </div>
        <div className="roomWorkspaceHeaderActions">
          <button onClick={onRefresh} disabled={loading}>{loading ? '새로고침 중…' : '새로고침'}</button>
          <button className="primary" onClick={() => openAction('correct')}>작업방 수정</button>
        </div>
      </header>

      <details className="roomTermGuide">
        <summary>용어가 어렵다면 보기</summary>
        <div>
          <span><b>작업방</b> 목표와 기록이 이어지는 공간</span>
          <span><b>참고 자료</b> 답을 만들 때 사용해도 되는 정보</span>
          <span><b>규칙</b> 앞으로도 계속 지켜야 할 조건</span>
          <span><b>수정 내용</b> 같은 실수를 반복하지 않게 하는 사용자 정정</span>
          <span><b>확인할 항목</b> 자동 적용 전에 사용자가 봐야 하는 내용</span>
        </div>
      </details>

      {error && <div className="runStudioWarning roomWorkspaceError"><b>불러오기 실패:</b> {error}</div>}

      <div className="roomWorkspaceBody">
        <nav className="roomWorkspaceNav" aria-label="작업방 메뉴">
          <div className="roomWorkspaceNavIntro">
            <b>메뉴</b>
            <span>필요한 정보만 펼쳐보세요.</span>
          </div>
          {NAV_ITEMS.map((item) => (
            <button key={item.id} className={`roomWorkspaceNavItem ${section === item.id ? 'isActive' : ''}`} onClick={() => setSection(item.id)}>
              <span className="roomWorkspaceNavText"><b>{item.label}</b><small>{item.description}</small></span>
              {navBadges[item.id] > 0 && <span className="roomWorkspaceNavBadge">{navBadges[item.id]}</span>}
            </button>
          ))}
          <div className="roomWorkspaceNavTools">
            <button onClick={onOpenGraph}>관계 그래프</button>
            <button onClick={onOpenRawTrace}>원본 실행 기록</button>
          </div>
        </nav>

        <main className="roomWorkspaceContent">
          <RoomChatPanel threadId={threadId} externalRef={externalRef} currentStatus={currentStatus} onActivity={onRefresh} />

          {section === 'overview' && (
            <div className="roomWorkspaceSection">
              <RunStudioOverviewPanel
                summary={summary}
                controlPlaneSummary={controlPlaneSummary}
                teamView={teamView}
                legacyTeam={effectiveTeam}
                orchestration={orchestration}
                collaboration={collaboration}
                checkpoints={checkpoints}
                loading={loading}
                onRefresh={onRefresh}
              />

              <section className="roomQuickActions" aria-label="자주 쓰는 작업방 기능">
                <button onClick={() => openAction('continue')}><b>이어가기</b><span>현재 작업을 계속합니다</span></button>
                <button onClick={() => openAction('correct')}><b>잘못 이해한 점 수정</b><span>같은 실수를 막습니다</span></button>
                <button onClick={() => openAction('exclude_source')}><b>자료 제외</b><span>낡거나 틀린 정보를 빼냅니다</span></button>
                <button onClick={() => openAction('branch')}><b>다른 방향 만들기</b><span>현재 방향은 남겨둡니다</span></button>
              </section>

              <DisclosureSection
                title="진행 중인 작업"
                summary={activeTaskCount > 0 ? `${activeTaskCount}개가 진행 중입니다.` : '현재 진행 중인 작업이 없습니다.'}
                badge={activeTaskCount || null}
                defaultOpen={false}
                persistKey={`overview-work:${threadId || 'none'}`}
              >
                <WatchTasksPanel threadId={threadId} />
              </DisclosureSection>

              <DisclosureSection
                title="확인할 항목"
                summary={reviewCount > 0 ? `${reviewCount}개가 사용자의 확인을 기다립니다.` : '지금 확인할 항목이 없습니다.'}
                badge={reviewCount || null}
                defaultOpen={false}
                persistKey={`overview-review:${threadId || 'none'}`}
                tone={reviewCount > 0 ? 'attention' : 'ok'}
              >
                <ReviewInboxPanel threadId={threadId} />
              </DisclosureSection>
            </div>
          )}

          {section === 'work' && (
            <div className="roomWorkspaceSection">
              <div className="roomSectionHeading"><div><div className="runStudioEyebrow">진행 중</div><h2>현재 작업과 중간 저장</h2><p>평소에는 작업 상태만 보고, 실행 세부 정보는 필요할 때 펼쳐보세요.</p></div><button className="primary" onClick={() => openAction('continue')}>작업 이어가기</button></div>
              <DisclosureSection title="현재 작업" summary="진행 상태와 다음 단계를 확인합니다." defaultOpen persistKey={`work-current:${threadId || 'none'}`}><WatchTasksPanel threadId={threadId} /></DisclosureSection>
              <DisclosureSection title="중간 저장과 되돌리기" summary="작업의 저장 지점과 재개 위치를 확인합니다." badge={num((checkpoints as any)?.count, (checkpoints as any)?.items?.length) || null} persistKey={`work-checkpoints:${threadId || 'none'}`}><CheckpointPanel checkpoints={checkpoints} /></DisclosureSection>
              <DisclosureSection title="실행 세부 정보" summary="Agent 활동, 정보 사용 방식, 실행 정책을 확인합니다." persistKey={`work-runtime:${threadId || 'none'}`}>
                <div className="roomWorkspaceStack"><AgentActivityPanel threadId={threadId} runId={currentRunId || null} summary={summary} /><ContextRuntimePanel threadId={threadId} runId={currentRunId || null} summary={summary} /><RuntimePolicyPanel summary={summary} /></div>
              </DisclosureSection>
            </div>
          )}

          {section === 'sources' && (
            <div className="roomWorkspaceSection">
              <div className="roomSectionHeading"><div><div className="runStudioEyebrow">참고 자료</div><h2>무엇을 믿고 답하는지 확인</h2><p>사용 중인 자료, 빠진 자료, 충돌하는 자료를 필요한 만큼만 펼쳐보세요.</p></div><button onClick={() => openAction('exclude_source')}>자료 제외</button></div>
              <DisclosureSection title="현재 사용할 수 있는 자료" summary="작업방이 참고하도록 허용된 정보 범위입니다." defaultOpen persistKey={`sources-scope:${threadId || 'none'}`}><ScopeMapPanel scopeProjection={scopeProjection} /></DisclosureSection>
              <DisclosureSection title="빠졌거나 충돌하는 정보" summary={missingCount + conflictCount > 0 ? `${missingCount + conflictCount}개를 확인해야 합니다.` : '현재 알려진 문제는 없습니다.'} badge={missingCount + conflictCount || null} defaultOpen={missingCount + conflictCount > 0} tone={missingCount + conflictCount > 0 ? 'attention' : 'ok'} persistKey={`sources-missing:${threadId || 'none'}`}><MissingContextPanel decisions={decisions} /></DisclosureSection>
              <DisclosureSection title="근거 자세히 보기" summary="어떤 주장에 어떤 자료가 연결됐는지 확인합니다." persistKey={`sources-evidence:${threadId || 'none'}`}>
                {detailLoaded?.evidence || evidence ? <EvidencePanel evidence={evidence} onFocusNode={onFocusNode} onOpenNode={onOpenNode} onExcludeSource={(source) => openAction('exclude_source', source)} /> : <section className="card runStudioPanel roomLoadCard"><h3>근거 세부 정보</h3><p>필요할 때만 불러옵니다.</p><button onClick={onLoadEvidence} disabled={Boolean(detailLoading?.evidence)}>{detailLoading?.evidence ? '불러오는 중…' : '근거 불러오기'}</button></section>}
              </DisclosureSection>
              <DisclosureSection title="왜 이 정보가 선택됐는지" summary="선택·고정·제외·충돌 판단을 확인합니다." persistKey={`sources-decisions:${threadId || 'none'}`}>
                {detailLoaded?.contextDecisions || decisions ? <ContextDecisionPanel decisions={decisions} onFocusNode={onFocusNode} onOpenNode={onOpenNode} onPinNode={onPinNode} onExcludeNode={(source) => openAction('exclude_source', source)} /> : <section className="card runStudioPanel roomLoadCard"><h3>정보 선택 이유</h3><p>필요할 때만 불러옵니다.</p><button onClick={onLoadContextDecisions} disabled={Boolean(detailLoading?.contextDecisions)}>{detailLoading?.contextDecisions ? '불러오는 중…' : '선택 이유 불러오기'}</button></section>}
              </DisclosureSection>
              <DisclosureSection title="접근 범위와 공개 설정" summary="누가 어떤 정보를 볼 수 있는지 관리합니다." persistKey={`sources-access:${threadId || 'none'}`}><div className="roomWorkspaceTwoColumn"><ScopeGrantPanel scopeProjection={scopeProjection} legacyTeam={effectiveTeam} threadId={summary?.thread?.id || null} onSaved={onRefresh} /><VisibilityPanel visibilityProjection={visibility} /></div></DisclosureSection>
              <DisclosureSection title="작업방 문서" summary="연결된 문서와 설명을 확인합니다." persistKey={`sources-docs:${threadId || 'none'}`}><RoomDocsPanel threadId={threadId} /></DisclosureSection>
            </div>
          )}

          {section === 'rules' && (
            <div className="roomWorkspaceSection">
              <div className="roomSectionHeading"><div><div className="runStudioEyebrow">기억과 규칙</div><h2>앞으로도 계속 지킬 내용</h2><p>사용자 정정, 작업 규칙, 기억 후보를 구분해서 관리합니다.</p></div><div className="roomSectionActions"><button onClick={() => openAction('rule')}>규칙 추가</button><button className="primary" onClick={() => openAction('correct')}>잘못 이해한 점 수정</button></div></div>
              <DisclosureSection title="현재 기억과 규칙" summary="작업방이 현재 유지하고 있는 조건입니다." badge={ruleCount || null} defaultOpen persistKey={`rules-board:${threadId || 'none'}`}><SemanticBoardPanel threadId={threadId} summary={summary} /></DisclosureSection>
              <DisclosureSection title="새로 기억할 후보" summary="자동 반영 전에 검토할 규칙·기억·기능 후보입니다." persistKey={`rules-review:${threadId || 'none'}`}><MemoryRuleSkillReviewPanel threadId={threadId} /></DisclosureSection>
              <DisclosureSection title="장기 기억으로 저장" summary="검토된 내용을 어떤 형태로 남길지 확인합니다." persistKey={`rules-materialize:${threadId || 'none'}`}><MemoryMaterializationPanel threadId={threadId} /></DisclosureSection>
            </div>
          )}

          {section === 'review' && (
            <div className="roomWorkspaceSection">
              <div className="roomSectionHeading"><div><div className="runStudioEyebrow">확인 필요</div><h2>자동 적용 전에 살펴볼 항목</h2><p>근거가 충분한지 보고 승인·보류·거절합니다.</p></div></div>
              <DisclosureSection title="확인 대기 목록" summary={reviewCount > 0 ? `${reviewCount}개가 기다리고 있습니다.` : '현재 대기 항목이 없습니다.'} badge={reviewCount || null} defaultOpen tone={reviewCount > 0 ? 'attention' : 'ok'} persistKey={`review-inbox:${threadId || 'none'}`}><ReviewInboxPanel threadId={threadId} /></DisclosureSection>
              <DisclosureSection title="기억과 규칙 후보" summary="승인 전에 위험과 근거를 확인합니다." persistKey={`review-memory:${threadId || 'none'}`}><MemoryRuleSkillReviewPanel threadId={threadId} /></DisclosureSection>
              <DisclosureSection title="관련 근거" summary="선택한 항목을 뒷받침하는 자료입니다." persistKey={`review-evidence:${threadId || 'none'}`}>
                {detailLoaded?.evidence || evidence ? <EvidencePanel evidence={evidence} onFocusNode={onFocusNode} onOpenNode={onOpenNode} /> : <button className="roomInlineLoad" onClick={onLoadEvidence}>근거 불러오기</button>}
              </DisclosureSection>
            </div>
          )}

          {section === 'history' && (
            <div className="roomWorkspaceSection">
              <div className="roomSectionHeading"><div><div className="runStudioEyebrow">변경 기록</div><h2>어떻게 지금 상태가 되었는지 보기</h2><p>일반 기록부터 보고, 원본 실행 기록은 문제를 깊게 조사할 때만 여세요.</p></div><button onClick={onOpenRawTrace}>원본 실행 기록</button></div>
              <DisclosureSection title="중요 변경과 결정" summary="사용자에게 의미 있는 변경만 모아봅니다." defaultOpen persistKey={`history-focus:${threadId || 'none'}`}><FocusedAuditTimelinePanel auditTimeline={auditTimeline} onFocusNode={onFocusNode} onOpenNode={onOpenNode} onFocusTrace={onFocusTrace} onOpenTrace={onOpenTrace} /></DisclosureSection>
              <DisclosureSection title="결정 과정" summary="어떤 판단을 거쳐 결과가 나왔는지 확인합니다." persistKey={`history-decisions:${threadId || 'none'}`}><DecisionTracePanel threadId={threadId} runId={currentRunId || null} summary={summary} /></DisclosureSection>
              <DisclosureSection title="기술 실행 기록" summary="GoC로 전달된 저수준 실행 이벤트입니다." persistKey={`history-events:${threadId || 'none'}`}><RuntimeEventProjectionPanel runId={currentRunId || null} threadId={threadId} /></DisclosureSection>
            </div>
          )}

          {section === 'advanced' && (
            <div className="roomWorkspaceSection">
              <div className="roomSectionHeading"><div><div className="runStudioEyebrow">고급 설정</div><h2>Agent·모델·기억 구조·평가</h2><p>일상적인 작업에는 필요하지 않습니다. 문제 진단이나 정책 조정 때만 펼쳐보세요.</p></div><button onClick={onOpenAdvanced}>기존 고급 도구 열기</button></div>
              <div className="roomAdvancedTabs">
                {([
                  ['runtime', '실행 방식'],
                  ['agents', 'Agent'],
                  ['memory', '기억 구조'],
                  ['evaluation', '평가'],
                ] as const).map(([id, label]) => <button key={id} className={advancedGroup === id ? 'primary' : ''} onClick={() => setAdvancedGroup(id)}>{label}</button>)}
              </div>
              {advancedGroup === 'runtime' && <>
                <DisclosureSection title="실행 정책" summary="현재 provider·모델·작업 실행 기준입니다." defaultOpen persistKey={`advanced-policy:${threadId || 'none'}`}><RuntimePolicyPanel summary={summary} /></DisclosureSection>
                <DisclosureSection title="작업 전달과 협업" summary="여러 단계나 Agent 사이의 전달 구조입니다." persistKey={`advanced-collab:${threadId || 'none'}`}><div className="roomWorkspaceStack"><div className="roomWorkspaceTwoColumn"><ExecutionMapPanel orchestration={orchestration} teamView={teamView} collaboration={collaboration} checkpoints={checkpoints} /><CollaborationPanel collaboration={collaboration} /></div><div className="roomWorkspaceTwoColumn"><AuthorityPanel authority={authority} runtimeAuthority={summary?.runtime_authority} /><OrchestrationPanel orchestration={orchestration} checkpoints={checkpoints} teamView={teamView} /></div><LegacyFallbackNoticePanel summary={controlPlaneSummary} /></div></DisclosureSection>
              </>}
              {advancedGroup === 'agents' && <>
                <DisclosureSection title="현재 Agent 구성" summary="참여 Agent와 연결된 기능을 확인합니다." defaultOpen persistKey={`advanced-agents:${threadId || 'none'}`}><div className="roomWorkspaceStack"><div className="roomWorkspaceTwoColumn"><AgentRoomPanel summary={summary} teamView={teamView} legacyTeam={effectiveTeam} /><AttachedSkillsPanel summary={summary} team={effectiveTeam} /></div>{teamView || effectiveTeam ? <AgentTeamPanel threadId={threadId} teamView={teamView} legacyTeam={effectiveTeam} orchestration={orchestration} collaboration={collaboration} /> : <button className="roomInlineLoad" onClick={onLoadAgentTeam}>Agent 자세히 불러오기</button>}<WhyThisTeamPanel teamView={teamView} whyThisTeam={whyThisTeam} /></div></DisclosureSection>
                <DisclosureSection title="설치된 Agent 패키지" summary="재사용 가능한 Agent와 팀 구성을 관리합니다." persistKey={`advanced-packages:${threadId || 'none'}`}><div className="roomWorkspaceStack"><AgentPackagesPanel threadId={threadId} summary={summary} /><TeamPackagesPanel threadId={threadId} /></div></DisclosureSection>
              </>}
              {advancedGroup === 'memory' && <>
                <DisclosureSection title="기억 구조와 사용량" summary="기억이 어떻게 나뉘고 어떤 부분이 많이 쓰이는지 확인합니다." defaultOpen persistKey={`advanced-memory:${threadId || 'none'}`}><div className="roomWorkspaceTwoColumn"><MemoryTopologyPanel topology={memoryTopology} onLoadDetail={onLoadMemoryTopology} detailLoading={Boolean(detailLoading?.memoryTopology)} detailLoaded={Boolean(detailLoaded?.memoryTopology || memoryTopology)} /><MemoryDemandPanel demand={memoryDemand} onLoadDetail={onLoadMemoryDemand} detailLoading={Boolean(detailLoading?.memoryDemand)} detailLoaded={Boolean(detailLoaded?.memoryDemand || memoryDemand)} /></div></DisclosureSection>
                <DisclosureSection title="기억 저장과 실행 정보" summary="검토된 기억과 실행에 사용할 정보를 확인합니다." persistKey={`advanced-memory-detail:${threadId || 'none'}`}><div className="roomWorkspaceStack"><MemoryMaterializationPanel threadId={threadId} />{detailLoaded?.contextPacks || contextPacks ? <ContextPackPanel contextPacks={contextPacks} summary={summary} onLoadDetail={onLoadContextPacks} detailLoading={Boolean(detailLoading?.contextPacks)} detailLoaded={Boolean(detailLoaded?.contextPacks || contextPacks)} /> : <button className="roomInlineLoad" onClick={onLoadContextPacks}>실행 정보 불러오기</button>}{detailLoaded?.skillUsage || skillUsage ? <SkillUsagePanel skillUsage={skillUsage} summary={summary} onLoadDetail={onLoadSkillUsage} detailLoading={Boolean(detailLoading?.skillUsage)} detailLoaded={Boolean(detailLoaded?.skillUsage || skillUsage)} /> : <button className="roomInlineLoad" onClick={onLoadSkillUsage}>기능 사용 기록 불러오기</button>}</div></DisclosureSection>
              </>}
              {advancedGroup === 'evaluation' && <>
                <DisclosureSection title="검증된 시작 방법" summary="평가된 Recipe와 권장 시작 구성을 확인합니다." defaultOpen persistKey="advanced-recipes"><RecipeStarterKitsPanel /></DisclosureSection>
                <DisclosureSection title="모델과 실행 방식 평가" summary="실제 시나리오에서의 성능 기록입니다." persistKey="advanced-evaluations"><div className="roomWorkspaceStack"><HarnessEvaluationPanel /><HarnessSpecPanel harnessSpec={harnessSpec} harnessSummary={harnessSummary} /></div></DisclosureSection>
                <DisclosureSection title="검색·압축·연결 진단" summary="고급 품질 분석과 내부 연결 정보를 확인합니다." persistKey="advanced-diagnostics"><div className="roomWorkspaceStack"><CrossReferencePanel crossReferences={crossReferences} onFocusNode={onFocusNode} onOpenNode={onOpenNode} /><ProjectionRetrievalPanel projectionRetrieval={projectionRetrieval} /><GraphCompressionPanel graphCompression={graphCompression} /><AdvancedToolsPanel onOpenGraph={onOpenGraph} onOpenRawTrace={onOpenRawTrace} onOpenAdvanced={onOpenAdvanced} /></div></DisclosureSection>
              </>}
            </div>
          )}
        </main>
      </div>

      <RoomCommandDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        threadId={threadId}
        externalRef={externalRef}
        initialAction={drawerAction}
        initialDraft={drawerDraft}
        onApplied={() => { onRefresh(); window.setTimeout(onRefresh, 1200) }}
      />
    </div>
  )
}
