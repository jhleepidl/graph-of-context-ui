import React, { useEffect, useState } from 'react'
import { api } from '../../api'

type Props = {
  threadId?: string | null
  runId?: string | null
  summary?: any | null
}

function clean(value: unknown, fallback = '—'): string {
  const text = typeof value === 'string' ? value.trim() : String(value || '').trim()
  return text || fallback
}

function time(value?: string | null): string {
  const text = clean(value, '')
  if (!text) return ''
  const d = new Date(text)
  return Number.isNaN(d.getTime()) ? text : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function SectionList({ title, items, empty, render }: { title: string, items: any[], empty: string, render: (item: any, index: number) => React.ReactNode }) {
  return (
    <div className="runStudioTraceSection">
      <div className="runStudioMiniHeading">{title}</div>
      {items.length ? <div className="runStudioQuickList">{items.slice(0, 6).map(render)}</div> : <div className="muted">{empty}</div>}
    </div>
  )
}

export default function DecisionTracePanel({ threadId, runId, summary }: Props) {
  const [detail, setDetail] = useState<any | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const trace = detail || null
  const overview = trace?.summary || {}
  const sections = trace?.sections || {}
  const attention = Array.isArray(trace?.attention) ? trace.attention : []
  const fallbackSummary = summary?.runtime_policy_summary || {}

  const load = async () => {
    const cleanThread = (threadId || '').trim()
    if (!cleanThread) return
    setLoading(true)
    setError('')
    try {
      setDetail(await api.decisionTrace(cleanThread, runId || undefined, 80))
    } catch (e: any) {
      setError(e?.message || String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    setDetail(null)
    setError('')
  }, [threadId, runId])

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Decision Trace</h3>
          <div className="muted">A human-readable “why?” view for execution policy, agent handoffs, skills/rules, model usage, and memory context.</div>
        </div>
        <button onClick={load} disabled={loading || !threadId}>{loading ? 'Loading...' : 'Load why trace'}</button>
      </div>

      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
        <span className="pill">policy: {overview.policy_count ?? fallbackSummary.policy_event_count ?? 0}</span>
        <span className="pill">handoffs: {overview.handoff_count ?? 0}</span>
        <span className="pill">projections: {overview.context_projection_count ?? 0}</span>
        <span className="pill">typed deltas: {overview.handoff_delta_count ?? 0}</span>
        <span className="pill">skills: {overview.skill_count ?? (summary as any)?.semantic_board_summary?.by_type?.skill_card ?? 0}</span>
        <span className="pill">models: {overview.model_usage_count ?? (summary as any)?.model_catalog_summary?.usage_event_count ?? 0}</span>
        <span className="pill">attention: {overview.attention_count ?? attention.length}</span>
      </div>

      {error && <div className="runStudioWarning">{error}</div>}
      {attention.length > 0 && (
        <div className="runStudioWarning">
          <b>Needs attention:</b> {attention.map((row: any) => clean(row.title)).join(' · ')}
        </div>
      )}

      {!trace ? (
        <div className="muted">Load the trace to see why the runtime selected each policy, skill, model, and handoff.</div>
      ) : (
        <div className="runStudioTraceGrid">
          <SectionList
            title="Why execution was allowed or blocked"
            items={sections.why_execution_allowed || []}
            empty="No policy decisions synced."
            render={(item, index) => (
              <div key={`policy-${index}`} className="runStudioQuickListItem">
                <div className="runStudioQuickListHeader"><span className="runStudioQuickListTitle">{clean(item.policy?.execution_mode || item.type)}</span><span className="muted">{time(item.created_at)}</span></div>
                <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
                  <span className="pill">write: {clean(item.policy?.workspace_write)}</span>
                  <span className="pill">artifact: {clean(item.policy?.artifact_delivery)}</span>
                  <span className="pill">fallback: {clean(item.policy?.legacy_manual_fallback)}</span>
                </div>
              </div>
            )}
          />
          <SectionList
            title="Why agents interacted"
            items={[...(sections.why_agents_interacted?.typed_deltas || []), ...(sections.why_agents_interacted?.activity_handoffs || [])]}
            empty="No handoffs synced."
            render={(item, index) => (
              <div key={`handoff-${index}`} className="runStudioQuickListItem">
                <div className="runStudioQuickListHeader"><span className="runStudioQuickListTitle">{clean(item.from_agent, '?')} → {clean(item.to_agent, '?')}</span><span className="muted">{time(item.created_at)}</span></div>
                <div className="muted">{clean(item.summary, 'No summary')}</div>
              </div>
            )}
          />
          <SectionList
            title="Why skills/rules applied"
            items={[...(sections.why_skills_rules_applied?.skills || []), ...(sections.why_skills_rules_applied?.rules || [])]}
            empty="No skill/rule cards synced."
            render={(item, index) => (
              <div key={`skill-rule-${index}`} className="runStudioQuickListItem">
                <div className="runStudioQuickListHeader"><span className="runStudioQuickListTitle">{clean(item.title || item.id)}</span><span className="muted">{clean(item.kind)}</span></div>
                <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
                  <span className="pill">status: {clean(item.status)}</span>
                  <span className="pill">reuse: {item.reuse_score ?? 0}</span>
                  <span className="pill">source: {clean(item.source)}</span>
                </div>
              </div>
            )}
          />
          <SectionList
            title="Why context was projected"
            items={sections.why_context_projected || []}
            empty="No compiled context projection events synced."
            render={(item, index) => (
              <div key={`projection-${index}`} className="runStudioQuickListItem">
                <div className="runStudioQuickListHeader"><span className="runStudioQuickListTitle">{clean(item.role_id || 'agent')} · {clean(item.task_type || 'task')}</span><span className="muted">{time(item.created_at)}</span></div>
                <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
                  <span className="pill">{clean(item.snapshot_id || 'ctx')}</span>
                  <span className="pill">{item.cache_hit ? 'cache hit' : 'compiled'}</span>
                  <span className="pill">{item.compile_ms ?? 0}ms</span>
                  <span className="pill">{item.context_tokens ?? 0} tok</span>
                </div>
              </div>
            )}
          />
          <SectionList
            title="Why models were used"
            items={sections.why_models_used || []}
            empty="No model usage synced."
            render={(item, index) => (
              <div key={`model-${index}`} className="runStudioQuickListItem">
                <div className="runStudioQuickListHeader"><span className="runStudioQuickListTitle">{[item.provider, item.model].filter(Boolean).join(' · ') || 'model usage'}</span><span className="muted">{time(item.created_at)}</span></div>
                <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
                  <span className="pill">tokens: {item.tokens ?? 0}</span>
                  {item.role_id && <span className="pill">role: {clean(item.role_id)}</span>}
                  {item.task_kind && <span className="pill">task: {clean(item.task_kind)}</span>}
                </div>
              </div>
            )}
          />
          <SectionList
            title="Why context changed"
            items={sections.why_context_changed?.operations || []}
            empty="No context substrate operations synced."
            render={(item, index) => (
              <div key={`context-${index}`} className="runStudioQuickListItem">
                <div className="runStudioQuickListHeader"><span className="runStudioQuickListTitle">{clean(item.op || item.operation_id)}</span><span className="muted">{time(item.created_at)}</span></div>
                <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
                  <span className="pill">lane: {clean(item.lane)}</span>
                  <span className="pill">status: {clean(item.status)}</span>
                  <span className="pill">mode: {clean(item.commit_mode)}</span>
                  <span className="pill">v{item.version ?? 0}</span>
                </div>
              </div>
            )}
          />
          <SectionList
            title="Why writeback was batched"
            items={sections.why_context_changed?.write_metrics || []}
            empty="No context writeback metrics synced."
            render={(item, index) => (
              <div key={`write-${index}`} className="runStudioQuickListItem">
                <div className="runStudioQuickListHeader"><span className="runStudioQuickListTitle">{clean(item.status || item.event_id || 'writeback')}</span><span className="muted">{time(item.created_at)}</span></div>
                <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
                  <span className="pill">batch: {item.batch_size ?? 0}</span>
                  <span className="pill">committed: {item.committed ?? 0}</span>
                  <span className="pill">proposals: {item.proposals ?? 0}</span>
                  <span className="pill">conflicts: {item.conflicts ?? 0}</span>
                </div>
              </div>
            )}
          />
        </div>
      )}
    </section>
  )
}
