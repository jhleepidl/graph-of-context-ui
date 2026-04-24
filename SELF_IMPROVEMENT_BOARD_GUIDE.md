# Self-improvement board guide

GoC now exposes self-improvement artifacts on the Board.

## New lanes

- `improvement_jobs`
- `code_snapshots`
- `code_diffs`
- `test_reports`
- `canary_results`

## API

- `POST /api/threads/{thread_id}/improvement_jobs`
- `GET /api/threads/{thread_id}/improvement_jobs`
- `GET /api/threads/{thread_id}/improvement_jobs/{job_id}`
- `POST /api/threads/{thread_id}/improvement_jobs/{job_id}/report`

All improvement artifacts are marked as `learning_excluded=true` and `promotion_blocked=true`.
They are visible for audit and operator review, but are not reused as skills or team assets.
