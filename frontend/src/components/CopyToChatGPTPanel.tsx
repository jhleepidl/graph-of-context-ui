import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api'

type ContextNode = {
  id: string
  type?: string | null
  text?: string | null
  created_at?: string | null
  payload_json?: string | null
}

type Props = {
  activeNodes: ContextNode[]
  threadId: string | null
  ctxId: string | null
  onAfterMutation: () => Promise<void>
}

type SearchResult = {
  node_id: string
  score: number
  node_type: string
  snippet: string
}

const LANGUAGE_LOCK = '중요: 아래 포맷/규칙은 영어로 쓰여있지만, 너의 답변 내용은 반드시 한국어로 작성해라.'
const BOOTSTRAP_NOTICE = '이 채팅은 새 대화다. 아래 ACTIVE CONTEXT를 앞으로의 대화에서 배경지식으로 사용해라.'
const BOOTSTRAP_REPLY_RULE = 'TAGGED FORMAT으로 답하고, [FINAL]에는 짧은 확인 문장(한국어)만 작성하고 긴 본문은 쓰지 마라.'

const TAGGED_FORMAT = `Respond in the following TAGGED FORMAT exactly (sections optional, but keep [FINAL]):

[FINAL]
<final answer in Korean>

[DECISIONS]
- ...

[ASSUMPTIONS]
- ...

[PLAN]
- ...

[CONTEXT_CANDIDATES]
- ...

Rules:
- Bullets must start with "- "
- Do not include any extra sections besides these.
- Use ONLY the ACTIVE CONTEXT below. If insufficient, ask which context to add.
- Keep it concise.`

function shortId(id: string): string {
  return id.slice(0, 6)
}

function parsePayload(payloadJson?: string | null): Record<string, any> {
  try {
    return JSON.parse(payloadJson || '{}')
  } catch {
    return {}
  }
}

function formatScore(score: number): string {
  if (!Number.isFinite(score)) return '-'
  return score.toFixed(4)
}

