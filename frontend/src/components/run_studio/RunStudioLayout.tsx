import React from 'react'
import NowPanel from './NowPanel'
import AgentTeamPanel from './AgentTeamPanel'
import ContextDecisionPanel from './ContextDecisionPanel'
import EvidencePanel from './EvidencePanel'
import MissingContextPanel from './MissingContextPanel'
import AdvancedToolsPanel from './AdvancedToolsPanel'
import {
  type RunStudioAgentTeam,
  type RunStudioContextDecisions,
  type RunStudioEvidence,
  type RunStudioSummary,
} from './types'

type Props = {
  summary: RunStudioSummary | null
  team: RunStudioAgentTeam | null
  decisions: RunStudioContextDecisions | null
  evidence: RunStudioEvidence | null
  loading: boolean
  error: string
  onRefresh: () => void
  onOpenGraph: () => void
  onOpenRawTrace: () => void
  onOpenAdvanced: () => void
  onOpenNode: (nodeId: string) => void
  onOpenTrace: (nodeIds: string[]) => void
}

export default function RunStudioLayout({
  summary,
  team,
  decisions,
  evidence,
  loading,
  error,
  onRefresh,
  onOpenGraph,
  onOpenRawTrace,
  onOpenAdvanced,
  onOpenNode,
  onOpenTrace,
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
        <NowPanel summary={summary} />
        <AgentTeamPanel team={team} />
      </div>

      <div className="runStudioGrid runStudioGrid--bottom">
        <ContextDecisionPanel decisions={decisions} onOpenNode={onOpenNode} />
        <EvidencePanel evidence={evidence} onOpenNode={onOpenNode} onOpenTrace={onOpenTrace} />
      </div>

      <div className="runStudioGrid runStudioGrid--bottom">
        <MissingContextPanel decisions={decisions} onOpenNode={onOpenNode} onOpenConflict={onOpenTrace} />
        <AdvancedToolsPanel
          onOpenGraph={onOpenGraph}
          onOpenRawTrace={onOpenRawTrace}
          onOpenAdvanced={onOpenAdvanced}
        />
      </div>
    </div>
  )
}
