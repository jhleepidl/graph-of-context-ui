import React from 'react'

type Props = {
  summary?: any | null
  teamView?: any | null
  legacyTeam?: any | null
}

function arr(value: any): any[] {
  return Array.isArray(value) ? value : []
}

function text(value: any, fallback = '-'): string {
  const clean = typeof value === 'string' ? value.trim() : String(value ?? '').trim()
  return clean || fallback
}

function inferAgents(teamView: any, legacyTeam: any): string[] {
  const items = arr(teamView?.items).length ? arr(teamView?.items) : arr(legacyTeam?.items)
  return items
    .map((row) => text(row?.role || row?.role_id || row?.id || row?.agent_id || row?.label, ''))
    .filter(Boolean)
    .slice(0, 8)
}

function inferWorkflow(summary: any): string {
  return text(
    summary?.agent_room?.default_workflow
      || summary?.watch_task?.workflow_kind
      || summary?.current_task?.workflow_kind
      || summary?.team_workflow_contract?.workflow_kind
      || summary?.runtime_metadata?.team_workflow_contract?.workflow_kind,
    'task-adaptive'
  )
}

export default function AgentRoomPanel({ summary, teamView, legacyTeam }: Props) {
  const room = summary?.agent_room || summary?.agentRoom || null
  const agents = arr(room?.default_agents || room?.defaultAgents).length
    ? arr(room?.default_agents || room?.defaultAgents)
    : inferAgents(teamView, legacyTeam)
  const workflow = inferWorkflow(summary)
  const autonomy = room?.autonomy_policy || room?.autonomyPolicy || summary?.autonomy_policy || {}
  const skills = arr(room?.installed_skills || room?.installedSkills || summary?.current_run_skills?.items).slice(0, 6)
  const rules = arr(room?.active_rules || room?.activeRules || summary?.runtime_rules).slice(0, 5)

  return (
    <section className="card runStudioPanel runStudioAgentRoomPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3>Agent Room</h3>
          <div className="muted">Standing workspace: default agents, workflow, autonomy policy, memory/rule/skill growth surface.</div>
        </div>
        <div className="runStudioMetaRow" style={{ marginBottom: 0 }}>
          <span className="pill">workflow: {workflow}</span>
          <span className="pill">agents: {agents.length}</span>
        </div>
      </div>
      <div className="runStudioQuickList">
        <div className="runStudioQuickListItem">
          <div className="runStudioQuickListHeader"><b>Default agents</b></div>
          <div className="runStudioMetaRow">
            {agents.length ? agents.map((agent) => <span key={agent} className="pill">{agent}</span>) : <span className="muted">No standing agents configured yet. Use /agents suggest or /task loop.</span>}
          </div>
        </div>
        <div className="runStudioQuickListItem">
          <div className="runStudioQuickListHeader"><b>Autonomy policy</b></div>
          <div className="muted">
            small changes: {text(autonomy.small_safe_changes || autonomy.smallSafeChanges, 'auto/review by task')} · risky/large: {text(autonomy.risky_or_large_changes || autonomy.riskyOrLargeChanges, 'approval required')} · deployment: {text(autonomy.deployment, 'forbidden without approval')}
          </div>
        </div>
        <div className="runStudioQuickListItem">
          <div className="runStudioQuickListHeader"><b>Growth surfaces</b></div>
          <div className="runStudioMetaRow">
            <span className="pill">memory proposals</span>
            <span className="pill">skill candidates</span>
            <span className="pill">learned rules</span>
            <span className="pill">role evolution</span>
          </div>
        </div>
        {(skills.length > 0 || rules.length > 0) && (
          <div className="runStudioQuickListItem">
            <div className="runStudioQuickListHeader"><b>Attached knowledge</b></div>
            <div className="muted">
              {skills.length ? `skills: ${skills.map((row: any) => text(row?.name || row?.id || row)).join(', ')}` : 'skills: -'}
              <br />
              {rules.length ? `rules: ${rules.map((row: any) => text(row?.text || row?.title || row)).join(' · ')}` : 'rules: -'}
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
