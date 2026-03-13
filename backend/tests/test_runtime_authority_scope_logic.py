from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlmodel import SQLModel, Session, create_engine

from app.models import ContextSet, Node, Thread
from app.services.run_skill_summary import (
    build_run_skill_summary,
    build_thread_context_pack_summary,
    build_thread_skill_usage_summary,
)
from app.services.run_studio import build_run_studio_agent_team, build_run_studio_summary
from app.services.runtime_authority import (
    derive_runtime_authority,
    extract_runtime_authority_from_container,
)
from app.services.runtime_scope import resolve_current_runtime_scope
from tests.runtime_contract_fixtures import standalone_runtime_contract_scenario


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
    payload: dict | None = None,
    created_at: datetime | None = None,
) -> FakeNode:
    return FakeNode(
        id=node_id,
        type=node_type,
        text="",
        payload_json=json.dumps(payload or {}),
        created_at=created_at or datetime.now(timezone.utc),
    )


class RuntimeAuthorityAndScopeTests(unittest.TestCase):
    def test_container_message_or_reason_only_does_not_mark_degraded(self) -> None:
        message_only = extract_runtime_authority_from_container({"message": "hello"})
        reason_only = extract_runtime_authority_from_container({"reason": "completed"})
        self.assertNotIn("fallback_reason", message_only)
        self.assertNotIn("fallback_reason", reason_only)
        self.assertNotIn("degraded_mode", message_only)
        self.assertNotIn("degraded_mode", reason_only)

    def test_nodes_with_normal_message_or_reason_fields_do_not_degrade(self) -> None:
        nodes = [
            make_node(
                "run-normal-message",
                "Run",
                payload={"message": "completed successfully"},
            ),
            make_node(
                "step-normal-reason",
                "Step",
                payload={"reason": "tool call finished"},
            ),
        ]
        authority = derive_runtime_authority(nodes=nodes, context_source_default="goc")
        self.assertFalse(bool(authority.get("degraded_mode")))
        self.assertIsNone(authority.get("fallback_reason"))

    def test_canonical_standalone_contract_ignores_normal_message_and_reason_fields(self) -> None:
        scenario = standalone_runtime_contract_scenario()
        run_payload = json.loads(scenario.nodes[0].payload_json)
        step_payload = json.loads(scenario.nodes[1].payload_json)
        run_payload["message"] = "runtime completed normally"
        step_payload["reason"] = "tool call finished"

        nodes = [
            make_node("run-standalone-contract", "Run", payload=run_payload, created_at=scenario.nodes[0].created_at),
            make_node("step-standalone-contract", "Step", payload=step_payload, created_at=scenario.nodes[1].created_at),
        ]
        authority = derive_runtime_authority(
            nodes=nodes,
            context_source_default="goc",
            plan_source_default="goc",
            mode_default="goc",
        )
        self.assertEqual(authority, scenario.authority)

    def test_explicit_fallback_and_degraded_fields_mark_degraded(self) -> None:
        fallback_reason = derive_runtime_authority(
            nodes=[make_node("run-fallback-reason", "Run", payload={"fallback_reason": "GoC unavailable"})],
        )
        degraded_reason = derive_runtime_authority(
            nodes=[make_node("run-degraded-reason", "Run", payload={"degraded_reason": "remote authority unavailable"})],
        )
        fallback_block = derive_runtime_authority(
            nodes=[make_node("run-fallback-block", "Run", payload={"fallback": {"reason": "timeout"}})],
        )
        degraded_block = derive_runtime_authority(
            nodes=[make_node("run-degraded-block", "Run", payload={"degraded": {"message": "switched to local mode"}})],
        )

        self.assertTrue(bool(fallback_reason.get("degraded_mode")))
        self.assertEqual(fallback_reason.get("fallback_reason"), "GoC unavailable")
        self.assertTrue(bool(degraded_reason.get("degraded_mode")))
        self.assertEqual(degraded_reason.get("fallback_reason"), "remote authority unavailable")
        self.assertTrue(bool(fallback_block.get("degraded_mode")))
        self.assertEqual(fallback_block.get("fallback_reason"), "timeout")
        self.assertTrue(bool(degraded_block.get("degraded_mode")))
        self.assertEqual(degraded_block.get("fallback_reason"), "switched to local mode")

    def test_runtime_authority_normalizes_modern_payload(self) -> None:
        nodes = [
            make_node(
                "run-modern",
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
                        "fallback_reason": "runtime disconnected from GoC authority endpoint",
                    }
                },
            )
        ]

        authority = derive_runtime_authority(nodes=nodes, context_source_default="goc")
        self.assertEqual(authority["mode"], "goc")
        self.assertEqual(authority["plan_source"], "local_fallback")
        self.assertEqual(authority["context_source"], "goc")
        self.assertEqual(authority["agent_catalog_source"], "goc")
        self.assertEqual(authority["conversation_team_source"], "local")
        self.assertEqual(authority["skill_catalog_source"], "mixed")
        self.assertTrue(bool(authority["degraded_mode"]))
        self.assertIn("disconnected", str(authority["fallback_reason"] or ""))

    def test_runtime_authority_handles_legacy_payload_fields(self) -> None:
        nodes = [
            make_node(
                "run-legacy",
                "Run",
                payload={
                    "goc_mode": "goc",
                    "planning_source": "local",
                    "context_authority": "goc",
                    "team_source": "local",
                    "skills_source": "runtime",
                    "fallback": {"reason": "temporary goc timeout"},
                },
            )
        ]

        authority = derive_runtime_authority(nodes=nodes, context_source_default="goc")
        self.assertEqual(authority["mode"], "goc")
        self.assertEqual(authority["plan_source"], "local")
        self.assertEqual(authority["context_source"], "goc")
        self.assertEqual(authority["conversation_team_source"], "local")
        self.assertEqual(authority["skill_catalog_source"], "local")
        self.assertTrue(bool(authority["degraded_mode"]))
        self.assertIn("timeout", str(authority["fallback_reason"] or ""))

    def test_shared_current_run_resolution_applies_to_skill_and_context_summaries(self) -> None:
        base = datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node("run-old", "Run", payload={"status": "queued"}, created_at=base),
            make_node(
                "step-old",
                "Step",
                payload={
                    "run_id": "run-old",
                    "status": "queued",
                    "skill_usage_events": [{"skill_id": "skill.legacy.v1", "event_type": "used"}],
                },
                created_at=base + timedelta(seconds=1),
            ),
            make_node("run-new", "Run", payload={"status": "done"}, created_at=base + timedelta(seconds=10)),
            make_node(
                "step-new",
                "Step",
                payload={
                    "run_id": "run-new",
                    "status": "done",
                    "skill_usage_events": [{"skill_id": "skill.current.v1", "event_type": "used"}],
                },
                created_at=base + timedelta(seconds=11),
            ),
        ]

        scope = resolve_current_runtime_scope(nodes, [])
        self.assertEqual(scope.get("current_run_id"), "run-new")
        self.assertEqual(int(scope.get("stale_queued_step_count") or 0), 1)

        run_summary = build_run_skill_summary(nodes=nodes, edges=[])
        context_pack_summary = build_thread_context_pack_summary(nodes=nodes, edges=[])
        skill_usage_summary = build_thread_skill_usage_summary(nodes=nodes, edges=[])

        self.assertEqual(run_summary.get("run_id"), "run-new")
        self.assertEqual(context_pack_summary.get("run_id"), "run-new")
        self.assertEqual(skill_usage_summary.get("run_id"), "run-new")
        self.assertEqual(skill_usage_summary.get("count"), 1)
        self.assertEqual((skill_usage_summary.get("items") or [])[0].get("skill_id"), "skill.current.v1")

    def test_run_studio_summary_exposes_degraded_authority(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        base = datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc)

        with Session(engine) as session:
            thread = Thread(id="thread-authority", service_id="svc", title="Authority Test")
            context_set = ContextSet(
                id="ctx-authority",
                thread_id=thread.id,
                name="default",
                active_node_ids_json="[]",
            )
            run_node = Node(
                id="run-authority",
                thread_id=thread.id,
                type="Run",
                text="",
                payload_json=json.dumps(
                    {
                        "runtime_authority": {
                            "mode": "goc",
                            "plan_source": "local_fallback",
                            "context_source": "goc",
                            "agent_catalog_source": "goc",
                            "conversation_team_source": "local",
                            "skill_catalog_source": "mixed",
                            "degraded_mode": True,
                            "fallback_reason": "planner service unavailable",
                        },
                        "runtime_team_snapshot": {
                            "runtime_agents": [{"runtime_instance_id": "rt-1", "role_label": "Planner"}]
                        },
                    }
                ),
                created_at=base,
            )
            step_node = Node(
                id="step-authority",
                thread_id=thread.id,
                type="Step",
                text="",
                payload_json=json.dumps({"run_id": "run-authority", "status": "running"}),
                created_at=base + timedelta(seconds=1),
            )

            session.add(thread)
            session.add(context_set)
            session.add(run_node)
            session.add(step_node)
            session.commit()

            summary = build_run_studio_summary(session, thread=thread, context_set_id=context_set.id)
            team_detail = build_run_studio_agent_team(session, thread=thread)

            authority = summary.get("runtime_authority") or {}
            self.assertEqual(authority.get("mode"), "goc")
            self.assertEqual(authority.get("plan_source"), "local_fallback")
            self.assertTrue(bool(authority.get("degraded_mode")))
            self.assertIn("unavailable", str(authority.get("fallback_reason") or ""))

            now_state = (summary.get("now") or {}).get("state") or {}
            self.assertTrue(bool(now_state.get("degraded_mode")))
            self.assertEqual(now_state.get("plan_source"), "local_fallback")

            current_run_skills = summary.get("current_run_skills") or {}
            self.assertTrue(bool(current_run_skills.get("degraded_mode")))
            self.assertEqual(current_run_skills.get("mode"), "goc")

            self.assertEqual(team_detail.get("mode"), "goc")
            self.assertTrue(bool(team_detail.get("degraded_mode")))


if __name__ == "__main__":
    unittest.main()
