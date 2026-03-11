import React from 'react'
import { type RunStudioSkillUsage, type RunStudioSummary } from './types'

type Props = {
  skillUsage: RunStudioSkillUsage | null
  summary: RunStudioSummary | null
}

export default function SkillUsagePanel({ skillUsage, summary }: Props) {
  const fallbackItems = summary?.current_run_skills?.skill_usage || []
  const items = (skillUsage?.items && skillUsage.items.length > 0) ? skillUsage.items : fallbackItems

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Skill Usage</h3>
        <div className="runStudioMetaRow">
          <span className="pill">events: {items.length}</span>
          <span className="pill">run: {summary?.current_run_skills?.run_id ? String(summary.current_run_skills.run_id).slice(0, 8) : '-'}</span>
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
