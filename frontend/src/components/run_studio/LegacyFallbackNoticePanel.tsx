import React from 'react'
import { type ControlPlaneSummaryProjection } from './types'

type Props = {
  summary: ControlPlaneSummaryProjection | null
}

export default function LegacyFallbackNoticePanel({ summary }: Props) {
  if (!summary) return null
  if (!summary.legacyFallback && !summary.degradedMode) return null

  return (
    <section className="card runStudioPanel runStudioLegacyNotice">
      <div className="runStudioPanelHeader">
        <div>
          <h3 style={{ margin: 0 }}>Compatibility / fallback state</h3>
          <div className="muted">This run is not being rendered from a full structured control-plane payload.</div>
        </div>
        <div className="runStudioMetaRow">
          {summary.legacyFallback && <span className="pill">legacy fallback</span>}
          {summary.degradedMode && <span className="pill">degraded mode</span>}
        </div>
      </div>
      {summary.fallbackReason ? (
        <div className="runStudioWarning"><b>Reason:</b> {summary.fallbackReason}</div>
      ) : (
        <div className="muted">Selectors are falling back to older team/runtime fields. The control-plane view may be partial.</div>
      )}
    </section>
  )
}
