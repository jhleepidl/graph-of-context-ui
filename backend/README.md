# Graph-of-Context MVP (Backend) - Postgres + FAISS (no pgvector extension)

This backend stores the conversation graph in Postgres, and performs vector search using an in-process FAISS index.
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

## Vector search notes
- Backend stores **normalized** embeddings in Postgres table `node_embeddings` (JSON text).
- It also maintains a FAISS index **per thread** in `GOC_FAISS_DIR` (default: `./data/faiss`).
- Search endpoint: `/api/threads/{thread_id}/search?q=...`

## Compiled context freshness
- `compiled_text`는 캐시 없이 매 요청마다 DB의 current active nodes/edges로 동적 생성합니다.
- 따라서 node text 수정, node/edge 삭제/추가, activate 변경 직후 다음 `/api/context_sets/{id}/compiled` 호출에 즉시 반영됩니다.


## Added in this refactor
- ContextSet version history (`ContextSetVersion`)
- Compiled-context explain endpoint (`/api/context_sets/{id}/compiled`)
- Version diff endpoints
- Research-inspired recovery planner endpoints (`/unfold_plan`, `/apply_unfold_plan`)
- Dependency-aware unfold with bounded closure
