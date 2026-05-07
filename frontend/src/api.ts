const API_BASE = (import.meta.env.VITE_API_BASE || '').trim().replace(/\/+$/, '')

export const UI_TOKEN_STORAGE_KEY = 'goc:ui_token:v1'
export const ADMIN_KEY_STORAGE_KEY = 'goc:admin_key:v1'
const LEGACY_UI_TOKEN_STORAGE_KEYS = ['goc:bearer-token']

function apiUrl(path: string): string {
  return API_BASE ? `${API_BASE}${path}` : path
}

function readSessionStorage(key: string): string {
  try {
    return (window.sessionStorage.getItem(key) || '').trim()
  } catch {
    return ''
  }
}

function writeSessionStorage(key: string, value: string): void {
  try {
    if (value) {
      window.sessionStorage.setItem(key, value)
    } else {
      window.sessionStorage.removeItem(key)
    }
  } catch {
    // ignore storage failures
  }
}

export function getStoredAdminKey(): string {
  if (typeof window === 'undefined') return ''
  return readSessionStorage(ADMIN_KEY_STORAGE_KEY)
}

export function setStoredAdminKey(key: string): void {
  if (typeof window === 'undefined') return
  writeSessionStorage(ADMIN_KEY_STORAGE_KEY, (key || '').trim())
}

export function clearStoredAdminKey(): void {
  if (typeof window === 'undefined') return
  writeSessionStorage(ADMIN_KEY_STORAGE_KEY, '')
}

export function getStoredBearerToken(): string {
  if (typeof window === 'undefined') return ''
  const current = readSessionStorage(UI_TOKEN_STORAGE_KEY)
  if (current) return current

  for (const legacyKey of LEGACY_UI_TOKEN_STORAGE_KEYS) {
    const legacySession = readSessionStorage(legacyKey)
    if (legacySession) {
      writeSessionStorage(UI_TOKEN_STORAGE_KEY, legacySession)
      try {
        window.sessionStorage.removeItem(legacyKey)
      } catch {
        // ignore
      }
      try {
        window.localStorage.removeItem(legacyKey)
      } catch {
        // ignore
      }
      return legacySession
    }

    try {
      const legacyLocal = (window.localStorage.getItem(legacyKey) || '').trim()
      if (!legacyLocal) continue
      writeSessionStorage(UI_TOKEN_STORAGE_KEY, legacyLocal)
      window.localStorage.removeItem(legacyKey)
      return legacyLocal
    } catch {
      // ignore
    }
  }

  return captureBearerTokenFromLocation()
}

export function setStoredBearerToken(token: string): void {
  if (typeof window === 'undefined') return
  const clean = (token || '').trim()
  writeSessionStorage(UI_TOKEN_STORAGE_KEY, clean)
  for (const legacyKey of LEGACY_UI_TOKEN_STORAGE_KEYS) {
    try {
      window.sessionStorage.removeItem(legacyKey)
    } catch {
      // ignore
    }
    try {
      window.localStorage.removeItem(legacyKey)
    } catch {
      // ignore
    }
  }
}


function captureBearerTokenFromLocation(): string {
  if (typeof window === 'undefined') return ''
  const read = (raw: string): string => {
    const clean = raw.startsWith('#') ? raw.slice(1) : raw
    if (!clean) return ''
    const params = new URLSearchParams(clean)
    return (params.get('token') || params.get('ui_token') || '').trim()
  }

  const token = read(window.location.hash || '') || read(window.location.search || '')
  if (!token) return ''
  writeSessionStorage(UI_TOKEN_STORAGE_KEY, token)
  return token
}

function buildHeaders(existing?: HeadersInit): Headers {
  const headers = new Headers(existing || undefined)
  if (headers.has('X-Admin-Key') || headers.has('Authorization')) {
    return headers
  }

  const adminKey = getStoredAdminKey()
  if (adminKey) {
    headers.set('X-Admin-Key', adminKey)
    return headers
  }

  const token = getStoredBearerToken() || captureBearerTokenFromLocation()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  return headers
}

function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const headers = buildHeaders(init?.headers)
  return fetch(apiUrl(path), {
    ...init,
    headers,
  })
}

