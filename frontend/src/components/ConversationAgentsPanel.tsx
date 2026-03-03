import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'

type Props = {
  threadId: string | null
}

type AgentItem = {
  id: string
  name: string
  visibility: 'private' | 'unlisted' | 'public'
  model: string
  source_agent_id: string | null
}

type ConversationMember = {
  id: string
  agent_id: string
  enabled: boolean
  order_index: number
  overrides_json: Record<string, unknown>
  agent: AgentItem
}

type ConversationState = {
  id: string
  thread_id: string
  owner_user_id: string
  agents: ConversationMember[]
}

function asString(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

function asBool(value: unknown): boolean {
  return value === true
}

function normalizeVisibility(value: unknown): 'private' | 'unlisted' | 'public' {
  const clean = asString(value).toLowerCase()
  if (clean === 'public') return 'public'
  if (clean === 'unlisted') return 'unlisted'
  return 'private'
}

function asObject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  return value as Record<string, unknown>
}

function normalizeAgent(raw: any): AgentItem | null {
  if (!raw || typeof raw !== 'object') return null
  const id = asString(raw.id)
  if (!id) return null
  return {
    id,
    name: asString(raw.name) || `agent-${id.slice(0, 8)}`,
    visibility: normalizeVisibility(raw.visibility),
    model: asString(raw.model),
    source_agent_id: asString(raw.source_agent_id) || null,
  }
}

function normalizeConversation(raw: any): ConversationState | null {
  if (!raw || typeof raw !== 'object') return null
  const id = asString(raw.id)
  const threadId = asString(raw.thread_id)
  if (!id || !threadId) return null
  const rows = Array.isArray(raw.agents) ? raw.agents : []
  const members: ConversationMember[] = rows
    .map((row: any) => {
      const agent = normalizeAgent(row?.agent)
      const agentId = asString(row?.agent_id || agent?.id)
      if (!agent || !agentId) return null
      return {
        id: asString(row?.id),
        agent_id: agentId,
        enabled: asBool(row?.enabled),
        order_index: Number.isFinite(Number(row?.order_index)) ? Number(row.order_index) : 0,
        overrides_json: asObject(row?.overrides_json),
        agent,
      }
    })
    .filter((row: ConversationMember | null): row is ConversationMember => Boolean(row))
    .sort((a, b) => a.order_index - b.order_index)
  return {
    id,
    thread_id: threadId,
    owner_user_id: asString(raw.owner_user_id),
    agents: members,
  }
}

