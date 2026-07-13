import React, { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api'
import { usePageVisibility } from '../../hooks/usePageVisibility'
import { makeClientCommandId, runtimeCommandPollDelay } from '../../utils/runtimePolling'
import DisclosureSection from './DisclosureSection'

type RuntimeEvent = {
  event_id?: string
  event_type?: string
  run_id?: string
  occurred_at?: string
  ingested_at?: string
  payload?: Record<string, unknown>
}

type RuntimeCommand = {
  command_id?: string
  status?: string
  error_message?: string
  result?: Record<string, unknown>
}

type ChatTurn = {
  id: string
  role: 'user' | 'assistant' | 'system'
  text: string
  at: string
  runId?: string
  commandId?: string
  optimistic?: boolean
}

type Props = {
  threadId?: string | null
  externalRef?: string | null
  currentStatus?: string
  onActivity?: () => void
}

const TERMINAL = new Set(['applied', 'rejected', 'failed', 'cancelled'])
const MAX_COMMAND_WAIT_MS = 10 * 60 * 1000

function clean(value: unknown): string {
  return typeof value === 'string' ? value.trim() : String(value || '').trim()
}

function parseTelegramChatId(externalRef?: string | null): string {
  const raw = clean(externalRef)
  if (!raw) return ''
  const explicit = raw.match(/(?:telegram|chat)(?::|\/|=)(-?\d+)/i)
  if (explicit?.[1]) return explicit[1]
  if (/^-?\d+$/.test(raw)) return raw
  return raw.match(/(-?\d+)$/)?.[1] || ''
}

function eventText(event: RuntimeEvent): string {
  const payload = event.payload && typeof event.payload === 'object' ? event.payload : {}
  const type = clean(event.event_type).toLowerCase()
  if (type === 'run.start' || type === 'run.started') {
    return clean(payload.userText || payload.user_text || payload.message || payload.goal)
  }
  if (type === 'run.finish' || type === 'run.completed') {
    return clean(payload.summary || payload.output || payload.reply || payload.response)
  }
  if (type === 'run.failed') return clean(payload.error || payload.summary || '작업이 실패했습니다.')
  return ''
}

function toTurns(events: RuntimeEvent[]): ChatTurn[] {
  return [...events]
    .sort((a, b) => clean(a.occurred_at || a.ingested_at).localeCompare(clean(b.occurred_at || b.ingested_at)))
    .flatMap((event): ChatTurn[] => {
      const type = clean(event.event_type).toLowerCase()
      const text = eventText(event)
      if (!text) return []
      const role: ChatTurn['role'] = (type === 'run.start' || type === 'run.started')
        ? 'user'
        : (type === 'run.failed' ? 'system' : 'assistant')
      return [{
        id: clean(event.event_id) || `${type}:${clean(event.run_id)}:${clean(event.occurred_at)}`,
        role,
        text,
        at: clean(event.occurred_at || event.ingested_at),
        runId: clean(event.run_id) || undefined,
        commandId: clean((event as any).command_id) || undefined,
      }]
    })
    .slice(-20)
}

function mergeOptimistic(actual: ChatTurn[], optimistic: ChatTurn[]): ChatTurn[] {
  const remaining = optimistic.filter((candidate) => {
    const candidateTime = Date.parse(candidate.at || '') || 0
    return !actual.some((turn) => {
      if (turn.role !== 'user') return false
      if (candidate.commandId && turn.commandId) return candidate.commandId === turn.commandId
      if (turn.text !== candidate.text) return false
      const actualTime = Date.parse(turn.at || '') || 0
      return !candidateTime || !actualTime || Math.abs(actualTime - candidateTime) < 10 * 60 * 1000
    })
  })
  return [...actual, ...remaining]
    .sort((a, b) => clean(a.at).localeCompare(clean(b.at)))
    .slice(-20)
}

export default function RoomChatPanel({ threadId, externalRef, currentStatus = 'idle', onActivity }: Props) {
  const cleanThreadId = clean(threadId)
  const chatId = useMemo(() => parseTelegramChatId(externalRef), [externalRef])
  const pageVisible = usePageVisibility()
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [optimistic, setOptimistic] = useState<ChatTurn[]>([])
  const [draft, setDraft] = useState('')
  const [loading, setLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [activeCommandId, setActiveCommandId] = useState('')
  const pollTimer = useRef<number | null>(null)
  const refreshTimer = useRef<number | null>(null)
  const pendingSentAt = useRef('')
  const cursorRef = useRef('')
  const eventsRef = useRef<Map<string, RuntimeEvent>>(new Map())
  const mountedRef = useRef(true)
  const roomGenerationRef = useRef(0)

  const publishTurns = () => {
    const actual = toTurns([...eventsRef.current.values()])
    setTurns(mergeOptimistic(actual, optimistic))
    return actual
  }

  const loadTurns = async ({ delta = false, silent = false, generation = roomGenerationRef.current }: { delta?: boolean; silent?: boolean; generation?: number } = {}): Promise<ChatTurn[]> => {
    if (!cleanThreadId) {
      eventsRef.current.clear()
      cursorRef.current = ''
      setTurns([])
      return []
    }
    if (!silent) setLoading(true)
    try {
      const result = await api.runtimeEvents({
        thread_id: cleanThreadId,
        after_event_id: delta ? cursorRef.current || undefined : undefined,
        limit: delta ? 100 : 60,
      })
      if (!mountedRef.current || generation !== roomGenerationRef.current) return []
      const items: RuntimeEvent[] = Array.isArray(result?.items) ? result.items : []
      if (!delta) eventsRef.current.clear()
      for (const event of items) {
        const eventId = clean(event.event_id) || `${clean(event.event_type)}:${clean(event.run_id)}:${clean(event.occurred_at || event.ingested_at)}`
        eventsRef.current.set(eventId, { ...event, event_id: eventId })
      }
      cursorRef.current = clean(result?.next_cursor) || cursorRef.current
      const actual = toTurns([...eventsRef.current.values()])
      setOptimistic((rows) => rows.filter((candidate) => !actual.some((turn) => turn.role === 'user' && turn.text === candidate.text)))
      setTurns(mergeOptimistic(actual, optimistic))
      setError('')
      return actual
    } catch (nextError: any) {
      if (mountedRef.current && generation === roomGenerationRef.current && !silent) setError(clean(nextError?.message || nextError || '대화 기록을 불러오지 못했습니다.'))
    } finally {
      if (mountedRef.current && generation === roomGenerationRef.current && !silent) setLoading(false)
    }
    return []
  }

  useEffect(() => {
    mountedRef.current = true
    const generation = roomGenerationRef.current + 1
    roomGenerationRef.current = generation
    cursorRef.current = ''
    eventsRef.current.clear()
    pendingSentAt.current = ''
    setOptimistic([])
    setTurns([])
    setStatus('')
    setError('')
    setSending(false)
    setActiveCommandId('')
    if (pollTimer.current) window.clearTimeout(pollTimer.current)
    if (refreshTimer.current) window.clearTimeout(refreshTimer.current)
    void loadTurns({ generation })
    return () => {
      if (pollTimer.current) window.clearTimeout(pollTimer.current)
      if (refreshTimer.current) window.clearTimeout(refreshTimer.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cleanThreadId])

  useEffect(() => () => {
    mountedRef.current = false
    roomGenerationRef.current += 1
  }, [])

  useEffect(() => {
    publishTurns()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [optimistic])

  const followAssistantReply = async (commandId: string, sentAt: string, generation: number, attempt = 0) => {
    if (generation !== roomGenerationRef.current) return
    const rows = await loadTurns({ delta: true, silent: true, generation })
    const sentAtMs = Date.parse(sentAt || '') || 0
    const answered = rows.some((turn) => {
      if (turn.role !== 'assistant') return false
      if (commandId && turn.commandId) return commandId === turn.commandId
      const turnAtMs = Date.parse(turn.at || '') || 0
      return Boolean(sentAtMs && turnAtMs >= sentAtMs - 2 * 60 * 1000)
    })
    if (answered || attempt >= 60 || !mountedRef.current || generation !== roomGenerationRef.current) {
      pendingSentAt.current = ''
      return
    }
    const delay = pageVisible ? Math.min(5000, 1200 + attempt * 180) : 10000
    refreshTimer.current = window.setTimeout(() => void followAssistantReply(commandId, sentAt, generation, attempt + 1), delay)
  }

  const pollCommand = async (commandId: string, generation: number, attempt = 0, startedAt = Date.now()) => {
    if (generation !== roomGenerationRef.current) return
    try {
      const command: RuntimeCommand = await api.runtimeCommand(commandId)
      if (!mountedRef.current || generation !== roomGenerationRef.current) return
      const nextStatus = clean(command.status).toLowerCase() || 'queued'
      setStatus(nextStatus)
      if (TERMINAL.has(nextStatus)) {
        setSending(false)
        if (nextStatus !== 'applied') {
          setError(clean(command.error_message) || `메시지 전달 상태: ${nextStatus}`)
          return
        }
        onActivity?.()
        await followAssistantReply(commandId, pendingSentAt.current, generation)
        return
      }
      if (Date.now() - startedAt >= MAX_COMMAND_WAIT_MS) {
        setSending(false)
        setError('작업이 계속 진행 중입니다. Telegram 또는 작업 상태에서 결과를 확인하고, 필요하면 상태 확인을 다시 누르세요.')
        return
      }
      pollTimer.current = window.setTimeout(
        () => void pollCommand(commandId, generation, attempt + 1, startedAt),
        runtimeCommandPollDelay(nextStatus, attempt, pageVisible),
      )
    } catch (nextError: any) {
      if (!mountedRef.current) return
      setSending(false)
      setError(clean(nextError?.message || nextError || '메시지 상태를 확인하지 못했습니다. 다시 확인할 수 있습니다.'))
    }
  }

  const send = async () => {
    const message = clean(draft)
    if (sending) return
    if (!cleanThreadId) return setError('먼저 작업방을 선택하세요.')
    if (!chatId) return setError('이 작업방에는 Telegram 연결 정보가 없습니다.')
    if (!message) return setError('보낼 메시지를 입력하세요.')
    if (message.startsWith('/')) return setError('명령어는 ‘작업방 수정’에서 실행하고, 채팅에는 일반 메시지를 입력하세요.')

    const commandId = makeClientCommandId('cmd_goc_chat')
    const sentAt = new Date().toISOString()
    const optimisticTurn: ChatTurn = { id: `optimistic:${commandId}`, role: 'user', text: message, at: sentAt, commandId, optimistic: true }
    const generation = roomGenerationRef.current
    setSending(true)
    setError('')
    setStatus('queued')
    setActiveCommandId(commandId)
    pendingSentAt.current = sentAt
    setOptimistic((rows) => [...rows.filter((row) => row.text !== message), optimisticTurn].slice(-4))

    try {
      const out = await api.createRuntimeCommand({
        command_id: commandId,
        command_type: 'room_message',
        thread_id: cleanThreadId,
        aggregate_type: 'room',
        aggregate_id: cleanThreadId,
        payload: { message, chat_id: chatId, user_id: chatId, source: 'goc_room_chat', client_request_id: commandId },
      })
      const command = out?.command || out
      const returnedId = clean(command?.command_id)
      if (!returnedId) throw new Error('메시지 전달 응답에 command_id가 없습니다.')
      setDraft('')
      await pollCommand(returnedId, generation)
    } catch (nextError: any) {
      setSending(false)
      setOptimistic((rows) => rows.filter((row) => row.id !== optimisticTurn.id))
      setError(clean(nextError?.message || nextError || '메시지를 보내지 못했습니다. 입력 내용은 유지됩니다.'))
    }
  }

  const displayTurns = mergeOptimistic(turns.filter((turn) => !turn.optimistic), optimistic)
  const lastTurn = displayTurns[displayTurns.length - 1]
  const summary = lastTurn
    ? `${lastTurn.role === 'assistant' ? '최근 답변' : '최근 메시지'}: ${lastTurn.text.slice(0, 72)}${lastTurn.text.length > 72 ? '…' : ''}`
    : 'Telegram과 같은 작업방에 메시지를 보냅니다.'

  return (
    <DisclosureSection
      title="작업방 채팅"
      summary={summary}
      badge={sending ? (status === 'accepted' ? '작업 중' : '전달 중') : (clean(currentStatus).toLowerCase() === 'active' ? '작업 중' : null)}
      persistKey={`room-chat:${cleanThreadId || 'none'}`}
      defaultOpen={false}
      tone={error ? 'attention' : 'neutral'}
      actions={<button type="button" onClick={() => void loadTurns({ delta: Boolean(cursorRef.current) })} disabled={loading}>{loading ? '불러오는 중…' : '새로고침'}</button>}
    >
      <div className="roomChatPanel">
        <div className="roomChatHistory" aria-live="polite">
          {displayTurns.length === 0 && <div className="roomChatEmpty">아직 표시할 대화가 없습니다. 아래에서 첫 메시지를 보내세요.</div>}
          {displayTurns.map((turn) => (
            <article key={turn.id} className={`roomChatTurn roomChatTurn--${turn.role}${turn.optimistic ? ' isOptimistic' : ''}`}>
              <div className="roomChatTurnMeta">
                <b>{turn.role === 'user' ? '나' : turn.role === 'assistant' ? 'Room' : '상태'}</b>
                {turn.optimistic && <span>전송 대기</span>}
                {turn.at && <time>{new Date(turn.at).toLocaleString()}</time>}
              </div>
              <div>{turn.text}</div>
            </article>
          ))}
        </div>
        <label className="roomChatComposer">
          <span>메시지</span>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
                event.preventDefault()
                void send()
              }
            }}
            placeholder="예: 이전 계획을 이어서 첫 번째 단계만 진행해줘."
          />
        </label>
        <div className="roomChatFooter">
          <div>
            {status && <span className={`roomChatStatus roomChatStatus--${status}`}>{status === 'applied' ? '전달됨' : status === 'accepted' ? 'Room 작업 중' : status}</span>}
            {error && <span className="roomChatError">{error}</span>}
            {!error && <span className="muted">Ctrl/⌘ + Enter로 전송 · 긴 작업은 진행 중 상태로 유지됩니다.</span>}
          </div>
          <div className="row" style={{ marginBottom: 0 }}>
            {!sending && activeCommandId && status && !TERMINAL.has(status) && (
              <button type="button" onClick={() => { setSending(true); setError(''); void pollCommand(activeCommandId, roomGenerationRef.current) }}>상태 다시 확인</button>
            )}
            <button type="button" className="primary" disabled={sending || !clean(draft)} onClick={() => void send()}>
              {sending ? (status === 'accepted' ? '작업 중…' : '보내는 중…') : '메시지 보내기'}
            </button>
          </div>
        </div>
      </div>
    </DisclosureSection>
  )
}
