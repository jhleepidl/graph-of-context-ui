import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import {
  applyManualPriorityRules,
  buildDependencyMap,
  manualRuleLabel,
  manualRulePillClass,
  nodeTypePillClass,
  pickBudgetedNodes,
  priorityBucketLabel,
  priorityBucketPillClass,
  scoreNodesForRequest,
  type ManualPriorityRule,
  type NodePriorityScore,
} from '../utils/contextPriority'

type ContextNode = {
  id: string
  type?: string | null
  text?: string | null
  created_at?: string | null
  payload_json?: string | null
}

type EdgeLike = { id?: string; from_id: string; to_id: string; type?: string | null }

type Props = {
  activeNodes: ContextNode[]
  allNodes?: ContextNode[]
  edges?: EdgeLike[]
  threadId: string | null
  ctxId: string | null
  onAfterMutation: () => Promise<void>
  onReplaceActive?: (nodeIds: string[]) => Promise<void>
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

function formatPct01(v: number): string {
  if (!Number.isFinite(v)) return '-'
  return `${Math.round(v * 100)}%`
}

function formatResourceLine(n: ContextNode): string {
  const payload = parsePayload(n.payload_json)
  const name = (payload.name || '').toString().trim() || `resource-${shortId(n.id)}`
  const kind = (payload.resource_kind || 'file').toString()
  const source = (payload.source || 'unknown').toString()
  const uri = (payload.uri || '').toString().trim()
  const summary = (payload.summary || n.text || '').toString().trim()

  const lines = [`- ${name} (kind=${kind}, source=${source}, id=${shortId(n.id)})`]
  if (uri) lines.push(`  - uri: ${uri}`)
  if (summary) {
    const compact = summary.replace(/\s+/g, ' ').trim()
    lines.push(`  - summary: ${compact.slice(0, 320)}${compact.length > 320 ? '...' : ''}`)
  }
  return lines.join('\n')
}

function CopyToChatGPTPanel({ activeNodes, allNodes = [], edges = [], threadId, ctxId, onAfterMutation, onReplaceActive }: Props) {
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

  const [resourceName, setResourceName] = useState('')
  const [resourceKind, setResourceKind] = useState<'file' | 'link' | 'image' | 'table' | 'doc' | 'code' | 'other'>('file')
  const [resourceUri, setResourceUri] = useState('')
  const [resourceSummary, setResourceSummary] = useState('')
  const [resourceStatus, setResourceStatus] = useState('')

  const [priorityBudgetTokens, setPriorityBudgetTokens] = useState('2000')
  const [priorityStatus, setPriorityStatus] = useState('')
  const [priorityRules, setPriorityRules] = useState<Record<string, ManualPriorityRule>>({})

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

  const resourceNodes = useMemo(() => orderedActiveNodes.filter((n) => (n.type || '') === 'Resource'), [orderedActiveNodes])
  const activeContextNodes = useMemo(() => orderedActiveNodes.filter((n) => (n.type || '') !== 'Resource'), [orderedActiveNodes])

  const analyzableAllNodes = useMemo(() => {
    const base = (allNodes && allNodes.length > 0 ? allNodes : activeNodes)
      .filter((n): n is ContextNode => Boolean(n && n.id))
    const seen = new Set<string>()
    return base.filter((n) => {
      if (seen.has(n.id)) return false
      seen.add(n.id)
      return true
    })
  }, [allNodes, activeNodes])

  const activeIdSet = useMemo(() => new Set(orderedActiveNodes.map((n) => n.id)), [orderedActiveNodes])

  const baseScoredAllNodes = useMemo(() => {
    return scoreNodesForRequest(analyzableAllNodes, userRequest)
  }, [analyzableAllNodes, userRequest])

  const scoredAllNodes = useMemo(() => {
    return applyManualPriorityRules(baseScoredAllNodes, priorityRules)
  }, [baseScoredAllNodes, priorityRules])

  const scoreByNodeId = useMemo(() => new Map(scoredAllNodes.map((s) => [s.node.id, s])), [scoredAllNodes])

  const dependencyMap = useMemo(() => {
    return buildDependencyMap(edges)
  }, [edges])

  const alwaysIncludeIdSet = useMemo(() => new Set(Object.entries(priorityRules).filter(([, v]) => v === 'always').map(([k]) => k)), [priorityRules])
  const neverIncludeIdSet = useMemo(() => new Set(Object.entries(priorityRules).filter(([, v]) => v === 'never').map(([k]) => k)), [priorityRules])
  const pinnedIdSet = useMemo(() => new Set(Object.entries(priorityRules).filter(([, v]) => v === 'pin').map(([k]) => k)), [priorityRules])

  const scoredActiveContextNodes = useMemo(() => {
    return activeContextNodes
      .map((n) => scoreByNodeId.get(n.id))
      .filter((v): v is NodePriorityScore => Boolean(v))
      .sort((a, b) => {
        const ar = a.manualRule === 'always' ? 3 : a.manualRule === 'pin' ? 2 : a.manualRule === 'never' ? -1 : 0
        const br = b.manualRule === 'always' ? 3 : b.manualRule === 'pin' ? 2 : b.manualRule === 'never' ? -1 : 0
        if (ar !== br) return br - ar
        return b.priority - a.priority
      })
  }, [activeContextNodes, scoreByNodeId])

  const scoredMissingCandidates = useMemo(() => {
    return scoredAllNodes
      .filter((s) => !activeIdSet.has(s.node.id))
      .filter((s) => (s.node.type || '') !== 'Resource')
      .sort((a, b) => {
        const ar = a.manualRule === 'always' ? 3 : a.manualRule === 'pin' ? 2 : a.manualRule === 'never' ? -1 : 0
        const br = b.manualRule === 'always' ? 3 : b.manualRule === 'pin' ? 2 : b.manualRule === 'never' ? -1 : 0
        if (ar !== br) return br - ar
        return (b.priority + b.omissionRisk * 0.35) - (a.priority + a.omissionRisk * 0.35)
      })
  }, [scoredAllNodes, activeIdSet])

  const highRiskMissingCandidates = useMemo(() => {
    return scoredMissingCandidates
      .filter((s) => s.manualRule === 'always' || (s.bucket !== 'skippable' && (s.relevance >= 0.12 || s.locality >= 0.58)))
      .slice(0, 8)
  }, [scoredMissingCandidates])

  const priorityBudgetValue = useMemo(() => {
    const n = Number(priorityBudgetTokens)
    return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0
  }, [priorityBudgetTokens])

  const budgetSelection = useMemo(() => {
    if (!priorityBudgetValue || scoredActiveContextNodes.length === 0) return null
    return pickBudgetedNodes(scoredActiveContextNodes, priorityBudgetValue, {
      dependencyMap,
      alwaysIncludeIds: alwaysIncludeIdSet,
      neverIncludeIds: neverIncludeIdSet,
      pinnedIds: pinnedIdSet,
    })
  }, [priorityBudgetValue, scoredActiveContextNodes, dependencyMap, alwaysIncludeIdSet, neverIncludeIdSet, pinnedIdSet])

  const budgetSelectedIdSet = useMemo(() => {
    if (!budgetSelection) return new Set<string>()
    return new Set(budgetSelection.selected.map((s) => s.node.id))
  }, [budgetSelection])

  const resourcesSection = useMemo(() => {
    if (resourceNodes.length === 0) return '(none)'
    return resourceNodes.map(formatResourceLine).join('\n')
  }, [resourceNodes])

  const contextSection = useMemo(() => {
    if (activeContextNodes.length === 0) {
      return '(active context is empty)'
    }
    return activeContextNodes
      .map((n) => {
        const body = (n.text || '').trim() || '(empty)'
        return `[NODE ${shortId(n.id)} type=${n.type || 'Unknown'}]\n${body}`
      })
      .join('\n\n')
  }, [activeContextNodes])

  const builtPrompt = useMemo(() => {
    const req = userRequest.trim() || '(write request here)'
    return [
      LANGUAGE_LOCK,
      '',
      TAGGED_FORMAT,
      '',
      '[RESOURCES]',
      resourcesSection,
      '',
      '[ACTIVE CONTEXT]',
      contextSection,
      '',
      '[USER REQUEST]',
      req,
    ].join('\n')
  }, [contextSection, resourcesSection, userRequest])

  const bootstrapPrompt = useMemo(() => {
    return [
      LANGUAGE_LOCK,
      '',
      BOOTSTRAP_NOTICE,
      BOOTSTRAP_REPLY_RULE,
      '',
      TAGGED_FORMAT,
      '',
      '[RESOURCES]',
      resourcesSection,
      '',
      '[ACTIVE CONTEXT]',
      contextSection,
    ].join('\n')
  }, [contextSection, resourcesSection])

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
    if (!threadId) {
      setPriorityRules({})
      return
    }
    try {
      const raw = localStorage.getItem(`goc:priorityRules:${threadId}`)
      const parsed = raw ? JSON.parse(raw) : {}
      if (parsed && typeof parsed === 'object') {
        const next: Record<string, ManualPriorityRule> = {}
        for (const [k, v] of Object.entries(parsed)) {
          if (v === 'pin' || v === 'always' || v === 'never') next[k] = v
        }
        setPriorityRules(next)
      } else {
        setPriorityRules({})
      }
    } catch {
      setPriorityRules({})
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

  function persistPriorityRules(next: Record<string, ManualPriorityRule>) {
    setPriorityRules(next)
    if (!threadId) return
    try {
      localStorage.setItem(`goc:priorityRules:${threadId}`, JSON.stringify(next))
    } catch {
      // ignore storage failures
    }
  }

  function setNodePriorityRule(nodeId: string, rule: ManualPriorityRule | null) {
    setPriorityStatus('')
    const next = { ...priorityRules }
    if (!rule) delete next[nodeId]
    else next[nodeId] = rule
    persistPriorityRules(next)
  }

  function clearPriorityRules() {
    persistPriorityRules({})
    setPriorityStatus('수동 우선순위 규칙을 초기화했습니다.')
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

  async function handleCreateResourceNode() {
    const name = resourceName.trim()
    const summary = resourceSummary.trim()
    if (!name) {
      setResourceStatus('파일명/리소스명을 입력하세요.')
      return
    }
    if (!threadId) {
      setResourceStatus('thread가 선택되지 않았습니다.')
      return
    }
    try {
      const out = await api.createResource(threadId, {
        name,
        summary: summary || null,
        resource_kind: resourceKind,
        uri: resourceUri.trim() || null,
        source: resourceKind === 'link' ? 'link' : 'chatgpt_upload',
        attach_to: lastUserRequestNodeId,
        context_set_id: ctxId,
        auto_activate: true,
      })
      await onAfterMutation()
      const nid = out?.node?.id ? shortId(out.node.id) : '-'
      setResourceStatus(`Resource 노드 추가 완료 (${nid})${lastUserRequestNodeId ? ' · 최근 USER REQUEST에 연결' : ''}`)
      setResourceName('')
      setResourceUri('')
      setResourceSummary('')
    } catch (e: any) {
      setResourceStatus(`실패: ${e?.message || String(e)}`)
    }
  }

  function insertResourceTemplate(kind: typeof resourceKind) {
    setResourceKind(kind)
    if (!resourceSummary.trim()) {
      setResourceSummary(
        kind === 'file'
          ? '이 리소스가 답변에 어떤 영향을 줬는지(핵심 섹션/제약/숫자/주의사항)를 3~5줄로 적으세요.'
          : '링크/리소스의 핵심 내용과 이 대화에서 필요한 포인트를 요약하세요.'
      )
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

  async function handleAddPriorityCandidate(nodeId: string) {
    if (!ctxId) {
      setPriorityStatus('활성화할 Context Set이 없습니다.')
      return
    }
    try {
      await api.activate(ctxId, [nodeId])
      await onAfterMutation()
      setPriorityStatus(`추천 노드를 Active에 추가: ${shortId(nodeId)}`)
    } catch (e: any) {
      setPriorityStatus(`추가 실패: ${e?.message || String(e)}`)
    }
  }

  async function handleApplyPriorityBudget() {
    if (!onReplaceActive) {
      setPriorityStatus('Active 교체 콜백이 연결되지 않았습니다.')
      return
    }
    if (!budgetSelection || priorityBudgetValue <= 0) {
      setPriorityStatus('유효한 budget을 입력하세요.')
      return
    }

    const resourceIds = orderedActiveNodes.filter((n) => (n.type || '') === 'Resource').map((n) => n.id)
    const selectedIds = budgetSelection.selected.map((s) => s.node.id)
    try {
      await onReplaceActive([...resourceIds, ...selectedIds])
      setPriorityStatus(`Budget 적용 완료: ${selectedIds.length}개 context + ${resourceIds.length}개 resource${budgetSelection.dependencyAddedIds.length ? ` · dependency ${budgetSelection.dependencyAddedIds.length}개 포함` : ''}`)
    } catch (e: any) {
      setPriorityStatus(`Budget 적용 실패: ${e?.message || String(e)}`)
    }
  }

  function ruleOf(nodeId: string): ManualPriorityRule | null {
    return priorityRules[nodeId] || null
  }

  function RuleButtons({ nodeId }: { nodeId: string }) {
    const current = ruleOf(nodeId)
    return (
      <span className="ruleButtons">
        <button className={`tiny ${current === 'pin' ? 'isActive' : ''}`} onClick={() => setNodePriorityRule(nodeId, current === 'pin' ? null : 'pin')}>Pin</button>
        <button className={`tiny ${current === 'always' ? 'isActive' : ''}`} onClick={() => setNodePriorityRule(nodeId, current === 'always' ? null : 'always')}>Always</button>
        <button className={`tiny ${current === 'never' ? 'isActive' : ''}`} onClick={() => setNodePriorityRule(nodeId, current === 'never' ? null : 'never')}>Never</button>
        {current && <button className="tiny" onClick={() => setNodePriorityRule(nodeId, null)}>Clear</button>}
      </span>
    )
  }

  return (
    <div>
      <h3>Copy to ChatGPT</h3>
      <div className="muted">템플릿은 영어지만 답변은 한국어로 하도록 프롬프트에 포함됩니다. Active Resource는 [RESOURCES] 섹션으로 자동 포함됩니다. (현재 {resourceNodes.length}개)</div>
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
                    <span className={`pill pillType ${item.node_type === "Resource" ? "pill--resource" : "pill--default"}`}>{item.node_type}</span>
                  </label>
                  {priorityRules[item.node_id] && <span className={`pill ${manualRulePillClass(priorityRules[item.node_id])}`}>{manualRuleLabel(priorityRules[item.node_id])}</span>}
                  <button onClick={() => handleAddSuggested(item.node_id)}>Add</button>
                  <RuleButtons nodeId={item.node_id} />
                </div>
                <div className="muted">
                  score={formatScore(item.score)} id={shortId(item.node_id)}
                  {scoreByNodeId.get(item.node_id) ? ` · heuristic=${formatPct01(scoreByNodeId.get(item.node_id)!.priority)} (${priorityBucketLabel(scoreByNodeId.get(item.node_id)!.bucket)})` : ''}
                </div>
                <div style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{item.snippet || '(empty)'}</div>
              </div>
            )
          })}
        </div>
      )}

      <h3>Context Prioritizer (Beta)</h3>
      <div className="muted">
        USER REQUEST 기준으로 각 노드의 로컬성/생략위험/관련도를 추정해 우선순위를 추천합니다. 절대판정이 아니라 추천기입니다.
      </div>
      <div className="row">
        <span className="pill">active analyzed: {scoredActiveContextNodes.length}</span>
        <span className="pill">missing candidates: {highRiskMissingCandidates.length}</span>
        <span className="pill">budget: {priorityBudgetValue || '-'} tok</span>
        <span className="pill">rules: {Object.keys(priorityRules).length}</span>
        <button onClick={clearPriorityRules} disabled={Object.keys(priorityRules).length === 0}>Clear rules</button>
        {priorityStatus && <span className="muted">{priorityStatus}</span>}
      </div>
      <div className="card">
        <div className="row" style={{ marginBottom: 6 }}>
          <b>Budget-based Active trim</b>
          <input
            value={priorityBudgetTokens}
            onChange={(e) => setPriorityBudgetTokens(e.target.value.replace(/[^0-9]/g, ''))}
            placeholder="2000"
            style={{ width: 96, padding: 6 }}
          />
          <button onClick={() => setPriorityBudgetTokens('1000')}>1k</button>
          <button onClick={() => setPriorityBudgetTokens('2000')}>2k</button>
          <button onClick={() => setPriorityBudgetTokens('4000')}>4k</button>
          <button onClick={handleApplyPriorityBudget} disabled={!budgetSelection || !onReplaceActive}>Apply to Active</button>
        </div>
        {budgetSelection ? (
          <>
            <div className="muted" style={{ marginBottom: 8 }}>
              selected {budgetSelection.selected.length} / {scoredActiveContextNodes.length} nodes · approx {budgetSelection.usedTokens} tokens · deps {budgetSelection.dependencyAddedIds.length}
            </div>
            <div className="priorityList">
              {budgetSelection.selected.slice(0, 6).map((s) => (
                <div key={`budget-${s.node.id}`} className="priorityRow">
                  <div className="priorityRowMain">
                    <span className={`pill pillType ${nodeTypePillClass(s.node.type)}`}>{s.node.type || 'Unknown'}</span>
                    <span className={`pill ${priorityBucketPillClass(s.bucket)}`}>{priorityBucketLabel(s.bucket)}</span>
                    {s.manualRule && <span className={`pill ${manualRulePillClass(s.manualRule)}`}>{manualRuleLabel(s.manualRule)}</span>}
                    {s.selectionTag && <span className="pill">{s.selectionTag}</span>}
                    <span className="muted">{shortId(s.node.id)} · ~{s.estTokens}t</span>
                  </div>
                  <div className="prioritySnippet">{((s.node.text || '').trim() || '(empty)').slice(0, 220)}</div>
                </div>
              ))}
            </div>
            {budgetSelection.omitted.length > 0 && (
              <div className="muted" style={{ marginTop: 8 }}>
                제외 예정 상위: {budgetSelection.omitted.slice(0, 3).map((s) => `${shortId(s.node.id)}(${priorityBucketLabel(s.bucket)})`).join(', ')}
              </div>
            )}
          </>
        ) : (
          <div className="muted">Budget 입력 후 Active context가 있으면 자동 선택 미리보기가 표시됩니다. (수동 규칙 + dependency-aware 적용)</div>
        )}
      </div>

      {scoredActiveContextNodes.length > 0 && (
        <div className="card">
          <div className="row" style={{ marginBottom: 6 }}>
            <b>Active node priority</b>
            <span className="muted">현재 요청 기준 상위 {Math.min(8, scoredActiveContextNodes.length)}개</span>
          </div>
          <div className="priorityList">
            {scoredActiveContextNodes.slice(0, 8).map((s) => (
              <div key={`active-priority-${s.node.id}`} className={`priorityRow ${budgetSelection && !budgetSelectedIdSet.has(s.node.id) ? 'isDim' : ''}`}>
                <div className="priorityRowMain">
                  <span className={`pill pillType ${nodeTypePillClass(s.node.type)}`}>{s.node.type || 'Unknown'}</span>
                  <span className={`pill ${priorityBucketPillClass(s.bucket)}`}>{priorityBucketLabel(s.bucket)}</span>
                  {s.manualRule && <span className={`pill ${manualRulePillClass(s.manualRule)}`}>{manualRuleLabel(s.manualRule)}</span>}
                  <span className="pill">P {formatPct01(s.priority)}</span>
                  <span className="pill">L {formatPct01(s.locality)}</span>
                  <span className="pill">R {formatPct01(s.relevance)}</span>
                  <span className="pill">Risk {formatPct01(s.omissionRisk)}</span>
                  <span className="muted">~{s.estTokens}t · {shortId(s.node.id)}</span>
                  <RuleButtons nodeId={s.node.id} />
                </div>
                {s.reasons.length > 0 && <div className="muted">{s.reasons.join(' · ')}</div>}
                <div className="prioritySnippet">{((s.node.text || '').trim() || '(empty)').slice(0, 240)}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {highRiskMissingCandidates.length > 0 && (
        <div className="card">
          <div className="row" style={{ marginBottom: 6 }}>
            <b>Missing but likely useful</b>
            <span className="muted">Active에 없는 후보 (요청 기준)</span>
          </div>
          <div className="priorityList">
            {highRiskMissingCandidates.map((s) => (
              <div key={`missing-priority-${s.node.id}`} className="priorityRow">
                <div className="priorityRowMain">
                  <span className={`pill pillType ${nodeTypePillClass(s.node.type)}`}>{s.node.type || 'Unknown'}</span>
                  <span className={`pill ${priorityBucketPillClass(s.bucket)}`}>{priorityBucketLabel(s.bucket)}</span>
                  {s.manualRule && <span className={`pill ${manualRulePillClass(s.manualRule)}`}>{manualRuleLabel(s.manualRule)}</span>}
                  <span className="pill">Risk {formatPct01(s.omissionRisk)}</span>
                  <span className="pill">R {formatPct01(s.relevance)}</span>
                  <span className="muted">~{s.estTokens}t · {shortId(s.node.id)}</span>
                  <button onClick={() => handleAddPriorityCandidate(s.node.id)} disabled={!ctxId}>Add</button>
                  <RuleButtons nodeId={s.node.id} />
                </div>
                {s.reasons.length > 0 && <div className="muted">{s.reasons.join(' · ')}</div>}
                <div className="prioritySnippet">{((s.node.text || '').trim() || '(empty)').slice(0, 220)}</div>
              </div>
            ))}
          </div>
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

      <h3>Resource Notes (Attachments/Links)</h3>
      <div className="muted">ChatGPT 웹 첨부파일은 자동 수집이 어렵기 때문에, 파일명/요약만 Resource 노드로 기록해 두는 방식입니다. 필요하면 최근 USER REQUEST와 ATTACHED_TO edge로 연결됩니다.</div>
      <div className="row">
        <input
          value={resourceName}
          onChange={(e) => setResourceName(e.target.value)}
          placeholder="예: requirements_v3.pdf"
          style={{ flex: 1, padding: 8, borderRadius: 10, border: '1px solid #e5e7eb' }}
        />
        <select value={resourceKind} onChange={(e) => setResourceKind(e.target.value as any)} style={{ padding: 8, borderRadius: 10, border: '1px solid #e5e7eb' }}>
          <option value="file">file</option>
          <option value="link">link</option>
          <option value="image">image</option>
          <option value="table">table</option>
          <option value="doc">doc</option>
          <option value="code">code</option>
          <option value="other">other</option>
        </select>
      </div>
      <div className="row">
        <input
          value={resourceUri}
          onChange={(e) => setResourceUri(e.target.value)}
          placeholder="링크/경로(선택)"
          style={{ flex: 1, padding: 8, borderRadius: 10, border: '1px solid #e5e7eb' }}
        />
        <button onClick={() => insertResourceTemplate('file')}>첨부파일 템플릿</button>
        <button onClick={() => insertResourceTemplate('link')}>링크 템플릿</button>
      </div>
      <textarea
        value={resourceSummary}
        onChange={(e) => setResourceSummary(e.target.value)}
        placeholder="이 리소스의 핵심 요약 / 답변에 영향 준 포인트 / 재사용시 주의점"
      />
      <div className="row">
        <button onClick={handleCreateResourceNode}>Add Resource Node</button>
        {resourceStatus && <div className="muted">{resourceStatus}</div>}
      </div>

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

export default CopyToChatGPTPanel
