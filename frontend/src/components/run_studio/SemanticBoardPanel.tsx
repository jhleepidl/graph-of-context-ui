import React, { useEffect, useState } from 'react'
import { api } from '../../api'

type Props = {
  threadId?: string | null
  summary?: any | null
}

function clean(value: unknown, fallback = '—'): string {
  const text = typeof value === 'string' ? value.trim() : String(value || '').trim()
  return text || fallback
}

function typeLabel(value: unknown): string {
  return clean(value).replace(/_card$/, '').replace(/_/g, ' ')
}

export default function SemanticBoardPanel({ threadId, summary }: Props) {
  const [detail, setDetail] = useState<any | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('')
  const overview = detail?.summary || summary?.semantic_board_summary || {}
  const cards = Array.isArray(detail?.cards) ? detail.cards : (overview.recent || [])
  const topReusable = Array.isArray(overview.top_reusable) ? overview.top_reusable : []
  const byType = overview.by_type || {}

  const load = async (cardType = filter) => {
    const cleanThread = (threadId || '').trim()
    if (!cleanThread) return
    setLoading(true)
    setError('')
    try {
      setDetail(await api.semanticBoard(cleanThread, cardType || null, 120))
    } catch (e: any) {
      setError(e?.message || String(e))
    } finally {
      setLoading(false)
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
          <h3>Semantic Board</h3>
          <div className="muted">Typed cards for memory, skills, rules, packages and agent concepts. Markdown/HTML become projections, not the source of truth.</div>
        </div>
        <button onClick={() => load()} disabled={loading || !threadId}>{loading ? 'Loading...' : 'Load board'}</button>
      </div>

      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
        <span className="pill">cards: {overview.card_count ?? 0}</span>
        <span className="pill">links: {overview.link_count ?? 0}</span>
        {Object.entries(byType).slice(0, 4).map(([key, value]) => (
          <span className="pill" key={key}>{typeLabel(key)}: {String(value)}</span>
        ))}
      </div>

      <div className="runStudioMetaRow" style={{ marginBottom: 10 }}>
        {['', 'skill_card', 'rule_card', 'memory_card', 'agent_card'].map((type) => (
          <button
            key={type || 'all'}
            className={filter === type ? 'secondary active' : 'secondary'}
            onClick={() => { setFilter(type); load(type) }}
            disabled={loading || !threadId}
          >
            {type ? typeLabel(type) : 'all'}
          </button>
        ))}
      </div>

      {error && <div className="runStudioWarning">{error}</div>}

      {topReusable.length > 0 && (
        <div style={{ marginBottom: 10 }}>
          <div className="runStudioMiniHeading">Top reusable</div>
          <div className="runStudioMetaRow">
            {topReusable.slice(0, 5).map((card: any) => (
              <span className="pill" key={card.id}>{clean(card.title || card.id)} · {card.reuse_score}</span>
            ))}
          </div>
        </div>
      )}

      {cards.length ? (
        <div className="runStudioQuickList">
          {cards.slice(0, 10).map((card: any, index: number) => (
            <div key={card.card_id || card.id || index} className="runStudioQuickListItem">
              <div className="runStudioQuickListHeader">
                <span className="runStudioQuickListTitle">{clean(card.title || card.id)}</span>
                <span className="muted">{typeLabel(card.type || card.card_type)}</span>
              </div>
              <div className="runStudioMetaRow" style={{ marginTop: 6 }}>
                <span className="pill">status: {clean(card.status)}</span>
                {(card.reuse_score || card.performance?.reuse_score) && <span className="pill">reuse: {card.reuse_score || card.performance?.reuse_score}</span>}
                {card.source && <span className="pill">source: {clean(card.source)}</span>}
              </div>
              <div className="muted" style={{ marginTop: 6 }}>{clean(card.id || card.card_id)}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="muted">No semantic board cards have been synced yet. Use /board mirror in ddalggak or sync imported skills/rules.</div>
      )}
    </section>
  )
}
