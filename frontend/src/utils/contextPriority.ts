export type PrioritizableNode = {
  id: string
  type?: string | null
  text?: string | null
  created_at?: string | null
  payload_json?: string | null
}

export type PrioritizableEdge = {
  id?: string
  from_id: string
  to_id: string
  type?: string | null
}

export type PriorityBucket = 'must' | 'recommended' | 'optional' | 'skippable'
export type ManualPriorityRule = 'pin' | 'always' | 'never'

export type NodePriorityScore = {
  node: PrioritizableNode
  priority: number
  locality: number
  omissionRisk: number
  redundancy: number
  relevance: number
  costPenalty: number
  estTokens: number
  bucket: PriorityBucket
  reasons: string[]
  manualRule?: ManualPriorityRule | null
  selectionTag?: 'always' | 'must' | 'value' | 'dependency'
  dependencyIds?: string[]
}

export type PickBudgetOptions = {
  dependencyMap?: Map<string, string[]>
  alwaysIncludeIds?: Iterable<string>
  neverIncludeIds?: Iterable<string>
  pinnedIds?: Iterable<string>
}

const STOPWORDS = new Set([
  'the','and','for','with','that','this','from','into','your','you','are','was','were','been','have','has','had','will','would','can','could','should','about','after','before','when','where','what','which','while','than','then','them','they','their','there','here','also','just','only','using','used','use','need','make','made','like','such','very','more','most','less','many','much','some','any','each','other','others','than','onto','over','under','through',
  '그리고','그런데','하지만','또한','이것','저것','그것','있다','없다','하는','하기','에서','으로','이다','입니다','하는데','위해','대한','관련','사용','현재','경우','정도','같은','같다','때문','때문에','해야','한다','하면','하고','까지','에서','및','또','수','더','잘','좀','있는','없는'
])

function clamp01(n: number): number {
  if (!Number.isFinite(n)) return 0
  if (n < 0) return 0
  if (n > 1) return 1
  return n
}

export function parsePayloadSafe(payloadJson?: string | null): Record<string, unknown> {
  try {
    const parsed = JSON.parse(payloadJson || '{}')
    if (parsed && typeof parsed === 'object') return parsed as Record<string, unknown>
    return {}
  } catch {
    return {}
  }
}

export function estimateTokensHeuristic(text?: string | null): number {
  const s = (text || '').trim()
  if (!s) return 0
  const chars = s.length
  const lines = s.split(/\n+/).length
  return Math.max(1, Math.ceil(chars / 3.2) + Math.floor(lines * 0.5))
}

function normalizeText(s?: string | null): string {
  return (s || '').replace(/\s+/g, ' ').trim().toLowerCase()
}

function extractTerms(s?: string | null): string[] {
  const text = normalizeText(s)
  if (!text) return []
  const matches = text.match(/[a-z0-9가-힣_\-./]{2,}/g) || []
  return matches.filter((t) => !STOPWORDS.has(t) && t.length >= 2)
}

function buildCorpusTermFreq(nodes: PrioritizableNode[]): Map<string, number> {
  const freq = new Map<string, number>()
  for (const node of nodes) {
    const payload = parsePayloadSafe(node.payload_json)
    const payloadBits = [payload.name, payload.uri, payload.summary]
      .filter((v): v is string => typeof v === 'string')
      .join(' ')
    const seen = new Set<string>(extractTerms(`${node.text || ''} ${payloadBits}`))
    for (const t of seen) {
      freq.set(t, (freq.get(t) || 0) + 1)
    }
  }
  return freq
}

function overlapScore(aTerms: string[], bTerms: string[]): number {
  if (!aTerms.length || !bTerms.length) return 0
  const a = new Set(aTerms)
  const b = new Set(bTerms)
  let hit = 0
  for (const t of a) {
    if (b.has(t)) hit += 1
  }
  const denom = Math.max(1, Math.min(a.size, b.size))
  return clamp01(hit / denom)
}

function countMatches(text: string, patterns: RegExp[]): number {
  let count = 0
  for (const p of patterns) {
    if (p.test(text)) count += 1
  }
  return count
}

