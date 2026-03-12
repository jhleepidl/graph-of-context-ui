from __future__ import annotations

from typing import Any, Protocol


class PlanningBoundaryProvider(Protocol):
    def project(self, *, run_id: str | None, runtime_authority: dict[str, Any] | None = None) -> dict[str, Any]:
        ...


class RuntimePlanningBoundary:
    """Current planning boundary: planning is runtime-managed, GoC-ready."""

    def project(
        self,
        *,
        run_id: str | None,
        runtime_authority: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        authority = runtime_authority or {}
        return {
            "status": "runtime_managed",
            "managed_by": "runtime",
            "run_id": run_id,
            "plan_source": str(authority.get("plan_source") or "local"),
            "mode": str(authority.get("mode") or "standalone"),
            "degraded_mode": bool(authority.get("degraded_mode") or False),
            "fallback_reason": authority.get("fallback_reason"),
            "ready_for_goc_planner": True,
            "future_capabilities": [
                "task_interpretation",
                "team_plan_generation",
                "skill_attachment_decisions",
                "context_pack_assembly",
            ],
        }


def build_planning_boundary_projection(
    *,
    run_id: str | None,
    runtime_authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provider: PlanningBoundaryProvider = RuntimePlanningBoundary()
    return provider.project(run_id=run_id, runtime_authority=runtime_authority)
