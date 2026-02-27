import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'

const AGENTS_THREAD_TITLE = 'agents'
const AGENT_RESOURCE_KIND = 'agent_profile'

type Props = {
  onNavigate: (path: string) => void
}

type ThreadSummary = {
  id: string
  title?: string | null
}

type GraphNode = {
  id: string
  type?: string | null
  text?: string | null
  payload_json?: string | null
  created_at?: string | null
}

type AgentProfile = {
  nodeId: string
  createdAt: string
  rawText: string
  payload: Record<string, unknown>
  form: AgentForm
}

type AgentForm = {
  agent_id: string
  title: string
  provider: string
  model: string
  base_prompt: string
}

function createEmptyForm(): AgentForm {
  return {
    agent_id: '',
    title: '',
    provider: '',
    model: '',
    base_prompt: '',
  }
}

function normalizeTitle(title?: string | null): string {
  return (title || '').trim().toLowerCase()
}

function asString(v: unknown): string {
  if (typeof v === 'string') return v.trim()
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  return ''
}

function parsePayload(payloadJson?: string | null): Record<string, unknown> {
  try {
    const parsed = JSON.parse(payloadJson || '{}')
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
  } catch {
    // ignore malformed payload_json
  }
  return {}
}

function parseBasePromptFromText(text: string): string {
  const marker = 'Base Prompt:'
  const idx = text.indexOf(marker)
  if (idx < 0) return ''
  return text.slice(idx + marker.length).trim()
}

function normalizeForm(input: AgentForm): AgentForm {
  return {
    agent_id: input.agent_id.trim(),
    title: input.title.trim(),
    provider: input.provider.trim(),
    model: input.model.trim(),
    base_prompt: input.base_prompt.trim(),
  }
}

function validateForm(input: AgentForm): string {
  if (!input.agent_id.trim()) return 'agent_id를 입력하세요.'
  if (!input.title.trim()) return 'title을 입력하세요.'
  if (!input.provider.trim()) return 'provider를 입력하세요.'
  if (!input.model.trim()) return 'model을 입력하세요.'
  return ''
}

function buildAgentNodeText(form: AgentForm): string {
  const lines = [
    `Agent Profile: ${form.title}`,
    `Agent ID: ${form.agent_id}`,
    `Provider: ${form.provider}`,
    `Model: ${form.model}`,
  ]
  if (form.base_prompt) {
    lines.push('Base Prompt:')
    lines.push(form.base_prompt)
  }
  return lines.join('\n').trim()
}

function buildAgentPayload(existing: Record<string, unknown>, form: AgentForm): Record<string, unknown> {
  const next: Record<string, unknown> = {
    ...existing,
    name: form.title || form.agent_id,
    resource_kind: AGENT_RESOURCE_KIND,
    source: asString(existing.source) || 'manual',
    tag: asString(existing.tag) || 'RESOURCE',
    summary: form.base_prompt || null,
    agent_id: form.agent_id,
    title: form.title,
    provider: form.provider,
    model: form.model,
    base_prompt: form.base_prompt,
  }
  return next
}

function nodeToAgentProfile(node: GraphNode): AgentProfile | null {
  if ((node.type || '') !== 'Resource') return null
  const payload = parsePayload(node.payload_json)
  if (asString(payload.resource_kind) !== AGENT_RESOURCE_KIND) return null

  const rawText = asString(node.text)
  const form: AgentForm = {
    agent_id: asString(payload.agent_id) || asString(payload.name) || node.id.slice(0, 12),
    title: asString(payload.title) || asString(payload.name) || `agent-${node.id.slice(0, 6)}`,
    provider: asString(payload.provider),
    model: asString(payload.model),
    base_prompt: asString(payload.base_prompt) || asString(payload.summary) || parseBasePromptFromText(rawText),
  }

  return {
    nodeId: node.id,
    createdAt: asString(node.created_at),
    rawText,
    payload,
    form,
  }
}

