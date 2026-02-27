import React, { useMemo, useState } from 'react'
import { clearStoredAdminKey, getStoredAdminKey, setStoredAdminKey } from '../api'

type Props = {
  onAdminAuthChanged: () => void
  onNavigate: (path: string) => void
}

function maskKey(key: string): string {
  if (!key) return ''
  if (key.length <= 8) return '********'
  return `${key.slice(0, 4)}...${key.slice(-4)}`
}

export default function AdminLoginPage({ onAdminAuthChanged, onNavigate }: Props) {
  const [inputKey, setInputKey] = useState('')
  const [status, setStatus] = useState('')
  const currentKey = useMemo(() => getStoredAdminKey(), [status])

  function handleSave() {
    const clean = inputKey.trim()
    if (!clean) {
      setStatus('Admin Key를 입력하세요.')
      return
    }
    setStoredAdminKey(clean)
    setInputKey('')
    setStatus('Admin Key가 현재 세션에 저장되었습니다.')
    onAdminAuthChanged()
  }

  function handleLogout() {
    clearStoredAdminKey()
    setStatus('Admin Key를 세션에서 제거했습니다.')
    onAdminAuthChanged()
  }

  return (
    <div className="routePage">
      <div className="routeCard">
        <h2>Admin Login</h2>
        <p className="muted">서버 세션 없이, 브라우저 sessionStorage의 Admin Key를 헤더로 전송합니다.</p>
        <label className="routeLabel">
          Admin Key
          <input
            type="password"
            value={inputKey}
            onChange={(e) => setInputKey(e.target.value)}
            placeholder="Enter admin key"
          />
        </label>
        <div className="row">
          <button className="primary" onClick={handleSave}>Save Session Key</button>
          <button onClick={handleLogout}>Logout</button>
          <button onClick={() => onNavigate('/admin/service-requests')}>Go Requests</button>
        </div>
        <div className="muted">Current session key: {currentKey ? maskKey(currentKey) : '(none)'}</div>
        {status && <div className="routeStatus">{status}</div>}
      </div>
    </div>
  )
}
