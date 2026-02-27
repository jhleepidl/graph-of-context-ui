import React, { useEffect, useMemo, useState } from 'react'
import WorkspaceApp from './pages/WorkspaceApp'
import AdminLoginPage from './pages/AdminLoginPage'
import GuestRequestServicePage from './pages/GuestRequestServicePage'
import AdminServiceRequestsPage from './pages/AdminServiceRequestsPage'
import AgentsPage from './pages/AgentsPage'
import {
  clearStoredAdminKey,
  getStoredAdminKey,
  setStoredBearerToken,
} from './api'

function normalizePath(pathname: string): string {
  if (!pathname) return '/'
  if (pathname === '/') return '/'
  return pathname.endsWith('/') ? pathname.slice(0, -1) : pathname
}

function captureTokenFromHash(): void {
  if (typeof window === 'undefined') return
  const rawHash = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : window.location.hash
  if (!rawHash) return

  const hashParams = new URLSearchParams(rawHash)
  const token = (hashParams.get('token') || '').trim()
  if (!token) return

  setStoredBearerToken(token)
  hashParams.delete('token')
  const nextHash = hashParams.toString()
  const nextUrl = `${window.location.pathname}${window.location.search}${nextHash ? `#${nextHash}` : ''}`
  window.history.replaceState(null, '', nextUrl)
}

export default function App() {
  const [path, setPath] = useState<string>(() => normalizePath(window.location.pathname))
  const [hasAdminKey, setHasAdminKey] = useState<boolean>(() => !!getStoredAdminKey())

  useEffect(() => {
    captureTokenFromHash()

    function handlePopState() {
      setPath(normalizePath(window.location.pathname))
      setHasAdminKey(!!getStoredAdminKey())
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  const route = useMemo(() => {
    if (path === '/admin/login') return 'admin_login'
    if (path === '/guest/request-service') return 'guest_request_service'
    if (path === '/admin/service-requests') return 'admin_service_requests'
    if (path === '/agents') return 'agents'
    return 'workspace'
  }, [path])

  function navigate(nextPath: string) {
    const normalized = normalizePath(nextPath)
    if (normalized === path) return
    window.history.pushState(null, '', normalized)
    setPath(normalized)
    setHasAdminKey(!!getStoredAdminKey())
  }

  function handleAdminAuthChanged() {
    setHasAdminKey(!!getStoredAdminKey())
  }

  function handleAdminLogout() {
    clearStoredAdminKey()
    setHasAdminKey(false)
    if (route === 'admin_service_requests') {
      navigate('/admin/login')
    }
  }

  return (
    <div className="routeShell">
      <header className="topNav">
        <div className="topNavLeft">
          <button className={route === 'workspace' ? 'primary' : ''} onClick={() => navigate('/')}>GoC</button>
          <button className={route === 'agents' ? 'primary' : ''} onClick={() => navigate('/agents')}>Agents</button>
          <button className={route === 'guest_request_service' ? 'primary' : ''} onClick={() => navigate('/guest/request-service')}>Request Service Key</button>
          <button className={route === 'admin_login' ? 'primary' : ''} onClick={() => navigate('/admin/login')}>Admin Login</button>
          {hasAdminKey && (
            <button className={route === 'admin_service_requests' ? 'primary' : ''} onClick={() => navigate('/admin/service-requests')}>Admin Requests</button>
          )}
        </div>
        <div className="topNavRight">
          {hasAdminKey ? <span className="pill">Admin ON</span> : <span className="pill">Admin OFF</span>}
          {hasAdminKey && <button onClick={handleAdminLogout}>Admin Logout</button>}
        </div>
      </header>

      <main className={route === 'workspace' ? 'routeMain routeMainWorkspace' : 'routeMain'}>
        {route === 'workspace' && <WorkspaceApp />}
        {route === 'agents' && <AgentsPage onNavigate={navigate} />}
        {route === 'admin_login' && (
          <AdminLoginPage onAdminAuthChanged={handleAdminAuthChanged} onNavigate={navigate} />
        )}
        {route === 'guest_request_service' && (
          <GuestRequestServicePage onNavigate={navigate} />
        )}
        {route === 'admin_service_requests' && (
          <AdminServiceRequestsPage hasAdminKey={hasAdminKey} onNavigate={navigate} />
        )}
      </main>
    </div>
  )
}
