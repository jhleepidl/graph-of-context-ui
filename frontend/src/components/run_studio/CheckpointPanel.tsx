import React from 'react'
import { type CheckpointProjection } from './types'

type Props = {
  checkpoints: CheckpointProjection | null
}

function statusClass(status: string): string {
  const clean = status.trim().toLowerCase()
  if (clean === 'running' || clean === 'active') return 'runStudioStatus--running'
  if (clean === 'pending' || clean === 'queued') return 'runStudioStatus--queued'
  if (clean === 'blocked' || clean === 'error') return 'runStudioStatus--blocked'
  if (clean === 'done' || clean === 'approved') return 'runStudioStatus--done'
  return 'runStudioStatus--idle'
}

export default function CheckpointPanel({ checkpoints }: Props) {
  const items = checkpoints?.items || []
  const counts = checkpoints?.counts || {}

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Checkpoints</h3>
        <div className="runStudioMetaRow">
          <span className="pill">total: {counts.total ?? items.length}</span>
          <span className="pill">human interrupts: {counts.human_interrupts ?? 0}</span>
          <span className="pill">approval required: {counts.approval_required ?? 0}</span>
          <span className="pill">blocking: {counts.blocking ?? 0}</span>
        </div>
      </div>

      <div className="runStudioList">
        {items.map((checkpoint, index) => {
          const status = String(checkpoint.status || 'pending')
          return (
            <article key={`${checkpoint.checkpoint_id || checkpoint.label || 'checkpoint'}:${index}`} className="runStudioListItem">
              <div className="row" style={{ marginBottom: 4 }}>
                <span className="pill">{checkpoint.label || checkpoint.kind || checkpoint.checkpoint_id || 'checkpoint'}</span>
                <span className={`pill runStudioStatus ${statusClass(status)}`}>{status}</span>
                {checkpoint.stage && <span className="pill">stage: {checkpoint.stage}</span>}
              </div>
              <div className="runStudioMetaRow">
                {checkpoint.requires_human && <span className="pill">human interrupt</span>}
                {checkpoint.requires_approval && <span className="pill">approval stop</span>}
                {checkpoint.blocking && <span className="pill">blocking</span>}
              </div>
              {checkpoint.selection_reason && <div className="muted">reason: {checkpoint.selection_reason}</div>}
            </article>
          )
        })}

        {items.length === 0 && (
          <div className="muted">No explicit execution checkpoints were emitted for this run scope.</div>
        )}
      </div>
    </section>
  )
}
