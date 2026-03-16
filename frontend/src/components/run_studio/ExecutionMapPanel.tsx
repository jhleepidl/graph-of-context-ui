import React from 'react'
import {
  type CheckpointProjection,
  type CollaborationProjection,
  type OrchestrationProjection,
  type TeamViewProjection,
} from './types'

type Props = {
  orchestration: OrchestrationProjection | null
  teamView: TeamViewProjection | null
  collaboration: CollaborationProjection | null
  checkpoints: CheckpointProjection | null
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : String(value ?? '').trim()
}

function laneTitle(roleId: string): string {
  if (roleId === 'researcher') return 'Research lanes'
  if (roleId === 'reviewer') return 'Review gate'
  if (roleId === 'synthesizer') return 'Final synthesis'
  if (roleId === 'builder') return 'Build lane'
  if (roleId === 'operator') return 'Runtime ops'
  return 'Runtime lane'
}

export default function ExecutionMapPanel({ orchestration, teamView, collaboration, checkpoints }: Props) {
  const items = teamView?.items || []
  const byId = new Map(items.map((item) => [String(item.runtime_instance_id || item.agent_id || ''), item]))
  const parallelGroups = orchestration?.parallel_groups || []
  const sequentialAfter = orchestration?.sequential_after || {}
  const supervisorRuntime = orchestration?.supervisor_runtime || null
  const supervisorMode = cleanText(orchestration?.supervisor_mode || supervisorRuntime?.interaction_mode || supervisorRuntime?.mode)
  const checkpointItems = checkpoints?.items || []
  const collaborationItems = collaboration?.items || []

  const groupedByRole = new Map<string, typeof items>()
  items.forEach((item) => {
    const role = cleanText(item.role_id || item.role_label || 'runtime') || 'runtime'
    if (!groupedByRole.has(role)) groupedByRole.set(role, [])
    groupedByRole.get(role)!.push(item)
  })

  const renderedParallelIds = new Set<string>()
  parallelGroups.forEach((group) => {
    ;(group.member_instance_ids || []).forEach((id) => renderedParallelIds.add(String(id)))
  })

  const lanes = Array.from(groupedByRole.entries()).map(([role, laneItems]) => ({
    role,
    title: laneTitle(role),
    items: laneItems,
  }))

  return (
    <section className="card runStudioPanel runStudioExecutionMapPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3 style={{ margin: 0 }}>Execution Map</h3>
          <div className="muted">A control-plane view of how this run fans out, reviews work, and converges.</div>
        </div>
        <div className="runStudioMetaRow">
          {supervisorMode && <span className="pill">supervisor: {supervisorMode}</span>}
          <span className="pill">parallel groups: {parallelGroups.length}</span>
          <span className="pill">collaboration cells: {collaborationItems.length}</span>
          <span className="pill">checkpoints: {checkpointItems.length}</span>
        </div>
      </div>

      {supervisorMode && (
        <div className="runStudioExecutionHeader">
          <div className="runStudioExecutionNode runStudioExecutionNode--supervisor">
            <div className="runStudioExecutionNodeTitle">Supervisor runtime</div>
            <div className="muted">{supervisorMode}</div>
            {supervisorRuntime?.authority_profile_id && (
              <div className="muted">authority: {String(supervisorRuntime.authority_profile_id)}</div>
            )}
          </div>
        </div>
      )}

      {parallelGroups.length > 0 && (
        <div className="runStudioExecutionCluster">
          {parallelGroups.map((group, index) => {
            const memberLabels = (group.member_instance_ids || [])
              .map((id) => byId.get(String(id)))
              .filter(Boolean)
              .map((item) => String(item?.display_label || item?.role_label || item?.runtime_instance_id || 'runtime agent'))
            return (
              <div key={`parallel-${group.group_id || index}`} className="runStudioExecutionParallelGroup">
                <div className="runStudioExecutionClusterTitle">{group.label || group.group_id || `Parallel group ${index + 1}`}</div>
                <div className="runStudioExecutionInlineNodes">
                  {memberLabels.map((label) => (
                    <div key={`${group.group_id || index}:${label}`} className="runStudioExecutionNode runStudioExecutionNode--parallel">
                      <div className="runStudioExecutionNodeTitle">{label}</div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}

      <div className="runStudioExecutionLaneGrid">
        {lanes.map((lane) => (
          <article key={lane.role} className="runStudioExecutionLane">
            <div className="runStudioExecutionLaneTitle">{lane.title}</div>
            <div className="runStudioExecutionLaneItems">
              {lane.items.map((item) => {
                const itemId = String(item.runtime_instance_id || item.agent_id || '')
                const dependencies = Object.entries(sequentialAfter)
                  .filter(([target]) => target === itemId)
                  .flatMap(([, deps]) => deps)
                  .map((dep) => byId.get(String(dep))?.display_label || dep)
                return (
                  <div key={itemId || item.display_label} className="runStudioExecutionNode">
                    <div className="runStudioExecutionNodeTitle">{item.display_label || item.role_label || itemId || 'runtime agent'}</div>
                    <div className="muted">slot: {item.slot_label || item.slot_id || item.role_id || '-'}</div>
                    {dependencies.length > 0 && (
                      <div className="muted">after: {dependencies.join(' | ')}</div>
                    )}
                    {renderedParallelIds.has(itemId) && <div className="runStudioExecutionBadge">parallel</div>}
                    {item.selection_reason && <div className="muted">{item.selection_reason}</div>}
                  </div>
                )
              })}
            </div>
          </article>
        ))}
      </div>

      {(collaborationItems.length > 0 || checkpointItems.length > 0) && (
        <div className="runStudioExecutionFooterGrid">
          {collaborationItems.length > 0 && (
            <div className="runStudioExecutionFootCard">
              <div className="runStudioExecutionClusterTitle">Collaboration</div>
              {collaborationItems.slice(0, 4).map((item, index) => (
                <div key={`collab-${index}`} className="muted">
                  {item.pattern || item.kind || 'collaboration'} · {item.member_labels?.join(' | ') || item.member_instance_ids?.join(' | ') || 'members pending'}
                </div>
              ))}
            </div>
          )}
          {checkpointItems.length > 0 && (
            <div className="runStudioExecutionFootCard">
              <div className="runStudioExecutionClusterTitle">Checkpoints</div>
              {checkpointItems.slice(0, 4).map((item, index) => (
                <div key={`checkpoint-${index}`} className="muted">
                  {item.checkpoint_id || `checkpoint-${index + 1}`} · {item.supervisor_decision_summary || item.completion_signal_summary || 'gate'}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
