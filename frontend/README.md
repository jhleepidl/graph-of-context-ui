# Graph-of-Context MVP (Frontend)

## Run
```bash
npm install
npm run dev
```

By default dev requests to `/api` are proxied to `VITE_BACKEND_PROXY_TARGET` (default: `http://127.0.0.1:8703`).
You can also set `VITE_API_BASE` to call a full backend URL directly.

## Auth Token + Deep Link
- URL hash에 `#token=<bearer>`를 붙이면 앱 시작 시 토큰을 읽어 `sessionStorage(goc:ui_token:v1)`에 저장하고, 이후 모든 API 요청에 자동 첨부됩니다.
- UI Bearer 토큰은 해당 `service_id` 범위 내에서 **read + write**(노드 편집/activate/split/fold 등) 권한을 가집니다.
- UI Bearer 토큰은 짧은 TTL을 권장합니다. 만료되면 ServiceKey로 `/api/service/mint_ui_token`을 호출해 재발급하세요.
- URL query의 `?thread=<threadId>&ctx=<ctxId>`가 있으면 초기 로딩에서 해당 thread/context set을 우선 선택합니다.

Example:
```text
https://<host>/goc/?thread=<threadId>&ctx=<ctxId>#token=gocu1.<service_id>.<exp>.<sig>
```

## Admin / Guest UI routes
- `/guest/request-service`: 인증 없이 서비스 키 발급 신청 생성
- `/admin/login`: Admin Key를 `sessionStorage(goc:admin_key:v1)`에 저장/삭제
- `/admin/service-requests`: Admin 요청 목록 조회/approve + 1회 api_key 표시/복사, service rotate/revoke

## Header priority (auto)
1. `X-Admin-Key` (sessionStorage에 admin key가 있으면 최우선)
2. `Authorization: Bearer <ui_token>`
3. `Authorization: ServiceKey ...` (프론트 기본 동선에서는 자동 사용하지 않음)

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
