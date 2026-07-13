import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { copyText } from '../utils/clipboard'

type Manifest = {
  schema_version: string
  product_positioning?: Record<string, any>
  companions: Array<{
    id: string
    label: string
    purpose: string
    best_for?: string[]
    memory_connections?: Array<{ source: string; mode: string; strictness: string }>
    excluded_by_default?: string[]
    agent_mode?: string
    action_policy?: string
    branch_policy?: string
  }>
  context_modes: Array<{ id: string; label: string; description: string; telegram_command: string; risk?: string }>
  agent_modes: Array<{ id: string; label: string; description: string; telegram_command: string }>
  user_flows: Array<{ id: string; label: string; description: string; commands?: string[] }>
  runtime_status?: Record<string, any>
  ux_notes?: string[]
  non_goals?: string[]
}

type CopyStatus = {
  text: string
  at: number
}

function asCommandForCompanion(id: string): string {
  return `/companion switch ${id}`
}

function shortList(items?: string[], max = 4): string {
  const values = Array.isArray(items) ? items.filter(Boolean) : []
  if (values.length === 0) return '—'
  if (values.length <= max) return values.join(', ')
  return `${values.slice(0, max).join(', ')} +${values.length - max}`
}

async function copyCommand(command: string, setCopyStatus: (status: CopyStatus) => void) {
  await copyText(command)
  setCopyStatus({ text: command, at: Date.now() })
}

