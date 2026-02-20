# Graph-of-Context MVP (Web) - Postgres + FAISS (no pgvector extension)

This repo contains a minimal Graph-of-Context workflow:
- Graph storage (nodes/edges) + visualization
- Active Context (user on/off control)
- Run with Active Context (LLM call; stub if no API key)
- Folding/Unfolding
- Context search powered by in-process FAISS (no pgvector extension)
- Copy-to-ChatGPT prompt generation with embedded TAGGED FORMAT rules and explicit Korean-answer instruction
- Paste-from-ChatGPT import and manual context-node creation without running the agent
- Direct USER REQUEST-to-context-node creation, persisted draggable node layout, and cleaner chronological edges
- Interactive edge add/delete in graph view (connect handles, delete selected edge)
- Interactive Active Context toggling from graph and fold-focused view (members hidden until detail view/zoom)
- Folded-view virtual edges preserve connectivity between a fold and outside nodes
- Drag-and-drop Active Context composition (add from timeline, reorder, drop-to-remove)
- Graph viewer node movement is disabled to focus on edge create/delete and fold/unfold workflows

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
