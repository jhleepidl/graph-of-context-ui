from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.services.resolved_runtime import resolve_runtime_projection
from app.services.run_skill_summary import (
    build_thread_context_pack_summary,
    build_thread_skill_usage_summary,
)


FIXTURE = json.loads(
    Path(__file__).with_name("runtime_contract_golden_fixture.json").read_text()
)


def _node(node_id: str, node_type: str, payload: dict, *, created_at: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=node_id,
        type=node_type,
        text=node_id,
        payload_json=json.dumps(payload),
        created_at=created_at,
    )


def _sorted_strings(values: list[str]) -> list[str]:
    return sorted(str(value or "") for value in values)


class RuntimeContractGoldenFixtureTests(unittest.TestCase):
    def test_ddalggak_runtime_contract_fixture_projects_without_drift(self) -> None:
        for scenario in FIXTURE.get("scenarios") or []:
            with self.subTest(scenario=scenario.get("name")):
                nodes = [
                    _node(
                        scenario["run_id"],
                        "Run",
                        scenario["run_payload"],
                        created_at="2026-03-14T00:00:00Z",
                    ),
                    _node(
                        f"step-{scenario['name']}",
                        "Step",
                        scenario["step_payload"],
                        created_at="2026-03-14T00:00:01Z",
                    ),
                ]

                projection = resolve_runtime_projection(
                    nodes=nodes,
                    edges=[],
                    run_id=scenario["run_id"],
                    include_conversation_team=False,
                    context_source_default="goc",
                    plan_source_default="local",
                )
                capability_payload = projection.capability_payload()
                context_pack_payload = build_thread_context_pack_summary(
                    nodes=nodes,
                    edges=[],
                    run_id=scenario["run_id"],
                )
                skill_usage_payload = build_thread_skill_usage_summary(
                    nodes=nodes,
                    edges=[],
                    run_id=scenario["run_id"],
                )

                expected = scenario["expected"]
                self.assertEqual(projection.authority, scenario["authority"])
                self.assertEqual(capability_payload.get("runtime_authority"), scenario["authority"])
                self.assertEqual(capability_payload.get("action_source"), scenario["action_source"])
                self.assertEqual(capability_payload.get("plan_source"), expected["plan_source"])
                self.assertEqual(capability_payload.get("degraded_mode"), expected["degraded_mode"])

                counts = capability_payload.get("counts") or {}
                self.assertEqual(counts.get("runtime_agents"), expected["counts"]["runtime_agents"])
                self.assertEqual(counts.get("attached_skills"), expected["counts"]["attached_skills"])
                self.assertEqual(counts.get("context_packs"), expected["counts"]["context_packs"])
                self.assertEqual(counts.get("skill_usage"), expected["counts"]["skill_usage"])
                self.assertEqual(counts.get("collaboration"), expected["counts"]["collaboration"])
                self.assertEqual(counts.get("checkpoints"), expected["counts"]["checkpoints"])

                self.assertEqual(
                    _sorted_strings([
                        item.get("runtime_instance_id") or item.get("instance_id")
                        for item in capability_payload.get("runtime_agents") or []
                    ]),
                    _sorted_strings(expected["runtime_agent_instance_ids"]),
                )
                self.assertEqual(
                    _sorted_strings([
                        item.get("skill_id")
                        for item in capability_payload.get("attached_skills") or []
                    ]),
                    _sorted_strings(expected["attached_skill_ids"]),
                )
                self.assertEqual(
                    _sorted_strings([
                        item.get("context_pack_id")
                        for item in capability_payload.get("context_packs") or []
                    ]),
                    _sorted_strings(expected["context_pack_ids"]),
                )
                self.assertEqual(
                    _sorted_strings([
                        item.get("skill_id")
                        for item in capability_payload.get("skill_usage") or []
                    ]),
                    _sorted_strings(expected["skill_usage_ids"]),
                )
                self.assertEqual(
                    _sorted_strings([
                        item.get("context_pack_id")
                        for item in context_pack_payload.get("items") or []
                    ]),
                    _sorted_strings(expected["context_pack_ids"]),
                )
                self.assertEqual(context_pack_payload.get("count"), expected["counts"]["context_packs"])
                self.assertEqual(
                    _sorted_strings([
                        item.get("skill_id")
                        for item in skill_usage_payload.get("items") or []
                    ]),
                    _sorted_strings(expected["skill_usage_ids"]),
                )
                self.assertEqual(skill_usage_payload.get("count"), expected["counts"]["skill_usage"])

                collaboration = capability_payload.get("collaboration") or {}
                self.assertEqual(
                    _sorted_strings([item.get("pattern") for item in collaboration.get("items") or []]),
                    _sorted_strings(expected["collaboration_patterns"]),
                )

                orchestration = capability_payload.get("orchestration") or {}
                if expected.get("supervisor_runtime_instance_id"):
                    supervisor_runtime = orchestration.get("supervisor_runtime") or {}
                    self.assertEqual(
                        supervisor_runtime.get("instance_id"),
                        expected["supervisor_runtime_instance_id"],
                    )
                if expected.get("interrupt_ready") is True:
                    self.assertEqual(
                        bool((orchestration.get("checkpoint_count") or 0) > 0),
                        True,
                    )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
