import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'

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

type CatalogMode = 'all_enabled' | 'selected'

type CatalogEntry = {
  nodeId: string
  key: string
  title: string
  summary: string
  meta?: string
}

type Props = {
  threadId: string | null
  threads: ThreadSummary[]
  onAfterSave: () => Promise<void>
}

function asString(v: unknown): string {
  if (typeof v === 'string') return v.trim()
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  return ''
}

function normalizeTitle(title?: string | null): string {
  return (title || '').trim().toLowerCase()
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

function parseObjectText(text?: string | null): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(text || '{}')
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>
    }
  } catch {
    // ignore parse errors
  }
  return null
}

function parseStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  const out = value
    .map((item) => asString(item))
    .filter((item) => !!item)
  return [...new Set(out)]
}

function pickCatalogThreadId(threads: ThreadSummary[], preferredTitles: string[]): string | null {
  for (const title of preferredTitles) {
    const hit = threads.find((thread) => {
      return normalizeTitle(thread.title) === normalizeTitle(title) && asString(thread.service_id) !== 'public'
    })
    if (hit?.id) return hit.id
  }
  return null
}

function toCatalogEntry(node: GraphNode, kind: 'agent'): CatalogEntry | null {
  const payload = parsePayload(node.payload_json)
  const key = asString(payload.agent_id) || asString(payload.name) || node.id.slice(0, 12)
  if (!key) return null
  const title = (
    asString(payload.title)
    || asString(payload.tool_title)
    || asString(payload.name)
    || `${kind}-${node.id.slice(0, 6)}`
  )
  const summary = asString(payload.summary) || asString(node.text).replace(/\s+/g, ' ').slice(0, 150)
  return {
    nodeId: node.id,
    key,
    title,
    summary,
  }
}

function pickLatestNode(nodes: GraphNode[]): GraphNode | null {
  if (nodes.length === 0) return null
  const sorted = [...nodes].sort((a, b) => {
    const ac = asString(a.created_at)
    const bc = asString(b.created_at)
    if (ac === bc) return asString(a.id).localeCompare(asString(b.id))
    return ac.localeCompare(bc)
  })
  return sorted[sorted.length - 1] || null
}

function buildEnabledFromSet(
  mode: CatalogMode,
  selected: string[],
  disabled: string[],
  allKeys: string[],
): string[] {
  const allUnique = [...new Set(allKeys)]
  const disabledSet = new Set(disabled)
  if (mode === 'all_enabled') {
    return allUnique.filter((key) => !disabledSet.has(key))
  }
  const selectedSet = new Set(selected)
  return allUnique.filter((key) => selectedSet.has(key) && !disabledSet.has(key))
}


function toSkillCatalogEntry(raw: unknown): CatalogEntry | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null
  const row = raw as Record<string, unknown>
  const key = asString(row.id) || asString(row.slug) || asString(row.name)
  if (!key) return null
  const category = asString(row.category)
  const roles = parseStringArray(row.compatible_roles).slice(0, 4)
  return {
    nodeId: key,
    key,
    title: asString(row.name) || key,
    summary: asString(row.description) || '-',
    meta: [category, roles.length > 0 ? `roles: ${roles.join(', ')}` : ''].filter(Boolean).join(' · '),
  }
}