export default function AgentsPage({ onNavigate }: Props) {
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [agentsThreadId, setAgentsThreadId] = useState<string | null>(null)
  const [profiles, setProfiles] = useState<AgentProfile[]>([])
  const [createForm, setCreateForm] = useState<AgentForm>(() => createEmptyForm())
  const [editForm, setEditForm] = useState<AgentForm>(() => createEmptyForm())
  const [editingProfile, setEditingProfile] = useState<AgentProfile | null>(null)
  const [loadingThreads, setLoadingThreads] = useState(false)
  const [loadingProfiles, setLoadingProfiles] = useState(false)
  const [creating, setCreating] = useState(false)
  const [savingEdit, setSavingEdit] = useState(false)
  const [deletingNodeId, setDeletingNodeId] = useState<string | null>(null)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')

  const linkedThreadId = useMemo(() => {
    const params = new URLSearchParams(window.location.search)
    const fromLink = (params.get('thread') || '').trim()
    return fromLink || null
  }, [])

  const agentsThread = useMemo(
    () => threads.find((thread) => thread.id === agentsThreadId) || null,
    [threads, agentsThreadId],
  )

  const sortedProfiles = useMemo(() => {
    return [...profiles].sort((a, b) => {
      if (a.createdAt === b.createdAt) return a.nodeId < b.nodeId ? -1 : 1
      return a.createdAt < b.createdAt ? 1 : -1
    })
  }, [profiles])

  const reloadProfiles = useCallback(async (threadId: string) => {
    setLoadingProfiles(true)
    setError('')
    try {
      const out = await api.graph(threadId)
      const graphNodes = Array.isArray(out?.nodes) ? (out.nodes as GraphNode[]) : []
      const mapped = graphNodes
        .map((node) => nodeToAgentProfile(node))
        .filter((item): item is AgentProfile => Boolean(item))
      setProfiles(mapped)
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
      setProfiles([])
    } finally {
      setLoadingProfiles(false)
    }
  }, [])

  const reloadThreads = useCallback(async (preferredThreadId?: string | null) => {
    setLoadingThreads(true)
    setError('')
    try {
      const out = await api.threads()
      const list = Array.isArray(out) ? (out as ThreadSummary[]) : []
      setThreads(list)
      setAgentsThreadId((current) => {
        if (preferredThreadId && list.some((thread) => thread.id === preferredThreadId)) {
          return preferredThreadId
        }
        if (current && list.some((thread) => thread.id === current)) {
          return current
        }
        if (linkedThreadId && list.some((thread) => thread.id === linkedThreadId)) {
          return linkedThreadId
        }
        const found = list.find((thread) => normalizeTitle(thread.title) === AGENTS_THREAD_TITLE)
        return found?.id || null
      })
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
      setThreads([])
      setAgentsThreadId(null)
    } finally {
      setLoadingThreads(false)
    }
  }, [linkedThreadId])

  useEffect(() => {
    void reloadThreads()
  }, [reloadThreads])

  useEffect(() => {
    if (!agentsThreadId) {
      setProfiles([])
      return
    }
    void reloadProfiles(agentsThreadId)
  }, [agentsThreadId, reloadProfiles])

  async function handleCreateAgentsThread() {
    setStatus('')
    setError('')
    try {
      const created = await api.createThread('agents')
      const nextId = asString((created as { id?: string }).id)
      await reloadThreads(nextId || null)
      setStatus('agents thread를 생성했습니다.')
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
    }
  }

  async function handleCreateProfile() {
    const threadId = agentsThreadId
    if (!threadId) {
      setError('agents thread를 먼저 선택하세요.')
      return
    }

    const cleanForm = normalizeForm(createForm)
    const validationError = validateForm(cleanForm)
    if (validationError) {
      setError(validationError)
      return
    }

    setCreating(true)
    setError('')
    setStatus('')
    try {
      const out = await api.createResource(threadId, {
        name: cleanForm.title || cleanForm.agent_id,
        summary: cleanForm.base_prompt || null,
        resource_kind: AGENT_RESOURCE_KIND,
        source: 'manual',
        auto_activate: false,
      })
      const node = (out as { node?: GraphNode })?.node
      if (!node?.id) {
        throw new Error('resource 생성 응답에 node.id가 없습니다.')
      }
      const payload = buildAgentPayload(parsePayload(node.payload_json), cleanForm)
      await api.patchNode(node.id, {
        text: buildAgentNodeText(cleanForm),
        payload_json: JSON.stringify(payload),
      })
      setCreateForm(createEmptyForm())
      await reloadProfiles(threadId)
      setStatus(`Agent profile 생성 완료 (${node.id.slice(0, 8)})`)
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
    } finally {
      setCreating(false)
    }
  }

  function openEditModal(profile: AgentProfile) {
    setEditingProfile(profile)
    setEditForm({ ...profile.form })
    setError('')
    setStatus('')
  }

  async function handleSaveEdit() {
    if (!editingProfile) return
    const cleanForm = normalizeForm(editForm)
    const validationError = validateForm(cleanForm)
    if (validationError) {
      setError(validationError)
      return
    }

    setSavingEdit(true)
    setError('')
    try {
      const payload = buildAgentPayload(editingProfile.payload, cleanForm)
      await api.patchNode(editingProfile.nodeId, {
        text: buildAgentNodeText(cleanForm),
        payload_json: JSON.stringify(payload),
      })
      if (agentsThreadId) {
        await reloadProfiles(agentsThreadId)
      }
      setEditingProfile(null)
      setStatus(`Agent profile 수정 완료 (${editingProfile.nodeId.slice(0, 8)})`)
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
    } finally {
      setSavingEdit(false)
    }
  }

  async function handleDeleteProfile(profile: AgentProfile) {
    const ok = window.confirm(`agent "${profile.form.title}"를 삭제할까요?`)
    if (!ok) return
    setDeletingNodeId(profile.nodeId)
    setError('')
    setStatus('')
    try {
      await api.deleteNodeById(profile.nodeId)
      if (agentsThreadId) {
        await reloadProfiles(agentsThreadId)
      }
      setStatus(`Agent profile 삭제 완료 (${profile.nodeId.slice(0, 8)})`)
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
    } finally {
      setDeletingNodeId(null)
    }
  }

  return (
    <div className="routePage">
      <div className="routeCard">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h2 style={{ margin: 0 }}>Agents</h2>
          <div className="row" style={{ marginBottom: 0 }}>
            <button onClick={() => onNavigate('/')}>Back to Workspace</button>
            <button onClick={() => void reloadThreads()} disabled={loadingThreads}>
              {loadingThreads ? 'Loading...' : 'Refresh'}
            </button>
          </div>
        </div>

        <div className="row">
          <label className="muted">
            Agents thread:
            <select
              style={{ marginLeft: 8, minWidth: 280 }}
              value={agentsThreadId || ''}
              onChange={(e) => setAgentsThreadId((e.target.value || '').trim() || null)}
            >
              <option value="">(선택 안됨)</option>
              {threads.map((thread) => (
                <option key={thread.id} value={thread.id}>
                  {(thread.title || '(untitled)').trim() || '(untitled)'} ({thread.id.slice(0, 8)})
                </option>
              ))}
            </select>
          </label>
          <button onClick={handleCreateAgentsThread}>Create "agents" Thread</button>
          {agentsThread && <span className="pill">selected: {agentsThread.title || '(untitled)'}</span>}
          {linkedThreadId && <span className="pill">linked thread param 사용 가능</span>}
        </div>

        {!agentsThreadId && (
          <div className="routeStatus">
            `title=agents`인 thread를 찾지 못했습니다. 위에서 thread를 선택하거나 새로 생성하세요.
          </div>
        )}
        {error && <div className="routeStatus routeStatusError">{error}</div>}
        {status && <div className="routeStatus">{status}</div>}

        <div className="agentsLayout">
          <div className="card agentsFormCard">
            <h3 style={{ marginTop: 0 }}>Create Agent Profile</h3>
            <label className="routeLabel">
              agent_id
              <input
                value={createForm.agent_id}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, agent_id: e.target.value }))}
                placeholder="e.g. planner-main"
              />
            </label>
            <label className="routeLabel">
              title
              <input
                value={createForm.title}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, title: e.target.value }))}
                placeholder="e.g. Planner Agent"
              />
            </label>
            <label className="routeLabel">
              provider
              <input
                value={createForm.provider}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, provider: e.target.value }))}
                placeholder="e.g. openai"
              />
            </label>
            <label className="routeLabel">
              model
              <input
                value={createForm.model}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, model: e.target.value }))}
                placeholder="e.g. gpt-5"
              />
            </label>
            <label className="routeLabel">
              base_prompt
              <textarea
                value={createForm.base_prompt}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, base_prompt: e.target.value }))}
                placeholder="Agent 기본 프롬프트"
                style={{ minHeight: 140 }}
              />
            </label>
            <div className="row">
              <button
                className="primary"
                onClick={() => void handleCreateProfile()}
                disabled={creating || !agentsThreadId}
              >
                {creating ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>

          <div className="card">
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0 }}>Agent Profiles</h3>
              <span className="pill">count: {sortedProfiles.length}</span>
            </div>
            {loadingProfiles && <div className="muted">Loading...</div>}
            <div className="routeTableWrap">
              <table className="routeTable">
                <thead>
                  <tr>
                    <th>agent_id</th>
                    <th>title</th>
                    <th>provider</th>
                    <th>model</th>
                    <th>base_prompt</th>
                    <th>created_at</th>
                    <th>actions</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedProfiles.map((profile) => (
                    <tr key={profile.nodeId}>
                      <td>{profile.form.agent_id}</td>
                      <td>{profile.form.title}</td>
                      <td>{profile.form.provider || '-'}</td>
                      <td>{profile.form.model || '-'}</td>
                      <td style={{ maxWidth: 360 }}>
                        {(profile.form.base_prompt || profile.rawText || '').replace(/\s+/g, ' ').slice(0, 140) || '-'}
                      </td>
                      <td>{profile.createdAt || '-'}</td>
                      <td>
                        <div className="row agentsActionRow">
                          <button onClick={() => openEditModal(profile)}>Edit</button>
                          <button
                            className="danger"
                            onClick={() => void handleDeleteProfile(profile)}
                            disabled={deletingNodeId === profile.nodeId}
                          >
                            {deletingNodeId === profile.nodeId ? 'Deleting...' : 'Delete'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {sortedProfiles.length === 0 && !loadingProfiles && (
                    <tr>
                      <td colSpan={7}>
                        <span className="muted">등록된 `agent_profile` 리소스가 없습니다.</span>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      {editingProfile && (
        <div className="modalOverlay" onClick={() => setEditingProfile(null)}>
          <div className="modalCard agentsEditModal" onClick={(e) => e.stopPropagation()}>
            <div className="row modalHeader">
              <h3 style={{ margin: 0 }}>Edit Agent Profile</h3>
              <button onClick={() => setEditingProfile(null)}>Close</button>
            </div>

            <label className="routeLabel">
              agent_id
              <input
                value={editForm.agent_id}
                onChange={(e) => setEditForm((prev) => ({ ...prev, agent_id: e.target.value }))}
              />
            </label>
            <label className="routeLabel">
              title
              <input
                value={editForm.title}
                onChange={(e) => setEditForm((prev) => ({ ...prev, title: e.target.value }))}
              />
            </label>
            <label className="routeLabel">
              provider
              <input
                value={editForm.provider}
                onChange={(e) => setEditForm((prev) => ({ ...prev, provider: e.target.value }))}
              />
            </label>
            <label className="routeLabel">
              model
              <input
                value={editForm.model}
                onChange={(e) => setEditForm((prev) => ({ ...prev, model: e.target.value }))}
              />
            </label>
            <label className="routeLabel">
              base_prompt
              <textarea
                value={editForm.base_prompt}
                onChange={(e) => setEditForm((prev) => ({ ...prev, base_prompt: e.target.value }))}
                style={{ minHeight: 180 }}
              />
            </label>

            <div className="row">
              <button className="primary" onClick={() => void handleSaveEdit()} disabled={savingEdit}>
                {savingEdit ? 'Saving...' : 'Save'}
              </button>
              <button onClick={() => setEditingProfile(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
