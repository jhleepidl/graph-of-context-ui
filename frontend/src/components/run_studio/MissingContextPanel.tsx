import React from 'react'
import { type RunStudioContextDecisions } from './types'

type Props = {
  decisions: RunStudioContextDecisions | null
}

export default function MissingContextPanel({ decisions }: Props) {
  const missing = decisions?.missing || []
  const conflicting = decisions?.conflicting || []

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Missing / Conflicting Context</h3>
      </div>

      <div className="runStudioDualList">
        <div>
          <div className="muted" style={{ marginBottom: 6 }}>Missing</div>
          <div className="runStudioList">
            {missing.slice(0, 10).map((item, index) => (
              <article key={`${item.id || 'missing'}:${index}`} className="runStudioListItem">
                <div className="row" style={{ marginBottom: 4 }}>
                  <span className="pill">{item.type || 'MissingReference'}</span>
                </div>
                <div>{item.text || item.id || '(unresolved reference)'}</div>
                {item.reason && <div className="muted">{item.reason}</div>}
              </article>
            ))}
            {missing.length === 0 && <div className="muted">No explicit missing-context signals.</div>}
          </div>
        </div>

        <div>
          <div className="muted" style={{ marginBottom: 6 }}>Conflicts</div>
          <div className="runStudioList">
            {conflicting.slice(0, 10).map((item, index) => (
              <article key={`${item.edge_id || item.from_id || 'conflict'}:${index}`} className="runStudioListItem">
                <div className="row" style={{ marginBottom: 4 }}>
                  <span className="pill">{item.type || 'conflict'}</span>
                </div>
                <div>{item.from_text || item.from_id || '-'}</div>
                <div className="muted">vs</div>
                <div>{item.to_text || item.to_id || '-'}</div>
                {item.reason && <div className="muted">{item.reason}</div>}
              </article>
            ))}
            {conflicting.length === 0 && <div className="muted">No explicit conflict signals.</div>}
          </div>
        </div>
      </div>
    </section>
  )
}
