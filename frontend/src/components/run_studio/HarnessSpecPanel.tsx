import React from 'react'
import { type RunStudioHarnessSpec, type RunStudioHarnessSummary } from './types'

type Props = {
  harnessSpec: RunStudioHarnessSpec | null
  harnessSummary: RunStudioHarnessSummary | null
}

export default function HarnessSpecPanel({ harnessSpec, harnessSummary }: Props) {
  if (!harnessSpec && !harnessSummary) return null
  const summary = harnessSummary || null
  const resolvedRoleEntries = Object.entries(summary?.resolved_role_delivery || {})
  const deliveryPolicy = summary?.delivery_policy || null
  return (
    <div className="card">
      <div className="runStudioPanelHeader">
        <h3 style={{ margin: 0 }}>Harness Spec</h3>
      </div>
      <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
        {summary?.name && <span className="pill">{summary.name}</span>}
        {summary?.spec_hash && <span className="pill">spec: {summary.spec_hash}</span>}
        {deliveryPolicy?.default_delivery_mode && <span className="pill">delivery: {deliveryPolicy.default_delivery_mode}</span>}
        {summary?.compression_enabled !== undefined && <span className="pill">compression: {summary.compression_enabled ? 'on' : 'off'}</span>}
        {summary?.shareable !== undefined && <span className="pill">shareable: {summary.shareable ? 'yes' : 'no'}</span>}
        {deliveryPolicy?.default_budget_tier && <span className="pill">budget: {deliveryPolicy.default_budget_tier}</span>}
        {deliveryPolicy?.default_risk_level && <span className="pill">risk: {deliveryPolicy.default_risk_level}</span>}
      </div>
      {summary?.description && <div className="muted" style={{ marginTop: 8 }}>{summary.description}</div>}
      {summary?.tags?.length ? <div className="runStudioMetaRow" style={{ marginTop: 8 }}>{summary.tags.map((tag) => <span key={tag} className="pill">{tag}</span>)}</div> : null}
      {resolvedRoleEntries.length ? (
        <div style={{ marginTop: 12 }}>
          <div className="muted" style={{ marginBottom: 6 }}>Role delivery</div>
          <div className="kvTable">
            {resolvedRoleEntries.slice(0, 10).map(([roleId, delivery]) => {
              const mode = typeof delivery === 'string' ? delivery : String(delivery?.delivery_mode || '')
              const effectiveRole = typeof delivery === 'string' ? '' : String(delivery?.effective_role_id || '')
              const badge = effectiveRole && effectiveRole !== roleId ? `${mode} → ${effectiveRole}` : mode
              return (
                <div key={roleId} className="kvRow">
                  <div>{roleId}</div>
                  <div>{badge}</div>
                </div>
              )
            })}
          </div>
        </div>
      ) : null}
      {harnessSpec?.compression_policy ? (
        <div style={{ marginTop: 12 }}>
          <div className="muted" style={{ marginBottom: 6 }}>Compression policy</div>
          <pre className="codeBlock" style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(harnessSpec.compression_policy, null, 2)}</pre>
        </div>
      ) : null}
    </div>
  )
}
