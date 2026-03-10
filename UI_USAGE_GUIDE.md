# UI Usage Guide

This guide explains how to interpret Run Studio and avoid confusion between team setup and actual execution.

## Thread Team vs Execution
- **Thread Team (Config)** is static configuration for a thread: enabled agents, order, and overrides.
- **Runtime Team** is what a run actually used at execution time (from runtime snapshots/step payloads).
- Changing Thread Team does **not** mean work already executed.
- Work execution is confirmed when a run has execution steps, tool calls, artifacts, or status progression.

## What Run Studio Shows
- **Now**: current task/objective/step, run status, approval state, and an execution hint.
- **Agent Team**: runtime team first (when available), otherwise thread team/inferred step agents.
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
- If status indicates running/done and steps exist, execution has started/completed.

## Basic Troubleshooting
- **Team changed but no work executed**:
  - Check the Now panel execution hint.
  - Open Raw Trace and verify run/step nodes exist.
  - Trigger a run action if only team configuration changed.
- **Runtime team differs from Thread Team**:
  - Runtime snapshots represent what actually ran.
  - Thread Team is only default configuration.
- **Need to inspect evidence/context quality**:
  - Use Context Decisions and Evidence cards first.
  - Use Focus/Open actions to jump into Graph details for verification.
