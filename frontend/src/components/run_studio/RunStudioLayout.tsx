import React, { useState } from 'react'
import ControlPlaneSummaryPanel from './ControlPlaneSummaryPanel'
import LegacyFallbackNoticePanel from './LegacyFallbackNoticePanel'
import ExecutionMapPanel from './ExecutionMapPanel'
import ScopeMapPanel from './ScopeMapPanel'
import VisibilityPanel from './VisibilityPanel'
import ScopeGrantPanel from './ScopeGrantPanel'
import NowPanel from './NowPanel'
import AgentTeamPanel from './AgentTeamPanel'
import WhyThisTeamPanel from './WhyThisTeamPanel'
import OrchestrationPanel from './OrchestrationPanel'
import CollaborationPanel from './CollaborationPanel'
import AuthorityPanel from './AuthorityPanel'
import CheckpointPanel from './CheckpointPanel'
import AttachedSkillsPanel from './AttachedSkillsPanel'
import ContextPackPanel from './ContextPackPanel'
import ContextDecisionPanel from './ContextDecisionPanel'
import EvidencePanel from './EvidencePanel'
import MissingContextPanel from './MissingContextPanel'
import SkillUsagePanel from './SkillUsagePanel'
import AdvancedToolsPanel from './AdvancedToolsPanel'
import MemoryProjectionPanel from './MemoryProjectionPanel'
import TeamRecommendationPanel from './TeamRecommendationPanel'
import SelectionOutcomePanel from './SelectionOutcomePanel'
import CrossReferencePanel from './CrossReferencePanel'
import FocusedAuditTimelinePanel from './FocusedAuditTimelinePanel'
import ProjectionRetrievalPanel from './ProjectionRetrievalPanel'
import GraphCompressionPanel from './GraphCompressionPanel'
import HarnessSpecPanel from './HarnessSpecPanel'
import {
  type RunStudioAgentTeam,
  type RunStudioContextPacks,
  type RunStudioContextDecisions,
  type RunStudioEvidence,
  type RunStudioSkillUsage,
  type RunStudioSummary,
  type RunStudioMemoryGraph,
  type RunStudioTraceScope,
  type RunStudioCrossReferences,
  type RunStudioAuditTimeline,
  type RunStudioAuditTimelineEvent,
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
  selectSkillAttachmentOverview,
} from './selectors'

type DetailState = {
  agentTeam?: boolean
  contextDecisions?: boolean
  evidence?: boolean
  contextPacks?: boolean
  skillUsage?: boolean
  memoryGraph?: boolean
  traceScope?: boolean
  teamSelection?: boolean
}

type Props = {
  summary: RunStudioSummary | null
  team: RunStudioAgentTeam | null
  decisions: RunStudioContextDecisions | null
  evidence: RunStudioEvidence | null
  contextPacks: RunStudioContextPacks | null
  skillUsage: RunStudioSkillUsage | null
  memoryGraph: RunStudioMemoryGraph | null
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


function cleanTimelineText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : String(value || '').trim()
}

