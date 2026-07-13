import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../../api'

type RecipeEvidence = {
  status?: string
  reason?: string
  evidence_scope?: string
  live_runs?: number
  passed_runs?: number
  success_rate?: number
  policy_violations?: number
}

type RecipeField = {
  id?: string
  label?: string
  required?: boolean
  placeholder?: string
}

type CollaborationProfile = {
  id?: string
  title?: string
  title_ko?: string
  status?: string
  runtime_support?: string
  description?: string
  description_ko?: string
  execution_pattern?: string
  relative_cost?: string
  min_participants?: number
  max_participants?: number
}

type Recipe = {
  id?: string
  version?: number
  title?: string
  title_ko?: string
  category?: string
  description?: string
  description_ko?: string
  recommended_room_package?: string
  recommended_collaboration_profile?: string
  alternative_collaboration_profiles?: string[]
  input_fields?: RecipeField[]
  example?: string
  evidence_summary?: RecipeEvidence
}

function statusLabel(status = ''): string {
  if (status === 'recommended') return '✅ Recommended'
  if (status === 'evaluated') return '📊 Evaluated'
  if (status === 'revalidation_needed') return '⚠️ Revalidation needed'
  if (status === 'deprecated') return '🗄 Deprecated'
  return '🧪 Experimental'
}

function buildTemplate(recipe: Recipe): string {
  const lines = [
    `${recipe.title_ko || recipe.title || recipe.id || 'Recipe'} template`,
    `Recipe: ${recipe.id || 'unknown'} v${recipe.version || 1}`,
    '',
  ]
  for (const field of recipe.input_fields || []) {
    lines.push(`${field.label || field.id || 'field'}:`)
    lines.push(field.placeholder ? `  ${field.placeholder}` : '  ')
    lines.push('')
  }
  return lines.join('\n').trim()
}

async function copyText(text: string): Promise<void> {
  await navigator.clipboard.writeText(text)
}