export default function ConversationAgentsPanel({ threadId }: Props) {
  const [conversation, setConversation] = useState<ConversationState | null>(null)
  const [availableAgents, setAvailableAgents] = useState<AgentItem[]>([])
  const [selectedAgentId, setSelectedAgentId] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [overridesDraft, setOverridesDraft] = useState<Record<string, string>>({})

  const memberIdSet = useMemo(() => new Set((conversation?.agents || []).map((row) => row.agent_id)), [conversation])
  const candidateAgents = useMemo(
    () => availableAgents.filter((agent) => !memberIdSet.has(agent.id)),
    [availableAgents, memberIdSet],
  )

  const refresh = useCallback(async () => {
    if (!threadId) {
      setConversation(null)
      setAvailableAgents([])
      setSelectedAgentId('')
      return
    }
    setLoading(true)
    setError('')
    try {
      const [convOut, myOut, publicOut] = await Promise.all([
        api.ensureConversation(threadId),
        api.agents('my', false),
        api.agents('public', false),
      ])
      const nextConversation = normalizeConversation(convOut?.conversation)
      setConversation(nextConversation)
      const merged = new Map<string, AgentItem>()
      for (const source of [myOut?.items, publicOut?.items]) {
        const rows = Array.isArray(source) ? source : []
        for (const raw of rows) {
          const agent = normalizeAgent(raw)
          if (!agent) continue
          merged.set(agent.id, agent)
        }
      }
      const nextAvailable = [...merged.values()].sort((a, b) => a.name.localeCompare(b.name))
      setAvailableAgents(nextAvailable)
      setSelectedAgentId((prev) => {
        if (prev && nextAvailable.some((row) => row.id === prev)) return prev
        return nextAvailable[0]?.id || ''
      })
      const nextDraft: Record<string, string> = {}
      for (const member of nextConversation?.agents || []) {
        nextDraft[member.agent_id] = JSON.stringify(member.overrides_json || {}, null, 2)
      }
      setOverridesDraft(nextDraft)
    } catch (e) {
      setConversation(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [threadId])

  useEffect(() => {
    void refresh()
  }, [refresh])

  function applyConversationResponse(raw: any) {
    const next = normalizeConversation(raw)
    if (!next) return
    setConversation(next)
    const nextDraft: Record<string, string> = {}
    for (const member of next.agents) {
      nextDraft[member.agent_id] = JSON.stringify(member.overrides_json || {}, null, 2)
    }
    setOverridesDraft(nextDraft)
  }

  async function handleAddAgent() {
    if (!threadId) return
    const agentId = selectedAgentId.trim()
    if (!agentId) {
      setError('추가할 agent를 선택하세요.')
      return
    }
    setBusyId(agentId)
    setError('')
    setStatus('')
    try {
      const out = await api.addConversationAgent(threadId, { agent_id: agentId, enabled: true })
      applyConversationResponse(out?.conversation)
      setStatus('agent를 conversation에 추가했습니다.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyId(null)
    }
  }

  async function handleToggleEnabled(member: ConversationMember, enabled: boolean) {
    if (!threadId) return
    setBusyId(member.agent_id)
    setError('')
    setStatus('')
    try {
      const out = await api.patchConversationAgent(threadId, member.agent_id, { enabled })
      applyConversationResponse(out?.conversation)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyId(null)
    }
  }

  async function handleRemove(member: ConversationMember) {
    if (!threadId) return
    setBusyId(member.agent_id)
    setError('')
    setStatus('')
    try {
      const out = await api.removeConversationAgent(threadId, member.agent_id)
      applyConversationResponse(out?.conversation)
      setStatus(`agent 제거: ${member.agent.name}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyId(null)
    }
  }

  async function handleMove(member: ConversationMember, direction: -1 | 1) {
    if (!threadId || !conversation) return
    const ids = conversation.agents.map((row) => row.agent_id)
    const index = ids.indexOf(member.agent_id)
    if (index < 0) return
    const nextIndex = index + direction
    if (nextIndex < 0 || nextIndex >= ids.length) return
    const nextIds = [...ids]
    const tmp = nextIds[index]
    nextIds[index] = nextIds[nextIndex]
    nextIds[nextIndex] = tmp

    setBusyId(member.agent_id)
    setError('')
    setStatus('')
    try {
      const out = await api.reorderConversationAgents(threadId, nextIds)
      applyConversationResponse(out?.conversation)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyId(null)
    }
  }

  async function handleSaveOverrides(member: ConversationMember) {
    if (!threadId) return
    const raw = (overridesDraft[member.agent_id] || '').trim()
    let parsed: Record<string, unknown> = {}
    if (raw) {
      try {
        const value = JSON.parse(raw)
        if (!value || typeof value !== 'object' || Array.isArray(value)) {
          setError('overrides_json은 JSON object여야 합니다.')
          return
        }
        parsed = value as Record<string, unknown>
      } catch {
        setError('overrides_json JSON 파싱에 실패했습니다.')
        return
      }
    }
    setBusyId(member.agent_id)
    setError('')
    setStatus('')
    try {
      const out = await api.patchConversationAgent(threadId, member.agent_id, { overrides_json: parsed })
      applyConversationResponse(out?.conversation)
      setStatus(`overrides 저장 완료: ${member.agent.name}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyId(null)
    }
  }

  if (!threadId) {
    return <div className="card"><div className="muted">thread를 먼저 선택하세요.</div></div>
  }

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <b>Conversation Agents</b>
        <button onClick={() => void refresh()} disabled={loading}>{loading ? 'Loading...' : 'Refresh'}</button>
      </div>
      <div className="muted" style={{ marginBottom: 8 }}>
        enabled된 agent 목록이 현재 conversation의 router 대상입니다.
      </div>
      {error && <div className="routeStatus routeStatusError">{error}</div>}
      {status && <div className="routeStatus">{status}</div>}

      <div className="row">
        <select
          style={{ minWidth: 320 }}
          value={selectedAgentId}
          onChange={(e) => setSelectedAgentId(e.target.value)}
        >
          <option value="">(추가할 agent 선택)</option>
          {candidateAgents.map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.name} [{agent.visibility}] {agent.model ? `· ${agent.model}` : ''}
            </option>
          ))}
        </select>
        <button onClick={() => void handleAddAgent()} disabled={!selectedAgentId || busyId === selectedAgentId}>
          Add
        </button>
      </div>

      <div className="routeTableWrap">
        <table className="routeTable">
          <thead>
            <tr>
              <th>order</th>
              <th>agent</th>
              <th>enabled</th>
              <th>actions</th>
            </tr>
          </thead>
          <tbody>
            {(conversation?.agents || []).map((member, index) => (
              <tr key={member.agent_id}>
                <td>{index + 1}</td>
                <td>
                  <div><b>{member.agent.name}</b></div>
                  <div className="muted">{member.agent.id.slice(0, 8)} · {member.agent.visibility}</div>
                  <label className="routeLabel" style={{ marginTop: 8 }}>
                    overrides_json
                    <textarea
                      value={overridesDraft[member.agent_id] || '{}'}
                      onChange={(e) => setOverridesDraft((prev) => ({ ...prev, [member.agent_id]: e.target.value }))}
                      style={{ minHeight: 72 }}
                    />
                  </label>
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={member.enabled}
                    onChange={(e) => void handleToggleEnabled(member, e.target.checked)}
                    disabled={busyId === member.agent_id}
                  />
                </td>
                <td>
                  <div className="row agentsActionRow">
                    <button onClick={() => void handleMove(member, -1)} disabled={index === 0 || busyId === member.agent_id}>Up</button>
                    <button
                      onClick={() => void handleMove(member, 1)}
                      disabled={index === (conversation?.agents.length || 0) - 1 || busyId === member.agent_id}
                    >
                      Down
                    </button>
                    <button onClick={() => void handleSaveOverrides(member)} disabled={busyId === member.agent_id}>Save Overrides</button>
                    <button className="danger" onClick={() => void handleRemove(member)} disabled={busyId === member.agent_id}>Remove</button>
                  </div>
                </td>
              </tr>
            ))}
            {(conversation?.agents.length || 0) === 0 && !loading && (
              <tr>
                <td colSpan={4}>
                  <span className="muted">아직 conversation에 추가된 agent가 없습니다.</span>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