function typeWeights(type?: string | null): { locality: number; omission: number; redundancyBias: number } {
  switch (type || '') {
    case 'Decision':
      return { locality: 0.72, omission: 0.9, redundancyBias: 0.15 }
    case 'Assumption':
      return { locality: 0.7, omission: 0.82, redundancyBias: 0.18 }
    case 'Plan':
      return { locality: 0.64, omission: 0.8, redundancyBias: 0.14 }
    case 'Resource':
      return { locality: 0.68, omission: 0.74, redundancyBias: 0.2 }
    case 'Fold':
      return { locality: 0.62, omission: 0.76, redundancyBias: 0.12 }
    case 'ContextCandidate':
      return { locality: 0.46, omission: 0.48, redundancyBias: 0.35 }
    case 'Message':
      return { locality: 0.5, omission: 0.54, redundancyBias: 0.3 }
    default:
      return { locality: 0.44, omission: 0.52, redundancyBias: 0.26 }
  }
}

function recencyScore(createdAt?: string | null): number {
  if (!createdAt) return 0.4
  const t = new Date(createdAt).getTime()
  if (!Number.isFinite(t)) return 0.4
  const ageMs = Date.now() - t
  if (ageMs <= 0) return 1
  const days = ageMs / (1000 * 60 * 60 * 24)
  if (days <= 1) return 1
  if (days <= 7) return 0.85
  if (days <= 30) return 0.65
  if (days <= 90) return 0.45
  return 0.28
}

export function scoreNodeForRequest(
  node: PrioritizableNode,
  userRequest: string,
  corpusTermFreq: Map<string, number>,
  corpusSize: number,
): NodePriorityScore {
  const payload = parsePayloadSafe(node.payload_json)
  const payloadText = [payload.name, payload.uri, payload.summary]
    .filter((v): v is string => typeof v === 'string')
    .join(' ')
  const text = `${node.text || ''} ${payloadText}`.trim()
  const normalized = normalizeText(text)
  const nodeTerms = extractTerms(text)
  const reqTerms = extractTerms(userRequest)

  let rareHits = 0
  let technicalHits = 0
  let namingHits = 0
  let uniqueLikeHits = 0
  const seen = new Set(nodeTerms)
  for (const term of seen) {
    const f = corpusTermFreq.get(term) || 0
    if (f <= Math.max(1, Math.floor(corpusSize * 0.05))) rareHits += 1
    if (/[A-Za-z]/.test(term) && (/[_.\/]/.test(term) || /\d/.test(term) || /[A-Z]/.test(term))) technicalHits += 1
    if (/^[a-z]+(?:[A-Z][a-z0-9]+)+$/.test(term) || /^[a-z0-9]+(?:_[a-z0-9]+)+$/.test(term) || /^[a-z0-9]+(?:-[a-z0-9]+)+$/.test(term)) namingHits += 1
    if (term.length >= 6 && f <= 2) uniqueLikeHits += 1
  }

  const overlap = overlapScore(nodeTerms, reqTerms)
  let queryMentionBoost = 0
  if (reqTerms.length) {
    const reqJoined = reqTerms.join(' ')
    if (reqJoined && normalized.includes(reqTerms[0] || '')) queryMentionBoost += 0.08
  }
  for (const t of reqTerms.slice(0, 8)) {
    if (t && normalized.includes(t)) queryMentionBoost += 0.03
  }
  queryMentionBoost = clamp01(queryMentionBoost)
  const relevance = clamp01(overlap * 0.75 + queryMentionBoost * 0.4)

  const typeW = typeWeights(node.type)
  const explicitConstraintHits = countMatches(text, [/\bmust\b/i, /\bshould not\b/i, /\bdo not\b/i, /주의/, /제약/, /규칙/, /금지/, /항상/, /반드시/, /예외/])
  const localitySignals = clamp01(
    typeW.locality * 0.55 +
    Math.min(1, rareHits / 6) * 0.22 +
    Math.min(1, technicalHits / 5) * 0.12 +
    Math.min(1, namingHits / 3) * 0.1 +
    Math.min(1, uniqueLikeHits / 5) * 0.1,
  )

  const estTokens = estimateTokensHeuristic(text)
  const costPenalty = clamp01(estTokens / 1200)

  const genericPhrases = countMatches(text, [/예시/i, /예를 들/i, /기본적으로/, /일반적으로/, /typically/i, /generally/i, /overview/i, /요약/])
  const redundancy = clamp01(
    typeW.redundancyBias * 0.5 +
    (1 - Math.min(1, rareHits / 5)) * 0.2 +
    Math.min(1, genericPhrases / 4) * 0.25 +
    (relevance < 0.1 ? 0.15 : 0),
  )

  const omissionRisk = clamp01(
    typeW.omission * 0.45 +
    relevance * 0.28 +
    localitySignals * 0.2 +
    Math.min(1, explicitConstraintHits / 2) * 0.14 +
    recencyScore(node.created_at) * 0.06,
  )

  const priority = clamp01(
    omissionRisk * 0.42 +
    relevance * 0.36 +
    localitySignals * 0.18 +
    recencyScore(node.created_at) * 0.08 -
    redundancy * 0.16 -
    costPenalty * 0.14,
  )

  let bucket: PriorityBucket
  if (omissionRisk >= 0.72 && (relevance >= 0.16 || localitySignals >= 0.55)) bucket = 'must'
  else if (priority >= 0.5 || (relevance >= 0.25 && omissionRisk >= 0.45)) bucket = 'recommended'
  else if (priority >= 0.28) bucket = 'optional'
  else bucket = 'skippable'

  const reasons: string[] = []
  if (relevance >= 0.35) reasons.push('요청과 직접 관련')
  else if (relevance >= 0.15) reasons.push('요청과 부분 관련')
  if (localitySignals >= 0.65) reasons.push('로컬/고유 정보 가능성 높음')
  else if (localitySignals >= 0.48) reasons.push('프로젝트 특화 가능성')
  if (omissionRisk >= 0.7) reasons.push('생략 시 혼동 위험 높음')
  if ((node.type || '') === 'Decision') reasons.push('결정사항 타입')
  if ((node.type || '') === 'Assumption') reasons.push('가정/전제 타입')
  if ((node.type || '') === 'Plan') reasons.push('실행계획 타입')
  if ((node.type || '') === 'Resource') reasons.push('첨부/리소스 메타')
  if (costPenalty >= 0.7) reasons.push('길어서 토큰 비용 큼')
  if (redundancy >= 0.55) reasons.push('일반/중복 정보일 수 있음')

  return {
    node,
    priority,
    locality: localitySignals,
    omissionRisk,
    redundancy,
    relevance,
    costPenalty,
    estTokens,
    bucket,
    reasons: reasons.slice(0, 4),
    manualRule: null,
    dependencyIds: [],
  }
}