function formatTimelinePreviewTimestamp(value?: string | null): string {
  const clean = cleanTimelineText(value)
  if (!clean) return ''
  const parsed = new Date(clean)
  if (Number.isNaN(parsed.getTime())) return clean
  return parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function compactTimelinePreview(items: RunStudioAuditTimelineEvent[] = []): RunStudioAuditTimelineEvent[] {
  return items.slice(-3).reverse()
}

export default function RunStudioLayout({
  summary,
  team,
  decisions,
  evidence,
  contextPacks,
  skillUsage,
  memoryGraph,
  traceScope,
  crossReferences,
  auditTimeline,
  projectionRetrieval,
  graphCompression,
  harnessSpec,
  harnessSummary,
  teamSelection,
  detailLoaded,
  detailLoading,
  loading,
  error,
  onRefresh,
  onLoadAgentTeam,
  onLoadContextDecisions,
  onLoadEvidence,
  onLoadContextPacks,
  onLoadSkillUsage,
  onLoadMemoryGraph,
  onLoadTraceScope,
  onLoadTeamSelection,
  onInspectTeamSelectionEvent,
  onClearRunDrilldown,
  focusedRunId,
  focusedEventId,
  focusedEventLabel,
  onOpenGraph,
  onOpenRawTrace,
  onOpenRawTraceNode,
  onOpenAdvanced,
  onFocusNode,
  onOpenNode,
  onFocusTrace,
  onOpenTrace,
  onAddToActive,
  onPinNode,
}: Props) {
  const memoryProjection = summary?.projections?.memory_context
  const runtimeAuthority = summary?.runtime_authority
  const planningBoundary = summary?.planning_boundary
  const effectiveTeam = selectEffectiveAgentTeam(summary, team)
  const teamView = selectEffectiveTeamView(summary, team)
  const whyThisTeam = selectEffectiveWhyThisTeam(summary, team)
  const orchestration = selectEffectiveOrchestration(summary, teamView)
  const scopeProjection = selectEffectiveScopeProjection(summary, effectiveTeam)
  const visibilityProjection = summary?.current_run_skills?.visibility_projection || summary?.visibility_projection || null
  const collaboration = selectEffectiveCollaboration(summary)
  const showLegacyContextPacks = Boolean(scopeProjection?.legacy_context_packs_enabled || (scopeProjection?.legacy_context_pack_count || 0) > 0)
  const authorityProjection = selectEffectiveAuthority(summary, team)
  const checkpoints = selectEffectiveCheckpoints(summary)
  const controlPlaneSummary = selectControlPlaneSummary(summary, team)
  const skillAttachmentOverview = selectSkillAttachmentOverview(summary, effectiveTeam)
  const decisionsLoaded = Boolean(detailLoaded?.contextDecisions || decisions)
  const evidenceLoaded = Boolean(detailLoaded?.evidence || evidence)
  const [showExecutionDetails, setShowExecutionDetails] = useState(false)
  const [showContextDetails, setShowContextDetails] = useState(false)
  const [showDiagnostics, setShowDiagnostics] = useState(false)
  const [showRecentActivity, setShowRecentActivity] = useState(false)
  const recentTimelineItems = compactTimelinePreview(auditTimeline?.items || [])
  const compactActionItems = [
    {
      key: 'team',
      label: teamView || effectiveTeam ? 'Inspect team' : 'Load team detail',
      helper: teamView || effectiveTeam ? 'Current team and attached skills' : 'Load the compact runtime team view',
      onClick: teamView || effectiveTeam ? undefined : onLoadAgentTeam,
    },
    {
      key: 'context',
      label: showContextDetails ? 'Hide context' : 'Review context',
      helper: 'Scope grants, evidence, and attached skills',
      onClick: () => setShowContextDetails((value) => !value),
    },
    {
      key: 'execution',
      label: showExecutionDetails ? 'Hide execution' : 'Review execution',
      helper: 'Planner rationale, selection outcomes, and checkpoints',
      onClick: () => setShowExecutionDetails((value) => !value),
    },
    {
      key: 'activity',
      label: showRecentActivity ? 'Hide activity' : 'Recent activity',
      helper: 'Latest timeline events and recent changes',
      onClick: () => setShowRecentActivity((value) => !value),
    },
    {
      key: 'graph',
      label: 'Open Graph',
      helper: 'Focus nodes or inspect graph structure',
      onClick: onOpenGraph,
    },
    {
      key: 'advanced',
      label: 'Advanced',
      helper: 'Raw trace, artifacts, and power tools',
      onClick: onOpenAdvanced,
    },
  ]

  return (
    <div className="runStudioLayout">
      <div className="card runStudioHeaderCard">
        <div className="runStudioPanelHeader">
          <div>
            <h2 style={{ margin: 0 }}>Run Studio</h2>
            <div className="muted">
              Agency cockpit: agent 분담, handoff, review, synthesis를 먼저 보여줍니다. | {summary?.thread?.title || 'Untitled thread'} | context: {summary?.context_set?.name || 'default'}
            </div>
          </div>
          <div className="row" style={{ marginBottom: 0 }}>
            <button onClick={onRefresh} disabled={loading}>{loading ? 'Refreshing...' : 'Refresh'}</button>
          </div>
        </div>
        {memoryProjection && (
          <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
            <span className="pill">mode: {runtimeAuthority?.mode || summary?.mode || 'standalone'}</span>
            <span className="pill">plan: {runtimeAuthority?.plan_source || summary?.plan_source || 'local'}</span>
            <span className="pill">context: {runtimeAuthority?.context_source || summary?.context_source || 'local'}</span>
            <span className="pill">team: {runtimeAuthority?.conversation_team_source || summary?.conversation_team_source || 'local'}</span>
            <span className="pill">skills: {runtimeAuthority?.skill_catalog_source || summary?.skill_catalog_source || 'local'}</span>
            {runtimeAuthority?.degraded_mode && <span className="pill">degraded fallback</span>}
            {planningBoundary?.status && <span className="pill">planning: {planningBoundary.status}</span>}
            {planningBoundary?.ready_for_goc_control_plane && <span className="pill">goc control-plane ready</span>}
            <span className="pill">core: {memoryProjection.core_count ?? 0}</span>
            <span className="pill">supporting: {memoryProjection.supporting_count ?? 0}</span>
            <span className="pill">execution/debug: {memoryProjection.execution_count ?? 0}</span>
          </div>
        )}
        {runtimeAuthority?.degraded_mode && runtimeAuthority?.fallback_reason && (
          <div className="runStudioWarning"><b>Fallback reason:</b> {runtimeAuthority.fallback_reason}</div>
        )}
        {error && <div className="runStudioWarning"><b>Load error:</b> {error}</div>}
      </div>

      <div className="runStudioGrid runStudioGrid--bottom">
        <ControlPlaneSummaryPanel summary={controlPlaneSummary} skillOverview={skillAttachmentOverview} />
        <NowPanel
          summary={summary}
          team={effectiveTeam}
          teamView={teamView}
          orchestration={orchestration}
          collaboration={collaboration}
          checkpoints={checkpoints}
          controlPlaneSummary={controlPlaneSummary}
        />
      </div>

      <section className="card runStudioPanel runStudioAgencyCockpit">
        <div className="runStudioPanelHeader">
          <div>
            <h3>Agency Cockpit</h3>
            <div className="muted">자율 agent들이 어떻게 나뉘고, 서로 검토하고, 다시 합쳐지는지 보는 기본 화면입니다. Diagnostics와 self-improve는 보조 영역으로 둡니다.</div>
          </div>
          <div className="runStudioMetaRow" style={{ marginBottom: 0 }}>
            <span className="pill">agents: {controlPlaneSummary?.runtimeAgentCount ?? teamView?.items?.length ?? effectiveTeam?.items?.length ?? 0}</span>
            <span className="pill">collaboration: {collaboration?.count ?? collaboration?.items?.length ?? 0}</span>
            {orchestration?.parallel_group_count ? <span className="pill">parallel groups: {orchestration.parallel_group_count}</span> : null}
          </div>
        </div>
        <div className="runStudioGrid runStudioGrid--bottom">
          <ExecutionMapPanel
            orchestration={orchestration}
            teamView={teamView}
            collaboration={collaboration}
            checkpoints={checkpoints}
          />
          <CollaborationPanel collaboration={collaboration} />
        </div>
      </section>

      <div className="runStudioGrid runStudioGrid--top">
        {teamView || effectiveTeam ? (
          <AgentTeamPanel
            teamView={teamView}
            legacyTeam={effectiveTeam}
            orchestration={orchestration}
            collaboration={collaboration}
          />
        ) : (
          <section className="card runStudioPanel">
            <div className="runStudioPanelHeader">
              <h3>Runtime Team</h3>
            </div>
            <div className="muted" style={{ marginBottom: 8 }}>
              This run is keeping the team surface compact. Load details only when you need them.
            </div>
            <button onClick={onLoadAgentTeam} disabled={Boolean(detailLoading?.agentTeam)}>
              {detailLoading?.agentTeam ? 'Loading...' : 'Load team detail'}
            </button>
          </section>
        )}
        <AttachedSkillsPanel summary={summary} team={effectiveTeam} />
      </div>

      <div className="runStudioGrid runStudioGrid--bottom">
        <WhyThisTeamPanel teamView={teamView} whyThisTeam={whyThisTeam} />
        <section className="card runStudioPanel runStudioQuickActionsPanel">
          <div className="runStudioPanelHeader">
            <div>
              <h3>Quick actions</h3>
              <div className="muted">Start here. Open only the next area you need instead of loading every diagnostic at once.</div>
            </div>
            <div className="row" style={{ marginBottom: 0 }}>
              <button onClick={onRefresh} disabled={loading}>{loading ? 'Refreshing...' : 'Refresh'}</button>
            </div>
          </div>
          <div className="runStudioQuickActionsGrid">
            {compactActionItems.map((item) => (
              <button
                key={item.key}
                type="button"
                className="runStudioQuickActionButton"
                onClick={item.onClick}
                disabled={!item.onClick}
              >
                <span className="runStudioQuickActionTitle">{item.label}</span>
                <span className="runStudioQuickActionHelper">{item.helper}</span>
              </button>
            ))}
          </div>
          <div className="runStudioMetaRow" style={{ marginTop: 10 }}>
            <span className="pill">start with status</span>
            <span className="pill">open details only when needed</span>
            <span className="pill">graph and advanced stay secondary</span>
          </div>
        </section>
      </div>

      <section className="card runStudioPanel runStudioDisclosurePanel">
        <div className="runStudioPanelHeader">
          <div>
            <h3>Recent activity</h3>
            <div className="muted">A compact view of the latest run changes. Open the full timeline only when you need chronology and metadata.</div>
          </div>
          <button onClick={() => setShowRecentActivity((value) => !value)}>{showRecentActivity ? 'Hide' : 'Show timeline'}</button>
        </div>
        {!showRecentActivity && (
          recentTimelineItems.length > 0 ? (
            <div className="runStudioQuickList">
              {recentTimelineItems.map((event, index) => (
                <div key={event.event_id || `${event.category || 'event'}-${index}`} className="runStudioQuickListItem">
                  <div className="runStudioQuickListHeader">
                    <span className="runStudioQuickListTitle">{cleanTimelineText(event.title || event.category || 'timeline event')}</span>
                    <span className="muted">{formatTimelinePreviewTimestamp(event.timestamp)}</span>
                  </div>
                  <div className="muted">{cleanTimelineText(event.summary || '최근 activity가 기록되었습니다.')}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="muted">No recent activity has been recorded for this run yet.</div>
          )
        )}
        {showRecentActivity && (
          <FocusedAuditTimelinePanel
            auditTimeline={auditTimeline}
            onFocusNode={onFocusNode}
            onOpenNode={onOpenNode}
            onFocusTrace={onFocusTrace}
            onOpenTrace={onOpenTrace}
          />
        )}
      </section>

      <section className="card runStudioPanel runStudioDisclosurePanel">
        <div className="runStudioPanelHeader">
          <div>
            <h3>Execution details</h3>
            <div className="muted">Planner rationale, selection outcomes, and orchestration maps.</div>
          </div>
          <button onClick={() => setShowExecutionDetails((value) => !value)}>{showExecutionDetails ? 'Hide' : 'Show'}</button>
        </div>
        {showExecutionDetails && (
          <div className="runStudioDisclosureBody">
            <HarnessSpecPanel harnessSpec={harnessSpec} harnessSummary={harnessSummary} />
            <LegacyFallbackNoticePanel summary={controlPlaneSummary} />
            <ExecutionMapPanel
              orchestration={orchestration}
              teamView={teamView}
              collaboration={collaboration}
              checkpoints={checkpoints}
            />
            <TeamRecommendationPanel
              teamSelection={teamSelection}
              onLoadDetail={onLoadTeamSelection}
              detailLoading={Boolean(detailLoading?.teamSelection)}
              detailLoaded={Boolean(detailLoaded?.teamSelection)}
            />
            <SelectionOutcomePanel
              teamSelection={teamSelection}
              onInspectEvent={(row) => onInspectTeamSelectionEvent?.(row)}
              onClearInspect={onClearRunDrilldown}
              inspectedRunId={focusedRunId}
              inspectedEventId={focusedEventId}
            />
            <div className="runStudioGrid runStudioGrid--bottom">
              <OrchestrationPanel orchestration={orchestration} checkpoints={checkpoints} teamView={teamView} />
              <section className="card runStudioPanel">
                <div className="runStudioPanelHeader">
                  <h3>Collaboration detail</h3>
                </div>
                <div className="muted">주요 collaboration은 상단 Agency Cockpit에 항상 표시됩니다. 이 영역은 checkpoint/authority와 함께 보는 상세 실행 진단입니다.</div>
              </section>
            </div>
            <div className="runStudioGrid runStudioGrid--bottom">
              <CheckpointPanel checkpoints={checkpoints} />
              <AuthorityPanel authority={authorityProjection} runtimeAuthority={runtimeAuthority} />
            </div>
          </div>
        )}
      </section>

      <section className="card runStudioPanel runStudioDisclosurePanel">
        <div className="runStudioPanelHeader">
          <div>
            <h3>Context and evidence</h3>
            <div className="muted">Scope, visibility, missing context, evidence, and retrieval details.</div>
          </div>
          <button onClick={() => setShowContextDetails((value) => !value)}>{showContextDetails ? 'Hide' : 'Show'}</button>
        </div>
        {showContextDetails && (
          <div className="runStudioDisclosureBody">
            <div className="runStudioGrid runStudioGrid--bottom">
              <ScopeMapPanel scopeProjection={scopeProjection} />
              <VisibilityPanel visibilityProjection={visibilityProjection} />
            </div>
            <div className="runStudioGrid runStudioGrid--bottom">
              <ScopeGrantPanel
                scopeProjection={scopeProjection}
                legacyTeam={effectiveTeam}
                threadId={summary?.thread?.id || null}
                onSaved={onRefresh}
              />
              {showLegacyContextPacks ? (
                <ContextPackPanel
                  contextPacks={contextPacks}
                  summary={summary}
                  onLoadDetail={onLoadContextPacks}
                  detailLoading={Boolean(detailLoading?.contextPacks)}
                  detailLoaded={Boolean(detailLoaded?.contextPacks)}
                />
              ) : (
                <section className="card runStudioPanel">
                  <div className="runStudioPanelHeader">
                    <h3>Legacy Context Packs</h3>
                  </div>
                  <div className="muted">Scope-first runtime is active. Legacy context pack projection is not part of the main execution path.</div>
                </section>
              )}
            </div>
            <div className="runStudioGrid runStudioGrid--bottom">
              {decisionsLoaded ? (
                <ContextDecisionPanel
                  decisions={decisions}
                  onFocusNode={onFocusNode}
                  onOpenNode={onOpenNode}
                  onPinNode={onPinNode}
                />
              ) : (
                <section className="card runStudioPanel">
                  <div className="runStudioPanelHeader">
                    <h3>Context Decisions</h3>
                  </div>
                  <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                    <span className="pill">selected: {summary?.context_decisions_counts?.selected ?? 0}</span>
                    <span className="pill">pinned: {summary?.context_decisions_counts?.pinned ?? 0}</span>
                    <span className="pill">missing: {summary?.context_decisions_counts?.missing ?? 0}</span>
                    <span className="pill">conflicts: {summary?.context_decisions_counts?.conflicting ?? 0}</span>
                  </div>
                  <button onClick={onLoadContextDecisions} disabled={Boolean(detailLoading?.contextDecisions)}>
                    {detailLoading?.contextDecisions ? 'Loading...' : 'Load detail'}
                  </button>
                </section>
              )}
              {evidenceLoaded ? (
                <EvidencePanel
                  evidence={evidence}
                  onFocusNode={onFocusNode}
                  onOpenNode={onOpenNode}
                  onFocusTrace={onFocusTrace}
                  onOpenTrace={onOpenTrace}
                  onAddToActive={onAddToActive}
                  onPinNode={onPinNode}
                />
              ) : (
                <section className="card runStudioPanel">
                  <div className="runStudioPanelHeader">
                    <h3>Evidence</h3>
                  </div>
                  <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                    <span className="pill">claims: {summary?.evidence_counts?.claims ?? 0}</span>
                    <span className="pill">supported: {summary?.evidence_counts?.supported ?? 0}</span>
                    <span className="pill">uncertain: {summary?.evidence_counts?.with_uncertainty ?? 0}</span>
                    <span className="pill">conflicts: {summary?.evidence_counts?.with_conflicts ?? 0}</span>
                  </div>
                  <button onClick={onLoadEvidence} disabled={Boolean(detailLoading?.evidence)}>
                    {detailLoading?.evidence ? 'Loading...' : 'Load detail'}
                  </button>
                </section>
              )}
            </div>
            <div className="runStudioGrid runStudioGrid--bottom">
              {decisionsLoaded ? (
                <MissingContextPanel
                  decisions={decisions}
                  onFocusNode={onFocusNode}
                  onOpenNode={onOpenNode}
                  onIncludeNode={onAddToActive}
                  onPinNode={onPinNode}
                  onFocusConflict={onFocusTrace}
                  onOpenConflict={onOpenTrace}
                />
              ) : (
                <section className="card runStudioPanel">
                  <div className="runStudioPanelHeader">
                    <h3>Missing / Conflicting Context</h3>
                  </div>
                  <div className="muted" style={{ marginBottom: 8 }}>
                    Context decision details are loaded on demand to keep initial Run Studio fetch lightweight.
                  </div>
                  <button onClick={onLoadContextDecisions} disabled={Boolean(detailLoading?.contextDecisions)}>
                    {detailLoading?.contextDecisions ? 'Loading...' : 'Load detail'}
                  </button>
                </section>
              )}
              <SkillUsagePanel
                skillUsage={skillUsage}
                summary={summary}
                onLoadDetail={onLoadSkillUsage}
                detailLoading={Boolean(detailLoading?.skillUsage)}
                detailLoaded={Boolean(detailLoaded?.skillUsage)}
              />
            </div>
          </div>
        )}
      </section>

      <section className="card runStudioPanel runStudioDisclosurePanel">
        <div className="runStudioPanelHeader">
          <div>
            <h3>Diagnostics and legacy views</h3>
            <div className="muted">Deep trace scope, cross references, projection retrieval, memory graphs, and power tools.</div>
          </div>
          <button onClick={() => setShowDiagnostics((value) => !value)}>{showDiagnostics ? 'Hide' : 'Show'}</button>
        </div>
        {showDiagnostics && (
          <div className="runStudioDisclosureBody">
            {focusedRunId && (
              <section className="card runStudioPanel">
                <div className="runStudioPanelHeader">
                  <div>
                    <h3>Focused Drill-down</h3>
                    <div className="muted">Inspecting run-scoped evidence, context packs, skill usage, memory projection, and graph trace from a team-selection event.</div>
                  </div>
                  <div className="row">
                    {traceScope?.node_ids && traceScope.node_ids.length > 0 && onFocusTrace && (
                      <button onClick={() => onFocusTrace(traceScope.node_ids || [])}>Focus trace in Graph</button>
                    )}
                    {traceScope?.node_ids && traceScope.node_ids.length > 0 && onOpenTrace && (
                      <button onClick={() => onOpenTrace(traceScope.node_ids || [])}>Open trace detail</button>
                    )}
                    {traceScope?.anchor_node_id && onOpenRawTraceNode && (
                      <button onClick={() => onOpenRawTraceNode(traceScope.anchor_node_id || '')}>Open in Raw Trace</button>
                    )}
                    {!onOpenRawTraceNode && traceScope?.anchor_node_id && (
                      <button onClick={onOpenRawTrace}>Open Raw Trace</button>
                    )}
                    {onClearRunDrilldown && (
                      <button onClick={onClearRunDrilldown}>Clear focus</button>
                    )}
                  </div>
                </div>
                <div className="runStudioMetaRow">
                  <span className="pill">run: {focusedRunId}</span>
                  {focusedEventId && <span className="pill">event: {focusedEventId}</span>}
                  {focusedEventLabel && <span className="pill">label: {focusedEventLabel}</span>}
                  {typeof traceScope?.node_count === 'number' && <span className="pill">trace nodes: {traceScope.node_count}</span>}
                  {typeof traceScope?.edge_count === 'number' && <span className="pill">trace edges: {traceScope.edge_count}</span>}
                  {typeof traceScope?.step_count === 'number' && <span className="pill">steps: {traceScope.step_count}</span>}
                  {typeof traceScope?.memory_node_count === 'number' && <span className="pill">memory nodes: {traceScope.memory_node_count}</span>}
                  {typeof traceScope?.evidence_node_count === 'number' && <span className="pill">evidence nodes: {traceScope.evidence_node_count}</span>}
                </div>
                {traceScope?.anchor_node_id && (
                  <div className="muted" style={{ marginTop: 8 }}>anchor node: {traceScope.anchor_node_id}</div>
                )}
                {!traceScope?.node_ids?.length && onLoadTraceScope && (
                  <div className="row" style={{ marginTop: 8 }}>
                    <button onClick={onLoadTraceScope}>Load trace scope</button>
                  </div>
                )}
              </section>
            )}
            {focusedRunId && <ProjectionRetrievalPanel projectionRetrieval={projectionRetrieval} />}
            {focusedRunId && (
              <CrossReferencePanel
                crossReferences={crossReferences}
                onFocusNode={onFocusNode}
                onOpenNode={onOpenNode}
                onFocusTrace={onFocusTrace}
                onOpenTrace={onOpenTrace}
                onRefresh={onRefresh}
              />
            )}
            <MemoryProjectionPanel
              memoryGraph={memoryGraph}
              onLoadDetail={onLoadMemoryGraph}
              detailLoading={Boolean(detailLoading?.memoryGraph)}
              detailLoaded={Boolean(detailLoaded?.memoryGraph)}
              onRefresh={onLoadMemoryGraph}
            />
            <GraphCompressionPanel graphCompression={graphCompression} />
            <AdvancedToolsPanel
              onOpenGraph={onOpenGraph}
              onOpenRawTrace={onOpenRawTrace}
              onOpenAdvanced={onOpenAdvanced}
            />
          </div>
        )}
      </section>
    </div>
  )
}
