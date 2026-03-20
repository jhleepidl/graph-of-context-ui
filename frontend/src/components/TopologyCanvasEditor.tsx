import React, { useEffect, useMemo, useState } from 'react'
import ReactFlow, {
  addEdge,
  Background,
  Connection,
  Controls,
  Edge,
  MarkerType,
  MiniMap,
  Node,
  OnConnect,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
} from 'reactflow'
import 'reactflow/dist/style.css'

type TopologyParticipantFormRow = {
  participant_id: string
  kind: string
  role: string
  label: string
  provider: string
}

type TopologyNodeFormRow = {
  node_id: string
  participant_id: string
  kind: string
  stage_index: string
}

type TopologyEdgeFormRow = {
  from: string
  to: string
  condition: string
  label: string
}

type Props = {
  participants: TopologyParticipantFormRow[]
  nodes: TopologyNodeFormRow[]
  edges: TopologyEdgeFormRow[]
  finalParticipantId: string
  finalOwnerParticipantId: string
  validationWarnings: string[]
  validationErrors: string[]
  onParticipantsChange: React.Dispatch<React.SetStateAction<TopologyParticipantFormRow[]>>
  onNodesChange: React.Dispatch<React.SetStateAction<TopologyNodeFormRow[]>>
  onEdgesChange: React.Dispatch<React.SetStateAction<TopologyEdgeFormRow[]>>
  onFinalParticipantChange: (value: string) => void
  onFinalOwnerParticipantChange: (value: string) => void
}

type CanvasNodeData = {
  title: string
  subtitle: string
  isFinalParticipant: boolean
  isFinalOwner: boolean
  hasParticipantWarning: boolean
}

