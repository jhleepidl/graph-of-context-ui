# UI Usage Guide

This guide is for operators using Run Studio day-to-day.

## Read This First
- `Thread Team Config` is configuration. Its manifest editor is the primary control surface for ddalggak team state.
- The lower roster editor in `Thread Team Config` is a compatibility membership editor, not the canonical structure_v2 editor.
- `Team View` shows the runtime agents that actually executed for the run scope.
- Team changes alone do not prove execution happened.
- `ddalggak` is the execution runtime; GoC is the graph-first projection/control layer.
- `planner` should not be interpreted as a worker role in Run Studio. Planning is surfaced as control-plane/runtime stages instead.

## Where To Look
- `Now`: current run/step status, blocked/pending signals, stale queued indicator.
- `Team View`: runtime agents first; falls back to thread/inferred data when runtime snapshot is missing.
- `Why this team?`: selection explanations, slot reasons, preset-backed vs synthesized choices.
- `Orchestration`: supervisor mode, parallel groups, sequential dependencies, report-back edges.
- `Collaboration`: reflection/debate/committee cells.
- `Authority`: authority profiles, restrictions, approval-required actions.
- `Checkpoints`: human-interrupt and approval stops.
- `Context Decisions`: selected/pinned/excluded/missing/conflicting context.
- `Evidence`: ranked claims and supporting/conflicting links.
- `Graph` / `Raw Trace`: deep drill-down.

## Skill-Aware Panels
- `Dominant Skills`: runtime-agent -> skill links, load level, selected-by, reason.
- `Context Packs`: shared/role-specific/skill-scoped loading counts.
- `Skill Usage`: event stream for selection/escalation/usage traces.
- If a run has no skill metadata, these panels stay visible and show empty-state messages.

Skill-specific interpretation is documented in [`SKILLS_IN_UI_GUIDE.md`](SKILLS_IN_UI_GUIDE.md).

## Deep-Link Behavior
- `?thread=<id>&ctx=<id>` attempts exact selection.
- If explicit thread is unavailable, UI shows a notice and does not silently pick another thread.

## Quick Troubleshooting
- Team changed but no execution:
  - check `Now` status and current run step counts.
  - inspect `Raw Trace` for actual steps.
- Need to understand why multiple runtime agents exist:
  - start in `Why this team?`
  - then inspect `Orchestration` and `Collaboration`
- Status shows queued but feels stale:
  - inspect `Now.stale_queued_step_count` (older runs can be excluded from current status).
- Need context/evidence validation:
  - start in `Context Decisions` + `Evidence`, then jump to `Graph`.
