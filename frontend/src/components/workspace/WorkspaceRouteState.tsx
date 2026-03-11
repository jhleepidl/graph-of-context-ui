import React from 'react'
import { type WorkspaceMainTab } from '../../hooks/useWorkspaceTabs'

type Props = {
  workspaceMainTab: WorkspaceMainTab
  setWorkspaceMainTab: (tab: WorkspaceMainTab) => void
}

export default function WorkspaceRouteState({ workspaceMainTab, setWorkspaceMainTab }: Props) {
  return (
    <div className="card">
      <div className="row" style={{ marginBottom: 0 }}>
        <button className={workspaceMainTab === 'run_studio' ? 'primary' : ''} onClick={() => setWorkspaceMainTab('run_studio')}>Run Studio</button>
        <button className={workspaceMainTab === 'graph' ? 'primary' : ''} onClick={() => setWorkspaceMainTab('graph')}>Graph</button>
        <button className={workspaceMainTab === 'raw_trace' ? 'primary' : ''} onClick={() => setWorkspaceMainTab('raw_trace')}>Raw Trace</button>
        <button className={workspaceMainTab === 'artifacts' ? 'primary' : ''} onClick={() => setWorkspaceMainTab('artifacts')}>Artifacts</button>
        <button className={workspaceMainTab === 'advanced' ? 'primary' : ''} onClick={() => setWorkspaceMainTab('advanced')}>Advanced</button>
        <span className="muted">
          {workspaceMainTab === 'run_studio' && 'Operational view: run status, runtime team, context decisions, and evidence'}
          {workspaceMainTab === 'graph' && 'Graph editing and manual fold/unfold controls'}
          {workspaceMainTab === 'raw_trace' && 'Detailed execution graph + timeline + node inspector'}
          {workspaceMainTab === 'artifacts' && 'Artifact/resource inventory and selection state'}
          {workspaceMainTab === 'advanced' && 'Copy/Paste prompt tools and thread-level power controls'}
        </span>
      </div>
    </div>
  )
}
