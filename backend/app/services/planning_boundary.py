from __future__ import annotations

from typing import Any, Protocol


class PlanningBoundaryProvider(Protocol):
    def project(
        self,
        *,
        run_id: str | None,
        runtime_authority: dict[str, Any] | None = None,
        runtime_snapshot: dict[str, Any] | None = None,
        capabilities: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


class RuntimePlanningBoundary:
    """Current planning boundary: runtime-managed orchestration, GoC control-plane ready."""

    def _stage_status(self, present: bool) -> str:
        return "ready" if present else "pending"

    def project(
        self,
        *,
        run_id: str | None,
        runtime_authority: dict[str, Any] | None = None,
        runtime_snapshot: dict[str, Any] | None = None,
        capabilities: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        authority = runtime_authority or {}
        snapshot = runtime_snapshot or {}
        capability_payload = capabilities or {}
        team_plan = snapshot.get("team_plan") or {}
        runtime_agents = list(capability_payload.get("runtime_agents") or [])
        attached_skills = list(capability_payload.get("attached_skills") or [])
        context_packs = list(capability_payload.get("context_packs") or [])
        execution_graph = snapshot.get("execution_graph") or {}

        plan_source = str(authority.get("plan_source") or "local")
        mode = str(authority.get("mode") or "standalone")
        degraded_mode = bool(authority.get("degraded_mode") or False)
        fallback_reason = authority.get("fallback_reason")
        managed_by = "runtime"
        if mode == "goc" and plan_source == "goc":
            managed_by = "goc_control_plane"
        elif plan_source == "local_fallback":
            managed_by = "runtime_fallback"

        stages = [
            {
                "stage": "task_interpretation",
                "status": self._stage_status(bool(snapshot.get("task_interpretation"))),
                "managed_by": managed_by,
            },
            {
                "stage": "team_building",
                "status": self._stage_status(bool(team_plan or runtime_agents)),
                "managed_by": managed_by,
            },
            {
                "stage": "preset_resolution",
                "status": self._stage_status(
                    any(str(item.get("preset_id") or "").strip() for item in runtime_agents)
                ),
                "managed_by": managed_by,
            },
            {
                "stage": "skill_resolution",
                "status": self._stage_status(bool(attached_skills)),
                "managed_by": managed_by,
            },
            {
                "stage": "context_pack_building",
                "status": self._stage_status(
                    bool(context_packs)
                    or any(str(item.get("context_pack_id") or "").strip() for item in runtime_agents)
                ),
                "managed_by": managed_by,
            },
            {
                "stage": "execution_coordination",
                "status": self._stage_status(
                    bool(execution_graph)
                    or bool(team_plan.get("supervisor_runtime"))
                    or bool(snapshot.get("collaboration_cells"))
                    or bool(snapshot.get("checkpoints"))
                ),
                "managed_by": managed_by,
            },
        ]
        return {
            "status": "runtime_managed",
            "managed_by": managed_by,
            "run_id": run_id,
            "plan_source": plan_source,
            "mode": mode,
            "degraded_mode": degraded_mode,
            "fallback_reason": fallback_reason,
            "stages": stages,
            "ready_for_goc_control_plane": True,
            "ready_for_goc_planner": True,
            "future_capabilities": [
                "task_interpretation",
                "team_building",
                "preset_resolution",
                "skill_resolution",
                "context_pack_building",
                "execution_coordination",
            ],
        }


def build_planning_boundary_projection(
    *,
    run_id: str | None,
    runtime_authority: dict[str, Any] | None = None,
    runtime_snapshot: dict[str, Any] | None = None,
    capabilities: dict[str, Any] | None = None,
) -> dict[str, Any]:
    provider: PlanningBoundaryProvider = RuntimePlanningBoundary()
    return provider.project(
        run_id=run_id,
        runtime_authority=runtime_authority,
        runtime_snapshot=runtime_snapshot,
        capabilities=capabilities,
    )
