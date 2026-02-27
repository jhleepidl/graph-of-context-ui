import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../api'

type Strategy = 'auto' | 'tagged' | 'heading' | 'bullets' | 'paragraph' | 'sentences' | 'custom'

type Props = {
  nodeId: string
  threadId: string | null
  ctxId: string | null
  onClose: () => void
  onAfterMutation: () => Promise<void>
  mode?: 'modal' | 'drawer'
}

type PartItem = {
  id: string
  type: string
  text: string
  created_at?: string
  index: number
  kind: string
}

function shortId(id: string): string {
  return id.slice(0, 6)
}

function toInt(value: string): number | null {
  const v = Number(value)
  if (!Number.isFinite(v)) return null
  return Math.max(1, Math.floor(v))
}

export default function NodeDetailModal({ nodeId, threadId, ctxId, onClose, onAfterMutation, mode = 'modal' }: Props) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')
  const [nodeData, setNodeData] = useState<any | null>(null)
  const [editableText, setEditableText] = useState('')
  const [savingPatch, setSavingPatch] = useState(false)

  const [selectedPartIds, setSelectedPartIds] = useState<string[]>([])
  const [replaceParentForActivation, setReplaceParentForActivation] = useState(false)

  const [strategy, setStrategy] = useState<Strategy>('auto')
  const [customText, setCustomText] = useState('')
  const [targetChars, setTargetChars] = useState('900')
  const [maxChars, setMaxChars] = useState('2000')
  const [inheritReplyTo, setInheritReplyTo] = useState(true)
  const [replaceInActive, setReplaceInActive] = useState(false)

  const loadNode = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const out = await api.getNode(nodeId)
      setNodeData(out)
      setEditableText(out?.text || '')
      const partEdges: any[] = out.part_edges || []
      const nextSelected = partEdges.map((e) => e.to_id).filter(Boolean)
      setSelectedPartIds(nextSelected)
    } catch (e: any) {
      setError(e?.message || String(e))
    } finally {
      setLoading(false)
    }
  }, [nodeId])

  useEffect(() => {
    loadNode()
  }, [loadNode])

  const parts = useMemo(() => {
    if (!nodeData) return [] as PartItem[]
    const partById = new Map<string, any>((nodeData.parts || []).map((p: any) => [p.id, p]))
    const edges: any[] = nodeData.part_edges || []
    return edges.map((e) => {
      const meta = (() => {
        try {
          return JSON.parse(e.payload_json || '{}')
        } catch {
          return {}
        }
      })()
      const p = partById.get(e.to_id)
      return {
        id: e.to_id,
        type: p?.type || 'Unknown',
        text: p?.text || '',
        created_at: p?.created_at,
        index: Number(meta.index || 0),
        kind: String(meta.kind || ''),
      }
    })
  }, [nodeData])

  const partCount = parts.length

  function togglePart(id: string) {
    setSelectedPartIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  async function handleActivateSelectedParts() {
    if (!ctxId) {
      setStatus('활성화할 Context Set이 없습니다.')
      return
    }
    if (selectedPartIds.length === 0) {
      setStatus('선택된 part가 없습니다.')
      return
    }
    try {
      if (replaceParentForActivation) {
        await api.deactivate(ctxId, [nodeId])
      }
      await api.activate(ctxId, selectedPartIds)
      await onAfterMutation()
      setStatus(`${selectedPartIds.length}개 part를 Active에 반영했습니다.`)
    } catch (e: any) {
      setStatus(`실패: ${e?.message || String(e)}`)
    }
  }

  async function handleSplit() {
    if (!threadId) {
      setStatus('thread가 선택되지 않았습니다.')
      return
    }
    try {
      setStatus('')
      const payload = {
        strategy,
        custom_text: strategy === 'custom' ? customText : null,
        child_type: null,
        context_set_id: ctxId,
        replace_in_active: replaceInActive,
        inherit_reply_to: inheritReplyTo,
        target_chars: toInt(targetChars),
        max_chars: toInt(maxChars),
      }
      const out = await api.splitNode(nodeId, payload)
      await onAfterMutation()
      await loadNode()
      setStatus(`Split 완료: ${out.created_ids?.length || 0}개 생성 (${out.strategy_used})`)
    } catch (e: any) {
      setStatus(`실패: ${e?.message || String(e)}`)
    }
  }

  async function handleSaveNodeText() {
    try {
      setSavingPatch(true)
      setStatus('')
      await api.patchNode(nodeId, { text: editableText })
      await onAfterMutation()
      await loadNode()
      setStatus('Node text 저장 완료')
    } catch (e: any) {
      setStatus(`저장 실패: ${e?.message || String(e)}`)
    } finally {
      setSavingPatch(false)
    }
  }

  const body = (
    <>
      <div className="row modalHeader">
        <h3 style={{ margin: 0 }}>Node Detail / Split</h3>
        <button onClick={onClose}>Close</button>
      </div>
      {loading && <div className="muted">Loading...</div>}
      {error && <div className="muted" style={{ color: '#b91c1c' }}>{error}</div>}
      {nodeData && (
        <>
          <div className="muted">id={shortId(nodeData.id)} type={nodeData.type}</div>
          <div className="muted">{nodeData.created_at}</div>
          <textarea
            value={editableText}
            onChange={(e) => setEditableText(e.target.value)}
            style={{ height: 180 }}
          />
          <div className="row">
            <button className="primary" onClick={handleSaveNodeText} disabled={savingPatch}>
              {savingPatch ? 'Saving...' : 'Save'}
            </button>
          </div>

          <h4 style={{ marginBottom: 6 }}>Parts ({partCount})</h4>
          {partCount === 0 && <div className="muted">아직 분할된 part가 없습니다.</div>}
          {partCount > 0 && (
            <>
              <div className="row">
                <label className="muted">
                  <input
                    type="checkbox"
                    checked={replaceParentForActivation}
                    onChange={(e) => setReplaceParentForActivation(e.target.checked)}
                  /> Replace parent in Active
                </label>
                <button onClick={handleActivateSelectedParts}>Activate selected parts</button>
              </div>
              <div className="modalPartList">
                {parts.map((p) => (
                  <label key={p.id} className="card" style={{ display: 'block' }}>
                    <div className="row" style={{ marginBottom: 4 }}>
                      <input
                        type="checkbox"
                        checked={selectedPartIds.includes(p.id)}
                        onChange={() => togglePart(p.id)}
                      />
                      <span className="pill">{p.type}</span>
                      <span className="muted">#{p.index} {p.kind ? `(${p.kind})` : ''} {shortId(p.id)}</span>
                    </div>
                    <div style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>{(p.text || '').slice(0, 280) || '(empty)'}</div>
                  </label>
                ))}
              </div>
            </>
          )}

          <h4 style={{ marginBottom: 6 }}>Split</h4>
          <div className="row">
            <label className="muted">
              strategy:
              <select value={strategy} onChange={(e) => setStrategy(e.target.value as Strategy)} style={{ marginLeft: 6 }}>
                <option value="auto">auto</option>
                <option value="tagged">tagged</option>
                <option value="heading">heading</option>
                <option value="bullets">bullets</option>
                <option value="paragraph">paragraph</option>
                <option value="sentences">sentences</option>
                <option value="custom">custom</option>
              </select>
            </label>
          </div>
          {strategy === 'custom' && (
            <textarea
              value={customText}
              onChange={(e) => setCustomText(e.target.value)}
              placeholder="blank line 기준으로 chunk를 나눕니다."
              style={{ height: 120 }}
            />
          )}
          <div className="row">
            <label className="muted">
              target chars:
              <input
                value={targetChars}
                onChange={(e) => setTargetChars(e.target.value)}
                style={{ marginLeft: 6, width: 90 }}
              />
            </label>
            <label className="muted">
              max chars:
              <input
                value={maxChars}
                onChange={(e) => setMaxChars(e.target.value)}
                style={{ marginLeft: 6, width: 90 }}
              />
            </label>
          </div>
          <div className="row">
            <label className="muted">
              <input
                type="checkbox"
                checked={inheritReplyTo}
                onChange={(e) => setInheritReplyTo(e.target.checked)}
              /> inherit_reply_to
            </label>
            <label className="muted">
              <input
                type="checkbox"
                checked={replaceInActive}
                onChange={(e) => setReplaceInActive(e.target.checked)}
              /> replace_in_active
            </label>
          </div>
          <div className="row">
            <button className="primary" onClick={handleSplit}>Split</button>
          </div>
        </>
      )}
      {status && <div className="muted">{status}</div>}
    </>
  )

  if (mode === 'drawer') {
    return (
      <div className="nodeDrawer">
        <div className="modalCard nodeDrawerCard">{body}</div>
      </div>
    )
  }

  return (
    <div className="modalOverlay" onClick={onClose}>
      <div className="modalCard" onClick={(e) => e.stopPropagation()}>
        {body}
      </div>
    </div>
  )
}