export function scoreNodesForRequest(nodes: PrioritizableNode[], userRequest: string): NodePriorityScore[] {
  const corpus = nodes.filter((n) => Boolean(n?.id))
  const termFreq = buildCorpusTermFreq(corpus)
  const size = Math.max(1, corpus.length)
  return corpus.map((n) => scoreNodeForRequest(n, userRequest, termFreq, size))
}

export function applyManualPriorityRules(
  scored: NodePriorityScore[],
  rules?: Record<string, ManualPriorityRule | undefined>,
): NodePriorityScore[] {
  if (!rules || Object.keys(rules).length === 0) return scored
  return scored.map((s) => {
    const rule = rules[s.node.id]
    if (!rule) return s
    if (rule === 'always') {
      return {
        ...s,
        manualRule: 'always',
        priority: Math.max(s.priority, 0.97),
        omissionRisk: Math.max(s.omissionRisk, 0.9),
        bucket: 'must',
        reasons: ['사용자 고정(항상 포함)', ...s.reasons.filter((r) => r !== '사용자 고정(항상 포함)')].slice(0, 5),
      }
    }
    if (rule === 'never') {
      return {
        ...s,
        manualRule: 'never',
        priority: Math.min(s.priority, 0.03),
        omissionRisk: Math.min(s.omissionRisk, 0.08),
        bucket: 'skippable',
        reasons: ['사용자 규칙(기본 제외)', ...s.reasons.filter((r) => r !== '사용자 규칙(기본 제외)')].slice(0, 5),
      }
    }
    return {
      ...s,
      manualRule: 'pin',
      priority: clamp01(s.priority + 0.08),
      reasons: ['사용자 핀(우선 고려)', ...s.reasons.filter((r) => r !== '사용자 핀(우선 고려)')].slice(0, 5),
    }
  })
}

