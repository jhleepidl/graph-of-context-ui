import React from 'react'
import { createMemoryMaterializationShadowModule, listMemoryMaterializationModules, previewMemoryMaterialization, saveMemoryMaterializationCandidates } from '../../api'

type Props = { threadId?: string | null }
type Candidate = {
  candidate_id?: string
  domain?: string
  title?: string
  description?: string
  materialization_score?: number
  recommendation?: string
  proposed_store?: string
  proposed_schema?: { table?: string }
  proposed_operations?: Array<{ name?: string }>
  signal_counts?: Record<string, number>
  backfill_preview?: { total_candidates?: number; high_confidence?: number; needs_review?: number; rows?: Array<Record<string, unknown>> }
  publish_policy?: Record<string, unknown>
  reasons?: string[]
}
type ModuleRow = { module_id?: string; title?: string; domain?: string; status?: string; table_name?: string; row_count?: number; review_count?: number; high_confidence_count?: number }
type Preview = { inventory?: Record<string, unknown>; summary?: Record<string, unknown>; candidates?: Candidate[]; next_steps?: string[]; saved_candidates?: Array<Record<string, unknown>> }
function clean(value: unknown): string { return typeof value === 'string' ? value.trim() : String(value || '').trim() }
function arr<T>(value: unknown): T[] { return Array.isArray(value) ? value as T[] : [] }
function num(value: unknown): number { return typeof value === 'number' && Number.isFinite(value) ? value : Number(value || 0) || 0 }
function trunc(value: unknown, max = 220): string { const text = clean(value); return text.length > max ? `${text.slice(0, max - 1).trim()}…` : text }
function signalSummary(candidate: Candidate): string {
  const c = candidate.signal_counts || {}
  return [`evidence=${num(c.evidence)}`, `queries=${num(c.domain_queries)}`, `aggregate=${num(c.aggregate_queries)}`, `corrections=${num(c.corrections)}`].join(' · ')
}

