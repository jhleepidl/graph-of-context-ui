# UI Usage Guide

This guide is for operators using Run Studio day-to-day.

## Read This First
- `Thread Team` is configuration.
- `Runtime Team` is what actually executed for the run scope.
- Team changes alone do not prove execution happened.

## Where To Look
- `Now`: current run/step status, blocked/pending signals, stale queued indicator.
- `Agent Team`: runtime team first; falls back to thread/inferred data when runtime snapshot is missing.
- `Context Decisions`: selected/pinned/excluded/missing/conflicting context.
- `Evidence`: ranked claims and supporting/conflicting links.
- `Graph` / `Raw Trace`: deep drill-down.

## Skill-Aware Panels
- `Attached Skills`: role -> skill links, load level, selected-by, reason.
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
- Status shows queued but feels stale:
  - inspect `Now.stale_queued_step_count` (older runs can be excluded from current status).
- Need context/evidence validation:
  - start in `Context Decisions` + `Evidence`, then jump to `Graph`.
