import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../../api'

type RoomDocFile = {
  path?: string | null
  kind?: string | null
  category?: string | null
  title?: string | null
  summary?: string | null
  content?: string | null
}

type RoomDocsBrowser = {
  schema_version?: string | null
  summary?: {
    file_count?: number
    action_count?: number
    doc_count?: number
    event_count?: number
    by_category?: Record<string, number>
  }
  navigation?: string[]
  files?: RoomDocFile[]
}

type Props = {
  threadId?: string | null
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : String(value || '').trim()
}

export default function RoomDocsPanel({ threadId }: Props) {
  const [data, setData] = useState<RoomDocsBrowser | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const [selectedPath, setSelectedPath] = useState<string | null>(null)

  const load = async () => {
    const cleanThreadId = cleanText(threadId)
    if (!cleanThreadId) return
    setLoading(true)
    setError('')
    try {
      const next = await api.getThreadRoomDocs(cleanThreadId, 240)
      setData(next || null)
      const files = Array.isArray(next?.files) ? next.files : []
      if (!selectedPath && files.length) setSelectedPath(cleanText(files[0].path || ''))
    } catch (err: any) {
      setError(err?.message || String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId])

  const files = Array.isArray(data?.files) ? data!.files : []
  const categories = useMemo(() => {
    const values = new Set<string>()
    for (const file of files) {
      const cat = cleanText(file.category || '(none)')
      if (cat) values.add(cat)
    }
    return Array.from(values).sort()
  }, [files])
  const filtered = useMemo(() => {
    const q = cleanText(query).toLowerCase()
    const c = cleanText(category)
    return files.filter((file) => {
      if (c && cleanText(file.category || '(none)') !== c) return false
      if (!q) return true
      return JSON.stringify({ path: file.path, title: file.title, summary: file.summary, content: file.content }).toLowerCase().includes(q)
    })
  }, [files, query, category])
  const selected = filtered.find((file) => cleanText(file.path) === cleanText(selectedPath)) || filtered[0] || null

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Room Docs Browser</h3>
          <div className="muted">Browse AGENTS.md, MOCs, living docs, and action notes as materialized room context views.</div>
        </div>
        <button onClick={load} disabled={loading || !threadId}>{loading ? 'Loading...' : 'Refresh'}</button>
      </div>
      {error && <div className="runStudioWarning"><b>Load error:</b> {error}</div>}
      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
        <span className="pill">files: {data?.summary?.file_count ?? files.length}</span>
        <span className="pill">docs: {data?.summary?.doc_count ?? 0}</span>
        <span className="pill">actions: {data?.summary?.action_count ?? 0}</span>
        <span className="pill">events: {data?.summary?.event_count ?? 0}</span>
      </div>
      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
        {(data?.navigation || []).map((item) => <span key={item} className="pill">{item}</span>)}
      </div>
      <div className="row" style={{ marginBottom: 8 }}>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search docs/actions" />
        <select value={category} onChange={(event) => setCategory(event.target.value)}>
          <option value="">All categories</option>
          {categories.map((cat) => <option key={cat} value={cat}>{cat}</option>)}
        </select>
      </div>
      {!files.length ? (
        <div className="muted">No room docs yet. Sync Telegram room events or create room usage events first.</div>
      ) : (
        <div className="runStudioGrid runStudioGrid--bottom">
          <div style={{ display: 'grid', gap: 8, alignContent: 'start' }}>
            {filtered.slice(0, 40).map((file) => {
              const path = cleanText(file.path || '(untitled)')
              const active = cleanText(selected?.path) === path
              return (
                <button key={path} type="button" className={`runStudioDrilldownButton ${active ? 'runStudioDrilldownButton--active' : ''}`} onClick={() => setSelectedPath(path)}>
                  <span className="runStudioDrilldownTitle">{path}</span>
                  <span className="runStudioDrilldownHelper">{cleanText(file.title || file.summary || file.kind || '')}</span>
                  <span className="pill">{cleanText(file.category || '(none)')}</span>
                </button>
              )
            })}
          </div>
          <article className="runStudioAgentCard" style={{ gridColumn: 'span 2' }}>
            <div className="runStudioAgentCardHeader">
              <div>
                <div className="runStudioAgentCardTitle">{cleanText(selected?.path || 'No file selected')}</div>
                <div className="muted">{cleanText(selected?.kind || 'doc')} · {cleanText(selected?.category || '(none)')}</div>
              </div>
            </div>
            <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 520, overflow: 'auto' }}>{cleanText(selected?.content || selected?.summary || '')}</pre>
          </article>
        </div>
      )}
    </section>
  )
}
