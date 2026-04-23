import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'

type BoardCard = {
  id: string
  lane_id?: string
  title?: string | null
  summary?: string | null
  preview_text?: string | null
  created_at?: string | null
  resource_kind?: string | null
  source?: string | null
  uri?: string | null
  tags?: string[]
  learning_excluded?: boolean
  promotion_blocked?: boolean
  shareability?: string | null
  privacy_class?: string | null
  history_stream_key?: string | null
  candidate_key?: string | null
  candidate_kind?: string | null
  promotion_status?: string | null
  review_status?: string | null
  derived_from_history_title?: string | null
  promoted_node_id?: string | null
  promoted_resource_kind?: string | null
  published_to_library?: boolean
  stale?: boolean
  counts?: Record<string, number>
  payload?: Record<string, unknown>
}

type BoardLane = {
  id: string
  title: string
  description?: string | null
  count?: number
  cards?: BoardCard[]
}

type BoardData = {
  policy?: Record<string, unknown>
  lanes?: BoardLane[]
  counts?: Record<string, number>
}

function cleanText(value: unknown): string {
  return String(value || '').trim()
}

function formatWhen(value: string | null | undefined): string {
  const raw = cleanText(value)
  if (!raw) return ''
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return raw
  return date.toLocaleString()
}

export default function BoardPanel({ threadId }: { threadId: string | null }) {
  const [data, setData] = useState<BoardData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string>('')
  const [expandedCardId, setExpandedCardId] = useState<string>('')
  const [busyCandidateId, setBusyCandidateId] = useState<string>('')
  const [actionStatus, setActionStatus] = useState<string>('')

  const reloadBoard = useCallback(async () => {
    const tid = cleanText(threadId)
    if (!tid) {
      setData(null)
      setError('')
      return
    }
    setLoading(true)
    setError('')
    try {
      const next = await api.getThreadBoard(tid)
      setData(next || null)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err || 'Unknown error'))
    } finally {
      setLoading(false)
    }
  }, [threadId])

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      const tid = cleanText(threadId)
      if (!tid) {
        if (!cancelled) {
          setData(null)
          setError('')
        }
        return
      }
      if (!cancelled) {
        setActionStatus('')
      }
      try {
        await reloadBoard()
      } catch {
        // handled in reloadBoard
      }
    }
    run()
    return () => {
      cancelled = true
    }
  }, [threadId, reloadBoard])

  const lanes = useMemo(() => Array.isArray(data?.lanes) ? data?.lanes || [] : [], [data])

  const handleApprove = useCallback(async (card: BoardCard, publishToLibrary: boolean) => {
    const tid = cleanText(threadId)
    const candidateId = cleanText(card.id)
    if (!tid || !candidateId) return
    setBusyCandidateId(candidateId)
    setActionStatus('')
    setError('')
    try {
      const result = await api.approveBoardCandidate(tid, candidateId, { publish_to_library: publishToLibrary })
      const kind = cleanText(result?.promoted_resource_kind || card.candidate_kind || 'resource')
      const targetThread = cleanText(result?.target_thread_id)
      setActionStatus(
        publishToLibrary
          ? `Approved and published ${kind} to library${targetThread ? ` (${targetThread.slice(0, 8)})` : ''}.`
          : `Approved ${kind} into this thread.`
      )
      await reloadBoard()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err || 'Unknown error'))
    } finally {
      setBusyCandidateId('')
    }
  }, [reloadBoard, threadId])

  if (!cleanText(threadId)) {
    return <div className="card"><div className="muted">Select a thread to open the Board.</div></div>
  }

  return (
    <div className="boardPanelRoot">
      <div className="card">
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontWeight: 700 }}>Board</div>
            <div className="muted">Raw history stays visible here, but is excluded from learning and promotion by policy.</div>
          </div>
          <div>
            {data?.policy?.raw_history_learning_excluded === true && <span className="pill">raw history: learning excluded</span>}
            {data?.policy?.promotion_requires_structured_artifacts === true && <span className="pill">promotion: structured only</span>}
            {data?.policy?.candidate_learning_requires_review === true && <span className="pill">candidates: review required</span>}
          </div>
        </div>
        {actionStatus && <div className="muted" style={{ marginTop: 8 }}>{actionStatus}</div>}
      </div>

      {loading && <div className="card"><div className="muted">Loading board…</div></div>}
      {!!error && <div className="card"><div className="muted">{error}</div></div>}

      <div className="boardLaneWrap">
        {lanes.map((lane) => (
          <section key={lane.id} className="boardLaneColumn">
            <div className="card boardLaneHeader">
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
                <div style={{ fontWeight: 700 }}>{cleanText(lane.title) || lane.id}</div>
                <span className="pill">{Number(lane.count || (lane.cards || []).length || 0)}</span>
              </div>
              {cleanText(lane.description) && <div className="muted" style={{ marginTop: 6 }}>{cleanText(lane.description)}</div>}
            </div>
            {(lane.cards || []).length === 0 && <div className="card"><div className="muted">No cards.</div></div>}
            {(lane.cards || []).map((card) => {
              const expanded = expandedCardId === card.id
              const preview = cleanText(card.preview_text)
              const canApprove = lane.id === 'promotion_candidates'
                && cleanText(card.review_status) !== 'approved'
                && cleanText(card.promotion_status) !== 'promoted'
                && card.stale !== true
              const busy = busyCandidateId === card.id
              return (
                <article key={card.id} className="card boardCard">
                  <div style={{ fontWeight: 700 }}>{cleanText(card.title) || card.id}</div>
                  <div className="muted" style={{ marginTop: 4 }}>{cleanText(card.summary) || 'No summary'}</div>
                  <div className="boardCardMetaRow" style={{ marginTop: 8 }}>
                    {cleanText(card.resource_kind) && <span className="pill">{cleanText(card.resource_kind)}</span>}
                    {card.learning_excluded === true && <span className="pill">learning excluded</span>}
                    {card.promotion_blocked === true && <span className="pill">promotion blocked</span>}
                    {cleanText(card.privacy_class) && <span className="pill">privacy: {cleanText(card.privacy_class)}</span>}
                    {cleanText(card.shareability) && <span className="pill">share: {cleanText(card.shareability)}</span>}
                    {cleanText(card.candidate_kind) && <span className="pill">candidate: {cleanText(card.candidate_kind)}</span>}
                    {cleanText(card.promotion_status) && <span className="pill">promotion: {cleanText(card.promotion_status)}</span>}
                    {cleanText(card.review_status) && <span className="pill">review: {cleanText(card.review_status)}</span>}
                    {cleanText(card.promoted_resource_kind) && <span className="pill">promoted as: {cleanText(card.promoted_resource_kind)}</span>}
                    {card.published_to_library === true && <span className="pill">published to library</span>}
                    {card.stale === true && <span className="pill">stale</span>}
                  </div>
                  {(card.tags || []).length > 0 && (
                    <div className="boardCardMetaRow" style={{ marginTop: 6 }}>
                      {(card.tags || []).map((tag) => <span key={`${card.id}:${tag}`} className="pill">#{tag}</span>)}
                    </div>
                  )}
                  <div className="muted" style={{ marginTop: 8 }}>
                    {formatWhen(card.created_at) && <span>created: {formatWhen(card.created_at)}</span>}
                    {cleanText(card.source) && <span>{formatWhen(card.created_at) ? ' · ' : ''}source: {cleanText(card.source)}</span>}
                    {cleanText(card.history_stream_key) && <span>{(formatWhen(card.created_at) || cleanText(card.source)) ? ' · ' : ''}stream: {cleanText(card.history_stream_key)}</span>}
                    {cleanText(card.derived_from_history_title) && <span>{(formatWhen(card.created_at) || cleanText(card.source) || cleanText(card.history_stream_key)) ? ' · ' : ''}from: {cleanText(card.derived_from_history_title)}</span>}
                    {cleanText(card.promoted_node_id) && <span>{(formatWhen(card.created_at) || cleanText(card.source) || cleanText(card.history_stream_key) || cleanText(card.derived_from_history_title)) ? ' · ' : ''}promoted node: {cleanText(card.promoted_node_id).slice(0, 8)}</span>}
                  </div>
                  {canApprove && (
                    <div className="row" style={{ marginTop: 8, gap: 8 }}>
                      <button disabled={busy} onClick={() => handleApprove(card, false)}>
                        {busy ? 'Approving…' : 'Approve'}
                      </button>
                      <button disabled={busy} onClick={() => handleApprove(card, true)}>
                        {busy ? 'Publishing…' : 'Approve + Publish'}
                      </button>
                    </div>
                  )}
                  {preview && (
                    <>
                      <div className="boardPreview" style={{ marginTop: 8 }}>
                        {expanded ? preview : `${preview.slice(0, 420)}${preview.length > 420 ? '…' : ''}`}
                      </div>
                      {preview.length > 420 && (
                        <button style={{ marginTop: 8 }} onClick={() => setExpandedCardId(expanded ? '' : card.id)}>
                          {expanded ? 'Collapse' : 'Expand'}
                        </button>
                      )}
                    </>
                  )}
                </article>
              )
            })}
          </section>
        ))}
      </div>
    </div>
  )
}
