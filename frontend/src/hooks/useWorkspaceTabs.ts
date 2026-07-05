import { useEffect, useMemo, useState } from 'react'

const RIGHT_PANEL_TAB_STORAGE_KEY = 'goc:right-panel-tab:v1'
const MOBILE_SECTION_STORAGE_KEY = 'goc:mobile-section:v1'
const WORKSPACE_MAIN_TAB_STORAGE_KEY = 'goc:workspace-main-tab:v1'

export type MobileSection = 'left' | 'center' | 'right'
export type RightPanelTab = 'inspector' | 'prompt' | 'run' | 'job_settings' | 'conversation_agents'
export type WorkspaceMainTab = 'companion' | 'run_studio' | 'board' | 'graph' | 'raw_trace' | 'artifacts' | 'advanced'

function readStoredRightPanelTab(): RightPanelTab {
  if (typeof window === 'undefined') return 'inspector'
  try {
    const raw = window.localStorage.getItem(RIGHT_PANEL_TAB_STORAGE_KEY)
    if (raw === 'inspector' || raw === 'prompt' || raw === 'run' || raw === 'job_settings' || raw === 'conversation_agents') return raw
  } catch {
    // ignore storage failures
  }
  return 'inspector'
}

function readStoredMobileSection(): MobileSection {
  if (typeof window === 'undefined') return 'center'
  try {
    const raw = window.localStorage.getItem(MOBILE_SECTION_STORAGE_KEY)
    if (raw === 'left' || raw === 'center' || raw === 'right') return raw
  } catch {
    // ignore storage failures
  }
  return 'center'
}

function readStoredWorkspaceMainTab(): WorkspaceMainTab {
  if (typeof window === 'undefined') return 'run_studio'
  try {
    const raw = window.localStorage.getItem(WORKSPACE_MAIN_TAB_STORAGE_KEY)
    if (raw === 'companion' || raw === 'run_studio' || raw === 'board' || raw === 'graph' || raw === 'raw_trace' || raw === 'artifacts' || raw === 'advanced') return raw
  } catch {
    // ignore storage failures
  }
  return 'companion'
}

export function useWorkspaceTabs() {
  const [workspaceMainTab, setWorkspaceMainTab] = useState<WorkspaceMainTab>(() => readStoredWorkspaceMainTab())
  const [rightPanelTab, setRightPanelTab] = useState<RightPanelTab>(() => readStoredRightPanelTab())
  const [mobileSection, setMobileSection] = useState<MobileSection>(() => readStoredMobileSection())

  useEffect(() => {
    try {
      window.localStorage.setItem(WORKSPACE_MAIN_TAB_STORAGE_KEY, workspaceMainTab)
    } catch {
      // ignore localStorage errors
    }
  }, [workspaceMainTab])

  useEffect(() => {
    try {
      window.localStorage.setItem(RIGHT_PANEL_TAB_STORAGE_KEY, rightPanelTab)
    } catch {
      // ignore localStorage errors
    }
  }, [rightPanelTab])

  useEffect(() => {
    try {
      window.localStorage.setItem(MOBILE_SECTION_STORAGE_KEY, mobileSection)
    } catch {
      // ignore localStorage errors
    }
  }, [mobileSection])

  const workspaceMainTabLabel = useMemo(() => {
    if (workspaceMainTab === 'companion') return 'Companion Hub'
    if (workspaceMainTab === 'run_studio') return 'Run Studio'
    if (workspaceMainTab === 'board') return 'Board'
    if (workspaceMainTab === 'graph') return 'Graph'
    if (workspaceMainTab === 'raw_trace') return 'Raw Trace'
    if (workspaceMainTab === 'artifacts') return 'Artifacts'
    return 'Advanced'
  }, [workspaceMainTab])

  return {
    workspaceMainTab,
    setWorkspaceMainTab,
    rightPanelTab,
    setRightPanelTab,
    mobileSection,
    setMobileSection,
    workspaceMainTabLabel,
  }
}
