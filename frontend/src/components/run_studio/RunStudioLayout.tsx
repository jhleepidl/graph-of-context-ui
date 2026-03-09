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
}: Props) {
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
        {error && <div className="runStudioWarning"><b>Load error:</b> {error}</div>}
      </div>

      <div className="runStudioGrid runStudioGrid--top">
        <NowPanel summary={summary} />
        <AgentTeamPanel team={team} />
      </div>

      <div className="runStudioGrid runStudioGrid--bottom">
        <ContextDecisionPanel decisions={decisions} />
        <EvidencePanel evidence={evidence} />
      </div>

      <div className="runStudioGrid runStudioGrid--bottom">
        <MissingContextPanel decisions={decisions} />
        <AdvancedToolsPanel
          onOpenGraph={onOpenGraph}
          onOpenRawTrace={onOpenRawTrace}
          onOpenAdvanced={onOpenAdvanced}
        />
      </div>
    </div>
  )
}
