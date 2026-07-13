import React from 'react'
import { type WorkspaceMainTab } from '../../hooks/useWorkspaceTabs'

type Props = {
  workspaceMainTab: WorkspaceMainTab
  setWorkspaceMainTab: (tab: WorkspaceMainTab) => void
}

const TABS: Array<{ id: WorkspaceMainTab; label: string }> = [
  { id: 'run_studio', label: '작업방' },
  { id: 'graph', label: '관계 보기' },
  { id: 'artifacts', label: '결과물' },
  { id: 'advanced', label: '고급 도구' },
]

export default function WorkspaceRouteState({ workspaceMainTab, setWorkspaceMainTab }: Props) {
  const active = TABS.some((item) => item.id === workspaceMainTab) ? workspaceMainTab : 'advanced'
  return (
    <div className="workspaceViewSwitch" role="tablist" aria-label="Workspace view">
      {TABS.map((item) => (
        <button key={item.id} className={active === item.id ? 'isActive' : ''} onClick={() => setWorkspaceMainTab(item.id)}>{item.label}</button>
      ))}
    </div>
  )
}