export default function JobSettingsPanel({ threadId, threads, onAfterSave }: Props) {
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')

  const [jobConfigNode, setJobConfigNode] = useState<GraphNode | null>(null)
  const [jobConfigData, setJobConfigData] = useState<Record<string, unknown> | null>(null)
  const [jobConfigParseError, setJobConfigParseError] = useState('')
  const [activeCtxId, setActiveCtxId] = useState<string | null>(null)
  const [isEditingActiveJobConfig, setIsEditingActiveJobConfig] = useState(false)

  const [agentsCatalog, setAgentsCatalog] = useState<CatalogEntry[]>([])
  const [skillsCatalog, setSkillsCatalog] = useState<CatalogEntry[]>([])

  const [agentMode, setAgentMode] = useState<CatalogMode>('selected')
  const [skillMode, setSkillMode] = useState<CatalogMode>('selected')
  const [enabledAgents, setEnabledAgents] = useState<string[]>([])
  const [enabledSkills, setEnabledSkills] = useState<string[]>([])

  const [agentsCatalogThreadId, setAgentsCatalogThreadId] = useState<string | null>(null)

  const agentKeys = useMemo(() => [...new Set(agentsCatalog.map((item) => item.key))], [agentsCatalog])
  const skillKeys = useMemo(() => [...new Set(skillsCatalog.map((item) => item.key))], [skillsCatalog])
  const enabledAgentsSet = useMemo(() => new Set(enabledAgents), [enabledAgents])
  const enabledSkillsSet = useMemo(() => new Set(enabledSkills), [enabledSkills])

  const reload = useCallback(async () => {
    setLoading(true)
    setError('')
    setStatus('')
    setJobConfigParseError('')
    try {
      if (!threadId) {
        setJobConfigNode(null)
        setJobConfigData(null)
        setActiveCtxId(null)
        setIsEditingActiveJobConfig(false)
        setAgentsCatalog([])
        setSkillsCatalog([])
        setEnabledAgents([])
        setEnabledSkills([])
        return
      }

      const agentsCatalogTid = pickCatalogThreadId(threads, ['agents', 'agents:profiles'])
      setAgentsCatalogThreadId(agentsCatalogTid)

      const [ctxSetsOut, jobRes, agentRes, skillsRes] = await Promise.all([
        api.ctxSets(threadId),
        api.listResources(threadId, 'job_config'),
        agentsCatalogTid ? api.listResources(agentsCatalogTid, 'agent_profile') : Promise.resolve({ items: [] }),
        threadId ? api.skills(threadId) : Promise.resolve({ items: [] }),
      ])
      const ctxSets = Array.isArray(ctxSetsOut) ? ctxSetsOut : []
      const defaultCtxId = asString((ctxSets[0] as { id?: unknown } | undefined)?.id) || null
      setActiveCtxId(defaultCtxId)
      let activeNodeIdSet = new Set<string>()
      if (defaultCtxId) {
        try {
          const compiled = await api.ctxCompiled(defaultCtxId, true)
          const activeNodeIds = Array.isArray(compiled?.active_node_ids) ? compiled.active_node_ids : []
          activeNodeIdSet = new Set(
            activeNodeIds
              .map((id: unknown) => asString(id))
              .filter((id: string) => !!id),
          )
        } catch {
          activeNodeIdSet = new Set<string>()
        }
      }

      const agentNodes = Array.isArray(agentRes?.items) ? (agentRes.items as GraphNode[]) : []
      const mappedAgents = agentNodes
        .map((node) => toCatalogEntry(node, 'agent'))
        .filter((item): item is CatalogEntry => Boolean(item))
      setAgentsCatalog(mappedAgents)

      const rawSkills = Array.isArray(skillsRes?.items) ? (skillsRes.items as unknown[]) : []
      const mappedSkills = rawSkills
        .map((row) => toSkillCatalogEntry(row))
        .filter((item): item is CatalogEntry => Boolean(item))
      setSkillsCatalog(mappedSkills)

      const jobNodes = Array.isArray(jobRes?.items) ? (jobRes.items as GraphNode[]) : []
      const activeJobNodes = jobNodes.filter((node) => activeNodeIdSet.has(node.id))
      const selectedJobNode = activeJobNodes.length > 0 ? pickLatestNode(activeJobNodes) : pickLatestNode(jobNodes)
      setJobConfigNode(selectedJobNode)
      setIsEditingActiveJobConfig(Boolean(selectedJobNode && activeNodeIdSet.has(selectedJobNode.id)))

      if (!selectedJobNode) {
        setJobConfigData(null)
        setEnabledAgents([])
        setEnabledSkills([])
        return
      }

      const parsed = parseObjectText(selectedJobNode.text)
      if (!parsed) {
        setJobConfigData(null)
        setJobConfigParseError('job_config text가 유효한 JSON object가 아닙니다.')
        return
      }
      setJobConfigData(parsed)

      const rawAgentSet = (
        parsed.agent_set && typeof parsed.agent_set === 'object' && !Array.isArray(parsed.agent_set)
          ? (parsed.agent_set as Record<string, unknown>)
          : null
      )
      const participants = rawAgentSet ? [] : parseStringArray((parsed as Record<string, unknown>).participants)
      const nextAgentMode: CatalogMode = (
        asString(rawAgentSet?.mode) === 'all_enabled' ? 'all_enabled' : 'selected'
      )
      const nextAgentSelected = parseStringArray(rawAgentSet?.selected)
      const nextAgentDisabled = parseStringArray(rawAgentSet?.disabled)
      const effectiveAgentSelected = rawAgentSet ? nextAgentSelected : participants
      const allAgentKeys = [...new Set(mappedAgents.map((item) => item.key))]
      setAgentMode(nextAgentMode)
      setEnabledAgents(buildEnabledFromSet(nextAgentMode, effectiveAgentSelected, nextAgentDisabled, allAgentKeys))

      const rawSkillSet = (
        (parsed.skill_set && typeof parsed.skill_set === 'object' && !Array.isArray(parsed.skill_set)
          ? (parsed.skill_set as Record<string, unknown>)
          : null)
        || (parsed.tool_set && typeof parsed.tool_set === 'object' && !Array.isArray(parsed.tool_set)
          ? (parsed.tool_set as Record<string, unknown>)
          : null)
      )
      const nextSkillMode: CatalogMode = (
        asString(rawSkillSet?.mode) === 'all_enabled' ? 'all_enabled' : 'selected'
      )
      const nextSkillSelected = parseStringArray(rawSkillSet?.selected)
      const nextSkillDisabled = parseStringArray(rawSkillSet?.disabled)
      const allSkillKeys = [...new Set(mappedSkills.map((item) => item.key))]
      setSkillMode(nextSkillMode)
      setEnabledSkills(buildEnabledFromSet(nextSkillMode, nextSkillSelected, nextSkillDisabled, allSkillKeys))
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [threadId, threads])

  useEffect(() => {
    void reload()
  }, [reload])

  function toggleAgent(key: string, checked: boolean) {
    setEnabledAgents((prev) => {
      const set = new Set(prev)
      if (checked) set.add(key)
      else set.delete(key)
      return [...set]
    })
  }

  function toggleSkill(key: string, checked: boolean) {
    setEnabledSkills((prev) => {
      const set = new Set(prev)
      if (checked) set.add(key)
      else set.delete(key)
      return [...set]
    })
  }

  async function handleSave() {
    if (!jobConfigNode?.id || !jobConfigData) {
      setError('저장할 job_config가 없습니다.')
      return
    }
    setSaving(true)
    setError('')
    setStatus('')
    try {
      const next: Record<string, unknown> = { ...jobConfigData }

      const enabledAgentSet = new Set(enabledAgents)
      const agentSelected = agentKeys.filter((key) => enabledAgentSet.has(key))
      const agentDisabled = agentKeys.filter((key) => !enabledAgentSet.has(key))
      next.agent_set = {
        mode: agentMode,
        selected: agentSelected,
        disabled: agentDisabled,
      }

      const enabledSkillSet = new Set(enabledSkills)
      const skillSelected = skillKeys.filter((key) => enabledSkillSet.has(key))
      const skillDisabled = skillKeys.filter((key) => !enabledSkillSet.has(key))
      const normalizedSkillSet = {
        mode: skillMode,
        selected: skillSelected,
        disabled: skillDisabled,
      }
      next.skill_set = normalizedSkillSet
      next.tool_set = normalizedSkillSet

      await api.patchNode(jobConfigNode.id, {
        text: JSON.stringify(next, null, 2),
      })
      setJobConfigData(next)
      setStatus('Job Settings를 저장했습니다.')
      await onAfterSave()
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0 }}>Job Settings</h3>
        <div className="row" style={{ marginBottom: 0 }}>
          <button onClick={() => void reload()} disabled={loading}>
            {loading ? 'Loading...' : 'Refresh'}
          </button>
          <button className="primary" onClick={() => void handleSave()} disabled={saving || !jobConfigNode || !!jobConfigParseError}>
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>

      {!threadId && <div className="routeStatus">먼저 thread(job)를 선택하세요.</div>}
      {threadId && !jobConfigNode && !loading && (
        <div className="routeStatus">이 thread에는 `job_config`가 없습니다.</div>
      )}
      {jobConfigNode && (
        <div className="row" style={{ marginBottom: 8 }}>
          <span className="muted">
            job_config node: {jobConfigNode.id} {jobConfigNode.created_at ? `(${jobConfigNode.created_at})` : ''}
          </span>
          <span className={`pill ${isEditingActiveJobConfig ? 'pillActive' : ''}`}>
            active: {isEditingActiveJobConfig ? 'yes' : 'no'}
          </span>
          {activeCtxId && <span className="pill">ctx: {activeCtxId.slice(0, 8)}</span>}
        </div>
      )}
      {jobConfigParseError && <div className="routeStatus routeStatusError">{jobConfigParseError}</div>}
      {error && <div className="routeStatus routeStatusError">{error}</div>}
      {status && <div className="routeStatus">{status}</div>}

      <div className="card" style={{ marginTop: 10 }}>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <b>Agent Set</b>
          <div className="row" style={{ marginBottom: 0 }}>
            <span className="pill">catalog: {agentsCatalogThreadId ? agentsCatalogThreadId.slice(0, 8) : 'none'}</span>
            <label className="muted">
              mode:
              <select
                value={agentMode}
                onChange={(e) => {
                  const mode = e.target.value as CatalogMode
                  setAgentMode(mode)
                  if (mode === 'all_enabled') {
                    setEnabledAgents([...agentKeys])
                  }
                }}
                style={{ marginLeft: 8 }}
              >
                <option value="all_enabled">all_enabled</option>
                <option value="selected">selected</option>
              </select>
            </label>
          </div>
        </div>
        {agentsCatalog.length === 0 ? (
          <div className="muted">Agents Catalog를 찾지 못했거나 `agent_profile` 리소스가 없습니다.</div>
        ) : (
          <div className="routeTableWrap">
            <table className="routeTable">
              <thead>
                <tr>
                  <th>enabled</th>
                  <th>agent_id</th>
                  <th>title</th>
                  <th>summary</th>
                </tr>
              </thead>
              <tbody>
                {agentsCatalog.map((agent) => (
                  <tr key={`${agent.nodeId}:${agent.key}`}>
                    <td>
                      <input
                        type="checkbox"
                        checked={enabledAgentsSet.has(agent.key)}
                        onChange={(e) => toggleAgent(agent.key, e.target.checked)}
                      />
                    </td>
                    <td>{agent.key}</td>
                    <td>{agent.title || '-'}</td>
                    <td>{agent.summary || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card" style={{ marginTop: 10 }}>
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <b>Skill Set</b>
          <div className="row" style={{ marginBottom: 0 }}>
            <span className="pill">source: thread skill registry</span>
            <label className="muted">
              mode:
              <select
                value={skillMode}
                onChange={(e) => {
                  const mode = e.target.value as CatalogMode
                  setSkillMode(mode)
                  if (mode === 'all_enabled') {
                    setEnabledSkills([...skillKeys])
                  }
                }}
                style={{ marginLeft: 8 }}
              >
                <option value="all_enabled">all_enabled</option>
                <option value="selected">selected</option>
              </select>
            </label>
          </div>
        </div>
        <div className="muted" style={{ marginBottom: 8 }}>skill_set를 우선 저장하고, runtime 호환성을 위해 tool_set에도 같은 값을 미러링합니다.</div>
        {skillsCatalog.length === 0 ? (
          <div className="muted">현재 thread에서 관측된 skill registry가 없습니다.</div>
        ) : (
          <div className="routeTableWrap">
            <table className="routeTable">
              <thead>
                <tr>
                  <th>enabled</th>
                  <th>skill_id</th>
                  <th>title</th>
                  <th>summary</th>
                  <th>meta</th>
                </tr>
              </thead>
              <tbody>
                {skillsCatalog.map((skill) => (
                  <tr key={`${skill.nodeId}:${skill.key}`}>
                    <td>
                      <input
                        type="checkbox"
                        checked={enabledSkillsSet.has(skill.key)}
                        onChange={(e) => toggleSkill(skill.key, e.target.checked)}
                      />
                    </td>
                    <td>{skill.key}</td>
                    <td>{skill.title || '-'}</td>
                    <td>{skill.summary || '-'}</td>
                    <td>{skill.meta || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
