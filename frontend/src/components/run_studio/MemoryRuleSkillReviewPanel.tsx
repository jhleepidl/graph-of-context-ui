import React from 'react'
import { getMemoryReviewOverview } from '../../api'

type Proposal = { proposal_id?: string; kind?: string; title?: string; summary?: string; risk?: string; status?: string; recommended_action?: string; source?: string }
type Claim = { claim_id?: string; claim?: string; categories?: string[]; evidence_status?: string; risk?: string; recommended_action?: string; source?: string }
type ReviewOverview = { claims?: { summary?: Record<string, unknown>; claims?: Claim[] }, pressure?: { memory?: Record<string, unknown>; pressure_signals?: string[]; recommended_actions?: string[] }, review_queue?: { summary?: Record<string, unknown>; proposals?: Proposal[] }, policy?: { principle?: string; safe_defaults?: string[] } }
type Props = { threadId?: string | null }
function clean(v: unknown): string { return typeof v === 'string' ? v.trim() : String(v || '').trim() }
function num(v: unknown): number { return typeof v === 'number' && Number.isFinite(v) ? v : Number(v || 0) || 0 }
function arr<T>(v: unknown): T[] { return Array.isArray(v) ? v as T[] : [] }
function trunc(v: unknown, max = 220): string { const t = clean(v); return t.length > max ? `${t.slice(0, max - 1).trim()}…` : t }
function badge(risk?: string): string { return clean(risk) === 'high' ? 'pill runStudioPillDanger' : 'pill' }
export default function MemoryRuleSkillReviewPanel({ threadId }: Props) {
  const [overview, setOverview] = React.useState<ReviewOverview | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState('')
  const load = React.useCallback(async () => { const t = clean(threadId); if (!t) { setError('Select a GoC thread before loading the review queue.'); return } setLoading(true); setError(''); try { setOverview(await getMemoryReviewOverview(t) as ReviewOverview) } catch (e: any) { setError(e?.message || String(e)) } finally { setLoading(false) } }, [threadId])
  React.useEffect(() => { if (threadId) void load() }, [threadId, load])
  const qs = overview?.review_queue?.summary || {}, cs = overview?.claims?.summary || {}, mem = overview?.pressure?.memory || {}
  const proposals = arr<Proposal>(overview?.review_queue?.proposals), claims = arr<Claim>(overview?.claims?.claims), signals = arr<string>(overview?.pressure?.pressure_signals)
  return <section className="card runStudioPanel runStudioReviewPanel">
    <div className="runStudioPanelHeader"><div><h3 style={{ margin: 0 }}>Memory / Rule / Skill Review</h3><div className="muted">Agent proposes, runtime commits, GoC reviews. Review memory writes, learned rules, skill candidates, evidence gaps, and pressure in one place.</div></div><button onClick={load} disabled={loading || !threadId}>{loading ? 'Loading…' : 'Refresh review'}</button></div>
    {error && <div className="runStudioWarning" style={{ marginTop: 8 }}>{error}</div>}
    <div className="runStudioMetaRow" style={{ marginTop: 8 }}><span className="pill">proposals: {num(qs.proposal_count)}</span><span className="pill">memory: {num(qs.memory_proposals)}</span><span className="pill">rules: {num(qs.rule_proposals)}</span><span className="pill">skills: {num(qs.skill_proposals)}</span><span className={badge(num(qs.high_risk_count) > 0 ? 'high' : '')}>high risk: {num(qs.high_risk_count)}</span><span className="pill">claims: {num(cs.claim_count)}</span><span className={badge(num(cs.unsupported_count) > 0 ? 'high' : '')}>unsupported: {num(cs.unsupported_count)}</span><span className="pill">memory mode: {clean(mem.mode) || 'unknown'}</span><span className="pill">stress: {num(mem.stress_score).toFixed(2)}</span></div>
    {!overview && !error && <div className="muted" style={{ marginTop: 8 }}>Load this before activating learned rules, committing external facts, publishing memory, or enabling write skills.</div>}
    {signals.length > 0 && <div className="runStudioPanelSubcard" style={{ marginTop: 10 }}><b>Pressure signals</b><div className="runStudioMetaRow" style={{ marginTop: 6 }}>{signals.map((s) => <span key={s} className="pill">{s}</span>)}</div>{arr<string>(overview?.pressure?.recommended_actions).length > 0 && <ul className="runStudioCompactList">{arr<string>(overview?.pressure?.recommended_actions).slice(0, 4).map((item) => <li key={item}>{item}</li>)}</ul>}</div>}
    <div className="runStudioGrid runStudioGrid--bottom" style={{ marginTop: 10 }}><section className="runStudioPanelSubcard" style={{ margin: 0 }}><div className="runStudioPanelHeader"><b>Review queue</b><span className="muted">Approve / reject / edit before commit</span></div>{proposals.length === 0 ? <div className="muted">No pending proposal detected yet.</div> : proposals.slice(0, 10).map((p) => <div key={clean(p.proposal_id || p.summary)} className="runStudioReviewItem"><div className="runStudioQuickListHeader"><b>{clean(p.title || p.kind)}</b><span className={badge(p.risk)}>{clean(p.risk) || 'risk'}</span></div><div>{trunc(p.summary, 260)}</div><div className="muted">{clean(p.kind)} · {clean(p.status) || 'pending'} · {clean(p.recommended_action)}</div></div>)}</section><section className="runStudioPanelSubcard" style={{ margin: 0 }}><div className="runStudioPanelHeader"><b>Evidence gaps</b><span className="muted">High-risk claims need source/freshness</span></div>{claims.length === 0 ? <div className="muted">No high-risk claim candidate detected.</div> : claims.slice(0, 10).map((c) => <div key={clean(c.claim_id || c.claim)} className="runStudioReviewItem"><div className="runStudioQuickListHeader"><b>{arr<string>(c.categories).slice(0, 2).join(', ') || 'claim'}</b><span className={badge(c.risk)}>{clean(c.evidence_status) || 'review'}</span></div><div>{trunc(c.claim, 260)}</div><div className="muted">{clean(c.recommended_action)} · {clean(c.source)}</div></div>)}</section></div>
    {overview?.policy?.principle && <div className="muted" style={{ marginTop: 10 }}>{overview.policy.principle}: {arr<string>(overview.policy.safe_defaults).join(' · ')}</div>}
  </section>
}
