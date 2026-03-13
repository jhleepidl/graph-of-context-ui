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
- `ddalggak` remains runtime-first; GoC is the upgrade/control layer when connected.

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

Compatibility aliases are still available under `/api/conversations/{thread_id}/team...` for backward compatibility.

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
- See operator behavior details in [`../UI_USAGE_GUIDE.md`](../UI_USAGE_GUIDE.md).
