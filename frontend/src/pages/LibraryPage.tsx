import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'

const PUBLIC_LIBRARY_TITLE = 'agents:library'
const PUBLIC_SKILL_LIBRARY_TITLE = 'skills:library'
const BLUEPRINT_RESOURCE_KIND = 'agent_blueprint'
const AGENT_RESOURCE_KIND = 'agent_profile'
const AGENTS_THREAD_TITLES = ['agents:profiles', 'agents'] as const
const PREFERRED_AGENTS_THREAD_TITLE = AGENTS_THREAD_TITLES[0]
const SKILL_CATALOG_THREAD_TITLES = ['skills:catalog', 'skills'] as const
type AgentsThreadTitle = (typeof AGENTS_THREAD_TITLES)[number]
type SkillCatalogThreadTitle = (typeof SKILL_CATALOG_THREAD_TITLES)[number]

type Props = {
  onNavigate: (path: string) => void
}

type ThreadSummary = {
  id: string
  title?: string | null
  service_id?: string | null
}

type GraphNode = {
  id: string
  type?: string | null
  text?: string | null
  payload_json?: string | null
  created_at?: string | null
}

type BlueprintItem = {
  nodeId: string
  createdAt: string
  rawText: string
  payload: Record<string, unknown>
  blueprintId: string
  agentId: string
  title: string
  summary: string
  tags: string[]
}

type SkillCredentialRequirement = {
  key: string
  required?: boolean
  provider?: string
}

type SkillExecutionAdapter = {
  kind?: string
  entrypoint?: string
  endpoint?: string
}

type SkillItem = {
  id: string
  name: string
  version: string
  description: string
  category: string
  capability_tags: string[]
  compatible_roles: string[]
  visibility: string
  status: string
  source: string
  trust_level?: string
  side_effect_level?: string
  required_tools?: string[]
  credential_requirements?: SkillCredentialRequirement[]
  execution_adapter?: SkillExecutionAdapter
}

function normalizeTitle(title?: string | null): string {
  return (title || '').trim().toLowerCase()
}

function asAgentsThreadTitle(title?: string | null): AgentsThreadTitle | null {
  const normalized = normalizeTitle(title)
  for (const candidate of AGENTS_THREAD_TITLES) {
    if (candidate === normalized) return candidate
  }
  return null
}

