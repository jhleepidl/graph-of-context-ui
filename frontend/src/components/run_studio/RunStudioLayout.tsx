import React from 'react'
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

  return (
    <div className="runStudioLayout">
      <div className="card runStudioHeaderCard">
        <div className="runStudioPanelHeader">
          <div>
            <h2 style={{ margin: 0 }}>Run Studio</h2>
            <div className="muted">
              {summary?.thread?.title || 'Untitled thread'} | context: {summary?.context_set?.name || 'default'}
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

      <ControlPlaneSummaryPanel summary={controlPlaneSummary} skillOverview={skillAttachmentOverview} />
      <LegacyFallbackNoticePanel summary={controlPlaneSummary} />

      <ExecutionMapPanel
        orchestration={orchestration}
        teamView={teamView}
        collaboration={collaboration}
        checkpoints={checkpoints}
      />

      <div className="runStudioGrid runStudioGrid--bottom">
        <ScopeMapPanel scopeProjection={scopeProjection} />
        <VisibilityPanel visibilityProjection={visibilityProjection} />
      </div>

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
              <h3>Runtime Agents</h3>
            </div>
            <div className="muted" style={{ marginBottom: 8 }}>
              Runtime team detail is available on demand.
            </div>
            <button onClick={onLoadAgentTeam} disabled={Boolean(detailLoading?.agentTeam)}>
              {detailLoading?.agentTeam ? 'Loading...' : 'Load detail'}
            </button>
          </section>
        )}
        <AttachedSkillsPanel summary={summary} team={effectiveTeam} />
      </div>

      <WhyThisTeamPanel teamView={teamView} whyThisTeam={whyThisTeam} />

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

      <div className="runStudioGrid runStudioGrid--bottom">
        <ScopeGrantPanel
          scopeProjection={scopeProjection}
          legacyTeam={effectiveTeam}
          threadId={summary?.thread?.id || null}
          onSaved={onRefresh}
        />
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

      <div className="runStudioGrid runStudioGrid--bottom">
        <OrchestrationPanel orchestration={orchestration} checkpoints={checkpoints} teamView={teamView} />
      </div>

      <div className="runStudioGrid runStudioGrid--bottom">
        <CollaborationPanel collaboration={collaboration} />
        <CheckpointPanel checkpoints={checkpoints} />
      </div>

      <div className="runStudioGrid runStudioGrid--bottom">
        <AuthorityPanel authority={authorityProjection} runtimeAuthority={runtimeAuthority} />
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
        <MemoryProjectionPanel
          memoryGraph={memoryGraph}
          onLoadDetail={onLoadMemoryGraph}
          detailLoading={Boolean(detailLoading?.memoryGraph)}
          detailLoaded={Boolean(detailLoaded?.memoryGraph)}
          onRefresh={onLoadMemoryGraph}
        />
      </div>

      <div className="runStudioGrid runStudioGrid--bottom">
        <SkillUsagePanel
          skillUsage={skillUsage}
          summary={summary}
          onLoadDetail={onLoadSkillUsage}
          detailLoading={Boolean(detailLoading?.skillUsage)}
          detailLoaded={Boolean(detailLoaded?.skillUsage)}
        />
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

        <AdvancedToolsPanel
          onOpenGraph={onOpenGraph}
          onOpenRawTrace={onOpenRawTrace}
          onOpenAdvanced={onOpenAdvanced}
        />
      </div>
    </div>
  )
}
