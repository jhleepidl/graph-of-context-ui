const API_BASE = (import.meta.env.VITE_API_BASE || '').trim().replace(/\/+$/, '')

function apiUrl(path: string): string {
  return API_BASE ? `${API_BASE}${path}` : path
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
  threads: () => j<any[]>(fetch(apiUrl('/api/threads'))),
  createThread: (title?: string) =>
    j<any>(fetch(apiUrl('/api/threads'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title }) })),

  graph: (threadId: string) => j<any>(fetch(apiUrl(`/api/threads/${threadId}/graph`))),
  saveNodeLayout: (threadId: string, positions: Array<{ id: string; x: number; y: number }>) =>
    j<any>(fetch(apiUrl(`/api/threads/${threadId}/layout`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ positions }),
    })),
  createEdge: (threadId: string, fromId: string, toId: string, type = 'NEXT') =>
    j<any>(fetch(apiUrl(`/api/threads/${threadId}/edges`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ from_id: fromId, to_id: toId, type }),
    })),
  deleteEdge: (threadId: string, edgeId: string) =>
    j<any>(fetch(apiUrl(`/api/threads/${threadId}/edges/${edgeId}`), {
      method: 'DELETE',
    })),
  deleteNode: (threadId: string, nodeId: string) =>
    j<any>(fetch(apiUrl(`/api/threads/${threadId}/nodes/${nodeId}`), {
      method: 'DELETE',
    })),

  addMessage: (threadId: string, role: 'user'|'assistant', text: string, reply_to?: string) =>
    j<any>(fetch(apiUrl(`/api/threads/${threadId}/messages`), { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ role, text, reply_to })})),

  getNode: (nodeId: string) =>
    j<any>(fetch(apiUrl(`/api/nodes/${nodeId}`))),
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
    fetch(apiUrl(`/api/nodes/${nodeId}/split`), {
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
    fetch(apiUrl(`/api/threads/${threadId}/import_chatgpt`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  ),

  ctxSets: (threadId: string) => j<any[]>(fetch(apiUrl(`/api/threads/${threadId}/context_sets`))),
  createCtx: (threadId: string, name: string) =>
    j<any>(fetch(apiUrl('/api/context_sets'), { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ thread_id: threadId, name })})),
  ctx: (ctxId: string) => j<any>(fetch(apiUrl(`/api/context_sets/${ctxId}`))),
  reorderActive: (ctxId: string, nodeIds: string[]) =>
    j<any>(fetch(apiUrl(`/api/context_sets/${ctxId}/reorder`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ node_ids: nodeIds }),
    })),

  activate: (ctxId: string, nodeIds: string[]) =>
    j<any>(fetch(apiUrl(`/api/context_sets/${ctxId}/activate`), { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ node_ids: nodeIds })})),
  deactivate: (ctxId: string, nodeIds: string[]) =>
    j<any>(fetch(apiUrl(`/api/context_sets/${ctxId}/deactivate`), { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ node_ids: nodeIds })})),

  fold: (threadId: string, memberIds: string[], title?: string) =>
    j<any>(fetch(apiUrl('/api/folds'), { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ thread_id: threadId, member_node_ids: memberIds, title })})),
  unfold: (ctxId: string, foldId: string) =>
    j<any>(fetch(apiUrl(`/api/context_sets/${ctxId}/unfold/${foldId}`), { method:'POST' })),

  run: (ctxId: string, user_message: string) =>
    j<any>(fetch(apiUrl('/api/runs'), { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ context_set_id: ctxId, user_message })})),

  search: (threadId: string, q: string, k = 10) =>
    j<any>(fetch(apiUrl(`/api/threads/${threadId}/search?q=${encodeURIComponent(q)}&k=${k}`))),

  estimateTokens: (text: string, model?: string | null) =>
    j<{ tokens: number; method: 'tiktoken' | 'heuristic' }>(
      fetch(apiUrl('/api/tokens/estimate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, model: model || null }),
      }),
    ),
}
