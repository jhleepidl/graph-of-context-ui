import React, { useEffect, useState } from 'react'
import { api } from '../../api'

type Props = {
  threadId?: string | null
}

function clean(value: unknown, fallback = '—'): string {
  const text = typeof value === 'string' ? value.trim() : String(value || '').trim()
  return text || fallback
}

function pkgPayload(item: any): any {
  return item?.package && typeof item.package === 'object' ? item.package : item
}

export default function TeamPackagesPanel({ threadId }: Props) {
  const [detail, setDetail] = useState<any | null>(null)
  const [library, setLibrary] = useState<any | null>(null)
  const [loading, setLoading] = useState(false)
  const [libraryLoading, setLibraryLoading] = useState(false)
  const [error, setError] = useState('')
  const overview = detail?.summary || {}
  const items = Array.isArray(detail?.items) ? detail.items : []
  const libraryItems = Array.isArray(library?.items) ? library.items : []

  const load = async () => {
    const cleanThread = (threadId || '').trim()
    if (!cleanThread) return
    setLoading(true)
    setError('')
    try {
      setDetail(await api.teamPackages(cleanThread, 80))
    } catch (e: any) {
      setError(e?.message || String(e))
    } finally {
      setLoading(false)
    }
  }

  const loadLibrary = async () => {
    setLibraryLoading(true)
    setError('')
    try {
      setLibrary(await api.teamLibrary('', 40))
    } catch (e: any) {
      setError(e?.message || String(e))
    } finally {
      setLibraryLoading(false)
    }
  }

  useEffect(() => {
    setDetail(null)
    setError('')
  }, [threadId])

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Shared Team Packages</h3>
          <div className="muted">Reusable team settings. Clones start with fresh private memory; credentials and provider state are never copied.</div>
        </div>
        <div className="runStudioButtonRow">
          <button onClick={load} disabled={loading || !threadId}>{loading ? 'Loading...' : 'Load thread'}</button>
          <button onClick={loadLibrary} disabled={libraryLoading}>{libraryLoading ? 'Loading...' : 'Browse library'}</button>
        </div>
      </div>
      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
        <span className="pill">thread packages: {overview.package_count ?? items.length}</span>
        <span className="pill">clone-safe: {overview.clone_safe_count ?? 0}</span>
        <span className="pill">public library: {library?.summary?.package_count ?? libraryItems.length}</span>
      </div>
      {error && <div className="runStudioWarning">{error}</div>}
      {items.length ? (
        <div className="runStudioQuickList">
          {items.slice(0, 5).map((item: any, index: number) => {
            const pkg = pkgPayload(item)
            return (
              <div key={item.package_id || pkg.package_id || index} className="runStudioQuickListItem">
                <div className="runStudioQuickListHeader">
                  <span className="runStudioQuickListTitle">{clean(item.title || pkg.title || item.package_id)}</span>
                  <span className="muted">{clean(item.status || pkg.status)}</span>
                </div>
                <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
                  <span className="pill">agents: {item.agent_count ?? (Array.isArray(pkg.agents) ? pkg.agents.length : 0)}</span>
                  <span className="pill">visibility: {clean(item.visibility || pkg.visibility)}</span>
                  <span className="pill">private memory: {item.copies_private_memory ? 'copies' : 'fresh on clone'}</span>
                </div>
                <div className="muted" style={{ marginTop: 6 }}>{clean(item.package_id || pkg.package_id)}</div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="muted">No shared team package has been synced yet. Use /team publish or /team publish --server in ddalggak.</div>
      )}
      {libraryItems.length ? (
        <div style={{ marginTop: 12 }}>
          <div className="muted" style={{ marginBottom: 6 }}>Public library preview</div>
          <div className="runStudioQuickList">
            {libraryItems.slice(0, 4).map((item: any, index: number) => (
              <div key={item.package_id || index} className="runStudioQuickListItem">
                <div className="runStudioQuickListHeader">
                  <span className="runStudioQuickListTitle">{clean(item.title || item.package_id)}</span>
                  <span className="muted">{clean(item.visibility)}</span>
                </div>
                <div className="muted" style={{ marginTop: 6 }}>{clean(item.package_id)}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  )
}
