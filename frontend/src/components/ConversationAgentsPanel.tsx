import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api, diffThreadTeamManifest, exportThreadTeamManifest, installThreadTeamManifest, listThreadTeamBlueprintTemplates, validateThreadTeamManifest } from '../api'
import { copyText } from '../utils/clipboard'
import TopologyCanvasEditor from './TopologyCanvasEditor'

type Props = {
  threadId: string | null
  refreshKey?: number
}

type AgentItem = {
  id: string
  name: string
  visibility: 'private' | 'unlisted' | 'public'
  model: string
  source_agent_id: string | null
}

type ConversationMember = {
  id: string
  agent_id: string
  enabled: boolean
  order_index: number
  overrides_json: Record<string, unknown>
  agent: AgentItem
}

type ConversationState = {
  id: string
  thread_id: string
  owner_user_id: string
  agents: ConversationMember[]
}

type KnowledgeDocFormRow = {
  doc_id: string
  file_name: string
  title: string
  purpose: string
  write_hint: string
  target_roles: string
}

type KnowledgeEditorFormState = {
  profileId: string
  displayName: string
  docs: KnowledgeDocFormRow[]
  stableSlots: string[]
  mutableSlots: string[]
  immutableFiles: string[]
}

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

type TopologyEditorFormState = {
  pattern: string
  executionPattern: string
  finalParticipantId: string
  finalOwnerParticipantId: string
  participants: TopologyParticipantFormRow[]
  nodes: TopologyNodeFormRow[]
  edges: TopologyEdgeFormRow[]
}

type RuntimeExecutionEditorFormState = {
  checkpointWriteOnTurnEnd: boolean
  checkpointWriteOnApprovalPause: boolean
  checkpointWriteOnResume: boolean
  checkpointExposeRestoreContextToAgents: boolean
  continuousImprovementEnabled: boolean
  continuousImprovementMode: string
  continuousImprovementMaxTurns: string
  continuousImprovementMaxTotalActions: string
  continuousImprovementMinTurns: string
  continuousImprovementProgressEachTurn: boolean
  continuousImprovementStopSignals: string
  approvalMatrixDraft: string
  codexSandboxMode: string
  codexApprovalPolicy: string
  codexProfile: string
  codexAddDirs: string
  codexMcpServersDraft: string
  geminiApprovalMode: string
  geminiSettingsOverwrite: string
  geminiExtraEnvDraft: string
  geminiMcpServersDraft: string
}

type ThreadSummary = {
  id: string
  title?: string | null
  service_id?: string | null
}

type GraphResourceNode = {
  id: string
  type?: string | null
  text?: string | null
  payload_json?: string | null
  created_at?: string | null
}

type TeamCatalogItem = {
  nodeId: string
  createdAt: string
  title: string
  summary: string
  tags: string[]
  recommendedFor: string[]
  manifest: Record<string, any>
}

type TeamBlueprintTemplateItem = {
  taskArchetype: string
  title: string
  description: string
  tags: string[]
  goodFor: string[]
  badFor: string[]
  blueprintDocument: Record<string, any>
}

function asString(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return ''
}

function asBool(value: unknown): boolean {
  return value === true
}

function normalizeVisibility(value: unknown): 'private' | 'unlisted' | 'public' {
  const clean = asString(value).toLowerCase()
  if (clean === 'public') return 'public'
  if (clean === 'unlisted') return 'unlisted'
  return 'private'
}

function asObject(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  return value as Record<string, unknown>
}

const TEAM_CATALOG_THREAD_TITLES = ['teams:catalog', 'agent-teams'] as const
const TEAM_BLUEPRINT_RESOURCE_KIND = 'agent_team_blueprint'

function normalizeTitle(value?: string | null): string {
  return asString(value).toLowerCase()
}

function parsePayloadJson(value?: string | null): Record<string, unknown> {
  try {
    const parsed = JSON.parse(value || '{}')
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed as Record<string, unknown>
  } catch {
    // ignore malformed payload
  }
  return {}
}

function parseManifestJson(value?: string | null): Record<string, any> {
  try {
    const parsed = JSON.parse(value || '{}')
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed as Record<string, any>
  } catch {
    // ignore malformed manifest
  }
  return {}
}

function toStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((entry) => asString(entry)).filter(Boolean)
}

function deriveTeamBlueprintTitle(manifest: Record<string, any> | null): string {
  const blueprint = asObject(manifest?.blueprint)
  const team = asObject(manifest?.team || blueprint?.team_seed || manifest?.team_config?.active_team || manifest?.team_config?.pending_team)
  const structure = asObject(blueprint?.structure || manifest?.structure || manifest?.structure_v2 || asObject(team).structure || asObject(team).structure_v2)
  const participants = Array.isArray(structure?.participants) ? structure.participants : []
  return (
    asString(manifest?.title)
    || asString(manifest?.thread?.title)
    || asString(team?.team_name)
    || asString(team?.display_name)
    || (participants.length > 0 ? `${participants.length}-agent team` : 'Agent Team Template')
  )
}

function deriveTeamBlueprintSummary(manifest: Record<string, any> | null): string {
  const blueprint = asObject(manifest?.blueprint)
  const team = asObject(manifest?.team || blueprint?.team_seed || manifest?.team_config?.active_team || manifest?.team_config?.pending_team)
  const structure = asObject(blueprint?.structure || manifest?.structure || manifest?.structure_v2 || asObject(team).structure || asObject(team).structure_v2)
  const pattern = asString(structure?.topology?.pattern || structure?.execution_pattern || team?.interaction_spec?.execution_pattern)
  const participants = Array.isArray(structure?.participants) ? structure.participants : []
  const labels = participants
    .map((entry) => asString(asObject(entry).role) || asString(asObject(entry).label) || asString(asObject(entry).participant_id))
    .filter(Boolean)
    .slice(0, 4)
  if (labels.length > 0) {
    return `${labels.join(', ')} 중심 ${pattern || 'hybrid'} topology team`
  }
  return pattern ? `${pattern} topology team template` : 'Reusable agent team template'
}

function resourceNodeToTeamCatalogItem(node: GraphResourceNode): TeamCatalogItem | null {
  if ((node.type || '') !== 'Resource') return null
  const payload = parsePayloadJson(node.payload_json)
  if (asString(payload.resource_kind) !== TEAM_BLUEPRINT_RESOURCE_KIND) return null
  const manifest = parseManifestJson(node.text)
  if (!manifest || Object.keys(manifest).length === 0) return null
  const title = asString(payload.title) || deriveTeamBlueprintTitle(manifest) || `team-${node.id.slice(0, 8)}`
  const summary = asString(payload.summary) || deriveTeamBlueprintSummary(manifest)
  return {
    nodeId: node.id,
    createdAt: asString(node.created_at),
    title,
    summary,
    tags: [...new Set(toStringList(payload.tags))],
    recommendedFor: [...new Set(toStringList(payload.recommended_for || payload.good_for || payload.use_cases))],
    manifest,
  }
}


function normalizeTemplateItem(raw: any): TeamBlueprintTemplateItem | null {
  if (!raw || typeof raw !== 'object') return null
  const blueprintDocument = asObject(raw.blueprint_document || raw.blueprintDocument)
  if (!Object.keys(blueprintDocument).length) return null
  return {
    taskArchetype: asString(raw.task_archetype || raw.taskArchetype) || 'implementation',
    title: asString(raw.title) || 'Blueprint Template',
    description: asString(raw.description),
    tags: [...new Set(toStringList(raw.tags))],
    goodFor: [...new Set(toStringList(raw.good_for || raw.goodFor))],
    badFor: [...new Set(toStringList(raw.bad_for || raw.badFor))],
    blueprintDocument: blueprintDocument as Record<string, any>,
  }
}

function normalizeAgent(raw: any): AgentItem | null {
  if (!raw || typeof raw !== 'object') return null
  const id = asString(raw.id)
  if (!id) return null
  return {
    id,
    name: asString(raw.name) || `agent-${id.slice(0, 8)}`,
    visibility: normalizeVisibility(raw.visibility),
    model: asString(raw.model),
    source_agent_id: asString(raw.source_agent_id) || null,
  }
}

function normalizeConversation(raw: any): ConversationState | null {
  if (!raw || typeof raw !== 'object') return null
  const id = asString(raw.id)
  const threadId = asString(raw.thread_id)
  if (!id || !threadId) return null
  const rows = Array.isArray(raw.agents) ? raw.agents : []
  const members: ConversationMember[] = rows
    .map((row: any) => {
      const agent = normalizeAgent(row?.agent)
      const agentId = asString(row?.agent_id || agent?.id)
      if (!agent || !agentId) return null
      return {
        id: asString(row?.id),
        agent_id: agentId,
        enabled: asBool(row?.enabled),
        order_index: Number.isFinite(Number(row?.order_index)) ? Number(row.order_index) : 0,
        overrides_json: asObject(row?.overrides_json),
        agent,
      }
    })
    .filter((row: ConversationMember | null): row is ConversationMember => Boolean(row))
    .sort((a, b) => a.order_index - b.order_index)
  return {
    id,
    thread_id: threadId,
    owner_user_id: asString(raw.owner_user_id),
    agents: members,
  }
}

function lineageKeyForAgent(agent: Pick<AgentItem, 'id' | 'source_agent_id'>): string {
  const sourceAgentId = asString(agent.source_agent_id)
  return sourceAgentId || asString(agent.id)
}

function commandSuggestionList({
  manifest,
  applyState,
}: {
  manifest: Record<string, any> | null
  applyState: 'active' | 'pending'
}): string[] {
  const out: string[] = []
  const row = manifest || {}
  const installProposalState = asObject(row.install_proposal_state)
  const installProposal = asObject(row.install_proposal)
  const credentialBinding = asObject(row.credential_binding_state)
  const requirements = asObject(row.requirements)
  const patternConflict = asObject(row.pattern_conflict)
  const pendingCredentialKeys = Array.isArray(installProposal?.actions?.credential_requests)
    ? installProposal.actions.credential_requests
        .map((entry: any) => asString(entry?.credential_key || entry?.credentialKey || entry?.key))
        .filter(Boolean)
    : []

  out.push(`/team pull --${applyState}`)
  out.push(`/team push --${applyState}`)
  if (applyState === 'pending') out.push('/team apply')
  if (asString(installProposalState.status)) out.push('/team proposal')
  if ((Number(credentialBinding?.summary?.bound_count || 0) > 0) || pendingCredentialKeys.length > 0) out.push('/credential pending')
  if (pendingCredentialKeys.length > 0) {
    for (const key of pendingCredentialKeys.slice(0, 3)) out.push(`/credential set ${key} <secret> --resume`)
  }
  if (Array.isArray(requirements.tools) && requirements.tools.length > 0) out.push('/team requirements')
  if (asString(patternConflict.classification) === 'structure_override_required') out.push('/team refine <자연어 수정>')

  return [...new Set(out)]
}


function prettyJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2)
}

