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

Recommended local PostgreSQL setup in `.env`:
```text
GOC_DB_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/goc
GOC_DB_AUTO_CREATE=true
GOC_DB_CREATE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/postgres
GOC_DB_CREATE_DATABASE=postgres
```

Notes:
- `GOC_DB_AUTO_CREATE=true` lets the backend create the target database automatically when the server can connect to the maintenance database.
- `GOC_DB_CREATE_URL` should point at an existing admin/maintenance database such as `postgres`.
- `GET /healthz` now verifies database reachability and returns `503` when the DB is unavailable.

## Architecture
- Graph storage stays generic: `Node` / `Edge`.
- Run Studio data is assembled via service projections (no graph-stack replacement).
- Skill layer is additive and payload-driven.
- `ddalggak` is the execution runtime.
- GoC is the graph-first projection/control layer when connected.
- Human-authored presets remain text-first, but the runtime/control model is structured.

### Core Runtime Model
- `RuntimeAgent = Role + Attached Skills + Context Pack`.
- Team composition is capability-slot fulfillment.
- `TeamPlan v2` can carry `task_interpretation`, `slots`, `runtime_agents`, `SupervisorRuntime`, `collaboration_cells`, `authority_graph`, `checkpoints`, and `execution_graph`.
- `SupervisorRuntime` is a control actor, not a worker role.
- `planner` is not a canonical runtime worker role in GoC projections.
- Collaboration cells describe runtime cooperation such as reflection, debate, and committee review.
- GoC stays backward compatible with legacy runtime payloads and mixed payloads.

### Service Ownership
- `app/services/run_studio.py`: Run Studio screen-level summary assembly + capability composition.
- `app/services/resolved_runtime.py`: shared runtime-facing projection layer for scoped authority, team, capability, and planning-boundary resolution.
- `app/services/runtime_snapshot.py`: canonical runtime/team snapshot extraction + normalization.
- `app/services/runtime_scope.py`: shared current-run / active runtime scope resolution (single source of truth).
- `app/services/runtime_authority.py`: ddalggak -> GoC authority contract normalization, canonical precedence, and backward-compatible extraction.
- `app/services/conversation_team.py`: structured conversation team projection (runtime snapshot, membership, inference fallback).
- `app/services/skill_projections.py`: runtime attached-skill and skill-usage extraction.
- `app/services/context_packs.py`: context pack shaping (shared/role/skill scope).
- `app/services/run_skill_summary.py`: run-level aggregation and lineage (`skill -> context -> evidence`).
- `app/services/skill_registry.py`: skill package metadata registry (runtime + defaults).
- `app/services/planning_boundary.py`: lightweight planning capability boundary (`runtime_managed`, GoC-ready).

### Capability Domains
- `context authority`: compiled context, selected/excluded/missing/conflicting explainability (`context_decisions`, graph context compilation).
- `agent management`: catalog lifecycle and conversation membership APIs (`routers/agents.py`).
- `conversation team projection`: operator-visible team state (`conversation_team.py`, Run Studio team panels).
- `runtime projection + scope`: unified run/step scope across summary/context-pack/skill-usage views (`runtime_scope.py`).
- `skills observability`: attached skills, usage events, context-pack skill metadata (projection-oriented; runtime-executed).
- `planning boundary`: explicit seam for future GoC planning migration without changing runtime projection contracts.

### Run Studio Projection Vocabulary
- `Team View`: normalized runtime agents for the current run scope.
- `Why this team?`: selection explanations, slot-level reasons, preset vs synthesized summary.
- `Orchestration`: supervisor mode, parallel groups, sequential dependencies, and report-back edges.
- `Collaboration`: reflection/debate/committee cells.
- `Authority`: per-instance authority profile summary and restrictions.
- `Checkpoints`: human-interrupt and approval stops.

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
- No API path changes are required for TeamPlan v2 support.

Structured runtime/control fields may now appear on `summary` and run-scoped capability payloads:
- `task_interpretation`
- `team_view`
- `why_this_team`
- `orchestration`
- `collaboration`
- `authority`
- `checkpoints`

Authority/fallback projection fields are exposed across summary and run-scoped detail payloads:
- `mode`
- `plan_source`
- `context_source`
- `agent_catalog_source`
- `conversation_team_source`
- `skill_catalog_source`
- `degraded_mode`
- `fallback_reason`

These fields form the canonical ddalggak -> GoC runtime authority contract. GoC consumes exact canonical fields first, then falls back to backward-compatible inference for older payload shapes.