async function j<T>(resOrPromise: Response | Promise<Response>): Promise<T> {
  let res: Response
  try {
    res = await resOrPromise
  } catch (e: any) {
    throw new Error(`Network request failed: ${e?.message || String(e)}`)
  }
  if (!res.ok) {
    const msg = await res.text().catch(() => '')
    throw new Error(msg || `${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

async function readApiErrorResponse(res: Response): Promise<string> {
  const raw = await res.text().catch(() => '')
  if (!raw) return `${res.status} ${res.statusText}`
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object') {
      const detail = (parsed as Record<string, unknown>).detail
      if (typeof detail === 'string' && detail.trim()) return detail.trim()
    }
  } catch {
    // not JSON; keep raw string
  }
  return raw
}

function parseDownloadFilename(contentDisposition: string | null, fallback: string): string {
  const raw = (contentDisposition || '').trim()
  if (!raw) return fallback

  const utf8Match = raw.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1].trim())
    } catch {
      return utf8Match[1].trim()
    }
  }

  const quotedMatch = raw.match(/filename=\"([^\"]+)\"/i)
  if (quotedMatch?.[1]) return quotedMatch[1].trim()

  const plainMatch = raw.match(/filename=([^;]+)/i)
  if (plainMatch?.[1]) return plainMatch[1].trim()

  return fallback
}



export function listThreadTeamBlueprintTemplates(threadId: string) {
  return j<any>(apiFetch(`/api/threads/${threadId}/team/blueprint/templates`))
}

export function exportThreadTeamManifest(threadId: string) {
  return j<any>(apiFetch(`/api/threads/${threadId}/team/blueprint`))
}

export function validateThreadTeamManifest(
  threadId: string,
  body: { manifest: Record<string, any>; apply_state?: "active" | "pending" },
) {
  return j<any>(apiFetch(`/api/threads/${threadId}/team/blueprint/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }))
}

export function diffThreadTeamManifest(
  threadId: string,
  body: { manifest: Record<string, any>; apply_state?: "active" | "pending" },
) {
  return j<any>(apiFetch(`/api/threads/${threadId}/team/blueprint/diff`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }))
}

export function installThreadTeamManifest(
  threadId: string,
  body: { manifest: Record<string, any>; apply_state?: "active" | "pending" },
) {
  return j<any>(apiFetch(`/api/threads/${threadId}/team/blueprint/install`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }))
}

export function previewThreadTeamPublishCandidate(
  threadId: string,
  body: { visibility?: string } = {},
) {
  return j<any>(apiFetch(`/api/threads/${threadId}/team/blueprint/publish_candidate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }))
}


export function getMemoryReviewOverview(threadId: string) {
  return j<any>(apiFetch(`/api/threads/${threadId}/memory/review/overview`))
}

export function previewMemoryMaterialization(
  threadId: string,
  body: { min_score?: number; max_candidates?: number; include_backfill_preview?: boolean } = {},
) {
  return j<any>(apiFetch(`/api/threads/${threadId}/memory/materialization/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }))
}

