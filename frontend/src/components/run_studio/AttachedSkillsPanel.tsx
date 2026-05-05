import React, { useMemo, useState } from 'react'
import { type AgentSkillAttachmentProjection, type RunStudioAgentTeam, type RunStudioSummary } from './types'
import { selectEffectiveAgentTeam, selectSkillAttachmentOverview } from './selectors'
import { humanizeSkill } from './teamPresentation'

type Props = {
  summary: RunStudioSummary | null
  team: RunStudioAgentTeam | null
}

type AgentSkillRow = {
  id: string
  name: string
  level: string
  selectedBy: string | null
  status?: string | null
  reason?: string | null
}

type AgentWithSkillRows = {
  agent: AgentSkillAttachmentProjection
  rows: AgentSkillRow[]
}

type SkillMatrixRow = {
  id: string
  name: string
  count: number
  agents: Array<{
    runtimeId?: string | null
    label: string
    role: string
    slot?: string | null
    level: string
    selectedBy: string | null
  }>
}

function cleanText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : String(value || '').trim()
}

function normalizeSkillLevel(value: unknown): string {
  return cleanText(value) || 'metadata_only'
}


function isAgentSkillRow(row: AgentSkillRow | null): row is AgentSkillRow {
  return row !== null
}

function isNonEmptyText(value: string): value is string {
  return value.length > 0
}

function skillLevelClass(level: string): string {
  const clean = level.toLowerCase()
  if (clean.includes('full') || clean.includes('runtime') || clean.includes('loaded')) return 'runStudioSkillLevel--full'
  if (clean.includes('selected') || clean.includes('attached')) return 'runStudioSkillLevel--selected'
  if (clean.includes('blocked') || clean.includes('missing')) return 'runStudioSkillLevel--blocked'
  return 'runStudioSkillLevel--metadata'
}

function buildSkillRows(agent: AgentSkillAttachmentProjection): AgentSkillRow[] {
  const explicitRows: AgentSkillRow[] = []
  ;(agent.attached_skills || []).forEach((skill) => {
    const id = cleanText(skill.skill_id)
    if (!id) return
    explicitRows.push({
      id,
      name: humanizeSkill(skill.skill_name || id),
      level: normalizeSkillLevel(skill.load_level),
      selectedBy: cleanText(skill.selected_by) || null,
      status: cleanText(skill.status) || null,
      reason: cleanText(skill.selection_reason) || null,
    })
  })

  if (explicitRows.length > 0) return explicitRows

  const fallbackRows: AgentSkillRow[] = []
  ;(agent.attached_skill_ids || []).forEach((skillIdRaw) => {
    const id = cleanText(skillIdRaw)
    if (!id) return
    fallbackRows.push({
      id,
      name: humanizeSkill(id),
      level: 'metadata_only',
      selectedBy: null,
    })
  })
  return fallbackRows
}


function buildAgentRows(agents: AgentSkillAttachmentProjection[]): AgentWithSkillRows[] {
  return agents.map((agent) => ({ agent, rows: buildSkillRows(agent) }))
}

function buildSkillMatrix(agentRows: AgentWithSkillRows[], topSkillIds: string[]): SkillMatrixRow[] {
  const rowsBySkill = new Map<string, SkillMatrixRow>()

  agentRows.forEach(({ agent, rows }) => {
    rows.forEach((skill) => {
      const current = rowsBySkill.get(skill.id) || {
        id: skill.id,
        name: skill.name,
        count: 0,
        agents: [],
      }
      current.count += 1
      current.name = skill.name || current.name || skill.id
      current.agents.push({
        runtimeId: agent.runtime_instance_id,
        label: agent.display_label,
        role: agent.role_label,
        slot: agent.slot_label,
        level: skill.level,
        selectedBy: skill.selectedBy,
      })
      rowsBySkill.set(skill.id, current)
    })
  })

  const rank = new Map(topSkillIds.map((skillId, index) => [skillId, index]))
  return Array.from(rowsBySkill.values()).sort((a, b) => {
    const rankA = rank.has(a.id) ? rank.get(a.id)! : 9999
    const rankB = rank.has(b.id) ? rank.get(b.id)! : 9999
    if (rankA !== rankB) return rankA - rankB
    if (b.count !== a.count) return b.count - a.count
    return a.name.localeCompare(b.name)
  })
}