Canonical contract expectations:
- `mode`: `standalone | goc`
- `plan_source`: `local | goc | local_fallback`
- `context_source`: `local | goc`
- `agent_catalog_source`: `local | goc`
- `conversation_team_source`: `local | goc`
- `skill_catalog_source`: `local | goc | mixed`
- `degraded_mode`: `boolean`
- `fallback_reason`: `string | null`

Contract precedence:
- canonical `runtime_authority` / `runtimeAuthority` payload blocks win over legacy sibling fields
- canonical exact field names win over inferred legacy aliases when both are present
- later legacy node data can fill gaps, but it does not override canonical contract fields already observed

Degraded behavior:
- `plan_source=local_fallback` or an explicit `fallback_reason` surfaces `degraded_mode=true`
- ordinary `message` / `reason` fields are not treated as degraded signals
- resolved runtime projections keep summary, team, skill, context-pack, and planning-boundary views aligned to the same authority truth

Planning-boundary semantics:
- planning is no longer framed around a planner worker concept
- the compatibility field remains, but the projection now centers on runtime/control stages
- current stage vocabulary: `task_interpretation`, `team_building`, `preset_resolution`, `skill_resolution`, `context_pack_building`, `execution_coordination`

Additional skill routes:
- `GET /api/skills`
- `GET /api/skills/{skill_id}`
- `GET /api/runs/{run_id}/skills`
- `GET /api/runs/{run_id}/context_packs`
- `GET /api/threads/{thread_id}/skill_usage`

Structured team endpoints (canonical thread-based semantics):
- `GET /api/threads/{thread_id}/team`
- `POST /api/threads/{thread_id}/team/members`
- `POST /api/threads/{thread_id}/team/reorder`
- `PATCH /api/threads/{thread_id}/team/members/{agent_id}`
- `DELETE /api/threads/{thread_id}/team/members/{agent_id}`

Team route semantics:
- `/api/threads/{thread_id}/team...` is the canonical structured team API.
- `/api/conversations/{thread_id}/team...` remains available as a compatibility alias only.
- Passive team reads do not bootstrap default agents and do not create explicit membership.
- Team payloads represent explicit persisted conversation/thread membership. They do not claim to be the full runtime active team or runtime baseline/default policy.
- `conversation.team` is the canonical structured membership block. `conversation.agents` remains a backward-compatible alias of the same explicit membership entries.
- `conversation.team.enabled_members` and `conversation.team.disabled_members` split the persisted membership list by the stored `enabled` flag.
- `conversation.team.baseline_policy.mode=not_modeled` means the backend is not asserting baseline/default agent availability for that thread. Missing baseline/default agents are not treated as membership errors unless a future policy layer models them explicitly.

Conversation ensure/bootstrap semantics:
- `POST /api/conversations/ensure` is safe by default: it ensures the conversation row exists and returns the current explicit membership view.
- `bootstrap_defaults=true` installs private copies of the public default agents for the conversation owner, but it still does not create explicit membership by itself.
- `add_to_conversation=true` is the extra opt-in that seeds explicit conversation membership from those bootstrapped private copies. It requires `bootstrap_defaults=true`.
- `POST /api/agents/bootstrap_defaults` remains the explicit install/bootstrap route. Its `add_to_conversation` flag is an explicit membership mutation, not passive read behavior.

Logical agent lineage for integration consumers:
- Public default agents are the canonical templates: `is_system_default=true`, `system_key` is set, `service_id=public`, `owner_user_id=system`.
- Installed private copies derived from those defaults keep `source_agent_id=<public_default_agent_id>` and have `is_system_default=false`.
- Consumers that want to dedupe logical roles across public defaults and installed private copies should treat `source_agent_id` as the lineage pointer when present, then fall back to the agent's own `id` for standalone/private-only agents.

## Auth Headers
- `X-Admin-Key: <GOC_ADMIN_KEY>`
- `Authorization: ServiceKey <raw>`
- `Authorization: Bearer <ui_token>`

## Notes
- Existing routes and graph model compatibility are preserved.
- Runtime snapshot extraction precedence and normalization now live in `runtime_snapshot.py`.
- Current run resolution is centralized in `runtime_scope.py`; run-studio and skill/context summaries now share the same inference path.
- Canonical runtime authority contract interpretation is centralized in `runtime_authority.py` and consumed through `resolved_runtime.py`.
- GoC is authoritative for graph-backed context and structured agent/team management once connected.
- Skill package execution/content authority remains mostly runtime-side; GoC currently focuses on skill observability/projection.
- TeamPlan v2 and legacy runtime payloads are both first-class supported inputs.
- See operator behavior details in [`../UI_USAGE_GUIDE.md`](../UI_USAGE_GUIDE.md).
