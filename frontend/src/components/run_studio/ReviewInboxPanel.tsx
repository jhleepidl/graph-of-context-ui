import React from 'react'
import { applyRuntimeProposalAction, getReviewInbox, runCanonicalProjectionWorker } from '../../api'

type Proposal = {
  proposal_id?: string
  kind?: string
  proposal_kind?: string
  title?: string
  summary?: string
  risk?: string
  status?: string
  source?: string
  source_id?: string
  recommended_action?: string
  evidence_status?: string
  source_original_language?: string
  display_text?: string
  canonical_projection_status?: string
  canonical_projection_id?: string
  projection_method?: string
  projection_confidence?: number
  canonical_text_en?: string
  user_surface_locale?: string
  ephemeral_detected?: boolean
}
type ReviewInbox = {
  summary?: Record<string, unknown>
  persisted_summary?: Record<string, unknown>
  detected_summary?: Record<string, unknown>
  proposals?: Proposal[]
  policy?: { principle?: string; actions?: string[]; safe_defaults?: string[] }
}
type Props = { threadId?: string | null }

function clean(v: unknown): string { return typeof v === 'string' ? v.trim() : String(v || '').trim() }
function num(v: unknown): number { return typeof v === 'number' && Number.isFinite(v) ? v : Number(v || 0) || 0 }
function arr<T>(v: unknown): T[] { return Array.isArray(v) ? v as T[] : [] }
function trunc(v: unknown, max = 220): string { const t = clean(v); return t.length > max ? `${t.slice(0, max - 1).trim()}…` : t }
function riskClass(risk?: string): string { return ['high', 'critical'].includes(clean(risk).toLowerCase()) ? 'pill runStudioPillDanger' : 'pill' }
function kindOf(p: Proposal): string { return clean(p.proposal_kind || p.kind || 'proposal') }

