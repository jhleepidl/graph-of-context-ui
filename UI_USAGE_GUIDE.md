# UI Usage Guide

This guide explains how to interpret Run Studio and avoid confusion between team setup and actual execution.

## Thread Team vs Execution
- **Thread Team (Config)** is static configuration for a thread: enabled agents, order, and overrides.
- **Runtime Team** is what a run actually used at execution time (from runtime snapshots/step payloads).
- Changing Thread Team does **not** mean work already executed.
- Work execution is confirmed when a run has execution steps, tool calls, artifacts, or status progression.

## What Run Studio Shows
- **Now**: current task/objective/step, run status, approval state, and an execution hint.
- **Agent Team**: runtime team first (when available), otherwise thread team/inferred step agents. Runtime items now include attached skills/context pack links when emitted.
- **Attached Skills**: role -> skill mapping, load level (`metadata_only` / `instructions` / `resources`), and selection reason.
- **Context Packs**: shared context count, role-specific count, and skill-scoped loading summaries.
- **Skill Usage**: skill usage/feedback events with event type, timestamp, and payload summary.
- **Context Decisions**: selected, pinned, excluded, missing, and conflicting context signals.
- **Evidence**: ranked claims with supporting nodes, provenance, uncertainty, and conflicts.

## Which View To Use
- **Run Studio**: primary operational view.
- **Graph**: detailed graph editing, fold/unfold, and manual graph inspection.
- **Raw Trace**: execution trace details (runs/steps/timeline).
- **Artifacts**: generated files/resources.
- **Advanced**: power tools (prompt builder, run controls, thread team configuration, inspector).

## Approvals and Post-Team-Change Behavior
- If Run Studio shows **Waiting for approval**, execution is paused until approval resolves.
- If Run Studio shows **Team updated, but no execution step detected yet**, team composition changed but execution has not started.
- If Run Studio shows **Older queued work exists in prior runs**, queued steps exist in older runs but are not treated as the current run.
- If status indicates running/done and steps exist, execution has started/completed.

## Deep-Link Behavior (`?thread=...`)
- If a `thread` query parameter is provided, the workspace tries to open that exact thread.
- If the thread cannot be resolved or accessed, the UI now shows a clear notice and does **not** silently open a different thread.
- You can then manually pick a different thread from the selector.

## Basic Troubleshooting
- **Team changed but no work executed**:
  - Check the Now panel execution hint.
  - Open Raw Trace and verify run/step nodes exist.
  - Trigger a run action if only team configuration changed.
- **`/context` (or `?thread=`) opened unexpected content**:
  - Check the deep-link notice in the left panel.
  - If the target thread is unavailable, no fallback thread is auto-opened.
  - Select a thread manually after confirming access.
- **Runtime team differs from Thread Team**:
  - Runtime snapshots represent what actually ran.
  - Thread Team is only default configuration.
- **Need to inspect evidence/context quality**:
  - Use Context Decisions and Evidence cards first.
  - Use Focus/Open actions to jump into Graph details for verification.
- **Need to answer \"why was this skill selected?\"**:
  - Check `Attached Skills` for `selection_reason` and `selected_by`.
  - Check `Skill Usage` for selection/escalation events.
  - Check `Context Packs` for whether the skill stayed at `metadata_only` or escalated to `instructions/resources`.
  - Use Graph/Raw Trace if you need deeper downstream lineage inspection.
