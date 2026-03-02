import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import dagre from 'dagre'
import ReactFlow, {
  Background,
  Controls,
  Handle,
  MarkerType,
  Node,
  NodeProps,
  Position,
  ReactFlowInstance,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { copyText } from '../utils/clipboard'
import { api } from '../api'

type Props = {
  threadId: string | null
  nodes: any[]
  edges: any[]
  onOpenOldGraph?: (nodeId: string | null) => void
}

type ExecutionNodeData = {
  node: any
  payload: Record<string, any>
  isRunningStep: boolean
}

type TimelineStep = {
  node: any
  payload: Record<string, any>
  agentId: string
  status: 'queued' | 'running' | 'done' | 'error' | 'unknown'
  startMs: number
  endMs: number | null
}

type FilterState = {
  showMessages: boolean
  showTools: boolean
  showArtifacts: boolean
  showContextNodes: boolean
}

type TimelineZoomPreset = 'auto' | '5m' | '15m' | '30m' | '60m'

type CompiledPreviewState = {
  contextSetId: string
  title: string
  text: string
  loading: boolean
  error: string
}

const NODE_TYPE = { executionNode: ExecutionNodeCard }
const TOOL_TYPES = new Set(['ToolCall', 'ToolResult'])
const ARTIFACT_TYPES = new Set(['Artifact', 'Resource'])
const RUN_STEP_TYPES = new Set(['Run', 'Step'])
const TIMELINE_ZOOM_PRESETS: Array<{ value: TimelineZoomPreset; label: string }> = [
  { value: 'auto', label: 'Auto' },
  { value: '5m', label: '5m' },
  { value: '15m', label: '15m' },
  { value: '30m', label: '30m' },
  { value: '60m', label: '60m' },
]
const TIMELINE_SPAN_MS: Record<Exclude<TimelineZoomPreset, 'auto'>, number> = {
  '5m': 5 * 60 * 1000,
  '15m': 15 * 60 * 1000,
  '30m': 30 * 60 * 1000,
  '60m': 60 * 60 * 1000,
}

function clampNumber(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function parsePayload(node: any): Record<string, any> {
  try {
    const parsed = JSON.parse(node?.payload_json || '{}')
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed
  } catch {
    // ignore malformed payload_json
  }
  return {}
}

function parseMs(value: unknown): number | null {
  if (!value) return null
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value > 1e12 ? value : value * 1000
  }
  if (typeof value !== 'string') return null
  const t = Date.parse(value)
  return Number.isFinite(t) ? t : null
}

function shortText(value: string, max = 96): string {
  const oneLine = (value || '').replace(/\s+/g, ' ').trim()
  if (!oneLine) return ''
  return oneLine.length > max ? `${oneLine.slice(0, max)}…` : oneLine
}

function normalizeStatus(raw: unknown): 'queued' | 'running' | 'done' | 'error' | 'unknown' {
  const status = String(raw || '').trim().toLowerCase()
  if (!status) return 'unknown'
  if (status === 'queued' || status === 'pending' || status === 'waiting') return 'queued'
  if (status === 'running' || status === 'in_progress' || status === 'active') return 'running'
  if (status === 'done' || status === 'completed' || status === 'success' || status === 'ok') return 'done'
  if (status === 'error' || status === 'failed' || status === 'failure') return 'error'
  return 'unknown'
}

function formatTime(valueMs: number | null): string {
  if (!valueMs) return '-'
  const d = new Date(valueMs)
  if (!Number.isFinite(d.getTime())) return '-'
  return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function durationLabel(startMs: number | null, endMs: number | null): string {
  if (!startMs) return '-'
  const end = endMs || Date.now()
  if (end < startMs) return '-'
  const sec = Math.max(0, Math.round((end - startMs) / 1000))
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  const rem = sec % 60
  return `${min}m ${rem}s`
}

function edgeStyle(edgeType: string): { stroke: string; strokeWidth: number; strokeDasharray?: string; animated?: boolean } {
  if (edgeType === 'NEXT') return { stroke: '#667085', strokeWidth: 2 }
  if (edgeType === 'INVOKES') return { stroke: '#0f766e', strokeWidth: 1.8 }
  if (edgeType === 'RETURNS') return { stroke: '#0891b2', strokeWidth: 1.8, strokeDasharray: '6 4' }
  if (edgeType === 'BELONGS_TO_RUN' || edgeType === 'IN_RUN') return { stroke: '#1d4ed8', strokeWidth: 1.9 }
  if (edgeType === 'SPLIT_FROM') return { stroke: '#c026d3', strokeWidth: 1.7, strokeDasharray: '5 4' }
  if (edgeType === 'JOINS') return { stroke: '#7c3aed', strokeWidth: 1.7, strokeDasharray: '2 4' }
  if (edgeType === 'HAS_PART') return { stroke: '#0f766e', strokeWidth: 1.7 }
  if (edgeType === 'ATTACHED_TO') return { stroke: '#0e7490', strokeWidth: 1.6, strokeDasharray: '4 4' }
  return { stroke: '#98a2b3', strokeWidth: 1.4, strokeDasharray: '2 5' }
}

function stepAgent(payload: Record<string, any>): string {
  return String(payload.agent_id || payload.agent || payload.assignee || 'unknown-agent')
}

function stepGoal(node: any, payload: Record<string, any>): string {
  const goal = String(payload.goal || payload.title || node?.text || '').trim()
  return shortText(goal || '(no goal)', 140)
}

function pickContextSetId(payload: Record<string, any>, keys: string[]): string | null {
  for (const key of keys) {
    const value = payload[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return null
}

function pickLensSpec(payload: Record<string, any>): Record<string, any> | null {
  const raw = payload.lens_spec
  if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    return raw as Record<string, any>
  }
  const fallback: Record<string, any> = {}
  if (payload.lens_mode != null) fallback.mode = payload.lens_mode
  if (payload.lens_query != null) fallback.query = payload.lens_query
  if (payload.lens_budget_tokens != null) fallback.budget_tokens = payload.lens_budget_tokens
  if (payload.lens_budget != null && fallback.budget_tokens == null) fallback.budget_tokens = payload.lens_budget
  if (payload.lens_closure != null) fallback.closure = payload.lens_closure
  return Object.keys(fallback).length > 0 ? fallback : null
}

function pickLensAddedCount(payload: Record<string, any>): number {
  if (typeof payload.lens_added_ids_count === 'number' && Number.isFinite(payload.lens_added_ids_count)) {
    return Math.max(0, Math.round(payload.lens_added_ids_count))
  }
  if (typeof payload.lens_added_count === 'number' && Number.isFinite(payload.lens_added_count)) {
    return Math.max(0, Math.round(payload.lens_added_count))
  }
  if (Array.isArray(payload.lens_added_ids)) {
    return payload.lens_added_ids.length
  }
  return 0
}

function sizeForNode(nodeType: string): { width: number; height: number } {
  if (nodeType === 'Run') return { width: 300, height: 120 }
  if (nodeType === 'Step') return { width: 320, height: 148 }
  if (TOOL_TYPES.has(nodeType)) return { width: 280, height: 118 }
  if (ARTIFACT_TYPES.has(nodeType)) return { width: 280, height: 112 }
  if (nodeType === 'Message') return { width: 292, height: 110 }
  return { width: 272, height: 104 }
}

function shouldIncludeNode(node: any, filter: FilterState): boolean {
  const type = String(node?.type || '')
  if (RUN_STEP_TYPES.has(type)) return true
  if (type === 'Message') return filter.showMessages
  if (TOOL_TYPES.has(type)) return filter.showTools
  if (ARTIFACT_TYPES.has(type)) return filter.showArtifacts
  return filter.showContextNodes
}

function pickNodeSummary(node: any, payload: Record<string, any>): string {
  const type = String(node?.type || '')
  if (type === 'Message') {
    return shortText(String(node?.text || payload.summary || '(empty)'))
  }
  if (type === 'Run') {
    return shortText(String(payload.summary || payload.goal || node?.text || ''), 120)
  }
  if (type === 'Step') {
    return stepGoal(node, payload)
  }
  if (type === 'ToolCall' || type === 'ToolResult') {
    return shortText(String(payload.summary || payload.result_summary || node?.text || '(no summary)'))
  }
  if (type === 'Artifact' || type === 'Resource') {
    const fileName = String(payload.file_name || payload.name || '')
    const uri = String(payload.uri || '')
    const summary = String(payload.summary || node?.text || '')
    const head = fileName || uri || 'artifact'
    return shortText(summary ? `${head} - ${summary}` : head)
  }
  return shortText(String(node?.text || payload.summary || '(empty)'))
}

function ExecutionNodeCard({ data, selected }: NodeProps<ExecutionNodeData>) {
  const node = data.node
  const payload = data.payload
  const type = String(node?.type || '')
  const status = normalizeStatus(payload.status)
  const role = type === 'Message' ? String(payload.role || '').trim() : ''
  const runId = String(payload.run_id || payload.id || node?.id || '').slice(0, 8)
  const startedAt = parseMs(payload.started_at)
  const endedAt = parseMs(payload.ended_at)
  const toolName = String(payload.tool_name || payload.name || payload.tool || '')
  const stepStatusClass = status !== 'unknown' ? `status-${status}` : ''

  return (
    <div className={`executionNodeCard ${selected ? 'isSelected' : ''} ${data.isRunningStep ? 'isRunning' : ''}`}>
      <Handle id="target-top" type="target" position={Position.Top} className="executionHandle executionHandle--target" />
      <div className="executionNodeHeader">
        <span className={`pill executionPill executionPill--${type.toLowerCase() || 'default'}`}>{type}</span>
        {type === 'Message' && role && <span className="pill">{role}</span>}
        {type === 'Step' && <span className={`pill executionStatusPill ${stepStatusClass}`}>{status}</span>}
        {type === 'Run' && <span className={`pill executionStatusPill ${stepStatusClass}`}>{status === 'unknown' ? 'run' : status}</span>}
      </div>

      {type === 'Run' && (
        <div className="executionNodeMeta">
          <div><b>run</b> {runId || '-'}</div>
          <div>started {formatTime(startedAt)}</div>
        </div>
      )}
      {type === 'Step' && (
        <div className="executionNodeMeta">
          <div><b>agent</b> {stepAgent(payload)}</div>
          <div className="executionNodeGoal">{stepGoal(node, payload)}</div>
          <div>duration {durationLabel(startedAt, endedAt)}</div>
        </div>
      )}
      {(type === 'ToolCall' || type === 'ToolResult') && (
        <div className="executionNodeMeta">
          <div><b>tool</b> {toolName || '-'}</div>
          <div>{pickNodeSummary(node, payload)}</div>
        </div>
      )}
      {(type === 'Artifact' || type === 'Resource') && (
        <div className="executionNodeMeta">
          <div><b>file</b> {String(payload.file_name || payload.name || payload.uri || '-')}</div>
          <div>{pickNodeSummary(node, payload)}</div>
        </div>
      )}
      {!RUN_STEP_TYPES.has(type) && !TOOL_TYPES.has(type) && !ARTIFACT_TYPES.has(type) && type !== 'Message' && (
        <div className="executionNodeMeta">{pickNodeSummary(node, payload)}</div>
      )}

      <Handle id="source-bottom" type="source" position={Position.Bottom} className="executionHandle executionHandle--source" />
    </div>
  )
}

export default function ExecutionPanel({ threadId, nodes, edges, onOpenOldGraph }: Props) {
  const [filter, setFilter] = useState<FilterState>({
    showMessages: false,
    showTools: false,
    showArtifacts: false,
    showContextNodes: false,
  })
  const [timelineZoom, setTimelineZoom] = useState<TimelineZoomPreset>('auto')
  const [followActive, setFollowActive] = useState(true)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [copyState, setCopyState] = useState('')
  const [compiledPreview, setCompiledPreview] = useState<CompiledPreviewState | null>(null)
  const [traceExportBusy, setTraceExportBusy] = useState(false)
  const [traceExportError, setTraceExportError] = useState('')
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null)
  const lastFittedLayoutRef = useRef('')
  const lastFollowKeyRef = useRef('')

  const nodesById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes])
  const payloadById = useMemo(() => {
    const out = new Map<string, Record<string, any>>()
    for (const node of nodes) out.set(node.id, parsePayload(node))
    return out
  }, [nodes])

  const runningStepNodes = useMemo(() => {
    return nodes
      .filter((node) => node.type === 'Step')
      .filter((node) => normalizeStatus(payloadById.get(node.id)?.status) === 'running')
  }, [nodes, payloadById])

  const primaryRunningStepId = useMemo(() => {
    if (runningStepNodes.length === 0) return null
    const sorted = [...runningStepNodes].sort((a, b) => {
      const pa = payloadById.get(a.id) || {}
      const pb = payloadById.get(b.id) || {}
      const ta = parseMs(pa.started_at) || parseMs(a.created_at) || 0
      const tb = parseMs(pb.started_at) || parseMs(b.created_at) || 0
      if (ta !== tb) return tb - ta
      return String(b.id).localeCompare(String(a.id))
    })
    return sorted[0]?.id || null
  }, [runningStepNodes, payloadById])

  const runningSignature = useMemo(() => {
    const entries = runningStepNodes
      .map((node) => {
        const payload = payloadById.get(node.id) || {}
        return `${node.id}:${String(payload.started_at || '')}:${String(payload.status || '')}`
      })
      .sort()
    return entries.join('|')
  }, [runningStepNodes, payloadById])

  const filteredNodes = useMemo(() => nodes.filter((node) => shouldIncludeNode(node, filter)), [nodes, filter])
  const filteredNodeIdSet = useMemo(() => new Set(filteredNodes.map((node) => node.id)), [filteredNodes])
  const filteredEdges = useMemo(
    () => edges.filter((edge) => filteredNodeIdSet.has(edge.from_id) && filteredNodeIdSet.has(edge.to_id)),
    [edges, filteredNodeIdSet],
  )

  const rfNodes = useMemo<Node[]>(() => {
    if (filteredNodes.length === 0) return []

    const graph = new dagre.graphlib.Graph()
    graph.setGraph({
      rankdir: 'LR',
      ranksep: 96,
      nodesep: 46,
      edgesep: 24,
      marginx: 22,
      marginy: 22,
      acyclicer: 'greedy',
    })
    graph.setDefaultEdgeLabel(() => ({}))

    for (const node of filteredNodes) {
      const { width, height } = sizeForNode(node.type)
      graph.setNode(node.id, { width, height })
    }
    for (const edge of filteredEdges) {
      graph.setEdge(edge.from_id, edge.to_id)
    }
    dagre.layout(graph)

    return filteredNodes.map((node) => {
      const payload = payloadById.get(node.id) || {}
      const size = sizeForNode(node.type)
      const position = graph.node(node.id) as { x: number; y: number } | undefined
      const x = position ? position.x - size.width / 2 : 0
      const y = position ? position.y - size.height / 2 : 0
      return {
        id: node.id,
        type: 'executionNode',
        position: { x, y },
        draggable: false,
        data: {
          node,
          payload,
          isRunningStep: node.type === 'Step' && normalizeStatus(payload.status) === 'running',
        },
        style: { width: size.width },
      }
    })
  }, [filteredNodes, filteredEdges, payloadById])

  const rfEdges = useMemo(() => {
    return filteredEdges.map((edge) => {
      const style = edgeStyle(String(edge.type || ''))
      return {
        id: edge.id,
        source: edge.from_id,
        target: edge.to_id,
        type: 'smoothstep',
        label: edge.type === 'NEXT' ? undefined : edge.type,
        animated: Boolean(style.animated),
        markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18, color: style.stroke },
        style: {
          stroke: style.stroke,
          strokeWidth: style.strokeWidth,
          strokeDasharray: style.strokeDasharray,
        },
      }
    })
  }, [filteredEdges])

  const nodeCenterById = useMemo(() => {
    const out = new Map<string, { x: number; y: number }>()
    for (const node of rfNodes) {
      const original = nodesById.get(node.id)
      if (!original) continue
      const size = sizeForNode(original.type)
      out.set(node.id, { x: node.position.x + size.width / 2, y: node.position.y + size.height / 2 })
    }
    return out
  }, [rfNodes, nodesById])

  const selectedNode = selectedNodeId ? nodesById.get(selectedNodeId) || null : null
  const selectedPayload = selectedNode ? payloadById.get(selectedNode.id) || {} : {}
  const selectedIsStep = selectedNode?.type === 'Step'
  const sharedContextSetId = selectedIsStep
    ? pickContextSetId(selectedPayload, ['shared_context_set_id', 'shared_ctx_set_id', 'base_context_set_id', 'context_set_id'])
    : null
  const lensContextSetId = selectedIsStep
    ? pickContextSetId(selectedPayload, ['lens_context_set_id', 'lens_ctx_set_id', 'step_context_set_id', 'agent_context_set_id'])
    : null
  const lensSpec = selectedIsStep ? pickLensSpec(selectedPayload) : null
  const lensAddedIdsCount = selectedIsStep ? pickLensAddedCount(selectedPayload) : 0
  const selectedRunId = useMemo(() => {
    if (!selectedNode) return ''
    if (selectedNode.type === 'Run') {
      return String(selectedNode.id || '').trim()
    }
    if (selectedNode.type !== 'Step') return ''
    const fromPayload = String(selectedPayload.run_id || '').trim()
    if (fromPayload) return fromPayload
    for (const edge of edges) {
      if (edge.from_id === selectedNode.id) {
        const target = nodesById.get(edge.to_id)
        if (target?.type === 'Run') return String(target.id || '').trim()
      }
      if (edge.to_id === selectedNode.id) {
        const source = nodesById.get(edge.from_id)
        if (source?.type === 'Run') return String(source.id || '').trim()
      }
    }
    return ''
  }, [selectedNode, selectedPayload, edges, nodesById])

  const layoutSignature = useMemo(() => {
    const nodeIds = filteredNodes.map((node) => node.id).join(',')
    const edgeIds = filteredEdges.map((edge) => edge.id).join(',')
    return `${nodeIds}|${edgeIds}`
  }, [filteredNodes, filteredEdges])

  const focusNode = useCallback((nodeId: string, zoom = 1.06) => {
    if (!rfInstance) return
    const center = nodeCenterById.get(nodeId)
    if (!center) return
    rfInstance.setCenter(center.x, center.y, { zoom, duration: 240 })
  }, [rfInstance, nodeCenterById])

  useEffect(() => {
    if (!rfInstance || rfNodes.length === 0) return
    if (layoutSignature === lastFittedLayoutRef.current) return
    lastFittedLayoutRef.current = layoutSignature
    rfInstance.fitView({ padding: 0.18, duration: 220 })
  }, [rfInstance, rfNodes.length, layoutSignature])

  useEffect(() => {
    if (selectedNodeId && nodesById.has(selectedNodeId)) return
    if (primaryRunningStepId) {
      setSelectedNodeId(primaryRunningStepId)
      return
    }
    const latestStep = [...nodes]
      .filter((node) => node.type === 'Step')
      .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))[0]
    if (latestStep?.id) {
      setSelectedNodeId(latestStep.id)
      return
    }
    setSelectedNodeId(null)
  }, [selectedNodeId, nodesById, primaryRunningStepId, nodes])

  useEffect(() => {
    if (!followActive) return
    if (!primaryRunningStepId) return
    if (!rfInstance) return
    const nextKey = `${primaryRunningStepId}|${runningSignature}`
    if (nextKey === lastFollowKeyRef.current) return
    lastFollowKeyRef.current = nextKey
    setSelectedNodeId(primaryRunningStepId)
    focusNode(primaryRunningStepId, 1.1)
  }, [followActive, primaryRunningStepId, runningSignature, rfInstance, focusNode])

  const timelineSteps = useMemo<TimelineStep[]>(() => {
    const out: TimelineStep[] = []
    for (const node of nodes) {
      if (node.type !== 'Step') continue
      const payload = payloadById.get(node.id) || {}
      const started = parseMs(payload.started_at)
      const ended = parseMs(payload.ended_at)
      if (!started && !ended) continue
      out.push({
        node,
        payload,
        agentId: stepAgent(payload),
        status: normalizeStatus(payload.status),
        startMs: started || ended || Date.now(),
        endMs: ended,
      })
    }
    return out.sort((a, b) => a.startMs - b.startMs)
  }, [nodes, payloadById])

  const timelineRows = useMemo(() => {
    const byAgent = new Map<string, TimelineStep[]>()
    for (const step of timelineSteps) {
      const arr = byAgent.get(step.agentId) || []
      arr.push(step)
      byAgent.set(step.agentId, arr)
    }
    return [...byAgent.entries()]
      .map(([agentId, steps]) => ({ agentId, steps: steps.sort((a, b) => a.startMs - b.startMs) }))
      .sort((a, b) => a.agentId.localeCompare(b.agentId))
  }, [timelineSteps])

  const timelineWindow = useMemo(() => {
    const now = Date.now()
    const fixedSpanMs = timelineZoom === 'auto' ? null : TIMELINE_SPAN_MS[timelineZoom]

    if (timelineSteps.length === 0) {
      const spanMs = fixedSpanMs || (15 * 60 * 1000)
      const start = now - spanMs
      return { start, end: now, now, spanMs, observedSpanMs: 0, autoSpanMs: spanMs }
    }
    const minStart = Math.min(...timelineSteps.map((step) => step.startMs))
    const maxEnd = Math.max(...timelineSteps.map((step) => step.endMs || now), now)
    const observedSpan = Math.max(1, maxEnd - minStart)
    const autoSpanMs = Math.round(clampNumber(observedSpan * 1.4, 5 * 60 * 1000, 60 * 60 * 1000))
    const spanMs = fixedSpanMs || autoSpanMs
    const end = Math.max(now, maxEnd)
    const start = end - spanMs
    return { start, end, now, spanMs, observedSpanMs: observedSpan, autoSpanMs }
  }, [timelineSteps, timelineZoom])

  const relatedStepNodes = useMemo(() => {
    if (!selectedNode || selectedNode.type !== 'Step') return []
    const targetTypes = new Set(['ToolCall', 'ToolResult', 'Artifact', 'Resource'])
    const byId = new Map<string, { node: any; relation: string }>()
    const directToolCalls: string[] = []

    for (const edge of edges) {
      if (edge.from_id !== selectedNode.id) continue
      const target = nodesById.get(edge.to_id)
      if (!target || !targetTypes.has(target.type)) continue
      if (!byId.has(target.id)) {
        byId.set(target.id, { node: target, relation: String(edge.type || 'LINK') })
      }
      if (target.type === 'ToolCall') directToolCalls.push(target.id)
    }

    if (directToolCalls.length > 0) {
      const callSet = new Set(directToolCalls)
      for (const edge of edges) {
        if (!callSet.has(edge.from_id)) continue
        const target = nodesById.get(edge.to_id)
        if (!target || !targetTypes.has(target.type)) continue
        if (!byId.has(target.id)) {
          byId.set(target.id, { node: target, relation: `via ToolCall/${String(edge.type || 'LINK')}` })
        }
      }
    }

    return [...byId.values()].sort((a, b) => String(a.node.created_at || '').localeCompare(String(b.node.created_at || '')))
  }, [selectedNode, edges, nodesById])

  const runningAgentIds = useMemo(() => {
    const out = new Set<string>()
    for (const node of runningStepNodes) {
      out.add(stepAgent(payloadById.get(node.id) || {}))
    }
    return out
  }, [runningStepNodes, payloadById])

  const handleSelectNode = useCallback((nodeId: string) => {
    setSelectedNodeId(nodeId)
    focusNode(nodeId, 1.07)
  }, [focusNode])

  async function handleCopyNodeJson() {
    if (!selectedNode) return
    const payload = payloadById.get(selectedNode.id) || {}
    const ok = await copyText(JSON.stringify({ ...selectedNode, payload }, null, 2))
    setCopyState(ok ? 'Node JSON copied' : 'Copy failed')
  }

  async function handleCopyNodeText() {
    if (!selectedNode) return
    const ok = await copyText(String(selectedNode.text || ''))
    setCopyState(ok ? 'Node text copied' : 'Copy failed')
  }

  async function openCompiledPreview(contextSetId: string, title: string) {
    const cleanId = (contextSetId || '').trim()
    if (!cleanId) return
    setCompiledPreview({
      contextSetId: cleanId,
      title,
      text: '',
      loading: true,
      error: '',
    })
    try {
      const out = await api.ctxCompiled(cleanId, false)
      setCompiledPreview({
        contextSetId: cleanId,
        title,
        text: String(out?.compiled_text || ''),
        loading: false,
        error: '',
      })
    } catch (e: any) {
      setCompiledPreview({
        contextSetId: cleanId,
        title,
        text: '',
        loading: false,
        error: e?.message || String(e),
      })
    }
  }

  async function handleCopyCompiledPreview() {
    if (!compiledPreview) return
    const ok = await copyText(compiledPreview.text || '')
    setCopyState(ok ? 'Compiled text copied' : 'Copy failed')
  }

  async function handleTraceExport() {
    if (!threadId || traceExportBusy) return
    setTraceExportError('')
    setTraceExportBusy(true)
    try {
      const out = await api.traceExport(threadId, {
        include_compiled: true,
        max_compiled_chars: 10000,
        run_id: selectedRunId || null,
        format: 'zip',
      })
      const objectUrl = URL.createObjectURL(out.blob)
      try {
        const anchor = document.createElement('a')
        anchor.href = objectUrl
        anchor.download = out.filename || `trace_export_${threadId}.zip`
        document.body.appendChild(anchor)
        anchor.click()
        anchor.remove()
      } finally {
        URL.revokeObjectURL(objectUrl)
      }
    } catch (e: any) {
      setTraceExportError(e?.message || String(e))
    } finally {
      setTraceExportBusy(false)
    }
  }

  return (
    <div className="executionLayout">
      <div className="executionGraphCard card">
        <div className="executionToolbar">
          <div className="executionToolbarLeft">
            <span className="pill">Execution Graph</span>
            <label><input type="checkbox" checked={filter.showMessages} onChange={(e) => setFilter((prev) => ({ ...prev, showMessages: e.target.checked }))} /> Show Messages</label>
            <label><input type="checkbox" checked={filter.showTools} onChange={(e) => setFilter((prev) => ({ ...prev, showTools: e.target.checked }))} /> Show Tools</label>
            <label><input type="checkbox" checked={filter.showArtifacts} onChange={(e) => setFilter((prev) => ({ ...prev, showArtifacts: e.target.checked }))} /> Show Artifacts</label>
            <label><input type="checkbox" checked={filter.showContextNodes} onChange={(e) => setFilter((prev) => ({ ...prev, showContextNodes: e.target.checked }))} /> Show Context Nodes</label>
          </div>
          <div className="executionToolbarRight">
            <label><input type="checkbox" checked={followActive} onChange={(e) => setFollowActive(e.target.checked)} /> Follow Active</label>
            {selectedRunId && <span className="muted">run: {selectedRunId.slice(0, 8)}</span>}
            <button onClick={() => void handleTraceExport()} disabled={!threadId || traceExportBusy}>
              {traceExportBusy && <span className="executionSpinner" />}
              {traceExportBusy ? 'Exporting...' : 'Export trace'}
            </button>
            <button onClick={() => rfInstance?.fitView({ padding: 0.18, duration: 220 })}>Fit</button>
          </div>
        </div>
        {traceExportError && <div className="executionToolbarError">{traceExportError}</div>}
        {runningStepNodes.length > 0 && (
          <div className="executionRunningStrip">
            running {runningStepNodes.length} step(s): {runningStepNodes.map((node) => stepAgent(payloadById.get(node.id) || {})).join(', ')}
          </div>
        )}
        <div className="executionGraphCanvas">
          <ReactFlow
            nodes={rfNodes}
            edges={rfEdges}
            nodeTypes={NODE_TYPE}
            onInit={setRfInstance}
            onNodeClick={(_, node) => handleSelectNode(node.id)}
            onPaneClick={() => setSelectedNodeId(null)}
            nodesDraggable={false}
            nodesConnectable={false}
            fitView
          >
            <Background gap={18} color="#d6dee8" />
            <Controls />
          </ReactFlow>
        </div>
      </div>

      <div className="executionRightColumn">
        <div className="executionTimelineCard card">
          <div className="executionSectionTitleRow">
            <h3>Timeline</h3>
            <div className="executionTimelineControls">
              <label className="muted" htmlFor="execution-timeline-zoom">Zoom</label>
              <select
                id="execution-timeline-zoom"
                value={timelineZoom}
                onChange={(e) => setTimelineZoom(e.target.value as TimelineZoomPreset)}
              >
                {TIMELINE_ZOOM_PRESETS.map((preset) => (
                  <option key={preset.value} value={preset.value}>{preset.label}</option>
                ))}
              </select>
              <span className="muted">
                {formatTime(timelineWindow.start)} - {formatTime(timelineWindow.end)}
              </span>
            </div>
          </div>
          {timelineRows.length === 0 ? (
            <div className="muted">started_at / ended_at 정보가 있는 Step이 아직 없습니다.</div>
          ) : (
            <div className="executionTimelineRows">
              {timelineRows.map((row) => {
                const nowLeft = ((timelineWindow.now - timelineWindow.start) / timelineWindow.spanMs) * 100
                return (
                  <div className="executionTimelineRow" key={row.agentId}>
                    <div className={`executionTimelineAgent ${runningAgentIds.has(row.agentId) ? 'isRunning' : ''}`}>{row.agentId}</div>
                    <div className="executionTimelineTrack">
                      <div className="executionNowLine" style={{ left: `${Math.max(0, Math.min(100, nowLeft))}%` }} />
                      {row.steps.map((step) => {
                        const rawStart = step.startMs
                        const rawEnd = step.endMs || timelineWindow.now
                        if (rawEnd <= timelineWindow.start || rawStart >= timelineWindow.end) return null

                        const start = Math.max(rawStart, timelineWindow.start)
                        const end = Math.min(rawEnd, timelineWindow.end)
                        const leftPct = ((start - timelineWindow.start) / timelineWindow.spanMs) * 100
                        const widthPctRaw = ((end - start) / timelineWindow.spanMs) * 100
                        const widthPct = Math.max(0.9, widthPctRaw)
                        const selected = selectedNodeId === step.node.id
                        const fullGoal = String(step.payload.goal || step.payload.title || step.node.text || '(no goal)')
                        const tinyLabel = widthPctRaw < 2

                        return (
                          <button
                            key={step.node.id}
                            className={`executionTimelineBar status-${step.status} ${selected ? 'isSelected' : ''}`}
                            style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
                            onClick={() => handleSelectNode(step.node.id)}
                            title={`${fullGoal} (${formatTime(step.startMs)} ~ ${formatTime(step.endMs || timelineWindow.now)})`}
                          >
                            {tinyLabel ? (
                              <span className="executionTimelineBarDot">•</span>
                            ) : (
                              <span className="executionTimelineBarLabel">{stepGoal(step.node, step.payload)}</span>
                            )}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        <div className="executionInspectorCard card">
          <div className="executionSectionTitleRow">
            <h3>Inspector</h3>
            <span className="muted">{selectedNode ? selectedNode.id.slice(0, 8) : 'No selection'}</span>
          </div>

          {!selectedNode && <div className="muted">그래프 또는 타임라인에서 노드를 선택하세요.</div>}

          {selectedNode && (
            <>
              <div className="executionInspectorActions">
                <button onClick={handleCopyNodeJson}>Copy node JSON</button>
                <button onClick={handleCopyNodeText}>Copy node text</button>
                {onOpenOldGraph && <button onClick={() => onOpenOldGraph(selectedNode.id)}>Open in old Graph 탭</button>}
              </div>
              {copyState && <div className="muted">{copyState}</div>}

              <div className="executionInspectorBlock">
                <div><b>{selectedNode.type}</b> <span className="muted">{selectedNode.created_at}</span></div>
                <pre>{String(selectedNode.text || '(empty)')}</pre>
              </div>

              {selectedNode.type === 'Step' && (
                <div className="executionInspectorBlock">
                  <div><b>agent_id</b> {stepAgent(selectedPayload)}</div>
                  <div><b>goal</b> {stepGoal(selectedNode, selectedPayload)}</div>
                  <div><b>status</b> {normalizeStatus(selectedPayload.status)}</div>
                  <div><b>started_at</b> {String(selectedPayload.started_at || '-')}</div>
                  <div><b>ended_at</b> {String(selectedPayload.ended_at || '-')}</div>
                  <div><b>error</b> {String(selectedPayload.error || selectedPayload.error_message || '-')}</div>
                  <div><b>outputs</b> {shortText(String(selectedPayload.outputs || selectedPayload.output || '-'), 200)}</div>
                </div>
              )}

              {selectedNode.type === 'Step' && (
                <div className="executionInspectorBlock">
                  <div><b>shared_context_set_id</b> {sharedContextSetId || '-'}</div>
                  <div><b>lens_context_set_id</b> {lensContextSetId || '-'}</div>
                  <div><b>lens_added_ids_count</b> {lensAddedIdsCount}</div>
                  <div><b>lens_spec</b></div>
                  <pre>{lensSpec ? JSON.stringify(lensSpec, null, 2) : '-'}</pre>
                  <div className="executionInspectorActions" style={{ marginTop: 6, marginBottom: 0 }}>
                    <button
                      onClick={() => sharedContextSetId && openCompiledPreview(sharedContextSetId, 'Shared Compiled')}
                      disabled={!sharedContextSetId}
                    >
                      Open shared compiled
                    </button>
                    <button
                      onClick={() => lensContextSetId && openCompiledPreview(lensContextSetId, 'Lens Compiled')}
                      disabled={!lensContextSetId}
                    >
                      Open lens compiled
                    </button>
                  </div>
                </div>
              )}

              {selectedNode.type === 'Step' && (
                <div className="executionInspectorBlock">
                  <div><b>Related Tool/Artifact Nodes</b></div>
                  {relatedStepNodes.length === 0 ? (
                    <div className="muted">연결된 ToolCall/ToolResult/Artifact/Resource가 없습니다.</div>
                  ) : (
                    <div className="executionRelatedList">
                      {relatedStepNodes.map((item) => (
                        <button key={item.node.id} className="executionRelatedItem" onClick={() => handleSelectNode(item.node.id)}>
                          <span className={`pill executionPill executionPill--${String(item.node.type || '').toLowerCase()}`}>{item.node.type}</span>
                          <span>{pickNodeSummary(item.node, payloadById.get(item.node.id) || {})}</span>
                          <span className="muted">{item.relation}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}

              <div className="executionInspectorBlock">
                <div><b>payload_json</b></div>
                <pre>{JSON.stringify(selectedPayload, null, 2)}</pre>
              </div>
            </>
          )}
        </div>
      </div>

      {compiledPreview && (
        <div className="modalOverlay" onClick={() => setCompiledPreview(null)}>
          <div className="modalCard executionCompiledModal" onClick={(e) => e.stopPropagation()}>
            <div className="row modalHeader">
              <h3 style={{ margin: 0 }}>{compiledPreview.title}</h3>
              <button onClick={() => setCompiledPreview(null)}>Close</button>
            </div>
            <div className="muted" style={{ marginBottom: 8 }}>
              ContextSet: {compiledPreview.contextSetId}
            </div>
            <div className="executionInspectorActions">
              <button onClick={handleCopyCompiledPreview} disabled={!compiledPreview.text}>Copy compiled text</button>
            </div>
            {compiledPreview.loading && <div className="muted">Loading compiled context...</div>}
            {!compiledPreview.loading && compiledPreview.error && (
              <div className="muted" style={{ color: '#b91c1c' }}>{compiledPreview.error}</div>
            )}
            {!compiledPreview.loading && !compiledPreview.error && (
              <pre className="executionCompiledText">{compiledPreview.text || '(empty)'}</pre>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
