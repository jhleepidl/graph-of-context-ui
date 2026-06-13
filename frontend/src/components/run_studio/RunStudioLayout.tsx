import React, { useState } from 'react'
import RunStudioOverviewPanel from './RunStudioOverviewPanel'
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
import MemoryTopologyPanel from './MemoryTopologyPanel'
import MemoryDemandPanel from './MemoryDemandPanel'
import MemoryMaterializationPanel from './MemoryMaterializationPanel'
import MemoryRuleSkillReviewPanel from './MemoryRuleSkillReviewPanel'
import ReviewInboxPanel from './ReviewInboxPanel'
import WatchTasksPanel from './WatchTasksPanel'
import AgentRoomPanel from './AgentRoomPanel'
import TeamRecommendationPanel from './TeamRecommendationPanel'
import SelectionOutcomePanel from './SelectionOutcomePanel'
import CrossReferencePanel from './CrossReferencePanel'
import FocusedAuditTimelinePanel from './FocusedAuditTimelinePanel'
import ProjectionRetrievalPanel from './ProjectionRetrievalPanel'
import GraphCompressionPanel from './GraphCompressionPanel'
import HarnessSpecPanel from './HarnessSpecPanel'
import RuntimePolicyPanel from './RuntimePolicyPanel'
import AgentActivityPanel from './AgentActivityPanel'
import AgentPackagesPanel from './AgentPackagesPanel'
import TeamPackagesPanel from './TeamPackagesPanel'
import ModelCatalogPanel from './ModelCatalogPanel'
import SemanticBoardPanel from './SemanticBoardPanel'
import DecisionTracePanel from './DecisionTracePanel'
import ContextSubstratePanel from './ContextSubstratePanel'
import ContextRuntimePanel from './ContextRuntimePanel'
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

