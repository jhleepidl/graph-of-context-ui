from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlmodel import SQLModel, Session, create_engine

from app.services.conversation_team import build_conversation_team_projection
from app.services.resolved_runtime import resolve_conversation_team, resolve_runtime_projection
from app.services.run_skill_summary import (
    build_run_skill_summary,
    build_thread_context_pack_summary,
    build_thread_skill_usage_summary,
)


@dataclass
class FakeNode:
    id: str
    type: str
    text: str
    payload_json: str
    created_at: datetime


def make_node(
    node_id: str,
    node_type: str,
    *,
    text: str = "",
    payload: dict | None = None,
    created_at: datetime | None = None,
) -> FakeNode:
    return FakeNode(
        id=node_id,
        type=node_type,
        text=text,
        payload_json=json.dumps(payload or {}),
        created_at=created_at or datetime.now(timezone.utc),
    )


def _stable_payload(payload: dict) -> dict:
    out = dict(payload)
    out.pop("updated_at", None)
    return out


class ResolvedRuntimeLogicTests(unittest.TestCase):
    def test_resolved_runtime_projection_aligns_capability_slices(self) -> None:
        base = datetime(2026, 3, 12, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node("run-old", "Run", payload={"status": "queued"}, created_at=base),
            make_node(
                "step-old",
                "Step",
                payload={
                    "run_id": "run-old",
                    "status": "queued",
                    "skill_usage_events": [{"skill_id": "skill.legacy.runtime.v1", "event_type": "used"}],
                },
                created_at=base + timedelta(seconds=1),
            ),
            make_node(
                "run-current",
                "Run",
                payload={
                    "runtime_authority": {
                        "mode": "goc",
                        "plan_source": "local_fallback",
                        "context_source": "goc",
                        "agent_catalog_source": "goc",
                        "conversation_team_source": "local",
                        "skill_catalog_source": "mixed",
                        "degraded_mode": True,
                        "fallback_reason": "planner temporarily unavailable",
                    },
                    "runtime_team_snapshot": {
                        "runtime_agents": [
                            {
                                "runtime_instance_id": "rt-1",
                                "role_label": "Analyst",
                                "attached_skills": [
                                    {
                                        "skill_id": "skill.claim_evidence_audit.v1",
                                        "load_level": "instructions",
                                        "selected_by": "runtime",
                                    }
                                ],
                                "context_pack_id": "cp-1",
                            }
                        ]
                    },
                    "context_packs": [
                        {
                            "context_pack_id": "cp-1",
                            "scope": "runtime",
                            "target_runtime_agent_instance_id": "rt-1",
                            "shared_items_count": 2,
                            "role_specific_items_count": 1,
                            "skill_items": [
                                {
                                    "skill_id": "skill.claim_evidence_audit.v1",
                                    "load_level": "instructions",
                                    "count": 2,
                                }
                            ],
                        }
                    ],
                },
                created_at=base + timedelta(seconds=10),
            ),
            make_node(
                "step-current",
                "Step",
                payload={
                    "run_id": "run-current",
                    "status": "running",
                    "agent_id": "rt-1",
                    "skill_usage_events": [{"skill_id": "skill.claim_evidence_audit.v1", "event_type": "used"}],
                },
                created_at=base + timedelta(seconds=11),
            ),
        ]

        projection = resolve_runtime_projection(
            nodes=nodes,
            edges=[],
            context_source_default="goc",
            plan_source_default="local",
            mode_default="goc",
        )
        capability_summary = projection.capability_payload()
        context_pack_summary = projection.context_pack_payload()
        skill_usage_summary = projection.skill_usage_payload()

        self.assertEqual(projection.run_id, "run-current")
        self.assertEqual(capability_summary.get("run_id"), "run-current")
        self.assertEqual(context_pack_summary.get("run_id"), "run-current")
        self.assertEqual(skill_usage_summary.get("run_id"), "run-current")
        self.assertEqual(context_pack_summary.get("count"), 1)
        self.assertEqual(skill_usage_summary.get("count"), 1)
        self.assertEqual((skill_usage_summary.get("items") or [])[0].get("skill_id"), "skill.claim_evidence_audit.v1")
        self.assertEqual(
            capability_summary.get("runtime_authority"),
            context_pack_summary.get("runtime_authority"),
        )
        self.assertEqual(
            capability_summary.get("runtime_authority"),
            skill_usage_summary.get("runtime_authority"),
        )
        self.assertEqual(
            capability_summary.get("planning_boundary"),
            context_pack_summary.get("planning_boundary"),
        )
        self.assertEqual(
            capability_summary.get("planning_boundary"),
            skill_usage_summary.get("planning_boundary"),
        )
        self.assertTrue(bool(capability_summary.get("degraded_mode")))
        self.assertEqual(capability_summary.get("fallback_reason"), "planner temporarily unavailable")

        direct_capability_summary = build_run_skill_summary(nodes=nodes, edges=[])
        direct_context_pack_summary = build_thread_context_pack_summary(nodes=nodes, edges=[])
        direct_skill_usage_summary = build_thread_skill_usage_summary(nodes=nodes, edges=[])
        self.assertEqual(
            _stable_payload(capability_summary),
            _stable_payload(direct_capability_summary),
        )
        self.assertEqual(
            _stable_payload(context_pack_summary),
            _stable_payload(direct_context_pack_summary),
        )
        self.assertEqual(
            _stable_payload(skill_usage_summary),
            _stable_payload(direct_skill_usage_summary),
        )

    def test_resolved_runtime_projection_preserves_authority_normalization(self) -> None:
        clean_projection = resolve_runtime_projection(
            nodes=[
                make_node("run-clean", "Run", payload={"message": "completed successfully"}),
                make_node("step-clean", "Step", payload={"reason": "tool finished"}),
            ],
            edges=[],
            context_source_default="goc",
        )
        clean_summary = clean_projection.capability_payload()
        self.assertFalse(bool(clean_summary.get("degraded_mode")))
        self.assertIsNone(clean_summary.get("fallback_reason"))

        degraded_projection = resolve_runtime_projection(
            nodes=[
                make_node("run-degraded", "Run", payload={"degraded": {"message": "switched to local mode"}}),
            ],
            edges=[],
            context_source_default="goc",
        )
        degraded_summary = degraded_projection.capability_payload()
        self.assertTrue(bool(degraded_summary.get("degraded_mode")))
        self.assertEqual(degraded_summary.get("fallback_reason"), "switched to local mode")

    def test_conversation_team_service_matches_resolved_runtime_team(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        base = datetime(2026, 3, 12, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node(
                "run-team",
                "Run",
                payload={
                    "runtime_team_snapshot": {
                        "runtime_agents": [
                            {
                                "runtime_instance_id": "rt-team-1",
                                "role_label": "Planner",
                                "status": "running",
                                "ephemeral": True,
                                "attached_skills": [{"skill_id": "skill.claim_evidence_audit.v1"}],
                            }
                        ]
                    }
                },
                created_at=base,
            ),
            make_node(
                "step-team",
                "Step",
                payload={"run_id": "run-team", "status": "running", "agent_id": "rt-team-1"},
                created_at=base + timedelta(seconds=1),
            ),
        ]

        with Session(engine) as session:
            resolved_payload = resolve_conversation_team(
                session,
                thread_id="thread-team",
                nodes=nodes,
            ).as_payload()
            service_payload = build_conversation_team_projection(
                session,
                thread_id="thread-team",
                nodes=nodes,
            )

        self.assertEqual(_stable_payload(resolved_payload), _stable_payload(service_payload))


if __name__ == "__main__":
    unittest.main()
