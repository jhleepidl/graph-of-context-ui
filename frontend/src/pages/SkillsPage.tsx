import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'

type Props = { onNavigate: (path: string) => void }

type ThreadSummary = { id: string; title?: string | null }

type SkillRecord = {
  id: string
  name: string
  description: string
  category: string
  version: string
  source: string
  visibility: string
  status: string
  roles: string[]
  tags: string[]
  instructionsRef: string
  resourceRefs: string[]
  utilityRefs: string[]
}

function asString(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  const out: string[] = []
  const seen = new Set<string>()
  for (const row of value) {
    const clean = asString(row)
    if (!clean || seen.has(clean)) continue
    seen.add(clean)
    out.push(clean)
  }
  return out
}

function normalizeSkill(raw: any): SkillRecord | null {
  if (!raw || typeof raw !== 'object') return null
  const id = asString(raw.id) || asString(raw.slug) || asString(raw.name)
  if (!id) return null
  return {
    id,
    name: asString(raw.name) || id,
    description: asString(raw.description),
    category: asString(raw.category),
    version: asString(raw.version),
    source: asString(raw.source),
    visibility: asString(raw.visibility),
    status: asString(raw.status),
    roles: asStringArray(raw.compatible_roles),
    tags: asStringArray(raw.capability_tags),
    instructionsRef: asString(raw.instructions_ref),
    resourceRefs: asStringArray(raw.resource_refs),
    utilityRefs: asStringArray(raw.utility_refs),
  }
}

function normalizeThread(raw: any): ThreadSummary | null {
  if (!raw || typeof raw !== 'object') return null
  const id = asString(raw.id)
  if (!id) return null
  return { id, title: asString(raw.title) || `thread-${id.slice(0, 8)}` }
}

function readLinkedThreadId(): string | null {
  if (typeof window === 'undefined') return null
  const params = new URLSearchParams(window.location.search)
  return (params.get('thread') || '').trim() || null
}

