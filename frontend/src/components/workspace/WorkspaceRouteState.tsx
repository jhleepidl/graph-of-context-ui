import React from 'react'
import { type WorkspaceMainTab } from '../../hooks/useWorkspaceTabs'

type Props = {
  workspaceMainTab: WorkspaceMainTab
  setWorkspaceMainTab: (tab: WorkspaceMainTab) => void
}

export default function WorkspaceRouteState({ workspaceMainTab, setWorkspaceMainTab }: Props) {
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 6 }}>
        <button className={workspaceMainTab === 'run_studio' ? 'primary' : ''} onClick={() => setWorkspaceMainTab('run_studio')}>Studio</button>
        <button className={workspaceMainTab === 'board' ? 'primary' : ''} onClick={() => setWorkspaceMainTab('board')}>Board</button>
        <button className={workspaceMainTab === 'graph' ? 'primary' : ''} onClick={() => setWorkspaceMainTab('graph')}>Graph</button>
        <button className={workspaceMainTab === 'advanced' ? 'primary' : ''} onClick={() => setWorkspaceMainTab('advanced')}>More</button>
      </div>
      <div className="muted">
        {workspaceMainTab === 'run_studio' && 'Start here: current status, active team, recent activity, and the next action.'}
        {workspaceMainTab === 'board' && 'Board view for raw history, promotion candidates, and reusable thread assets.'}
        {workspaceMainTab === 'graph' && 'Graph editing and manual fold/unfold controls.'}
        {workspaceMainTab === 'advanced' && 'Expanded diagnostics, raw trace, artifacts, and power-user controls.'}
        {workspaceMainTab === 'raw_trace' && 'Detailed execution graph + timeline + node inspector.'}
        {workspaceMainTab === 'artifacts' && 'Artifact/resource inventory and selection state.'}
      </div>
    </div>
  )
}
