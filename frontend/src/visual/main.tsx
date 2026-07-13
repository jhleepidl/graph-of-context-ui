import React from 'react'
import { createRoot } from 'react-dom/client'
import RunStudioLayout from '../components/run_studio/RunStudioLayout'
import '../styles.css'

const summary: any = {
  thread: {
    id: 'thread_demo',
    title: 'AI Rooms product research',
    external_ref: 'telegram:-1001234567890',
  },
  context_set: { id: 'context_demo', name: 'governed project context' },
  now: {
    state: {
      current_run_id: 'run_continuity_42',
      current_run_status: 'active',
      goal: 'Validate that Room goals, source boundaries, corrections, and next actions survive model changes.',
    },
  },
  projections: {
    execution: {
      current_step: {
        run_id: 'run_continuity_42',
        status: 'active',
        goal: 'Compare baseline and AI Rooms continuation behavior.',
      },
    },
    memory_context: {
      selected_count: 7,
      pinned_count: 3,
      conflict_count: 1,
    },
  },
  context_decisions_counts: { selected: 7, pinned: 3, conflicting: 1, missing: 2 },
  watch_tasks_summary: {
    active_count: 1,
    next_action: 'Run the model-swap continuation scenario and record whether the correction remains active.',
  },
  review_inbox_summary: { pending_count: 3, high_risk_count: 1 },
  semantic_board_summary: { rule_count: 5, correction_count: 2 },
  correction_count: 2,
  context_runtime_summary: { mode: 'project-only' },
  model_catalog_summary: { node_count: 6 },
  agent_room_summary: {
    current_goal: 'Validate durable Room continuity.',
    default_workflow: 'single-model-first',
    default_agents: ['executor'],
  },
  runtime_policy_summary: { latest: { context_mode: 'project-only' } },
  runtime_authority: { owner: 'ddalggak' },
}

const decisions: any = {
  selected: [
    { id: 'source_docs', target_node_id: 'source_docs', type: 'Document', text: 'Current product positioning docs', reason: 'canonical project source' },
    { id: 'correction_1', target_node_id: 'correction_1', type: 'Correction', text: 'Do not change backend schema in this iteration.', reason: 'accepted user correction' },
  ],
  pinned: [{ id: 'rule_1', target_node_id: 'rule_1', type: 'Rule', text: 'Uploaded files override stale assumptions.' }],
  missing: [{ key: 'current model signature', reason: 'required for continuation comparison' }],
  conflicting: [{ node_ids: ['source_old', 'source_docs'], reason: 'old positioning conflicts with the current canonical doc' }],
}

const evidence: any = {
  items: [
    { claim_node_id: 'source_docs', claim_node_type: 'Document', claim_text: 'Product positioning', provenance: ['docs/PRODUCT_POSITIONING_ROOM_CONTINUITY.md'], selected_in_context: true },
    { claim_node_id: 'eval_42', claim_node_type: 'Evaluation', claim_text: 'Continuity evaluation run', provenance: ['runs/continuity/run_continuity_42'], selected_in_context: true },
  ],
}

function noop() {}

function Fixture() {
  return (
    <div className="visualFixtureShell">
      <header className="topNav topNav--workspace">
        <div className="topNavBrand"><span className="topNavBrandMark">G</span><span><b>GoC</b><small>작업방 관리</small></span></div>
        <nav className="topNavPrimary"><button className="isActive">작업방</button><button>자료함</button><button>Agent</button><button>도구</button></nav>
        <div className="topNavRight"><button>서비스 이용</button><button>관리자</button></div>
      </header>
      <div className="visualFixtureWorkspace">
        <aside className="roomSidebar">
          <header className="roomSidebarHeader"><div><div className="runStudioEyebrow">작업방</div><h2>내 작업 공간</h2></div><button className="primary roomSidebarNewButton">+ 새 작업방</button></header>
          <label className="roomSidebarWorkspacePicker"><span>작업 공간</span><select defaultValue="product"><option value="product">Product research (3)</option></select></label>
          <div className="roomSidebarList">
            <button className="roomSidebarItem isActive"><span className="roomSidebarItemMark" /><span className="roomSidebarItemText"><b>AI Rooms product research</b><small>thread_d</small></span></button>
            <button className="roomSidebarItem"><span className="roomSidebarItemMark" /><span className="roomSidebarItemText"><b>Installation guide</b><small>thread_i</small></span></button>
            <button className="roomSidebarItem"><span className="roomSidebarItemMark" /><span className="roomSidebarItemText"><b>Personal inventory recommendations</b><small>thread_r</small></span></button>
          </div>
          <div className="roomSidebarSelectedTools"><div className="roomSidebarSelectedHeading"><span>선택한 작업방</span><button className="dangerText">삭제</button></div><label><span>정보 묶음</span><select defaultValue="main"><option value="main">governed project context</option></select></label><div className="roomSidebarToolRow"><button>새 정보 묶음</button><button>다시 불러오기</button></div><button>Agent 고급 설정</button></div>
          <details className="roomSidebarDetails"><summary>작업방 기억 검색</summary></details>
          <details className="roomSidebarDetails"><summary>변경 기록 찾아보기</summary></details>
        </aside>
        <main className="visualFixtureMain">
          <RunStudioLayout
            threadId="thread_demo"
            summary={summary}
            team={null}
            decisions={decisions}
            evidence={evidence}
            contextPacks={null}
            skillUsage={null}
            memoryGraph={null}
            memoryTopology={null}
            memoryDemand={null}
            traceScope={null}
            crossReferences={null}
            auditTimeline={{ items: [] } as any}
            projectionRetrieval={null}
            graphCompression={null}
            harnessSpec={null}
            harnessSummary={null}
            teamSelection={null}
            detailLoaded={{ contextDecisions: true, evidence: true }}
            detailLoading={{}}
            loading={false}
            error=""
            onRefresh={noop}
            onLoadAgentTeam={noop}
            onLoadContextDecisions={noop}
            onLoadEvidence={noop}
            onLoadContextPacks={noop}
            onLoadSkillUsage={noop}
            onLoadMemoryGraph={noop}
            onLoadMemoryTopology={noop}
            onLoadMemoryDemand={noop}
            onLoadTraceScope={noop}
            onLoadTeamSelection={noop}
            onOpenGraph={noop}
            onOpenRawTrace={noop}
            onOpenAdvanced={noop}
            onFocusNode={noop}
            onOpenNode={noop}
            onFocusTrace={noop}
            onOpenTrace={noop}
            onAddToActive={noop}
            onPinNode={noop}
          />
        </main>
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(<Fixture />)
