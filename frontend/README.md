# Graph-of-Context MVP (Frontend)

## Run
```bash
npm install
npm run dev
```

By default dev requests to `/api` are proxied to `VITE_BACKEND_PROXY_TARGET` (default: `http://127.0.0.1:8703`).
You can also set `VITE_API_BASE` to call a full backend URL directly.

## Notes
- Graph visualization uses React Flow.
- Timeline + Active Context panels drive control.
- Copy to ChatGPT panel auto-embeds TAGGED FORMAT rules (English) plus a Korean-only response instruction (`답변은 한국어`) before Active Context and User Request.
- Paste from ChatGPT can parse `[FINAL]/[DECISIONS]/[ASSUMPTIONS]/[PLAN]/[CONTEXT_CANDIDATES]` and create active context nodes.
- You can create and activate a context node directly without running the agent.
- You can add the current `USER REQUEST` input directly as a context node (no model echo required).
- Graph nodes are fixed in the viewer (drag-move disabled) to focus on edge/fold operations.
- Edges are rendered in a chronological/type-aware order for cleaner flow.
- You can add edges by dragging between node handles (select edge type first), and delete selected edges with Delete/Backspace.
- In graph view, drag-select nodes for Fold and use handle connections for edge operations.
- Fold members are hidden by default; use `Fold 상세 보기` (or zoom in) to inspect unfolded member nodes.
- In folded view, external connections of folded members are preserved via fold-level virtual edges.
- Active Context cards can be drag-reordered, and you can drop cards into the remove zone to deactivate.
- Timeline cards are draggable into Active Context for quick composition.
