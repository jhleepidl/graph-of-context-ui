# Skills In UI Guide

This is a supplement to [`UI_USAGE_GUIDE.md`](UI_USAGE_GUIDE.md), focused only on skill interpretation.

## Mental Model
- `ddalggak` is the execution runtime; GoC projects what it emitted into graph/control views.
- `RuntimeAgent = Role + Attached Skills + Context Pack`.
- `Skill` = reusable procedural package.
- `Context Pack` = shared + role-specific + skill-specific context loading.
- Human-authored presets remain text-first. They can later be instantiated as structured runtime agents.

## Load Levels
- `metadata_only`: skill identity/descriptor only.
- `instructions`: procedural instructions loaded.
- `resources`: instructions + resource/tool context loaded.

## “Why was this skill selected?”
1. Open `Team View` and inspect each runtime agent's `Dominant Skills`.
2. Open `Why this team?` to see slot-level and runtime-agent selection reasons.
3. Check `Skill Usage` for selection/escalation events.
4. Check `Context Packs` to confirm load-level escalation and skill-scoped item counts.
5. If still unclear, inspect `Raw Trace`/`Graph` lineage.

## Related APIs
- `GET /api/skills`
- `GET /api/skills/{skill_id}`
- `GET /api/runs/{run_id}/skills`
- `GET /api/runs/{run_id}/context_packs`
- `GET /api/threads/{thread_id}/run_studio/context_packs`
- `GET /api/threads/{thread_id}/run_studio/skill_usage`

If these responses have empty `attached_skills` / `context_packs` / `skill_usage`, UI behavior is still valid and indicates no skill-aware runtime metadata was emitted for that run scope.
