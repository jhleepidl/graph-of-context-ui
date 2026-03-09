# Graph-of-Context Run Studio (Web) - Postgres + FAISS (no pgvector extension)

This repo now ships with a **Run Studio-first** workspace while keeping the generic graph backend/model:
- Run Studio default UI:
  - Now panel (task/objective/current step/blocked/pending approval)
  - Agent Team panel (active roles, order, runtime status, runtime snapshot source)
  - Context Decisions panel (selected/pinned/excluded/missing/conflicting)
  - Evidence panel (claims/evidence/provenance/uncertainty/conflicts with ranking)
- Secondary tabs:
  - Graph (manual graph editing and fold/unfold)
  - Raw Trace (execution graph + timeline + inspector)
  - Artifacts
  - Advanced tools (Prompt Builder / Run / Job Settings / Thread Team / Inspector)
- Backend remains graph-first and generic (`Node`/`Edge`), with additive run-studio projection endpoints.

## Run Studio API Additions
- `GET /api/threads/{thread_id}/run_studio/summary`
- `GET /api/threads/{thread_id}/run_studio/agent_team`
- `GET /api/threads/{thread_id}/run_studio/context_decisions`
- `GET /api/threads/{thread_id}/run_studio/evidence`

All existing APIs remain available.

## Run Studio second-pass behavior
- Agent Team prefers runtime team snapshots (`runtime_team_snapshot`, `runtime_agents`, `team_plan`) from run/step payloads when present, and falls back to conversation membership/inferred steps when missing.
- Context projection separates:
  - `core_items` (Decision/Assumption/Plan/MemoryItem/Observation/ContextSummary)
  - `supporting_items` (Artifact/Resource/ContextCandidate)
  - `execution_items` (Step/Message/Fold/Run/ToolCall/ToolResult)
- Context Decisions and Evidence cards support drill-down actions (open node / open trace pair), routing operators to graph-level details quickly.
- Graph/editor/manual tools remain available under secondary tabs (`Graph`, `Raw Trace`, `Advanced`).

## 1) Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Set GOC_DB_URL to your server Postgres
uvicorn app.main:app --reload --port 8000
```

## 2) Frontend
```bash
cd frontend
npm install
npm run dev
```

Open: http://127.0.0.1:5173
