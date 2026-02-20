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
# add OPENAI_API_KEY to enable real embeddings + LLM
uvicorn app.main:app --reload --port 8000
```

## Vector search notes
- Backend stores **normalized** embeddings in Postgres table `node_embeddings` (JSON text).
- It also maintains a FAISS index **per thread** in `GOC_FAISS_DIR` (default: `./data/faiss`).
- Search endpoint: `/api/threads/{thread_id}/search?q=...`
