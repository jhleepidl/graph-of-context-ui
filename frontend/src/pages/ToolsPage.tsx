import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'

const TOOLS_THREAD_TITLES = ['tools', 'tools:specs'] as const
const PREFERRED_TOOLS_THREAD_TITLE = 'tools'
const TOOL_RESOURCE_KIND = 'tool_spec'
type ToolsThreadTitle = (typeof TOOLS_THREAD_TITLES)[number]

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

type ToolSpecForm = {
  name: string
  summary: string
  raw_json: string
}

type ToolSpecRecord = {
  nodeId: string
  createdAt: string
  rawText: string
  payload: Record<string, unknown>
  toolId: string
  toolTitle: string
  form: ToolSpecForm
}

function createEmptyForm(): ToolSpecForm {
  return {
    name: '',
    summary: '',
    raw_json: '{\n  "tool_id": "",\n  "title": "",\n  "description": ""\n}',
  }
}

function normalizeTitle(title?: string | null): string {
  return (title || '').trim().toLowerCase()
}

function asToolsThreadTitle(title?: string | null): ToolsThreadTitle | null {
  const normalized = normalizeTitle(title)
  for (const candidate of TOOLS_THREAD_TITLES) {
    if (candidate === normalized) return candidate
  }
  return null
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

function normalizeForm(input: ToolSpecForm): ToolSpecForm {
  return {
    name: input.name.trim(),
    summary: input.summary.trim(),
    raw_json: input.raw_json.trim(),
  }
}

function parseJsonText(raw: string): unknown | null {
  const clean = (raw || '').trim()
  if (!clean) return null
  try {
    return JSON.parse(clean)
  } catch {
    return null
  }
}

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2)
}

function extractToolMeta(spec: unknown): { toolId: string; title: string; description: string } {
  if (!spec || typeof spec !== 'object' || Array.isArray(spec)) {
    return { toolId: '', title: '', description: '' }
  }
  const obj = spec as Record<string, unknown>
  return {
    toolId: asString(obj.tool_id) || asString(obj.id) || asString(obj.name),
    title: asString(obj.title) || asString(obj.display_name) || asString(obj.name),
    description: asString(obj.description),
  }
}

function validateForm(input: ToolSpecForm): string {
  if (!input.name.trim()) return 'name을 입력하세요.'
  const parsed = parseJsonText(input.raw_json)
  if (parsed === null) return 'raw_json은 유효한 JSON이어야 합니다.'
  if (typeof parsed !== 'object') return 'raw_json은 object/array JSON을 권장합니다.'
  return ''
}

function buildToolPayload(
  existing: Record<string, unknown>,
  form: ToolSpecForm,
  toolSpec: unknown,
): Record<string, unknown> {
  const meta = extractToolMeta(toolSpec)
  const next: Record<string, unknown> = {
    ...existing,
    name: form.name,
    resource_kind: TOOL_RESOURCE_KIND,
    source: asString(existing.source) || 'manual',
    tag: asString(existing.tag) || 'RESOURCE',
    summary: form.summary || meta.description || null,
    tool_id: meta.toolId || form.name,
    tool_title: meta.title || form.name,
    tool_spec: toolSpec,
  }
  return next
}

function nodeToToolSpec(node: GraphNode): ToolSpecRecord | null {
  if ((node.type || '') !== 'Resource') return null
  const payload = parsePayload(node.payload_json)
  if (asString(payload.resource_kind) !== TOOL_RESOURCE_KIND) return null

  const rawText = asString(node.text)
  const parsed = parseJsonText(rawText) ?? payload.tool_spec ?? {}
  const meta = extractToolMeta(parsed)
  const name = asString(payload.name) || meta.title || meta.toolId || `tool-${node.id.slice(0, 6)}`
  const summary = asString(payload.summary) || meta.description
  const rawJson = (() => {
    if (rawText) return rawText
    try {
      return formatJson(parsed)
    } catch {
      return '{}'
    }
  })()

  return {
    nodeId: node.id,
    createdAt: asString(node.created_at),
    rawText,
    payload,
    toolId: asString(payload.tool_id) || meta.toolId || name,
    toolTitle: asString(payload.tool_title) || meta.title || name,
    form: {
      name,
      summary,
      raw_json: rawJson,
    },
  }
}