export default function ReviewInboxPanel({ threadId }: Props) {
  const [inbox, setInbox] = React.useState<ReviewInbox | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [actingId, setActingId] = React.useState('')
  const [error, setError] = React.useState('')

  const load = React.useCallback(async () => {
    const t = clean(threadId)
    if (!t) { setError('Select a GoC thread before loading the Review Inbox.'); return }
    setLoading(true)
    setError('')
    try {
      setInbox(await getReviewInbox(t, { include_detected: true, limit: 100 }) as ReviewInbox)
    } catch (e: any) {
      setError(e?.message || String(e))
    } finally {
      setLoading(false)
    }
  }, [threadId])

  React.useEffect(() => { if (threadId) void load() }, [threadId, load])

  async function runProjectionWorker() {
    const t = clean(threadId)
    if (!t) return
    setActingId('projection-worker')
    setError('')
    try {
      await runCanonicalProjectionWorker(t, { limit: 50, actor: 'goc_review_inbox' })
      await load()
    } catch (e: any) {
      setError(e?.message || String(e))
    } finally {
      setActingId('')
    }
  }

  async function act(proposal: Proposal, action: string) {
    const t = clean(threadId)
    const id = clean(proposal.proposal_id)
    if (!t || !id) return
    if (proposal.ephemeral_detected) {
      setError('This detected proposal has not been persisted yet. Ask ddalggak to sync proposals, or use Memory / Rule / Skill Review for source details.')
      return
    }
    setActingId(`${id}:${action}`)
    setError('')
    try {
      await applyRuntimeProposalAction(t, id, { action, actor: 'goc_review_inbox' })
      await load()
    } catch (e: any) {
      setError(e?.message || String(e))
    } finally {
      setActingId('')
    }
  }

  const summary = inbox?.summary || {}
  const proposals = arr<Proposal>(inbox?.proposals)
  const critical = proposals.filter((p) => ['high', 'critical'].includes(clean(p.risk).toLowerCase()))
  const needsEvidence = proposals.filter((p) => clean(p.status) === 'needs_evidence' || clean(p.evidence_status).includes('unsupported'))

  return <section className="card runStudioPanel runStudioReviewInboxPanel">
    <div className="runStudioPanelHeader">
      <div>
        <h3 style={{ margin: 0 }}>Review Inbox</h3>
        <div className="muted">First stop for proposals: memory commits, learned rules, evidence gaps, skills, and materialization candidates.</div>
      </div>
      <div className="runStudioMetaRow">
        <button onClick={runProjectionWorker} disabled={Boolean(actingId) || !threadId}>{actingId === 'projection-worker' ? 'Projecting…' : 'Run projection worker'}</button>
        <button onClick={load} disabled={loading || !threadId}>{loading ? 'Loading…' : 'Refresh inbox'}</button>
      </div>
    </div>
    {error && <div className="runStudioWarning" style={{ marginTop: 8 }}>{error}</div>}
    <div className="runStudioMetaRow" style={{ marginTop: 8 }}>
      <span className="pill">open: {num(summary.proposal_count)}</span>
      <span className="pill">pending: {num(summary.pending_review_count)}</span>
      <span className={riskClass(num(summary.high_risk_count) > 0 ? 'high' : '')}>high risk: {num(summary.high_risk_count)}</span>
      <span className={riskClass(needsEvidence.length ? 'high' : '')}>needs evidence: {needsEvidence.length}</span>
      <span className="pill">persisted: {num(inbox?.persisted_summary?.proposal_count)}</span>
      <span className="pill">detected: {num(inbox?.detected_summary?.proposal_count)}</span>
    </div>
    {critical.length > 0 && <div className="runStudioPanelSubcard" style={{ marginTop: 10 }}>
      <b>Needs attention first</b>
      <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
        {critical.slice(0, 6).map((p) => <span key={clean(p.proposal_id || p.summary)} className="pill runStudioPillDanger">{kindOf(p)} · {trunc(p.summary || p.title, 72)}</span>)}
      </div>
    </div>}
    {proposals.length === 0 ? <div className="muted" style={{ marginTop: 10 }}>No open proposal yet.</div> : <div className="runStudioPanelSubcard" style={{ marginTop: 10 }}>
      {proposals.slice(0, 16).map((p) => {
        const id = clean(p.proposal_id || p.summary || p.title)
        const persisted = !p.ephemeral_detected
        return <div key={id} className="runStudioReviewItem">
          <div className="runStudioQuickListHeader">
            <b>{clean(p.title) || kindOf(p)}</b>
            <span className={riskClass(p.risk)}>{clean(p.risk) || 'risk'}</span>
          </div>
          <div>{trunc(p.display_text || p.summary, 280)}</div>
          {clean(p.canonical_text_en) && <div className="muted">canonical en: {trunc(p.canonical_text_en, 220)}</div>}
          <div className="muted">{kindOf(p)} · {clean(p.status) || 'pending'} · {clean(p.recommended_action)} · lang: {clean(p.source_original_language || p.user_surface_locale) || 'auto'} · canonical: {clean(p.canonical_projection_status) || 'unknown'}{clean(p.projection_method) ? ` via ${clean(p.projection_method)}` : ''} {p.ephemeral_detected ? '· detected only' : ''}</div>
          <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
            <button disabled={!persisted || Boolean(actingId)} onClick={() => act(p, 'approve')}>{actingId === `${p.proposal_id}:approve` ? 'Approving…' : 'Approve'}</button>
            <button disabled={!persisted || Boolean(actingId)} onClick={() => act(p, 'reject')}>Reject</button>
            <button disabled={!persisted || Boolean(actingId)} onClick={() => act(p, 'needs_evidence')}>Needs evidence</button>
            <button disabled={!persisted || Boolean(actingId)} onClick={() => act(p, 'mark_stale')}>Mark stale</button>
          </div>
        </div>
      })}
    </div>}
    {inbox?.policy?.principle && <div className="muted" style={{ marginTop: 10 }}>{inbox.policy.principle}: {arr<string>(inbox.policy.safe_defaults).join(' · ')}</div>}
  </section>
}
