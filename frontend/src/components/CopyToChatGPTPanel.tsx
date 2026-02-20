import React, { useMemo, useState } from 'react'
import { api } from '../api'

type ContextNode = {
  id: string
  type?: string | null
  text?: string | null
  created_at?: string | null
}

type Props = {
  activeNodes: ContextNode[]
  threadId: string | null
  ctxId: string | null
  onAfterMutation: () => Promise<void>
}

const LANGUAGE_LOCK = '중요: 아래 포맷/규칙은 영어로 쓰여있지만, 너의 답변 내용은 반드시 한국어로 작성해라.'

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

function byCreatedAtAsc(a: ContextNode, b: ContextNode): number {
  const av = a.created_at || ''
  const bv = b.created_at || ''
  if (av < bv) return -1
  if (av > bv) return 1
  return 0
}

type TaggedSection = {
  tag: 'FINAL' | 'DECISIONS' | 'ASSUMPTIONS' | 'PLAN' | 'CONTEXT_CANDIDATES'
  text: string
}

const TAGS = ['FINAL', 'DECISIONS', 'ASSUMPTIONS', 'PLAN', 'CONTEXT_CANDIDATES'] as const
const TAG_REGEX = /\[(FINAL|DECISIONS|ASSUMPTIONS|PLAN|CONTEXT_CANDIDATES)\]\s*([\s\S]*?)(?=\n\[(?:FINAL|DECISIONS|ASSUMPTIONS|PLAN|CONTEXT_CANDIDATES)\]|\s*$)/g

function parseTaggedSections(raw: string): TaggedSection[] {
  const out: TaggedSection[] = []
  TAG_REGEX.lastIndex = 0
  for (const m of raw.matchAll(TAG_REGEX)) {
    const tag = m[1] as TaggedSection['tag']
    if (!TAGS.includes(tag)) continue
    const text = (m[2] || '').trim()
    if (!text) continue
    out.push({ tag, text })
  }
  return out
}

export default function CopyToChatGPTPanel({ activeNodes, threadId, ctxId, onAfterMutation }: Props) {
  const [userRequest, setUserRequest] = useState('')
  const [status, setStatus] = useState('')
  const [userRequestStatus, setUserRequestStatus] = useState('')
  const [showPreview, setShowPreview] = useState(false)
  const [pasteText, setPasteText] = useState('')
  const [pasteStatus, setPasteStatus] = useState('')
  const [manualContextText, setManualContextText] = useState('')
  const [manualStatus, setManualStatus] = useState('')

  const contextSection = useMemo(() => {
    const sorted = [...activeNodes].sort(byCreatedAtAsc)
    if (sorted.length === 0) {
      return '(active context is empty)'
    }
    return sorted
      .map((n) => {
        const body = (n.text || '').trim() || '(empty)'
        return `[NODE ${shortId(n.id)} type=${n.type || 'Unknown'}]\n${body}`
      })
      .join('\n\n')
  }, [activeNodes])

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

  async function createAndActivateMessage(role: 'user' | 'assistant', text: string): Promise<void> {
    if (!threadId) {
      throw new Error('thread가 선택되지 않았습니다.')
    }
    const node = await api.addMessage(threadId, role, text)
    if (ctxId) {
      await api.activate(ctxId, [node.id])
    }
  }

  async function copyPrompt() {
    setShowPreview(true)
    try {
      await copyWithFallback(builtPrompt)
      setStatus('복사됨')
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
      await createAndActivateMessage('user', req)
      await onAfterMutation()
      setUserRequestStatus('USER REQUEST를 Context 노드로 추가했습니다.')
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
    try {
      const parsed = parseTaggedSections(raw)
      const sections = parsed.length > 0 ? parsed : [{ tag: 'FINAL', text: raw }]
      for (const s of sections) {
        await createAndActivateMessage('assistant', `[${s.tag}]\n${s.text}`)
      }
      await onAfterMutation()
      setPasteStatus(`${sections.length}개 노드를 생성하고 Active Context에 추가했습니다.`)
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
        <button className="primary" onClick={copyPrompt}>Copy Prompt</button>
        <button onClick={handleAddUserRequestContext}>Add USER REQUEST to Context</button>
        {status && <div className="muted">{status}</div>}
      </div>
      {userRequestStatus && <div className="muted">{userRequestStatus}</div>}

      <h3>Paste from ChatGPT</h3>
      <textarea
        value={pasteText}
        onChange={(e) => setPasteText(e.target.value)}
        placeholder="ChatGPT 응답을 붙여넣으세요. [FINAL]/[DECISIONS]... 형식이면 섹션별로 노드를 만듭니다."
      />
      <div className="row">
        <button onClick={handlePasteFromChatGPT}>Paste from ChatGPT</button>
        {pasteStatus && <div className="muted">{pasteStatus}</div>}
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

      {showPreview && (
        <>
          <h3>Prompt Preview</h3>
          <textarea
            readOnly
            value={builtPrompt}
            style={{ height: 260 }}
          />
        </>
      )}
    </div>
  )
}