type RunStudioDetailSection = 'workspace' | 'execution' | 'memory' | 'models' | 'diagnostics' | null

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
  threadId,
  summary,
  team,
  decisions,
  evidence,
  contextPacks,
  skillUsage,
  memoryGraph,
  memoryTopology,
  memoryDemand,
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
  onLoadMemoryTopology,
  onLoadMemoryDemand,
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
  const [openSection, setOpenSection] = useState<RunStudioDetailSection>(null)
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

  const drilldownItems: Array<{ key: Exclude<RunStudioDetailSection, null>, title: string, helper: string, count?: string }> = [
    {
      key: 'workspace',
      title: 'Agent workspace',
      helper: 'Agent room, packages, active team, attached skills',
      count: `${controlPlaneSummary?.runtimeAgentCount ?? teamView?.items?.length ?? effectiveTeam?.items?.length ?? 0} agents`,
    },
    {
      key: 'execution',
      title: 'Execution flow',
      helper: 'Runtime policy, handoffs, checkpoints, collaboration',
      count: `${(summary as any)?.context_runtime_summary?.projection_count ?? 0} projections`,
    },
    {
      key: 'memory',
      title: 'Memory & review',
      helper: 'Semantic board, memory pressure, materialization, evidence, rules and skills',
      count: `${(summary as any)?.semantic_board_summary?.card_count ?? 0} cards`,
    },
    {
      key: 'models',
      title: 'Models & cost',
      helper: 'Model catalog, token usage, privacy and routing hints',
      count: `${(summary as any)?.model_catalog_summary?.node_count ?? (summary as any)?.model_catalog_summary?.count ?? 0} nodes`,
    },
    {
      key: 'diagnostics',
      title: 'Diagnostics',
      helper: 'Raw trace, graph compression, legacy projections and tools',
      count: 'advanced',
    },
  ]

  return (
    <div className="runStudioLayout runStudioLayout--focused">
      <div className="card runStudioHeaderCard runStudioHeaderCard--focused">
        <div className="runStudioPanelHeader">
          <div>
            <h2 style={{ margin: 0 }}>Run Studio</h2>
            <div className="muted">
              {summary?.thread?.title || 'Untitled thread'} · context: {summary?.context_set?.name || 'default'}
            </div>
          </div>
          <div className="row" style={{ marginBottom: 0 }}>
            <button onClick={onRefresh} disabled={loading}>{loading ? 'Refreshing...' : 'Refresh'}</button>
          </div>
        </div>
        <div className="runStudioMetaRow" style={{ marginTop: 8 }}>
          <span className="pill">mode: {runtimeAuthority?.mode || summary?.mode || 'standalone'}</span>
          <span className="pill">plan: {runtimeAuthority?.plan_source || summary?.plan_source || 'local'}</span>
          <span className="pill">context: {runtimeAuthority?.context_source || summary?.context_source || 'local'}</span>
          <span className="pill">team: {runtimeAuthority?.conversation_team_source || summary?.conversation_team_source || 'local'}</span>
          {runtimeAuthority?.degraded_mode && <span className="pill">degraded fallback</span>}
          {planningBoundary?.status && <span className="pill">planning: {planningBoundary.status}</span>}
        </div>
        {runtimeAuthority?.degraded_mode && runtimeAuthority?.fallback_reason && (
          <div className="runStudioWarning"><b>Fallback reason:</b> {runtimeAuthority.fallback_reason}</div>
        )}
        {error && <div className="runStudioWarning"><b>Load error:</b> {error}</div>}
      </div>

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

      <div className="runStudioGrid runStudioGrid--primaryWork">
        <WatchTasksPanel threadId={threadId} />
        <ReviewInboxPanel threadId={threadId} />
      </div>

      <section className="card runStudioPanel runStudioDrilldownHub">
        <div className="runStudioPanelHeader">
          <div>
            <h3>Explore details</h3>
            <div className="muted">The first screen stays focused. Open one area when you need deeper runtime evidence.</div>
          </div>
          {openSection && <button onClick={() => setOpenSection(null)}>Close detail</button>}
        </div>
        <div className="runStudioDrilldownGrid">
          {drilldownItems.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`runStudioDrilldownButton ${openSection === item.key ? 'runStudioDrilldownButton--active' : ''}`}
              onClick={() => setOpenSection((value) => value === item.key ? null : item.key)}
            >
              <span className="runStudioDrilldownTitle">{item.title}</span>
              <span className="runStudioDrilldownHelper">{item.helper}</span>
              {item.count && <span className="pill">{item.count}</span>}
            </button>
          ))}
        </div>
      </section>

      {openSection === 'workspace' && (
        <section className="card runStudioPanel runStudioDetailShelf">
          <div className="runStudioPanelHeader">
            <div>
              <h3>Agent workspace</h3>
              <div className="muted">Agent room setup, reusable packages, active team and attached skills.</div>
            </div>
          </div>
          <div className="runStudioGrid runStudioGrid--bottom">
            <AgentRoomPanel summary={summary} teamView={teamView} legacyTeam={effectiveTeam} />
            <AgentPackagesPanel threadId={threadId} summary={summary} />
            <TeamPackagesPanel threadId={threadId} />
          </div>
          <div className="runStudioGrid runStudioGrid--top">
            {teamView || effectiveTeam ? (
              <AgentTeamPanel
                threadId={threadId}
                teamView={teamView}
                legacyTeam={effectiveTeam}
                orchestration={orchestration}
                collaboration={collaboration}
              />
            ) : (
              <section className="card runStudioPanel">
                <div className="runStudioPanelHeader"><h3>Runtime Team</h3></div>
                <div className="muted" style={{ marginBottom: 8 }}>Team details are loaded on demand.</div>
                <button onClick={onLoadAgentTeam} disabled={Boolean(detailLoading?.agentTeam)}>
                  {detailLoading?.agentTeam ? 'Loading...' : 'Load team detail'}
                </button>
              </section>
            )}
            <AttachedSkillsPanel summary={summary} team={effectiveTeam} />
          </div>
          <WhyThisTeamPanel teamView={teamView} whyThisTeam={whyThisTeam} />
        </section>
      )}

      {openSection === 'execution' && (
        <section className="card runStudioPanel runStudioDetailShelf">
          <div className="runStudioPanelHeader">
            <div>
              <h3>Execution flow</h3>
              <div className="muted">Runtime policy, agent activity, execution map, collaboration and approval checkpoints.</div>
            </div>
          </div>
          <div className="runStudioGrid runStudioGrid--bottom">
            <RuntimePolicyPanel summary={summary} />
            <AgentActivityPanel threadId={threadId} runId={summary?.now?.state?.current_run_id || null} summary={summary} />
          </div>
          <ContextRuntimePanel threadId={threadId} runId={summary?.now?.state?.current_run_id || null} summary={summary} />
          <DecisionTracePanel threadId={threadId} runId={summary?.now?.state?.current_run_id || null} summary={summary} />
          <ContextSubstratePanel threadId={threadId} runId={summary?.now?.state?.current_run_id || null} summary={summary} />
          <div className="runStudioGrid runStudioGrid--bottom">
            <ExecutionMapPanel orchestration={orchestration} teamView={teamView} collaboration={collaboration} checkpoints={checkpoints} />
            <CollaborationPanel collaboration={collaboration} />
          </div>
          <div className="runStudioGrid runStudioGrid--bottom">
            <CheckpointPanel checkpoints={checkpoints} />
            <AuthorityPanel authority={authorityProjection} runtimeAuthority={runtimeAuthority} />
          </div>
          <div className="runStudioGrid runStudioGrid--bottom">
            <OrchestrationPanel orchestration={orchestration} checkpoints={checkpoints} teamView={teamView} />
            <LegacyFallbackNoticePanel summary={controlPlaneSummary} />
          </div>
        </section>
      )}

      {openSection === 'memory' && (
        <section className="card runStudioPanel runStudioDetailShelf">
          <div className="runStudioPanelHeader">
            <div>
              <h3>Memory & review</h3>
              <div className="muted">Memory, rules, skills, materialization, evidence and context only when you need them.</div>
            </div>
            <button onClick={() => setShowContextDetails((value) => !value)}>{showContextDetails ? 'Hide context evidence' : 'Show context evidence'}</button>
          </div>
          <SemanticBoardPanel threadId={threadId} summary={summary} />
          <MemoryRuleSkillReviewPanel threadId={threadId} />
          <div className="runStudioGrid runStudioGrid--bottom">
            <MemoryTopologyPanel
              topology={memoryTopology}
              onLoadDetail={onLoadMemoryTopology}
              detailLoading={Boolean(detailLoading?.memoryTopology)}
              detailLoaded={Boolean(detailLoaded?.memoryTopology || memoryTopology)}
            />
            <MemoryDemandPanel
              demand={memoryDemand}
              onLoadDetail={onLoadMemoryDemand}
              detailLoading={Boolean(detailLoading?.memoryDemand)}
              detailLoaded={Boolean(detailLoaded?.memoryDemand || memoryDemand)}
            />
          </div>
          <div className="runStudioGrid runStudioGrid--bottom">
            <MemoryMaterializationPanel threadId={threadId} />
            <ScopeMapPanel scopeProjection={scopeProjection} />
          </div>
          {showContextDetails && (
            <div className="runStudioDisclosureBody">
              <div className="runStudioGrid runStudioGrid--bottom">
                <ScopeGrantPanel
                  scopeProjection={scopeProjection}
                  legacyTeam={effectiveTeam}
                  threadId={summary?.thread?.id || null}
                  onSaved={onRefresh}
                />
                <VisibilityPanel visibilityProjection={visibilityProjection} />
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
                    <div className="runStudioPanelHeader"><h3>Context Decisions</h3></div>
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
                    <div className="runStudioPanelHeader"><h3>Evidence</h3></div>
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
                    <div className="runStudioPanelHeader"><h3>Missing / Conflicting Context</h3></div>
                    <div className="muted" style={{ marginBottom: 8 }}>Load context decision details to inspect missing or conflicting memory.</div>
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
              {showLegacyContextPacks && (
                <ContextPackPanel
                  contextPacks={contextPacks}
                  summary={summary}
                  onLoadDetail={onLoadContextPacks}
                  detailLoading={Boolean(detailLoading?.contextPacks)}
                  detailLoaded={Boolean(detailLoaded?.contextPacks)}
                />
              )}
            </div>
          )}
        </section>
      )}

      {openSection === 'models' && (
        <section className="card runStudioPanel runStudioDetailShelf">
          <div className="runStudioPanelHeader">
            <div>
              <h3>Models & cost</h3>
              <div className="muted">Provider catalog, privacy tiers, routing hints, and token usage.</div>
            </div>
          </div>
          <ModelCatalogPanel threadId={threadId} runId={summary?.now?.state?.current_run_id || null} summary={summary} />
        </section>
      )}

      {openSection === 'diagnostics' && (
        <section className="card runStudioPanel runStudioDetailShelf">
          <div className="runStudioPanelHeader">
            <div>
              <h3>Advanced diagnostics</h3>
              <div className="muted">Raw traces, team selection, graph compression, legacy memory projection, and power tools.</div>
            </div>
            <button onClick={() => setShowDiagnostics((value) => !value)}>{showDiagnostics ? 'Hide extra tools' : 'Show extra tools'}</button>
          </div>
          <div className="runStudioGrid runStudioGrid--bottom">
            <HarnessSpecPanel harnessSpec={harnessSpec} harnessSummary={harnessSummary} />
            <FocusedAuditTimelinePanel
              auditTimeline={auditTimeline}
              onFocusNode={onFocusNode}
              onOpenNode={onOpenNode}
              onFocusTrace={onFocusTrace}
              onOpenTrace={onOpenTrace}
            />
          </div>
          <div className="runStudioGrid runStudioGrid--bottom">
            <TeamRecommendationPanel
              threadId={threadId}
              teamSelection={teamSelection}
              onLoadDetail={onLoadTeamSelection}
              onActionComplete={onLoadTeamSelection}
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
          </div>
          {focusedRunId && (
            <div className="runStudioGrid runStudioGrid--bottom">
              <ProjectionRetrievalPanel projectionRetrieval={projectionRetrieval} />
              <CrossReferencePanel
                crossReferences={crossReferences}
                onFocusNode={onFocusNode}
                onOpenNode={onOpenNode}
                onFocusTrace={onFocusTrace}
                onOpenTrace={onOpenTrace}
                onRefresh={onRefresh}
              />
            </div>
          )}
          {showDiagnostics && (
            <div className="runStudioDisclosureBody">
              <MemoryProjectionPanel
                memoryGraph={memoryGraph}
                onLoadDetail={onLoadMemoryGraph}
                detailLoading={Boolean(detailLoading?.memoryGraph)}
                detailLoaded={Boolean(detailLoaded?.memoryGraph)}
                onRefresh={onLoadMemoryGraph}
              />
              <GraphCompressionPanel graphCompression={graphCompression} />
              <ProjectionRetrievalPanel projectionRetrieval={projectionRetrieval} />
              <AdvancedToolsPanel
                onOpenGraph={onOpenGraph}
                onOpenRawTrace={onOpenRawTrace}
                onOpenAdvanced={onOpenAdvanced}
              />
            </div>
          )}
        </section>
      )}
    </div>
  )
}
