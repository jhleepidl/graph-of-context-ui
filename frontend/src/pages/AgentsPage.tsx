import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api, getStoredAdminKey } from '../api'
import ConversationAgentsPanel from '../components/ConversationAgentsPanel'

type Props = {
  onNavigate: (path: string) => void
}

type AgentVisibility = 'private' | 'unlisted' | 'public'
type AgentScope = 'my' | 'public' | 'installed'
type ThreadMembershipState = 'represented' | 'disabled' | 'missing'

type AgentRecord = {
  id: string
  owner_user_id: string
  owner: AgentOwnerSummary | null
  service_id: string
  name: string
  description: string
  system_prompt: string
  instruction: string
  tools: string[]
  model: string
  visibility: AgentVisibility
  source_agent_id: string | null
  system_key: string | null
  is_system_default: boolean
  is_archived: boolean
  created_at: string
  updated_at: string
  can_write: boolean
}

type AgentForm = {
  name: string
  description: string
  system_prompt: string
  instruction: string
  tools_text: string
  model: string
  visibility: AgentVisibility
}

type AgentOwnerSummary = {
  user_id: string
  telegram_user_id: string
  username: string
  display_name: string
}

type ThreadSummary = {
  id: string
  title: string
  created_at: string
  updated_at: string
}

type ConversationMembership = {
  agent_id: string
  enabled: boolean
  lineage_key: string
}