function parseJsonObjectDraft(raw: string, label: string): Record<string, any> {
  const clean = (raw || '').trim()
  if (!clean) return {}
  const value = JSON.parse(clean)
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${label} JSON은 object여야 합니다.`)
  }
  return value as Record<string, any>
}

function extractKnowledgeEditorsFromManifest(manifest: Record<string, any> | null): { knowledgeSurface: Record<string, any>; memoryPolicy: Record<string, any> } {
  const structure = asObject(manifest?.blueprint?.structure || manifest?.structure || manifest?.structure_v2 || manifest?.team?.structure || manifest?.team?.structure_v2)
  const knowledgeSurface = asObject(structure?.knowledge_surface || structure?.knowledgeSurface || manifest?.team?.knowledge_surface || manifest?.team?.knowledgeSurface || manifest?.team?.knowledge_base_profile)
  const memoryPolicy = asObject(structure?.memory_policy || structure?.memoryPolicy || manifest?.team?.memory_policy || manifest?.team?.memoryPolicy || knowledgeSurface?.memory_policy)
  return { knowledgeSurface, memoryPolicy }
}

function buildKnowledgeBaseProfileFromEditors(knowledgeSurface: Record<string, any>, memoryPolicy: Record<string, any>): Record<string, any> {
  return {
    profile_id: asString(knowledgeSurface?.profile_id || knowledgeSurface?.profileId) || 'default_kb',
    display_name: asString(knowledgeSurface?.display_name || knowledgeSurface?.displayName) || 'Default Knowledge Base',
    docs: Array.isArray(knowledgeSurface?.docs) ? knowledgeSurface.docs : [],
    stable_memory_files: Array.isArray(knowledgeSurface?.stable_memory_files || knowledgeSurface?.stableMemoryFiles)
      ? (knowledgeSurface?.stable_memory_files || knowledgeSurface?.stableMemoryFiles)
      : [],
    memory_policy: memoryPolicy || {},
  }
}


function normalizeListDraft(raw: string): string[] {
  return (raw || '')
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean)
}

function emptyKnowledgeDocRow(): KnowledgeDocFormRow {
  return {
    doc_id: '',
    file_name: '',
    title: '',
    purpose: '',
    write_hint: '',
    target_roles: '',
  }
}

function emptyTopologyParticipantRow(): TopologyParticipantFormRow {
  return {
    participant_id: '',
    kind: 'agent',
    role: '',
    label: '',
    provider: '',
  }
}

function emptyTopologyNodeRow(): TopologyNodeFormRow {
  return {
    node_id: '',
    participant_id: '',
    kind: 'agent',
    stage_index: '',
  }
}

function emptyTopologyEdgeRow(): TopologyEdgeFormRow {
  return {
    from: '',
    to: '',
    condition: '',
    label: '',
  }
}

function extractKnowledgeFormState(manifest: Record<string, any> | null): KnowledgeEditorFormState {
  const { knowledgeSurface, memoryPolicy } = extractKnowledgeEditorsFromManifest(manifest)
  const docsRaw = Array.isArray(knowledgeSurface?.docs) ? knowledgeSurface.docs : []
  const docs = docsRaw.length > 0
    ? docsRaw.map((entry: any) => ({
        doc_id: asString(entry?.doc_id || entry?.docId || entry?.semantic_slot || entry?.semanticSlot),
        file_name: asString(entry?.file_name || entry?.fileName),
        title: asString(entry?.title),
        purpose: asString(entry?.purpose),
        write_hint: asString(entry?.write_hint || entry?.writeHint),
        target_roles: Array.isArray(entry?.target_roles || entry?.targetRoles)
          ? (entry?.target_roles || entry?.targetRoles).map((row: any) => asString(row)).filter(Boolean).join(', ')
          : '',
      }))
    : [emptyKnowledgeDocRow()]
  return {
    profileId: asString(knowledgeSurface?.profile_id || knowledgeSurface?.profileId) || 'default_kb',
    displayName: asString(knowledgeSurface?.display_name || knowledgeSurface?.displayName) || 'Default Knowledge Base',
    docs,
    stableSlots: Array.isArray(memoryPolicy?.stable_semantic_slots || memoryPolicy?.stableSemanticSlots)
      ? (memoryPolicy?.stable_semantic_slots || memoryPolicy?.stableSemanticSlots).map((row: any) => asString(row)).filter(Boolean)
      : [],
    mutableSlots: Array.isArray(memoryPolicy?.mutable_semantic_slots || memoryPolicy?.mutableSemanticSlots)
      ? (memoryPolicy?.mutable_semantic_slots || memoryPolicy?.mutableSemanticSlots).map((row: any) => asString(row)).filter(Boolean)
      : [],
    immutableFiles: Array.isArray(memoryPolicy?.immutable_file_names || memoryPolicy?.immutableFileNames)
      ? (memoryPolicy?.immutable_file_names || memoryPolicy?.immutableFileNames).map((row: any) => asString(row)).filter(Boolean)
      : [],
  }
}

function buildKnowledgeEditorsFromForm(form: KnowledgeEditorFormState): { knowledgeSurface: Record<string, any>; memoryPolicy: Record<string, any> } {
  const docs = form.docs
    .map((entry) => ({
      doc_id: asString(entry.doc_id),
      file_name: asString(entry.file_name),
      title: asString(entry.title),
      purpose: asString(entry.purpose),
      write_hint: asString(entry.write_hint),
      target_roles: normalizeListDraft(entry.target_roles),
    }))
    .filter((entry) => entry.doc_id && entry.file_name)
  return {
    knowledgeSurface: {
      version: 1,
      profile_id: asString(form.profileId) || 'default_kb',
      display_name: asString(form.displayName) || 'Default Knowledge Base',
      docs,
    },
    memoryPolicy: {
      stable_semantic_slots: form.stableSlots,
      mutable_semantic_slots: form.mutableSlots,
      immutable_file_names: form.immutableFiles,
    },
  }
}

function applyKnowledgeEditorsToManifest(
  manifest: Record<string, any>,
  knowledgeSurface: Record<string, any>,
  memoryPolicy: Record<string, any>,
  applyState: 'active' | 'pending',
): Record<string, any> {
  const next = JSON.parse(JSON.stringify(manifest || {})) as Record<string, any>
  const structure = asObject(next.structure_v2)
  next.structure_v2 = {
    ...structure,
    knowledge_surface: knowledgeSurface,
    memory_policy: memoryPolicy,
  }

  const knowledgeBaseProfile = buildKnowledgeBaseProfileFromEditors(knowledgeSurface, memoryPolicy)

  if (next.team && typeof next.team === 'object' && !Array.isArray(next.team)) {
    next.team = {
      ...asObject(next.team),
      knowledge_surface: knowledgeSurface,
      memory_policy: memoryPolicy,
      knowledge_base_profile: knowledgeBaseProfile,
      structure_v2: {
        ...asObject(asObject(next.team).structure_v2),
        knowledge_surface: knowledgeSurface,
        memory_policy: memoryPolicy,
      },
    }
  }

  if (next.team_config && typeof next.team_config === 'object' && !Array.isArray(next.team_config)) {
    const targetKey = applyState === 'active' ? 'active_team' : 'pending_team'
    const targetTeam = asObject(asObject(next.team_config)[targetKey])
    next.team_config = {
      ...asObject(next.team_config),
      structure_v2: {
        ...asObject(asObject(next.team_config).structure_v2),
        knowledge_surface: knowledgeSurface,
        memory_policy: memoryPolicy,
      },
      [targetKey]: {
        ...targetTeam,
        knowledge_surface: knowledgeSurface,
        memory_policy: memoryPolicy,
        knowledge_base_profile: knowledgeBaseProfile,
        structure_v2: {
          ...asObject(targetTeam.structure_v2),
          knowledge_surface: knowledgeSurface,
          memory_policy: memoryPolicy,
        },
      },
    }
  }

  return next
}

function extractTopologyFormState(manifest: Record<string, any> | null): TopologyEditorFormState {
  const structure = asObject(manifest?.blueprint?.structure || manifest?.structure || manifest?.structure_v2 || manifest?.team?.structure || manifest?.team?.structure_v2)
  const participantsRaw = Array.isArray(structure?.participants) ? structure.participants : []
  const topology = asObject(structure?.topology)
  const nodesRaw = Array.isArray(topology?.nodes) ? topology.nodes : []
  const edgesRaw = Array.isArray(topology?.edges) ? topology.edges : []
  const controlPolicy = asObject(structure?.control_policy || structure?.controlPolicy)
  const participants = participantsRaw.length > 0
    ? participantsRaw.map((entry: any) => ({
        participant_id: asString(entry?.participant_id || entry?.participantId || entry?.id),
        kind: asString(entry?.kind) || 'agent',
        role: asString(entry?.role),
        label: asString(entry?.label || entry?.display_name || entry?.displayName || entry?.name),
        provider: asString(entry?.provider),
      }))
    : [emptyTopologyParticipantRow()]
  const nodes = nodesRaw.length > 0
    ? nodesRaw.map((entry: any) => ({
        node_id: asString(entry?.node_id || entry?.nodeId || entry?.id),
        participant_id: asString(entry?.participant_id || entry?.participantId || entry?.agent_id || entry?.agentId),
        kind: asString(entry?.kind) || 'agent',
        stage_index: asString(entry?.stage_index ?? entry?.stage ?? ''),
      }))
    : [emptyTopologyNodeRow()]
  const edges = edgesRaw.length > 0
    ? edgesRaw.map((entry: any) => ({
        from: asString(entry?.from || entry?.from_id || entry?.source),
        to: asString(entry?.to || entry?.to_id || entry?.target),
        condition: asString(entry?.condition),
        label: asString(entry?.label || entry?.type),
      }))
    : [emptyTopologyEdgeRow()]
  return {
    pattern: asString(topology?.pattern) || 'hybrid',
    executionPattern: asString(topology?.execution_pattern || topology?.executionPattern),
    finalParticipantId: asString(topology?.final_participant_id || topology?.finalParticipantId),
    finalOwnerParticipantId: asString(controlPolicy?.final_answer_owner_participant_id || controlPolicy?.finalAnswerOwnerParticipantId),
    participants,
    nodes,
    edges,
  }
}

function buildTopologyEditorsFromForm(form: TopologyEditorFormState) {
  const participants = form.participants
    .map((entry) => ({
      participant_id: asString(entry.participant_id),
      kind: asString(entry.kind) || 'agent',
      role: asString(entry.role),
      label: asString(entry.label),
      provider: asString(entry.provider),
    }))
    .filter((entry) => entry.participant_id)
  const nodes = form.nodes
    .map((entry) => ({
      node_id: asString(entry.node_id),
      participant_id: asString(entry.participant_id),
      kind: asString(entry.kind) || 'agent',
      ...(asString(entry.stage_index) ? { stage_index: Number.isFinite(Number(entry.stage_index)) ? Number(entry.stage_index) : asString(entry.stage_index) } : {}),
    }))
    .filter((entry) => entry.node_id || entry.participant_id)
  const edges = form.edges
    .map((entry) => ({
      from: asString(entry.from),
      to: asString(entry.to),
      ...(asString(entry.condition) ? { condition: asString(entry.condition) } : {}),
      ...(asString(entry.label) ? { label: asString(entry.label) } : {}),
    }))
    .filter((entry) => entry.from && entry.to)
  const topology = {
    pattern: asString(form.pattern) || 'hybrid',
    ...(asString(form.executionPattern) ? { execution_pattern: asString(form.executionPattern) } : {}),
    ...(asString(form.finalParticipantId) ? { final_participant_id: asString(form.finalParticipantId) } : {}),
    nodes,
    edges,
  }
  const controlPolicy = {
    ...(asString(form.finalOwnerParticipantId) ? { final_answer_owner_participant_id: asString(form.finalOwnerParticipantId) } : {}),
  }
  return { participants, topology, controlPolicy }
}

function applyTopologyEditorsToManifest(
  manifest: Record<string, any>,
  participants: Record<string, any>[],
  topology: Record<string, any>,
  controlPolicy: Record<string, any>,
  applyState: 'active' | 'pending',
): Record<string, any> {
  const next = JSON.parse(JSON.stringify(manifest || {})) as Record<string, any>
  const structure = asObject(next.structure_v2)
  next.structure_v2 = {
    ...structure,
    participants,
    topology,
    control_policy: {
      ...asObject(structure?.control_policy || structure?.controlPolicy),
      ...controlPolicy,
    },
  }

  if (next.team && typeof next.team === 'object' && !Array.isArray(next.team)) {
    next.team = {
      ...asObject(next.team),
      structure_v2: next.structure_v2,
      ...(asString(controlPolicy.final_answer_owner_participant_id) ? { final_answer_owner: asString(controlPolicy.final_answer_owner_participant_id) } : {}),
    }
  }

  if (next.team_config && typeof next.team_config === 'object' && !Array.isArray(next.team_config)) {
    const targetKey = applyState === 'active' ? 'active_team' : 'pending_team'
    const targetTeam = asObject(asObject(next.team_config)[targetKey])
    next.team_config = {
      ...asObject(next.team_config),
      structure_v2: next.structure_v2,
      [targetKey]: {
        ...targetTeam,
        structure_v2: next.structure_v2,
        ...(asString(controlPolicy.final_answer_owner_participant_id) ? { final_answer_owner: asString(controlPolicy.final_answer_owner_participant_id) } : {}),
      },
    }
  }

  return next
}

function extractRuntimeExecutionFormState(manifest: Record<string, any> | null): RuntimeExecutionEditorFormState {
  const structure = asObject(manifest?.blueprint?.structure || manifest?.structure || manifest?.structure_v2 || manifest?.team?.structure || manifest?.team?.structure_v2)
  const controlPolicy = asObject(structure?.control_policy || structure?.controlPolicy)
  const runtimeExecution = asObject(controlPolicy?.runtime_execution || controlPolicy?.runtimeExecution || manifest?.team?.runtime_execution || manifest?.team?.runtimeExecution)
  const checkpointing = asObject(runtimeExecution?.checkpointing)
  const continuousImprovement = asObject(runtimeExecution?.continuous_improvement || runtimeExecution?.continuousImprovement)
  const providers = asObject(runtimeExecution?.providers)
  const codex = asObject(providers?.codex || runtimeExecution?.codex)
  const gemini = asObject(providers?.gemini || runtimeExecution?.gemini)
  const approvalMatrix = asObject(runtimeExecution?.approval_matrix || runtimeExecution?.approvalMatrix)
  return {
    checkpointWriteOnTurnEnd: checkpointing?.write_on_turn_end === true || checkpointing?.writeOnTurnEnd === true,
    checkpointWriteOnApprovalPause: checkpointing?.write_on_approval_pause !== false && checkpointing?.writeOnApprovalPause !== false,
    checkpointWriteOnResume: checkpointing?.write_on_resume !== false && checkpointing?.writeOnResume !== false,
    checkpointExposeRestoreContextToAgents: checkpointing?.expose_restore_context_to_agents !== false && checkpointing?.exposeRestoreContextToAgents !== false,
    continuousImprovementEnabled: continuousImprovement?.enabled === true,
    continuousImprovementMode: asString(continuousImprovement?.mode || continuousImprovement?.strategy) || 'until_quality_threshold',
    continuousImprovementMaxTurns: asString(continuousImprovement?.max_turns ?? continuousImprovement?.maxTurns ?? 8) || '8',
    continuousImprovementMaxTotalActions: asString(continuousImprovement?.max_total_actions ?? continuousImprovement?.maxTotalActions ?? 48) || '48',
    continuousImprovementMinTurns: asString(continuousImprovement?.min_turns ?? continuousImprovement?.minTurns ?? 1) || '1',
    continuousImprovementProgressEachTurn: continuousImprovement?.progress_report_each_turn !== false && continuousImprovement?.progressReportEachTurn !== false,
    continuousImprovementStopSignals: Array.isArray(continuousImprovement?.stop_signals || continuousImprovement?.stopSignals)
      ? (continuousImprovement?.stop_signals || continuousImprovement?.stopSignals).map((entry: any) => asString(entry)).filter(Boolean).join(', ')
      : 'quality_threshold_met, ready_for_user, final_answer_ready, done_enough',
    approvalMatrixDraft: prettyJson(approvalMatrix),
    codexSandboxMode: asString(codex?.sandbox_mode || codex?.sandboxMode) || 'workspace-write',
    codexApprovalPolicy: asString(codex?.approval_policy || codex?.approvalPolicy) || 'never',
    codexProfile: asString(codex?.profile),
    codexAddDirs: Array.isArray(codex?.add_dirs || codex?.addDirs) ? (codex?.add_dirs || codex?.addDirs).map((entry: any) => asString(entry)).filter(Boolean).join(', ') : '',
    codexMcpServersDraft: prettyJson(asObject(codex?.mcp_servers || codex?.mcpServers)),
    geminiApprovalMode: asString(gemini?.approval_mode || gemini?.approvalMode) || 'default',
    geminiSettingsOverwrite: asString(gemini?.settings_overwrite || gemini?.settingsOverwrite) || 'merge',
    geminiExtraEnvDraft: prettyJson(asObject(gemini?.extra_env || gemini?.extraEnv)),
    geminiMcpServersDraft: prettyJson(asObject(gemini?.mcp_servers || gemini?.mcpServers)),
  }
}

function buildRuntimeExecutionEditorsFromForm(form: RuntimeExecutionEditorFormState): { runtimeExecution: Record<string, any> } {
  const approvalMatrix = parseJsonObjectDraft(form.approvalMatrixDraft, 'approval_matrix')
  const codexMcpServers = parseJsonObjectDraft(form.codexMcpServersDraft, 'codex mcp_servers')
  const geminiExtraEnv = parseJsonObjectDraft(form.geminiExtraEnvDraft, 'gemini extra_env')
  const geminiMcpServers = parseJsonObjectDraft(form.geminiMcpServersDraft, 'gemini mcp_servers')
  return {
    runtimeExecution: {
      checkpointing: {
        enabled: true,
        write_on_turn_end: form.checkpointWriteOnTurnEnd,
        write_on_approval_pause: form.checkpointWriteOnApprovalPause,
        write_on_resume: form.checkpointWriteOnResume,
        expose_restore_context_to_agents: form.checkpointExposeRestoreContextToAgents,
      },
      continuous_improvement: {
        enabled: form.continuousImprovementEnabled,
        mode: asString(form.continuousImprovementMode) || 'until_quality_threshold',
        max_turns: Number.isFinite(Number(form.continuousImprovementMaxTurns)) ? Number(form.continuousImprovementMaxTurns) : 8,
        max_total_actions: Number.isFinite(Number(form.continuousImprovementMaxTotalActions)) ? Number(form.continuousImprovementMaxTotalActions) : 48,
        min_turns: Number.isFinite(Number(form.continuousImprovementMinTurns)) ? Number(form.continuousImprovementMinTurns) : 1,
        progress_report_each_turn: form.continuousImprovementProgressEachTurn,
        stop_signals: normalizeListDraft(form.continuousImprovementStopSignals),
      },
      approval_matrix: approvalMatrix,
      providers: {
        codex: {
          sandbox_mode: asString(form.codexSandboxMode) || 'workspace-write',
          approval_policy: asString(form.codexApprovalPolicy) || 'never',
          profile: asString(form.codexProfile),
          add_dirs: normalizeListDraft(form.codexAddDirs),
          mcp_servers: codexMcpServers,
        },
        gemini: {
          approval_mode: asString(form.geminiApprovalMode) || 'default',
          settings_overwrite: asString(form.geminiSettingsOverwrite) || 'merge',
          extra_env: geminiExtraEnv,
          mcp_servers: geminiMcpServers,
        },
      },
    },
  }
}

function applyRuntimeExecutionToManifest(
  manifest: Record<string, any>,
  runtimeExecution: Record<string, any>,
  applyState: 'active' | 'pending',
): Record<string, any> {
  const next = JSON.parse(JSON.stringify(manifest || {})) as Record<string, any>
  const structure = asObject(next.structure_v2)
  const nextStructure = {
    ...structure,
    control_policy: {
      ...asObject(structure?.control_policy || structure?.controlPolicy),
      runtime_execution: runtimeExecution,
    },
  }
  next.structure_v2 = nextStructure

  if (next.team && typeof next.team === 'object' && !Array.isArray(next.team)) {
    const teamStructure = asObject(asObject(next.team).structure_v2)
    next.team = {
      ...asObject(next.team),
      runtime_execution: runtimeExecution,
      structure_v2: {
        ...teamStructure,
        control_policy: {
          ...asObject(teamStructure?.control_policy || teamStructure?.controlPolicy),
          runtime_execution: runtimeExecution,
        },
      },
    }
  }

  if (next.team_config && typeof next.team_config === 'object' && !Array.isArray(next.team_config)) {
    const targetKey = applyState === 'active' ? 'active_team' : 'pending_team'
    const targetTeam = asObject(asObject(next.team_config)[targetKey])
    const targetStructure = asObject(targetTeam.structure_v2)
    next.team_config = {
      ...asObject(next.team_config),
      structure_v2: nextStructure,
      [targetKey]: {
        ...targetTeam,
        runtime_execution: runtimeExecution,
        structure_v2: {
          ...targetStructure,
          control_policy: {
            ...asObject(targetStructure?.control_policy || targetStructure?.controlPolicy),
            runtime_execution: runtimeExecution,
          },
        },
      },
    }
  }

  return next
}

export default function ConversationAgentsPanel({ threadId, refreshKey = 0 }: Props) {
  const [conversation, setConversation] = useState<ConversationState | null>(null)
  const [availableAgents, setAvailableAgents] = useState<AgentItem[]>([])
  const [selectedAgentId, setSelectedAgentId] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState<string | null>(null)
  const [overridesDraft, setOverridesDraft] = useState<Record<string, string>>({})
  const [manifestDraft, setManifestDraft] = useState('')
  const [manifestApplyState, setManifestApplyState] = useState<'active' | 'pending'>('active')
  const [manifestStatus, setManifestStatus] = useState('')
  const [manifestError, setManifestError] = useState('')
  const [manifestBusy, setManifestBusy] = useState<string | null>(null)
  const [manifestValidation, setManifestValidation] = useState<any>(null)
  const [manifestDiff, setManifestDiff] = useState<any>(null)
  const [knowledgeProfileId, setKnowledgeProfileId] = useState('default_kb')
  const [knowledgeDisplayName, setKnowledgeDisplayName] = useState('Default Knowledge Base')
  const [knowledgeDocRows, setKnowledgeDocRows] = useState<KnowledgeDocFormRow[]>([emptyKnowledgeDocRow()])
  const [stableSlotDraft, setStableSlotDraft] = useState('')
  const [mutableSlotDraft, setMutableSlotDraft] = useState('')
  const [immutableFilesDraft, setImmutableFilesDraft] = useState('')
  const [topologyPatternDraft, setTopologyPatternDraft] = useState('hybrid')
  const [topologyExecutionPatternDraft, setTopologyExecutionPatternDraft] = useState('')
  const [topologyFinalParticipantDraft, setTopologyFinalParticipantDraft] = useState('')
  const [topologyFinalOwnerDraft, setTopologyFinalOwnerDraft] = useState('')
  const [topologyParticipantRows, setTopologyParticipantRows] = useState<TopologyParticipantFormRow[]>([emptyTopologyParticipantRow()])
  const [topologyNodeRows, setTopologyNodeRows] = useState<TopologyNodeFormRow[]>([emptyTopologyNodeRow()])
  const [topologyEdgeRows, setTopologyEdgeRows] = useState<TopologyEdgeFormRow[]>([emptyTopologyEdgeRow()])
  const [checkpointWriteOnTurnEnd, setCheckpointWriteOnTurnEnd] = useState(false)
  const [checkpointWriteOnApprovalPause, setCheckpointWriteOnApprovalPause] = useState(true)
  const [checkpointWriteOnResume, setCheckpointWriteOnResume] = useState(true)
  const [checkpointExposeRestoreContextToAgents, setCheckpointExposeRestoreContextToAgents] = useState(true)
  const [continuousImprovementEnabled, setContinuousImprovementEnabled] = useState(false)
  const [continuousImprovementMode, setContinuousImprovementMode] = useState('until_quality_threshold')
  const [continuousImprovementMaxTurns, setContinuousImprovementMaxTurns] = useState('8')
  const [continuousImprovementMaxTotalActions, setContinuousImprovementMaxTotalActions] = useState('48')
  const [continuousImprovementMinTurns, setContinuousImprovementMinTurns] = useState('1')
  const [continuousImprovementProgressEachTurn, setContinuousImprovementProgressEachTurn] = useState(true)
  const [continuousImprovementStopSignals, setContinuousImprovementStopSignals] = useState('quality_threshold_met, ready_for_user, final_answer_ready, done_enough')
  const [approvalMatrixDraft, setApprovalMatrixDraft] = useState('{}')
  const [codexSandboxMode, setCodexSandboxMode] = useState('workspace-write')
  const [codexApprovalPolicy, setCodexApprovalPolicy] = useState('never')
  const [codexProfile, setCodexProfile] = useState('')
  const [codexAddDirs, setCodexAddDirs] = useState('')
  const [codexMcpServersDraft, setCodexMcpServersDraft] = useState('{}')
  const [geminiApprovalMode, setGeminiApprovalMode] = useState('default')
  const [geminiSettingsOverwrite, setGeminiSettingsOverwrite] = useState('merge')
  const [geminiExtraEnvDraft, setGeminiExtraEnvDraft] = useState('{}')
  const [geminiMcpServersDraft, setGeminiMcpServersDraft] = useState('{}')
  const [teamCatalogItems, setTeamCatalogItems] = useState<TeamCatalogItem[]>([])
  const [teamCatalogBusy, setTeamCatalogBusy] = useState<string | null>(null)
  const [teamCatalogStatus, setTeamCatalogStatus] = useState('')
  const [teamCatalogError, setTeamCatalogError] = useState('')
  const [teamBlueprintTitle, setTeamBlueprintTitle] = useState('')
  const [teamBlueprintSummary, setTeamBlueprintSummary] = useState('')
  const [teamBlueprintTagsDraft, setTeamBlueprintTagsDraft] = useState('')
  const [teamBlueprintGoodForDraft, setTeamBlueprintGoodForDraft] = useState('')
  const [teamBlueprintTemplates, setTeamBlueprintTemplates] = useState<TeamBlueprintTemplateItem[]>([])
  const [teamBlueprintTemplateError, setTeamBlueprintTemplateError] = useState('')

  const memberLineageKeySet = useMemo(() => {
    const out = new Set<string>()
    for (const row of conversation?.agents || []) {
      out.add(lineageKeyForAgent(row.agent))
    }
    return out
  }, [conversation])
  const candidateAgents = useMemo(
    () => availableAgents.filter((agent) => !memberLineageKeySet.has(lineageKeyForAgent(agent))),
    [availableAgents, memberLineageKeySet],
  )


  const reloadBlueprintTemplates = useCallback(async () => {
    if (!threadId) {
      setTeamBlueprintTemplates([])
      setTeamBlueprintTemplateError('')
      return
    }
    try {
      const out = await listThreadTeamBlueprintTemplates(threadId)
      const rows = Array.isArray(out?.items) ? out.items : []
      setTeamBlueprintTemplates(rows.map((row: any) => normalizeTemplateItem(row)).filter(Boolean) as TeamBlueprintTemplateItem[])
      setTeamBlueprintTemplateError('')
    } catch (e) {
      setTeamBlueprintTemplates([])
      setTeamBlueprintTemplateError(e instanceof Error ? e.message : String(e))
    }
  }, [threadId])

  const refresh = useCallback(async () => {
    if (!threadId) {
      setConversation(null)
      setAvailableAgents([])
      setSelectedAgentId('')
      return
    }
    setLoading(true)
    setError('')
    try {
      const [convOut, myOut, publicOut] = await Promise.all([
        api.threadTeam(threadId),
        api.agents('my', false),
        api.agents('public', false),
      ])
      const nextConversation = normalizeConversation(convOut?.conversation)
      setConversation(nextConversation)
      const merged = new Map<string, AgentItem>()
      for (const source of [myOut?.items, publicOut?.items]) {
        const rows = Array.isArray(source) ? source : []
        for (const raw of rows) {
          const agent = normalizeAgent(raw)
          if (!agent) continue
          merged.set(agent.id, agent)
        }
      }
      const nextAvailable = [...merged.values()].sort((a, b) => a.name.localeCompare(b.name))
      setAvailableAgents(nextAvailable)
      setSelectedAgentId((prev) => {
        if (prev && nextAvailable.some((row) => row.id === prev)) return prev
        return nextAvailable[0]?.id || ''
      })
      const nextDraft: Record<string, string> = {}
      for (const member of nextConversation?.agents || []) {
        nextDraft[member.agent_id] = JSON.stringify(member.overrides_json || {}, null, 2)
      }
      setOverridesDraft(nextDraft)
    } catch (e) {
      setConversation(null)
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [threadId])

  useEffect(() => {
    void refresh()
  }, [threadId, refreshKey, refresh])

  useEffect(() => {
    void reloadBlueprintTemplates()
  }, [threadId, refreshKey, reloadBlueprintTemplates])

  function applyConversationResponse(raw: any) {
    const next = normalizeConversation(raw)
    if (!next) return
    setConversation(next)
    const nextDraft: Record<string, string> = {}
    for (const member of next.agents) {
      nextDraft[member.agent_id] = JSON.stringify(member.overrides_json || {}, null, 2)
    }
    setOverridesDraft(nextDraft)
  }

  async function handleAddAgent() {
    if (!threadId) return
    const agentId = selectedAgentId.trim()
    if (!agentId) {
      setError('추가할 agent를 선택하세요.')
      return
    }
    setBusyId(agentId)
    setError('')
    setStatus('')
    try {
      const out = await api.addThreadTeamMember(threadId, { agent_id: agentId, enabled: true })
      applyConversationResponse(out?.conversation)
      setStatus('agent를 thread 팀에 추가했습니다.')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyId(null)
    }
  }

  async function handleToggleEnabled(member: ConversationMember, enabled: boolean) {
    if (!threadId) return
    setBusyId(member.agent_id)
    setError('')
    setStatus('')
    try {
      const out = await api.patchThreadTeamMember(threadId, member.agent_id, { enabled })
      applyConversationResponse(out?.conversation)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyId(null)
    }
  }

  async function handleRemove(member: ConversationMember) {
    if (!threadId) return
    setBusyId(member.agent_id)
    setError('')
    setStatus('')
    try {
      const out = await api.removeThreadTeamMember(threadId, member.agent_id)
      applyConversationResponse(out?.conversation)
      setStatus(`agent 제거: ${member.agent.name}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyId(null)
    }
  }

  async function handleMove(member: ConversationMember, direction: -1 | 1) {
    if (!threadId || !conversation) return
    const ids = conversation.agents.map((row) => row.agent_id)
    const index = ids.indexOf(member.agent_id)
    if (index < 0) return
    const nextIndex = index + direction
    if (nextIndex < 0 || nextIndex >= ids.length) return
    const nextIds = [...ids]
    const tmp = nextIds[index]
    nextIds[index] = nextIds[nextIndex]
    nextIds[nextIndex] = tmp

    setBusyId(member.agent_id)
    setError('')
    setStatus('')
    try {
      const out = await api.reorderThreadTeam(threadId, nextIds)
      applyConversationResponse(out?.conversation)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyId(null)
    }
  }

  async function handleSaveOverrides(member: ConversationMember) {
    if (!threadId) return
    const raw = (overridesDraft[member.agent_id] || '').trim()
    let parsed: Record<string, unknown> = {}
    if (raw) {
      try {
        const value = JSON.parse(raw)
        if (!value || typeof value !== 'object' || Array.isArray(value)) {
          setError('overrides_json은 JSON object여야 합니다.')
          return
        }
        parsed = value as Record<string, unknown>
      } catch {
        setError('overrides_json JSON 파싱에 실패했습니다.')
        return
      }
    }
    setBusyId(member.agent_id)
    setError('')
    setStatus('')
    try {
      const out = await api.patchThreadTeamMember(threadId, member.agent_id, { overrides_json: parsed })
      applyConversationResponse(out?.conversation)
      setStatus(`overrides 저장 완료: ${member.agent.name}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusyId(null)
    }
  }


  function parseManifestDraft(): Record<string, any> | null {
    const raw = manifestDraft.trim()
    if (!raw) {
      setManifestError('blueprint JSON을 먼저 불러오거나 입력하세요.')
      return null
    }
    try {
      const value = JSON.parse(raw)
      if (!value || typeof value !== 'object' || Array.isArray(value)) {
        setManifestError('blueprint는 JSON object여야 합니다.')
        return null
      }
      return value as Record<string, any>
    } catch {
      setManifestError('blueprint JSON 파싱에 실패했습니다.')
      return null
    }
  }


  function handleLoadBlueprintTemplate(template: TeamBlueprintTemplateItem) {
    setManifestError('')
    setManifestStatus(`template blueprint를 draft에 불러왔습니다: ${template.title}`)
    setManifestValidation(null)
    setManifestDiff(null)
    setManifestDraft(JSON.stringify(template.blueprintDocument, null, 2))
  }

  async function handleExportManifest() {
    if (!threadId) return
    setManifestBusy('export')
    setManifestError('')
    setManifestStatus('')
    try {
      const out = await exportThreadTeamManifest(threadId)
      const manifest = out?.manifest || out || {}
      setManifestDraft(JSON.stringify(manifest, null, 2))
      setManifestValidation(null)
      setManifestStatus('현재 thread team blueprint를 불러왔습니다.')
    } catch (e) {
      setManifestError(e instanceof Error ? e.message : String(e))
    } finally {
      setManifestBusy(null)
    }
  }

  async function handlePreviewManifestDiff() {
    if (!threadId) return
    const manifest = parseManifestDraft()
    if (!manifest) return
    setManifestBusy('diff')
    setManifestError('')
    setManifestStatus('')
    try {
      const out = await diffThreadTeamManifest(threadId, { manifest, apply_state: manifestApplyState })
      setManifestDiff(out)
      if (out?.candidate_manifest) setManifestDraft(JSON.stringify(out.candidate_manifest, null, 2))
      setManifestStatus('blueprint diff preview를 갱신했습니다.')
    } catch (e) {
      setManifestError(e instanceof Error ? e.message : String(e))
    } finally {
      setManifestBusy(null)
    }
  }

  async function handleValidateManifest() {
    if (!threadId) return
    const manifest = parseManifestDraft()
    if (!manifest) return
    setManifestBusy('validate')
    setManifestError('')
    setManifestStatus('')
    try {
      const out = await validateThreadTeamManifest(threadId, { manifest, apply_state: manifestApplyState })
      setManifestValidation(out)
      setManifestDiff(null)
      if (out?.manifest) setManifestDraft(JSON.stringify(out.manifest, null, 2))
      setManifestStatus(out?.ok ? 'blueprint validation 성공' : 'blueprint validation에서 수정이 필요합니다.')
    } catch (e) {
      setManifestError(e instanceof Error ? e.message : String(e))
    } finally {
      setManifestBusy(null)
    }
  }

  async function handleInstallManifest() {
    if (!threadId) return
    const manifest = parseManifestDraft()
    if (!manifest) return
    setManifestBusy('install')
    setManifestError('')
    setManifestStatus('')
    try {
      const out = await installThreadTeamManifest(threadId, { manifest, apply_state: manifestApplyState })
      const normalizedManifest = out?.manifest || out || {}
      setManifestDraft(JSON.stringify(normalizedManifest, null, 2))
      setManifestValidation({ ok: true, manifest: normalizedManifest, apply_state: manifestApplyState })
      setManifestDiff(null)
      setManifestStatus(`blueprint를 ${manifestApplyState === 'active' ? 'active' : 'pending'} team에 설치했습니다.`)
      await refresh()
    } catch (e) {
      setManifestError(e instanceof Error ? e.message : String(e))
    } finally {
      setManifestBusy(null)
    }
  }

  const ensurePrivateTeamCatalogThread = useCallback(async (): Promise<string> => {
    const listRaw = await api.threads()
    const list = Array.isArray(listRaw) ? (listRaw as ThreadSummary[]) : []
    const existing = list.find((thread) => TEAM_CATALOG_THREAD_TITLES.includes(normalizeTitle(thread.title) as (typeof TEAM_CATALOG_THREAD_TITLES)[number]))
    if (existing?.id) return existing.id
    const created = await api.createThread(TEAM_CATALOG_THREAD_TITLES[0], {
      meta_json: { catalog_kind: TEAM_BLUEPRINT_RESOURCE_KIND },
    })
    const nextId = asString((created as { id?: string }).id)
    if (!nextId) throw new Error('team catalog thread 생성에 실패했습니다.')
    return nextId
  }, [])

  const ensureDefaultContextSet = useCallback(async (targetThreadId: string): Promise<string | null> => {
    const sets = await api.ctxSets(targetThreadId)
    const list = Array.isArray(sets) ? sets : []
    if (list[0]?.id) return asString(list[0].id)
    const created = await api.createCtx(targetThreadId, 'default')
    return asString((created as { id?: string }).id) || null
  }, [])

  const reloadTeamCatalog = useCallback(async () => {
    setTeamCatalogError('')
    try {
      const listRaw = await api.threads()
      const list = Array.isArray(listRaw) ? (listRaw as ThreadSummary[]) : []
      const catalogThread = list.find((thread) => TEAM_CATALOG_THREAD_TITLES.includes(normalizeTitle(thread.title) as (typeof TEAM_CATALOG_THREAD_TITLES)[number]))
      if (!catalogThread?.id) {
        setTeamCatalogItems([])
        return
      }
      const out = await api.listResources(catalogThread.id, TEAM_BLUEPRINT_RESOURCE_KIND)
      const rows = Array.isArray(out?.items) ? (out.items as GraphResourceNode[]) : []
      const mapped = rows
        .map((row) => resourceNodeToTeamCatalogItem(row))
        .filter((item): item is TeamCatalogItem => Boolean(item))
        .sort((a, b) => (a.createdAt === b.createdAt ? a.nodeId.localeCompare(b.nodeId) : a.createdAt < b.createdAt ? 1 : -1))
      setTeamCatalogItems(mapped)
    } catch (error) {
      setTeamCatalogItems([])
      setTeamCatalogError(error instanceof Error ? error.message : String(error))
    }
  }, [])

  async function handleSaveCurrentTeamToCatalog() {
    if (!threadId) return
    setTeamCatalogBusy('save')
    setTeamCatalogError('')
    setTeamCatalogStatus('')
    try {
      let manifest = manifestDraft.trim() ? parseManifestDraft() : null
      if (!manifest) {
        manifest = ((await exportThreadTeamManifest(threadId))?.manifest || {}) as Record<string, any>
      }
      if (!manifest || Object.keys(manifest).length === 0) {
        throw new Error('저장할 blueprint를 준비하지 못했습니다.')
      }
      const title = teamBlueprintTitle.trim() || deriveTeamBlueprintTitle(manifest)
      const summary = teamBlueprintSummary.trim() || deriveTeamBlueprintSummary(manifest)
      const tags = teamBlueprintTagsDraft.split(',').map((entry) => entry.trim()).filter(Boolean)
      const recommendedFor = teamBlueprintGoodForDraft.split('\n').map((entry) => entry.trim()).filter(Boolean)
      const catalogThreadId = await ensurePrivateTeamCatalogThread()
      const contextSetId = await ensureDefaultContextSet(catalogThreadId)
      const payload = {
        resource_kind: TEAM_BLUEPRINT_RESOURCE_KIND,
        title,
        summary,
        tags,
        recommended_for: recommendedFor,
        exported_from_thread_id: threadId,
        exported_at: new Date().toISOString(),
        schema_kind: asString(manifest?.kind) || 'ddalggak_team_blueprint',
      }
      await api.createResource(catalogThreadId, {
        name: title,
        summary,
        resource_kind: TEAM_BLUEPRINT_RESOURCE_KIND,
        source: 'manual',
        context_set_id: contextSetId,
        auto_activate: true,
        text_mode: 'plain',
        raw_text: JSON.stringify(manifest, null, 2),
        payload_json: payload,
      })
      setManifestDraft(JSON.stringify(manifest, null, 2))
      setTeamCatalogStatus(`현재 팀을 catalog에 저장했습니다: ${title}`)
      await reloadTeamCatalog()
    } catch (e) {
      setTeamCatalogError(e instanceof Error ? e.message : String(e))
    } finally {
      setTeamCatalogBusy(null)
    }
  }

  async function handleInstallCatalogItem(item: TeamCatalogItem) {
    if (!threadId) return
    setTeamCatalogBusy(item.nodeId)
    setTeamCatalogError('')
    setTeamCatalogStatus('')
    try {
      const out = await installThreadTeamManifest(threadId, {
        manifest: item.manifest,
        apply_state: manifestApplyState,
      })
      const normalizedManifest = out?.manifest || out || item.manifest
      setManifestDraft(JSON.stringify(normalizedManifest, null, 2))
      setManifestValidation({ ok: true, manifest: normalizedManifest, apply_state: manifestApplyState })
      setManifestDiff(null)
      setTeamCatalogStatus(`catalog team을 ${manifestApplyState} state로 설치했습니다: ${item.title}`)
      await refresh()
    } catch (e) {
      setTeamCatalogError(e instanceof Error ? e.message : String(e))
    } finally {
      setTeamCatalogBusy(null)
    }
  }

  useEffect(() => {
    void reloadTeamCatalog()
  }, [threadId, reloadTeamCatalog])

  const parsedManifestDraft = (() => {
    try {
      return manifestDraft.trim() ? JSON.parse(manifestDraft) : null
    } catch {
      return null
    }
  })()

  const effectiveManifest = manifestValidation?.manifest || parsedManifestDraft || null
  const requirementSummary = effectiveManifest?.requirements || null
  const installProposalSummary = effectiveManifest?.install_proposal || null
  const installProposalStateSummary = effectiveManifest?.install_proposal_state || null
  const credentialBindingSummary = effectiveManifest?.credential_binding_state || null
  const structureSummary = effectiveManifest?.structure_v2 || effectiveManifest?.team?.structure_v2 || null
  const patternConflictSummary = effectiveManifest?.pattern_conflict || null
  const temporaryExecutionOverrideSummary = effectiveManifest?.temporary_execution_override || null
  const patternRecoverySummary = effectiveManifest?.pattern_recovery || null
  const teamConfigSummary = effectiveManifest?.team_config || null
  const compatibilityTeamSummary = effectiveManifest?.team || null
  const manifestPrimarySchema = asString(effectiveManifest?.primary_schema || 'team_blueprint_v1') || 'team_blueprint_v1'
  const validationSummary = structureSummary?.validation || {}
  const topologyNodes = Array.isArray(structureSummary?.topology?.nodes) ? structureSummary.topology.nodes : []
  const topologyEdges = Array.isArray(structureSummary?.topology?.edges) ? structureSummary.topology.edges : []
  const knowledgeSurfaceSummary = asObject(structureSummary?.knowledge_surface || structureSummary?.knowledgeSurface || compatibilityTeamSummary?.knowledge_surface || compatibilityTeamSummary?.knowledgeSurface || compatibilityTeamSummary?.knowledge_base_profile)
  const memoryPolicySummary = asObject(structureSummary?.memory_policy || structureSummary?.memoryPolicy || compatibilityTeamSummary?.memory_policy || compatibilityTeamSummary?.memoryPolicy || knowledgeSurfaceSummary?.memory_policy)
  const runtimeExecutionSummary = asObject(structureSummary?.control_policy?.runtime_execution || structureSummary?.controlPolicy?.runtimeExecution || compatibilityTeamSummary?.runtime_execution || compatibilityTeamSummary?.runtimeExecution)
  const runtimeExecutionCheckpointingSummary = asObject(runtimeExecutionSummary?.checkpointing)
  const runtimeExecutionContinuousSummary = asObject(runtimeExecutionSummary?.continuous_improvement || runtimeExecutionSummary?.continuousImprovement)
  const runtimeExecutionApprovalSummary = asObject(runtimeExecutionSummary?.approval_matrix || runtimeExecutionSummary?.approvalMatrix)
  const runtimeExecutionProvidersSummary = asObject(runtimeExecutionSummary?.providers)
  const runtimeExecutionCodexSummary = asObject(runtimeExecutionProvidersSummary?.codex || runtimeExecutionSummary?.codex)
  const runtimeExecutionGeminiSummary = asObject(runtimeExecutionProvidersSummary?.gemini || runtimeExecutionSummary?.gemini)
  const knowledgeDocs = Array.isArray(knowledgeSurfaceSummary?.docs) ? knowledgeSurfaceSummary.docs : []
  const stableSlots = Array.isArray(memoryPolicySummary?.stable_semantic_slots || memoryPolicySummary?.stableSemanticSlots) ? (memoryPolicySummary?.stable_semantic_slots || memoryPolicySummary?.stableSemanticSlots) : []
  const mutableSlots = Array.isArray(memoryPolicySummary?.mutable_semantic_slots || memoryPolicySummary?.mutableSemanticSlots) ? (memoryPolicySummary?.mutable_semantic_slots || memoryPolicySummary?.mutableSemanticSlots) : []
  const immutableFiles = Array.isArray(memoryPolicySummary?.immutable_file_names || memoryPolicySummary?.immutableFileNames) ? (memoryPolicySummary?.immutable_file_names || memoryPolicySummary?.immutableFileNames) : []
  const operatorCommandSuggestions = commandSuggestionList({ manifest: effectiveManifest, applyState: manifestApplyState })

  useEffect(() => {
    const formState = extractKnowledgeFormState(effectiveManifest)
    setKnowledgeProfileId(formState.profileId)
    setKnowledgeDisplayName(formState.displayName)
    setKnowledgeDocRows(formState.docs)
    setStableSlotDraft(formState.stableSlots.join(', '))
    setMutableSlotDraft(formState.mutableSlots.join(', '))
    setImmutableFilesDraft(formState.immutableFiles.join(', '))
  }, [effectiveManifest])

  useEffect(() => {
    if (!effectiveManifest) return
    setTeamBlueprintTitle((prev) => prev.trim() ? prev : deriveTeamBlueprintTitle(effectiveManifest))
    setTeamBlueprintSummary((prev) => prev.trim() ? prev : deriveTeamBlueprintSummary(effectiveManifest))
  }, [effectiveManifest])

  useEffect(() => {
    const formState = extractTopologyFormState(effectiveManifest)
    setTopologyPatternDraft(formState.pattern)
    setTopologyExecutionPatternDraft(formState.executionPattern)
    setTopologyFinalParticipantDraft(formState.finalParticipantId)
    setTopologyFinalOwnerDraft(formState.finalOwnerParticipantId)
    setTopologyParticipantRows(formState.participants)
    setTopologyNodeRows(formState.nodes)
    setTopologyEdgeRows(formState.edges)
  }, [effectiveManifest])

  useEffect(() => {
    const formState = extractRuntimeExecutionFormState(effectiveManifest)
    setCheckpointWriteOnTurnEnd(formState.checkpointWriteOnTurnEnd)
    setCheckpointWriteOnApprovalPause(formState.checkpointWriteOnApprovalPause)
    setCheckpointWriteOnResume(formState.checkpointWriteOnResume)
    setCheckpointExposeRestoreContextToAgents(formState.checkpointExposeRestoreContextToAgents)
    setContinuousImprovementEnabled(formState.continuousImprovementEnabled)
    setContinuousImprovementMode(formState.continuousImprovementMode)
    setContinuousImprovementMaxTurns(formState.continuousImprovementMaxTurns)
    setContinuousImprovementMaxTotalActions(formState.continuousImprovementMaxTotalActions)
    setContinuousImprovementMinTurns(formState.continuousImprovementMinTurns)
    setContinuousImprovementProgressEachTurn(formState.continuousImprovementProgressEachTurn)
    setContinuousImprovementStopSignals(formState.continuousImprovementStopSignals)
    setApprovalMatrixDraft(formState.approvalMatrixDraft)
    setCodexSandboxMode(formState.codexSandboxMode)
    setCodexApprovalPolicy(formState.codexApprovalPolicy)
    setCodexProfile(formState.codexProfile)
    setCodexAddDirs(formState.codexAddDirs)
    setCodexMcpServersDraft(formState.codexMcpServersDraft)
    setGeminiApprovalMode(formState.geminiApprovalMode)
    setGeminiSettingsOverwrite(formState.geminiSettingsOverwrite)
    setGeminiExtraEnvDraft(formState.geminiExtraEnvDraft)
    setGeminiMcpServersDraft(formState.geminiMcpServersDraft)
  }, [effectiveManifest])

  async function handleApplyKnowledgeEditors() {
    const manifest = parseManifestDraft()
    if (!manifest) return
    setManifestError('')
    setManifestStatus('')
    try {
      const { knowledgeSurface, memoryPolicy } = buildKnowledgeEditorsFromForm({
        profileId: knowledgeProfileId,
        displayName: knowledgeDisplayName,
        docs: knowledgeDocRows,
        stableSlots: normalizeListDraft(stableSlotDraft),
        mutableSlots: normalizeListDraft(mutableSlotDraft),
        immutableFiles: normalizeListDraft(immutableFilesDraft),
      })
      const nextManifest = applyKnowledgeEditorsToManifest(manifest, knowledgeSurface, memoryPolicy, manifestApplyState)
      setManifestDraft(JSON.stringify(nextManifest, null, 2))
      setManifestValidation(null)
      setManifestDiff(null)
      setManifestStatus('memory plan / knowledge settings를 blueprint draft에 반영했습니다.')
    } catch (e) {
      setManifestError(e instanceof Error ? e.message : String(e))
    }
  }

  async function handleApplyTopologyEditors() {
    const manifest = parseManifestDraft()
    if (!manifest) return
    setManifestError('')
    setManifestStatus('')
    try {
      const { participants, topology, controlPolicy } = buildTopologyEditorsFromForm({
        pattern: topologyPatternDraft,
        executionPattern: topologyExecutionPatternDraft,
        finalParticipantId: topologyFinalParticipantDraft,
        finalOwnerParticipantId: topologyFinalOwnerDraft,
        participants: topologyParticipantRows,
        nodes: topologyNodeRows,
        edges: topologyEdgeRows,
      })
      const nextManifest = applyTopologyEditorsToManifest(manifest, participants, topology, controlPolicy, manifestApplyState)
      setManifestDraft(JSON.stringify(nextManifest, null, 2))
      setManifestValidation(null)
      setManifestDiff(null)
      setManifestStatus('topology / participants를 blueprint draft에 반영했습니다.')
    } catch (e) {
      setManifestError(e instanceof Error ? e.message : String(e))
    }
  }

  async function handleApplyRuntimeExecutionEditors() {
    const manifest = parseManifestDraft()
    if (!manifest) return
    setManifestError('')
    setManifestStatus('')
    try {
      const { runtimeExecution } = buildRuntimeExecutionEditorsFromForm({
        checkpointWriteOnTurnEnd,
        checkpointWriteOnApprovalPause,
        checkpointWriteOnResume,
        checkpointExposeRestoreContextToAgents,
        continuousImprovementEnabled,
        continuousImprovementMode,
        continuousImprovementMaxTurns,
        continuousImprovementMaxTotalActions,
        continuousImprovementMinTurns,
        continuousImprovementProgressEachTurn,
        continuousImprovementStopSignals,
        approvalMatrixDraft,
        codexSandboxMode,
        codexApprovalPolicy,
        codexProfile,
        codexAddDirs,
        codexMcpServersDraft,
        geminiApprovalMode,
        geminiSettingsOverwrite,
        geminiExtraEnvDraft,
        geminiMcpServersDraft,
      })
      const nextManifest = applyRuntimeExecutionToManifest(manifest, runtimeExecution, manifestApplyState)
      setManifestDraft(JSON.stringify(nextManifest, null, 2))
      setManifestValidation(null)
      setManifestDiff(null)
      setManifestStatus('runtime_execution policy를 blueprint draft에 반영했습니다.')
    } catch (e) {
      setManifestError(e instanceof Error ? e.message : String(e))
    }
  }

  if (!threadId) {
    return <div className="card"><div className="muted">thread를 먼저 선택하세요.</div></div>
  }

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <b>Thread Team</b>
        <button onClick={() => void refresh()} disabled={loading}>{loading ? 'Loading...' : 'Refresh'}</button>
      </div>
      <div className="muted" style={{ marginBottom: 8 }}>
        이 패널은 canonical Team Blueprint를 편집하고, 아래 roster editor는 빠른 membership 조정을 위한 보조 도구입니다.
      </div>
      {error && <div className="routeStatus routeStatusError">{error}</div>}
      {status && <div className="routeStatus">{status}</div>}

      <div className="row">
        <select
          style={{ minWidth: 320 }}
          value={selectedAgentId}
          onChange={(e) => setSelectedAgentId(e.target.value)}
        >
          <option value="">(추가할 agent 선택)</option>
          {candidateAgents.map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.name} [{agent.visibility}] {agent.model ? `· ${agent.model}` : ''}
            </option>
          ))}
        </select>
        <button onClick={() => void handleAddAgent()} disabled={!selectedAgentId || busyId === selectedAgentId}>
          Add
        </button>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
          <b>ddalggak Team Blueprint</b>
          <div className="row" style={{ gap: 8 }}>
            <select value={manifestApplyState} onChange={(e) => setManifestApplyState((e.target.value === 'pending' ? 'pending' : 'active'))}>
              <option value="active">install as active</option>
              <option value="pending">install as pending</option>
            </select>
            <button onClick={() => void handleExportManifest()} disabled={manifestBusy !== null}>{manifestBusy === 'export' ? 'Loading...' : 'Export'}</button>
            <button onClick={() => void handlePreviewManifestDiff()} disabled={manifestBusy !== null}>{manifestBusy === 'diff' ? 'Previewing...' : 'Preview diff'}</button>
            <button onClick={() => void handleValidateManifest()} disabled={manifestBusy !== null}>{manifestBusy === 'validate' ? 'Validating...' : 'Validate'}</button>
            <button onClick={() => void handleInstallManifest()} disabled={manifestBusy !== null}>{manifestBusy === 'install' ? 'Installing...' : 'Install'}</button>
            <button onClick={() => void handleCopyManifest()} disabled={manifestBusy !== null || !manifestDraft.trim()}>Copy</button>
            <button onClick={() => void handleDownloadManifest()} disabled={manifestBusy !== null || !manifestDraft.trim()}>Download</button>
          </div>
        </div>
        <div className="muted" style={{ marginTop: 6, marginBottom: 8 }}>
          Thread team을 ddalggak blueprint로 export/validate/install 합니다. team_blueprint_v1가 canonical schema입니다.
        </div>
        {manifestError && <div className="routeStatus routeStatusError">{manifestError}</div>}
        {manifestStatus && <div className="routeStatus">{manifestStatus}</div>}
        <label className="routeLabel" style={{ marginTop: 8 }}>
          blueprint JSON
          <textarea
            value={manifestDraft}
            onChange={(e) => setManifestDraft(e.target.value)}
            style={{ minHeight: 220, fontFamily: 'monospace' }}
            placeholder={`{
  "kind": "ddalggak_team_blueprint",
  "primary_schema": "team_blueprint_v1",
  "structure_v2": {
    "kind": "team_structure_v2",
    "version": 2,
    "participants": []
  }
}` }
          />
        </label>
        {manifestValidation && (
          <div className="muted" style={{ marginTop: 8 }}>
            validation: {manifestValidation.ok ? 'ok' : 'needs fixes'}
            {Array.isArray(manifestValidation.errors) && manifestValidation.errors.length > 0 ? ` · ${manifestValidation.errors.join(' / ')}` : ''}
          </div>
        )}
        {manifestDiff?.diff && (
          <div style={{ marginTop: 8, padding: 10, border: '1px solid var(--border-color, #ddd)', borderRadius: 8 }}>
            <div><b>Install preview</b></div>
            <div className="muted" style={{ marginTop: 4 }}>
              apply_state={String(manifestDiff?.apply_state || manifestApplyState)}
            </div>
            <div className="muted" style={{ marginTop: 4 }}>
              agents +{Number(manifestDiff?.diff?.summary?.agent_add_count || 0)} · -{Number(manifestDiff?.diff?.summary?.agent_remove_count || 0)} · ~{Number(manifestDiff?.diff?.summary?.agent_change_count || 0)}
            </div>
            <div className="muted" style={{ marginTop: 4 }}>
              tools +{Number(manifestDiff?.diff?.summary?.tool_add_count || 0)} · credentials +{Number(manifestDiff?.diff?.summary?.credential_add_count || 0)} · skills +{Number(manifestDiff?.diff?.summary?.skill_add_count || 0)}
            </div>
            <div className="muted" style={{ marginTop: 4 }}>
              install_proposal Δgaps={Number(manifestDiff?.diff?.summary?.install_proposal_gap_delta || 0)} · state={String(manifestDiff?.diff?.install_proposal?.candidate_state || 'none')}
            </div>
            <div className="muted" style={{ marginTop: 4 }}>
              action Δ tool_installs={Number(manifestDiff?.diff?.summary?.tool_install_delta || 0)} · credential_requests={Number(manifestDiff?.diff?.summary?.credential_request_delta || 0)} · generated_skills={Number(manifestDiff?.diff?.summary?.generated_skill_delta || 0)}
            </div>
            <div className="muted" style={{ marginTop: 4 }}>
              credential binding Δ bound={Number(manifestDiff?.diff?.summary?.bound_credential_delta || 0)}
            </div>
            <div className="muted" style={{ marginTop: 4 }}>
              structure Δ participants={Number(manifestDiff?.diff?.summary?.participant_delta || 0)} · pattern={String(manifestDiff?.diff?.structure_v2?.candidate_pattern || 'none')} · warnings={Number(manifestDiff?.diff?.summary?.structure_warning_delta || 0)}
            </div>
            {Array.isArray(manifestDiff?.diff?.preview_lines) && manifestDiff.diff.preview_lines.length > 0 && (
              <ul style={{ marginTop: 8 }}>
                {manifestDiff.diff.preview_lines.map((entry: any, index: number) => (
                  <li key={`preview-${index}`}>{String(entry || '')}</li>
                ))}
              </ul>
            )}
            {Array.isArray(manifestDiff?.diff?.agents?.added) && manifestDiff.diff.agents.added.length > 0 && (
              <div style={{ marginTop: 6 }}>
                <b style={{ fontSize: 12 }}>Agents to add</b>
                <div className="muted">{manifestDiff.diff.agents.added.join(', ')}</div>
              </div>
            )}
            {Array.isArray(manifestDiff?.diff?.agents?.removed) && manifestDiff.diff.agents.removed.length > 0 && (
              <div style={{ marginTop: 6 }}>
                <b style={{ fontSize: 12 }}>Agents to remove</b>
                <div className="muted">{manifestDiff.diff.agents.removed.join(', ')}</div>
              </div>
            )}
            {Array.isArray(manifestDiff?.diff?.credential_binding?.bound_added) && manifestDiff.diff.credential_binding.bound_added.length > 0 && (
              <div style={{ marginTop: 6 }}>
                <b style={{ fontSize: 12 }}>Credential bindings to add</b>
                <div className="muted">{manifestDiff.diff.credential_binding.bound_added.join(', ')}</div>
              </div>
            )}
          </div>
        )}
        {effectiveManifest && (
          <div style={{ marginTop: 10 }}>
            <div><b>Manifest runtime summary</b></div>
            <div className="muted" style={{ marginTop: 4 }}>
              kind={String(effectiveManifest?.kind || 'ddalggak_team_blueprint')} · version={String(effectiveManifest?.version || '1')} · apply_state={String(effectiveManifest?.apply_state || manifestApplyState)} · primary_schema={manifestPrimarySchema}
            </div>
            <div className="muted" style={{ marginTop: 4 }}>
              team_config status={String(teamConfigSummary?.status || '(unknown)')} · active_agents={Number(teamConfigSummary?.active_team?.agents?.length || 0)} · pending_agents={Number(teamConfigSummary?.pending_team?.agents?.length || 0)}
            </div>
          </div>
        )}
        {operatorCommandSuggestions.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <div><b>Telegram operator commands</b></div>
            <div className="muted" style={{ marginTop: 4 }}>GoC에서 상태를 본 뒤 ddalggak Telegram에서 이어서 써야 하는 시나리오를 위한 명령입니다.</div>
            <ul style={{ marginTop: 6 }}>
              {operatorCommandSuggestions.map((entry, index) => (
                <li key={`op-cmd-${index}`}><code>{entry}</code></li>
              ))}
            </ul>
          </div>
        )}
        {(patternConflictSummary || temporaryExecutionOverrideSummary || patternRecoverySummary) && (
          <div style={{ marginTop: 10 }}>
            <div><b>Pattern runtime state</b></div>
            {patternConflictSummary && (
              <div className="muted" style={{ marginTop: 4 }}>
                conflict={String(patternConflictSummary?.classification || 'none')} · current={String(patternConflictSummary?.current_pattern || '(unknown)')} · requested={String(patternConflictSummary?.requested_pattern || '(none)')}
                {patternConflictSummary?.reason ? ` · ${String(patternConflictSummary.reason)}` : ''}
              </div>
            )}
            {temporaryExecutionOverrideSummary && (
              <div className="muted" style={{ marginTop: 4 }}>
                temporary override={String(temporaryExecutionOverrideSummary?.effective_pattern || temporaryExecutionOverrideSummary?.mode || 'active')} · original={String(temporaryExecutionOverrideSummary?.original_pattern || '(unknown)')}
                {temporaryExecutionOverrideSummary?.reason ? ` · ${String(temporaryExecutionOverrideSummary.reason)}` : ''}
              </div>
            )}
            {patternRecoverySummary && (
              <div className="muted" style={{ marginTop: 4 }}>
                recovery={String(patternRecoverySummary?.recovery_mode || '(pending)')} · original={String(patternRecoverySummary?.original_pattern || '(unknown)')}
                {patternRecoverySummary?.reason ? ` · ${String(patternRecoverySummary.reason)}` : ''}
              </div>
            )}
          </div>
        )}
        {(knowledgeDocs.length > 0 || Object.keys(knowledgeSurfaceSummary).length > 0 || Object.keys(memoryPolicySummary).length > 0) && (
          <div style={{ marginTop: 10 }}>
            <div><b>Knowledge surface / memory policy</b></div>
            <div className="muted" style={{ marginTop: 4 }}>
              profile={String(knowledgeSurfaceSummary?.profile_id || knowledgeSurfaceSummary?.profileId || '(unset)')} · docs={knowledgeDocs.length} · stable_slots={stableSlots.length} · mutable_slots={mutableSlots.length}
            </div>
            {knowledgeDocs.length > 0 && (
              <ul style={{ marginTop: 6 }}>
                {knowledgeDocs.slice(0, 8).map((entry: any, index: number) => (
                  <li key={`kb-doc-${index}`}>{String(entry?.semantic_slot || entry?.doc_id || 'doc')} → <code>{String(entry?.file_name || entry?.fileName || 'unknown.md')}</code> · {String(entry?.write_policy || entry?.writePolicy || 'mutable')}</li>
                ))}
              </ul>
            )}
            {(stableSlots.length > 0 || mutableSlots.length > 0 || immutableFiles.length > 0) && (
              <div className="muted" style={{ marginTop: 4 }}>
                stable={stableSlots.join(', ') || '(none)'} · mutable={mutableSlots.join(', ') || '(none)'} · immutable_files={immutableFiles.slice(0, 6).join(', ') || '(none)'}
              </div>
            )}
            <div style={{ marginTop: 8 }}>
              <div className="muted">JSON 대신 form으로 KB 문서 구조와 메모리 정책을 편집합니다.</div>
              <div className="row" style={{ gap: 12, marginTop: 8, alignItems: 'flex-start' }}>
                <label className="routeLabel" style={{ flex: 1 }}>
                  Profile ID
                  <input value={knowledgeProfileId} onChange={(e) => setKnowledgeProfileId(e.target.value)} />
                </label>
                <label className="routeLabel" style={{ flex: 1 }}>
                  Display name
                  <input value={knowledgeDisplayName} onChange={(e) => setKnowledgeDisplayName(e.target.value)} />
                </label>
              </div>
              <div style={{ marginTop: 8 }}>
                <b style={{ fontSize: 12 }}>KB docs</b>
                <div className="muted" style={{ marginTop: 4 }}>semantic slot과 concrete filename을 팀 목적에 맞게 조정합니다.</div>
                {knowledgeDocRows.map((row, index) => (
                  <div key={`kb-form-row-${index}`} style={{ border: '1px solid var(--border-color, #ddd)', borderRadius: 8, padding: 8, marginTop: 8 }}>
                    <div className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
                      <label className="routeLabel" style={{ flex: 1 }}>
                        Slot
                        <input value={row.doc_id} onChange={(e) => setKnowledgeDocRows((prev) => prev.map((entry, i) => i === index ? { ...entry, doc_id: e.target.value } : entry))} />
                      </label>
                      <label className="routeLabel" style={{ flex: 1 }}>
                        File name
                        <input value={row.file_name} onChange={(e) => setKnowledgeDocRows((prev) => prev.map((entry, i) => i === index ? { ...entry, file_name: e.target.value } : entry))} />
                      </label>
                    </div>
                    <div className="row" style={{ gap: 8, marginTop: 8, alignItems: 'flex-start' }}>
                      <label className="routeLabel" style={{ flex: 1 }}>
                        Title
                        <input value={row.title} onChange={(e) => setKnowledgeDocRows((prev) => prev.map((entry, i) => i === index ? { ...entry, title: e.target.value } : entry))} />
                      </label>
                      <label className="routeLabel" style={{ flex: 1 }}>
                        Target roles (comma)
                        <input value={row.target_roles} onChange={(e) => setKnowledgeDocRows((prev) => prev.map((entry, i) => i === index ? { ...entry, target_roles: e.target.value } : entry))} />
                      </label>
                    </div>
                    <label className="routeLabel" style={{ display: 'block', marginTop: 8 }}>
                      Purpose
                      <input value={row.purpose} onChange={(e) => setKnowledgeDocRows((prev) => prev.map((entry, i) => i === index ? { ...entry, purpose: e.target.value } : entry))} />
                    </label>
                    <label className="routeLabel" style={{ display: 'block', marginTop: 8 }}>
                      Write hint
                      <input value={row.write_hint} onChange={(e) => setKnowledgeDocRows((prev) => prev.map((entry, i) => i === index ? { ...entry, write_hint: e.target.value } : entry))} />
                    </label>
                    <div className="row" style={{ marginTop: 8 }}>
                      <button onClick={() => setKnowledgeDocRows((prev) => prev.length > 1 ? prev.filter((_, i) => i !== index) : prev)}>Remove doc</button>
                    </div>
                  </div>
                ))}
                <div className="row" style={{ marginTop: 8 }}>
                  <button onClick={() => setKnowledgeDocRows((prev) => [...prev, emptyKnowledgeDocRow()])}>Add doc</button>
                </div>
              </div>
              <div className="row" style={{ gap: 12, marginTop: 8, alignItems: 'flex-start' }}>
                <label className="routeLabel" style={{ flex: 1 }}>
                  Stable semantic slots
                  <input value={stableSlotDraft} onChange={(e) => setStableSlotDraft(e.target.value)} placeholder="decisions, artifacts" />
                </label>
                <label className="routeLabel" style={{ flex: 1 }}>
                  Mutable semantic slots
                  <input value={mutableSlotDraft} onChange={(e) => setMutableSlotDraft(e.target.value)} placeholder="plan, research, progress" />
                </label>
              </div>
              <label className="routeLabel" style={{ display: 'block', marginTop: 8 }}>
                Immutable files
                <input value={immutableFilesDraft} onChange={(e) => setImmutableFilesDraft(e.target.value)} placeholder="knowledge_base_profile.json, knowledge_base_profile.md, knowledge_base_contract.md" />
              </label>
              <div className="row" style={{ marginTop: 8 }}>
                <button onClick={() => {
                  const formState = extractKnowledgeFormState(effectiveManifest)
                  setKnowledgeProfileId(formState.profileId)
                  setKnowledgeDisplayName(formState.displayName)
                  setKnowledgeDocRows(formState.docs)
                  setStableSlotDraft(formState.stableSlots.join(', '))
                  setMutableSlotDraft(formState.mutableSlots.join(', '))
                  setImmutableFilesDraft(formState.immutableFiles.join(', '))
                }}>
                  Reload from manifest
                </button>
                <button onClick={() => void handleApplyKnowledgeEditors()} disabled={manifestBusy !== null}>Apply KB to blueprint draft</button>
              </div>
            </div>
          </div>
        )}

        {(Object.keys(runtimeExecutionSummary).length > 0 || true) && (
          <div style={{ marginTop: 10 }}>
            <div><b>Runtime execution policy</b></div>
            <div className="muted" style={{ marginTop: 4 }}>
              checkpointing.turn_end={runtimeExecutionCheckpointingSummary?.write_on_turn_end === true ? 'on' : 'off'} · approval_pause={runtimeExecutionCheckpointingSummary?.write_on_approval_pause === false ? 'off' : 'on'} · resume={runtimeExecutionCheckpointingSummary?.write_on_resume === false ? 'off' : 'on'}
            </div>
            <div className="muted" style={{ marginTop: 4 }}>
              continuous_improvement={runtimeExecutionContinuousSummary?.enabled === true ? 'enabled' : 'disabled'} · mode={String(runtimeExecutionContinuousSummary?.mode || 'until_quality_threshold')} · max_turns={String(runtimeExecutionContinuousSummary?.max_turns ?? 8)} · max_total_actions={String(runtimeExecutionContinuousSummary?.max_total_actions ?? 48)}
            </div>
            <div className="muted" style={{ marginTop: 4 }}>
              codex sandbox={String(runtimeExecutionCodexSummary?.sandbox_mode || 'workspace-write')} · codex approval={String(runtimeExecutionCodexSummary?.approval_policy || 'never')} · codex mcp={Object.keys(asObject(runtimeExecutionCodexSummary?.mcp_servers || runtimeExecutionCodexSummary?.mcpServers)).length}
            </div>
            <div className="muted" style={{ marginTop: 4 }}>
              gemini approval_mode={String(runtimeExecutionGeminiSummary?.approval_mode || 'default')} · gemini settings_overwrite={String(runtimeExecutionGeminiSummary?.settings_overwrite || 'merge')} · gemini mcp={Object.keys(asObject(runtimeExecutionGeminiSummary?.mcp_servers || runtimeExecutionGeminiSummary?.mcpServers)).length}
            </div>
            <div style={{ marginTop: 8 }}>
              <div className="muted">GoC control-plane에서 checkpoint / continuous improvement / provider sandbox·approval·MCP 정책을 함께 편집합니다.</div>
              <div style={{ marginTop: 8, border: '1px solid var(--border-color, #ddd)', borderRadius: 8, padding: 10 }}>
                <b style={{ fontSize: 12 }}>Checkpointing</b>
                <div className="row" style={{ gap: 12, marginTop: 8, flexWrap: 'wrap' }}>
                  <label><input type="checkbox" checked={checkpointWriteOnTurnEnd} onChange={(e) => setCheckpointWriteOnTurnEnd(e.target.checked)} /> write_on_turn_end</label>
                  <label><input type="checkbox" checked={checkpointWriteOnApprovalPause} onChange={(e) => setCheckpointWriteOnApprovalPause(e.target.checked)} /> write_on_approval_pause</label>
                  <label><input type="checkbox" checked={checkpointWriteOnResume} onChange={(e) => setCheckpointWriteOnResume(e.target.checked)} /> write_on_resume</label>
                  <label><input type="checkbox" checked={checkpointExposeRestoreContextToAgents} onChange={(e) => setCheckpointExposeRestoreContextToAgents(e.target.checked)} /> expose_restore_context_to_agents</label>
                </div>
              </div>
              <div style={{ marginTop: 8, border: '1px solid var(--border-color, #ddd)', borderRadius: 8, padding: 10 }}>
                <b style={{ fontSize: 12 }}>Continuous improvement</b>
                <div className="row" style={{ gap: 12, marginTop: 8, flexWrap: 'wrap' }}>
                  <label><input type="checkbox" checked={continuousImprovementEnabled} onChange={(e) => setContinuousImprovementEnabled(e.target.checked)} /> enabled</label>
                  <label><input type="checkbox" checked={continuousImprovementProgressEachTurn} onChange={(e) => setContinuousImprovementProgressEachTurn(e.target.checked)} /> progress_report_each_turn</label>
                </div>
                <div className="row" style={{ gap: 12, marginTop: 8, alignItems: 'flex-start' }}>
                  <label className="routeLabel" style={{ flex: 1 }}>
                    Mode
                    <input value={continuousImprovementMode} onChange={(e) => setContinuousImprovementMode(e.target.value)} />
                  </label>
                  <label className="routeLabel" style={{ flex: 1 }}>
                    Max turns
                    <input value={continuousImprovementMaxTurns} onChange={(e) => setContinuousImprovementMaxTurns(e.target.value)} />
                  </label>
                  <label className="routeLabel" style={{ flex: 1 }}>
                    Max total actions
                    <input value={continuousImprovementMaxTotalActions} onChange={(e) => setContinuousImprovementMaxTotalActions(e.target.value)} />
                  </label>
                  <label className="routeLabel" style={{ flex: 1 }}>
                    Min turns
                    <input value={continuousImprovementMinTurns} onChange={(e) => setContinuousImprovementMinTurns(e.target.value)} />
                  </label>
                </div>
                <label className="routeLabel" style={{ display: 'block', marginTop: 8 }}>
                  Stop signals (comma)
                  <input value={continuousImprovementStopSignals} onChange={(e) => setContinuousImprovementStopSignals(e.target.value)} />
                </label>
              </div>
              <div style={{ marginTop: 8, border: '1px solid var(--border-color, #ddd)', borderRadius: 8, padding: 10 }}>
                <b style={{ fontSize: 12 }}>Approval matrix</b>
                <label className="routeLabel" style={{ display: 'block', marginTop: 8 }}>
                  approval_matrix JSON
                  <textarea value={approvalMatrixDraft} onChange={(e) => setApprovalMatrixDraft(e.target.value)} style={{ minHeight: 100, fontFamily: 'monospace' }} />
                </label>
                <div className="muted">현재 keys: {Object.keys(runtimeExecutionApprovalSummary).join(', ') || '(default only)'}</div>
              </div>
              <div style={{ marginTop: 8, border: '1px solid var(--border-color, #ddd)', borderRadius: 8, padding: 10 }}>
                <b style={{ fontSize: 12 }}>Codex provider policy</b>
                <div className="row" style={{ gap: 12, marginTop: 8, alignItems: 'flex-start' }}>
                  <label className="routeLabel" style={{ flex: 1 }}>
                    Sandbox mode
                    <input value={codexSandboxMode} onChange={(e) => setCodexSandboxMode(e.target.value)} />
                  </label>
                  <label className="routeLabel" style={{ flex: 1 }}>
                    Approval policy
                    <input value={codexApprovalPolicy} onChange={(e) => setCodexApprovalPolicy(e.target.value)} />
                  </label>
                  <label className="routeLabel" style={{ flex: 1 }}>
                    Profile
                    <input value={codexProfile} onChange={(e) => setCodexProfile(e.target.value)} />
                  </label>
                </div>
                <label className="routeLabel" style={{ display: 'block', marginTop: 8 }}>
                  add_dirs (comma)
                  <input value={codexAddDirs} onChange={(e) => setCodexAddDirs(e.target.value)} />
                </label>
                <label className="routeLabel" style={{ display: 'block', marginTop: 8 }}>
                  mcp_servers JSON
                  <textarea value={codexMcpServersDraft} onChange={(e) => setCodexMcpServersDraft(e.target.value)} style={{ minHeight: 100, fontFamily: 'monospace' }} />
                </label>
              </div>
              <div style={{ marginTop: 8, border: '1px solid var(--border-color, #ddd)', borderRadius: 8, padding: 10 }}>
                <b style={{ fontSize: 12 }}>Gemini provider policy</b>
                <div className="row" style={{ gap: 12, marginTop: 8, alignItems: 'flex-start' }}>
                  <label className="routeLabel" style={{ flex: 1 }}>
                    Approval mode
                    <input value={geminiApprovalMode} onChange={(e) => setGeminiApprovalMode(e.target.value)} />
                  </label>
                  <label className="routeLabel" style={{ flex: 1 }}>
                    Settings overwrite
                    <input value={geminiSettingsOverwrite} onChange={(e) => setGeminiSettingsOverwrite(e.target.value)} />
                  </label>
                </div>
                <label className="routeLabel" style={{ display: 'block', marginTop: 8 }}>
                  extra_env JSON
                  <textarea value={geminiExtraEnvDraft} onChange={(e) => setGeminiExtraEnvDraft(e.target.value)} style={{ minHeight: 100, fontFamily: 'monospace' }} />
                </label>
                <label className="routeLabel" style={{ display: 'block', marginTop: 8 }}>
                  mcp_servers JSON
                  <textarea value={geminiMcpServersDraft} onChange={(e) => setGeminiMcpServersDraft(e.target.value)} style={{ minHeight: 100, fontFamily: 'monospace' }} />
                </label>
              </div>
              <div className="row" style={{ marginTop: 8 }}>
                <button onClick={() => {
                  const formState = extractRuntimeExecutionFormState(effectiveManifest)
                  setCheckpointWriteOnTurnEnd(formState.checkpointWriteOnTurnEnd)
                  setCheckpointWriteOnApprovalPause(formState.checkpointWriteOnApprovalPause)
                  setCheckpointWriteOnResume(formState.checkpointWriteOnResume)
                  setCheckpointExposeRestoreContextToAgents(formState.checkpointExposeRestoreContextToAgents)
                  setContinuousImprovementEnabled(formState.continuousImprovementEnabled)
                  setContinuousImprovementMode(formState.continuousImprovementMode)
                  setContinuousImprovementMaxTurns(formState.continuousImprovementMaxTurns)
                  setContinuousImprovementMaxTotalActions(formState.continuousImprovementMaxTotalActions)
                  setContinuousImprovementMinTurns(formState.continuousImprovementMinTurns)
                  setContinuousImprovementProgressEachTurn(formState.continuousImprovementProgressEachTurn)
                  setContinuousImprovementStopSignals(formState.continuousImprovementStopSignals)
                  setApprovalMatrixDraft(formState.approvalMatrixDraft)
                  setCodexSandboxMode(formState.codexSandboxMode)
                  setCodexApprovalPolicy(formState.codexApprovalPolicy)
                  setCodexProfile(formState.codexProfile)
                  setCodexAddDirs(formState.codexAddDirs)
                  setCodexMcpServersDraft(formState.codexMcpServersDraft)
                  setGeminiApprovalMode(formState.geminiApprovalMode)
                  setGeminiSettingsOverwrite(formState.geminiSettingsOverwrite)
                  setGeminiExtraEnvDraft(formState.geminiExtraEnvDraft)
                  setGeminiMcpServersDraft(formState.geminiMcpServersDraft)
                }}>Reload runtime policy from manifest</button>
                <button onClick={() => void handleApplyRuntimeExecutionEditors()} disabled={manifestBusy !== null}>Apply runtime policy to blueprint draft</button>
              </div>
            </div>
          </div>
        )}

        {structureSummary && (
          <div style={{ marginTop: 10 }}>
            <div><b>Structure v2</b></div>
            <div className="muted" style={{ marginTop: 4 }}>primary_schema={manifestPrimarySchema}</div>
            <div className="muted" style={{ marginTop: 4 }}>
              pattern={String(structureSummary?.topology?.pattern || 'hybrid')} · participants={Number(structureSummary?.participants?.length || 0)} · nodes={Number(structureSummary?.topology?.nodes?.length || 0)} · edges={Number(structureSummary?.topology?.edges?.length || 0)} · final_owner={String(structureSummary?.control_policy?.final_answer_owner_participant_id || structureSummary?.topology?.final_participant_id || '(unset)')}
            </div>
            <div className="muted" style={{ marginTop: 4 }}>
              validation ready={validationSummary?.pattern_ready === true ? 'yes' : 'no'} · strict_ready={validationSummary?.strict_pattern_ready === true ? 'yes' : 'no'} · warnings={Number(validationSummary?.warnings?.length || 0)} · errors={Number(validationSummary?.errors?.length || 0)}
            </div>
            <div style={{ marginTop: 8 }}>
              <div className="muted">JSON 대신 form으로 participants / topology nodes / edges를 편집합니다.</div>
              <TopologyCanvasEditor
                participants={topologyParticipantRows}
                nodes={topologyNodeRows}
                edges={topologyEdgeRows}
                finalParticipantId={topologyFinalParticipantDraft}
                finalOwnerParticipantId={topologyFinalOwnerDraft}
                validationWarnings={Array.isArray(validationSummary?.warnings) ? validationSummary.warnings.map((entry: any) => String(entry)) : []}
                validationErrors={Array.isArray(validationSummary?.errors) ? validationSummary.errors.map((entry: any) => String(entry)) : []}
                onParticipantsChange={setTopologyParticipantRows}
                onNodesChange={setTopologyNodeRows}
                onEdgesChange={setTopologyEdgeRows}
                onFinalParticipantChange={setTopologyFinalParticipantDraft}
                onFinalOwnerParticipantChange={setTopologyFinalOwnerDraft}
              />
              <div className="row" style={{ gap: 12, marginTop: 8, alignItems: 'flex-start' }}>
                <label className="routeLabel" style={{ flex: 1 }}>
                  Pattern
                  <input value={topologyPatternDraft} onChange={(e) => setTopologyPatternDraft(e.target.value)} placeholder="hybrid / debate / committee / graph" />
                </label>
                <label className="routeLabel" style={{ flex: 1 }}>
                  Execution pattern
                  <input value={topologyExecutionPatternDraft} onChange={(e) => setTopologyExecutionPatternDraft(e.target.value)} placeholder="sequential / parallel / graph" />
                </label>
              </div>
              <div className="row" style={{ gap: 12, marginTop: 8, alignItems: 'flex-start' }}>
                <label className="routeLabel" style={{ flex: 1 }}>
                  Final participant
                  <input value={topologyFinalParticipantDraft} onChange={(e) => setTopologyFinalParticipantDraft(e.target.value)} placeholder="participant id" />
                </label>
                <label className="routeLabel" style={{ flex: 1 }}>
                  Final owner participant
                  <input value={topologyFinalOwnerDraft} onChange={(e) => setTopologyFinalOwnerDraft(e.target.value)} placeholder="participant id" />
                </label>
              </div>
              <div style={{ marginTop: 8 }}>
                <b style={{ fontSize: 12 }}>Participants</b>
                {topologyParticipantRows.map((row, index) => (
                  <div key={`topology-participant-form-${index}`} style={{ border: '1px solid var(--border-color, #ddd)', borderRadius: 8, padding: 8, marginTop: 8 }}>
                    <div className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
                      <label className="routeLabel" style={{ flex: 1 }}>
                        Participant ID
                        <input value={row.participant_id} onChange={(e) => setTopologyParticipantRows((prev) => prev.map((entry, i) => i === index ? { ...entry, participant_id: e.target.value } : entry))} />
                      </label>
                      <label className="routeLabel" style={{ flex: 1 }}>
                        Kind
                        <input value={row.kind} onChange={(e) => setTopologyParticipantRows((prev) => prev.map((entry, i) => i === index ? { ...entry, kind: e.target.value } : entry))} />
                      </label>
                    </div>
                    <div className="row" style={{ gap: 8, marginTop: 8, alignItems: 'flex-start' }}>
                      <label className="routeLabel" style={{ flex: 1 }}>
                        Role
                        <input value={row.role} onChange={(e) => setTopologyParticipantRows((prev) => prev.map((entry, i) => i === index ? { ...entry, role: e.target.value } : entry))} />
                      </label>
                      <label className="routeLabel" style={{ flex: 1 }}>
                        Label
                        <input value={row.label} onChange={(e) => setTopologyParticipantRows((prev) => prev.map((entry, i) => i === index ? { ...entry, label: e.target.value } : entry))} />
                      </label>
                      <label className="routeLabel" style={{ flex: 1 }}>
                        Provider
                        <input value={row.provider} onChange={(e) => setTopologyParticipantRows((prev) => prev.map((entry, i) => i === index ? { ...entry, provider: e.target.value } : entry))} />
                      </label>
                    </div>
                    <div className="row" style={{ marginTop: 8 }}>
                      <button onClick={() => setTopologyParticipantRows((prev) => prev.length > 1 ? prev.filter((_, i) => i !== index) : prev)}>Remove participant</button>
                    </div>
                  </div>
                ))}
                <div className="row" style={{ marginTop: 8 }}>
                  <button onClick={() => setTopologyParticipantRows((prev) => [...prev, emptyTopologyParticipantRow()])}>Add participant</button>
                </div>
              </div>
              <div style={{ marginTop: 8 }}>
                <b style={{ fontSize: 12 }}>Topology nodes</b>
                {topologyNodeRows.map((row, index) => (
                  <div key={`topology-node-form-${index}`} style={{ border: '1px solid var(--border-color, #ddd)', borderRadius: 8, padding: 8, marginTop: 8 }}>
                    <div className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
                      <label className="routeLabel" style={{ flex: 1 }}>
                        Node ID
                        <input value={row.node_id} onChange={(e) => setTopologyNodeRows((prev) => prev.map((entry, i) => i === index ? { ...entry, node_id: e.target.value } : entry))} />
                      </label>
                      <label className="routeLabel" style={{ flex: 1 }}>
                        Participant ID
                        <input value={row.participant_id} onChange={(e) => setTopologyNodeRows((prev) => prev.map((entry, i) => i === index ? { ...entry, participant_id: e.target.value } : entry))} />
                      </label>
                      <label className="routeLabel" style={{ flex: 1 }}>
                        Kind
                        <input value={row.kind} onChange={(e) => setTopologyNodeRows((prev) => prev.map((entry, i) => i === index ? { ...entry, kind: e.target.value } : entry))} />
                      </label>
                      <label className="routeLabel" style={{ flex: 1 }}>
                        Stage
                        <input value={row.stage_index} onChange={(e) => setTopologyNodeRows((prev) => prev.map((entry, i) => i === index ? { ...entry, stage_index: e.target.value } : entry))} />
                      </label>
                    </div>
                    <div className="row" style={{ marginTop: 8 }}>
                      <button onClick={() => setTopologyNodeRows((prev) => prev.length > 1 ? prev.filter((_, i) => i !== index) : prev)}>Remove node</button>
                    </div>
                  </div>
                ))}
                <div className="row" style={{ marginTop: 8 }}>
                  <button onClick={() => setTopologyNodeRows((prev) => [...prev, emptyTopologyNodeRow()])}>Add node</button>
                </div>
              </div>
              <div style={{ marginTop: 8 }}>
                <b style={{ fontSize: 12 }}>Topology edges</b>
                {topologyEdgeRows.map((row, index) => (
                  <div key={`topology-edge-form-${index}`} style={{ border: '1px solid var(--border-color, #ddd)', borderRadius: 8, padding: 8, marginTop: 8 }}>
                    <div className="row" style={{ gap: 8, alignItems: 'flex-start' }}>
                      <label className="routeLabel" style={{ flex: 1 }}>
                        From
                        <input value={row.from} onChange={(e) => setTopologyEdgeRows((prev) => prev.map((entry, i) => i === index ? { ...entry, from: e.target.value } : entry))} />
                      </label>
                      <label className="routeLabel" style={{ flex: 1 }}>
                        To
                        <input value={row.to} onChange={(e) => setTopologyEdgeRows((prev) => prev.map((entry, i) => i === index ? { ...entry, to: e.target.value } : entry))} />
                      </label>
                    </div>
                    <div className="row" style={{ gap: 8, marginTop: 8, alignItems: 'flex-start' }}>
                      <label className="routeLabel" style={{ flex: 1 }}>
                        Condition
                        <input value={row.condition} onChange={(e) => setTopologyEdgeRows((prev) => prev.map((entry, i) => i === index ? { ...entry, condition: e.target.value } : entry))} />
                      </label>
                      <label className="routeLabel" style={{ flex: 1 }}>
                        Label
                        <input value={row.label} onChange={(e) => setTopologyEdgeRows((prev) => prev.map((entry, i) => i === index ? { ...entry, label: e.target.value } : entry))} />
                      </label>
                    </div>
                    <div className="row" style={{ marginTop: 8 }}>
                      <button onClick={() => setTopologyEdgeRows((prev) => prev.length > 1 ? prev.filter((_, i) => i !== index) : prev)}>Remove edge</button>
                    </div>
                  </div>
                ))}
                <div className="row" style={{ marginTop: 8 }}>
                  <button onClick={() => setTopologyEdgeRows((prev) => [...prev, emptyTopologyEdgeRow()])}>Add edge</button>
                </div>
              </div>
              <div className="row" style={{ marginTop: 8 }}>
                <button onClick={() => {
                  const formState = extractTopologyFormState(effectiveManifest)
                  setTopologyPatternDraft(formState.pattern)
                  setTopologyExecutionPatternDraft(formState.executionPattern)
                  setTopologyFinalParticipantDraft(formState.finalParticipantId)
                  setTopologyFinalOwnerDraft(formState.finalOwnerParticipantId)
                  setTopologyParticipantRows(formState.participants)
                  setTopologyNodeRows(formState.nodes)
                  setTopologyEdgeRows(formState.edges)
                }}>Reload topology from manifest</button>
                <button onClick={() => void handleApplyTopologyEditors()} disabled={manifestBusy !== null}>Apply topology to blueprint draft</button>
              </div>
            </div>
            {Array.isArray(structureSummary?.participants) && structureSummary.participants.length > 0 && (
              <ul style={{ marginTop: 4 }}>
                {structureSummary.participants.slice(0, 6).map((entry: any, index: number) => (
                  <li key={`participant-${index}`}>{String(entry?.participant_id || 'participant')} · {String(entry?.kind || 'agent')} · {String(entry?.role || 'specialist')}</li>
                ))}
              </ul>
            )}
            {topologyNodes.length > 0 && (
              <div style={{ marginTop: 6 }}>
                <b style={{ fontSize: 12 }}>Topology nodes</b>
                <ul style={{ marginTop: 4 }}>
                  {topologyNodes.slice(0, 8).map((entry: any, index: number) => (
                    <li key={`topology-node-${index}`}>{String(entry?.node_id || entry?.participant_id || entry?.id || 'node')} · kind={String(entry?.kind || 'agent')} · stage={String(entry?.stage_index ?? entry?.stage ?? '-')}</li>
                  ))}
                </ul>
              </div>
            )}
            {topologyEdges.length > 0 && (
              <div style={{ marginTop: 6 }}>
                <b style={{ fontSize: 12 }}>Topology edges</b>
                <ul style={{ marginTop: 4 }}>
                  {topologyEdges.slice(0, 8).map((entry: any, index: number) => (
                    <li key={`topology-edge-${index}`}>{String(entry?.from || entry?.from_id || entry?.source || '?')} → {String(entry?.to || entry?.to_id || entry?.target || '?')} · {String(entry?.condition || entry?.label || entry?.type || 'edge')}</li>
                  ))}
                </ul>
              </div>
            )}
            {Array.isArray(validationSummary?.errors) && validationSummary.errors.length > 0 && (
              <div style={{ marginTop: 6 }}>
                <b style={{ fontSize: 12 }}>Validation errors</b>
                <ul style={{ marginTop: 4 }}>
                  {validationSummary.errors.slice(0, 6).map((entry: any, index: number) => (
                    <li key={`structure-error-${index}`}>{String(entry || '')}</li>
                  ))}
                </ul>
              </div>
            )}
            {Array.isArray(validationSummary?.warnings) && validationSummary.warnings.length > 0 && (
              <div style={{ marginTop: 6 }}>
                <b style={{ fontSize: 12 }}>Validation warnings</b>
                <ul style={{ marginTop: 4 }}>
                  {validationSummary.warnings.slice(0, 6).map((entry: any, index: number) => (
                    <li key={`structure-warning-${index}`}>{String(entry || '')}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
        {compatibilityTeamSummary && (
          <div style={{ marginTop: 10 }}>
            <div><b>Compatibility team payload</b></div>
            <div className="muted" style={{ marginTop: 4 }}>
              team_name={String(compatibilityTeamSummary?.team_name || '(unset)')} · agents={Number(compatibilityTeamSummary?.agents?.length || 0)} · interaction_pattern={String(compatibilityTeamSummary?.interaction_spec?.execution_pattern || compatibilityTeamSummary?.interaction_spec?.pattern || '(unset)')}
            </div>
          </div>
        )}
        {installProposalSummary && (
          <div style={{ marginTop: 10 }}>
            <div><b>Install proposal</b></div>
            <div className="muted" style={{ marginTop: 4 }}>
              source={String(installProposalSummary?.source || 'team_requirement')} · blocking={installProposalSummary?.blocking ? 'yes' : 'no'} · gaps={Number(installProposalSummary?.gap_count || 0)}
            </div>
            {installProposalStateSummary && (
              <div className="muted" style={{ marginTop: 4 }}>
                state={String(installProposalStateSummary?.status || 'none')} · apply_state={String(installProposalStateSummary?.apply_state || installProposalSummary?.apply_state || 'pending')}
              </div>
            )}
            {Array.isArray(installProposalSummary?.gap_preview_lines) && installProposalSummary.gap_preview_lines.length > 0 && (
              <ul style={{ marginTop: 6 }}>
                {installProposalSummary.gap_preview_lines.slice(0, 6).map((entry: any, index: number) => (
                  <li key={`gap-preview-${index}`}>{String(entry || '')}</li>
                ))}
              </ul>
            )}
            {installProposalSummary?.actions && (
              <div style={{ marginTop: 6 }}>
                <b style={{ fontSize: 12 }}>Action proposals</b>
                <div className="muted" style={{ marginTop: 4 }}>
                  tool_installs={Number(installProposalSummary?.actions?.summary?.tool_install_count || 0)} · credential_requests={Number(installProposalSummary?.actions?.summary?.credential_request_count || 0)} · generated_skills={Number(installProposalSummary?.actions?.summary?.generated_skill_count || 0)}
                </div>
                {Array.isArray(installProposalSummary?.actions?.tool_install_proposals) && installProposalSummary.actions.tool_install_proposals.length > 0 && (
                  <ul style={{ marginTop: 4 }}>
                    {installProposalSummary.actions.tool_install_proposals.slice(0, 4).map((entry: any, index: number) => (
                      <li key={`tool-install-${index}`}>{String(entry?.tool_id || 'tool')} · by {String(entry?.required_by || 'agent')} · {String(entry?.strategy || 'connect_runtime_tool')}</li>
                    ))}
                  </ul>
                )}
                {Array.isArray(installProposalSummary?.actions?.credential_requests) && installProposalSummary.actions.credential_requests.length > 0 && (
                  <ul style={{ marginTop: 4 }}>
                    {installProposalSummary.actions.credential_requests.slice(0, 4).map((entry: any, index: number) => (
                      <li key={`cred-request-${index}`}>{String(entry?.credential_key || 'API_KEY')} · by {String(entry?.required_by || 'agent')}</li>
                    ))}
                  </ul>
                )}
                {Array.isArray(installProposalSummary?.actions?.generated_skill_proposals) && installProposalSummary.actions.generated_skill_proposals.length > 0 && (
                  <ul style={{ marginTop: 4 }}>
                    {installProposalSummary.actions.generated_skill_proposals.slice(0, 4).map((entry: any, index: number) => (
                      <li key={`skill-proposal-${index}`}>{String(entry?.skill_id || 'skill')} · by {String(entry?.required_by || 'agent')}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
            {Array.isArray(installProposalSummary?.suggested_commands) && installProposalSummary.suggested_commands.length > 0 && (
              <div style={{ marginTop: 6 }}>
                <b style={{ fontSize: 12 }}>Suggested commands</b>
                <ul style={{ marginTop: 4 }}>
                  {installProposalSummary.suggested_commands.slice(0, 6).map((entry: any, index: number) => (
                    <li key={`cmd-${index}`}><code>{String(entry || '')}</code></li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
        {credentialBindingSummary && (
          <div style={{ marginTop: 10 }}>
            <div><b>Credential bindings</b></div>
            <div className="muted" style={{ marginTop: 4 }}>
              bound={Number(credentialBindingSummary?.summary?.bound_count || credentialBindingSummary?.bindings?.length || 0)}
            </div>
            {Array.isArray(credentialBindingSummary?.bindings) && credentialBindingSummary.bindings.length > 0 && (
              <ul style={{ marginTop: 4 }}>
                {credentialBindingSummary.bindings.slice(0, 6).map((entry: any, index: number) => (
                  <li key={`binding-${index}`}>{String(entry?.credential_key || 'API_KEY')} · {String(entry?.masked_value || '(bound)')} · {String(entry?.source || 'telegram_command')}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        {requirementSummary && (
          <div style={{ marginTop: 10 }}>
            <div><b>Requirements</b></div>
            <div className="muted" style={{ marginTop: 4 }}>
              tools={Number(requirementSummary?.summary?.tool_count || requirementSummary?.tools?.length || 0)} · credentials={Number(requirementSummary?.summary?.credential_count || requirementSummary?.credentials?.length || 0)}
            </div>
            {Array.isArray(requirementSummary?.tools) && requirementSummary.tools.length > 0 && (
              <div style={{ marginTop: 6 }}>
                <b style={{ fontSize: 12 }}>Tools</b>
                <ul style={{ marginTop: 4 }}>
                  {requirementSummary.tools.slice(0, 6).map((entry: any, index: number) => (
                    <li key={`tool-${index}`}>{String(entry?.tool_id || 'tool')} · by {String(entry?.required_by || 'agent')}</li>
                  ))}
                </ul>
              </div>
            )}
            {Array.isArray(requirementSummary?.credentials) && requirementSummary.credentials.length > 0 && (
              <div style={{ marginTop: 6 }}>
                <b style={{ fontSize: 12 }}>Credentials</b>
                <ul style={{ marginTop: 4 }}>
                  {requirementSummary.credentials.slice(0, 6).map((entry: any, index: number) => (
                    <li key={`cred-${index}`}>{String(entry?.credential_key || 'API_KEY')} · by {String(entry?.required_by || 'agent')}</li>
                  ))}
                </ul>
              </div>
            )}
            {Array.isArray(requirementSummary?.install_hints) && requirementSummary.install_hints.length > 0 && (
              <div style={{ marginTop: 6 }}>
                <b style={{ fontSize: 12 }}>Install hints</b>
                <ul style={{ marginTop: 4 }}>
                  {requirementSummary.install_hints.slice(0, 6).map((entry: any, index: number) => (
                    <li key={`hint-${index}`}>{String(entry || '')}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      <div style={{ marginTop: 16 }}><b>Agent Team blueprint catalog</b></div>
      <div className="muted" style={{ marginTop: 4 }}>
        현재 thread의 blueprint를 재사용 가능한 team card로 저장하고, 같은 서비스의 다른 thread에 다시 설치할 수 있습니다.
      </div>
      {teamCatalogError && <div className="routeStatus routeStatusError" style={{ marginTop: 8 }}>{teamCatalogError}</div>}
      {teamCatalogStatus && <div className="routeStatus" style={{ marginTop: 8 }}>{teamCatalogStatus}</div>}
      <div className="row" style={{ gap: 12, marginTop: 8, alignItems: 'flex-start' }}>
        <label className="routeLabel" style={{ flex: 1 }}>
          Catalog title
          <input value={teamBlueprintTitle} onChange={(e) => setTeamBlueprintTitle(e.target.value)} placeholder="Research + Reviewer default team" />
        </label>
        <label className="routeLabel" style={{ flex: 1 }}>
          Summary
          <input value={teamBlueprintSummary} onChange={(e) => setTeamBlueprintSummary(e.target.value)} placeholder="코드 검토/리서치/최종 synthesis에 적합한 기본 팀" />
        </label>
      </div>
      <div className="row" style={{ gap: 12, marginTop: 8, alignItems: 'flex-start' }}>
        <label className="routeLabel" style={{ flex: 1 }}>
          Tags (comma)
          <input value={teamBlueprintTagsDraft} onChange={(e) => setTeamBlueprintTagsDraft(e.target.value)} placeholder="research, review, coding" />
        </label>
        <label className="routeLabel" style={{ flex: 1 }}>
          Good for (one per line)
          <textarea value={teamBlueprintGoodForDraft} onChange={(e) => setTeamBlueprintGoodForDraft(e.target.value)} style={{ minHeight: 72 }} placeholder={"large repo review\nlong-running implementation\nparallel research + synthesis"} />
        </label>
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <button onClick={() => void handleSaveCurrentTeamToCatalog()} disabled={teamCatalogBusy !== null}>
          {teamCatalogBusy === 'save' ? 'Saving...' : 'Save current team to catalog'}
        </button>
        <button onClick={() => void reloadTeamCatalog()} disabled={teamCatalogBusy !== null}>Refresh catalog</button>
      </div>
      <div className="routeTableWrap" style={{ marginTop: 8 }}>
        <table className="routeTable">
          <thead>
            <tr>
              <th>title</th>
              <th>summary</th>
              <th>good for</th>
              <th>tags</th>
              <th>created_at</th>
              <th>actions</th>
            </tr>
          </thead>
          <tbody>
            {teamCatalogItems.map((item) => (
              <tr key={item.nodeId}>
                <td><b>{item.title || '-'}</b></td>
                <td style={{ maxWidth: 280 }}>{item.summary || '-'}</td>
                <td style={{ maxWidth: 260 }}>
                  {item.recommendedFor.length > 0 ? (
                    <ul style={{ margin: 0, paddingLeft: 18 }}>
                      {item.recommendedFor.slice(0, 4).map((entry, index) => <li key={`${item.nodeId}-good-${index}`}>{entry}</li>)}
                    </ul>
                  ) : '-'}
                </td>
                <td>{item.tags.length > 0 ? item.tags.join(', ') : '-'}</td>
                <td>{item.createdAt || '-'}</td>
                <td>
                  <div className="row" style={{ marginBottom: 0 }}>
                    <button onClick={() => void handleInstallCatalogItem(item)} disabled={teamCatalogBusy !== null}>
                      {teamCatalogBusy === item.nodeId ? 'Installing...' : `Install (${manifestApplyState})`}
                    </button>
                    <button onClick={() => void copyText(JSON.stringify(item.manifest, null, 2))}>Copy JSON</button>
                  </div>
                </td>
              </tr>
            ))}
            {teamCatalogItems.length === 0 && (
              <tr>
                <td colSpan={6}><span className="muted">저장된 team card가 없습니다. 현재 thread team을 먼저 catalog에 저장하세요.</span></td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div style={{ marginTop: 16 }}><b>Compatibility roster editor</b></div>
      <div className="muted" style={{ marginTop: 4, marginBottom: 8 }}>
        아래 편집기는 빠른 membership 조정용입니다. structure_v2가 있는 팀에서는 blueprint export/validate/install이 기준 경로입니다.
      </div>
      <div className="routeTableWrap">
        <table className="routeTable">
          <thead>
            <tr>
              <th>order</th>
              <th>agent</th>
              <th>enabled</th>
              <th>actions</th>
            </tr>
          </thead>
          <tbody>
            {(conversation?.agents || []).map((member, index) => (
              <tr key={member.agent_id}>
                <td>{index + 1}</td>
                <td>
                  <div><b>{member.agent.name}</b></div>
                  <div className="muted">{member.agent.id.slice(0, 8)} · {member.agent.visibility}</div>
                  <label className="routeLabel" style={{ marginTop: 8 }}>
                    overrides_json
                    <textarea
                      value={overridesDraft[member.agent_id] || '{}'}
                      onChange={(e) => setOverridesDraft((prev) => ({ ...prev, [member.agent_id]: e.target.value }))}
                      style={{ minHeight: 72 }}
                    />
                  </label>
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={member.enabled}
                    onChange={(e) => void handleToggleEnabled(member, e.target.checked)}
                    disabled={busyId === member.agent_id}
                  />
                </td>
                <td>
                  <div className="row agentsActionRow">
                    <button onClick={() => void handleMove(member, -1)} disabled={index === 0 || busyId === member.agent_id}>Up</button>
                    <button
                      onClick={() => void handleMove(member, 1)}
                      disabled={index === (conversation?.agents.length || 0) - 1 || busyId === member.agent_id}
                    >
                      Down
                    </button>
                    <button onClick={() => void handleSaveOverrides(member)} disabled={busyId === member.agent_id}>Save Overrides</button>
                    <button className="danger" onClick={() => void handleRemove(member)} disabled={busyId === member.agent_id}>Remove</button>
                  </div>
                </td>
              </tr>
            ))}
            {(conversation?.agents.length || 0) === 0 && !loading && (
              <tr>
                <td colSpan={4}>
                  <span className="muted">아직 thread 팀에 추가된 agent가 없습니다.</span>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
