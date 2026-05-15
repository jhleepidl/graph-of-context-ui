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

## ddalggak runtime sync surfaces

Recent ddalggak builds can push additional runtime-control data into GoC. Run Studio now displays these as first-class panels:

- **Runtime Policy**: latest task-loop policy resolution, including `execution_mode`, `workspace_write`, `artifact_delivery`, and `legacy_manual_fallback`.
- **Agent Activity**: agent lifecycle events, handoffs, and policy events from `agent_activity.jsonl`, `agent_handoffs.jsonl`, and `execution_policy_resolutions.jsonl`.
- **Agent Packages**: portable agent package export/publish candidates created by `/agents export` or `/agents publish-candidate`. The panel highlights whether private memory is copied; safe packages should use fresh private memory on clone.
- **Model Catalog**: discovered model nodes from Gemini CLI, Codex CLI, Ollama, or OpenAI-compatible endpoints, plus recent token usage.

The ddalggak service can sync these surfaces through:

```text
POST /api/threads/{thread_id}/agent-activity
POST /api/threads/{thread_id}/agent-packages
POST /api/threads/{thread_id}/model-usage
POST /api/model-nodes
POST /api/model-nodes/usage
```

Read endpoints are available at the matching `GET` paths. Model catalog write endpoints require an admin or service principal. Thread-scoped endpoints follow the same thread read/write access rules as watch tasks and review inbox.

## Semantic Board in Run Studio

Run Studio now includes a Semantic Board panel under **Memory & review**. It is the human review projection for ddalggak's typed card board:

- `memory_card`, `skill_card`, `rule_card`, `agent_card`, package/model/task/evidence cards
- weighted links between cards such as `uses`, `exports_rule`, `applies_to`, `supports`
- score-aware reusable skills/rules surfaced as top reusable cards

Ingest from ddalggak with:

```http
POST /api/threads/{thread_id}/semantic-board
```

List in GoC with:

```http
GET /api/threads/{thread_id}/semantic-board?card_type=skill_card&limit=120
```

The board is intended as the canonical-candidate/mirror layer. Markdown and HTML remain projections for export, review, and handoff.
