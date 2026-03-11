# Skills In UI Guide

This guide explains how to read the additive skill layer in Run Studio.

## Mental Model
- **Agent = role** at runtime.
- **Skill = reusable procedural expertise package** attached to a runtime role.
- **Context Pack = shared + role-specific + skill-specific context loading plan**.

## Where Skills Appear
- **Agent Team**
  - Each runtime role can show `attached_skills` and `context_pack_id`.
- **Attached Skills panel**
  - Shows role-to-skill links, load level, selector (`selected_by`), and `selection_reason`.
- **Context Packs panel**
  - Shows `shared_items_count`, `role_specific_items_count`, and per-skill load summary (`skill_items`).
- **Skill Usage panel**
  - Shows skill event stream (`event_type`, timestamp, payload summary).

## Interpreting Load Levels
- `metadata_only`: skill id/descriptor loaded, but no full instructions/resources.
- `instructions`: skill procedural instructions were loaded.
- `resources`: skill instructions plus resource/tool context were loaded.

## Skill-Aware Context vs Generic Context
- Generic context view answers: "what context was active?"
- Skill-aware context view answers: "which skill caused which context load and at what level?"
- Use both together:
  - Context Decisions for selection/exclusion/missing/conflicts.
  - Context Packs for skill-scoped loading.

## Troubleshooting "Why Was This Skill Selected?"
1. Open **Attached Skills** and check `selected_by` + `selection_reason`.
2. Open **Skill Usage** and look for `selected`, `escalated`, `used` events.
3. Open **Context Packs** to verify if load escalated (`metadata_only` -> `instructions` -> `resources`).
4. If still unclear, inspect **Raw Trace** and **Graph** for downstream evidence/artifact links.

## API Paths
- `GET /api/skills`
- `GET /api/skills/{skill_id}`
- `GET /api/runs/{run_id}/skills`
- `GET /api/runs/{run_id}/context_packs`
- `GET /api/threads/{thread_id}/skill_usage`
- `GET /api/threads/{thread_id}/run_studio/context_packs`
- `GET /api/threads/{thread_id}/run_studio/skill_usage`