function asString(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

function nodeKeyForRow(row: TopologyNodeFormRow, index: number): string {
  return asString(row.node_id) || asString(row.participant_id) || `draft-node-${index + 1}`
}

function participantKeyForRow(row: TopologyParticipantFormRow, index: number): string {
  return asString(row.participant_id) || `participant-${index + 1}`
}

function buildLayoutPositions(rows: TopologyNodeFormRow[]): Map<string, { x: number; y: number }> {
  const byStage = new Map<number, TopologyNodeFormRow[]>()
  const fallbackStage = rows.length > 1 ? 0 : 1
  rows.forEach((row, index) => {
    const parsed = Number.parseInt(asString(row.stage_index), 10)
    const stage = Number.isFinite(parsed) ? parsed : fallbackStage + index
    const bucket = byStage.get(stage) || []
    bucket.push(row)
    byStage.set(stage, bucket)
  })

  const positions = new Map<string, { x: number; y: number }>()
  const stageIndexes = [...byStage.keys()].sort((a, b) => a - b)
  stageIndexes.forEach((stage, stageOffset) => {
    const items = byStage.get(stage) || []
    items.forEach((row, rowIndex) => {
      positions.set(nodeKeyForRow(row, rowIndex), {
        x: 80 + stageOffset * 240,
        y: 72 + rowIndex * 140,
      })
    })
  })
  return positions
}

function buildCanvasNodes({
  participants,
  nodes,
  finalParticipantId,
  finalOwnerParticipantId,
}: {
  participants: TopologyParticipantFormRow[]
  nodes: TopologyNodeFormRow[]
  finalParticipantId: string
  finalOwnerParticipantId: string
}): Node<CanvasNodeData>[] {
  const filteredParticipants = participants.filter((row) => participantKeyForRow(row, 0))
  const participantById = new Map(filteredParticipants.map((row, index) => [participantKeyForRow(row, index), row]))
  const filteredNodes = nodes.filter((row) => nodeKeyForRow(row, 0))
  const effectiveNodes = filteredNodes.length > 0
    ? filteredNodes
    : filteredParticipants.map((participant, index) => ({
        node_id: `node_${participantKeyForRow(participant, index)}`,
        participant_id: participantKeyForRow(participant, index),
        kind: participant.kind || 'agent',
        stage_index: String(index + 1),
      }))
  const positions = buildLayoutPositions(effectiveNodes)

  return effectiveNodes.map((row, index) => {
    const id = nodeKeyForRow(row, index)
    const participantId = asString(row.participant_id)
    const participant = participantById.get(participantId)
    const displayLabel = asString(participant?.label) || asString(participant?.participant_id) || participantId || id
    const role = asString(participant?.role) || asString(row.kind) || 'agent'
    const isFinalParticipant = participantId !== '' && participantId === asString(finalParticipantId)
    const isFinalOwner = participantId !== '' && participantId === asString(finalOwnerParticipantId)
    const hasParticipantWarning = participantId !== '' && !participantById.has(participantId)
    const borderColor = hasParticipantWarning ? '#dc2626' : isFinalOwner ? '#7c3aed' : isFinalParticipant ? '#2563eb' : '#cbd5e1'
    const background = hasParticipantWarning ? '#fef2f2' : isFinalOwner ? '#f5f3ff' : isFinalParticipant ? '#eff6ff' : '#ffffff'

    return {
      id,
      type: 'default',
      position: positions.get(id) || { x: 80, y: 80 + index * 120 },
      data: {
        title: displayLabel,
        subtitle: `${role}${participant?.provider ? ` · ${participant.provider}` : ''}`,
        isFinalParticipant,
        isFinalOwner,
        hasParticipantWarning,
      },
      style: {
        borderRadius: 14,
        border: `2px solid ${borderColor}`,
        background,
        minWidth: 180,
        boxShadow: '0 8px 24px rgba(15, 23, 42, 0.08)',
        padding: 10,
        fontSize: 12,
      },
    }
  })
}

function buildCanvasEdges(edges: TopologyEdgeFormRow[]): Edge[] {
  return edges
    .map((row, index) => {
      const source = asString(row.from)
      const target = asString(row.to)
      if (!source || !target) return null
      const label = asString(row.label) || asString(row.condition)
      return {
        id: `edge-${source}-${target}-${index + 1}`,
        source,
        target,
        label,
        type: 'smoothstep',
        markerEnd: { type: MarkerType.ArrowClosed },
        animated: Boolean(asString(row.condition)),
        style: {
          strokeWidth: 2,
        },
        labelStyle: {
          fontSize: 11,
          fontWeight: 600,
        },
      } satisfies Edge
    })
    .filter((row): row is Edge => Boolean(row))
}

function nextParticipantSeed(rows: TopologyParticipantFormRow[]): string {
  const base = rows.length + 1
  return `participant_${base}`
}

function nextNodeSeed(rows: TopologyNodeFormRow[]): string {
  const base = rows.length + 1
  return `node_${base}`
}

function TopologyCanvasEditorInner({
  participants,
  nodes,
  edges,
  finalParticipantId,
  finalOwnerParticipantId,
  validationWarnings,
  validationErrors,
  onParticipantsChange,
  onNodesChange,
  onEdgesChange,
  onFinalParticipantChange,
  onFinalOwnerParticipantChange,
}: Props) {
  const participantOptions = useMemo(
    () => participants
      .map((row, index) => ({
        id: participantKeyForRow(row, index),
        label: asString(row.label) || participantKeyForRow(row, index),
      }))
      .filter((row) => row.id),
    [participants],
  )

  const canvasNodes = useMemo(
    () => buildCanvasNodes({ participants, nodes, finalParticipantId, finalOwnerParticipantId }),
    [participants, nodes, finalParticipantId, finalOwnerParticipantId],
  )
  const canvasEdges = useMemo(() => buildCanvasEdges(edges), [edges])
  const [flowNodes, setFlowNodes, onFlowNodesChange] = useNodesState<CanvasNodeData>(canvasNodes)
  const [flowEdges, setFlowEdges, onFlowEdgesChange] = useEdgesState(canvasEdges)
  const [selectedNodeId, setSelectedNodeId] = useState('')
  const [selectedEdgeId, setSelectedEdgeId] = useState('')

  useEffect(() => {
    setFlowNodes(canvasNodes)
  }, [canvasNodes, setFlowNodes])

  useEffect(() => {
    setFlowEdges(canvasEdges)
  }, [canvasEdges, setFlowEdges])

  const selectedNode = useMemo(
    () => flowNodes.find((row) => row.id === selectedNodeId) || null,
    [flowNodes, selectedNodeId],
  )
  const selectedNodeIndex = useMemo(
    () => nodes.findIndex((row, index) => nodeKeyForRow(row, index) === selectedNodeId),
    [nodes, selectedNodeId],
  )
  const selectedNodeRow = selectedNodeIndex >= 0 ? nodes[selectedNodeIndex] : null
  const selectedEdgeIndex = useMemo(
    () => flowEdges.findIndex((row) => row.id === selectedEdgeId),
    [flowEdges, selectedEdgeId],
  )
  const selectedEdgeRow = selectedEdgeIndex >= 0 ? edges[selectedEdgeIndex] : null

  const onConnect = (connection: Connection) => {
    const source = asString(connection.source)
    const target = asString(connection.target)
    if (!source || !target) return
    onEdgesChange((prev) => {
      if (prev.some((row) => asString(row.from) === source && asString(row.to) === target)) return prev
      return [...prev, { from: source, to: target, condition: '', label: '' }]
    })
    setFlowEdges((prev) => addEdge({ ...connection, type: 'smoothstep', markerEnd: { type: MarkerType.ArrowClosed } }, prev))
  }

  return (
    <div style={{ marginTop: 10, border: '1px solid var(--border-color, #dbe1ea)', borderRadius: 14, overflow: 'hidden' }}>
      <div style={{ padding: '10px 12px', background: 'rgba(148, 163, 184, 0.08)', borderBottom: '1px solid var(--border-color, #dbe1ea)' }}>
        <div style={{ fontWeight: 700 }}>Topology canvas editor</div>
        <div className="muted" style={{ marginTop: 4 }}>
          노드를 연결하면 edge가 추가되고, 선택한 노드를 final participant / final owner로 바로 지정할 수 있습니다.
        </div>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 300px', minHeight: 380 }}>
        <div style={{ minHeight: 380 }}>
          <ReactFlow
            nodes={flowNodes.map((node) => ({
              ...node,
              data: {
                ...node.data,
                label: (
                  <div>
                    <div style={{ fontWeight: 700 }}>{node.data.title}</div>
                    <div style={{ marginTop: 4, fontSize: 11, opacity: 0.78 }}>{node.data.subtitle}</div>
                    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
                      {node.data.isFinalParticipant && <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 999, background: '#dbeafe', color: '#1d4ed8' }}>final participant</span>}
                      {node.data.isFinalOwner && <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 999, background: '#ede9fe', color: '#6d28d9' }}>final owner</span>}
                      {node.data.hasParticipantWarning && <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 999, background: '#fee2e2', color: '#b91c1c' }}>unknown participant</span>}
                    </div>
                  </div>
                ),
              },
            }))}
            edges={flowEdges}
            onNodesChange={onFlowNodesChange}
            onEdgesChange={onFlowEdgesChange}
            onConnect={onConnect as OnConnect}
            onSelectionChange={({ nodes: selectedNodes, edges: selectedEdges }) => {
              setSelectedNodeId(selectedNodes[0]?.id || '')
              setSelectedEdgeId(selectedEdges[0]?.id || '')
            }}
            onNodesDelete={(deleted) => {
              const deletedIds = new Set(deleted.map((row) => row.id))
              onNodesChange((prev) => prev.filter((row, index) => !deletedIds.has(nodeKeyForRow(row, index))))
              onEdgesChange((prev) => prev.filter((row) => !deletedIds.has(asString(row.from)) && !deletedIds.has(asString(row.to))))
              if (selectedNodeId && deletedIds.has(selectedNodeId)) setSelectedNodeId('')
            }}
            onEdgesDelete={(deleted) => {
              const deletedIds = new Set(deleted.map((row) => row.id))
              onEdgesChange((prev) => prev.filter((row, index) => !deletedIds.has(`edge-${asString(row.from)}-${asString(row.to)}-${index + 1}`)))
              if (selectedEdgeId && deletedIds.has(selectedEdgeId)) setSelectedEdgeId('')
            }}
            fitView
            deleteKeyCode={['Backspace', 'Delete']}
          >
            <MiniMap zoomable pannable />
            <Controls />
            <Background gap={18} size={1} />
          </ReactFlow>
        </div>
        <div style={{ borderLeft: '1px solid var(--border-color, #dbe1ea)', padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <div style={{ fontWeight: 700 }}>Quick actions</div>
            <div className="row" style={{ gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
              <button onClick={() => {
                const nextParticipantId = nextParticipantSeed(participants)
                onParticipantsChange((prev) => [...prev, { participant_id: nextParticipantId, kind: 'agent', role: 'specialist', label: nextParticipantId, provider: '' }])
                onNodesChange((prev) => [...prev, { node_id: nextNodeSeed(nodes), participant_id: nextParticipantId, kind: 'agent', stage_index: String(prev.length + 1) }])
              }}>Add participant node</button>
              <button onClick={() => {
                const seed = participantOptions[0]?.id || ''
                onNodesChange((prev) => [...prev, { node_id: nextNodeSeed(prev), participant_id: seed, kind: 'agent', stage_index: String(prev.length + 1) }])
              }}>Add node</button>
            </div>
          </div>

          {selectedNode && selectedNodeRow && (
            <div style={{ border: '1px solid var(--border-color, #dbe1ea)', borderRadius: 12, padding: 10 }}>
              <div style={{ fontWeight: 700 }}>Selected node</div>
              <div className="muted" style={{ marginTop: 4 }}>{selectedNode.id}</div>
              <label className="routeLabel" style={{ marginTop: 8 }}>
                Participant
                <select
                  value={asString(selectedNodeRow.participant_id)}
                  onChange={(e) => {
                    const value = e.target.value
                    onNodesChange((prev) => prev.map((row, index) => index === selectedNodeIndex ? { ...row, participant_id: value } : row))
                  }}
                >
                  <option value="">(none)</option>
                  {participantOptions.map((row) => (
                    <option key={row.id} value={row.id}>{row.label} ({row.id})</option>
                  ))}
                </select>
              </label>
              <div className="row" style={{ gap: 8, marginTop: 8, alignItems: 'flex-start' }}>
                <label className="routeLabel" style={{ flex: 1 }}>
                  Stage
                  <input
                    value={asString(selectedNodeRow.stage_index)}
                    onChange={(e) => onNodesChange((prev) => prev.map((row, index) => index === selectedNodeIndex ? { ...row, stage_index: e.target.value } : row))}
                  />
                </label>
                <label className="routeLabel" style={{ flex: 1 }}>
                  Kind
                  <input
                    value={asString(selectedNodeRow.kind)}
                    onChange={(e) => onNodesChange((prev) => prev.map((row, index) => index === selectedNodeIndex ? { ...row, kind: e.target.value } : row))}
                  />
                </label>
              </div>
              <div className="row" style={{ gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                <button onClick={() => onFinalParticipantChange(asString(selectedNodeRow.participant_id))}>Set final participant</button>
                <button onClick={() => onFinalOwnerParticipantChange(asString(selectedNodeRow.participant_id))}>Set final owner</button>
                <button onClick={() => {
                  onNodesChange((prev) => prev.filter((_, index) => index !== selectedNodeIndex))
                  onEdgesChange((prev) => prev.filter((row) => asString(row.from) !== selectedNode.id && asString(row.to) !== selectedNode.id))
                  setSelectedNodeId('')
                }}>Remove node</button>
              </div>
            </div>
          )}

          {selectedEdgeRow && (
            <div style={{ border: '1px solid var(--border-color, #dbe1ea)', borderRadius: 12, padding: 10 }}>
              <div style={{ fontWeight: 700 }}>Selected edge</div>
              <div className="muted" style={{ marginTop: 4 }}>{selectedEdgeRow.from} → {selectedEdgeRow.to}</div>
              <label className="routeLabel" style={{ marginTop: 8 }}>
                Label
                <input
                  value={asString(selectedEdgeRow.label)}
                  onChange={(e) => onEdgesChange((prev) => prev.map((row, index) => index === selectedEdgeIndex ? { ...row, label: e.target.value } : row))}
                />
              </label>
              <label className="routeLabel" style={{ marginTop: 8 }}>
                Condition
                <input
                  value={asString(selectedEdgeRow.condition)}
                  onChange={(e) => onEdgesChange((prev) => prev.map((row, index) => index === selectedEdgeIndex ? { ...row, condition: e.target.value } : row))}
                />
              </label>
              <div className="row" style={{ marginTop: 8 }}>
                <button onClick={() => {
                  onEdgesChange((prev) => prev.filter((_, index) => index !== selectedEdgeIndex))
                  setSelectedEdgeId('')
                }}>Remove edge</button>
              </div>
            </div>
          )}

          <div style={{ border: '1px solid var(--border-color, #dbe1ea)', borderRadius: 12, padding: 10 }}>
            <div style={{ fontWeight: 700 }}>Topology status</div>
            <div className="muted" style={{ marginTop: 6 }}>
              final participant: {finalParticipantId || '(unset)'}
            </div>
            <div className="muted" style={{ marginTop: 4 }}>
              final owner: {finalOwnerParticipantId || '(unset)'}
            </div>
            {validationErrors.length > 0 && (
              <div style={{ marginTop: 8, color: '#b91c1c', fontSize: 12 }}>
                errors: {validationErrors.slice(0, 4).join(' · ')}
              </div>
            )}
            {validationWarnings.length > 0 && (
              <div style={{ marginTop: 8, color: '#92400e', fontSize: 12 }}>
                warnings: {validationWarnings.slice(0, 4).join(' · ')}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function TopologyCanvasEditor(props: Props) {
  return (
    <ReactFlowProvider>
      <TopologyCanvasEditorInner {...props} />
    </ReactFlowProvider>
  )
}