const DEP_TYPES_DEFAULT = new Set(['REPLY_TO', 'ATTACHED_TO', 'REFERENCES', 'SUPPORTS', 'USES', 'INVOKES', 'RETURNS', 'SPLIT_FROM'])

export function buildDependencyMap(
  edges: PrioritizableEdge[],
  options?: { includeTypes?: string[]; includeHasPart?: boolean; bidirectional?: boolean },
): Map<string, string[]> {
  const includeTypes = new Set((options?.includeTypes && options.includeTypes.length > 0)
    ? options.includeTypes
    : Array.from(DEP_TYPES_DEFAULT))
  if (options?.includeHasPart) includeTypes.add('HAS_PART')
  const bidirectional = options?.bidirectional !== false
  const out = new Map<string, Set<string>>()

  const add = (a: string, b: string) => {
    if (!a || !b || a === b) return
    const cur = out.get(a) || new Set<string>()
    cur.add(b)
    out.set(a, cur)
  }

  for (const e of edges || []) {
    const t = (e.type || '').toString()
    if (!includeTypes.has(t)) continue
    add(e.from_id, e.to_id)
    if (bidirectional) add(e.to_id, e.from_id)
  }

  return new Map(Array.from(out.entries()).map(([k, v]) => [k, Array.from(v)]))
}

export function pickBudgetedNodes(scored: NodePriorityScore[], budgetTokens: number, opts?: PickBudgetOptions): {
  selected: NodePriorityScore[]
  omitted: NodePriorityScore[]
  usedTokens: number
  dependencyAddedIds: string[]
} {
  const budget = Math.max(1, Math.floor(budgetTokens))
  const alwaysIds = new Set<string>(Array.from(opts?.alwaysIncludeIds || []))
  const neverIds = new Set<string>(Array.from(opts?.neverIncludeIds || []))
  const pinnedIds = new Set<string>(Array.from(opts?.pinnedIds || []))
  const depMap = opts?.dependencyMap || new Map<string, string[]>()

  const byId = new Map(scored.map((s) => [s.node.id, s]))
  const candidates = scored.filter((s) => !neverIds.has(s.node.id))
  const must = candidates
    .filter((s) => s.bucket === 'must' || alwaysIds.has(s.node.id))
    .sort((a, b) => {
      const aAlways = alwaysIds.has(a.node.id) ? 1 : 0
      const bAlways = alwaysIds.has(b.node.id) ? 1 : 0
      if (aAlways !== bAlways) return bAlways - aAlways
      const aPinned = pinnedIds.has(a.node.id) ? 1 : 0
      const bPinned = pinnedIds.has(b.node.id) ? 1 : 0
      if (aPinned !== bPinned) return bPinned - aPinned
      return b.priority - a.priority
    })
  const rest = candidates
    .filter((s) => s.bucket !== 'must' && !alwaysIds.has(s.node.id))
    .sort((a, b) => {
      const aPinned = pinnedIds.has(a.node.id) ? 1 : 0
      const bPinned = pinnedIds.has(b.node.id) ? 1 : 0
      if (aPinned !== bPinned) return bPinned - aPinned
      const av = (a.priority + a.omissionRisk * 0.4 + (aPinned ? 0.12 : 0)) / Math.max(1, a.estTokens)
      const bv = (b.priority + b.omissionRisk * 0.4 + (bPinned ? 0.12 : 0)) / Math.max(1, b.estTokens)
      if (Math.abs(bv - av) > 1e-9) return bv - av
      return b.priority - a.priority
    })

  const selected: NodePriorityScore[] = []
  let used = 0
  const seen = new Set<string>()
  const dependencyAdded = new Set<string>()

  const includeOne = (base: NodePriorityScore, tag: NodePriorityScore['selectionTag'], allowOverrun: boolean): boolean => {
    if (seen.has(base.node.id) || neverIds.has(base.node.id)) return false

    const chainIds: string[] = []
    const stack = [...(depMap.get(base.node.id) || [])]
    const visited = new Set<string>()
    while (stack.length > 0) {
      const depId = stack.pop() as string
      if (!depId || visited.has(depId) || depId === base.node.id) continue
      visited.add(depId)
      if (neverIds.has(depId)) continue
      const depScore = byId.get(depId)
      if (!depScore) continue
      chainIds.push(depId)
      for (const next of depMap.get(depId) || []) {
        if (!visited.has(next)) stack.push(next)
      }
    }

    const depScores = chainIds
      .map((id) => byId.get(id))
      .filter((v): v is NodePriorityScore => Boolean(v))
      .filter((s) => !seen.has(s.node.id))
      .sort((a, b) => {
        const aPinned = pinnedIds.has(a.node.id) ? 1 : 0
        const bPinned = pinnedIds.has(b.node.id) ? 1 : 0
        if (aPinned !== bPinned) return bPinned - aPinned
        return b.priority - a.priority
      })

    let packageTokens = Math.max(1, base.estTokens)
    for (const d of depScores) packageTokens += Math.max(1, d.estTokens)

    if (!allowOverrun && used + packageTokens > budget) {
      return false
    }
    if (allowOverrun && used + packageTokens > budget * 1.25 && selected.length > 0) {
      return false
    }

    for (const d of depScores) {
      if (seen.has(d.node.id)) continue
      seen.add(d.node.id)
      used += Math.max(1, d.estTokens)
      dependencyAdded.add(d.node.id)
      selected.push({ ...d, selectionTag: 'dependency' })
    }
    seen.add(base.node.id)
    used += Math.max(1, base.estTokens)
    selected.push({ ...base, selectionTag: tag, dependencyIds: depScores.map((d) => d.node.id) })
    return true
  }

  for (const s of must) {
    const allowOverrun = true
    const tag: NodePriorityScore['selectionTag'] = alwaysIds.has(s.node.id) ? 'always' : 'must'
    includeOne(s, tag, allowOverrun)
  }

  for (const s of rest) {
    if (seen.has(s.node.id)) continue
    includeOne(s, 'value', false)
  }

  const omitted = scored.filter((s) => !seen.has(s.node.id)).sort((a, b) => b.priority - a.priority)
  selected.sort((a, b) => {
    const rankTag = (t?: NodePriorityScore['selectionTag']) => (t === 'always' ? 0 : t === 'must' ? 1 : t === 'dependency' ? 2 : 3)
    const dt = rankTag(a.selectionTag) - rankTag(b.selectionTag)
    if (dt !== 0) return dt
    if (a.bucket === 'must' && b.bucket !== 'must') return -1
    if (a.bucket !== 'must' && b.bucket === 'must') return 1
    return b.priority - a.priority
  })

  return { selected, omitted, usedTokens: used, dependencyAddedIds: Array.from(dependencyAdded) }
}

