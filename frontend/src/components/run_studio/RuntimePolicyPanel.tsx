import React from 'react'

type Props = {
  summary?: any | null
}

function clean(value: unknown, fallback = '—'): string {
  const text = typeof value === 'string' ? value.trim() : String(value || '').trim()
  return text || fallback
}

export default function RuntimePolicyPanel({ summary }: Props) {
  const policy = summary?.runtime_policy_summary || {}
  const latest = policy.latest || {}
  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Runtime Policy</h3>
          <div className="muted">Task-loop execution policy resolved by ddalggak. Use this to verify workspace write and legacy fallback boundaries.</div>
        </div>
      </div>
      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
        <span className="pill">events: {policy.policy_event_count ?? 0}</span>
        <span className="pill">workspace writes: {policy.workspace_write_allowed_count ?? 0}</span>
        <span className="pill">manual fallback disabled: {policy.legacy_manual_fallback_disabled_count ?? 0}</span>
      </div>
      {latest ? (
        <div className="runStudioQuickList">
          <div className="runStudioQuickListItem">
            <div className="runStudioQuickListHeader">
              <span className="runStudioQuickListTitle">{clean(latest.execution_mode, 'execution policy')}</span>
              <span className="muted">{clean(latest.created_at)}</span>
            </div>
            <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
              <span className="pill">write: {clean(latest.workspace_write)}</span>
              <span className="pill">artifact: {clean(latest.artifact_delivery)}</span>
              <span className="pill">fallback: {clean(latest.legacy_manual_fallback)}</span>
            </div>
            {latest.decision ? <div className="muted" style={{ marginTop: 6 }}>{latest.decision}</div> : null}
          </div>
        </div>
      ) : (
        <div className="muted">No runtime policy resolution has been synced yet.</div>
      )}
    </section>
  )
}
