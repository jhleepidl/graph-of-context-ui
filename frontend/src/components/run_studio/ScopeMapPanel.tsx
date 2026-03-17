import React from 'react'
import { type ScopeProjection } from './types'

type Props = {
  scopeProjection: ScopeProjection | null
}

export default function ScopeMapPanel({ scopeProjection }: Props) {
  const items = scopeProjection?.items || []
  const grantCounts = scopeProjection?.grant_counts || {}
  const visibilityCounts = scopeProjection?.visibility_counts || {}
  const mode = String(scopeProjection?.context_runtime_mode || 'shared_memory')
  const legacyCount = Number(scopeProjection?.legacy_context_pack_count || 0)
  const legacyEnabled = Boolean(scopeProjection?.legacy_context_packs_enabled)
  const legacyStrategy = String(scopeProjection?.legacy_context_strategy || 'disabled')
  const projectionNote = String(scopeProjection?.scope_projection_note || '').trim()

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3 style={{ margin: 0 }}>Visibility / Scope Map</h3>
          <div className="muted">Who sees what, with explicit grants and materialized scope boundaries.</div>
        </div>
        <div className="runStudioMetaRow">
          <span className="pill">mode: {mode}</span>
          <span className="pill">scopes: {scopeProjection?.count ?? items.length}</span>
          {legacyCount > 0 && <span className="pill">legacy packs: {legacyCount}</span>}
          {legacyEnabled && <span className="pill">legacy active</span>}
          {legacyCount > 0 && !legacyEnabled && <span className="pill">legacy: {legacyStrategy}</span>}
          {Object.entries(visibilityCounts).map(([key, value]) => (
            <span key={`visibility-${key}`} className="pill">{key}: {value}</span>
          ))}
        </div>
      </div>

      {projectionNote && <div className="runStudioWarning"><b>Scope note:</b> {projectionNote}</div>}

      {Object.keys(grantCounts).length > 0 && (
        <div className="runStudioMetaRow" style={{ marginBottom: 10 }}>
          {Object.entries(grantCounts).map(([key, value]) => (
            <span key={`grant-${key}`} className="pill">grant {key}: {value}</span>
          ))}
        </div>
      )}

      {items.length === 0 ? (
        <div className="muted">No scoped runtime projection has been emitted yet.</div>
      ) : (
        <div className="runStudioAgentCardGrid">
          {items.map((item, index) => (
            <article key={`${item.scope_id || 'scope'}:${index}`} className="runStudioAgentCard">
              <div className="row" style={{ marginBottom: 6 }}>
                <b>{item.display_label || item.scope_id || 'scope'}</b>
                <span className="pill">{item.visibility_mode || 'scoped'}</span>
              </div>
              <div className="runStudioMetaRow" style={{ marginBottom: 6 }}>
                {item.slot_id && <span className="pill">slot: {item.slot_id}</span>}
                {item.context_set_id && <span className="pill">ctx: {item.context_set_id}</span>}
                {typeof item.token_estimate === 'number' && <span className="pill">tokens: {item.token_estimate}</span>}
                {typeof item.active_node_count === 'number' && <span className="pill">active nodes: {item.active_node_count}</span>}
                {item.authoritative_scope === true && <span className="pill">authoritative</span>}
                {item.selection_strategy && <span className="pill">strategy: {item.selection_strategy}</span>}
                {typeof item.seed_node_count === 'number' && item.seed_node_count > 0 && <span className="pill">seeds: {item.seed_node_count}</span>}
                {typeof item.candidate_node_count === 'number' && item.candidate_node_count > 0 && <span className="pill">candidates: {item.candidate_node_count}</span>}
                {typeof item.positive_candidate_count === 'number' && item.positive_candidate_count > 0 && <span className="pill">positive: {item.positive_candidate_count}</span>}
                {item.selection_confidence && <span className="pill">confidence: {item.selection_confidence}</span>}
                {item.truncated === true && <span className="pill">truncated</span>}
                {item.empty_scope === true && <span className="pill">empty scope</span>}
                {item.soft_budget_exceeded === true && <span className="pill">soft budget exceeded</span>}
              </div>
              {item.selection_reason && <div className="muted">why visible: {item.selection_reason}</div>}
              {item.selection_summary && <div className="muted">materialization: {item.selection_summary}</div>}
              {item.visibility_rationale && <div className="muted">boundary rationale: {item.visibility_rationale}</div>}
              {(item.context_types || []).length > 0 && (
                <div className="runStudioAgentSkillSection">
                  <div className="runStudioAgentSkillSectionLabel">Context types</div>
                  <div className="runStudioMetaRow">
                    {(item.context_types || []).map((entry) => (
                      <span key={`${item.scope_id || 'scope'}:ctx:${entry}`} className="pill">{entry}</span>
                    ))}
                  </div>
                </div>
              )}
              {(item.grant_labels || []).length > 0 && (
                <div className="runStudioAgentSkillSection">
                  <div className="runStudioAgentSkillSectionLabel">Granted memory</div>
                  <div className="runStudioMetaRow">
                    {(item.grant_labels || []).map((entry) => (
                      <span key={`${item.scope_id || 'scope'}:grant:${entry}`} className="pill">{entry}</span>
                    ))}
                  </div>
                </div>
              )}
              {(item.matched_query_terms || []).length > 0 && (
                <div className="runStudioAgentSkillSection">
                  <div className="runStudioAgentSkillSectionLabel">Matched query terms</div>
                  <div className="runStudioMetaRow">
                    {(item.matched_query_terms || []).map((entry) => (
                      <span key={`${item.scope_id || 'scope'}:term:${entry}`} className="pill">{entry}</span>
                    ))}
                  </div>
                </div>
              )}
              {(item.matched_context_types || []).length > 0 && (
                <div className="runStudioAgentSkillSection">
                  <div className="runStudioAgentSkillSectionLabel">Matched context types</div>
                  <div className="runStudioMetaRow">
                    {(item.matched_context_types || []).map((entry) => (
                      <span key={`${item.scope_id || 'scope'}:match-ctx:${entry}`} className="pill">{entry}</span>
                    ))}
                  </div>
                </div>
              )}
              {(item.rejected_positive_node_ids || []).length > 0 && (
                <div className="runStudioAgentSkillSection">
                  <div className="runStudioAgentSkillSectionLabel">Rejected broad candidates</div>
                  <div className="runStudioMetaRow">
                    {(item.rejected_positive_node_ids || []).map((entry) => (
                      <span key={`${item.scope_id || 'scope'}:rejected:${entry}`} className="pill">{entry}</span>
                    ))}
                  </div>
                </div>
              )}
              {(item.active_type_labels || []).length > 0 && (
                <div className="runStudioAgentSkillSection">
                  <div className="runStudioAgentSkillSectionLabel">Materialized content</div>
                  <div className="runStudioMetaRow">
                    {(item.active_type_labels || []).map((entry) => (
                      <span key={`${item.scope_id || 'scope'}:type:${entry}`} className="pill">{entry}</span>
                    ))}
                  </div>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