export default function SkillsPage({ onNavigate }: Props) {
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [threadId, setThreadId] = useState<string>(() => readLinkedThreadId() || '')
  const [skills, setSkills] = useState<SkillRecord[]>([])
  const [selectedSkillId, setSelectedSkillId] = useState<string>('')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    setStatus('')
    try {
      const [threadsOut, skillsOut] = await Promise.all([
        api.threads(),
        api.skills(threadId || undefined),
      ])
      const nextThreads = Array.isArray(threadsOut) ? threadsOut.map((row: any) => normalizeThread(row)).filter((row: ThreadSummary | null): row is ThreadSummary => Boolean(row)) : []
      setThreads(nextThreads)
      const mapped = Array.isArray(skillsOut?.items)
        ? skillsOut.items.map((row: any) => normalizeSkill(row)).filter((row: SkillRecord | null): row is SkillRecord => Boolean(row))
        : []
      setSkills(mapped)
      setSelectedSkillId((prev) => prev && mapped.some((row: SkillRecord) => row.id === prev) ? prev : (mapped[0]?.id || ''))
      const source = asString(skillsOut?.observability?.skill_catalog_source) || 'local'
      setStatus(`Loaded ${mapped.length} skills · source=${source}${threadId ? ` · thread=${threadId.slice(0, 8)}` : ' · all visible threads'}`)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [threadId])

  useEffect(() => { void load() }, [load])

  const filteredSkills = useMemo(() => {
    const q = query.trim().toLowerCase()
    const base = [...skills].sort((a, b) => {
      return a.name.localeCompare(b.name) || a.id.localeCompare(b.id)
    })
    if (!q) return base
    return base.filter((skill) => {
      const hay = [skill.id, skill.name, skill.description, skill.category, ...skill.tags, ...skill.roles].join(' ').toLowerCase()
      return hay.includes(q)
    })
  }, [query, skills])

  const selectedSkill = useMemo(() => filteredSkills.find((row) => row.id === selectedSkillId) || filteredSkills[0] || null, [filteredSkills, selectedSkillId])
  const categoryCounts = useMemo(() => {
    const out: Record<string, number> = {}
    for (const skill of filteredSkills) {
      const key = skill.category || 'uncategorized'
      out[key] = (out[key] || 0) + 1
    }
    return Object.entries(out).sort((a, b) => b[1] - a[1]).slice(0, 6)
  }, [filteredSkills])

  async function handleCopySkillId(skillId: string) {
    try {
      await navigator.clipboard.writeText(skillId)
      setStatus(`Copied ${skillId}`)
    } catch {
      setStatus(`Copy failed. Skill id: ${skillId}`)
    }
  }

  return (
    <div className="routePage">
      <div className="routeCard">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <div>
            <h2 style={{ margin: 0 }}>Skills Catalog</h2>
            <div className="muted">Agent profiles now reference skill ids instead of tool ids. Browse the observed skill registry, then assign skill ids in Agents Catalog or Job Settings.</div>
          </div>
          <div className="row" style={{ marginBottom: 0 }}>
            <button onClick={() => onNavigate('/agents' + (window.location.search || ''))}>Open Agents Catalog</button>
            <button onClick={() => void load()} disabled={loading}>{loading ? 'Loading...' : 'Refresh'}</button>
          </div>
        </div>

        <div className="routeToolbar" style={{ marginTop: 12 }}>
          <label className="routeLabel" style={{ flex: '1 1 280px', marginBottom: 0 }}>
            Search
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="skill id / name / role / tag" />
          </label>
          <label className="routeLabel" style={{ flex: '1 1 320px', marginBottom: 0 }}>
            Scope thread
            <select value={threadId} onChange={(e) => setThreadId(e.target.value)}>
              <option value="">All visible threads</option>
              {threads.map((thread) => (
                <option key={thread.id} value={thread.id}>{thread.title || thread.id}</option>
              ))}
            </select>
          </label>
        </div>

        <div className="row" style={{ marginTop: 8 }}>
          <span className="pill">skills: {filteredSkills.length}</span>
          {categoryCounts.map(([category, count]) => (
            <span key={category} className="pill">{category}: {count}</span>
          ))}
        </div>
        {error && <div className="routeStatus routeStatusError">{error}</div>}
        {status && <div className="routeStatus">{status}</div>}

        <div className="skillsCatalogLayout" style={{ marginTop: 12 }}>
          <div className="routeTableWrap">
            <table className="routeTable">
              <thead>
                <tr>
                  <th>skill</th>
                  <th>category</th>
                  <th>roles</th>
                  <th>tags</th>
                  <th>source</th>
                </tr>
              </thead>
              <tbody>
                {filteredSkills.map((skill) => {
                  const selected = selectedSkill?.id === skill.id
                  return (
                    <tr key={skill.id} className={selected ? 'routeTableRowActive' : ''} onClick={() => setSelectedSkillId(skill.id)} style={{ cursor: 'pointer' }}>
                      <td>
                        <div><b>{skill.name}</b></div>
                        <div className="muted">{skill.id}</div>
                        {skill.description && <div className="muted" style={{ marginTop: 4 }}>{skill.description.slice(0, 140)}</div>}
                      </td>
                      <td>{skill.category || '-'}</td>
                      <td>{skill.roles.length ? skill.roles.join(', ') : '-'}</td>
                      <td>{skill.tags.length ? skill.tags.join(', ') : '-'}</td>
                      <td>{skill.source || '-'}</td>
                    </tr>
                  )
                })}
                {filteredSkills.length === 0 && !loading && (
                  <tr><td colSpan={5}><span className="muted">No skills matched.</span></td></tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="card">
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0 }}>Skill Detail</h3>
              {selectedSkill && <button onClick={() => void handleCopySkillId(selectedSkill.id)}>Copy skill id</button>}
            </div>
            {!selectedSkill && <div className="muted">Select a skill from the list.</div>}
            {selectedSkill && (
              <div className="skillsDetailGrid">
                <div className="skillsDetailItem"><div className="muted">Name</div><div>{selectedSkill.name}</div></div>
                <div className="skillsDetailItem"><div className="muted">Skill ID</div><div>{selectedSkill.id}</div></div>
                <div className="skillsDetailItem"><div className="muted">Category</div><div>{selectedSkill.category || '-'}</div></div>
                <div className="skillsDetailItem"><div className="muted">Version</div><div>{selectedSkill.version || '-'}</div></div>
                <div className="skillsDetailItem"><div className="muted">Visibility</div><div>{selectedSkill.visibility || '-'}</div></div>
                <div className="skillsDetailItem"><div className="muted">Status</div><div>{selectedSkill.status || '-'}</div></div>
                <div className="skillsDetailItem" style={{ gridColumn: '1 / -1' }}><div className="muted">Description</div><div>{selectedSkill.description || '-'}</div></div>
                <div className="skillsDetailItem"><div className="muted">Compatible roles</div><div>{selectedSkill.roles.length ? selectedSkill.roles.join(', ') : '-'}</div></div>
                <div className="skillsDetailItem"><div className="muted">Capability tags</div><div>{selectedSkill.tags.length ? selectedSkill.tags.join(', ') : '-'}</div></div>
                <div className="skillsDetailItem"><div className="muted">Instructions ref</div><div>{selectedSkill.instructionsRef || '-'}</div></div>
                <div className="skillsDetailItem"><div className="muted">Resource refs</div><div>{selectedSkill.resourceRefs.length ? selectedSkill.resourceRefs.join(', ') : '-'}</div></div>
                <div className="skillsDetailItem"><div className="muted">Utility refs</div><div>{selectedSkill.utilityRefs.length ? selectedSkill.utilityRefs.join(', ') : '-'}</div></div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
