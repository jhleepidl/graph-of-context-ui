# Room Continuity Control Surface

GoC's primary product surface is **Room continuity**: current goal, next action, source/evidence boundaries, user rules and corrections, active work, checkpoints, branches, and artifacts. `ddalggak` remains the execution plane. Agent, model, topology, collaboration, and harness projections remain inspectable under Advanced Runtime; they are not the product home.

> The model can change. The Room remembers.

The strongest suitable current single model plus provider-native delegation is the default execution baseline. External multi-agent orchestration must be justified by independent review needs or measured evaluation uplift.

---

# Graph-of-Context Run Studio

Graph-of-Context (GoC) is a graph-first projection and control layer for conversational runtimes.

- `ddalggak` is the execution runtime.
- GoC stays graph-first: it projects runtime state into operator-facing structures, explainability, and control-plane semantics.
- GoC keeps the generic `Node`/`Edge` model and adds an additive Run Studio projection layer without replacing the runtime.

## Product Surfaces
- `Run Studio` (default): `Now`, `Team View`, `Why this team?`, `Orchestration`, `Collaboration`, `Authority`, `Checkpoints`, `Dominant Skills`, `Context Packs`, `Skill Usage`, `Context Decisions`, `Evidence`.
- `Graph`: manual graph editing and fold/unfold.
- `Raw Trace`: execution trace and timeline.
- `Artifacts` and `Advanced` tools remain available.

## Runtime Model
- Human-authored presets are text-first role templates. They stay easy to edit and reason about.
- The internal runtime model is structured.
- `RuntimeAgent = Role + Attached Skills + Context Pack`.
- Team composition is capability-slot fulfillment, not a flat list of worker labels.
- `RuntimeAgent` instances may be preset-backed or synthesized.
- `SupervisorRuntime` is a control actor, not a worker role.
- `planner` is not a canonical runtime worker role in GoC projections.
- Collaboration cells express structured cooperation such as reflection, debate, and committee review.

## Authority Model (Current)
- GoC authoritative now:
  - graph-backed context compilation/selection/decisions and explainability
  - structured agent catalog + conversation team membership
  - runtime projection normalization including authority/fallback metadata and structured control-plane views
- Runtime-side today:
  - execution and team-plan realization inside `ddalggak`
  - skill package execution and most skill-content authority
  - runtime-emitted team/skill/context-pack/control payloads
- Planning boundary:
  - backend includes a lightweight planning-boundary projection for `task_interpretation`, `team_building`, `preset_resolution`, `skill_resolution`, `context_pack_building`, and `execution_coordination`
  - future GoC planning capability can attach richer control-plane decisions without breaking runtime payload compatibility

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

## Backward Compatibility
- GoC remains backward compatible with legacy runtime payloads.
- Older payloads that only expose legacy team/runtime/context shapes still project safely.
- Mixed payloads prefer the newer structured runtime fields first, then fall back to legacy data when needed.

This is still projection-oriented over the existing graph backend; no new graph stack is required.
- Run Studio uses `summary` as the primary load and lazy-loads detail panels.
- No-skill payloads remain valid: skill/context panels render empty-state safely.

## Docs Map
- Project overview: this file.
- Backend/API/service notes: [`backend/README.md`](backend/README.md)
- Frontend architecture notes: [`frontend/README.md`](frontend/README.md)
- Operator usage: [`docs/guides/UI_USAGE_GUIDE.md`](docs/guides/UI_USAGE_GUIDE.md)
- Skill UI supplement: [`docs/guides/SKILLS_IN_UI_GUIDE.md`](docs/guides/SKILLS_IN_UI_GUIDE.md)

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

### Memory Browser

GoC includes a read-only room memory browser at `GET /api/threads/{thread_id}/memory/browse`, surfaced in Run Studio above memory projections. It groups memory by surface and exposes status, owner role, trust tier, provenance, and preview text for easier browsing than Telegram.

### Room Docs Browser

Run Studio includes a Room Docs Browser backed by `GET /api/threads/{thread_id}/room-docs`, showing `AGENTS.md`, MOCs, living docs, and action notes derived from room usage events.
