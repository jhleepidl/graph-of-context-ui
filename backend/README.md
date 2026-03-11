# Backend Notes

## Setup
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Set `GOC_DB_URL` in `.env`:
```text
postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME
```

## Architecture
- Graph storage stays generic: `Node` / `Edge`.
- Run Studio data is assembled via service projections (no graph-stack replacement).
- Skill layer is additive and payload-driven.

### Service Ownership
- `app/services/run_studio.py`: Run Studio screen-level summary assembly.
- `app/services/runtime_snapshot.py`: canonical runtime/team snapshot extraction + normalization.
- `app/services/skill_projections.py`: runtime attached-skill and skill-usage extraction.
- `app/services/context_packs.py`: context pack shaping (shared/role/skill scope).
- `app/services/run_skill_summary.py`: run-level aggregation and lineage (`skill -> context -> evidence`).
- `app/services/skill_registry.py`: skill package metadata registry (runtime + defaults).

## Run Studio API Surface
- `GET /api/threads/{thread_id}/run_studio/summary`
- `GET /api/threads/{thread_id}/run_studio/agent_team`
- `GET /api/threads/{thread_id}/run_studio/context_decisions`
- `GET /api/threads/{thread_id}/run_studio/evidence`
- `GET /api/threads/{thread_id}/run_studio/context_packs`
- `GET /api/threads/{thread_id}/run_studio/skill_usage`

Summary-first strategy:
- `summary` is the canonical initial payload.
- detail routes are additive and intended for on-demand UI expansion.
- Skill-aware fields may be populated or empty depending on runtime payload availability; both shapes are supported.

Additional skill routes:
- `GET /api/skills`
- `GET /api/skills/{skill_id}`
- `GET /api/runs/{run_id}/skills`
- `GET /api/runs/{run_id}/context_packs`
- `GET /api/threads/{thread_id}/skill_usage`

## Auth Headers
- `X-Admin-Key: <GOC_ADMIN_KEY>`
- `Authorization: ServiceKey <raw>`
- `Authorization: Bearer <ui_token>`

## Notes
- Existing routes and graph model compatibility are preserved.
- Runtime snapshot extraction precedence and normalization now live in `runtime_snapshot.py`.
- See operator behavior details in [`../UI_USAGE_GUIDE.md`](../UI_USAGE_GUIDE.md).
