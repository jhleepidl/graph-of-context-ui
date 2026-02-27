import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api'

type Props = {
  hasAdminKey: boolean
  onNavigate: (path: string) => void
}

type StatusFilter = 'all' | 'pending' | 'approved' | 'rejected'

export default function AdminServiceRequestsPage({ hasAdminKey, onNavigate }: Props) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('pending')
  const [requests, setRequests] = useState<any[]>([])
  const [services, setServices] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [revealedKey, setRevealedKey] = useState('')
  const [revealedTitle, setRevealedTitle] = useState('')

  useEffect(() => {
    if (!hasAdminKey) {
      onNavigate('/admin/login')
      return
    }
    void reload()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasAdminKey, statusFilter])

  const pendingCount = useMemo(() => requests.filter((r) => r.status === 'pending').length, [requests])

  async function reload() {
    if (!hasAdminKey) return
    setLoading(true)
    setError('')
    try {
      const [reqOut, svcOut] = await Promise.all([
        api.adminServiceRequests(statusFilter),
        api.adminServices(),
      ])
      setRequests(reqOut?.items || [])
      setServices(svcOut?.items || [])
    } catch (e: any) {
      setError(e?.message || String(e))
    } finally {
      setLoading(false)
    }
  }

  async function approveRequest(requestId: string) {
    try {
      setError('')
      const out = await api.adminApproveServiceRequest(requestId)
      setRevealedTitle(`Approved request ${requestId}`)
      setRevealedKey(out?.api_key || '')
      await reload()
    } catch (e: any) {
      setError(e?.message || String(e))
    }
  }

  async function rotateService(serviceId: string) {
    try {
      setError('')
      const out = await api.adminRotateService(serviceId)
      setRevealedTitle(`Rotated service ${serviceId}`)
      setRevealedKey(out?.api_key || '')
      await reload()
    } catch (e: any) {
      setError(e?.message || String(e))
    }
  }

  async function revokeService(serviceId: string) {
    if (!window.confirm(`Revoke service ${serviceId}?`)) return
    try {
      setError('')
      await api.adminRevokeService(serviceId)
      await reload()
    } catch (e: any) {
      setError(e?.message || String(e))
    }
  }

  async function copyRevealedKey() {
    if (!revealedKey) return
    try {
      await navigator.clipboard.writeText(revealedKey)
    } catch {
      // ignore clipboard failures
    }
  }

  if (!hasAdminKey) return null

  return (
    <div className="routePage">
      <div className="routeCard">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h2 style={{ margin: 0 }}>Admin Service Requests</h2>
          <div className="row" style={{ marginBottom: 0 }}>
            <span className="pill">pending: {pendingCount}</span>
            <button onClick={() => onNavigate('/admin/login')}>Admin Login</button>
            <button onClick={() => void reload()} disabled={loading}>{loading ? 'Loading...' : 'Refresh'}</button>
          </div>
        </div>

        <div className="row">
          <label className="muted">
            status:
            <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as StatusFilter)} style={{ marginLeft: 8 }}>
              <option value="all">all</option>
              <option value="pending">pending</option>
              <option value="approved">approved</option>
              <option value="rejected">rejected</option>
            </select>
          </label>
        </div>

        {error && <div className="routeStatus routeStatusError">{error}</div>}

        <div className="routeTableWrap">
          <table className="routeTable">
            <thead>
              <tr>
                <th>request_id</th>
                <th>name</th>
                <th>description</th>
                <th>status</th>
                <th>created_at</th>
                <th>service_id</th>
                <th>actions</th>
              </tr>
            </thead>
            <tbody>
              {requests.map((row) => (
                <tr key={row.id}>
                  <td>{row.id}</td>
                  <td>{row.name}</td>
                  <td>{row.description || '-'}</td>
                  <td>{row.status}</td>
                  <td>{row.created_at}</td>
                  <td>{row.approved_service_id || '-'}</td>
                  <td>
                    {row.status === 'pending' && (
                      <button className="primary" onClick={() => void approveRequest(row.id)}>Approve</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h3 style={{ marginTop: 20 }}>Services</h3>
        <div className="routeTableWrap">
          <table className="routeTable">
            <thead>
              <tr>
                <th>service_id</th>
                <th>name</th>
                <th>status</th>
                <th>created_at</th>
                <th>actions</th>
              </tr>
            </thead>
            <tbody>
              {services.map((svc) => (
                <tr key={svc.id}>
                  <td>{svc.id}</td>
                  <td>{svc.name}</td>
                  <td>{svc.status}</td>
                  <td>{svc.created_at}</td>
                  <td>
                    <div className="row" style={{ marginBottom: 0 }}>
                      <button onClick={() => void rotateService(svc.id)} disabled={svc.status !== 'active'}>Rotate</button>
                      <button className="danger" onClick={() => void revokeService(svc.id)} disabled={svc.status !== 'active'}>Revoke</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {revealedKey && (
        <div className="modalOverlay" onClick={() => setRevealedKey('')}>
          <div className="modalCard" onClick={(e) => e.stopPropagation()} style={{ width: 'min(720px, 100%)' }}>
            <h3 style={{ marginTop: 0 }}>{revealedTitle || 'API Key'}</h3>
            <p className="muted">이 키는 재표시되지 않습니다. 안전한 저장소에 즉시 보관하세요.</p>
            <textarea readOnly value={revealedKey} style={{ height: 120 }} />
            <div className="row">
              <button className="primary" onClick={() => void copyRevealedKey()}>Copy</button>
              <button onClick={() => setRevealedKey('')}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
