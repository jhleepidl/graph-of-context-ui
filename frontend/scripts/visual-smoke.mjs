import { spawn } from 'node:child_process'
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises'
import path from 'node:path'
import os from 'node:os'
import process from 'node:process'
import { chromium } from 'playwright'

const root = path.resolve(new URL('..', import.meta.url).pathname)
const outputDir = path.join(root, 'test-results', 'visual')
await mkdir(outputDir, { recursive: true })

const port = Number(process.env.GOC_VISUAL_PORT || 4175)
const base = `http://127.0.0.1:${port}`
const server = spawn(process.execPath, ['./node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', String(port)], {
  cwd: root,
  stdio: ['ignore', 'pipe', 'pipe'],
})
let serverLog = ''
server.stdout.on('data', (chunk) => { serverLog += String(chunk) })
server.stderr.on('data', (chunk) => { serverLog += String(chunk) })

async function waitForServer() {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    try {
      const response = await fetch(`${base}/visual.html`)
      if (response.ok) return
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 150))
  }
  throw new Error(`Vite did not start.\n${serverLog}`)
}

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

let browserContext = null
let browserProfileDir = ''
let chatSent = false
const commandPolls = new Map()
let sawEventCursor = false
let sawClientCommandId = false

try {
  await waitForServer()
  browserProfileDir = await mkdtemp(path.join(os.tmpdir(), 'goc-visual-'))
  browserContext = await chromium.launchPersistentContext(browserProfileDir, {
    executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium',
    args: ['--no-sandbox'],
    viewport: { width: 1600, height: 1100 },
    deviceScaleFactor: 1,
  })
  const context = browserContext
  const browserErrors = []
  await context.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/api/threads' && route.request().method() === 'GET') {
      return json(route, [
        { id: 'thread_demo', title: 'AI Rooms product research', external_ref: 'telegram:-1001234567890', meta_json: { telegram: { chat_id: -1001234567890, title: 'Product research' } } },
        { id: 'thread_install', title: 'Installation guide', external_ref: 'telegram:-1001234567890', meta_json: { telegram: { chat_id: -1001234567890, title: 'Product research' } } },
        { id: 'thread_recommend', title: 'Personal inventory recommendations', external_ref: 'telegram:-1001234567890', meta_json: { telegram: { chat_id: -1001234567890, title: 'Product research' } } },
      ])
    }
    if (url.pathname === '/api/threads/thread_demo/context_sets') return json(route, [{ id: 'context_demo', thread_id: 'thread_demo', name: 'governed project context' }])
    if (url.pathname === '/api/threads/thread_demo/graph') return json(route, { nodes: [], edges: [] })
    if (url.pathname === '/api/context_sets/context_demo') return json(route, { id: 'context_demo', thread_id: 'thread_demo', name: 'governed project context', active_node_ids: [] })
    if (url.pathname === '/api/context_sets/context_demo/compiled') return json(route, { compiled_text: '', explain: {} })
    if (url.pathname === '/api/context_sets/context_demo/versions') return json(route, { versions: [] })
    if (url.pathname === '/api/threads/thread_demo/run_studio/summary') {
      return json(route, {
        thread: { id: 'thread_demo', title: 'AI Rooms product research', external_ref: 'telegram:-1001234567890' },
        context_set: { id: 'context_demo', name: 'governed project context' },
        now: { state: { current_run_id: 'run_continuity_42', current_run_status: 'active', goal: 'Validate that Room goals, source boundaries, corrections, and next actions survive model changes.' } },
        projections: { execution: { current_step: { run_id: 'run_continuity_42', status: 'active', goal: 'Compare baseline and AI Rooms continuation behavior.' } }, memory_context: { selected_count: 7, pinned_count: 3, conflict_count: 1 } },
        context_decisions_counts: { selected: 7, pinned: 3, conflicting: 1, missing: 2 },
        watch_tasks_summary: { active_count: 1, next_action: 'Run the model-swap continuation scenario and record whether the correction remains active.' },
        review_inbox_summary: { pending_count: 3, high_risk_count: 1 },
        semantic_board_summary: { rule_count: 5, correction_count: 2 },
        correction_count: 2,
        context_runtime_summary: { mode: 'project-only' },
        model_catalog_summary: { node_count: 6 },
        agent_room_summary: { current_goal: 'Validate durable Room continuity.', default_workflow: 'single-model-first', default_agents: ['executor'] },
        runtime_policy_summary: { latest: { context_mode: 'project-only' } },
        runtime_authority: { owner: 'ddalggak' },
      })
    }
    if (url.pathname.endsWith('/watch-tasks')) {
      return json(route, { active_task: { id: 'watch_1', status: 'active', workflow_kind: 'continuity_test', current_iteration: 2, max_iterations: 5, goal: 'Validate continuity after switching models.', required_passes: ['plan', 'correct', 'continue'], stop_conditions: ['continuation verified'], iterations: [] }, tasks: [] })
    }
    if (url.pathname.includes('/review/inbox')) {
      return json(route, { summary: { proposal_count: 3, pending_review_count: 3, high_risk_count: 1 }, persisted_summary: { proposal_count: 3 }, detected_summary: { proposal_count: 0 }, proposals: [{ proposal_id: 'proposal_1', title: 'Promote correction to Room rule', summary: 'Keep the backend schema unchanged for the current UI iteration.', risk: 'high', status: 'pending', recommended_action: 'approve', evidence_status: 'supported' }], policy: { principle: 'Evidence before promotion', safe_defaults: ['review high-risk changes'] } })
    }
    if (url.pathname === '/api/runtime/events') {
      const cursor = url.searchParams.get('after_event_id') || ''
      if (cursor) sawEventCursor = true
      const initial = [
        { event_id: 'evt_2', event_type: 'run.finish', run_id: 'run_chat_1', occurred_at: '2026-07-12T10:01:00Z', payload: { summary: '첫 번째 단계를 완료했고 다음 단계는 검토 대기 상태입니다.' } },
        { event_id: 'evt_1', event_type: 'run.start', run_id: 'run_chat_1', occurred_at: '2026-07-12T10:00:00Z', payload: { userText: '이전 계획을 이어서 첫 번째 단계만 진행해줘.' } },
      ]
      const delta = chatSent ? [
        { event_id: 'evt_3', event_type: 'run.start', run_id: 'run_chat_2', occurred_at: '2099-01-01T00:00:00Z', payload: { userText: '다음 단계에서 기존 규칙을 유지해줘.' } },
        { event_id: 'evt_4', event_type: 'run.finish', run_id: 'run_chat_2', occurred_at: '2099-01-01T00:00:01Z', payload: { summary: '기존 규칙을 유지한 채 다음 단계를 시작했습니다.' } },
      ] : []
      if (!cursor) return json(route, { items: initial, next_cursor: 'evt_2' })
      if (cursor === 'evt_2') return json(route, { items: delta, next_cursor: delta.length ? 'evt_4' : 'evt_2' })
      return json(route, { items: [], next_cursor: cursor })
    }
    if (url.pathname === '/api/runtime/commands' && route.request().method() === 'POST') {
      const body = JSON.parse(route.request().postData() || '{}')
      const isMessage = body.command_type === 'room_message'
      if (!body.command_id || !String(body.command_id).startsWith('cmd_goc_')) throw new Error('client command_id is required')
      sawClientCommandId = true
      if (isMessage) chatSent = true
      commandPolls.set(body.command_id, { type: body.command_type, count: 0 })
      return json(route, { command: { command_id: body.command_id, status: 'queued', command_type: body.command_type } }, 201)
    }
    if (url.pathname.startsWith('/api/runtime/commands/')) {
      const commandId = decodeURIComponent(url.pathname.split('/').pop() || '')
      const state = commandPolls.get(commandId) || { type: 'room_command', count: 0 }
      state.count += 1
      commandPolls.set(commandId, state)
      const status = state.type === 'room_message' && state.count === 1 ? 'accepted' : 'applied'
      return json(route, { command_id: commandId, status, command_type: state.type, result: { delivery: state.type === 'room_message' ? 'telegram_and_goc' : 'telegram' } })
    }
    return json(route, {})
  })

  const page = context.pages()[0] || await context.newPage()
  page.on('pageerror', (error) => browserErrors.push(String(error)))
  page.on('console', (message) => { if (message.type() === 'error') browserErrors.push(message.text()) })

  await page.goto(`${base}/?token=visual&thread=thread_demo&ctx=context_demo`, { waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: 'AI Rooms product research' }).waitFor()
  await page.locator('.roomSidebar').waitFor()
  await page.getByText('사용할 정보', { exact: true }).waitFor()
  await page.screenshot({ path: path.join(outputDir, 'room-workspace-app.png'), fullPage: true })
  await page.getByRole('button', { name: '작업방 수정' }).click()
  await page.getByRole('heading', { name: '작업방 수정' }).waitFor()
  await page.keyboard.press('Escape')
  await page.getByRole('heading', { name: '작업방 수정' }).waitFor({ state: 'hidden' })

  await page.goto(`${base}/visual.html`, { waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: 'AI Rooms product research' }).waitFor()
  const chatFold = page.getByRole('button', { name: /작업방 채팅/ })
  const workFold = page.getByRole('button', { name: /진행 중인 작업/ })
  const reviewFold = page.getByRole('button', { name: /확인할 항목/ })
  await chatFold.waitFor()
  if (await chatFold.getAttribute('aria-expanded') !== 'false') throw new Error('Room chat must start folded')
  if (await workFold.getAttribute('aria-expanded') !== 'false') throw new Error('Active work must start folded')
  if (await reviewFold.getAttribute('aria-expanded') !== 'false') throw new Error('Review must start folded')
  await page.screenshot({ path: path.join(outputDir, 'room-workspace-overview.png'), fullPage: true })

  await workFold.click()
  if (await workFold.getAttribute('aria-expanded') !== 'true') throw new Error('Active work did not expand')
  await page.reload({ waitUntil: 'networkidle' })
  const persistedWorkFold = page.getByRole('button', { name: /진행 중인 작업/ })
  if (await persistedWorkFold.getAttribute('aria-expanded') !== 'true') throw new Error('Fold state did not persist')
  await persistedWorkFold.click()

  await page.getByRole('button', { name: /작업방 채팅/ }).click()
  await page.getByText('첫 번째 단계를 완료했고 다음 단계는 검토 대기 상태입니다.', { exact: true }).waitFor()
  const composer = page.getByRole('textbox', { name: '메시지' })
  await composer.fill('/stop')
  await page.getByRole('button', { name: '메시지 보내기' }).click()
  await page.getByText(/명령어는 .*작업방 수정/).waitFor()
  await composer.fill('다음 단계에서 기존 규칙을 유지해줘.')
  await page.screenshot({ path: path.join(outputDir, 'room-workspace-chat-expanded.png'), fullPage: true })
  await page.getByRole('button', { name: '메시지 보내기' }).click()
  await page.getByText('전달됨', { exact: true }).waitFor()
  await page.getByText('기존 규칙을 유지한 채 다음 단계를 시작했습니다.', { exact: true }).waitFor()

  await page.getByRole('button', { name: /참고 자료/ }).click()
  await page.getByRole('heading', { name: '무엇을 믿고 답하는지 확인' }).waitFor()
  await page.screenshot({ path: path.join(outputDir, 'room-workspace-sources.png'), fullPage: true })

  await page.getByRole('button', { name: '작업방 수정' }).click()
  await page.getByRole('heading', { name: '작업방 수정' }).waitFor()
  await page.getByRole('button', { name: /잘못 이해한 점 수정/ }).click()
  await page.getByRole('textbox', { name: '변경 내용' }).fill('Keep the backend schema unchanged during this UI iteration.')
  await page.screenshot({ path: path.join(outputDir, 'room-workspace-edit-drawer.png'), fullPage: true })
  await page.getByRole('button', { name: '작업방에 적용' }).click()
  await page.getByText('applied', { exact: true }).waitFor()

  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${base}/visual.html`, { waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: 'AI Rooms product research' }).waitFor()
  await page.screenshot({ path: path.join(outputDir, 'room-workspace-mobile.png'), fullPage: true })

  if (!sawClientCommandId) throw new Error('GoC runtime commands did not include a client-generated command_id')
  if (!sawEventCursor) throw new Error('Room chat did not use incremental runtime event cursors')
  if (browserErrors.length) throw new Error(`Browser errors:\n${browserErrors.join('\n')}`)
  await writeFile(path.join(outputDir, 'RESULT.txt'), 'PASS\nFolded overview, persisted disclosure state, plain-language labels, shared-runtime Room chat, idempotent client command IDs, accepted-state polling, cursor-based projected reply, slash-command rejection, Sources, Room edit drawer, direct apply, keyboard close, and mobile rendering passed.\n')
  console.log(`Visual smoke passed. Screenshots: ${outputDir}`)
} finally {
  await browserContext?.close().catch(() => {})
  if (browserProfileDir) await rm(browserProfileDir, { recursive: true, force: true }).catch(() => {})
  server.kill('SIGTERM')
}