export default function CompanionControlHub({ threadId }: { threadId?: string | null }) {
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeCompanionId, setActiveCompanionId] = useState('research')
  const [excludeDraft, setExcludeDraft] = useState('')
  const [correctionDraft, setCorrectionDraft] = useState('')
  const [copyStatus, setCopyStatus] = useState<CopyStatus | null>(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError('')
      try {
        const out = await api.companionControlManifest()
        if (cancelled) return
        setManifest(out)
        if (Array.isArray(out?.companions) && out.companions[0]?.id) {
          setActiveCompanionId((prev) => prev || out.companions[0].id)
        }
      } catch (e: any) {
        if (!cancelled) setError(e?.message || String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const activeCompanion = useMemo(() => {
    return manifest?.companions?.find((item) => item.id === activeCompanionId) || manifest?.companions?.[0] || null
  }, [manifest, activeCompanionId])

  const contextModes = manifest?.context_modes || []
  const agentModes = manifest?.agent_modes || []
  const runtimeStatus = manifest?.runtime_status || {}

  if (loading) {
    return (
      <div className="card companionHub">
        <div className="muted">Room Home을 불러오는 중…</div>
      </div>
    )
  }

  if (error || !manifest) {
    return (
      <div className="card companionHub">
        <h3 style={{ marginTop: 0 }}>Room Home</h3>
        <div className="runStudioWarning">Companion control manifest를 불러오지 못했습니다. {error}</div>
      </div>
    )
  }

  return (
    <div className="companionHubStack">
      <div className="card companionHero">
        <div>
          <h2 style={{ marginTop: 0, marginBottom: 6 }}>Room Home</h2>
          <p className="muted" style={{ marginTop: 0 }}>
            이 Room의 목표·근거·규칙·정정·진행 상태를 먼저 확인합니다.
            Companion, Agent, 모델 설정은 필요한 경우에만 조정합니다.
          </p>
          <div className="row" style={{ marginBottom: 0 }}>
            <span className="pill">{manifest.schema_version}</span>
            {threadId && <span className="pill">thread {threadId.slice(0, 6)}</span>}
            <span className="pill">{runtimeStatus?.goc_web_runtime || 'web scaffold'}</span>
          </div>
        </div>
        <div className="companionHeroAside">
          <b>{manifest.product_positioning?.principle || 'The model can change. The Room remembers.'}</b>
          <p className="muted" style={{ marginBottom: 0 }}>
            Room state는 사용자 통제 아래 유지됩니다. durable write는 review 가능한 runtime command surface를 통해 처리합니다.
          </p>
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>Room continuity shortcuts</h3>
        <p className="muted">Telegram에서 현재 Room 상태를 확인하고, 같은 목표와 제약을 유지한 채 이어가거나 분기할 수 있습니다.</p>
        <div className="companionCommandList">
          {['/brief', '/continue', '/sources', '/rules', '/correct <correction>', '/branch <new direction>'].map((command) => (
            <button key={command} onClick={() => copyCommand(command, setCopyStatus)}>{command}</button>
          ))}
        </div>
      </div>

      <div className="companionGrid">
        <div className="card companionCardWide">
          <h3 style={{ marginTop: 0 }}>1. Companion 선택 (optional)</h3>
          <div className="companionList">
            {manifest.companions.map((item) => (
              <button
                key={item.id}
                className={`companionChoice ${activeCompanionId === item.id ? 'isActive' : ''}`}
                onClick={() => setActiveCompanionId(item.id)}
              >
                <b>{item.label}</b>
                <span>{item.purpose}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="card companionCardWide">
          <h3 style={{ marginTop: 0 }}>선택된 Companion</h3>
          {activeCompanion && (
            <>
              <div className="row" style={{ marginBottom: 8 }}>
                <span className="pill">{activeCompanion.id}</span>
                <span className="pill">mode: {activeCompanion.agent_mode || 'balanced'}</span>
                <span className="pill">action: {activeCompanion.action_policy || '—'}</span>
              </div>
              <p style={{ marginTop: 0 }}>{activeCompanion.purpose}</p>
              <p className="muted"><b>잘하는 것:</b> {shortList(activeCompanion.best_for, 6)}</p>
              <p className="muted"><b>기본 제외:</b> {shortList(activeCompanion.excluded_by_default, 6)}</p>
              <div className="companionSourceList">
                {(activeCompanion.memory_connections || []).map((conn) => (
                  <span key={`${conn.source}:${conn.mode}`} className="pill">
                    {conn.source} · {conn.mode} · {conn.strictness}
                  </span>
                ))}
              </div>
              <div className="row" style={{ marginTop: 12, marginBottom: 0 }}>
                <button className="primary" onClick={() => copyCommand(asCommandForCompanion(activeCompanion.id), setCopyStatus)}>
                  Copy switch command
                </button>
                <button onClick={() => copyCommand('/companion profile', setCopyStatus)}>Copy profile command</button>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="companionGrid">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>2. Context control</h3>
          <p className="muted">이번 질문에서 사용할 context를 줄이거나 stale assumption을 제외합니다.</p>
          {contextModes.map((mode) => (
            <div key={mode.id} className="companionActionRow">
              <div>
                <b>{mode.label}</b>
                <div className="muted">{mode.description}</div>
              </div>
              <button onClick={() => copyCommand(mode.telegram_command, setCopyStatus)}>Copy</button>
            </div>
          ))}
          <div className="companionInlineDraft">
            <input
              value={excludeDraft}
              onChange={(event) => setExcludeDraft(event.target.value)}
              placeholder="exclude할 source/assumption"
            />
            <button
              onClick={() => copyCommand(`/context exclude ${excludeDraft.trim() || '<source-or-assumption>'}`, setCopyStatus)}
            >
              Copy exclude
            </button>
          </div>
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>3. Agent mode</h3>
          <p className="muted">사용자가 원하는 strictness에 맞춰 low-risk 진행성과 high-risk 확인을 조절합니다.</p>
          {agentModes.map((mode) => (
            <div key={mode.id} className="companionActionRow">
              <div>
                <b>{mode.label}</b>
                <div className="muted">{mode.description}</div>
              </div>
              <button onClick={() => copyCommand(mode.telegram_command, setCopyStatus)}>Copy</button>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>4. Correct once, prevent repeats</h3>
        <p className="muted">
          정정은 room-local로 즉시 반영됩니다. durable해 보이는 정정은 silent memory가 아니라 reviewable merge proposal로 남고, accepted proposal은 branchable materialization 후보로만 연결됩니다.
        </p>
        <div className="companionInlineDraft">
          <input
            value={correctionDraft}
            onChange={(event) => setCorrectionDraft(event.target.value)}
            placeholder="예: 앞으로 docs-only면 runtime code는 건드리지 마"
          />
          <button
            className="primary"
            onClick={() => copyCommand(`/correct ${correctionDraft.trim() || '<correction>'}`, setCopyStatus)}
          >
            Copy correction
          </button>
          <button onClick={() => copyCommand('/correct proposals', setCopyStatus)}>Copy proposals</button>
          <button onClick={() => copyCommand('/correct approve latest', setCopyStatus)}>Copy approve</button>
          <button onClick={() => copyCommand('/correct materialize-preview', setCopyStatus)}>Copy materialization preview</button>
          <button onClick={() => copyCommand('/correct reject latest <reason>', setCopyStatus)}>Copy reject</button>
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>추천 사용 흐름</h3>
        <div className="companionFlowGrid">
          {manifest.user_flows.map((flow) => (
            <div key={flow.id} className="companionFlowCard">
              <b>{flow.label}</b>
              <p className="muted">{flow.description}</p>
              <div className="companionCommandList">
                {(flow.commands || []).map((command) => (
                  <button key={command} onClick={() => copyCommand(command, setCopyStatus)}>{command}</button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card companionNotes">
        <div>
          <h3 style={{ marginTop: 0 }}>UX guardrails</h3>
          <ul>
            {(manifest.ux_notes || []).map((note) => <li key={note}>{note}</li>)}
          </ul>
        </div>
        <div>
          <h3 style={{ marginTop: 0 }}>Non-goals</h3>
          <ul>
            {(manifest.non_goals || []).map((note) => <li key={note}>{note}</li>)}
          </ul>
        </div>
      </div>

      {copyStatus && (
        <div className="companionCopyToast">
          Copied: <code>{copyStatus.text}</code>
        </div>
      )}
    </div>
  )
}
