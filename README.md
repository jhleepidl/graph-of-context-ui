# Graph-of-Context Run Studio (Web) - Postgres + FAISS (no pgvector extension)

This repo now ships with a **Run Studio-first** workspace while keeping the generic graph backend/model:
- Run Studio default UI:
  - Now panel (task/objective/current step/blocked/pending approval)
  - Agent Team panel (active roles, order, runtime status)
  - Context Decisions panel (selected/pinned/excluded/missing/conflicting)
  - Evidence panel (claims/evidence/provenance/uncertainty/conflicts)
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