function asSkillCatalogThreadTitle(title?: string | null): SkillCatalogThreadTitle | null {
  const normalized = normalizeTitle(title)
  for (const candidate of SKILL_CATALOG_THREAD_TITLES) {
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

function parseRawJson(text: string): Record<string, unknown> {
  try {
    const parsed = JSON.parse(text || '')
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
  } catch {
    // ignore
  }
  return {}
}

function toTags(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value
    .map((item) => asString(item))
    .filter((item) => !!item)
}

function nodeToBlueprint(node: GraphNode): BlueprintItem | null {
  if ((node.type || '') !== 'Resource') return null
  const payload = parsePayload(node.payload_json)
  if (asString(payload.resource_kind) !== BLUEPRINT_RESOURCE_KIND) return null

  const rawText = asString(node.text)
  const rawJson = parseRawJson(rawText)
  const agentId = asString(payload.agent_id) || asString(rawJson.agent_id) || asString(payload.origin_agent_id)
  const title = (
    asString(payload.title)
    || asString(rawJson.title)
    || asString(payload.name)
    || agentId
    || `blueprint-${node.id.slice(0, 6)}`
  )
  const summary = (
    asString(payload.summary)
    || asString(rawJson.description)
    || asString(rawJson.base_prompt)
  )
  const tags = toTags(payload.tags).concat(toTags(rawJson.tags))
  const dedupTags = [...new Set(tags)]

  return {
    nodeId: node.id,
    createdAt: asString(node.created_at),
    rawText,
    payload,
    blueprintId: asString(payload.blueprint_id) || `pub_${node.id.slice(0, 8)}`,
    agentId,
    title,
    summary,
    tags: dedupTags,
  }
}

function isPrivateThread(thread: ThreadSummary): boolean {
  return asString(thread.service_id) !== 'public'
}

function downloadJson(filename: string, value: unknown) {
  if (typeof window === 'undefined' || typeof document === 'undefined') return
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json;charset=utf-8' })
  const href = URL.createObjectURL(blob)
  try {
    const link = document.createElement('a')
    link.href = href
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  } finally {
    URL.revokeObjectURL(href)
  }
}

export default function LibraryPage({ onNavigate }: Props) {
  const [threads, setThreads] = useState<ThreadSummary[]>([])
  const [libraryThreadId, setLibraryThreadId] = useState<string | null>(null)
  const [skillLibraryThreadId, setSkillLibraryThreadId] = useState<string | null>(null)
  const [items, setItems] = useState<BlueprintItem[]>([])
  const [skills, setSkills] = useState<SkillItem[]>([])
  const [loading, setLoading] = useState(false)
  const [installingNodeId, setInstallingNodeId] = useState<string | null>(null)
  const [skillBusyId, setSkillBusyId] = useState<string | null>(null)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')

  const libraryThread = useMemo(() => {
    if (!libraryThreadId) return null
    return threads.find((thread) => thread.id === libraryThreadId) || null
  }, [threads, libraryThreadId])

  const skillLibraryThread = useMemo(() => {
    if (!skillLibraryThreadId) return null
    return threads.find((thread) => thread.id === skillLibraryThreadId) || null
  }, [threads, skillLibraryThreadId])

  const sortedItems = useMemo(() => {
    return [...items].sort((a, b) => {
      if (a.createdAt === b.createdAt) return a.nodeId.localeCompare(b.nodeId)
      return a.createdAt < b.createdAt ? 1 : -1
    })
  }, [items])

  const sortedSkills = useMemo(() => {
    return [...skills].sort((a, b) => {
      const left = `${a.name}:${a.id}`.toLowerCase()
      const right = `${b.name}:${b.id}`.toLowerCase()
      return left.localeCompare(right)
    })
  }, [skills])

  const countAgentProfilesInThread = useCallback(async (threadId: string): Promise<number> => {
    try {
      const out = await api.graph(threadId)
      const graphNodes = Array.isArray(out?.nodes) ? (out.nodes as GraphNode[]) : []
      return graphNodes.reduce((count, node) => {
        if ((node.type || '') !== 'Resource') return count
        const payload = parsePayload(node.payload_json)
        return count + (asString(payload.resource_kind) === AGENT_RESOURCE_KIND ? 1 : 0)
      }, 0)
    } catch {
      return 0
    }
  }, [])

  const pickDefaultAgentsThreadId = useCallback(async (list: ThreadSummary[]): Promise<string | null> => {
    const candidates = list
      .filter((thread) => isPrivateThread(thread))
      .map((thread) => {
        const matchedTitle = asAgentsThreadTitle(thread.title)
        if (!matchedTitle) return null
        return { thread, matchedTitle }
      })
      .filter((item): item is { thread: ThreadSummary; matchedTitle: AgentsThreadTitle } => item !== null)

    if (candidates.length === 0) return null

    const scored = await Promise.all(
      candidates.map(async ({ thread, matchedTitle }) => ({
        thread,
        matchedTitle,
        profileCount: await countAgentProfilesInThread(thread.id),
      })),
    )

    scored.sort((a, b) => {
      if (a.profileCount !== b.profileCount) return b.profileCount - a.profileCount
      const aPriority = AGENTS_THREAD_TITLES.indexOf(a.matchedTitle)
      const bPriority = AGENTS_THREAD_TITLES.indexOf(b.matchedTitle)
      if (aPriority !== bPriority) return aPriority - bPriority
      return a.thread.id.localeCompare(b.thread.id)
    })
    return scored[0]?.thread.id || null
  }, [countAgentProfilesInThread])

  const ensurePrivateAgentsThread = useCallback(async (): Promise<string> => {
    const listRaw = await api.threads()
    const list = Array.isArray(listRaw) ? (listRaw as ThreadSummary[]) : []
    const picked = await pickDefaultAgentsThreadId(list)
    if (picked) return picked
    const created = await api.createThread(PREFERRED_AGENTS_THREAD_TITLE)
    const nextId = asString((created as { id?: string }).id)
    if (!nextId) {
      throw new Error('agents thread 생성에 실패했습니다.')
    }
    return nextId
  }, [pickDefaultAgentsThreadId])

  const ensurePrivateSkillCatalogThread = useCallback(async (): Promise<string> => {
    const listRaw = await api.threads()
    const list = Array.isArray(listRaw) ? (listRaw as ThreadSummary[]) : []
    const existing = list.find((thread) => isPrivateThread(thread) && asSkillCatalogThreadTitle(thread.title))
    if (existing?.id) return existing.id
    const created = await api.createThread(SKILL_CATALOG_THREAD_TITLES[0], {
      meta_json: { catalog_kind: 'skill_package' },
    })
    const nextId = asString((created as { id?: string }).id)
    if (!nextId) throw new Error('skills catalog thread 생성에 실패했습니다.')
    return nextId
  }, [])

  const ensureDefaultContextSet = useCallback(async (threadId: string): Promise<string | null> => {
    const sets = await api.ctxSets(threadId)
    const list = Array.isArray(sets) ? sets : []
    if (list[0]?.id) return asString(list[0].id)
    const created = await api.createCtx(threadId, 'default')
    return asString((created as { id?: string }).id) || null
  }, [])

  const reload = useCallback(async () => {
    setLoading(true)
    setError('')
    setStatus('')
    try {
      const out = await api.threads()
      const list = Array.isArray(out) ? (out as ThreadSummary[]) : []
      setThreads(list)
      const publicLibrary = list.find((thread) => {
        return asString(thread.service_id) === 'public' && normalizeTitle(thread.title) === PUBLIC_LIBRARY_TITLE
      }) || null
      const publicSkillLibrary = list.find((thread) => {
        return asString(thread.service_id) === 'public' && normalizeTitle(thread.title) === PUBLIC_SKILL_LIBRARY_TITLE
      }) || null

      if (!publicLibrary) {
        setLibraryThreadId(null)
        setItems([])
      } else {
        setLibraryThreadId(publicLibrary.id)
        const res = await api.listResources(publicLibrary.id, BLUEPRINT_RESOURCE_KIND)
        const rows = Array.isArray(res?.items) ? (res.items as GraphNode[]) : []
        const mapped = rows
          .map((node) => nodeToBlueprint(node))
          .filter((item): item is BlueprintItem => Boolean(item))
        setItems(mapped)
      }

      if (!publicSkillLibrary) {
        setSkillLibraryThreadId(null)
        setSkills([])
        if (!publicLibrary) setStatus('아직 Public Agent/Skill Library가 생성되지 않았습니다. (admin 승인 또는 publish 시 자동 생성)')
      } else {
        setSkillLibraryThreadId(publicSkillLibrary.id)
        const skillsRes = await api.skills(publicSkillLibrary.id, { include_defaults: false })
        const skillItems = Array.isArray(skillsRes?.items) ? (skillsRes.items as SkillItem[]) : []
        setSkills(skillItems)
      }

      if (publicLibrary && !publicSkillLibrary) {
        setStatus('Public Agent Library는 준비되어 있고, Skill Library는 아직 비어 있습니다.')
      }
      if (!publicLibrary && publicSkillLibrary) {
        setStatus('Public Skill Library는 준비되어 있고, Agent Library는 아직 비어 있습니다.')
      }
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
      setItems([])
      setSkills([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  async function handleInstall(item: BlueprintItem) {
    setInstallingNodeId(item.nodeId)
    setError('')
    setStatus('')
    try {
      if (!item.rawText) {
        throw new Error('설치할 blueprint 원문(raw_text)이 비어 있습니다.')
      }
      const targetThreadId = await ensurePrivateAgentsThread()
      const targetContextSetId = await ensureDefaultContextSet(targetThreadId)
      const installPayload: Record<string, unknown> = {
        ...item.payload,
        origin: {
          type: 'public',
          blueprint_id: item.blueprintId,
          public_node_id: item.nodeId,
          installed_at: new Date().toISOString(),
        },
      }
      const out = await api.createResource(targetThreadId, {
        name: item.title || item.agentId || item.blueprintId,
        summary: item.summary || null,
        resource_kind: AGENT_RESOURCE_KIND,
        source: 'manual',
        context_set_id: targetContextSetId,
        auto_activate: true,
        text_mode: 'plain',
        raw_text: item.rawText,
        payload_json: installPayload,
      })
      const nodeId = asString((out as { node?: { id?: string } })?.node?.id)
      setStatus(`설치 완료: ${item.title} -> agent_profile (${nodeId.slice(0, 8) || 'ok'})`)
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
    } finally {
      setInstallingNodeId(null)
    }
  }

  async function handleInstallSkill(item: SkillItem) {
    setSkillBusyId(item.id)
    setError('')
    setStatus('')
    try {
      const targetThreadId = await ensurePrivateSkillCatalogThread()
      const targetContextSetId = await ensureDefaultContextSet(targetThreadId)
      await api.installSkill({
        thread_id: targetThreadId,
        skill_id: item.id,
        source_thread_id: skillLibraryThreadId,
        context_set_id: targetContextSetId,
        auto_activate: true,
      })
      setStatus(`설치 완료: ${item.name || item.id} -> private skill catalog`)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSkillBusyId(null)
    }
  }

  async function handleDownloadSkill(item: SkillItem) {
    setSkillBusyId(item.id)
    setError('')
    setStatus('')
    try {
      const out = await api.exportSkill(item.id, skillLibraryThreadId, { include_defaults: false })
      const filename = `${(item.id || 'skill_package').replace(/[^a-z0-9-_\.]+/gi, '_')}.json`
      downloadJson(filename, out?.package || out)
      setStatus(`다운로드 완료: ${item.name || item.id}`)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSkillBusyId(null)
    }
  }

  return (
    <div className="routePage">
      <div className="routeCard">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h2 style={{ margin: 0 }}>Public Library</h2>
          <div className="row" style={{ marginBottom: 0 }}>
            <button onClick={() => onNavigate('/agents')}>Go Agents Catalog</button>
            <button onClick={() => void reload()} disabled={loading}>
              {loading ? 'Loading...' : 'Refresh'}
            </button>
          </div>
        </div>

        <div className="row">
          {libraryThread && <span className="pill">agent library: {(libraryThread.title || '(untitled)').trim() || '(untitled)'}</span>}
          {skillLibraryThread && <span className="pill">skill library: {(skillLibraryThread.title || '(untitled)').trim() || '(untitled)'}</span>}
          {libraryThread && <span className="pill">agent library id: {libraryThread.id}</span>}
          {skillLibraryThread && <span className="pill">skill library id: {skillLibraryThread.id}</span>}
        </div>

        {error && <div className="routeStatus routeStatusError">{error}</div>}
        {status && <div className="routeStatus">{status}</div>}

        <div style={{ marginTop: 16, marginBottom: 8 }}><b>Agent Blueprints</b></div>
        <div className="routeTableWrap">
          <table className="routeTable">
            <thead>
              <tr>
                <th>blueprint_id</th>
                <th>agent_id</th>
                <th>title</th>
                <th>summary</th>
                <th>tags</th>
                <th>created_at</th>
                <th>actions</th>
              </tr>
            </thead>
            <tbody>
              {sortedItems.map((item) => (
                <tr key={item.nodeId}>
                  <td>{item.blueprintId}</td>
                  <td>{item.agentId || '-'}</td>
                  <td>{item.title || '-'}</td>
                  <td style={{ maxWidth: 320 }}>
                    {(item.summary || item.rawText || '').replace(/\s+/g, ' ').slice(0, 150) || '-'}
                  </td>
                  <td>{item.tags.length ? item.tags.join(', ') : '-'}</td>
                  <td>{item.createdAt || '-'}</td>
                  <td>
                    <button
                      className="primary"
                      onClick={() => void handleInstall(item)}
                      disabled={installingNodeId === item.nodeId}
                    >
                      {installingNodeId === item.nodeId ? 'Installing...' : 'Install'}
                    </button>
                  </td>
                </tr>
              ))}
              {sortedItems.length === 0 && !loading && (
                <tr>
                  <td colSpan={11}>
                    <span className="muted">등록된 `agent_blueprint`가 없습니다.</span>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div style={{ marginTop: 24, marginBottom: 8 }}><b>Skill Packages</b></div>
        <div className="routeTableWrap">
          <table className="routeTable">
            <thead>
              <tr>
                <th>skill_id</th>
                <th>name</th>
                <th>version</th>
                <th>category</th>
                <th>adapter</th>
                <th>credentials</th>
                <th>roles</th>
                <th>tags</th>
                <th>trust / side effects</th>
                <th>visibility</th>
                <th>actions</th>
              </tr>
            </thead>
            <tbody>
              {sortedSkills.map((item) => (
                <tr key={item.id}>
                  <td>{item.id}</td>
                  <td>{item.name || '-'}</td>
                  <td>{item.version || '-'}</td>
                  <td>{item.category || '-'}</td>
                  <td>{item.execution_adapter?.kind || '-'}</td>
                  <td>{(item.credential_requirements || []).map((entry) => entry.key).join(', ') || '-'}</td>
                  <td>{(item.compatible_roles || []).join(', ') || '-'}</td>
                  <td>{(item.capability_tags || []).join(', ') || '-'}</td>
                  <td>{[item.trust_level, item.side_effect_level].filter(Boolean).join(' / ') || '-'}</td>
                  <td>{item.visibility || item.status || '-'}</td>
                  <td>
                    <div className="row" style={{ gap: 8 }}>
                      <button onClick={() => void handleDownloadSkill(item)} disabled={skillBusyId === item.id}>
                        {skillBusyId === item.id ? 'Working...' : 'Download'}
                      </button>
                      <button className="primary" onClick={() => void handleInstallSkill(item)} disabled={skillBusyId === item.id}>
                        {skillBusyId === item.id ? 'Working...' : 'Install'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {sortedSkills.length === 0 && !loading && (
                <tr>
                  <td colSpan={8}>
                    <span className="muted">등록된 public skill package가 없습니다.</span>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
