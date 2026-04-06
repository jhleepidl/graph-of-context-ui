from __future__ import annotations

import unittest

from sqlmodel import SQLModel, Session
from tests.db_test_utils import create_test_engine as create_engine

from app.services.resolved_runtime import resolve_runtime_projection
from app.services.run_skill_summary import (
    build_run_skill_summary,
    build_thread_context_pack_summary,
    build_thread_skill_usage_summary,
)
from app.services.run_studio import build_run_studio_agent_team, build_run_studio_summary
from app.services.runtime_authority import derive_runtime_authority
from tests.runtime_contract_fixtures import (
    canonical_runtime_authority,
    degraded_local_fallback_runtime_contract_scenario,
    goc_runtime_contract_scenario,
    make_fixture_node,
    mixed_skill_authority_runtime_contract_scenario,
    standalone_runtime_contract_scenario,
)
from app.models import ContextSet, Node, Thread


class RuntimeContractRoundtripTests(unittest.TestCase):
    def assert_authority_projection(self, payload: dict, expected: dict) -> None:
        self.assertEqual(payload.get("runtime_authority"), expected)
        for field, value in expected.items():
            self.assertEqual(payload.get(field), value)

    def assert_run_studio_authority(self, summary: dict, expected: dict) -> None:
        self.assert_authority_projection(summary, expected)
        self.assert_authority_projection((summary.get("now") or {}).get("state") or {}, expected)
        self.assert_authority_projection((summary.get("now") or {}).get("current_run") or {}, expected)
        self.assert_authority_projection(summary.get("agent_team") or {}, expected)
        self.assert_authority_projection(summary.get("current_run_skills") or {}, expected)
        self.assertEqual((summary.get("planning_boundary") or {}).get("plan_source"), expected.get("plan_source"))
        self.assertEqual((summary.get("planning_boundary") or {}).get("mode"), expected.get("mode"))
        self.assertEqual((summary.get("planning_boundary") or {}).get("degraded_mode"), expected.get("degraded_mode"))
        self.assertEqual((summary.get("planning_boundary") or {}).get("fallback_reason"), expected.get("fallback_reason"))
        self.assertTrue(bool((summary.get("planning_boundary") or {}).get("ready_for_goc_control_plane")))
        self.assertIn("stages", summary.get("planning_boundary") or {})

    def test_standalone_contract_roundtrip_projects_consistently(self) -> None:
        scenario = standalone_runtime_contract_scenario()
        expected = scenario.authority

        projection = resolve_runtime_projection(
            nodes=scenario.nodes,
            edges=[],
            context_source_default="goc",
            plan_source_default="goc",
            mode_default="goc",
        )
        self.assertEqual(projection.authority, expected)
        self.assert_authority_projection(projection.capability_payload(), expected)
        self.assert_authority_projection(projection.context_pack_payload(), expected)
        self.assert_authority_projection(projection.skill_usage_payload(), expected)

        self.assert_authority_projection(build_run_skill_summary(nodes=scenario.nodes, edges=[]), expected)
        self.assert_authority_projection(build_thread_context_pack_summary(nodes=scenario.nodes, edges=[]), expected)
        self.assert_authority_projection(build_thread_skill_usage_summary(nodes=scenario.nodes, edges=[]), expected)

        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            thread, context_set = scenario.seed_run_studio(session)
            summary = build_run_studio_summary(session, thread=thread, context_set_id=context_set.id)
            team_detail = build_run_studio_agent_team(session, thread=thread)

        self.assert_run_studio_authority(summary, expected)
        self.assert_authority_projection(team_detail, expected)
        self.assertEqual((summary.get("agent_team") or {}).get("items", [])[0].get("source"), "runtime_snapshot")
        self.assertFalse(bool(summary.get("degraded_mode")))

    def test_goc_contract_roundtrip_projects_consistently(self) -> None:
        scenario = goc_runtime_contract_scenario()
        expected = scenario.authority

        projection = resolve_runtime_projection(nodes=scenario.nodes, edges=[])
        self.assertEqual(projection.authority, expected)
        self.assert_authority_projection(projection.capability_payload(), expected)

        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            thread, context_set = scenario.seed_run_studio(session)
            summary = build_run_studio_summary(session, thread=thread, context_set_id=context_set.id)
            team_detail = build_run_studio_agent_team(session, thread=thread)

        self.assert_run_studio_authority(summary, expected)
        self.assert_authority_projection(team_detail, expected)
        self.assertEqual((summary.get("agent_team") or {}).get("items", [])[0].get("source"), "conversation_membership")
        self.assertEqual((summary.get("agent_team") or {}).get("conversation_team_source"), "goc")
        self.assertEqual((summary.get("agent_team") or {}).get("agent_catalog_source"), "goc")
        self.assertFalse(bool(summary.get("degraded_mode")))

    def test_local_fallback_contract_roundtrip_projects_consistently(self) -> None:
        scenario = degraded_local_fallback_runtime_contract_scenario()
        expected = scenario.authority

        projection = resolve_runtime_projection(nodes=scenario.nodes, edges=[])
        capability_summary = projection.capability_payload()
        context_pack_summary = projection.context_pack_payload()
        skill_usage_summary = projection.skill_usage_payload()
        self.assert_authority_projection(capability_summary, expected)
        self.assert_authority_projection(context_pack_summary, expected)
        self.assert_authority_projection(skill_usage_summary, expected)
        self.assertGreaterEqual(len(capability_summary.get("skill_packages") or []), 2)
        skill_sources = {str(item.get("source") or "") for item in capability_summary.get("skill_packages") or []}
        self.assertTrue(any(source.startswith("default_registry") for source in skill_sources))
        self.assertTrue(any(source and not source.startswith("default_registry") for source in skill_sources))

        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            thread, context_set = scenario.seed_run_studio(session)
            summary = build_run_studio_summary(session, thread=thread, context_set_id=context_set.id)
            team_detail = build_run_studio_agent_team(session, thread=thread)

        self.assert_run_studio_authority(summary, expected)
        self.assert_authority_projection(team_detail, expected)
        self.assertEqual((summary.get("agent_team") or {}).get("items", [])[0].get("source"), "conversation_membership")
        self.assertTrue(bool((summary.get("now") or {}).get("state", {}).get("degraded_mode")))
        self.assertEqual((summary.get("planning_boundary") or {}).get("plan_source"), "local_fallback")
        self.assertEqual((summary.get("planning_boundary") or {}).get("fallback_reason"), "planner service unavailable")

    def test_mixed_skill_contract_roundtrip_projects_consistently(self) -> None:
        scenario = mixed_skill_authority_runtime_contract_scenario()
        expected = scenario.authority

        summary = build_run_skill_summary(nodes=scenario.nodes, edges=[])
        self.assert_authority_projection(summary, expected)
        self.assertEqual(summary.get("skill_catalog_source"), "mixed")
        self.assertGreaterEqual(len(summary.get("skill_packages") or []), 2)

    def test_partial_canonical_contract_combines_safely_and_blocks_false_degraded(self) -> None:
        expected = canonical_runtime_authority(
            mode="goc",
            plan_source="goc",
            context_source="goc",
            agent_catalog_source="goc",
            conversation_team_source="local",
            skill_catalog_source="mixed",
            degraded_mode=False,
            fallback_reason=None,
        )
        nodes = [
            make_fixture_node(
                "run-partial-contract",
                "Run",
                payload={
                    "runtime_authority": {
                        "mode": "goc",
                        "plan_source": "goc",
                    },
                    "goc_mode": "standalone",
                    "fallback": {"reason": "legacy timeout"},
                    "message": "completed successfully",
                },
            ),
            make_fixture_node(
                "step-partial-contract",
                "Step",
                payload={
                    "run_id": "run-partial-contract",
                    "status": "running",
                    "runtime_authority": {
                        "context_source": "goc",
                        "agent_catalog_source": "goc",
                        "conversation_team_source": "local",
                        "skill_catalog_source": "mixed",
                        "degraded_mode": False,
                        "fallback_reason": None,
                    },
                    "team_source": "goc",
                    "reason": "tool call finished",
                },
            ),
        ]

        authority = derive_runtime_authority(
            nodes=nodes,
            context_source_default="local",
            plan_source_default="local",
            mode_default="standalone",
        )
        self.assertEqual(authority, expected)

        projection = resolve_runtime_projection(
            nodes=nodes,
            edges=[],
            context_source_default="local",
            plan_source_default="local",
            mode_default="standalone",
        )
        self.assertEqual(projection.authority, expected)
        self.assertFalse(bool(projection.capability_payload().get("degraded_mode")))

    def test_canonical_contract_precedes_legacy_sibling_and_later_legacy_step_fields(self) -> None:
        expected = canonical_runtime_authority(
            mode="standalone",
            plan_source="local",
            context_source="local",
            agent_catalog_source="local",
            conversation_team_source="local",
            skill_catalog_source="local",
            degraded_mode=False,
            fallback_reason=None,
        )
        nodes = [
            make_fixture_node(
                "run-canonical-precedence",
                "Run",
                payload={
                    "runtime_authority": expected,
                    "goc_mode": "goc",
                    "planning_source": "local_fallback",
                    "context_authority": "goc",
                    "fallback": {"reason": "legacy should not win"},
                },
            ),
            make_fixture_node(
                "step-canonical-precedence",
                "Step",
                payload={
                    "run_id": "run-canonical-precedence",
                    "status": "running",
                    "team_source": "goc",
                    "skills_source": "goc",
                    "degraded": {"message": "legacy degraded should not win"},
                },
            ),
        ]

        authority = derive_runtime_authority(nodes=nodes, context_source_default="goc")
        self.assertEqual(authority, expected)

    def test_actual_ddalggak_v2_payload_roundtrips_through_runtime_and_run_studio(self) -> None:
        authority = canonical_runtime_authority(
            mode="goc",
            plan_source="goc",
            context_source="goc",
            agent_catalog_source="goc",
            conversation_team_source="local",
            skill_catalog_source="mixed",
        )
        nodes = [
            make_fixture_node(
                "run-ddalggak-v2",
                "Run",
                payload={
                    "runtime_authority": authority,
                    "runtime_team_snapshot": {
                        "team_plan": {
                            "mode": "parallel",
                            "supervisor_runtime": {
                                "interaction_mode": "interrupt_on_completion",
                                "instance_id": "sup-1",
                                "enabled": True,
                            },
                            "slots": [
                                {"slot_id": "slot-1", "role_id": "role-1", "display_label": "Analyst"},
                            ],
                        },
                        "runtime_agents": [
                            {
                                "instance_id": "rt-1",
                                "slot_id": "slot-1",
                                "role_id": "role-1",
                                "display_label": "Analyst",
                                "authority_profile_id": "authority.read_only",
                            }
                        ],
                        "collaboration_cells": [
                            {
                                "cell_id": "cell-1",
                                "pattern": "reflection",
                                "member_instance_ids": ["rt-1"],
                                "topology": "self_loop",
                                "max_rounds": 2,
                                "termination": {"condition": "confidence_reached"},
                            }
                        ],
                        "authority_graph": [
                            {
                                "authority_id": "auth-1",
                                "runtime_instance_id": "rt-1",
                                "authority_profile_id": "authority.read_only",
                                "allowed_actions": ["research"],
                                "denied_actions": ["publish"],
                                "approval_required_for": ["publish"],
                            }
                        ],
                        "checkpoints": [
                            {
                                "checkpoint_id": "checkpoint-1",
                                "kind": "approval",
                                "human_interrupt_allowed": True,
                                "approval_required": True,
                                "trigger_after_instances": ["rt-1"],
                                "supervisor_decision": {"mode": "await_user", "condition": "research_reports_ready"},
                                "completion_signal": {"signal": "final_answer_ready"},
                            }
                        ],
                        "execution_graph": {
                            "parallel_groups": [{"group_id": "group-1", "member_instance_ids": ["rt-1"]}],
                            "supervisor_edges": [{"from": "sup-1", "to": "rt-1"}],
                        },
                    },
                },
            ),
            make_fixture_node(
                "step-ddalggak-v2",
                "Step",
                payload={"run_id": "run-ddalggak-v2", "status": "running", "agent_id": "rt-1"},
            ),
        ]

        projection = resolve_runtime_projection(nodes=nodes, edges=[])
        capability = projection.capability_payload()
        self.assertEqual((capability.get("collaboration") or {}).get("items", [])[0].get("kind"), "reflection")
        self.assertEqual((capability.get("collaboration") or {}).get("items", [])[0].get("termination"), {"condition": "confidence_reached"})
        self.assertEqual((capability.get("collaboration") or {}).get("items", [])[0].get("termination_summary"), "condition: confidence_reached")
        self.assertEqual((capability.get("orchestration") or {}).get("supervisor_mode"), "interrupt_on_completion")
        self.assertEqual((capability.get("orchestration") or {}).get("parallel_groups", [])[0].get("member_labels"), ["Analyst"])
        self.assertEqual((capability.get("checkpoints") or {}).get("items", [])[0].get("human_interrupt_allowed"), True)
        self.assertEqual((capability.get("checkpoints") or {}).get("items", [])[0].get("supervisor_decision"), {"mode": "await_user", "condition": "research_reports_ready"})
        self.assertEqual((capability.get("checkpoints") or {}).get("items", [])[0].get("supervisor_decision_summary"), "condition: research_reports_ready | mode: await_user")
        self.assertEqual((capability.get("checkpoints") or {}).get("items", [])[0].get("completion_signal_summary"), "signal: final_answer_ready")
        self.assertIn("publish", (capability.get("authority") or {}).get("items", [])[0].get("denied_actions") or [])

        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            thread = Thread(id="thread-ddalggak-v2", service_id="svc", title="ddalggak v2")
            context_set = ContextSet(id="ctx-ddalggak-v2", thread_id=thread.id, name="default", active_node_ids_json="[]")
            session.add(thread)
            session.add(context_set)
            session.flush()
            for raw in nodes:
                session.add(
                    Node(
                        id=raw.id,
                        thread_id=thread.id,
                        type=raw.type,
                        text=raw.text,
                        payload_json=raw.payload_json,
                        created_at=raw.created_at,
                    )
                )
            session.commit()
            summary = build_run_studio_summary(session, thread=thread, context_set_id=context_set.id)

        self.assertEqual((summary.get("collaboration") or {}).get("items", [])[0].get("kind"), "reflection")
        self.assertEqual((summary.get("collaboration") or {}).get("items", [])[0].get("termination"), {"condition": "confidence_reached"})
        self.assertEqual((summary.get("orchestration") or {}).get("supervisor_mode"), "interrupt_on_completion")
        self.assertEqual((summary.get("orchestration") or {}).get("parallel_groups", [])[0].get("member_labels"), ["Analyst"])
        self.assertEqual((summary.get("checkpoints") or {}).get("items", [])[0].get("human_interrupt_allowed"), True)
        self.assertEqual((summary.get("checkpoints") or {}).get("items", [])[0].get("completion_signal_summary"), "signal: final_answer_ready")
        self.assertIn("publish", (summary.get("authority") or {}).get("items", [])[0].get("denied_actions") or [])


if __name__ == "__main__":
    unittest.main()
