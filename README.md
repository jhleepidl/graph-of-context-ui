# Graph-of-Context Run Studio (Web) - Postgres + FAISS (no pgvector extension)

This repo now ships with a **Run Studio-first** workspace while keeping the generic graph backend/model:
- Run Studio default UI:
  - Now panel (task/objective/current step/blocked/pending approval)
  - Agent Team panel (active roles, order, runtime status, runtime snapshot source, attached skills)
  - Attached Skills panel (role -> skill mapping, load level, selection reason)
  - Context Packs panel (shared/role-specific/skill-specific loading and conflicts)
  - Skill Usage panel (skill events and runtime selection traces)
  - Context Decisions panel (selected/pinned/excluded/missing/conflicting)
  - Evidence panel (claims/evidence/provenance/uncertainty/conflicts with ranking)
- Secondary tabs:
  - Graph (manual graph editing and fold/unfold)
  - Raw Trace (execution graph + timeline + inspector)
  - Artifacts
  - Advanced tools (Prompt Builder / Run / Job Settings / Thread Team / Inspector)
- Backend remains graph-first and generic (`Node`/`Edge`), with additive run-studio projection endpoints.
- Operator usage guide is available at [`UI_USAGE_GUIDE.md`](UI_USAGE_GUIDE.md), including team setup vs execution troubleshooting.
- Skill-focused operator guide is available at [`SKILLS_IN_UI_GUIDE.md`](SKILLS_IN_UI_GUIDE.md).

## Run Studio API Additions
- `GET /api/threads/{thread_id}/run_studio/summary`
- `GET /api/threads/{thread_id}/run_studio/agent_team`
- `GET /api/threads/{thread_id}/run_studio/context_decisions`
- `GET /api/threads/{thread_id}/run_studio/evidence`
- `GET /api/threads/{thread_id}/run_studio/context_packs`
- `GET /api/threads/{thread_id}/run_studio/skill_usage`
- `GET /api/threads/{thread_id}/skill_usage`
- `GET /api/runs/{run_id}/skills`
- `GET /api/runs/{run_id}/context_packs`
- `GET /api/skills`
- `GET /api/skills/{skill_id}`

All existing APIs remain available.

## Skill layer model (additive)
- **Agent = role** at runtime.
- **Skill = reusable expertise package** attached to a runtime role.
- **TeamPlan** can define roles and attached skills.
- **ContextPack** includes shared + role-specific + skill-specific context loading.
- **RuntimeAgent** is an instantiated role with attached skills and optional context pack linkage.
- **Graph / Run Studio** remains generic `Node`/`Edge`, now with additive projections for skill/context/evidence lineage.

## Run Studio behavior (hardened)
- Canonical runtime snapshot field is `runtime_team_snapshot` (with compatibility tolerance for `runtimeTeamSnapshot`).
- Agent Team extraction order is explicit: `runtime_team_snapshot.runtime_agents` -> `runtime_agents` -> recognized member collections in known snapshot shapes -> conversation membership -> inferred step agents.
- Runtime extraction is strict: plain `team_plan` metadata dictionaries are ignored unless they carry explicit member-like collections, preventing garbage members from keys like `mode`, `reason`, `budget`, `execution_order`.
- Agent Team `source`/`source_key` labels are normalized and predictable (`runtime_snapshot`, `conversation_membership`, `inferred_from_steps`; keys like `runtime_team_snapshot.runtime_agents`, `runtime_agents`, `team_plan.agents`, `conversation_agents`, `step_payload.agent_id`).
- Context projection separates:
  - `core_items` (Decision/Assumption/Plan/MemoryItem/Observation/ContextSummary)
  - `supporting_items` (Artifact/Resource/ContextCandidate)
  - `execution_items` (Step/Message/Fold/Run/ToolCall/ToolResult)
- Context Decisions / Missing Context / Evidence cards support lightweight operator actions (`Focus in graph`, `Open detail`, `Include/Add to active`, `Pin`, `Compare pair`) using existing graph/context flows.
- The Now panel includes an execution hint to distinguish team-configuration changes from actual execution-step progress.
- Now summary selection is current-run scoped, so stale queued steps from older/superseded runs are de-prioritized in the primary status view.
- Deep-link `?thread=<id>` is deterministic: the UI opens that thread or shows an explicit unavailable notice (no silent fallback to another thread).
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
