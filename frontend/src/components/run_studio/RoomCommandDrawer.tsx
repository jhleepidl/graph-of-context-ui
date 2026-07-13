import React, { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../../api'
import { usePageVisibility } from '../../hooks/usePageVisibility'
import { makeClientCommandId, runtimeCommandPollDelay } from '../../utils/runtimePolling'
import { copyText } from '../../utils/clipboard'

type ActionKind = 'continue' | 'correct' | 'rule' | 'exclude_source' | 'branch' | 'context_mode'

type RuntimeCommand = {
  command_id?: string
  command_type?: string
  status?: string
  result?: Record<string, unknown>
  error_message?: string
  created_at?: string
  updated_at?: string
}

type Props = {
  open: boolean
  onClose: () => void
  threadId?: string | null
  externalRef?: string | null
  onApplied?: () => void
  initialAction?: ActionKind
  initialDraft?: string
}

const TERMINAL = new Set(['applied', 'rejected', 'failed', 'cancelled'])

const ACTIONS: Array<{ id: ActionKind; label: string; helper: string }> = [
  { id: 'continue', label: '작업 이어가기', helper: '현재 또는 가장 최근 작업을 계속합니다.' },
  { id: 'correct', label: '잘못 이해한 점 수정', helper: '같은 오해가 반복되지 않게 남깁니다.' },
  { id: 'rule', label: '규칙 추가', helper: '앞으로 계속 지킬 조건을 추가합니다.' },
  { id: 'exclude_source', label: '자료 제외', helper: '낡은 자료나 잘못된 가정을 현재 정보에서 뺍니다.' },
  { id: 'branch', label: '다른 방향 만들기', helper: '현재 방향은 남겨두고 대안을 따로 탐색합니다.' },
  { id: 'context_mode', label: '정보 사용 방식 변경', helper: '이 작업방 자료만 사용하거나 새로 시작하도록 설정합니다.' },
]

function clean(value: unknown): string {
  return typeof value === 'string' ? value.trim() : String(value || '').trim()
}

function parseTelegramChatId(externalRef?: string | null): string {
  const raw = clean(externalRef)
  if (!raw) return ''
  const explicit = raw.match(/(?:telegram|chat)(?::|\/|=)(-?\d+)/i)
  if (explicit?.[1]) return explicit[1]
  if (/^-?\d+$/.test(raw)) return raw
  const trailing = raw.match(/(-?\d+)$/)
  return trailing?.[1] || ''
}

function buildCommand(action: ActionKind, draft: string, contextMode: string): string {
  const value = clean(draft)
  if (action === 'continue') return '/continue'
  if (action === 'correct') return `/correct ${value}`
  if (action === 'rule') return `/rule ${value}`
  if (action === 'exclude_source') return `/context exclude ${value}`
  if (action === 'branch') return `/branch ${value}`
  if (contextMode === 'project-only') return '/context project-only'
  if (contextMode === 'clean-slate') return '/context clean-slate'
  return '/context reset'
}

function requiresDraft(action: ActionKind): boolean {
  return action === 'correct' || action === 'rule' || action === 'exclude_source' || action === 'branch'
}

export default function RoomCommandDrawer({
  open,
  onClose,
  threadId,
  externalRef,
  onApplied,
  initialAction = 'correct',
  initialDraft = '',
}: Props) {
  const pageVisible = usePageVisibility()
  const [action, setAction] = useState<ActionKind>(initialAction)
  const [draft, setDraft] = useState('')
  const [contextMode, setContextMode] = useState('project-only')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [command, setCommand] = useState<RuntimeCommand | null>(null)
  const [copied, setCopied] = useState(false)
  const pollTimerRef = useRef<number | null>(null)
  const chatId = useMemo(() => parseTelegramChatId(externalRef), [externalRef])
  const commandText = useMemo(() => buildCommand(action, draft, contextMode), [action, draft, contextMode])
  const selected = ACTIONS.find((item) => item.id === action) || ACTIONS[0]

  useEffect(() => {
    if (!open) return
    setAction(initialAction)
    setDraft(initialDraft)
    setError('')
    setCommand(null)
  }, [open, initialAction, initialDraft])

  useEffect(() => {
    if (!open) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKeyDown)
    }
  }, [open, onClose])

  useEffect(() => () => {
    if (pollTimerRef.current) window.clearTimeout(pollTimerRef.current)
  }, [])

  async function poll(commandId: string, attempt = 0, startedAt = Date.now()) {
    try {
      const next = await api.runtimeCommand(commandId)
      setCommand(next)
      const status = clean(next?.status).toLowerCase() || 'queued'
      if (status === 'applied') {
        setSubmitting(false)
        onApplied?.()
        return
      }
      if (TERMINAL.has(status)) {
        setSubmitting(false)
        setError(clean(next?.error_message) || `작업방 변경이 ${status} 상태로 끝났습니다.`)
        return
      }
      if (Date.now() - startedAt >= 5 * 60 * 1000) {
        setSubmitting(false)
        setError(status === 'queued'
          ? '아직 적용 대기 중입니다. ddalggak의 runtime command worker 설정을 확인하거나 Telegram용 명령을 복사하세요.'
          : '작업방에서 계속 처리 중입니다. 잠시 뒤 상태를 다시 확인하세요.')
        return
      }
      pollTimerRef.current = window.setTimeout(
        () => void poll(commandId, attempt + 1, startedAt),
        runtimeCommandPollDelay(status, attempt, pageVisible),
      )
    } catch (pollError: any) {
      setSubmitting(false)
      setError(`${pollError?.message || String(pollError)} · 같은 command ID로 상태를 다시 확인할 수 있습니다.`)
    }
  }

  async function submit() {
    const tId = clean(threadId)
    if (!tId) {
      setError('먼저 작업방을 선택하세요.')
      return
    }
    if (!chatId) {
      setError('이 작업방에는 Telegram 연결 정보가 없습니다. 명령을 복사해 Telegram에서 실행하세요.')
      return
    }
    if (requiresDraft(action) && !clean(draft)) {
      setError('적용할 내용을 입력하세요.')
      return
    }
    setSubmitting(true)
    setError('')
    setCommand(null)
    try {
      const commandId = makeClientCommandId('cmd_goc_room')
      const out = await api.createRuntimeCommand({
        command_id: commandId,
        command_type: 'room_command',
        thread_id: tId,
        aggregate_type: 'room',
        aggregate_id: tId,
        payload: {
          command: commandText,
          chat_id: chatId,
          user_id: chatId,
          source: 'goc_room_workspace',
          client_request_id: commandId,
        },
      })
      const created = out?.command || out
      setCommand(created)
      const returnedCommandId = clean(created?.command_id)
      if (!returnedCommandId) throw new Error('Runtime command response did not include command_id')
      await poll(returnedCommandId)
    } catch (submitError: any) {
      setSubmitting(false)
      setError(submitError?.message || String(submitError))
    }
  }

  async function copyFallback() {
    await copyText(commandText)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }

  if (!open) return null

  return (
    <div className="roomCommandOverlay" role="presentation" onMouseDown={(event) => {
      if (event.currentTarget === event.target) onClose()
    }}>
      <aside className="roomCommandDrawer" role="dialog" aria-modal="true" aria-label="Edit Room">
        <header className="roomCommandDrawerHeader">
          <div>
            <div className="runStudioEyebrow">작업방 수정</div>
            <h2>작업방 수정</h2>
            <p>ddalggak runtime을 통해 안전하게 적용합니다. 변경 결과는 Telegram과 GoC에 함께 남습니다.</p>
          </div>
          <button className="iconButton" onClick={onClose} aria-label="작업방 수정 닫기">×</button>
        </header>

        <div className="roomCommandActionList" role="tablist" aria-label="작업방 수정 종류">
          {ACTIONS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`roomCommandAction ${action === item.id ? 'isActive' : ''}`}
              onClick={() => { setAction(item.id); setError(''); setCommand(null) }}
            >
              <span>{item.label}</span>
              <small>{item.helper}</small>
            </button>
          ))}
        </div>

        <section className="roomCommandForm">
          <div className="roomCommandFormIntro">
            <b>{selected.label}</b>
            <span>{selected.helper}</span>
          </div>

          {action === 'context_mode' ? (
            <label>
              <span>정보 사용 방식</span>
              <select value={contextMode} onChange={(event) => setContextMode(event.target.value)}>
                <option value="project-only">이 작업방 자료만 사용</option>
                <option value="clean-slate">다음 요청은 새로 시작</option>
                <option value="reset">작업방 기본값으로 복원</option>
              </select>
            </label>
          ) : requiresDraft(action) ? (
            <label>
              <span>{action === 'exclude_source' ? '제외할 자료 또는 가정' : '변경 내용'}</span>
              <textarea
                autoFocus
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder={
                  action === 'correct' ? '예: 이번 작업에서는 UI만 수정하고 backend schema는 바꾸지 마.'
                    : action === 'rule' ? '예: 업로드한 파일과 충돌하면 파일을 정본으로 사용해.'
                      : action === 'exclude_source' ? '예: inventory-old.csv 또는 이전 PostgreSQL 가정'
                        : '예: 현재 설계를 보존하면서 local-first 대안을 별도 비교'
                }
              />
            </label>
          ) : (
            <div className="roomCommandInfoBox">현재 또는 가장 최근 작업을 이어갑니다.</div>
          )}

          <div className="roomCommandPreview">
            <span>실행 명령</span>
            <code>{commandText}</code>
          </div>
          <div className="roomCommandWorkerHint">바로 적용하려면 ddalggak runtime command worker가 필요합니다.  <code>GOC_RUNTIME_COMMAND_POLL_ENABLED=true</code> 설정을 이 작업방의 runtime에서 켜두세요.</div>

          {!chatId && (
            <div className="runStudioWarning">이 작업방에서 Telegram 연결 정보를 찾지 못했습니다. 바로 적용할 수는 없지만 명령을 복사할 수 있습니다.</div>
          )}
          {error && <div className="runStudioWarning">{error}</div>}
          {command && (
            <div className={`roomCommandStatus roomCommandStatus--${clean(command.status).toLowerCase() || 'queued'}`}>
              <b>{clean(command.status) || 'queued'}</b>
              <span>{clean(command.command_id)}</span>
              {clean(command.error_message) && <small>{clean(command.error_message)}</small>}
            </div>
          )}

          <div className="roomCommandFooter">
            <button onClick={copyFallback}>{copied ? '복사됨' : '명령 복사'}</button>
            {!submitting && command?.command_id && command?.status && !TERMINAL.has(clean(command.status).toLowerCase()) && (
              <button onClick={() => { setSubmitting(true); setError(''); void poll(clean(command.command_id)) }}>상태 다시 확인</button>
            )}
            <button className="primary" onClick={submit} disabled={submitting || (requiresDraft(action) && !clean(draft)) || !chatId}>
              {submitting ? '적용 중…' : '작업방에 적용'}
            </button>
          </div>
        </section>
      </aside>
    </div>
  )
}
