import React from 'react'

type PlannerCandidate = {
  seed_id: string
  seed_type?: string
  score?: number
  marginal_cost_tokens?: number
  closure_size?: number
  preview?: string
  closure_ids?: string[]
}

type Props = {
  compiledText: string
  excludedParentIds: string[]
  keptNodeIds: string[]
  versions: any[]
  versionDiff: any | null
  plannerResult: any | null
  nodesById: Map<string, any>
  onRefresh: () => void | Promise<void>
  onLoadDiff: (fromVersion: number, toVersion: number) => void | Promise<void>
  onPlan: (query: string, budgetTokens: number) => void | Promise<void>
  onApplySeeds: (seedIds: string[], budgetTokens: number) => void | Promise<void>
}

function shortId(id: string): string {
  return (id || '').slice(0, 6)
}

function nodeLabel(nodesById: Map<string, any>, nodeId: string): string {
  const n = nodesById.get(nodeId)
  if (!n) return nodeId
  const text = (n.text || '').replace(/\s+/g, ' ').trim()
  const preview = text ? ` · ${text.slice(0, 42)}${text.length > 42 ? '…' : ''}` : ''
  return `${n.type || 'Node'} ${shortId(nodeId)}${preview}`
}

export default function ContextInspector({
  compiledText,
  excludedParentIds,
  keptNodeIds,
  versions,
  versionDiff,
  plannerResult,
  nodesById,
  onRefresh,
  onLoadDiff,
  onPlan,
  onApplySeeds,
}: Props) {
  const [query, setQuery] = React.useState('')
  const [budgetTokens, setBudgetTokens] = React.useState(1200)
  const [selectedSeeds, setSelectedSeeds] = React.useState<string[]>([])

  React.useEffect(() => {
    setSelectedSeeds(plannerResult?.recommended_seed_ids || [])
  }, [plannerResult])

  function toggleSeed(seedId: string) {
    setSelectedSeeds((prev) => prev.includes(seedId) ? prev.filter((x) => x !== seedId) : [...prev, seedId])
  }

  const candidates: PlannerCandidate[] = plannerResult?.candidates || []
  const latest = versions?.[0]
  const previous = versions?.[1]

  return (
    <div className="contextInspectorStack">
      <div className="card inspectorCard">
        <div className="row inspectorHeader">
          <b>Compiled Context</b>
          <button onClick={() => onRefresh()}>Refresh</button>
        </div>
        <div className="muted" style={{ marginBottom: 8 }}>
          kept: {keptNodeIds.length} · hidden parents: {excludedParentIds.length}
        </div>
        {excludedParentIds.length > 0 && (
          <div className="pillRow" style={{ marginBottom: 8 }}>
            {excludedParentIds.slice(0, 8).map((id) => (
              <span className="pill" key={id} title={nodeLabel(nodesById, id)}>
                hidden {shortId(id)}
              </span>
            ))}
          </div>
        )}
        <pre className="compiledPreview">{compiledText || '(empty active context)'}</pre>
      </div>

      <div className="card inspectorCard">
        <div className="row inspectorHeader">
          <b>Context Versions</b>
          {latest && previous && (
            <button onClick={() => onLoadDiff(previous.version, latest.version)}>
              Diff latest 2
            </button>
          )}
        </div>
        <div className="versionList">
          {(versions || []).map((v) => (
            <div className="versionItem" key={v.id}>
              <div className="row" style={{ justifyContent: 'space-between', gap: 8 }}>
                <span><b>v{v.version}</b> · {v.reason}</span>
                <span className="muted">{String(v.created_at || '').slice(0, 19).replace('T', ' ')}</span>
              </div>
              <div className="muted">changed: {(v.changed_node_ids || []).length} · active: {(v.active_node_ids || []).length}</div>
              {(v.changed_node_ids || []).length > 0 && (
                <div className="pillRow" style={{ marginTop: 6 }}>
                  {v.changed_node_ids.slice(0, 6).map((id: string) => (
                    <span className="pill" key={id} title={nodeLabel(nodesById, id)}>{shortId(id)}</span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
        {versionDiff && (
          <div className="diffBox">
            <div><b>Diff</b> v{versionDiff.from_version?.version} → v{versionDiff.to_version?.version}</div>
            <div className="muted">added {versionDiff.added_ids?.length || 0} · removed {versionDiff.removed_ids?.length || 0} · moved {versionDiff.moved?.length || 0}</div>
            <div className="pillRow" style={{ marginTop: 6 }}>
              {(versionDiff.added_ids || []).slice(0, 10).map((id: string) => <span key={`a-${id}`} className="pill pill--candidate">+ {shortId(id)}</span>)}
              {(versionDiff.removed_ids || []).slice(0, 10).map((id: string) => <span key={`r-${id}`} className="pill pill--default">- {shortId(id)}</span>)}
            </div>
          </div>
        )}
      </div>

      <div className="card inspectorCard">
        <div className="row inspectorHeader">
          <b>Recovery Planner</b>
          <span className="pill">budget {budgetTokens}</span>
        </div>
        <div className="muted" style={{ marginBottom: 8 }}>
          연구 실험 코드의 dependency-closure/seed-selection 아이디어를 UI backend에 옮긴 버전입니다.
        </div>
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={3}
          placeholder="예: 이전에 분할해 둔 relocation 관련 근거를 다시 올려줘"
          style={{ width: '100%', resize: 'vertical' }}
        />
        <div className="row" style={{ marginTop: 8 }}>
          <input type="number" value={budgetTokens} onChange={(e) => setBudgetTokens(Number(e.target.value) || 1200)} style={{ width: 110 }} />
          <button onClick={() => onPlan(query, budgetTokens)} disabled={!query.trim()}>Preview plan</button>
          <button onClick={() => onApplySeeds(selectedSeeds, budgetTokens)} disabled={selectedSeeds.length === 0}>Apply selected</button>
        </div>

        {plannerResult && (
          <>
            <div className="muted" style={{ marginTop: 10 }}>
              recommended seeds: {(plannerResult.recommended_seed_ids || []).length} · estimated added nodes: {plannerResult.recommended_added_count || 0} · estimated cost: {plannerResult.recommended_cost_tokens || 0}
            </div>
            <div className="plannerList">
              {candidates.map((cand) => {
                const checked = selectedSeeds.includes(cand.seed_id)
                return (
                  <label className="plannerItem" key={cand.seed_id}>
                    <div className="row" style={{ alignItems: 'flex-start' }}>
                      <input type="checkbox" checked={checked} onChange={() => toggleSeed(cand.seed_id)} />
                      <div style={{ flex: 1 }}>
                        <div className="row" style={{ justifyContent: 'space-between', gap: 8 }}>
                          <span><b>{cand.seed_type || 'Node'}</b> {shortId(cand.seed_id)}</span>
                          <span className="muted">score {Number(cand.score || 0).toFixed(2)} · cost {cand.marginal_cost_tokens || 0} · closure {cand.closure_size || 0}</span>
                        </div>
                        <div style={{ marginTop: 4 }}>{cand.preview || '(no preview)'}</div>
                        {!!cand.closure_ids?.length && (
                          <div className="pillRow" style={{ marginTop: 6 }}>
                            {cand.closure_ids.slice(0, 8).map((id) => (
                              <span key={`${cand.seed_id}-${id}`} className="pill" title={nodeLabel(nodesById, id)}>{shortId(id)}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </label>
                )
              })}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