export default function CopyToChatGPTPanel({ activeNodes, threadId, ctxId, onAfterMutation }: Props) {
  const [userRequest, setUserRequest] = useState('')
  const [status, setStatus] = useState('')
  const [userRequestStatus, setUserRequestStatus] = useState('')
  const [autoSaveUserRequest, setAutoSaveUserRequest] = useState(true)
  const [lastUserRequestNodeId, setLastUserRequestNodeId] = useState<string | null>(null)
  const [previewText, setPreviewText] = useState('')

  const [pasteText, setPasteText] = useState('')
  const [pasteStatus, setPasteStatus] = useState('')
  const [manualContextText, setManualContextText] = useState('')
  const [manualStatus, setManualStatus] = useState('')
  const [suggestStatus, setSuggestStatus] = useState('')
  const [suggestResults, setSuggestResults] = useState<SearchResult[]>([])
  const [selectedSuggestionIds, setSelectedSuggestionIds] = useState<string[]>([])

  const [targetWindow, setTargetWindow] = useState<'8000' | '32000' | '128000'>('32000')
  const [activeContextTokens, setActiveContextTokens] = useState<number | null>(null)
  const [fullPromptTokens, setFullPromptTokens] = useState<number | null>(null)
  const [tokenMethod, setTokenMethod] = useState<'tiktoken' | 'heuristic' | ''>('')
  const [tokenStatus, setTokenStatus] = useState('')

  const orderedActiveNodes = useMemo(() => {
    const seen = new Set<string>()
    const orderedUnique = activeNodes.filter((node) => {
      if (!node?.id) return false
      if (seen.has(node.id)) return false
      seen.add(node.id)
      return true
    })

    const activeSet = new Set(orderedUnique.map((n) => n.id))
    const excludedParents = new Set<string>()
    for (const node of orderedUnique) {
      const payload = parsePayload(node.payload_json)
      const parentId = typeof payload.parent_id === 'string' ? payload.parent_id : ''
      if (parentId && activeSet.has(parentId)) {
        excludedParents.add(parentId)
      }
    }
    return orderedUnique.filter((node) => !excludedParents.has(node.id))
  }, [activeNodes])

  const contextSection = useMemo(() => {
    if (orderedActiveNodes.length === 0) {
      return '(active context is empty)'
    }
    return orderedActiveNodes
      .map((n) => {
        const body = (n.text || '').trim() || '(empty)'
        return `[NODE ${shortId(n.id)} type=${n.type || 'Unknown'}]\n${body}`
      })
      .join('\n\n')
  }, [orderedActiveNodes])

  const builtPrompt = useMemo(() => {
    const req = userRequest.trim() || '(write request here)'
    return [
      LANGUAGE_LOCK,
      '',
      TAGGED_FORMAT,
      '',
      '[ACTIVE CONTEXT]',
      contextSection,
      '',
      '[USER REQUEST]',
      req,
    ].join('\n')
  }, [contextSection, userRequest])

  const bootstrapPrompt = useMemo(() => {
    return [
      LANGUAGE_LOCK,
      '',
      BOOTSTRAP_NOTICE,
      BOOTSTRAP_REPLY_RULE,
      '',
      TAGGED_FORMAT,
      '',
      '[ACTIVE CONTEXT]',
      contextSection,
    ].join('\n')
  }, [contextSection])

  const usageRatio = useMemo(() => {
    if (fullPromptTokens == null) return 0
    const win = Number(targetWindow)
    if (!Number.isFinite(win) || win <= 0) return 0
    return fullPromptTokens / win
  }, [fullPromptTokens, targetWindow])

  useEffect(() => {
    if (!threadId) {
      setLastUserRequestNodeId(null)
      return
    }
    try {
      const cached = localStorage.getItem(`goc:lastUserReq:${threadId}`)
      setLastUserRequestNodeId(cached || null)
    } catch {
      setLastUserRequestNodeId(null)
    }
  }, [threadId])

  useEffect(() => {
    const timer = window.setTimeout(async () => {
      try {
        setTokenStatus('')
        const [ctxTok, promptTok] = await Promise.all([
          api.estimateTokens(contextSection, null),
          api.estimateTokens(builtPrompt, null),
        ])
        setActiveContextTokens(ctxTok.tokens)
        setFullPromptTokens(promptTok.tokens)
        setTokenMethod(promptTok.method || ctxTok.method)
      } catch (e: any) {
        setTokenStatus(`토큰 추정 실패: ${e?.message || String(e)}`)
      }
    }, 300)
    return () => window.clearTimeout(timer)
  }, [contextSection, builtPrompt])

  function cacheLastUserRequestNodeId(nodeId: string) {
    setLastUserRequestNodeId(nodeId)
    if (!threadId) return
    try {
      localStorage.setItem(`goc:lastUserReq:${threadId}`, nodeId)
    } catch {
      // ignore storage failures
    }
  }

  async function copyWithFallback(text: string): Promise<void> {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return
    }

    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.left = '-9999px'
    document.body.appendChild(ta)

    const selection = document.getSelection()
    const prevRange = selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null

    ta.select()
    ta.setSelectionRange(0, ta.value.length)
    const ok = document.execCommand('copy')

    document.body.removeChild(ta)
    if (prevRange && selection) {
      selection.removeAllRanges()
      selection.addRange(prevRange)
    }

    if (!ok) {
      throw new Error('copy command failed')
    }
  }

  async function createAndActivateMessage(role: 'user' | 'assistant', text: string): Promise<any> {
    if (!threadId) {
      throw new Error('thread가 선택되지 않았습니다.')
    }
    const node = await api.addMessage(threadId, role, text)
    if (ctxId) {
      await api.activate(ctxId, [node.id])
    }
    return node
  }

  async function copyPrompt() {
    try {
      setPreviewText(builtPrompt)
      let savedNodeId: string | null = null
      const req = userRequest.trim()
      if (autoSaveUserRequest && req) {
        const userNode = await createAndActivateMessage('user', req)
        savedNodeId = userNode.id
        cacheLastUserRequestNodeId(userNode.id)
        await onAfterMutation()
      }
      await copyWithFallback(builtPrompt)
      if (savedNodeId) {
        setStatus(`복사됨 (USER REQUEST 저장: ${shortId(savedNodeId)})`)
      } else {
        setStatus('복사됨')
      }
    } catch (e: any) {
      setStatus(`복사 실패: ${e?.message || String(e)}`)
    }
  }

  async function copyBootstrapPrompt() {
    try {
      setPreviewText(bootstrapPrompt)
      await copyWithFallback(bootstrapPrompt)
      setStatus('Bootstrap Prompt 복사됨')
    } catch (e: any) {
      setStatus(`복사 실패: ${e?.message || String(e)}`)
    }
  }

  async function handleAddUserRequestContext() {
    const req = userRequest.trim()
    if (!req) {
      setUserRequestStatus('USER REQUEST를 입력하세요.')
      return
    }
    try {
      const userNode = await createAndActivateMessage('user', req)
      cacheLastUserRequestNodeId(userNode.id)
      await onAfterMutation()
      setUserRequestStatus(`USER REQUEST를 Context 노드로 추가했습니다. (${shortId(userNode.id)})`)
    } catch (e: any) {
      setUserRequestStatus(`실패: ${e?.message || String(e)}`)
    }
  }

  async function handlePasteFromChatGPT() {
    const raw = pasteText.trim()
    if (!raw) {
      setPasteStatus('붙여넣을 텍스트를 입력하세요.')
      return
    }
    if (!threadId) {
      setPasteStatus('thread가 선택되지 않았습니다.')
      return
    }
    try {
      const imported = await api.importChatGPT(threadId, {
        raw_text: raw,
        context_set_id: ctxId,
        reply_to: lastUserRequestNodeId,
        source: 'chatgpt_web',
        auto_activate: true,
      })
      await onAfterMutation()

      const created = imported.created || {}
      const decisionIds: string[] = created.decision_ids || []
      const assumptionIds: string[] = created.assumption_ids || []
      const planIds: string[] = created.plan_ids || []
      const candidateIds: string[] = created.candidate_ids || []
      const finalCount = created.final_node_id ? 1 : 0
      const createdOrder = (imported.created_order || []).map((id: string) => shortId(id)).join(', ')
      const replyToUsed = imported.reply_to_used ? shortId(imported.reply_to_used) : '-'

      setPasteStatus(
        `가져오기 완료 | FINAL ${finalCount}, DECISIONS ${decisionIds.length}, ASSUMPTIONS ${assumptionIds.length}, PLAN ${planIds.length}, CONTEXT_CANDIDATES ${candidateIds.length} | IDs: ${createdOrder || '-'} | reply_to: ${replyToUsed}`,
      )
      setPasteText('')
    } catch (e: any) {
      setPasteStatus(`실패: ${e?.message || String(e)}`)
    }
  }

  async function handleCreateContextNode() {
    const text = manualContextText.trim()
    if (!text) {
      setManualStatus('Context 텍스트를 입력하세요.')
      return
    }
    try {
      await createAndActivateMessage('user', text)
      await onAfterMutation()
      setManualStatus('Context 노드를 생성하고 Active Context에 추가했습니다.')
      setManualContextText('')
    } catch (e: any) {
      setManualStatus(`실패: ${e?.message || String(e)}`)
    }
  }

  async function handleSuggestContext() {
    const q = userRequest.trim()
    if (!q) {
      setSuggestStatus('먼저 USER REQUEST를 입력하세요.')
      setSuggestResults([])
      setSelectedSuggestionIds([])
      return
    }
    if (!threadId) {
      setSuggestStatus('thread가 선택되지 않았습니다.')
      return
    }
    try {
      const out = await api.search(threadId, q, 10)
      const results = (out.results || []) as SearchResult[]
      setSuggestResults(results)
      setSelectedSuggestionIds([])
      setSuggestStatus(`${results.length}개 추천 결과`)
    } catch (e: any) {
      setSuggestStatus(`추천 실패: ${e?.message || String(e)}`)
    }
  }

  async function handleAddSuggested(nodeId: string) {
    if (!ctxId) {
      setSuggestStatus('활성화할 Context Set이 없습니다.')
      return
    }
    try {
      await api.activate(ctxId, [nodeId])
      await onAfterMutation()
      setSuggestStatus(`Active에 추가: ${shortId(nodeId)}`)
    } catch (e: any) {
      setSuggestStatus(`추가 실패: ${e?.message || String(e)}`)
    }
  }

  async function handleAddSelectedSuggestions() {
    if (!ctxId) {
      setSuggestStatus('활성화할 Context Set이 없습니다.')
      return
    }
    if (selectedSuggestionIds.length === 0) {
      setSuggestStatus('선택된 추천 항목이 없습니다.')
      return
    }
    try {
      await api.activate(ctxId, selectedSuggestionIds)
      await onAfterMutation()
      setSuggestStatus(`${selectedSuggestionIds.length}개를 Active에 추가했습니다.`)
      setSelectedSuggestionIds([])
    } catch (e: any) {
      setSuggestStatus(`추가 실패: ${e?.message || String(e)}`)
    }
  }

  function toggleSuggestionSelection(nodeId: string) {
    setSelectedSuggestionIds((prev) => {
      if (prev.includes(nodeId)) {
        return prev.filter((id) => id !== nodeId)
      }
      return [...prev, nodeId]
    })
  }

  return (
    <div>
      <h3>Copy to ChatGPT</h3>
      <div className="muted">템플릿은 영어지만 답변은 한국어로 하도록 프롬프트에 포함됩니다.</div>
      <textarea
        value={userRequest}
        onChange={(e) => setUserRequest(e.target.value)}
        placeholder="사용자 요청을 입력하세요."
      />
      <div className="row">
        <label className="muted" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <input
            type="checkbox"
            checked={autoSaveUserRequest}
            onChange={(e) => setAutoSaveUserRequest(e.target.checked)}
          />
          Copy할 때 USER REQUEST를 노드로 저장
        </label>
      </div>
      <div className="row">
        <button className="primary" onClick={copyPrompt}>Copy Prompt</button>
        <button onClick={copyBootstrapPrompt}>Copy Bootstrap (Context Only)</button>
        <button onClick={handleAddUserRequestContext}>Add USER REQUEST to Context</button>
        {status && <div className="muted">{status}</div>}
      </div>
      <div className="muted">
        Last USER REQUEST node: {lastUserRequestNodeId ? shortId(lastUserRequestNodeId) : '-'}
      </div>
      {userRequestStatus && <div className="muted">{userRequestStatus}</div>}

      <h3>Paste from ChatGPT</h3>
      <textarea
        value={pasteText}
        onChange={(e) => setPasteText(e.target.value)}
        placeholder="ChatGPT 응답을 붙여넣으세요. 백엔드에서 [FINAL]/[DECISIONS]...를 파싱해 구조화 노드로 가져옵니다."
      />
      <div className="row">
        <button onClick={handlePasteFromChatGPT}>Paste from ChatGPT</button>
        {pasteStatus && <div className="muted">{pasteStatus}</div>}
      </div>

      <h3>Suggest Context</h3>
      <div className="row">
        <button onClick={handleSuggestContext}>Suggest Context for this request</button>
        <button onClick={handleAddSelectedSuggestions}>Add selected to Active</button>
        {suggestStatus && <div className="muted">{suggestStatus}</div>}
      </div>
      {suggestResults.length > 0 && (
        <div>
          {suggestResults.map((item) => {
            const checked = selectedSuggestionIds.includes(item.node_id)
            return (
              <div key={item.node_id} className="card">
                <div className="row">
                  <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleSuggestionSelection(item.node_id)}
                    />
                    <span className="pill">{item.node_type}</span>
                  </label>
                  <button onClick={() => handleAddSuggested(item.node_id)}>Add</button>
                </div>
                <div className="muted">score={formatScore(item.score)} id={shortId(item.node_id)}</div>
                <div style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{item.snippet || '(empty)'}</div>
              </div>
            )
          })}
        </div>
      )}

      <h3>Token Estimate</h3>
      <div className="row">
        <label className="muted">
          Target window:
          <select
            value={targetWindow}
            onChange={(e) => setTargetWindow(e.target.value as '8000' | '32000' | '128000')}
            style={{ marginLeft: 6 }}
          >
            <option value="8000">8k</option>
            <option value="32000">32k</option>
            <option value="128000">128k</option>
          </select>
        </label>
      </div>
      <div className="muted">Active Context: {activeContextTokens ?? '-'} tokens</div>
      <div className="muted">Full Prompt: {fullPromptTokens ?? '-'} tokens {tokenMethod ? `(${tokenMethod})` : ''}</div>
      <div className="tokenBar">
        <div
          className={`tokenBarFill ${usageRatio > 0.8 ? 'warn' : ''}`}
          style={{ width: `${Math.min(100, Math.max(0, usageRatio * 100))}%` }}
        />
      </div>
      <div className="muted">
        Usage: {fullPromptTokens ?? 0} / {Number(targetWindow).toLocaleString()} ({(usageRatio * 100).toFixed(1)}%)
      </div>
      {usageRatio > 0.8 && <div className="muted" style={{ color: '#b91c1c' }}>경고: 컨텍스트 윈도우의 80%를 넘었습니다.</div>}
      {tokenStatus && <div className="muted">{tokenStatus}</div>}

      <h3>Create Context Node</h3>
      <textarea
        value={manualContextText}
        onChange={(e) => setManualContextText(e.target.value)}
        placeholder="Run 없이 추가할 Context 내용을 입력하세요."
      />
      <div className="row">
        <button onClick={handleCreateContextNode}>Add Context Node</button>
        {manualStatus && <div className="muted">{manualStatus}</div>}
      </div>

      {previewText && (
        <>
          <h3>Prompt Preview</h3>
          <textarea
            readOnly
            value={previewText}
            style={{ height: 260 }}
          />
        </>
      )}
    </div>
  )
}
