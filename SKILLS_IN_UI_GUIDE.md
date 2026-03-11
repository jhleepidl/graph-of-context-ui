# Skills In UI Guide

This is a supplement to [`UI_USAGE_GUIDE.md`](UI_USAGE_GUIDE.md), focused only on skill interpretation.

## Mental Model
- `Agent` = runtime role.
- `Skill` = reusable procedural package.
- `Context Pack` = shared + role-specific + skill-specific context loading.

## Load Levels
- `metadata_only`: skill identity/descriptor only.
- `instructions`: procedural instructions loaded.
- `resources`: instructions + resource/tool context loaded.

## “Why was this skill selected?”
1. Open `Attached Skills` and read `selected_by` + `selection_reason`.
2. Check `Skill Usage` for selection/escalation events.
3. Check `Context Packs` to confirm load-level escalation and skill-scoped item counts.
4. If still unclear, inspect `Raw Trace`/`Graph` lineage.

## Related APIs
- `GET /api/skills`
- `GET /api/skills/{skill_id}`
- `GET /api/runs/{run_id}/skills`
- `GET /api/runs/{run_id}/context_packs`
- `GET /api/threads/{thread_id}/run_studio/context_packs`
- `GET /api/threads/{thread_id}/run_studio/skill_usage`

If these responses have empty `attached_skills` / `context_packs` / `skill_usage`, UI behavior is still valid and indicates no skill-aware runtime metadata was emitted for that run scope.