export default function ToolsPage({ onNavigate }: Props) {
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [toolsThreadId, setToolsThreadId] = useState<string | null>(null)
  const [tools, setTools] = useState<ToolSpecRecord[]>([])
  const [createForm, setCreateForm] = useState<ToolSpecForm>(() => createEmptyForm())
  const [editForm, setEditForm] = useState<ToolSpecForm>(() => createEmptyForm())
  const [editingTool, setEditingTool] = useState<ToolSpecRecord | null>(null)
  const [loadingThreads, setLoadingThreads] = useState(false)
  const [loadingTools, setLoadingTools] = useState(false)
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

  const toolsThread = useMemo(
    () => threads.find((thread) => thread.id === toolsThreadId) || null,
    [threads, toolsThreadId],
  )

  const sortedTools = useMemo(() => {
    return [...tools].sort((a, b) => {
      if (a.createdAt === b.createdAt) return a.nodeId < b.nodeId ? -1 : 1
      return a.createdAt < b.createdAt ? 1 : -1
    })
  }, [tools])

  const countToolSpecsInThread = useCallback(async (threadId: string): Promise<number> => {
    try {
      const out = await api.graph(threadId)
      const graphNodes = Array.isArray(out?.nodes) ? (out.nodes as GraphNode[]) : []
      return graphNodes.reduce((count, node) => count + (nodeToToolSpec(node) ? 1 : 0), 0)
    } catch {
      return 0
    }
  }, [])

  const pickDefaultToolsThreadId = useCallback(async (list: ThreadSummary[]): Promise<string | null> => {
    const candidates = list
      .map((thread) => {
        const matchedTitle = asToolsThreadTitle(thread.title)
        if (!matchedTitle) return null
        return { thread, matchedTitle }
      })
      .filter((item): item is { thread: ThreadSummary; matchedTitle: ToolsThreadTitle } => item !== null)

    if (candidates.length === 0) return null

    const scored = await Promise.all(
      candidates.map(async ({ thread, matchedTitle }) => ({
        thread,
        matchedTitle,
        specCount: await countToolSpecsInThread(thread.id),
      })),
    )

    scored.sort((a, b) => {
      if (a.specCount !== b.specCount) return b.specCount - a.specCount
      const aPriority = TOOLS_THREAD_TITLES.indexOf(a.matchedTitle)
      const bPriority = TOOLS_THREAD_TITLES.indexOf(b.matchedTitle)
      if (aPriority !== bPriority) return aPriority - bPriority
      return a.thread.id.localeCompare(b.thread.id)
    })

    return scored[0]?.thread.id || null
  }, [countToolSpecsInThread])

  const reloadTools = useCallback(async (threadId: string) => {
    setLoadingTools(true)
    setError('')
    try {
      const out = await api.graph(threadId)
      const graphNodes = Array.isArray(out?.nodes) ? (out.nodes as GraphNode[]) : []
      const mapped = graphNodes
        .map((node) => nodeToToolSpec(node))
        .filter((item): item is ToolSpecRecord => Boolean(item))
      setTools(mapped)
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
      setTools([])
    } finally {
      setLoadingTools(false)
    }
  }, [])

  const reloadThreads = useCallback(async (preferredThreadId?: string | null) => {
    setLoadingThreads(true)
    setError('')
    try {
      const out = await api.threads()
      const list = Array.isArray(out) ? (out as ThreadSummary[]) : []
      setThreads(list)
      let nextThreadId: string | null = null
      if (preferredThreadId && list.some((thread) => thread.id === preferredThreadId)) {
        nextThreadId = preferredThreadId
      } else if (toolsThreadId && list.some((thread) => thread.id === toolsThreadId)) {
        nextThreadId = toolsThreadId
      } else if (linkedThreadId && list.some((thread) => thread.id === linkedThreadId)) {
        nextThreadId = linkedThreadId
      } else {
        nextThreadId = await pickDefaultToolsThreadId(list)
      }
      setToolsThreadId(nextThreadId)
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
      setThreads([])
      setToolsThreadId(null)
    } finally {
      setLoadingThreads(false)
    }
  }, [linkedThreadId, pickDefaultToolsThreadId, toolsThreadId])

  useEffect(() => {
    void reloadThreads()
  }, [reloadThreads])

  useEffect(() => {
    if (!toolsThreadId) {
      setTools([])
      return
    }
    void reloadTools(toolsThreadId)
  }, [toolsThreadId, reloadTools])

  async function handleCreateToolsThread() {
    setStatus('')
    setError('')
    try {
      const created = await api.createThread(PREFERRED_TOOLS_THREAD_TITLE)
      const nextId = asString((created as { id?: string }).id)
      await reloadThreads(nextId || null)
      setStatus(`${PREFERRED_TOOLS_THREAD_TITLE} thread를 생성했습니다.`)
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
    }
  }

  async function handleCreateToolSpec() {
    const threadId = toolsThreadId
    if (!threadId) {
      setError('tools thread를 먼저 선택하세요.')
      return
    }

    const cleanForm = normalizeForm(createForm)
    const validationError = validateForm(cleanForm)
    if (validationError) {
      setError(validationError)
      return
    }

    const parsedSpec = parseJsonText(cleanForm.raw_json)
    if (parsedSpec === null) {
      setError('raw_json 파싱에 실패했습니다.')
      return
    }

    setCreating(true)
    setError('')
    setStatus('')
    try {
      const canonicalRaw = formatJson(parsedSpec)
      const createPayload = buildToolPayload({}, cleanForm, parsedSpec)
      const out = await api.createResource(threadId, {
        name: cleanForm.name,
        summary: cleanForm.summary || null,
        resource_kind: TOOL_RESOURCE_KIND,
        source: 'manual',
        auto_activate: true,
        text_mode: 'plain',
        raw_text: canonicalRaw,
        payload_json: createPayload,
      })
      const node = (out as { node?: GraphNode })?.node
      if (!node?.id) {
        throw new Error('resource 생성 응답에 node.id가 없습니다.')
      }
      setCreateForm(createEmptyForm())
      await reloadTools(threadId)
      setStatus(`Tool spec 생성 완료 (${node.id.slice(0, 8)})`)
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
    } finally {
      setCreating(false)
    }
  }

  function openEditModal(spec: ToolSpecRecord) {
    setEditingTool(spec)
    setEditForm({ ...spec.form })
    setError('')
    setStatus('')
  }

  async function handleSaveEdit() {
    if (!editingTool) return
    const cleanForm = normalizeForm(editForm)
    const validationError = validateForm(cleanForm)
    if (validationError) {
      setError(validationError)
      return
    }

    const parsedSpec = parseJsonText(cleanForm.raw_json)
    if (parsedSpec === null) {
      setError('raw_json 파싱에 실패했습니다.')
      return
    }

    setSavingEdit(true)
    setError('')
    try {
      const payload = buildToolPayload(editingTool.payload, cleanForm, parsedSpec)
      await api.patchNode(editingTool.nodeId, {
        text: formatJson(parsedSpec),
        payload_json: JSON.stringify(payload),
      })
      if (toolsThreadId) {
        await reloadTools(toolsThreadId)
      }
      setEditingTool(null)
      setStatus(`Tool spec 수정 완료 (${editingTool.nodeId.slice(0, 8)})`)
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
    } finally {
      setSavingEdit(false)
    }
  }

  async function handleDeleteToolSpec(spec: ToolSpecRecord) {
    const ok = window.confirm(`tool "${spec.form.name}"를 삭제할까요?`)
    if (!ok) return
    setDeletingNodeId(spec.nodeId)
    setError('')
    setStatus('')
    try {
      await api.deleteNodeById(spec.nodeId)
      if (toolsThreadId) {
        await reloadTools(toolsThreadId)
      }
      setStatus(`Tool spec 삭제 완료 (${spec.nodeId.slice(0, 8)})`)
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
          <h2 style={{ margin: 0 }}>Tools</h2>
          <div className="row" style={{ marginBottom: 0 }}>
            <button onClick={() => onNavigate('/')}>Back to Workspace</button>
            <button onClick={() => void reloadThreads()} disabled={loadingThreads}>
              {loadingThreads ? 'Loading...' : 'Refresh'}
            </button>
          </div>
        </div>

        <div className="row">
          <label className="muted">
            Tools thread:
            <select
              style={{ marginLeft: 8, minWidth: 280 }}
              value={toolsThreadId || ''}
              onChange={(e) => setToolsThreadId((e.target.value || '').trim() || null)}
            >
              <option value="">(선택 안됨)</option>
              {threads.map((thread) => (
                <option key={thread.id} value={thread.id}>
                  {(thread.title || '(untitled)').trim() || '(untitled)'} ({thread.id.slice(0, 8)})
                </option>
              ))}
            </select>
          </label>
          <button onClick={handleCreateToolsThread}>Create "{PREFERRED_TOOLS_THREAD_TITLE}" Thread</button>
          {toolsThread && (
            <span className="pill">
              selected: {(toolsThread.title || '(untitled)').trim() || '(untitled)'} ({toolsThread.id})
            </span>
          )}
          {linkedThreadId && <span className="pill">linked thread param 사용 가능</span>}
        </div>

        {!toolsThreadId && (
          <div className="routeStatus">
            `title=tools:specs` 또는 `title=tools`인 thread를 찾지 못했습니다. 위에서 thread를 선택하거나 새로 생성하세요.
          </div>
        )}
        {error && <div className="routeStatus routeStatusError">{error}</div>}
        {status && <div className="routeStatus">{status}</div>}

        <div className="agentsLayout">
          <div className="card agentsFormCard">
            <h3 style={{ marginTop: 0 }}>Create Tool Spec</h3>
            <label className="routeLabel">
              name
              <input
                value={createForm.name}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, name: e.target.value }))}
                placeholder="e.g. web_search_tool"
              />
            </label>
            <label className="routeLabel">
              summary
              <input
                value={createForm.summary}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, summary: e.target.value }))}
                placeholder="도구 설명"
              />
            </label>
            <label className="routeLabel">
              raw_json
              <textarea
                value={createForm.raw_json}
                onChange={(e) => setCreateForm((prev) => ({ ...prev, raw_json: e.target.value }))}
                placeholder="tool_spec JSON"
                style={{ minHeight: 240 }}
              />
            </label>
            <div className="row">
              <button
                className="primary"
                onClick={() => void handleCreateToolSpec()}
                disabled={creating || !toolsThreadId}
              >
                {creating ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>

          <div className="card">
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <h3 style={{ margin: 0 }}>Tool Specs</h3>
              <span className="pill">count: {sortedTools.length}</span>
            </div>
            {loadingTools && <div className="muted">Loading...</div>}
            <div className="routeTableWrap">
              <table className="routeTable">
                <thead>
                  <tr>
                    <th>tool_id</th>
                    <th>title</th>
                    <th>name</th>
                    <th>summary</th>
                    <th>created_at</th>
                    <th>actions</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedTools.map((spec) => (
                    <tr key={spec.nodeId}>
                      <td>{spec.toolId || '-'}</td>
                      <td>{spec.toolTitle || '-'}</td>
                      <td>{spec.form.name || '-'}</td>
                      <td style={{ maxWidth: 360 }}>
                        {(spec.form.summary || spec.rawText || '').replace(/\s+/g, ' ').slice(0, 140) || '-'}
                      </td>
                      <td>{spec.createdAt || '-'}</td>
                      <td>
                        <div className="row agentsActionRow">
                          <button onClick={() => openEditModal(spec)}>Edit</button>
                          <button
                            className="danger"
                            onClick={() => void handleDeleteToolSpec(spec)}
                            disabled={deletingNodeId === spec.nodeId}
                          >
                            {deletingNodeId === spec.nodeId ? 'Deleting...' : 'Delete'}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {sortedTools.length === 0 && !loadingTools && (
                    <tr>
                      <td colSpan={6}>
                        <span className="muted">등록된 `tool_spec` 리소스가 없습니다.</span>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      {editingTool && (
        <div className="modalOverlay" onClick={() => setEditingTool(null)}>
          <div className="modalCard agentsEditModal" onClick={(e) => e.stopPropagation()}>
            <div className="row modalHeader">
              <h3 style={{ margin: 0 }}>Edit Tool Spec</h3>
              <button onClick={() => setEditingTool(null)}>Close</button>
            </div>

            <label className="routeLabel">
              name
              <input
                value={editForm.name}
                onChange={(e) => setEditForm((prev) => ({ ...prev, name: e.target.value }))}
              />
            </label>
            <label className="routeLabel">
              summary
              <input
                value={editForm.summary}
                onChange={(e) => setEditForm((prev) => ({ ...prev, summary: e.target.value }))}
              />
            </label>
            <label className="routeLabel">
              raw_json
              <textarea
                value={editForm.raw_json}
                onChange={(e) => setEditForm((prev) => ({ ...prev, raw_json: e.target.value }))}
                style={{ minHeight: 260 }}
              />
            </label>

            <div className="row">
              <button className="primary" onClick={() => void handleSaveEdit()} disabled={savingEdit}>
                {savingEdit ? 'Saving...' : 'Save'}
              </button>
              <button onClick={() => setEditingTool(null)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
