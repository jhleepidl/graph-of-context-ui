import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../../api'

type Props = {
  runId?: string | null
  threadId?: string | null
}

type RuntimeProjection = {
  run_id?: string
  status?: string
  last_event_type?: string
  last_sequence?: number
  event_count?: number
  agent_event_count?: number
  error_count?: number
  command_count?: number
  agent_ids?: string[]
  providers?: string[]
  command_ids?: string[]
  started_at?: string | null
  finished_at?: string | null
  updated_at?: string | null
}

function textList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item || '').trim()).filter(Boolean) : []
}

export default function RuntimeEventProjectionPanel({ runId, threadId }: Props) {
  const cleanRunId = String(runId || '').trim()
  const [projection, setProjection] = useState<RuntimeProjection | null>(null)
  const [events, setEvents] = useState<Record<string, any>[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const load = async () => {
    if (!cleanRunId) {
      setProjection(null)
      setEvents([])
      setError('')
      return
    }
    setLoading(true)
    setError('')
    try {
      const [nextProjection, eventList] = await Promise.all([
        api.runtimeRunProjection(cleanRunId),
        api.runtimeEvents({ run_id: cleanRunId, thread_id: String(threadId || '').trim() || undefined, limit: 12 }),
      ])
      setProjection(nextProjection || null)
      setEvents(Array.isArray(eventList?.items) ? eventList.items : [])
    } catch (nextError: any) {
      setProjection(null)
      setEvents([])
      setError(String(nextError?.message || nextError || 'Failed to load runtime projection'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // Reload only when the selected run/thread changes. Manual refresh is available below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cleanRunId, threadId])

  const agents = useMemo(() => textList(projection?.agent_ids), [projection])
  const providers = useMemo(() => textList(projection?.providers), [projection])

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Runtime event projection</h3>
          <div className="muted">Local-first ddalggak events projected by GoC. Duplicate delivery is ignored by event ID.</div>
        </div>
        <button type="button" onClick={() => void load()} disabled={!cleanRunId || loading}>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {!cleanRunId && <div className="muted">No current run ID is available yet.</div>}
      {cleanRunId && error && <div className="runStudioWarning"><b>Projection unavailable:</b> {error}</div>}
      {cleanRunId && projection && (
        <>
          <div className="runStudioMetaRow" style={{ marginTop: 8 }}>
            <span className="pill">status: {projection.status || 'unknown'}</span>
            <span className="pill">events: {projection.event_count ?? 0}</span>
            <span className="pill">agent events: {projection.agent_event_count ?? 0}</span>
            <span className="pill">errors: {projection.error_count ?? 0}</span>
            <span className="pill">commands: {projection.command_count ?? 0}</span>
          </div>
          <div style={{ marginTop: 10 }}>
            <div><b>Last event:</b> {projection.last_event_type || '—'} · sequence {projection.last_sequence ?? 0}</div>
            {agents.length > 0 && <div className="muted">agents: {agents.join(', ')}</div>}
            {providers.length > 0 && <div className="muted">providers: {providers.join(', ')}</div>}
          </div>
          <div style={{ marginTop: 12 }}>
            <b>Recent events</b>
            {events.length === 0 ? (
              <div className="muted">No ingested events for this run.</div>
            ) : (
              <div className="timeline" style={{ marginTop: 6 }}>
                {events.map((event) => (
                  <div key={String(event.event_id || event.id)} className="timelineItem">
                    <div><b>{String(event.event_type || 'event')}</b> · seq {Number(event.event_sequence || 0)}</div>
                    <div className="muted">{String(event.occurred_at || event.ingested_at || '')}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </section>
  )
}