export default function MemoryMaterializationPanel({ threadId }: Props) {
  const [preview, setPreview] = React.useState<Preview | null>(null)
  const [modules, setModules] = React.useState<ModuleRow[]>([])
  const [loading, setLoading] = React.useState(false)
  const [saving, setSaving] = React.useState(false)
  const [creating, setCreating] = React.useState('')
  const [error, setError] = React.useState('')
  const [notice, setNotice] = React.useState('')
  const loadModules = React.useCallback(async () => {
    const t = clean(threadId)
    if (!t) return
    try {
      const data = await listMemoryMaterializationModules(t, false)
      setModules(arr<ModuleRow>(data?.modules))
    } catch {
      // modules are best-effort; preview should remain usable even when this fails
    }
  }, [threadId])
  const loadPreview = React.useCallback(async () => {
    const t = clean(threadId)
    if (!t) { setError('Select a GoC thread before previewing memory materialization.'); return }
    setLoading(true); setError(''); setNotice('')
    try { setPreview(await previewMemoryMaterialization(t, { include_backfill_preview: true }) as Preview); await loadModules() }
    catch (e: any) { setError(e?.message || String(e)) }
    finally { setLoading(false) }
  }, [threadId, loadModules])
  const saveCandidates = React.useCallback(async () => {
    const t = clean(threadId)
    if (!t) { setError('Select a GoC thread before saving candidates.'); return }
    setSaving(true); setError(''); setNotice('')
    try {
      const data = await saveMemoryMaterializationCandidates(t, { max_candidates: 6 }) as Preview
      setPreview(data)
      setNotice(`Saved ${num(data?.summary?.saved_candidate_count || arr(data?.saved_candidates).length)} reviewable candidate(s).`)
    } catch (e: any) { setError(e?.message || String(e)) }
    finally { setSaving(false) }
  }, [threadId])
  const createShadow = React.useCallback(async (candidate: Candidate) => {
    const t = clean(threadId)
    if (!t) { setError('Select a GoC thread before creating a shadow module.'); return }
    const key = clean(candidate.domain || candidate.candidate_id || candidate.title)
    setCreating(key); setError(''); setNotice('')
    try {
      const result = await createMemoryMaterializationShadowModule(t, { candidate })
      setNotice(`Created shadow module: ${clean(result?.title || result?.module_id || key)}. Canonical writes remain disabled.`)
      await loadModules()
    } catch (e: any) { setError(e?.message || String(e)) }
    finally { setCreating('') }
  }, [threadId, loadModules])
  React.useEffect(() => { loadModules() }, [loadModules])
  const summary = preview?.summary || {}, inventory = preview?.inventory || {}, candidates = arr<Candidate>(preview?.candidates)
  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3 style={{ margin: 0 }}>Memory Materialization</h3>
          <div className="muted">Detect repeated/queryable memory that should evolve from markdown into typed logs, shadow tables, and safe read/write functions.</div>
        </div>
        <div className="row" style={{ marginBottom: 0, gap: 8 }}>
          <button onClick={loadPreview} disabled={loading || !threadId}>{loading ? 'Planning…' : 'Preview materialization'}</button>
          <button onClick={saveCandidates} disabled={saving || !threadId}>{saving ? 'Saving…' : 'Save candidates'}</button>
        </div>
      </div>
      <div className="runStudioMetaRow" style={{ marginTop: 8 }}>
        <span className="pill">evidence: {num(inventory.evidence_items)}</span>
        <span className="pill">demand queries: {num(inventory.demand_queries)}</span>
        {clean(inventory.memory_topology_mode) && <span className="pill">mode: {clean(inventory.memory_topology_mode)}</span>}
        <span className="pill">candidates: {num(summary.candidate_count || candidates.length)}</span>
        <span className="pill">shadow tables: {num(summary.shadow_table_candidates)}</span>
        <span className="pill">knowledge packs: {num(summary.publishable_knowledge_candidates)}</span>
        <span className="pill">modules: {modules.length}</span>
      </div>
      {notice && <div className="runStudioSuccess" style={{ marginTop: 8 }}>{notice}</div>}
      {error && <div className="runStudioWarning" style={{ marginTop: 8 }}>{error}</div>}
      {!preview && !error && <div className="muted" style={{ marginTop: 8 }}>Preview only: drafts schemas, backfill rows, and function contracts. Approval is required before canonical DB writes, raw-memory deletion, generated code execution, or public publishing.</div>}
      {modules.length > 0 && <div className="runStudioPanelSubcard" style={{ marginTop: 10 }}>
        <b>Shadow modules</b>
        <div className="muted">These are reviewable DB-backed materialized views. Write functions and canonical memory switching are still disabled.</div>
        <div className="runStudioMetaRow" style={{ marginTop: 6 }}>{modules.slice(0, 8).map((m) => <span className="pill" key={clean(m.module_id)}>{clean(m.title || m.module_id)} · rows {num(m.row_count)} · review {num(m.review_count)}</span>)}</div>
      </div>}
      {preview && candidates.length === 0 && <div className="muted" style={{ marginTop: 8 }}>No strong materialization candidate yet. Keep compact markdown memory and continue collecting usage signals.</div>}
      {candidates.length > 0 && <div className="runStudioGrid runStudioGrid--bottom" style={{ marginTop: 10 }}>{candidates.slice(0, 6).map((candidate) => {
        const table = clean(candidate.proposed_schema?.table)
        const ops = arr<{ name?: string }>(candidate.proposed_operations).slice(0, 5).map((op) => clean(op.name)).filter(Boolean)
        const back = candidate.backfill_preview || {}
        const sample = arr<Record<string, unknown>>(back.rows)[0]
        const publishable = clean(candidate.publish_policy?.publishable_as) === 'sourced_knowledge_pack'
        const key = clean(candidate.domain || candidate.candidate_id || candidate.title)
        return <article key={`${candidate.domain}:${table}`} className="runStudioPanelSubcard" style={{ margin: 0 }}>
          <div className="row" style={{ marginBottom: 6 }}><b>{clean(candidate.title) || clean(candidate.domain) || 'Memory module'}</b><span className="pill">score {num(candidate.materialization_score).toFixed(2)}</span><span className="pill">{clean(candidate.recommendation) || 'watch'}</span></div>
          <div className="muted">{clean(candidate.description)}</div>
          <div className="runStudioMetaRow" style={{ marginTop: 6 }}><span className="pill">store: {clean(candidate.proposed_store) || '-'}</span>{table && <span className="pill">table: {table}</span>}{publishable && <span className="pill">publishable knowledge pack</span>}</div>
          <div className="muted" style={{ marginTop: 6 }}>signals: {signalSummary(candidate)}</div>
          <div className="muted">backfill: {num(back.total_candidates)} rows · {num(back.high_confidence)} high confidence · {num(back.needs_review)} review</div>
          {ops.length > 0 && <div className="muted">functions drafted: {ops.join(', ')} · disabled until approval</div>}
          {arr<string>(candidate.reasons).length > 0 && <div className="muted">why: {arr<string>(candidate.reasons).slice(0, 4).join(', ')}</div>}
          {sample && <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12, marginTop: 8 }}>{trunc(JSON.stringify(sample), 320)}</pre>}
          <div className="row" style={{ marginTop: 8, marginBottom: 0 }}>
            <button onClick={() => createShadow(candidate)} disabled={!!creating || !threadId}>{creating === key ? 'Creating…' : 'Create shadow module'}</button>
          </div>
          <div className="runStudioWarning" style={{ marginTop: 8 }}>Safe now: preview/schema/backfill dry-run or shadow module. Approval required before canonical writes or public publish.</div>
        </article>
      })}</div>}
    </section>
  )
}
