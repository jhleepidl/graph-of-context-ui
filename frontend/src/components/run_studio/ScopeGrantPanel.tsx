import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../../api'
import { type RunStudioAgentTeam, type ScopeProjection } from './types'

type Props = {
  scopeProjection: ScopeProjection | null
  legacyTeam?: RunStudioAgentTeam | null
  threadId?: string | null
  onSaved?: () => void
}

type EditorRow = {
  key: string
  state: 'active' | 'pending'
  teamName: string
  agentId: string
  agentName: string
  roleId: string
  visibilityMode: string
  grants: string[]
  contextTypes: string[]
  publishTargets: string[]
  queryTemplate: string
  softTokens: string
  hardTokens: string
  scopeId: string
}

type Draft = {
  visibilityMode: string
  grants: string[]
  contextTypesText: string
  publishTargetsText: string
  queryTemplate: string
  softTokens: string
  hardTokens: string
}

const GRANT_OPTIONS = [
  { id: 'shared_summary', label: 'Shared summary' },
  { id: 'global_memory', label: 'Global memory' },
  { id: 'conversation_tail', label: 'Conversation tail' },
  { id: 'upstream_results', label: 'Upstream results' },
  { id: 'upstream_summaries', label: 'Upstream summaries' },
  { id: 'user_pinned_nodes', label: 'User pinned nodes' },
  { id: 'explicit_uploaded_files', label: 'Uploaded files' },
] as const

const CONTEXT_HINTS = ['news', 'evidence', 'citations', 'workspace', 'code', 'messages', 'files', 'risks']
const PUBLISH_HINTS = ['scratch', 'evidence_bundle', 'handoff_summary', 'review_findings', 'final_draft']

function asObject(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
}

function toArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : []
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : String(value || '').trim()
}

function csv(values: string[]): string {
  return values.filter(Boolean).join(', ')
}

function splitCsv(value: string): string[] {
  const out: string[] = []
  const seen = new Set<string>()
  value.split(',').map((entry) => entry.trim().toLowerCase()).filter(Boolean).forEach((entry) => {
    if (seen.has(entry)) return
    seen.add(entry)
    out.push(entry)
  })
  return out
}

function buildRows(teamConfig: RunStudioAgentTeam['team_config'] | undefined, configuredItems: RunStudioAgentTeam['configured_items'] | undefined): EditorRow[] {
  const scopeByStateAgent = new Map<string, string>()
  ;(configuredItems || []).forEach((item) => {
    const state = cleanText((item as { config_state?: string | null }).config_state).toLowerCase()
    const agentId = cleanText(item.agent_id || item.name).toLowerCase()
    if (!state || !agentId) return
    scopeByStateAgent.set(`${state}:${agentId}`, cleanText(item.scope_id))
  })

  const rows: EditorRow[] = []
  ;(['active', 'pending'] as const).forEach((state) => {
    const team = asObject(teamConfig?.[`${state}_team` as 'active_team' | 'pending_team'])
    if (Object.keys(team).length === 0) return
    const teamName = cleanText(team.team_name || `${state} team`) || `${state} team`
    toArray<Record<string, unknown>>(team.agents).forEach((agent, index) => {
      const contextPolicy = asObject(agent.context_policy || agent.contextPolicy)
      const reads = asObject(contextPolicy.reads)
      const writes = asObject(contextPolicy.writes)
      const budget = asObject(contextPolicy.default_budget || contextPolicy.defaultBudget)
      const agentId = cleanText(agent.agent_id || agent.agentId || agent.id || agent.name)
      if (!agentId) return
      const key = `${state}:${agentId}`
      rows.push({
        key,
        state,
        teamName,
        agentId,
        agentName: cleanText(agent.name || agentId) || agentId,
        roleId: cleanText(agent.role || agent.role_id || agent.roleId || 'researcher') || 'researcher',
        visibilityMode: cleanText(contextPolicy.base_mode || contextPolicy.baseMode || 'scoped_context') || 'scoped_context',
        grants: toArray<string>(reads.grants).map((entry) => cleanText(entry).toLowerCase()).filter(Boolean),
        contextTypes: toArray<string>(reads.context_types || reads.contextTypes).map((entry) => cleanText(entry).toLowerCase()).filter(Boolean),
        publishTargets: toArray<string>(writes.publish_targets || writes.publishTargets).map((entry) => cleanText(entry).toLowerCase()).filter(Boolean),
        queryTemplate: cleanText(reads.query_template || reads.queryTemplate),
        softTokens: cleanText(budget.soft_tokens ?? budget.softTokens ?? ''),
        hardTokens: cleanText(budget.hard_tokens ?? budget.hardTokens ?? ''),
        scopeId: scopeByStateAgent.get(key.toLowerCase()) || `configured_scope_${index + 1}`,
      })
    })
  })
  return rows
}