function asString(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

function asBool(value: unknown): boolean {
  return value === true
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  const out: string[] = []
  const seen = new Set<string>()
  for (const row of value) {
    const clean = asString(row)
    if (!clean || seen.has(clean)) continue
    seen.add(clean)
    out.push(clean)
  }
  return out
}

function normalizeVisibility(value: unknown): AgentVisibility {
  const clean = asString(value).toLowerCase()
  if (clean === 'public') return 'public'
  if (clean === 'unlisted') return 'unlisted'
  return 'private'
}

function normalizeAgent(raw: any): AgentRecord | null {
  if (!raw || typeof raw !== 'object') return null
  const id = asString(raw.id)
  if (!id) return null
  let owner: AgentOwnerSummary | null = null
  if (raw.owner && typeof raw.owner === 'object') {
    owner = {
      user_id: asString((raw.owner as any).user_id),
      telegram_user_id: asString((raw.owner as any).telegram_user_id),
      username: asString((raw.owner as any).username),
      display_name: asString((raw.owner as any).display_name),
    }
  }
  return {
    id,
    owner_user_id: asString(raw.owner_user_id),
    owner,
    service_id: asString(raw.service_id),
    name: asString(raw.name) || `agent-${id.slice(0, 8)}`,
    description: asString(raw.description),
    system_prompt: asString(raw.system_prompt),
    instruction: asString(raw.instruction),
    tools: asStringArray(raw.tools),
    model: asString(raw.model),
    visibility: normalizeVisibility(raw.visibility),
    source_agent_id: asString(raw.source_agent_id) || null,
    system_key: asString(raw.system_key) || null,
    is_system_default: asBool(raw.is_system_default),
    is_archived: asBool(raw.is_archived),
    created_at: asString(raw.created_at),
    updated_at: asString(raw.updated_at),
    can_write: asBool(raw.can_write),
  }
}

function normalizeThread(raw: any): ThreadSummary | null {
  if (!raw || typeof raw !== 'object') return null
  const id = asString(raw.id)
  if (!id) return null
  return {
    id,
    title: asString(raw.title) || `Untitled ${id.slice(0, 8)}`,
    created_at: asString(raw.created_at),
    updated_at: asString(raw.updated_at),
  }
}

function normalizeConversationMemberships(raw: any): ConversationMembership[] {
  const root = raw && typeof raw === 'object' ? raw : {}
  const conversation = root.conversation && typeof root.conversation === 'object' ? root.conversation : root
  const rows = Array.isArray((conversation as any)?.agents) ? (conversation as any).agents : []
  return rows
    .map((row: any) => {
      const agentId = asString(row?.agent_id || row?.agent?.id)
      if (!agentId) return null
      const sourceAgentId = asString(row?.agent?.source_agent_id) || null
      return {
        agent_id: agentId,
        enabled: asBool(row?.enabled),
        lineage_key: sourceAgentId || agentId,
      }
    })
    .filter((row: ConversationMembership | null): row is ConversationMembership => Boolean(row))
}

function timestampMs(value: string): number {
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function emptyForm(defaultVisibility: AgentVisibility = 'private'): AgentForm {
  return {
    name: '',
    description: '',
    system_prompt: '',
    instruction: '',
    tools_text: '',
    model: '',
    visibility: defaultVisibility,
  }
}

function toForm(agent: AgentRecord): AgentForm {
  return {
    name: agent.name,
    description: agent.description,
    system_prompt: agent.system_prompt,
    instruction: agent.instruction,
    tools_text: agent.tools.join('\n'),
    model: agent.model,
    visibility: agent.visibility,
  }
}

function parseTools(text: string): string[] {
  return text
    .split(/\r?\n|,/g)
    .map((row) => row.trim())
    .filter(Boolean)
    .filter((row, index, arr) => arr.indexOf(row) === index)
}

function formValidation(form: AgentForm): string {
  if (!form.name.trim()) return 'name을 입력하세요.'
  return ''
}

function scopeLabel(scope: AgentScope): string {
  if (scope === 'public') return 'Public'
  if (scope === 'installed') return 'Installed'
  return 'My Agents'
}

function membershipStateLabel(state: ThreadMembershipState): string {
  if (state === 'represented') return 'Already represented'
  if (state === 'disabled') return 'Disabled in thread'
  return 'Not in thread'
}

function lineageKeyForAgent(agent: Pick<AgentRecord, 'id' | 'source_agent_id'>): string {
  const sourceAgentId = asString(agent.source_agent_id)
  return sourceAgentId || agent.id
}

function creatorPrimary(agent: AgentRecord): string {
  const username = asString(agent.owner?.username)
  if (username) return `@${username}`
  const displayName = asString(agent.owner?.display_name)
  if (displayName) return displayName
  const userId = asString(agent.owner?.user_id) || asString(agent.owner_user_id)
  if (userId) return `user:${userId.slice(0, 8)}`
  return '-'
}

function creatorMeta(agent: AgentRecord): string {
  const ownerUserId = asString(agent.owner?.user_id) || asString(agent.owner_user_id)
  const telegramUserId = asString(agent.owner?.telegram_user_id)
  const out: string[] = []
  if (ownerUserId) out.push(`uid:${ownerUserId.slice(0, 8)}`)
  if (telegramUserId) out.push(`tg:${telegramUserId.slice(0, 10)}`)
  return out.join(' · ')
}

function readLinkedThreadId(): string | null {
  if (typeof window === 'undefined') return null
  const params = new URLSearchParams(window.location.search)
  const fromLink = (params.get('thread') || '').trim()
  return fromLink || null
}

export default function AgentsPage({ onNavigate }: Props) {
  const isAdminViewer = Boolean(getStoredAdminKey())
  const [scope, setScope] = useState<AgentScope>('my')
  const [agents, setAgents] = useState<AgentRecord[]>([])
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [busyAgentId, setBusyAgentId] = useState<string | null>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [createForm, setCreateForm] = useState<AgentForm>(() => emptyForm('private'))
  const [creating, setCreating] = useState(false)
  const [editingAgent, setEditingAgent] = useState<AgentRecord | null>(null)
  const [editForm, setEditForm] = useState<AgentForm>(() => emptyForm('private'))
  const [savingEdit, setSavingEdit] = useState(false)
  const [bootstrappingDefaults, setBootstrappingDefaults] = useState(false)
  const [threadTeamRefreshKey, setThreadTeamRefreshKey] = useState(0)

  const [linkedThreadId, setLinkedThreadId] = useState<string | null>(() => readLinkedThreadId())
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [threadsLoading, setThreadsLoading] = useState(true)
  const [selectedThreadId, setSelectedThreadId] = useState<string>('')
  const [threadSelectionInitialized, setThreadSelectionInitialized] = useState(false)
  const [membershipLoading, setMembershipLoading] = useState(false)
  const [membershipByLineageKey, setMembershipByLineageKey] = useState<Record<string, { enabled: boolean }>>({})

  const sortedAgents = useMemo(() => {
    return [...agents].sort((a, b) => {
      if (a.updated_at === b.updated_at) return a.id.localeCompare(b.id)
      return a.updated_at > b.updated_at ? -1 : 1
    })
  }, [agents])

  const selectedThread = useMemo(
    () => threads.find((thread) => thread.id === selectedThreadId) || null,
    [threads, selectedThreadId],
  )

  const selectedThreadLabel = useMemo(() => {
    if (selectedThread) return `${selectedThread.title} (${selectedThread.id.slice(0, 8)})`
    if (selectedThreadId) return selectedThreadId.slice(0, 8)
    return ''
  }, [selectedThread, selectedThreadId])

  const reloadAgents = useCallback(async (nextScope: AgentScope = scope) => {
    setLoading(true)
    setError('')
    try {
      const out = await api.agents(nextScope, false)
      const rows = Array.isArray(out?.items) ? out.items : []
      const mapped = rows
        .map((row) => normalizeAgent(row))
        .filter((row): row is AgentRecord => Boolean(row))
      setAgents(mapped)
    } catch (e) {
      setAgents([])
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [scope])

  const reloadThreads = useCallback(async () => {
    setThreadsLoading(true)
    setError('')
    try {
      const out = await api.threads()
      const rows = Array.isArray(out) ? out : []
      const mapped = rows
        .map((row) => normalizeThread(row))
        .filter((row): row is ThreadSummary => Boolean(row))
        .sort((a, b) => {
          const aScore = timestampMs(a.updated_at) || timestampMs(a.created_at)
          const bScore = timestampMs(b.updated_at) || timestampMs(b.created_at)
          if (aScore !== bScore) return bScore - aScore
          return a.id.localeCompare(b.id)
        })
      setThreads(mapped)
    } catch (e) {
      setThreads([])
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setThreadsLoading(false)
    }
  }, [])

  const reloadMembership = useCallback(async (threadId: string | null) => {
    const cleanThreadId = (threadId || '').trim()
    if (!cleanThreadId) {
      setMembershipByLineageKey({})
      return
    }
    setMembershipByLineageKey({})
    setMembershipLoading(true)
    setError('')
    try {
      await api.ensureConversation(cleanThreadId)
      const out = await api.conversationAgents(cleanThreadId)
      const memberships = normalizeConversationMemberships(out)
      const next: Record<string, { enabled: boolean }> = {}
      for (const membership of memberships) {
        const key = membership.lineage_key || membership.agent_id
        if (!next[key]) {
          next[key] = { enabled: membership.enabled }
          continue
        }
        next[key].enabled = next[key].enabled || membership.enabled
      }
      setMembershipByLineageKey(next)
    } catch (e) {
      setMembershipByLineageKey({})
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setMembershipLoading(false)
    }
  }, [])

  useEffect(() => {
    void reloadAgents(scope)
  }, [scope, reloadAgents])

  useEffect(() => {
    void reloadThreads()
  }, [reloadThreads])

  useEffect(() => {
    function handlePopState() {
      const nextLinkedThreadId = readLinkedThreadId()
      setLinkedThreadId(nextLinkedThreadId)
      if (!nextLinkedThreadId) {
        setSelectedThreadId('')
      }
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    if (threadSelectionInitialized) return
    if (threadsLoading) return
    const nextSelected = linkedThreadId || threads[0]?.id || ''
    setSelectedThreadId(nextSelected)
    setThreadSelectionInitialized(true)
  }, [linkedThreadId, threadSelectionInitialized, threads, threadsLoading])

  useEffect(() => {
    if (!linkedThreadId) return
    setSelectedThreadId(linkedThreadId)
  }, [linkedThreadId])

  useEffect(() => {
    if (!threadSelectionInitialized) return
    const selected = selectedThreadId.trim()
    const currentUrlThread = readLinkedThreadId() || ''
    if (selected === currentUrlThread) return
    if (selected) {
      onNavigate(`/agents?thread=${encodeURIComponent(selected)}`)
      setLinkedThreadId(selected)
      return
    }
    onNavigate('/agents')
    setLinkedThreadId(null)
  }, [selectedThreadId, threadSelectionInitialized, onNavigate])

  useEffect(() => {
    void reloadMembership(selectedThreadId || null)
  }, [selectedThreadId, reloadMembership])

  function getMembershipState(agent: AgentRecord): ThreadMembershipState {
    const membership = membershipByLineageKey[lineageKeyForAgent(agent)]
    if (!membership) return 'missing'
    return membership.enabled ? 'represented' : 'disabled'
  }

  async function handleCreate() {
    const validationError = formValidation(createForm)
    if (validationError) {
      setError(validationError)
      return
    }
    setCreating(true)
    setError('')
    setStatus('')
    try {
      await api.createAgent({
        name: createForm.name.trim(),
        description: createForm.description.trim(),
        system_prompt: createForm.system_prompt,
        instruction: createForm.instruction,
        tools: parseTools(createForm.tools_text),
        model: createForm.model.trim(),
        visibility: createForm.visibility,
      })
      setShowCreateModal(false)
      setCreateForm(emptyForm('private'))
      setScope('my')
      await reloadAgents('my')
      setStatus('새 agent를 생성했습니다.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setCreating(false)
    }
  }

  function openEdit(agent: AgentRecord) {
    setEditingAgent(agent)
    setEditForm(toForm(agent))
    setError('')
    setStatus('')
  }

  async function handleSaveEdit() {
    if (!editingAgent) return
    const validationError = formValidation(editForm)
    if (validationError) {
      setError(validationError)
      return
    }
    setSavingEdit(true)
    setError('')
    try {
      await api.patchAgent(editingAgent.id, {
        name: editForm.name.trim(),
        description: editForm.description.trim(),
        system_prompt: editForm.system_prompt,
        instruction: editForm.instruction,
        tools: parseTools(editForm.tools_text),
        model: editForm.model.trim(),
        visibility: editForm.visibility,
      })
      setEditingAgent(null)
      await reloadAgents(scope)
      setStatus(`agent 수정 완료: ${editingAgent.name}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSavingEdit(false)
    }
  }

  async function handlePublishToggle(agent: AgentRecord) {
    setBusyAgentId(agent.id)
    setError('')
    setStatus('')
    try {
      if (agent.visibility === 'public') {
        await api.unpublishAgent(agent.id)
        setStatus(`unpublish 완료: ${agent.name}`)
      } else {
        await api.publishAgent(agent.id)
        setStatus(`publish 완료: ${agent.name}`)
      }
      await reloadAgents(scope)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyAgentId(null)
    }
  }

  async function handleFork(agent: AgentRecord) {
    setBusyAgentId(agent.id)
    setError('')
    setStatus('')
    try {
      const out = await api.forkAgent(agent.id, { visibility: 'private' })
      const created = normalizeAgent(out?.agent)
      setScope('my')
      await reloadAgents('my')
      setStatus(created ? `fork 완료: ${created.name}` : `fork 완료: ${agent.name}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyAgentId(null)
    }
  }

  async function handleArchive(agent: AgentRecord, archived: boolean) {
    setBusyAgentId(agent.id)
    setError('')
    setStatus('')
    try {
      await api.archiveAgent(agent.id, archived)
      await reloadAgents(scope)
      setStatus(`${archived ? 'archive' : 'unarchive'} 완료: ${agent.name}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyAgentId(null)
    }
  }

  async function handleAddToConversation(agent: AgentRecord) {
    const targetThreadId = selectedThreadId.trim()
    if (!targetThreadId) {
      setError('먼저 대상 thread를 선택하세요.')
      return
    }
    const membershipState = getMembershipState(agent)
    const targetThreadLabel = selectedThread?.title || targetThreadId.slice(0, 8)
    if (membershipState === 'represented') {
      setError('')
      setStatus(`${targetThreadLabel} thread에는 이미 같은 계열(agent lineage)의 멤버가 있습니다.`)
      return
    }
    if (membershipState === 'disabled') {
      setError('')
      setStatus(`${targetThreadLabel} thread에는 같은 계열의 비활성 멤버가 있습니다. Thread Team에서 활성화하세요.`)
      return
    }

    setBusyAgentId(agent.id)
    setError('')
    setStatus('')
    try {
      await api.ensureConversation(targetThreadId)
      await api.addConversationAgent(targetThreadId, {
        agent_id: agent.id,
        enabled: true,
      })
      setStatus(`${targetThreadLabel} thread에 agent를 추가했습니다: ${agent.name}`)
      await reloadMembership(targetThreadId)
      setThreadTeamRefreshKey((v) => v + 1)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyAgentId(null)
    }
  }

  async function handleBootstrapDefaults() {
    setBootstrappingDefaults(true)
    setError('')
    setStatus('')
    try {
      const threadId = selectedThreadId.trim()
      const out = await api.bootstrapDefaultAgents({
        thread_id: threadId || null,
        add_to_conversation: Boolean(threadId),
      })
      const count = Number(out?.installed_count || 0)
      setScope('my')
      await reloadAgents('my')
      if (threadId) {
        const threadName = selectedThread?.title || threadId.slice(0, 8)
        await reloadMembership(threadId)
        setStatus(`기본 agent ${count}개를 설치했고, ${threadName} thread 팀에도 반영했습니다.`)
      } else {
        setStatus(`기본 agent ${count}개를 My Agents로 설치했습니다.`)
      }
      setThreadTeamRefreshKey((v) => v + 1)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBootstrappingDefaults(false)
    }
  }

  function handleOpenWorkspace() {
    const targetThreadId = selectedThreadId.trim()
    if (!targetThreadId) {
      onNavigate('/')
      return
    }
    onNavigate(`/?thread=${encodeURIComponent(targetThreadId)}`)
  }

  function handleClearTargetThread() {
    setSelectedThreadId('')
    setMembershipByLineageKey({})
    setLinkedThreadId(null)
    onNavigate('/agents')
  }

  const selectedThreadNotListed = Boolean(selectedThreadId && !selectedThread)

  return (
    <div className="routePage">
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-start' }}>
        <div className="routeCard" style={{ flex: '1 1 760px', minWidth: 0 }}>
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h2 style={{ margin: 0 }}>Agent Catalog</h2>
            <div className="row" style={{ marginBottom: 0 }}>
              <button onClick={() => onNavigate('/')}>Back to Workspace</button>
              <button onClick={() => void reloadAgents(scope)} disabled={loading}>
                {loading ? 'Loading...' : 'Refresh'}
              </button>
              <button className="primary" onClick={() => setShowCreateModal(true)}>Create Agent</button>
            </div>
          </div>

          <div className="row">
            <button className={scope === 'my' ? 'primary' : ''} onClick={() => setScope('my')}>My Agents</button>
            <button className={scope === 'public' ? 'primary' : ''} onClick={() => setScope('public')}>Public</button>
            <button className={scope === 'installed' ? 'primary' : ''} onClick={() => setScope('installed')}>Installed</button>
            <span className="pill">{scopeLabel(scope)} · {sortedAgents.length}</span>
            <button onClick={() => void handleBootstrapDefaults()} disabled={bootstrappingDefaults}>
              {bootstrappingDefaults ? 'Installing defaults...' : 'Bootstrap Defaults'}
            </button>
          </div>

          <div className="row" style={{ alignItems: 'center', flexWrap: 'wrap' }}>
            <label className="routeLabel" style={{ marginBottom: 0 }}>
              Target Thread
              <select
                value={selectedThreadId}
                onChange={(e) => setSelectedThreadId(e.target.value)}
                style={{ minWidth: 340 }}
              >
                <option value="">(thread 선택)</option>
                {threads.map((thread) => (
                  <option key={thread.id} value={thread.id}>
                    {thread.title} ({thread.id.slice(0, 8)})
                  </option>
                ))}
                {selectedThreadNotListed && (
                  <option value={selectedThreadId}>
                    Unknown ({selectedThreadId.slice(0, 8)})
                  </option>
                )}
              </select>
            </label>
            {linkedThreadId && <span className="pill">linked from workspace</span>}
            {threadsLoading && <span className="pill">Loading threads...</span>}
            {membershipLoading && selectedThreadId && <span className="pill">Checking thread membership...</span>}
            <button onClick={handleOpenWorkspace} disabled={!selectedThreadId}>Open in Workspace</button>
            <button onClick={handleClearTargetThread} disabled={!selectedThreadId && !linkedThreadId}>Clear</button>
            {selectedThreadLabel && <span className="muted">현재 대상: {selectedThreadLabel}</span>}
          </div>

          {error && <div className="routeStatus routeStatusError">{error}</div>}
          {status && <div className="routeStatus">{status}</div>}

          <div className="routeTableWrap" style={{ marginTop: 10 }}>
            <table className="routeTable">
              <thead>
                <tr>
                  <th>name</th>
                  <th>visibility</th>
                  <th>model</th>
                  <th>tools</th>
                  <th>description</th>
                  {isAdminViewer && <th>creator</th>}
                  <th>thread</th>
                  <th>updated_at</th>
                  <th>actions</th>
                </tr>
              </thead>
              <tbody>
                {sortedAgents.map((agent) => {
                  const threadState = getMembershipState(agent)
                  const isBusy = busyAgentId === agent.id
                  const addLabel = isBusy
                    ? 'Working...'
                    : threadState === 'represented'
                      ? 'Already represented'
                      : threadState === 'disabled'
                        ? 'Disabled in thread'
                        : 'Add to thread'
                  const addDisabled = isBusy || threadState !== 'missing'

                  return (
                    <tr key={agent.id}>
                      <td>
                        <div><b>{agent.name}</b></div>
                        <div className="muted">
                          {agent.id.slice(0, 8)}
                          {agent.source_agent_id ? ` · source ${agent.source_agent_id.slice(0, 8)}` : ''}
                          {agent.is_system_default ? ' · system' : ''}
                        </div>
                      </td>
                      <td>{agent.visibility}</td>
                      <td>{agent.model || '-'}</td>
                      <td>{agent.tools.length ? agent.tools.join(', ') : '-'}</td>
                      <td style={{ maxWidth: 320 }}>
                        {(agent.description || agent.instruction || '').replace(/\s+/g, ' ').slice(0, 180) || '-'}
                      </td>
                      {isAdminViewer && (
                        <td>
                          <div title={creatorMeta(agent) || undefined}>{creatorPrimary(agent)}</div>
                          {creatorMeta(agent) && <div className="muted">{creatorMeta(agent)}</div>}
                        </td>
                      )}
                      <td>
                        <span className="pill">{membershipStateLabel(threadState)}</span>
                      </td>
                      <td>{agent.updated_at || '-'}</td>
                      <td>
                        <div className="row agentsActionRow">
                          <button onClick={() => void handleFork(agent)} disabled={isBusy}>
                            {isBusy ? 'Working...' : 'Fork'}
                          </button>
                          <button onClick={() => void handleAddToConversation(agent)} disabled={addDisabled}>
                            {addLabel}
                          </button>
                          {agent.can_write && (
                            <>
                              <button onClick={() => openEdit(agent)}>Edit</button>
                              <button onClick={() => void handlePublishToggle(agent)} disabled={isBusy}>
                                {agent.visibility === 'public' ? 'Unpublish' : 'Publish'}
                              </button>
                              <button
                                className="danger"
                                onClick={() => void handleArchive(agent, !agent.is_archived)}
                                disabled={isBusy}
                              >
                                {agent.is_archived ? 'Unarchive' : 'Archive'}
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
                {sortedAgents.length === 0 && !loading && (
                  <tr>
                    <td colSpan={isAdminViewer ? 9 : 8}>
                      <span className="muted">결과가 없습니다.</span>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        <div style={{ flex: '1 1 420px', minWidth: 320 }}>
          {selectedThreadId ? (
            <ConversationAgentsPanel
              threadId={selectedThreadId || null}
              refreshKey={threadTeamRefreshKey}
            />
          ) : (
            <div className="card">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <b>Thread Team</b>
              </div>
              <div className="muted" style={{ marginBottom: 6 }}>
                thread를 선택하면 이 대화의 agent 팀을 편집할 수 있습니다.
              </div>
              <div className="muted">
                enabled된 agent만 현재 thread의 router 대상입니다.
              </div>
            </div>
          )}
        </div>
      </div>

      {showCreateModal && (
        <div className="modalOverlay" onClick={() => setShowCreateModal(false)}>
          <div className="modalCard agentsEditModal" onClick={(e) => e.stopPropagation()}>
            <div className="row modalHeader">
              <h3 style={{ margin: 0 }}>Create Agent</h3>
              <button onClick={() => setShowCreateModal(false)}>Close</button>
            </div>
            <AgentFormFields form={createForm} onChange={setCreateForm} />
            <div className="row" style={{ justifyContent: 'flex-end', marginTop: 10 }}>
              <button onClick={() => setShowCreateModal(false)}>Cancel</button>
              <button className="primary" onClick={() => void handleCreate()} disabled={creating}>
                {creating ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      {editingAgent && (
        <div className="modalOverlay" onClick={() => setEditingAgent(null)}>
          <div className="modalCard agentsEditModal" onClick={(e) => e.stopPropagation()}>
            <div className="row modalHeader">
              <h3 style={{ margin: 0 }}>Edit Agent</h3>
              <button onClick={() => setEditingAgent(null)}>Close</button>
            </div>
            {isAdminViewer && (
              <div className="muted" style={{ marginBottom: 8 }}>
                Creator: {creatorPrimary(editingAgent)}{creatorMeta(editingAgent) ? ` · ${creatorMeta(editingAgent)}` : ''}
              </div>
            )}
            <AgentFormFields form={editForm} onChange={setEditForm} />
            <div className="row" style={{ justifyContent: 'flex-end', marginTop: 10 }}>
              <button onClick={() => setEditingAgent(null)}>Cancel</button>
              <button className="primary" onClick={() => void handleSaveEdit()} disabled={savingEdit}>
                {savingEdit ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function AgentFormFields({
  form,
  onChange,
}: {
  form: AgentForm
  onChange: React.Dispatch<React.SetStateAction<AgentForm>>
}) {
  return (
    <>
      <label className="routeLabel">
        name
        <input value={form.name} onChange={(e) => onChange((prev) => ({ ...prev, name: e.target.value }))} />
      </label>
      <label className="routeLabel">
        description
        <textarea
          value={form.description}
          onChange={(e) => onChange((prev) => ({ ...prev, description: e.target.value }))}
          style={{ minHeight: 72 }}
        />
      </label>
      <label className="routeLabel">
        system_prompt
        <textarea
          value={form.system_prompt}
          onChange={(e) => onChange((prev) => ({ ...prev, system_prompt: e.target.value }))}
          style={{ minHeight: 120 }}
        />
      </label>
      <label className="routeLabel">
        instruction
        <textarea
          value={form.instruction}
          onChange={(e) => onChange((prev) => ({ ...prev, instruction: e.target.value }))}
          style={{ minHeight: 100 }}
        />
      </label>
      <label className="routeLabel">
        model
        <input value={form.model} onChange={(e) => onChange((prev) => ({ ...prev, model: e.target.value }))} />
      </label>
      <label className="routeLabel">
        tools (newline or comma separated)
        <textarea
          value={form.tools_text}
          onChange={(e) => onChange((prev) => ({ ...prev, tools_text: e.target.value }))}
          style={{ minHeight: 70 }}
        />
      </label>
      <label className="routeLabel">
        visibility
        <select
          value={form.visibility}
          onChange={(e) => onChange((prev) => ({ ...prev, visibility: normalizeVisibility(e.target.value) }))}
        >
          <option value="private">private</option>
          <option value="unlisted">unlisted</option>
          <option value="public">public</option>
        </select>
      </label>
    </>
  )
}
