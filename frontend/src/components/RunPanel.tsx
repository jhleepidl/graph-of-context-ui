import React, { useState } from 'react'

type Props = {
  onRun: (msg: string) => Promise<string>
}

export default function RunPanel({ onRun }: Props) {
  const [msg, setMsg] = useState('')
  const [resp, setResp] = useState<string>('')

  return (
    <div>
      <h3>Run</h3>
      <textarea value={msg} onChange={(e) => setMsg(e.target.value)} placeholder="다음 질문/요청을 입력" />
      <div className="row">
        <button className="primary" onClick={async () => {
          const m = msg.trim()
          if (!m) return
          const r = await onRun(m)
          setResp(r)
          setMsg('')
        }}>Run with Active Context</button>
      </div>
      <h3>Last Response</h3>
      <pre style={{ whiteSpace: 'pre-wrap' }}>{resp}</pre>
    </div>
  )
}
