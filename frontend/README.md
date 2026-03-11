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

## UI Notes
- Skill visibility and context pack visibility are preserved.
- Graph/Execution/Advanced surfaces are unchanged.
- Deep-link behavior for `?thread=<id>` stays deterministic (no silent fallback).

For operator interpretation, see [`../UI_USAGE_GUIDE.md`](../UI_USAGE_GUIDE.md) and [`../SKILLS_IN_UI_GUIDE.md`](../SKILLS_IN_UI_GUIDE.md).

