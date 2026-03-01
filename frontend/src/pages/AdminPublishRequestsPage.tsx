import React, { useEffect, useMemo, useState } from 'react'
import { api } from '../api'

type Props = {
  hasAdminKey: boolean
  onNavigate: (path: string) => void
}

type StatusFilter = 'all' | 'pending' | 'approved' | 'rejected'

function asString(v: unknown): string {
  if (typeof v === 'string') return v.trim()
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  return ''
}

export default function AdminPublishRequestsPage({ hasAdminKey, onNavigate }: Props) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('pending')
  const [rows, setRows] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [actioningId, setActioningId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [status, setStatus] = useState('')

  useEffect(() => {
    if (!hasAdminKey) {
      onNavigate('/admin/login')
      return
    }
    void reload()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasAdminKey, statusFilter])

  const pendingCount = useMemo(() => rows.filter((row) => row.status === 'pending').length, [rows])

  async function reload() {
    if (!hasAdminKey) return
    setLoading(true)
    setError('')
    try {
      const out = await api.adminPublishRequests(statusFilter)
      setRows(Array.isArray(out?.items) ? out.items : [])
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
      setRows([])
    } finally {
      setLoading(false)
    }
  }

  async function approveRequest(requestId: string) {
    setActioningId(requestId)
    setError('')
    setStatus('')
    try {
      const out = await api.adminApprovePublishRequest(requestId)
      const blueprintId = asString(out?.blueprint_id)
      const publicNodeId = asString(out?.public_node_id)
      setStatus(`승인 완료: blueprint_id=${blueprintId || '-'}, public_node_id=${publicNodeId || '-'} (Library에서 확인)`)
      await reload()
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
    } finally {
      setActioningId(null)
    }
  }

  async function rejectRequest(requestId: string) {
    setActioningId(requestId)
    setError('')
    setStatus('')
    try {
      await api.adminRejectPublishRequest(requestId)
      setStatus(`거절 완료: ${requestId}`)
      await reload()
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
    } finally {
      setActioningId(null)
    }
  }

  if (!hasAdminKey) return null

  return (
    <div className="routePage">
      <div className="routeCard">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h2 style={{ margin: 0 }}>Admin Publish Requests</h2>
          <div className="row" style={{ marginBottom: 0 }}>
            <span className="pill">pending: {pendingCount}</span>
            <button onClick={() => onNavigate('/library')}>Go Library</button>
            <button onClick={() => void reload()} disabled={loading}>
              {loading ? 'Loading...' : 'Refresh'}
            </button>
          </div>
        </div>

        <div className="row">
          <label className="muted">
            status:
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
              style={{ marginLeft: 8 }}
            >
              <option value="all">all</option>
              <option value="pending">pending</option>
              <option value="approved">approved</option>
              <option value="rejected">rejected</option>
            </select>
          </label>
        </div>

        {error && <div className="routeStatus routeStatusError">{error}</div>}
        {status && <div className="routeStatus">{status}</div>}

        <div className="routeTableWrap">
          <table className="routeTable">
            <thead>
              <tr>
                <th>request_id</th>
                <th>service_id</th>
                <th>agent_id</th>
                <th>title</th>
                <th>created_at</th>
                <th>status</th>
                <th>source_node_id</th>
                <th>snippet</th>
                <th>actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => {
                const preview = (row?.source_preview && typeof row.source_preview === 'object')
                  ? (row.source_preview as Record<string, unknown>)
                  : {}
                const requestId = asString(row?.id)
                const isPending = asString(row?.status) === 'pending'
                return (
                  <tr key={requestId || `row-${idx}`}>
                    <td>{requestId || '-'}</td>
                    <td>{asString(row?.service_id) || '-'}</td>
                    <td>{asString(preview.agent_id) || '-'}</td>
                    <td>{asString(preview.title) || '-'}</td>
                    <td>{asString(row?.created_at) || '-'}</td>
                    <td>{asString(row?.status) || '-'}</td>
                    <td>{asString(row?.source_node_id) || '-'}</td>
                    <td style={{ maxWidth: 320 }}>
                      {asString(preview.snippet).replace(/\s+/g, ' ').slice(0, 150) || '-'}
                    </td>
                    <td>
                      {isPending ? (
                        <div className="row" style={{ marginBottom: 0 }}>
                          <button
                            className="primary"
                            onClick={() => void approveRequest(requestId)}
                            disabled={actioningId === requestId}
                          >
                            {actioningId === requestId ? 'Approving...' : 'Approve'}
                          </button>
                          <button
                            className="danger"
                            onClick={() => void rejectRequest(requestId)}
                            disabled={actioningId === requestId}
                          >
                            {actioningId === requestId ? 'Rejecting...' : 'Reject'}
                          </button>
                        </div>
                      ) : (
                        <span className="muted">-</span>
                      )}
                    </td>
                  </tr>
                )
              })}
              {rows.length === 0 && !loading && (
                <tr>
                  <td colSpan={9}>
                    <span className="muted">표시할 publish request가 없습니다.</span>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
