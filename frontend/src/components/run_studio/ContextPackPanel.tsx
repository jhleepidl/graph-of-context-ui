import React from 'react'
import { type RunStudioContextPacks, type RunStudioSummary } from './types'
import { selectEffectiveContextPacks } from './selectors'

type Props = {
  contextPacks: RunStudioContextPacks | null
  summary: RunStudioSummary | null
  onLoadDetail?: () => void
  detailLoading?: boolean
  detailLoaded?: boolean
}

export default function ContextPackPanel({
  contextPacks,
  summary,
  onLoadDetail,
  detailLoading,
  detailLoaded,
}: Props) {
  const effectiveContextPacks = selectEffectiveContextPacks(summary, contextPacks)
  const items = effectiveContextPacks?.items || []
  const authority = effectiveContextPacks?.runtime_authority || summary?.runtime_authority
  const mode = String(authority?.mode || effectiveContextPacks?.mode || summary?.mode || 'standalone')
  const contextSource = String(
    authority?.context_source || effectiveContextPacks?.context_source || summary?.context_source || 'local',
  )
  const degradedMode = Boolean(authority?.degraded_mode ?? effectiveContextPacks?.degraded_mode ?? summary?.degraded_mode)
  const fallbackReason = String(
    authority?.fallback_reason || effectiveContextPacks?.fallback_reason || summary?.fallback_reason || '',
  ).trim()

  const sharedCount = items.reduce((acc, item) => acc + Number(item.shared_items_count || 0), 0)
  const roleSpecificCount = items.reduce((acc, item) => acc + Number(item.role_specific_items_count || 0), 0)
  const skillScopedCount = items.reduce(
    (acc, item) => acc + (item.skill_items || []).reduce((inner, sItem) => inner + Number(sItem.count || 0), 0),
    0,
  )

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Legacy Context Packs</h3>
        <div className="row" style={{ marginBottom: 0 }}>
          <span className="pill">mode: {mode}</span>
          <span className="pill">context: {contextSource}</span>
          {degradedMode && <span className="pill">degraded fallback</span>}
          <span className="pill">packs: {items.length}</span>
          <span className="pill">legacy compatibility</span>
          <span className="pill">shared: {sharedCount}</span>
          <span className="pill">role-specific: {roleSpecificCount}</span>
          <span className="pill">skill-scoped: {skillScopedCount}</span>
          {onLoadDetail && (
            <button className="tiny" onClick={onLoadDetail} disabled={Boolean(detailLoading)}>
              {detailLoading ? 'Loading...' : (detailLoaded ? 'Refresh detail' : 'Load detail')}
            </button>
          )}
        </div>
      </div>
      {degradedMode && fallbackReason && (
        <div className="runStudioWarning">
          <b>Fallback reason:</b> {fallbackReason}
        </div>
      )}

      <div className="runStudioList">
        {items.slice(0, 12).map((item, index) => (
          <article key={`${item.context_pack_id || 'context-pack'}:${item.target_runtime_agent_instance_id || 'runtime'}:${index}`} className="runStudioListItem">
            <div className="row" style={{ marginBottom: 4 }}>
              <span className="pill">{item.context_pack_id || 'context-pack'}</span>
              <span className="pill">scope: {item.scope || 'runtime'}</span>
              {item.target_runtime_agent_instance_id && (
                <span className="pill">runtime: {item.target_runtime_agent_instance_id}</span>
              )}
            </div>
            <div className="muted">
              shared: {item.shared_items_count || 0} | role-specific: {item.role_specific_items_count || 0}
            </div>
            {item.skill_items && item.skill_items.length > 0 && (
              <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
                {item.skill_items.slice(0, 6).map((skillItem) => (
                  <span key={`${skillItem.skill_id}:${skillItem.load_level || 'metadata_only'}`} className="pill">
                    {skillItem.skill_id} ({skillItem.load_level || 'metadata_only'}:{skillItem.count || 0})
                  </span>
                ))}
              </div>
            )}
            {(item.missing_items?.length || 0) > 0 && (
              <div className="muted">missing: {(item.missing_items || []).slice(0, 3).map((x) => String(x)).join(' | ')}</div>
            )}
            {(item.conflicts?.length || 0) > 0 && (
              <div className="muted">conflicts: {(item.conflicts || []).slice(0, 3).map((x) => String(x)).join(' | ')}</div>
            )}
          </article>
        ))}
        {items.length === 0 && (
          <div className="muted">No legacy context pack projection is active for this run.</div>
        )}
      </div>
    </section>
  )
}
