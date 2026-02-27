import React, { useState } from 'react'
import { api } from '../api'
import { copyText } from '../utils/clipboard'

type Props = {
  onNavigate: (path: string) => void
}

export default function GuestRequestServicePage({ onNavigate }: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<any | null>(null)
  const [copyStatus, setCopyStatus] = useState('')

  async function submit() {
    const cleanName = name.trim()
    if (!cleanName) {
      setError('서비스 이름을 입력하세요.')
      return
    }
    setSubmitting(true)
    setError('')
    setResult(null)
    try {
      const out = await api.createServiceRequest(cleanName, description.trim() || null)
      setResult(out?.service_request || null)
      setCopyStatus('')
    } catch (e: any) {
      setError(e?.message || String(e))
    } finally {
      setSubmitting(false)
    }
  }

  async function copyRequestId() {
    const id = result?.id
    if (!id) return
    const ok = await copyText(id)
    setCopyStatus(ok ? 'request_id copied' : 'copy failed (브라우저 권한/보안 컨텍스트 확인)')
  }

  return (
    <div className="routePage">
      <div className="routeCard">
        <h2>Request Service Key</h2>
        <p className="muted">인증 없이 서비스 키 발급 신청을 생성합니다. 승인 후 Admin이 ServiceKey를 발급합니다.</p>

        <label className="routeLabel">
          Service Name
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. ddalggak" />
        </label>

        <label className="routeLabel">
          Description
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="usage or owner info" />
        </label>

        <div className="row">
          <button className="primary" onClick={submit} disabled={submitting}>{submitting ? 'Submitting...' : 'Submit Request'}</button>
          <button onClick={() => onNavigate('/')}>Go GoC</button>
        </div>

        {error && <div className="routeStatus routeStatusError">{error}</div>}
        {result && (
          <div className="routeResult">
            <div><b>request_id:</b> {result.id}</div>
            <div><b>status:</b> {result.status}</div>
            <div><b>created_at:</b> {result.created_at}</div>
            <div className="row" style={{ marginTop: 8 }}>
              <button onClick={copyRequestId}>Copy request_id</button>
            </div>
            {copyStatus && <div className="muted">{copyStatus}</div>}
          </div>
        )}
      </div>
    </div>
  )
}
