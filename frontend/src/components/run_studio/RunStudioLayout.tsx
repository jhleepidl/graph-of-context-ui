import React from 'react'
import NowPanel from './NowPanel'
import AgentTeamPanel from './AgentTeamPanel'
import AttachedSkillsPanel from './AttachedSkillsPanel'
import ContextPackPanel from './ContextPackPanel'
import ContextDecisionPanel from './ContextDecisionPanel'
import EvidencePanel from './EvidencePanel'
import MissingContextPanel from './MissingContextPanel'
import SkillUsagePanel from './SkillUsagePanel'
import AdvancedToolsPanel from './AdvancedToolsPanel'
import {
  type RunStudioAgentTeam,
  type RunStudioContextPacks,
  type RunStudioContextDecisions,
  type RunStudioEvidence,
  type RunStudioSkillUsage,
  type RunStudioSummary,
} from './types'
import { selectEffectiveAgentTeam } from './selectors'

type DetailState = {
  agentTeam?: boolean
  contextDecisions?: boolean
  evidence?: boolean
  contextPacks?: boolean
  skillUsage?: boolean
}

type Props = {
  summary: RunStudioSummary | null
  team: RunStudioAgentTeam | null
  decisions: RunStudioContextDecisions | null
  evidence: RunStudioEvidence | null
  contextPacks: RunStudioContextPacks | null
  skillUsage: RunStudioSkillUsage | null
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
  onOpenGraph: () => void
  onOpenRawTrace: () => void
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
  onOpenGraph,
  onOpenRawTrace,
  onOpenAdvanced,
  onFocusNode,
  onOpenNode,
  onFocusTrace,
  onOpenTrace,
  onAddToActive,
  onPinNode,
}: Props) {
  const memoryProjection = summary?.projections?.memory_context
  const effectiveTeam = selectEffectiveAgentTeam(summary, team)
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
            <span className="pill">core: {memoryProjection.core_count ?? 0}</span>
            <span className="pill">supporting: {memoryProjection.supporting_count ?? 0}</span>
            <span className="pill">execution/debug: {memoryProjection.execution_count ?? 0}</span>
          </div>
        )}
        {error && <div className="runStudioWarning"><b>Load error:</b> {error}</div>}
      </div>

      <div className="runStudioGrid runStudioGrid--top">
        <NowPanel summary={summary} team={effectiveTeam} />
        {effectiveTeam ? (
          <AgentTeamPanel team={effectiveTeam} />
        ) : (
          <section className="card runStudioPanel">
            <div className="runStudioPanelHeader">
              <h3>Agent Team</h3>
            </div>
            <div className="muted" style={{ marginBottom: 8 }}>
              Runtime team detail is available on demand.
            </div>
            <button onClick={onLoadAgentTeam} disabled={Boolean(detailLoading?.agentTeam)}>
              {detailLoading?.agentTeam ? 'Loading...' : 'Load detail'}
            </button>
          </section>
        )}
      </div>

      <div className="runStudioGrid runStudioGrid--bottom">
        <AttachedSkillsPanel summary={summary} team={effectiveTeam} />
        <ContextPackPanel
          contextPacks={contextPacks}
          summary={summary}
          onLoadDetail={onLoadContextPacks}
          detailLoading={Boolean(detailLoading?.contextPacks)}
          detailLoaded={Boolean(detailLoaded?.contextPacks)}
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
        <SkillUsagePanel
          skillUsage={skillUsage}
          summary={summary}
          onLoadDetail={onLoadSkillUsage}
          detailLoading={Boolean(detailLoading?.skillUsage)}
          detailLoaded={Boolean(detailLoaded?.skillUsage)}
        />
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
      </div>

      <div className="runStudioGrid" style={{ gridTemplateColumns: '1fr' }}>
        <AdvancedToolsPanel
          onOpenGraph={onOpenGraph}
          onOpenRawTrace={onOpenRawTrace}
          onOpenAdvanced={onOpenAdvanced}
        />
      </div>
    </div>
  )
}