function initialDraft(row: EditorRow): Draft {
  return {
    visibilityMode: row.visibilityMode,
    grants: [...row.grants],
    contextTypesText: csv(row.contextTypes),
    publishTargetsText: csv(row.publishTargets),
    queryTemplate: row.queryTemplate,
    softTokens: row.softTokens,
    hardTokens: row.hardTokens,
  }
}

export default function ScopeGrantPanel({ scopeProjection, legacyTeam, threadId, onSaved }: Props) {
  const grantCounts = scopeProjection?.grant_counts || {}
  const items = scopeProjection?.items || []
  const denseRows = items
    .map((item) => ({
      label: item.display_label || item.scope_id || 'scope',
      grants: item.grant_labels || [],
    }))
    .filter((item) => item.grants.length > 0)

  const editorRows = useMemo(
    () => buildRows(legacyTeam?.team_config, legacyTeam?.configured_items),
    [legacyTeam?.configured_items, legacyTeam?.team_config],
  )
  const [drafts, setDrafts] = useState<Record<string, Draft>>({})
  const [saving, setSaving] = useState<Record<string, boolean>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [savedAt, setSavedAt] = useState<Record<string, string>>({})

  useEffect(() => {
    const next: Record<string, Draft> = {}
    editorRows.forEach((row) => {
      next[row.key] = initialDraft(row)
    })
    setDrafts(next)
  }, [editorRows])

  const updateDraft = (key: string, patch: Partial<Draft>) => {
    setDrafts((current) => ({
      ...current,
      [key]: {
        ...(current[key] || initialDraft(editorRows.find((row) => row.key === key) || editorRows[0])),
        ...patch,
      },
    }))
  }

  const toggleGrant = (key: string, grantId: string) => {
    const current = drafts[key] || initialDraft(editorRows.find((row) => row.key === key) || editorRows[0])
    const exists = current.grants.includes(grantId)
    updateDraft(key, {
      grants: exists ? current.grants.filter((entry) => entry !== grantId) : [...current.grants, grantId],
    })
  }

  const appendHint = (key: string, field: 'contextTypesText' | 'publishTargetsText', value: string) => {
    const current = drafts[key]
    if (!current) return
    const items = splitCsv(current[field])
    if (!items.includes(value)) items.push(value)
    updateDraft(key, { [field]: csv(items) } as Partial<Draft>)
  }

  const handleSave = async (row: EditorRow) => {
    if (!threadId) return
    const current = drafts[row.key]
    if (!current) return
    setSaving((state) => ({ ...state, [row.key]: true }))
    setErrors((state) => ({ ...state, [row.key]: '' }))
    try {
      await api.patchThreadTeamAgentContextPolicy(threadId, {
        team_state: row.state,
        agent_id: row.agentId,
        visibility_mode: current.visibilityMode || 'scoped_context',
        grants: current.grants,
        context_types: splitCsv(current.contextTypesText),
        publish_targets: splitCsv(current.publishTargetsText),
        query_template: current.queryTemplate.trim() || null,
        soft_tokens: current.softTokens.trim() ? Number(current.softTokens) : null,
        hard_tokens: current.hardTokens.trim() ? Number(current.hardTokens) : null,
      })
      setSavedAt((state) => ({ ...state, [row.key]: new Date().toLocaleTimeString() }))
      if (onSaved) onSaved()
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save context policy'
      setErrors((state) => ({ ...state, [row.key]: message }))
    } finally {
      setSaving((state) => ({ ...state, [row.key]: false }))
    }
  }

  const handleReset = (row: EditorRow) => {
    setDrafts((current) => ({
      ...current,
      [row.key]: initialDraft(row),
    }))
    setErrors((state) => ({ ...state, [row.key]: '' }))
  }

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3 style={{ margin: 0 }}>Scope Grants</h3>
          <div className="muted">Shared memory is explicit. Edit per-agent grants here and GoC will re-project the scope on refresh.</div>
        </div>
        <div className="runStudioMetaRow">
          {Object.keys(grantCounts).length === 0 ? (
            <span className="pill">no explicit grants</span>
          ) : Object.entries(grantCounts).map(([key, value]) => (
            <span key={`grant-total-${key}`} className="pill">{key}: {value}</span>
          ))}
        </div>
      </div>

      {editorRows.length > 0 && (
        <>
          <div className="runStudioWarning" style={{ marginBottom: 10 }}>
            <b>Editing policy:</b> changes update the persisted team config. In-flight runs may keep their current materialized scope until the next refresh or execution step.
          </div>
          <div className="runStudioGrantEditorGrid">
            {editorRows.map((row) => {
              const draft = drafts[row.key] || initialDraft(row)
              return (
                <article key={row.key} className="runStudioAgentCard runStudioGrantEditorCard">
                  <div className="row" style={{ marginBottom: 6 }}>
                    <b>{row.agentName}</b>
                    <span className="pill">{row.state}</span>
                  </div>
                  <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                    <span className="pill">team: {row.teamName}</span>
                    <span className="pill">role: {row.roleId}</span>
                    <span className="pill">scope: {row.scopeId}</span>
                  </div>

                  <div className="runStudioAgentSkillSection" style={{ marginTop: 0, borderTop: 'none', paddingTop: 0 }}>
                    <div className="runStudioAgentSkillSectionLabel">Memory grants</div>
                    <div className="runStudioGrantCheckboxGrid">
                      {GRANT_OPTIONS.map((grant) => (
                        <label key={`${row.key}:${grant.id}`} className="runStudioGrantCheckboxLabel">
                          <input
                            type="checkbox"
                            checked={draft.grants.includes(grant.id)}
                            onChange={() => toggleGrant(row.key, grant.id)}
                          />
                          <span>{grant.label}</span>
                        </label>
                      ))}
                    </div>
                  </div>

                  <div className="runStudioGrantFormGrid">
                    <label className="runStudioFieldLabel">
                      <span>Visibility mode</span>
                      <select value={draft.visibilityMode} onChange={(event) => updateDraft(row.key, { visibilityMode: event.target.value })}>
                        <option value="scoped_context">scoped_context</option>
                        <option value="shared_memory">shared_memory</option>
                        <option value="shared_only">shared_only</option>
                      </select>
                    </label>
                    <label className="runStudioFieldLabel">
                      <span>Soft token budget</span>
                      <input type="number" min={200} max={6000} value={draft.softTokens} onChange={(event) => updateDraft(row.key, { softTokens: event.target.value })} />
                    </label>
                    <label className="runStudioFieldLabel">
                      <span>Hard token budget</span>
                      <input type="number" min={200} max={8000} value={draft.hardTokens} onChange={(event) => updateDraft(row.key, { hardTokens: event.target.value })} />
                    </label>
                  </div>

                  <label className="runStudioFieldLabel" style={{ marginTop: 8 }}>
                    <span>Context types</span>
                    <input value={draft.contextTypesText} onChange={(event) => updateDraft(row.key, { contextTypesText: event.target.value })} placeholder="news, evidence, citations" />
                  </label>
                  <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                    {CONTEXT_HINTS.map((hint) => (
                      <button key={`${row.key}:ctxhint:${hint}`} type="button" className="ghost" onClick={() => appendHint(row.key, 'contextTypesText', hint)}>{hint}</button>
                    ))}
                  </div>

                  <label className="runStudioFieldLabel">
                    <span>Publish targets</span>
                    <input value={draft.publishTargetsText} onChange={(event) => updateDraft(row.key, { publishTargetsText: event.target.value })} placeholder="evidence_bundle, handoff_summary" />
                  </label>
                  <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
                    {PUBLISH_HINTS.map((hint) => (
                      <button key={`${row.key}:pubhint:${hint}`} type="button" className="ghost" onClick={() => appendHint(row.key, 'publishTargetsText', hint)}>{hint}</button>
                    ))}
                  </div>

                  <label className="runStudioFieldLabel">
                    <span>Query template</span>
                    <textarea rows={3} value={draft.queryTemplate} onChange={(event) => updateDraft(row.key, { queryTemplate: event.target.value })} placeholder="최근 뉴스, 이벤트, 발표, 가이던스" />
                  </label>

                  {errors[row.key] && <div className="runStudioWarning" style={{ marginTop: 8 }}>{errors[row.key]}</div>}
                  {savedAt[row.key] && !errors[row.key] && <div className="muted" style={{ marginTop: 8 }}>Saved at {savedAt[row.key]}</div>}

                  <div className="row" style={{ marginTop: 10, justifyContent: 'flex-end' }}>
                    <button type="button" className="ghost" onClick={() => handleReset(row)} disabled={Boolean(saving[row.key])}>Reset</button>
                    <button type="button" onClick={() => void handleSave(row)} disabled={!threadId || Boolean(saving[row.key])}>
                      {saving[row.key] ? 'Saving…' : 'Save grants'}
                    </button>
                  </div>
                </article>
              )
            })}
          </div>
        </>
      )}

      {editorRows.length === 0 && (denseRows.length === 0 ? (
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
      ))}
    </section>
  )
}