export function priorityBucketLabel(bucket: PriorityBucket): string {
  if (bucket === 'must') return 'MUST'
  if (bucket === 'recommended') return 'RECOMMEND'
  if (bucket === 'optional') return 'OPTIONAL'
  return 'SKIP'
}

export function priorityBucketPillClass(bucket: PriorityBucket): string {
  if (bucket === 'must') return 'pill--must'
  if (bucket === 'recommended') return 'pill--recommend'
  if (bucket === 'optional') return 'pill--optional'
  return 'pill--skip'
}

export function manualRuleLabel(rule?: ManualPriorityRule | null): string {
  if (rule === 'always') return 'ALWAYS'
  if (rule === 'never') return 'NEVER'
  if (rule === 'pin') return 'PIN'
  return ''
}

export function manualRulePillClass(rule?: ManualPriorityRule | null): string {
  if (rule === 'always') return 'pill--must'
  if (rule === 'never') return 'pill--skip'
  if (rule === 'pin') return 'pill--recommend'
  return 'pill--default'
}

export function nodeTypePillClass(type?: string | null): string {
  if (type === 'Resource') return 'pill--resource'
  if (type === 'Fold') return 'pill--fold'
  if (type === 'Decision') return 'pill--decision'
  if (type === 'Assumption') return 'pill--assumption'
  if (type === 'Plan') return 'pill--plan'
  if (type === 'ContextCandidate') return 'pill--candidate'
  if (type === 'MemoryItem') return 'pill--memory'
  return 'pill--default'
}
