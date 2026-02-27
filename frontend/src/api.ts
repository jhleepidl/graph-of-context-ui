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

  return ''
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

  const token = getStoredBearerToken()
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

export const api = {
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
    j<any>(apiFetch(`/api/admin/services/${serviceId}/revoke`, { method: 'POST' })),
  adminRotateService: (serviceId: string) =>
    j<any>(apiFetch(`/api/admin/services/${serviceId}/rotate`, { method: 'POST' })),

  threads: () => j<any[]>(apiFetch('/api/threads')),
  createThread: (title?: string) =>
    j<any>(apiFetch('/api/threads', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title }) })),
  deleteThread: (threadId: string) =>
    j<any>(apiFetch(`/api/threads/${threadId}`, { method: 'DELETE' })),

  graph: (threadId: string) => j<any>(apiFetch(`/api/threads/${threadId}/graph`)),
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
    },
  ) => j<any>(
    apiFetch(`/api/threads/${threadId}/resources`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  ),

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
  ctxCompiled: (ctxId: string, includeExplain = true) =>
    j<any>(apiFetch(`/api/context_sets/${ctxId}/compiled?include_explain=${includeExplain ? 'true' : 'false'}`)),
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
