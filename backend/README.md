# Graph-of-Context Run Studio (Backend) - Postgres + FAISS (no pgvector extension)

This backend stores the conversation graph in Postgres, performs vector search using an in-process FAISS index,
and now exposes additive Run Studio projection APIs over the same generic graph model.
This avoids needing the `pgvector` Postgres extension (useful on older PG versions / restricted environments).

## 0) Configure Postgres connection
Set `GOC_DB_URL` in `.env`:
```
postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME
```

(For local dev only, an optional `docker-compose.yml` is provided at repo root.)

## 1) Run backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# 필수: GOC_ADMIN_KEY, GOC_UI_TOKEN_SECRET
# 선택: OPENAI_API_KEY (실제 embeddings/LLM 사용 시)
uvicorn app.main:app --reload --port 8000
```

## Auth model (service = user 1명)
- `X-Admin-Key: <GOC_ADMIN_KEY>`: admin 전권
- `Authorization: ServiceKey <raw>`: service 범위 권한
- `Authorization: Bearer <ui_token>`: service 범위 권한(UI용, write 포함)

### Admin service APIs
- `GET /api/admin/service_requests?status=pending|approved|rejected`
- `POST /api/admin/service_requests/{id}/approve`
- `GET /api/admin/services`
- `POST /api/admin/services/{service_id}/rotate`
- `POST /api/admin/services/{service_id}/revoke`

### Service onboarding / key flow
1. `POST /api/service_requests` (무인증, IP별 rate-limit)
2. `POST /api/admin/service_requests/{id}/approve` (admin): service 생성 + ServiceKey 1회 반환
3. ServiceKey로 `POST /api/service/mint_ui_token` 호출하여 UI Bearer 발급

### UI token note
- UI Bearer는 read-only가 아니라 write 권한을 포함합니다.
- TTL을 짧게 운영하고 만료 시 ServiceKey로 재발급하는 흐름을 권장합니다.

### Admin security recommendations
- admin 라우트를 내부망/IP allowlist로 제한
- reverse proxy에서 basic auth/mTLS 추가
- 백엔드는 로컬 바인딩 또는 사설 네트워크로 노출 최소화

### CORS
- 개발 기본값은 `GOC_CORS_ALLOW_ORIGINS=*`
- 운영에서는 `GOC_CORS_ALLOW_ORIGINS=https://your-admin-ui.example.com,https://your-goc-ui.example.com` 처럼 명시적으로 제한하세요.

## Vector search notes
- Backend stores **normalized** embeddings in Postgres table `node_embeddings` (JSON text).
- It also maintains a FAISS index **per thread** in `GOC_FAISS_DIR` (default: `./data/faiss`).
- Search endpoint: `/api/threads/{thread_id}/search?q=...`

## Compiled context freshness
- `compiled_text`는 캐시 없이 매 요청마다 DB의 current active nodes/edges로 동적 생성합니다.
- 따라서 node text 수정, node/edge 삭제/추가, activate 변경 직후 다음 `/api/context_sets/{id}/compiled` 호출에 즉시 반영됩니다.
- `include_explain=true`일 때 `explain`에는 아래 진단 필드가 포함됩니다.
  - `active_input_ids`, `excluded_parent_ids`, `kept_node_ids`
  - `node_snippets`: `node_id -> snippet` 매핑
  - `section_map`: `compiled_text` 섹션 순서 기준 node 매핑(`section_index`, `node_id`, `node_type`, `snippet`)


## Added in this refactor
- ContextSet version history (`ContextSetVersion`)
- Compiled-context explain endpoint (`/api/context_sets/{id}/compiled`)
- Version diff endpoints
- Research-inspired recovery planner endpoints (`/unfold_plan`, `/apply_unfold_plan`)
- Dependency-aware unfold with bounded closure

## Run Studio projection endpoints (additive)
- `GET /api/threads/{thread_id}` (direct thread fetch for deterministic deep-link resolution)
- `GET /api/threads/{thread_id}/run_studio/summary`
- `GET /api/threads/{thread_id}/run_studio/agent_team`
- `GET /api/threads/{thread_id}/run_studio/context_decisions`
- `GET /api/threads/{thread_id}/run_studio/evidence`

Notes:
- Existing routes are preserved.
- The underlying graph schema (`Node`/`Edge`) is unchanged.
- Projections expose conversation/execution/memory-context logical views for frontend consumption.
- UI/operator guide is documented at [`../UI_USAGE_GUIDE.md`](../UI_USAGE_GUIDE.md), including how to distinguish thread team setup from actual execution.
- Agent Team projection now uses stricter runtime extraction rules:
  - canonical runtime snapshot field is `runtime_team_snapshot` (camelCase `runtimeTeamSnapshot` tolerated for compatibility)
  - canonical precedence favors `runtime_team_snapshot.runtime_agents`, then `runtime_agents`, then recognized snapshot member collections
  - plain plan metadata dicts are ignored (no fake members from `mode/reason/budget/execution_order`)
  - fallback remains `conversation_membership` then `inferred_from_steps`
  - `source` / `source_key` labels are normalized for predictable consumers
- Memory/context projection includes explicit buckets: `core_items`, `supporting_items`, `execution_items` (while preserving compatibility fields like `recent_items`).
- Evidence projection now returns ranked claims with `score` and `related_node_ids` for UI drill-down.
- Now summary includes current-run scoped status fields (for example `current_run_id`, `current_run_step_status_counts`, `stale_queued_step_count`) so stale queued steps from older runs do not dominate the primary status.

## Resource node plain-text + structured payload
- `POST /api/threads/{thread_id}/resources`는 기존 필드와 함께 아래 옵션을 지원합니다.
  - `raw_text`: `node.text`에 그대로 저장할 원문
  - `text_mode`: `"plain"`이면 `raw_text`가 없어도 포맷 템플릿 없이 저장
  - `payload_json`: 리소스의 구조화 메타(객체)
- `payload_json`은 서버 기본 필드(`name`, `resource_kind`, `mime_type`, `uri`, `source`, `context_set_id`, `summary`, `tag`)와 merge되며, 기본 필드가 최종값으로 우선합니다.
