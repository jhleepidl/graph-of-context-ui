# Frontend Notes

## Run
```bash
cd frontend
npm install
npm run dev
```

`/api` is proxied to `VITE_BACKEND_PROXY_TARGET` by default.
You can override with `VITE_API_BASE`.

## Workspace Architecture
- `WorkspaceApp.tsx` remains the page shell, but orchestration is split into hooks/components.
- `useWorkspaceThreadSelection.ts`: deep-link resolution, thread/workspace grouping, explicit-thread behavior.
- `useRunStudioData.ts`: summary-first Run Studio fetch + lazy detail loaders.
- `useRunStudioActions.ts`: graph focus/open/pin/add-to-active action wiring from Run Studio cards.
- `WorkspaceRouteState.tsx`: Run Studio/Graph/Raw Trace/Artifacts/Advanced tab controls.

## Run Studio Loading Strategy
- Initial load: `GET /run_studio/summary`.
- Detail panels load on demand:
  - `agent_team`
  - `context_decisions`
  - `evidence`
  - `context_packs`
  - `skill_usage`
- When detail is already loaded, refresh keeps it updated without restoring eager multi-endpoint startup.
- Summary data is sufficient to render core Run Studio cards before detail fetches complete.
- TeamPlan v2 support does not require API path changes.

## Authority/Fallback UI
- Run Studio surfaces canonical runtime authority metadata from backend projections:
  - `mode`, `plan_source`, `context_source`, `agent_catalog_source`, `conversation_team_source`, `skill_catalog_source`
  - `degraded_mode`, `fallback_reason`
- `Now`, `Team View`, `Orchestration`, `Authority`, `Context Packs`, and `Skill Usage` show fallback/degraded state when runtime falls back from GoC-backed authority.
- Planning is shown through a lightweight boundary projection that centers on runtime/control stages rather than a planner worker concept.

## Runtime/Control Model In UI
- `ddalggak` is the execution runtime.
- GoC is the graph-first projection and control layer.
- Human-authored presets are text-first, but the runtime/control model is structured.
- `RuntimeAgent = Role + Attached Skills + Context Pack`.
- Team composition is capability-slot fulfillment.
- `SupervisorRuntime` is shown as a control actor, not a worker role.
- Collaboration cells surface reflection/debate/committee behavior.
- The UI prefers newer `team_view` / `why_this_team` / `orchestration` / `collaboration` / `authority` / `checkpoints` payloads first and falls back gracefully to legacy `agent_team` and older runtime summaries.

## UI Notes
- Skill visibility and context pack visibility are preserved.
- `Team View`, `Why this team?`, `Orchestration`, `Collaboration`, `Authority`, and `Checkpoints` are projection-oriented views over runtime state.
- `Dominant Skills` remains observability-oriented: it does not imply full backend authority over runtime skill package content.
- Graph/Execution/Advanced surfaces are unchanged.
- Deep-link behavior for `?thread=<id>` stays deterministic (no silent fallback).
- No-skill or no-TeamPlan runs degrade gracefully: team/control panels show empty states or legacy fallbacks instead of failing.

For operator interpretation, see [`../UI_USAGE_GUIDE.md`](../UI_USAGE_GUIDE.md) and [`../SKILLS_IN_UI_GUIDE.md`](../SKILLS_IN_UI_GUIDE.md).
