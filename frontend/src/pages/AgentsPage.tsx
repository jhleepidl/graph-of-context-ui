import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'

type Props = {
  onNavigate: (path: string) => void
}

type AgentVisibility = 'private' | 'unlisted' | 'public'
type AgentScope = 'my' | 'public' | 'installed'

type AgentRecord = {
  id: string
  owner_user_id: string
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
  return {
    id,
    owner_user_id: asString(raw.owner_user_id),
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

export default function AgentsPage({ onNavigate }: Props) {
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

  const linkedThreadId = useMemo(() => {
    const params = new URLSearchParams(window.location.search)
    const fromLink = (params.get('thread') || '').trim()
    return fromLink || null
  }, [])
  const [conversationThreadId, setConversationThreadId] = useState<string>(linkedThreadId || '')

  const sortedAgents = useMemo(() => {
    return [...agents].sort((a, b) => {
      if (a.updated_at === b.updated_at) return a.id.localeCompare(b.id)
      return a.updated_at > b.updated_at ? -1 : 1
    })
  }, [agents])

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

  useEffect(() => {
    void reloadAgents(scope)
  }, [scope, reloadAgents])

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
    const targetThreadId = conversationThreadId.trim()
    if (!targetThreadId) {
      setError('conversation thread_id를 입력하세요.')
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
      setStatus(`대화(${targetThreadId.slice(0, 8)})에 agent를 추가했습니다: ${agent.name}`)
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
      const threadId = conversationThreadId.trim()
      const out = await api.bootstrapDefaultAgents({
        thread_id: threadId || null,
        add_to_conversation: Boolean(threadId),
      })
      const count = Number(out?.installed_count || 0)
      setScope('my')
      await reloadAgents('my')
      setStatus(`기본 agent ${count}개를 My Agents로 설치했습니다.`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBootstrappingDefaults(false)
    }
  }

  return (
    <div className="routePage">
      <div className="routeCard">
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

        <div className="row">
          <label className="muted">
            Current conversation thread_id:
            <input
              style={{ marginLeft: 8, minWidth: 280 }}
              value={conversationThreadId}
              onChange={(e) => setConversationThreadId(e.target.value)}
              placeholder="대화 thread_id"
            />
          </label>
          {linkedThreadId && <span className="pill">linked thread: {linkedThreadId.slice(0, 8)}</span>}
          <span className="muted">Workspace에서 열면 Add to current conversation 버튼으로 바로 추가할 수 있습니다.</span>
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
                <th>updated_at</th>
                <th>actions</th>
              </tr>
            </thead>
            <tbody>
              {sortedAgents.map((agent) => (
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
                  <td style={{ maxWidth: 360 }}>
                    {(agent.description || agent.instruction || '').replace(/\s+/g, ' ').slice(0, 180) || '-'}
                  </td>
                  <td>{agent.updated_at || '-'}</td>
                  <td>
                    <div className="row agentsActionRow">
                      <button onClick={() => void handleFork(agent)} disabled={busyAgentId === agent.id}>
                        {busyAgentId === agent.id ? 'Working...' : 'Fork'}
                      </button>
                      <button onClick={() => void handleAddToConversation(agent)} disabled={busyAgentId === agent.id}>
                        Add to current conversation
                      </button>
                      {agent.can_write && (
                        <>
                          <button onClick={() => openEdit(agent)}>Edit</button>
                          <button onClick={() => void handlePublishToggle(agent)} disabled={busyAgentId === agent.id}>
                            {agent.visibility === 'public' ? 'Unpublish' : 'Publish'}
                          </button>
                          <button
                            className="danger"
                            onClick={() => void handleArchive(agent, !agent.is_archived)}
                            disabled={busyAgentId === agent.id}
                          >
                            {agent.is_archived ? 'Unarchive' : 'Archive'}
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {sortedAgents.length === 0 && !loading && (
                <tr>
                  <td colSpan={7}>
                    <span className="muted">결과가 없습니다.</span>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
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
