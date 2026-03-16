import React from 'react'
import { type ControlPlaneSummaryProjection } from './types'

type Props = {
  summary: ControlPlaneSummaryProjection | null
}

export default function ControlPlaneSummaryPanel({ summary }: Props) {
  if (!summary) return null

  return (
    <section className="card runStudioPanel runStudioHeroPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3 style={{ margin: 0 }}>Control Plane Summary</h3>
          <div className="muted">Current orchestration posture and runtime composition</div>
        </div>
        <div className="runStudioMetaRow" style={{ marginBottom: 0 }}>
          <span className="pill">mode: {summary.mode}</span>
          <span className="pill">plan: {summary.planSource}</span>
          <span className="pill">context: {summary.contextSource}</span>
          <span className="pill">team: {summary.teamSource}</span>
          <span className="pill">skills: {summary.skillSource}</span>
          {summary.legacyFallback && <span className="pill">legacy fallback</span>}
          {summary.degradedMode && <span className="pill">degraded fallback</span>}
        </div>
      </div>

      <div className="runStudioNowGrid">
        <div className="runStudioNowItem">
          <div className="muted">Supervisor</div>
          <div>{summary.supervisorEnabled ? (summary.supervisorMode || 'enabled') : 'disabled'}</div>
        </div>
        <div className="runStudioNowItem">
          <div className="muted">Runtime Agents</div>
          <div>{summary.runtimeAgentCount}</div>
        </div>
        <div className="runStudioNowItem">
          <div className="muted">Parallel / Collaboration</div>
          <div>{summary.parallelGroupCount} groups / {summary.collaborationCount} cells</div>
        </div>
        <div className="runStudioNowItem">
          <div className="muted">Checkpoints</div>
          <div>{summary.checkpointCount}</div>
        </div>
      </div>

      <div className="runStudioMetaRow">
        <span className="pill">preset-backed: {summary.presetCount}</span>
        <span className="pill">synthesized: {summary.synthesizedCount}</span>
        {summary.reviewerPresent && <span className="pill">reviewer present</span>}
        {summary.synthesizerPresent && <span className="pill">synthesizer present</span>}
      </div>

      {summary.fallbackReason && (
        <div className="runStudioWarning"><b>Fallback reason:</b> {summary.fallbackReason}</div>
      )}
    </section>
  )
}
