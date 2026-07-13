import React, { Suspense, lazy, useEffect, useMemo, useState } from 'react'
const WorkspaceApp = lazy(() => import('./pages/WorkspaceApp'))
const AdminLoginPage = lazy(() => import('./pages/AdminLoginPage'))
const GuestRequestServicePage = lazy(() => import('./pages/GuestRequestServicePage'))
const AdminServiceRequestsPage = lazy(() => import('./pages/AdminServiceRequestsPage'))
const AgentsPage = lazy(() => import('./pages/AgentsPage'))
const ToolsPage = lazy(() => import('./pages/ToolsPage'))
const LibraryPage = lazy(() => import('./pages/LibraryPage'))
const AdminPublishRequestsPage = lazy(() => import('./pages/AdminPublishRequestsPage'))
import {
  clearStoredAdminKey,
  getStoredAdminKey,
  setStoredBearerToken,
} from './api'

function normalizePathname(pathname: string): string {
  if (!pathname) return '/'
  if (pathname === '/') return '/'
  return pathname.endsWith('/') ? pathname.slice(0, -1) : pathname
}

function parseRouteTarget(target: string): { pathname: string; search: string } {
  if (typeof window === 'undefined') {
    return {
      pathname: normalizePathname(target || '/'),
      search: '',
    }
  }
  const resolved = new URL(target || '/', window.location.origin)
  return {
    pathname: normalizePathname(resolved.pathname),
    search: resolved.search || '',
  }
}


function pickWorkspaceSearch(currentSearch: string, lastWorkspaceSearch: string): string {
  if (currentSearch && /(?:^|[?&])(thread|ctx)=/.test(currentSearch)) return currentSearch
  if (lastWorkspaceSearch && /(?:^|[?&])(thread|ctx)=/.test(lastWorkspaceSearch)) return lastWorkspaceSearch
  return ''
}


function RouteFallback({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="routePage">
      <div className="routeCard" style={{ maxWidth: 720 }}>
        <p className="muted" style={{ margin: 0 }}>{label}</p>
      </div>
    </div>
  )
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
  const [pathname, setPathname] = useState<string>(() => normalizePathname(window.location.pathname))
  const [search, setSearch] = useState<string>(() => window.location.search || '')
  const [hasAdminKey, setHasAdminKey] = useState<boolean>(() => !!getStoredAdminKey())
  const [lastWorkspaceSearch, setLastWorkspaceSearch] = useState<string>(() => window.location.search || '')

  useEffect(() => {
    captureTokenFromHash()

    function handlePopState() {
      const nextPath = normalizePathname(window.location.pathname)
      const nextSearch = window.location.search || ''
      if (nextPath === '/' && nextSearch) setLastWorkspaceSearch(nextSearch)
      setPathname(nextPath)
      setSearch(nextSearch)
      setHasAdminKey(!!getStoredAdminKey())
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  const route = useMemo(() => {
    if (pathname === '/admin/login') return 'admin_login'
    if (pathname === '/guest/request-service') return 'guest_request_service'
    if (pathname === '/admin/service-requests') return 'admin_service_requests'
    if (pathname === '/admin/publish-requests') return 'admin_publish_requests'
    if (pathname === '/agents') return 'agents'
    if (pathname === '/tools') return 'tools'
    if (pathname === '/library') return 'library'
    return 'workspace'
  }, [pathname])

  function navigate(nextPath: string) {
    const next = parseRouteTarget(nextPath)
    let nextSearch = next.search
    if (pathname === '/' && search) setLastWorkspaceSearch(search)
    if ((next.pathname === '/agents' || next.pathname === '/tools' || next.pathname === '/library') && !nextSearch) {
      nextSearch = pickWorkspaceSearch(search, lastWorkspaceSearch)
    }
    if (next.pathname === '/' && !nextSearch) {
      nextSearch = pickWorkspaceSearch(search, lastWorkspaceSearch)
    }
    if (next.pathname === '/' && nextSearch) setLastWorkspaceSearch(nextSearch)
    if (next.pathname === pathname && nextSearch === search) return
    window.history.pushState(null, '', `${next.pathname}${nextSearch}`)
    setPathname(next.pathname)
    setSearch(nextSearch)
    setHasAdminKey(!!getStoredAdminKey())
  }

  function handleAdminAuthChanged() {
    setHasAdminKey(!!getStoredAdminKey())
  }

  function handleAdminLogout() {
    clearStoredAdminKey()
    setHasAdminKey(false)
    if (route === 'admin_service_requests' || route === 'admin_publish_requests') {
      navigate('/admin/login')
    }
  }

  return (
    <div className="routeShell">
      <header className="topNav topNav--workspace">
        <div className="topNavBrand" onClick={() => navigate('/')} role="button" tabIndex={0}>
          <span className="topNavBrandMark">G</span>
          <span><b>GoC</b><small>작업방 관리</small></span>
        </div>
        <nav className="topNavPrimary" aria-label="주요 메뉴">
          <button className={route === 'workspace' ? 'isActive' : ''} onClick={() => navigate('/')}>작업방</button>
          <button className={route === 'library' ? 'isActive' : ''} onClick={() => navigate('/library')}>자료함</button>
          <button className={route === 'agents' ? 'isActive' : ''} onClick={() => navigate('/agents')}>Agent</button>
          <button className={route === 'tools' ? 'isActive' : ''} onClick={() => navigate('/tools')}>도구</button>
        </nav>
        <div className="topNavRight">
          <button className={route === 'guest_request_service' ? 'isActive' : ''} onClick={() => navigate('/guest/request-service')}>서비스 이용</button>
          <details className="topNavAdminMenu">
            <summary>{hasAdminKey ? '관리자 연결됨' : '관리자'}</summary>
            <div className="topNavAdminPopover">
              {!hasAdminKey && <button onClick={() => navigate('/admin/login')}>관리자 로그인</button>}
              {hasAdminKey && <button onClick={() => navigate('/admin/service-requests')}>서비스 요청</button>}
              {hasAdminKey && <button onClick={() => navigate('/admin/publish-requests')}>게시 요청</button>}
              {hasAdminKey && <button onClick={handleAdminLogout}>로그아웃</button>}
            </div>
          </details>
        </div>
      </header>

      <main className={route === 'workspace' ? 'routeMain routeMainWorkspace' : 'routeMain'}>
        <Suspense fallback={<RouteFallback label="화면을 불러오는 중…" />}>
          {route === 'workspace' && <WorkspaceApp />}
          {route === 'agents' && <AgentsPage onNavigate={navigate} />}
          {route === 'tools' && <ToolsPage onNavigate={navigate} />}
          {route === 'library' && <LibraryPage onNavigate={navigate} />}
          {route === 'admin_login' && (
            <AdminLoginPage onAdminAuthChanged={handleAdminAuthChanged} onNavigate={navigate} />
          )}
          {route === 'guest_request_service' && (
            <GuestRequestServicePage onNavigate={navigate} />
          )}
          {route === 'admin_service_requests' && (
            <AdminServiceRequestsPage hasAdminKey={hasAdminKey} onNavigate={navigate} />
          )}
          {route === 'admin_publish_requests' && (
            <AdminPublishRequestsPage hasAdminKey={hasAdminKey} onNavigate={navigate} />
          )}
        </Suspense>
      </main>
    </div>
  )
}
