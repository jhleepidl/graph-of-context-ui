import React from 'react'
import { type ScopeProjection } from './types'

type Props = {
  scopeProjection: ScopeProjection | null
}

export default function ScopeGrantPanel({ scopeProjection }: Props) {
  const grantCounts = scopeProjection?.grant_counts || {}
  const items = scopeProjection?.items || []
  const denseRows = items
    .map((item) => ({
      label: item.display_label || item.scope_id || 'scope',
      grants: item.grant_labels || [],
    }))
    .filter((item) => item.grants.length > 0)

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3 style={{ margin: 0 }}>Scope Grants</h3>
          <div className="muted">Shared memory is no longer implicit. Grants show exactly which shared classes were exposed.</div>
        </div>
        <div className="runStudioMetaRow">
          {Object.keys(grantCounts).length === 0 ? (
            <span className="pill">no explicit grants</span>
          ) : Object.entries(grantCounts).map(([key, value]) => (
            <span key={`grant-total-${key}`} className="pill">{key}: {value}</span>
          ))}
        </div>
      </div>

      {denseRows.length === 0 ? (
        <div className="muted">Every scope is currently isolated or grant metadata was not emitted.</div>
      ) : (
        <div className="runStudioSkillStack">
          {denseRows.map((row) => (
            <div key={row.label} className="runStudioSkillRow">
              <span className="runStudioSkillName">{row.label}</span>
              <div className="runStudioMetaRow">
                {row.grants.map((grant) => (
                  <span key={`${row.label}:${grant}`} className="pill">{grant}</span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
