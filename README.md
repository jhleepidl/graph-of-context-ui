# Graph-of-Context Run Studio

Graph-of-Context (GoC) is a graph-first control/upgrade layer for conversational runtimes.

- `ddalggak` remains standalone-first as a runtime.
- When connected, GoC upgrades context authority, structured agent management, and observability.
- GoC keeps the generic `Node`/`Edge` model and adds an additive Run Studio projection/control layer.

## Product Surfaces
- `Run Studio` (default): now/status, runtime team, attached skills, context packs, skill usage, context decisions, evidence.
- `Graph`: manual graph editing and fold/unfold.
- `Raw Trace`: execution trace and timeline.
- `Artifacts` and `Advanced` tools remain available.

## Skill-Aware Model (Additive)
- `Agent = role`
- `Skill = reusable expertise package`
- `TeamPlan = roles + attached skills + policy`
- `ContextPack = shared + role-specific + skill-specific context`
- `RuntimeAgent = instantiated role with attached skills`

## Authority Model (Current)
- GoC authoritative now:
  - graph-backed context compilation/selection/decisions and explainability
  - structured agent catalog + conversation team membership
  - runtime projection normalization including authority/fallback metadata
- Runtime-side today:
  - execution and most planning behavior
  - skill package execution and most skill-content authority
  - runtime-emitted team/skill/context-pack projection payloads
- Planning boundary:
  - backend now includes a lightweight planning boundary projection (`runtime_managed`, GoC-ready)
  - future GoC planning capability can attach task interpretation/team plan/skill/context-pack decisions without untangling existing projections

## Runtime Authority Projection Fields
Run Studio and run-scoped projection payloads now expose canonical authority metadata:
- `mode` (`standalone` | `goc`)
- `plan_source` (`local` | `goc` | `local_fallback`)
- `context_source` (`local` | `goc`)
- `agent_catalog_source` (`local` | `goc`)
- `conversation_team_source` (`local` | `goc`)
- `skill_catalog_source` (`local` | `goc` | `mixed`)
- `degraded_mode` (boolean)
- `fallback_reason` (string | null)

This remains projection-compatible with older runtime payload shapes.

This is still projection-oriented over the existing graph backend; no new graph stack is required.
- Run Studio uses `summary` as the primary load and lazy-loads detail panels.
- No-skill payloads remain valid: skill/context panels render empty-state safely.

## Docs Map
- Project overview: this file.
- Backend/API/service notes: [`backend/README.md`](backend/README.md)
- Frontend architecture notes: [`frontend/README.md`](frontend/README.md)
- Operator usage: [`UI_USAGE_GUIDE.md`](UI_USAGE_GUIDE.md)
- Skill UI supplement: [`SKILLS_IN_UI_GUIDE.md`](SKILLS_IN_UI_GUIDE.md)

## Quick Start
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.
