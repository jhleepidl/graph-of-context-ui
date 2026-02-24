import React, { useState } from 'react'

function pillClassForType(type?: string): string {
  if (type === 'Resource') return 'pill--resource'
  if (type === 'Fold') return 'pill--fold'
  if (type === 'Decision') return 'pill--decision'
  if (type === 'Assumption') return 'pill--assumption'
  if (type === 'Plan') return 'pill--plan'
  if (type === 'ContextCandidate') return 'pill--candidate'
  return 'pill--default'
}

type Item = { node_id: string, score: number, node_type: string, snippet: string }

type Props = {
  onSearch: (q: string) => Promise<Item[]>
  onActivate: (nodeId: string) => void
}

export default function SearchPanel({ onSearch, onActivate }: Props) {
  const [q, setQ] = useState('')
  const [items, setItems] = useState<Item[]>([])
  const [err, setErr] = useState<string>('')

  return (
    <div>
      <h3>Search</h3>
      <div className="row">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="context 검색" style={{ flex: 1, padding: 8, borderRadius: 10, border: '1px solid #e5e7eb' }} />
        <button onClick={async () => {
          setErr('')
          try {
            const res = await onSearch(q.trim())
            setItems(res)
          } catch (e: any) {
            setErr(String(e.message || e))
          }
        }}>Go</button>
      </div>
      {err && <div className="muted" style={{ color: '#ef4444' }}>{err}</div>}
      {items.map(it => (
        <div key={it.node_id} className="card">
          <div className="muted">score: {it.score.toFixed(3)}</div>
          <div><span className={`pill pillType ${pillClassForType(it.node_type)}`}>{it.node_type}</span> {it.snippet}</div>
          <div className="row" style={{ marginTop: 6 }}>
            <button onClick={() => onActivate(it.node_id)}>Add to Active</button>
          </div>
        </div>
      ))}
    </div>
  )
}
