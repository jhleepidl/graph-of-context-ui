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

type Props = {
  summary: RunStudioSummary | null
  team: RunStudioAgentTeam | null
  decisions: RunStudioContextDecisions | null
  evidence: RunStudioEvidence | null
  contextPacks: RunStudioContextPacks | null
  skillUsage: RunStudioSkillUsage | null
  loading: boolean
  error: string
  onRefresh: () => void
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
  loading,
  error,
  onRefresh,
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
        <NowPanel summary={summary} team={team} />
        <AgentTeamPanel team={team} />
      </div>

      <div className="runStudioGrid runStudioGrid--bottom">
        <AttachedSkillsPanel summary={summary} team={team} />
        <ContextPackPanel contextPacks={contextPacks} summary={summary} />
      </div>

      <div className="runStudioGrid runStudioGrid--bottom">
        <ContextDecisionPanel
          decisions={decisions}
          onFocusNode={onFocusNode}
          onOpenNode={onOpenNode}
          onPinNode={onPinNode}
        />
        <EvidencePanel
          evidence={evidence}
          onFocusNode={onFocusNode}
          onOpenNode={onOpenNode}
          onFocusTrace={onFocusTrace}
          onOpenTrace={onOpenTrace}
          onAddToActive={onAddToActive}
          onPinNode={onPinNode}
        />
      </div>

      <div className="runStudioGrid runStudioGrid--bottom">
        <SkillUsagePanel skillUsage={skillUsage} summary={summary} />
        <MissingContextPanel
          decisions={decisions}
          onFocusNode={onFocusNode}
          onOpenNode={onOpenNode}
          onIncludeNode={onAddToActive}
          onPinNode={onPinNode}
          onFocusConflict={onFocusTrace}
          onOpenConflict={onOpenTrace}
        />
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