export default function AttachedSkillsPanel({ summary, team }: Props) {
  const effectiveTeam = selectEffectiveAgentTeam(summary, team)
  const overview = selectSkillAttachmentOverview(summary, effectiveTeam)
  const agents = overview.agents
  const topSkills = overview.top_skills.slice(0, 10)
  const [showAgentCards, setShowAgentCards] = useState(false)
  const agentRows = useMemo(() => buildAgentRows(agents), [agents])
  const skillMatrix = useMemo(
    () => buildSkillMatrix(agentRows, overview.top_skills.map((skill) => skill.skill_id)),
    [agentRows, overview.top_skills],
  )
  const agentsWithoutSkills = agentRows.filter((entry) => entry.rows.length === 0)

  return (
    <section className="card runStudioPanel runStudioSkillAttachmentPanel">
      <div className="runStudioPanelHeader">
        <div>
          <h3 style={{ margin: 0 }}>Skill Map</h3>
          <div className="muted">어떤 skill이 어떤 agent에 붙어 있는지 먼저 보여주고, 필요하면 agent별 상세를 펼칩니다.</div>
        </div>
        <div className="runStudioMetaRow">
          <span className="pill">agents: {agents.length}</span>
          <span className="pill">agents with skills: {overview.agents_with_skills}</span>
          <span className="pill">unique skills: {overview.total_unique_skills}</span>
          <span className="pill">agent-skill links: {overview.total_agent_skill_links}</span>
        </div>
      </div>

      <div className="runStudioSkillMapHero">
        <div>
          <div className="runStudioSkillMapHeroTitle">Agent ↔ Skill at a glance</div>
          <div className="muted">
            위쪽 matrix는 skill 중심으로 읽습니다. 오른쪽 badge는 담당 agent와 load level을 같이 보여줍니다.
          </div>
        </div>
        <button type="button" onClick={() => setShowAgentCards((value) => !value)}>
          {showAgentCards ? 'Hide agent cards' : 'Show agent cards'}
        </button>
      </div>

      {topSkills.length > 0 && (
        <div className="runStudioSkillAttachmentSummary">
          <div className="muted" style={{ marginBottom: 6 }}>Top attached skills across the team</div>
          <div className="runStudioMetaRow">
            {topSkills.map((skill) => (
              <span key={skill.skill_id} className="pill runStudioSkillPill runStudioSkillPill--prominent">
                {humanizeSkill(skill.skill_name)} · {skill.count}
              </span>
            ))}
          </div>
        </div>
      )}

      {skillMatrix.length > 0 ? (
        <div className="runStudioSkillMatrixWrap">
          <table className="runStudioSkillMatrixTable">
            <thead>
              <tr>
                <th>Skill</th>
                <th>Attached agents</th>
                <th>Links</th>
              </tr>
            </thead>
            <tbody>
              {skillMatrix.map((skill) => (
                <tr key={skill.id}>
                  <td>
                    <div className="runStudioSkillMatrixName">{skill.name}</div>
                    {skill.id !== skill.name && <div className="muted runStudioSkillMatrixId">{skill.id}</div>}
                  </td>
                  <td>
                    <div className="runStudioAgentSkillBadgeList">
                      {skill.agents.map((agent, agentIndex) => (
                        <span
                          key={`${skill.id}:${agent.runtimeId || agent.label}:${agent.level}:${agentIndex}`}
                          className="runStudioAgentSkillBadge"
                          title={[agent.slot ? `slot: ${agent.slot}` : '', agent.selectedBy ? `selected by: ${agent.selectedBy}` : ''].filter(isNonEmptyText).join(' · ')}
                        >
                          <b>{agent.label}</b>
                          <span>{agent.role}</span>
                          <em className={skillLevelClass(agent.level)}>{agent.level}</em>
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="runStudioSkillMatrixCount">{skill.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="runStudioEmptyNotice">
          No attached skill projection was emitted yet. Run data may be using a legacy team view or the current route may not have selected skills.
        </div>
      )}

      {agentsWithoutSkills.length > 0 && (
        <div className="runStudioSkillCoverageNotice">
          <b>Agents without visible skills:</b>{' '}
          {agentsWithoutSkills.map(({ agent }) => agent.display_label).join(', ')}
        </div>
      )}

      {showAgentCards && (
        <div className="runStudioSkillAttachmentGrid">
          {agentRows.map(({ agent, rows }) => (
            <article key={agent.runtime_instance_id || agent.display_label} className="runStudioSkillAttachmentCard">
              <div className="row" style={{ marginBottom: 6 }}>
                <b>{agent.display_label}</b>
                <span className="pill">{agent.role_label}</span>
                {agent.preset_id && <span className="pill">preset</span>}
                {!agent.preset_id && agent.synthesized && <span className="pill">synthesized</span>}
              </div>
              <div className="muted">slot: {agent.slot_label || '-'}</div>
              {agent.authority_profile_id && <div className="muted">authority: {agent.authority_profile_id}</div>}
              <div className="runStudioSkillStack" style={{ marginTop: 8 }}>
                {rows.length > 0 ? rows.map((skill) => (
                  <div key={`${agent.runtime_instance_id || agent.display_label}:${skill.id}`} className="runStudioSkillRow">
                    <div>
                      <span className="runStudioSkillName">{skill.name}</span>
                      {skill.reason && <div className="muted">{skill.reason}</div>}
                    </div>
                    <div className="runStudioMetaRow" style={{ justifyContent: 'flex-end' }}>
                      <span className={`pill ${skillLevelClass(skill.level)}`}>{skill.level}</span>
                      {skill.status && <span className="pill">{skill.status}</span>}
                      {skill.selectedBy && <span className="pill">by: {skill.selectedBy}</span>}
                    </div>
                  </div>
                )) : <div className="muted">No attached skills emitted for this agent.</div>}
              </div>
            </article>
          ))}
        </div>
      )}

      {agents.length === 0 && (
        <div className="muted">No runtime agents are visible yet for this run scope.</div>
      )}
    </section>
  )
}
