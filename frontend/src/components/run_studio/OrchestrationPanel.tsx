import React from 'react'
import {
  type CheckpointProjection,
  type OrchestrationProjection,
  type TeamViewProjection,
} from './types'

type Props = {
  orchestration: OrchestrationProjection | null
  checkpoints: CheckpointProjection | null
  teamView?: TeamViewProjection | null
}

export default function OrchestrationPanel({ orchestration, checkpoints, teamView }: Props) {
  const parallelGroups = orchestration?.parallel_groups || []
  const sequentialAfter = orchestration?.sequential_after || {}
  const supervisorEdges = orchestration?.supervisor_edges || []
  const checkpointCount = Number(
    orchestration?.checkpoint_count || checkpoints?.counts?.total || checkpoints?.items?.length || 0,
  )
  const pendingCheckpoints = (checkpoints?.items || []).filter((item) => {
    const status = String(item.status || 'pending').toLowerCase()
    return status !== 'done' && status !== 'approved'
  }).length
  const supervisorInteractionMode =
    orchestration?.supervisor_runtime?.interaction_mode || orchestration?.supervisor_mode || orchestration?.supervisor_runtime?.mode
  const supervisorEnabled = Boolean(
    orchestration?.supervisor_enabled ||
    supervisorInteractionMode ||
    orchestration?.supervisor_runtime?.instance_id ||
    supervisorEdges.length,
  )
  const labelsByInstance = new Map(
    (teamView?.items || [])
      .map((item) => [String(item.runtime_instance_id || '').trim(), String(item.display_label || '').trim()])
      .filter((item): item is [string, string] => Boolean(item[0] && item[1])),
  )

  return (
    <section className="card runStudioPanel">
      <div className="runStudioPanelHeader">
        <h3>Orchestration</h3>
        <div className="runStudioMetaRow">
          <span className="pill">mode: {orchestration?.mode || 'runtime_managed'}</span>
          <span className="pill">parallel groups: {orchestration?.parallel_group_count ?? parallelGroups.length}</span>
          <span className="pill">sequential deps: {orchestration?.sequential_dependency_count ?? Object.keys(sequentialAfter).length}</span>
          <span className="pill">supervisor edges: {orchestration?.supervisor_edge_count ?? supervisorEdges.length}</span>
          <span className="pill">checkpoints: {checkpointCount}</span>
          {pendingCheckpoints > 0 && <span className="pill">pending: {pendingCheckpoints}</span>}
        </div>
      </div>

      <div className="runStudioMetaRow" style={{ marginBottom: 8 }}>
        {supervisorEnabled && <span className="pill">supervisor enabled</span>}
        {supervisorInteractionMode && <span className="pill">interaction: {supervisorInteractionMode}</span>}
        {orchestration?.supervisor_runtime?.instance_id && (
          <span className="pill">supervisor: {String(orchestration.supervisor_runtime.instance_id)}</span>
        )}
        {orchestration?.supervisor_runtime?.authority_profile_id && (
          <span className="pill">authority: {String(orchestration.supervisor_runtime.authority_profile_id)}</span>
        )}
        {orchestration?.supervisor_runtime?.user_visible != null && (
          <span className="pill">
            {orchestration.supervisor_runtime.user_visible ? 'user visible' : 'runtime-only'}
          </span>
        )}
        {Object.entries(orchestration?.checkpoint_status_counts || {}).map(([status, count]) => (
          <span key={status} className="pill">checkpoint {status}: {count}</span>
        ))}
      </div>

      <div className="runStudioList">
        {parallelGroups.map((group, index) => (
          <article key={`parallel:${group.group_id || index}`} className="runStudioListItem">
            <div className="row" style={{ marginBottom: 4 }}>
              <span className="pill">{group.label || group.group_id || `group-${index + 1}`}</span>
              <span className="pill">parallel</span>
            </div>
            <div className="muted">
              members: {((group.member_labels && group.member_labels.length > 0)
                ? group.member_labels
                : (group.member_instance_ids || [])
                    .map((memberId) => labelsByInstance.get(memberId) || memberId)
              ).join(' | ') || 'not specified'}
            </div>
          </article>
        ))}

        {Object.entries(sequentialAfter).map(([target, deps]) => (
          <article key={`sequential:${target}`} className="runStudioListItem">
            <div className="row" style={{ marginBottom: 4 }}>
              <span className="pill">{target}</span>
              <span className="pill">sequential after</span>
            </div>
            <div className="muted">{deps.join(' | ') || 'no dependencies listed'}</div>
          </article>
        ))}

        {supervisorEdges.map((edge, index) => (
          <article key={`supervisor:${index}`} className="runStudioListItem">
            <div className="row" style={{ marginBottom: 4 }}>
              <span className="pill">supervisor edge</span>
              {edge.from && <span className="pill">from: {String(edge.from)}</span>}
              {edge.to && <span className="pill">to: {String(edge.to)}</span>}
            </div>
            {edge.edge_summary && <div className="muted">{String(edge.edge_summary)}</div>}
            {(edge.type || edge.kind || edge.label) && (
              <div className="muted">{String(edge.type || edge.kind || edge.label)}</div>
            )}
          </article>
        ))}

        {parallelGroups.length === 0 && Object.keys(sequentialAfter).length === 0 && supervisorEdges.length === 0 && (
          <div className="muted">No explicit orchestration graph was emitted. Legacy runs still render as runtime-managed execution.</div>
        )}
      </div>
    </section>
  )
}