export default function RecipeStarterKitsPanel() {
  const [items, setItems] = useState<Recipe[]>([])
  const [catalogVersion, setCatalogVersion] = useState('')
  const [profiles, setProfiles] = useState<CollaborationProfile[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expanded, setExpanded] = useState<string | null>(null)
  const [copied, setCopied] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.recipeCatalog()
      setItems(Array.isArray(data?.items) ? data.items : [])
      setCatalogVersion(String(data?.catalog_version || ''))
      setProfiles(Array.isArray(data?.collaboration_profiles) ? data.collaboration_profiles : [])
    } catch (nextError: any) {
      setError(String(nextError?.message || nextError || 'Failed to load recipes'))
      setItems([])
      setProfiles([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  const ordered = useMemo(() => {
    const rank: Record<string, number> = { recommended: 0, evaluated: 1, revalidation_needed: 2, experimental: 3, deprecated: 4 }
    return [...items].sort((a, b) => {
      const sa = a.evidence_summary?.status || 'experimental'
      const sb = b.evidence_summary?.status || 'experimental'
      return (rank[sa] ?? 9) - (rank[sb] ?? 9) || String(a.category || '').localeCompare(String(b.category || ''))
    })
  }, [items])

  const profileById = useMemo(() => {
    const out = new Map<string, CollaborationProfile>()
    for (const profile of profiles) {
      if (profile.id) out.set(String(profile.id), profile)
    }
    return out
  }, [profiles])

  const handleCopy = async (key: string, text: string) => {
    try {
      await copyText(text)
      setCopied(key)
      window.setTimeout(() => setCopied((current) => current === key ? '' : current), 1600)
    } catch {
      setCopied('')
    }
  }

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Starter kits · evaluated recipes</h3>
          <div className="muted">Recipes structure the user task contract. Provider/model-specific harness prompts remain separate and can evolve independently.</div>
        </div>
        <button type="button" onClick={() => void load()} disabled={loading}>{loading ? 'Refreshing…' : 'Refresh'}</button>
      </div>
      {catalogVersion && <div className="muted">Catalog: {catalogVersion}</div>}
      {profiles.length > 0 && (
        <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
          {profiles.filter((profile) => profile.runtime_support === 'native').map((profile) => (
            <span key={profile.id} className="pill" title={profile.description_ko || profile.description || ''}>
              {profile.title_ko || profile.title || profile.id} · {profile.execution_pattern || 'adaptive'}
            </span>
          ))}
        </div>
      )}
      {error && <div className="runStudioWarning"><b>Recipe catalog unavailable:</b> {error}</div>}
      {!error && ordered.length === 0 && <div className="muted">No recipe is available.</div>}
      {ordered.length > 0 && (
        <div className="timeline" style={{ marginTop: 8 }}>
          {ordered.map((recipe) => {
            const id = String(recipe.id || 'unknown')
            const evidence = recipe.evidence_summary || {}
            const collaboration = profileById.get(String(recipe.recommended_collaboration_profile || 'auto'))
            const isOpen = expanded === id
            return (
              <div key={id} className="timelineItem">
                <div className="runStudioPanelHeader">
                  <div>
                    <div><b>{recipe.title_ko || recipe.title || id}</b> · <span className="muted">{id}</span></div>
                    <div className="runStudioMetaRow" style={{ marginTop: 4 }}>
                      <span className="pill">{statusLabel(evidence.status)}</span>
                      <span className="pill">{recipe.category || 'general'}</span>
                      <span className="pill">room: {recipe.recommended_room_package || 'task-adaptive'}</span>
                      <span className="pill">collab: {collaboration?.title_ko || recipe.recommended_collaboration_profile || 'auto'}</span>
                      {(evidence.live_runs || 0) > 0 && <span className="pill">{evidence.live_runs} live runs · {Math.round((evidence.success_rate || 0) * 100)}%</span>}
                    </div>
                  </div>
                  <button type="button" onClick={() => setExpanded(isOpen ? null : id)}>{isOpen ? 'Hide' : 'Details'}</button>
                </div>
                <div className="muted">{recipe.description_ko || recipe.description || ''}</div>
                {isOpen && (
                  <div style={{ marginTop: 10 }}>
                    <div><b>Evidence</b></div>
                    <div className="muted">{evidence.reason || 'No evaluation evidence yet.'}</div>
                    <div className="runStudioMetaRow" style={{ marginTop: 4 }}>
                      <span className="pill">scope: {evidence.evidence_scope || 'none'}</span>
                      <span className="pill">policy violations: {evidence.policy_violations || 0}</span>
                    </div>
                    <div style={{ marginTop: 10 }}><b>Collaboration</b></div>
                    <div className="muted">{collaboration?.description_ko || collaboration?.description || 'Task-adaptive collaboration.'}</div>
                    <div className="runStudioMetaRow" style={{ marginTop: 4 }}>
                      <span className="pill">pattern: {collaboration?.execution_pattern || 'task_adaptive'}</span>
                      <span className="pill">support: {collaboration?.runtime_support || 'native'}</span>
                      {collaboration?.relative_cost && <span className="pill">cost: {collaboration.relative_cost}</span>}
                    </div>
                    <div style={{ marginTop: 10 }}><b>Example</b></div>
                    <div className="muted" style={{ whiteSpace: 'pre-wrap' }}>{recipe.example || 'No example yet.'}</div>
                    <div style={{ marginTop: 10 }}><b>Template fields</b></div>
                    <div className="muted">{(recipe.input_fields || []).map((field) => `${field.required ? '필수' : '선택'} ${field.label || field.id}`).join(' · ')}</div>
                    <div className="runStudioMetaRow" style={{ marginTop: 10 }}>
                      <button type="button" onClick={() => void handleCopy(`${id}:telegram`, `/use ${id}`)}>{copied === `${id}:telegram` ? 'Copied' : 'Copy Telegram command'}</button>
                      <button type="button" onClick={() => void handleCopy(`${id}:template`, buildTemplate(recipe))}>{copied === `${id}:template` ? 'Copied' : 'Copy template'}</button>
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
