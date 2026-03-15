import React from 'react'
import {
  type AuthorityProjection,
  type RuntimeAuthorityProjection,
} from './types'

type Props = {
  authority: AuthorityProjection | null
  runtimeAuthority: RuntimeAuthorityProjection | null | undefined
}

export default function AuthorityPanel({ authority, runtimeAuthority }: Props) {
  const items = authority?.items || []
  const graphCount = authority?.graph_count ?? authority?.graph?.length ?? 0

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Authority</h3>
        <div className="runStudioMetaRow">
          <span className="pill">profiles: {authority?.count ?? items.length}</span>
          <span className="pill">graph entries: {graphCount}</span>
          {runtimeAuthority?.mode && <span className="pill">mode: {runtimeAuthority.mode}</span>}
          {runtimeAuthority?.plan_source && <span className="pill">plan: {runtimeAuthority.plan_source}</span>}
        </div>
      </div>

      <div className="runStudioList">
        {items.map((item, index) => (
          <article key={`${item.runtime_instance_id || item.authority_profile_id || 'authority'}:${index}`} className="runStudioListItem">
            <div className="row" style={{ marginBottom: 4 }}>
              <span className="pill">{item.display_label || item.runtime_instance_id || 'runtime agent'}</span>
              {item.authority_profile_id && <span className="pill">profile: {item.authority_profile_id}</span>}
              {item.managed_by && <span className="pill">managed by: {item.managed_by}</span>}
            </div>
            {(item.allowed_actions || []).length > 0 && (
              <div className="muted">allowed: {(item.allowed_actions || []).join(' | ')}</div>
            )}
            {(item.restricted_actions || []).length > 0 && (
              <div className="muted">denied: {(item.restricted_actions || []).join(' | ')}</div>
            )}
            {(item.approval_required_for || []).length > 0 && (
              <div className="muted">approval required: {(item.approval_required_for || []).join(' | ')}</div>
            )}
            {(!item.allowed_actions?.length && !item.restricted_actions?.length && !item.approval_required_for?.length) && (
              <div className="muted">Authority profile is present, but no action-level details were emitted.</div>
            )}
          </article>
        ))}

        {items.length === 0 && runtimeAuthority && (
          <article className="runStudioListItem">
            <div className="muted">
              Per-instance authority profiles are not present in this payload. Legacy authority still shows runtime mode, plan source,
              context source, team source, and skill source.
            </div>
            <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
              {runtimeAuthority.context_source && <span className="pill">context: {runtimeAuthority.context_source}</span>}
              {runtimeAuthority.conversation_team_source && <span className="pill">team: {runtimeAuthority.conversation_team_source}</span>}
              {runtimeAuthority.skill_catalog_source && <span className="pill">skills: {runtimeAuthority.skill_catalog_source}</span>}
              {runtimeAuthority.degraded_mode && <span className="pill">degraded fallback</span>}
            </div>
          </article>
        )}
      </div>
    </section>
  )
}