export function saveMemoryMaterializationCandidates(
  threadId: string,
  body: { min_score?: number; max_candidates?: number } = {},
) {
  return j<any>(apiFetch(`/api/threads/${threadId}/memory/materialization/candidates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }))
}

export function listMemoryMaterializationModules(threadId: string, includeRows = false) {
  const suffix = includeRows ? '?include_rows=true' : ''
  return j<any>(apiFetch(`/api/threads/${threadId}/memory/materialization/modules${suffix}`))
}

export function createMemoryMaterializationShadowModule(threadId: string, body: Record<string, unknown> = {}) {
  return j<any>(apiFetch(`/api/threads/${threadId}/memory/materialization/modules/shadow`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }))
}

export const api = {
  telegramWebAppLogin: (body: { init_data: string; max_age_sec?: number; ttl_sec?: number }) =>
    j<any>(apiFetch('/api/auth/telegram/webapp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })),
  createServiceRequest: (name: string, description?: string | null) =>
    j<any>(apiFetch('/api/service_requests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description: description || null }),
    })),
  adminServiceRequests: (status?: 'pending' | 'approved' | 'rejected' | 'all') => {
    const s = status && status !== 'all' ? `?status=${encodeURIComponent(status)}` : ''
    return j<any>(apiFetch(`/api/admin/service_requests${s}`))
  },
  adminApproveServiceRequest: (requestId: string) =>
    j<any>(apiFetch(`/api/admin/service_requests/${requestId}/approve`, { method: 'POST' })),
  adminServices: () => j<any>(apiFetch('/api/admin/services')),
  adminRevokeService: (serviceId: string) =>
    j<any>(apiFetch(`/api/admin/services/${serviceId}/revoke`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    })),
  adminRotateService: async (serviceId: string) => {
    const payload = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    } as const
    try {
      return await j<any>(apiFetch(`/api/admin/services/${serviceId}/rotate`, payload))
    } catch (firstErr: any) {
      // Compatibility fallback for proxy/path routing edge cases.
      try {
        return await j<any>(apiFetch(`/api/admin/services/${serviceId}/rotate_key`, payload))
      } catch {
        throw firstErr
      }
    }
  },
  adminPublishRequests: (status?: 'pending' | 'approved' | 'rejected' | 'all') => {
    const s = status && status !== 'all' ? `?status=${encodeURIComponent(status)}` : ''
    return j<any>(apiFetch(`/api/admin/publish_requests${s}`))
  },
  adminApprovePublishRequest: (requestId: string) =>
    j<any>(apiFetch(`/api/admin/publish_requests/${requestId}/approve`, { method: 'POST' })),
  adminRejectPublishRequest: (requestId: string) =>
    j<any>(apiFetch(`/api/admin/publish_requests/${requestId}/reject`, { method: 'POST' })),
  createPublishRequest: (sourceNodeId: string) =>
    j<any>(apiFetch('/api/publish_requests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_node_id: sourceNodeId }),
    })),

  agents: (scope: 'my' | 'public' | 'installed' = 'my', includeArchived = false) =>
    j<any>(apiFetch(`/api/agents?scope=${encodeURIComponent(scope)}&include_archived=${includeArchived ? 'true' : 'false'}`)),
  createAgent: (
    body: {
      name: string
      description?: string
      system_prompt?: string
      instruction?: string
      tools?: string[]
      model?: string
      visibility?: 'private' | 'unlisted' | 'public'
    },
  ) => j<any>(
    apiFetch('/api/agents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  ),
  getAgent: (agentId: string) => j<any>(apiFetch(`/api/agents/${agentId}`)),
  patchAgent: (
    agentId: string,
    body: {
      name?: string
      description?: string
      system_prompt?: string
      instruction?: string
      tools?: string[]
      model?: string
      visibility?: 'private' | 'unlisted' | 'public'
    },
  ) => j<any>(
    apiFetch(`/api/agents/${agentId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  ),
  forkAgent: (
    agentId: string,
    body?: {
      name?: string
      description?: string
      system_prompt?: string
      instruction?: string
      tools?: string[]
      model?: string
      visibility?: 'private' | 'unlisted' | 'public'
      reason?: string
      purpose?: string
      scope?: Record<string, unknown>
      scope_node_ids?: string[]
      source_surface_ids?: string[]
      publish_surface_ids?: string[]
      source_thread_id?: string
      source_run_id?: string
      rejoin_strategy?: string
    },
  ) => j<any>(
    apiFetch(`/api/agents/${agentId}/fork`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    }),
  ),
  rejoinAgent: (
    agentId: string,
    body?: {
      target_agent_id?: string
      summary?: string
      publish_surface_ids?: string[]
      artifact_ids?: string[]
      include_recent_outputs?: boolean
    },
  ) => j<any>(
    apiFetch(`/api/agents/${agentId}/rejoin`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    }),
  ),
  getAgentForkLineage: (agentId: string) => j<any>(apiFetch(`/api/agents/${agentId}/fork-lineage`)),
  publishAgent: (agentId: string) =>
    j<any>(apiFetch(`/api/agents/${agentId}/publish`, { method: 'POST' })),
  unpublishAgent: (agentId: string) =>
    j<any>(apiFetch(`/api/agents/${agentId}/unpublish`, { method: 'POST' })),
  archiveAgent: (agentId: string, archived = true) =>
    j<any>(
      apiFetch(`/api/agents/${agentId}/archive`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ archived }),
      }),
    ),
  defaultAgents: () => j<any>(apiFetch('/api/agents/defaults')),
  bootstrapDefaultAgents: (body?: { thread_id?: string | null; add_to_conversation?: boolean }) =>
    j<any>(
      apiFetch('/api/agents/bootstrap_defaults', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          thread_id: body?.thread_id || null,
          add_to_conversation: Boolean(body?.add_to_conversation),
        }),
      }),
    ),
  ensureConversation: (threadId: string) =>
    j<any>(
      apiFetch('/api/conversations/ensure', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thread_id: threadId }),
      }),
    ),
  threadTeam: (threadId: string) =>
    j<any>(apiFetch(`/api/threads/${threadId}/team`)),
  addThreadTeamMember: (
    threadId: string,
    body: {
      agent_id: string
      enabled?: boolean
      order_index?: number
      overrides_json?: Record<string, unknown> | null
    },
  ) =>
    j<any>(
      apiFetch(`/api/threads/${threadId}/team/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    ),
  patchThreadTeamMember: (
    threadId: string,
    agentId: string,
    body: {
      enabled?: boolean
      order_index?: number
      overrides_json?: Record<string, unknown> | null
    },
  ) =>
    j<any>(
      apiFetch(`/api/threads/${threadId}/team/members/${agentId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    ),
  removeThreadTeamMember: (threadId: string, agentId: string) =>
    j<any>(apiFetch(`/api/threads/${threadId}/team/members/${agentId}`, { method: 'DELETE' })),
  reorderThreadTeam: (threadId: string, agentIds: string[]) =>
    j<any>(
      apiFetch(`/api/threads/${threadId}/team/reorder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_ids: agentIds }),
      }),
    ),
  conversationAgents: (threadId: string) =>
    j<any>(apiFetch(`/api/threads/${threadId}/team`)),
  addConversationAgent: (
    threadId: string,
    body: {
      agent_id: string
      enabled?: boolean
      order_index?: number
      overrides_json?: Record<string, unknown> | null
    },
  ) =>
    j<any>(
      apiFetch(`/api/threads/${threadId}/team/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    ),
  patchConversationAgent: (
    threadId: string,
    agentId: string,
    body: {
      enabled?: boolean
      order_index?: number
      overrides_json?: Record<string, unknown> | null
    },
  ) =>
    j<any>(
      apiFetch(`/api/threads/${threadId}/team/members/${agentId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    ),
  removeConversationAgent: (threadId: string, agentId: string) =>
    j<any>(apiFetch(`/api/threads/${threadId}/team/members/${agentId}`, { method: 'DELETE' })),
  reorderConversationAgents: (threadId: string, agentIds: string[]) =>
    j<any>(
      apiFetch(`/api/threads/${threadId}/team/reorder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_ids: agentIds }),
      }),
    ),

  threads: () => j<any[]>(apiFetch('/api/threads')),
  thread: (threadId: string) => j<any>(apiFetch(`/api/threads/${threadId}`)),
  createThread: (
    title?: string,
    options?: {
      external_ref?: string | null
      meta_json?: Record<string, unknown> | null
    },
  ) =>
    j<any>(apiFetch('/api/threads', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title,
        external_ref: options?.external_ref || null,
        meta_json: options?.meta_json || null,
      }),
    })),
  ensureThread: (
    body: {
      external_ref: string
      title?: string | null
      meta_json?: Record<string, unknown> | null
      service_id?: string | null
    },
  ) => j<any>(
    apiFetch('/api/threads/ensure', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  ),
  deleteThread: (threadId: string) =>
    j<any>(apiFetch(`/api/threads/${threadId}`, { method: 'DELETE' })),

  graph: (threadId: string) => j<any>(apiFetch(`/api/threads/${threadId}/graph`)),
  runStudioSummary: (threadId: string, contextSetId?: string | null) => {
    const q = new URLSearchParams()
    const clean = (contextSetId || '').trim()
    if (clean) q.set('context_set_id', clean)
    const suffix = q.toString() ? `?${q.toString()}` : ''
    return j<any>(apiFetch(`/api/threads/${threadId}/run_studio/summary${suffix}`))
  },
  runStudioAgentTeam: (threadId: string) =>
    j<any>(apiFetch(`/api/threads/${threadId}/run_studio/agent_team`)),
  patchThreadTeamAgentContextPolicy: (
    threadId: string,
    body: {
      team_state: string
      agent_id: string
      visibility_mode?: string | null
      grants?: string[]
      context_types?: string[]
      publish_targets?: string[]
      query_template?: string | null
      soft_tokens?: number | null
      hard_tokens?: number | null
    },
  ) =>
    j<any>(apiFetch(`/api/threads/${threadId}/team/config/agents/context_policy`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })),
  runStudioContextDecisions: (threadId: string, contextSetId?: string | null) => {
    const q = new URLSearchParams()
    const clean = (contextSetId || '').trim()
    if (clean) q.set('context_set_id', clean)
    const suffix = q.toString() ? `?${q.toString()}` : ''
    return j<any>(apiFetch(`/api/threads/${threadId}/run_studio/context_decisions${suffix}`))
  },
  runStudioEvidence: (threadId: string, contextSetId?: string | null, runId?: string | null) => {
    const q = new URLSearchParams()
    const cleanContextSetId = (contextSetId || '').trim()
    const cleanRunId = (runId || '').trim()
    if (cleanContextSetId) q.set('context_set_id', cleanContextSetId)
    if (cleanRunId) q.set('run_id', cleanRunId)
    const suffix = q.toString() ? `?${q.toString()}` : ''
    return j<any>(apiFetch(`/api/threads/${threadId}/run_studio/evidence${suffix}`))
  },
  runStudioRunBundle: (threadId: string, contextSetId?: string | null, runId?: string | null) => {
    const q = new URLSearchParams()
    const cleanContextSetId = (contextSetId || '').trim()
    const cleanRunId = (runId || '').trim()
    if (cleanContextSetId) q.set('context_set_id', cleanContextSetId)
    if (cleanRunId) q.set('run_id', cleanRunId)
    const suffix = q.toString() ? `?${q.toString()}` : ''
    return j<any>(apiFetch(`/api/threads/${threadId}/run_studio/run_bundle${suffix}`))
  },
  runStudioContextPacks: (threadId: string, runId?: string | null) => {
    const q = new URLSearchParams()
    const cleanRunId = (runId || '').trim()
    if (cleanRunId) q.set('run_id', cleanRunId)
    const suffix = q.toString() ? `?${q.toString()}` : ''
    return j<any>(apiFetch(`/api/threads/${threadId}/run_studio/context_packs${suffix}`))
  },
  runStudioTraceScope: (threadId: string, runId?: string | null) => {
    const q = new URLSearchParams()
    const cleanRunId = (runId || '').trim()
    if (cleanRunId) q.set('run_id', cleanRunId)
    const suffix = q.toString() ? `?${q.toString()}` : ''
    return j<any>(apiFetch(`/api/threads/${threadId}/run_studio/trace_scope${suffix}`))
  },
  runStudioMemoryTopology: (threadId: string, runId?: string | null) => {
    const q = new URLSearchParams()
    const cleanRunId = (runId || '').trim()
    if (cleanRunId) q.set('run_id', cleanRunId)
    const suffix = q.toString() ? `?${q.toString()}` : ''
    return j<any>(apiFetch(`/api/threads/${threadId}/memory/topology${suffix}`))
  },
  runStudioMemoryDemand: (threadId: string, runId?: string | null) => {
    const q = new URLSearchParams()
    const cleanRunId = (runId || '').trim()
    if (cleanRunId) q.set('run_id', cleanRunId)
    const suffix = q.toString() ? `?${q.toString()}` : ''
    return j<any>(apiFetch(`/api/threads/${threadId}/memory/demand${suffix}`))
  },
  runStudioMemoryGraph: async (threadId: string, runId?: string | null) => {
    const q = new URLSearchParams()
    const cleanRunId = (runId || '').trim()
    if (cleanRunId) q.set('run_id', cleanRunId)
    const suffix = q.toString() ? `?${q.toString()}` : ''
    const [projections, edges, conflicts] = await Promise.all([
      j<any>(apiFetch(`/api/threads/${threadId}/memory/projections${suffix}`)),
      j<any>(apiFetch(`/api/threads/${threadId}/memory/edges${suffix}`)),
      j<any>(apiFetch(`/api/threads/${threadId}/memory/conflicts`)),
    ])
    return {
      projections: Array.isArray(projections?.items) ? projections.items : [],
      projection_count: Number(projections?.count || 0),
      edges: Array.isArray(edges?.items) ? edges.items : [],
      edge_count: Number(edges?.count || 0),
      edge_type_counts: edges?.type_counts || {},
      conflicts: Array.isArray(conflicts?.items) ? conflicts.items : [],
      conflict_count: Number(conflicts?.count || 0),
      conflict_status_counts: conflicts?.status_counts || {},
      conflict_reason_counts: conflicts?.reason_counts || {},
    }
  },
  resolveMemoryConflict: (conflictId: string, body: { status?: string | null; winning_node_id?: string | null; losing_node_ids?: string[] | null; summary?: string | null; rationale_codes?: string[] | null; supporting_claim_node_ids?: string[] | null; supporting_evidence_node_ids?: string[] | null; supporting_memory_node_ids?: string[] | null; resolved_by?: string | null; resolution_source?: string | null; merge_note?: string | null }) =>
    j<any>(apiFetch(`/api/memory/conflicts/${conflictId}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })),
  exportTeamSelectionDataset: (threadId: string, limit?: number | null, format?: 'json' | 'jsonl' | null) => {
    const q = new URLSearchParams()
    if (typeof limit === 'number' && Number.isFinite(limit) && limit > 0) q.set('limit', String(limit))
    if (format && format !== 'json') q.set('format', format)
    const suffix = q.toString() ? `?${q.toString()}` : ''
    if (format === 'jsonl') {
      return apiFetch(`/api/threads/${threadId}/team-selection-events/export${suffix}`).then(async (res) => {
        if (!res.ok) throw new Error(await readApiErrorResponse(res))
        return res.text()
      })
    }
    return j<any>(apiFetch(`/api/threads/${threadId}/team-selection-events/export${suffix}`))
  },
  runStudioSkillUsage: (threadId: string, runId?: string | null) => {
    const q = new URLSearchParams()
    const cleanRunId = (runId || '').trim()
    if (cleanRunId) q.set('run_id', cleanRunId)
    const suffix = q.toString() ? `?${q.toString()}` : ''
    return j<any>(apiFetch(`/api/threads/${threadId}/run_studio/skill_usage${suffix}`))
  },
  threadSkillUsage: (threadId: string, runId?: string | null) => {
    const q = new URLSearchParams()
    const cleanRunId = (runId || '').trim()
    if (cleanRunId) q.set('run_id', cleanRunId)
    const suffix = q.toString() ? `?${q.toString()}` : ''
    return j<any>(apiFetch(`/api/threads/${threadId}/skill_usage${suffix}`))
  },
  skills: (threadId?: string | null, options?: { include_defaults?: boolean | null }) => {
    const q = new URLSearchParams()
    const cleanThreadId = (threadId || '').trim()
    if (cleanThreadId) q.set('thread_id', cleanThreadId)
    if (options && typeof options.include_defaults === 'boolean') q.set('include_defaults', options.include_defaults ? 'true' : 'false')
    const suffix = q.toString() ? `?${q.toString()}` : ''
    return j<any>(apiFetch(`/api/skills${suffix}`))
  },
  skillDetail: (skillId: string, threadId?: string | null, options?: { include_defaults?: boolean | null }) => {
    const q = new URLSearchParams()
    const cleanThreadId = (threadId || '').trim()
    if (cleanThreadId) q.set('thread_id', cleanThreadId)
    if (options && typeof options.include_defaults === 'boolean') q.set('include_defaults', options.include_defaults ? 'true' : 'false')
    const suffix = q.toString() ? `?${q.toString()}` : ''
    return j<any>(apiFetch(`/api/skills/${encodeURIComponent(skillId)}${suffix}`))
  },
  exportSkill: (skillId: string, threadId?: string | null, options?: { include_defaults?: boolean | null }) => {
    const q = new URLSearchParams()
    const cleanThreadId = (threadId || '').trim()
    if (cleanThreadId) q.set('thread_id', cleanThreadId)
    if (options && typeof options.include_defaults === 'boolean') q.set('include_defaults', options.include_defaults ? 'true' : 'false')
    const suffix = q.toString() ? `?${q.toString()}` : ''
    return j<any>(apiFetch(`/api/skills/${encodeURIComponent(skillId)}/export${suffix}`))
  },
  installSkill: (body: { thread_id: string; skill_id?: string | null; package?: Record<string, unknown> | null; source_thread_id?: string | null; context_set_id?: string | null; auto_activate?: boolean }) =>
    j<any>(apiFetch('/api/skills/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })),
  publishSkill: (body: { skill_id?: string | null; package?: Record<string, unknown> | null; thread_id?: string | null; visibility?: 'public' | 'internal' | null }) =>
    j<any>(apiFetch('/api/skills/publish', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })),
  runSkills: (runId: string) =>
    j<any>(apiFetch(`/api/runs/${encodeURIComponent(runId)}/skills`)),
  runContextPacks: (runId: string) =>
    j<any>(apiFetch(`/api/runs/${encodeURIComponent(runId)}/context_packs`)),
  traceExport: async (
    threadId: string,
    params?: {
      run_id?: string | null
      include_compiled?: boolean
      max_compiled_chars?: number
      format?: 'zip'
    },
  ) => {
    const q = new URLSearchParams()
    q.set('include_compiled', params?.include_compiled === false ? 'false' : 'true')
    q.set('max_compiled_chars', String(params?.max_compiled_chars ?? 10000))
    q.set('format', params?.format || 'zip')
    const runId = (params?.run_id || '').trim()
    if (runId) q.set('run_id', runId)

    const res = await apiFetch(`/api/threads/${threadId}/trace_export?${q.toString()}`)
    if (!res.ok) {
      throw new Error(await readApiErrorResponse(res))
    }

    const filename = parseDownloadFilename(
      res.headers.get('Content-Disposition'),
      `trace_export_${threadId}.zip`,
    )
    const blob = await res.blob()
    return { blob, filename }
  },
  createNode: (
    threadId: string,
    body: {
      type: string
      text?: string | null
      payload_json?: Record<string, unknown> | null
      connect_from?: 'last' | { node_id: string; edge_type?: string } | null
    },
  ) => j<any>(
    apiFetch(`/api/threads/${threadId}/nodes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  ),
  saveNodeLayout: (threadId: string, positions: Array<{ id: string; x: number; y: number }>) =>
    j<any>(apiFetch(`/api/threads/${threadId}/layout`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ positions }),
    })),
  createEdge: (threadId: string, fromId: string, toId: string, type = 'NEXT') =>
    j<any>(apiFetch(`/api/threads/${threadId}/edges`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from_id: fromId, to_id: toId, type }),
    })),
  deleteEdge: (threadId: string, edgeId: string) =>
    j<any>(apiFetch(`/api/threads/${threadId}/edges/${edgeId}`, { method: 'DELETE' })),
  deleteNode: (threadId: string, nodeId: string) =>
    j<any>(apiFetch(`/api/threads/${threadId}/nodes/${nodeId}`, { method: 'DELETE' })),
  deleteNodeById: (nodeId: string) =>
    j<any>(apiFetch(`/api/nodes/${nodeId}`, { method: 'DELETE' })),

  addMessage: (threadId: string, role: 'user'|'assistant', text: string, reply_to?: string) =>
    j<any>(apiFetch(`/api/threads/${threadId}/messages`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ role, text, reply_to }) })),

  createResource: (
    threadId: string,
    body: {
      name: string
      summary?: string | null
      resource_kind?: string
      mime_type?: string | null
      uri?: string | null
      source?: 'chatgpt_upload' | 'manual' | 'link' | 'unknown'
      attach_to?: string | null
      context_set_id?: string | null
      auto_activate?: boolean
      raw_text?: string | null
      payload_json?: Record<string, unknown> | null
      text_mode?: 'formatted' | 'plain' | null
    },
  ) => j<any>(
    apiFetch(`/api/threads/${threadId}/resources`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  ),
  getThreadBoard: (threadId: string) => j<any>(apiFetch(`/api/threads/${threadId}/board`)),
  approveBoardCandidate: (threadId: string, candidateNodeId: string, body?: { publish_to_library?: boolean }) => j<any>(apiFetch(`/api/threads/${threadId}/board/candidates/${candidateNodeId}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  })),
  listImprovementJobs: (threadId: string) => j<any>(apiFetch(`/api/threads/${threadId}/improvement_jobs`)),
  createImprovementJob: (threadId: string, body: Record<string, unknown>) => j<any>(apiFetch(`/api/threads/${threadId}/improvement_jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  })),
  getImprovementJob: (threadId: string, jobId: string) => j<any>(apiFetch(`/api/threads/${threadId}/improvement_jobs/${jobId}`)),
  reportImprovementJob: (threadId: string, jobId: string, body: Record<string, unknown>) => j<any>(apiFetch(`/api/threads/${threadId}/improvement_jobs/${jobId}/report`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  })),
  listResources: (threadId: string, resourceKind?: string | null) => {
    const q = resourceKind ? `?resource_kind=${encodeURIComponent(resourceKind)}` : ''
    return j<any>(apiFetch(`/api/threads/${threadId}/resources${q}`))
  },

  getNode: (nodeId: string) => j<any>(apiFetch(`/api/nodes/${nodeId}`)),
  patchNode: (
    nodeId: string,
    body: {
      text: string
      payload_json?: string | null
    },
  ) => j<any>(
    apiFetch(`/api/nodes/${nodeId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  ),
  pinNode: (nodeId: string, level: 'required' | 'preferred' | null) =>
    j<any>(
      apiFetch(`/api/nodes/${nodeId}/pin`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level }),
      }),
    ),
  splitNode: (
    nodeId: string,
    body: {
      strategy: 'auto' | 'tagged' | 'heading' | 'bullets' | 'paragraph' | 'sentences' | 'custom'
      custom_text?: string | null
      child_type?: string | null
      context_set_id?: string | null
      replace_in_active?: boolean
      inherit_reply_to?: boolean
      target_chars?: number | null
      max_chars?: number | null
    },
  ) => j<any>(
    apiFetch(`/api/nodes/${nodeId}/split`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  ),

  importChatGPT: (
    threadId: string,
    body: {
      raw_text: string
      context_set_id?: string | null
      reply_to?: string | null
      source?: 'chatgpt_web' | 'unknown'
      auto_activate?: boolean
    },
  ) => j<any>(
    apiFetch(`/api/threads/${threadId}/import_chatgpt`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  ),

  ctxSets: (threadId: string) => j<any[]>(apiFetch(`/api/threads/${threadId}/context_sets`)),
  createCtx: (threadId: string, name: string) =>
    j<any>(apiFetch('/api/context_sets', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ thread_id: threadId, name }) })),
  ctx: (ctxId: string) => j<any>(apiFetch(`/api/context_sets/${ctxId}`)),
  ctxCompiled: (
    ctxId: string,
    includeExplainOrOptions: boolean | {
      includeExplain?: boolean
      maxChars?: number | null
      excludeTypes?: string[] | null
      excludeResourceKinds?: string[] | null
      includeMeta?: boolean
    } = true,
    extraOptions?: {
      maxChars?: number | null
      excludeTypes?: string[] | null
      excludeResourceKinds?: string[] | null
      includeMeta?: boolean
    },
  ) => {
    let includeExplain = true
    let opts: {
      maxChars?: number | null
      excludeTypes?: string[] | null
      excludeResourceKinds?: string[] | null
      includeMeta?: boolean
    } = {}

    if (typeof includeExplainOrOptions === 'boolean') {
      includeExplain = includeExplainOrOptions
      opts = extraOptions || {}
    } else {
      includeExplain = includeExplainOrOptions.includeExplain ?? true
      opts = includeExplainOrOptions
    }

    const q = new URLSearchParams()
    q.set('include_explain', includeExplain ? 'true' : 'false')
    if (opts.maxChars != null) q.set('max_chars', String(opts.maxChars))
    if (opts.excludeTypes && opts.excludeTypes.length > 0) q.set('exclude_types', opts.excludeTypes.join(','))
    if (opts.excludeResourceKinds && opts.excludeResourceKinds.length > 0) {
      q.set('exclude_resource_kinds', opts.excludeResourceKinds.join(','))
    }
    if (opts.includeMeta) q.set('include_meta', 'true')

    return j<any>(apiFetch(`/api/context_sets/${ctxId}/compiled?${q.toString()}`))
  },
  ctxVersions: (ctxId: string, limit = 20) =>
    j<any>(apiFetch(`/api/context_sets/${ctxId}/versions?limit=${limit}`)),
  ctxVersionDiff: (ctxId: string, fromVersion: number, toVersion: number) =>
    j<any>(apiFetch(`/api/context_sets/${ctxId}/diff?from_version=${fromVersion}&to_version=${toVersion}`)),
  previewUnfoldPlan: (
    ctxId: string,
    body: {
      query: string
      top_k?: number
      max_candidates?: number
      budget_tokens?: number
      closure_edge_types?: string[] | null
      closure_direction?: 'out' | 'in' | 'both'
      max_closure_nodes?: number | null
    },
  ) => j<any>(
    apiFetch(`/api/context_sets/${ctxId}/unfold_plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  ),
  applyUnfoldPlan: (
    ctxId: string,
    body: {
      seed_node_ids: string[]
      budget_tokens?: number
      closure_edge_types?: string[] | null
      closure_direction?: 'out' | 'in' | 'both'
      max_closure_nodes?: number | null
      include_explain?: boolean
    },
  ) => j<any>(
    apiFetch(`/api/context_sets/${ctxId}/apply_unfold_plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  ),
  reorderActive: (ctxId: string, nodeIds: string[]) =>
    j<any>(apiFetch(`/api/context_sets/${ctxId}/reorder`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_ids: nodeIds }),
    })),
  ctxRebuildActive: (
    ctxId: string,
    policy?: {
      recent_user_messages?: number
      recent_assistant_messages?: number
      recent_steps?: number
      recent_artifacts?: number
      exclude_resource_kinds?: string[]
      include_pinned?: boolean
    },
  ) => j<any>(
    apiFetch(`/api/context_sets/${ctxId}/rebuild_active`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ policy: policy || {} }),
    }),
  ),

  activate: (ctxId: string, nodeIds: string[]) =>
    j<any>(apiFetch(`/api/context_sets/${ctxId}/activate`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ node_ids: nodeIds }) })),
  deactivate: (ctxId: string, nodeIds: string[]) =>
    j<any>(apiFetch(`/api/context_sets/${ctxId}/deactivate`, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ node_ids: nodeIds }) })),

  fold: (threadId: string, memberIds: string[], title?: string) =>
    j<any>(apiFetch('/api/folds', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ thread_id: threadId, member_node_ids: memberIds, title }) })),
  unfold: (
    ctxId: string,
    foldId: string,
    body?: {
      closure_edge_types?: string[] | null
      closure_direction?: 'out' | 'in' | 'both'
      max_closure_nodes?: number | null
      replace_only_fold?: boolean
      include_explain?: boolean
    },
  ) =>
    j<any>(apiFetch(`/api/context_sets/${ctxId}/unfold/${foldId}`, {
      method:'POST',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })),

  run: (ctxId: string, user_message: string) =>
    j<any>(apiFetch('/api/runs', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ context_set_id: ctxId, user_message }) })),

  hierarchyPreview: (
    threadId: string,
    body: { context_set_id?: string | null; node_ids?: string[] | null; max_leaf_size?: number },
  ) => j<any>(
    apiFetch(`/api/threads/${threadId}/hierarchy_preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  ),

  search: (threadId: string, q: string, k = 10) =>
    j<any>(apiFetch(`/api/threads/${threadId}/search?q=${encodeURIComponent(q)}&k=${k}`)),

  estimateTokens: (text: string, model?: string | null) =>
    j<{ tokens: number; method: 'tiktoken' | 'heuristic' }>(
      apiFetch('/api/tokens/estimate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, model: model || null }),
      }),
    ),
}
