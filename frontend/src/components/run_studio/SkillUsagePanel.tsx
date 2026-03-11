import React from 'react'
import { type RunStudioSkillUsage, type RunStudioSummary } from './types'
import { selectEffectiveSkillUsage } from './selectors'

type Props = {
  skillUsage: RunStudioSkillUsage | null
  summary: RunStudioSummary | null
  onLoadDetail?: () => void
  detailLoading?: boolean
  detailLoaded?: boolean
}

export default function SkillUsagePanel({
  skillUsage,
  summary,
  onLoadDetail,
  detailLoading,
  detailLoaded,
}: Props) {
  const effectiveSkillUsage = selectEffectiveSkillUsage(summary, skillUsage)
  const items = effectiveSkillUsage?.items || []

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Skill Usage</h3>
        <div className="row" style={{ marginBottom: 0 }}>
          <span className="pill">events: {items.length}</span>
          <span className="pill">run: {summary?.current_run_skills?.run_id ? String(summary.current_run_skills.run_id).slice(0, 8) : '-'}</span>
          {onLoadDetail && (
            <button className="tiny" onClick={onLoadDetail} disabled={Boolean(detailLoading)}>
              {detailLoading ? 'Loading...' : (detailLoaded ? 'Refresh detail' : 'Load detail')}
            </button>
          )}
        </div>
      </div>

      <div className="runStudioList">
        {items.slice(-14).reverse().map((item, index) => (
          <article key={`${item.skill_id}:${item.timestamp || item.node_id || index}:${index}`} className="runStudioListItem">
            <div className="row" style={{ marginBottom: 4 }}>
              <span className="pill">{item.skill_name || item.skill_id}</span>
              <span className="pill">{item.event_type || 'used'}</span>
              {item.load_level && <span className="pill">load: {item.load_level}</span>}
              {item.runtime_instance_id && <span className="pill">runtime: {item.runtime_instance_id}</span>}
            </div>
            <div className="muted">{item.timestamp || '-'}</div>
            {item.selection_reason && <div className="muted">reason: {item.selection_reason}</div>}
            {item.payload_summary && <div>{item.payload_summary}</div>}
          </article>
        ))}
        {items.length === 0 && <div className="muted">No skill usage events detected.</div>}
      </div>
    </section>
  )
}
