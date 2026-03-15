from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.services.resolved_runtime import resolve_runtime_projection


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


class StructuredRuntimeFieldsProjectionTests(unittest.TestCase):
    def test_structured_runtime_fields_are_preserved_with_summaries(self) -> None:
        base = datetime(2026, 3, 16, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node(
                "run-structured",
                "Run",
                payload={
                    "runtime_team_snapshot": {
                        "team_plan": {
                            "mode": "parallel",
                            "slots": [
                                {"slot_id": "slot-1", "role_id": "role-1", "display_label": "Analyst"},
                                {"slot_id": "slot-2", "role_id": "role-2", "display_label": "Reviewer"},
                            ],
                            "supervisor_runtime": {
                                "interaction_mode": "interrupt_on_completion",
                                "instance_id": "sup-1",
                                "enabled": True,
                            },
                        },
                        "runtime_agents": [
                            {"instance_id": "rt-1", "slot_id": "slot-1", "role_id": "role-1", "display_label": "Analyst"},
                            {"instance_id": "rt-2", "slot_id": "slot-2", "role_id": "role-2", "display_label": "Reviewer"},
                        ],
                        "collaboration_cells": [
                            {
                                "cell_id": "cell-1",
                                "pattern": "debate",
                                "member_instance_ids": ["rt-1", "rt-2"],
                                "topology": "pairwise",
                                "max_rounds": 3,
                                "termination": {"condition": "research_reports_ready", "min_reports": 2},
                            }
                        ],
                        "checkpoints": [
                            {
                                "checkpoint_id": "checkpoint-1",
                                "kind": "approval",
                                "human_interrupt_allowed": True,
                                "approval_required": True,
                                "trigger_after_instances": ["rt-1"],
                                "supervisor_decision": {"mode": "await_user", "condition": "final_review_ready"},
                                "completion_signal": {"signal": "final_answer_ready"},
                            }
                        ],
                        "execution_graph": {
                            "parallel_groups": [
                                {"group_id": "group-1", "member_instance_ids": ["rt-1", "rt-2"]}
                            ],
                            "supervisor_edges": [{"from": "sup-1", "to": "rt-2"}],
                        },
                    }
                },
                created_at=base,
            ),
            make_node(
                "step-structured",
                "Step",
                payload={"run_id": "run-structured", "status": "running", "agent_id": "rt-1"},
                created_at=base + timedelta(seconds=1),
            ),
        ]

        payload = resolve_runtime_projection(nodes=nodes, edges=[]).capability_payload()

        collaboration_item = (payload.get("collaboration") or {}).get("items", [])[0]
        checkpoint_item = (payload.get("checkpoints") or {}).get("items", [])[0]
        orchestration = payload.get("orchestration") or {}

        self.assertEqual(collaboration_item.get("termination"), {"condition": "research_reports_ready", "min_reports": 2})
        self.assertEqual(collaboration_item.get("termination_summary"), "condition: research_reports_ready")
        self.assertNotIn("{'", str(collaboration_item.get("termination_summary") or ""))
        self.assertEqual(checkpoint_item.get("supervisor_decision"), {"mode": "await_user", "condition": "final_review_ready"})
        self.assertEqual(checkpoint_item.get("supervisor_decision_summary"), "condition: final_review_ready | mode: await_user")
        self.assertEqual(checkpoint_item.get("completion_signal"), {"signal": "final_answer_ready"})
        self.assertEqual(checkpoint_item.get("completion_signal_summary"), "signal: final_answer_ready")
        self.assertEqual(checkpoint_item.get("trigger_after_labels"), ["Analyst"])
        self.assertEqual((orchestration.get("parallel_groups") or [])[0].get("member_labels"), ["Analyst", "Reviewer"])
        self.assertEqual((orchestration.get("supervisor_edges") or [])[0].get("edge_summary"), "sup-1 -> Reviewer")

    def test_string_only_runtime_fields_still_project_cleanly(self) -> None:
        base = datetime(2026, 3, 16, 1, 0, tzinfo=timezone.utc)
        nodes = [
            make_node(
                "run-strings",
                "Run",
                payload={
                    "runtime_team_snapshot": {
                        "team_plan": {
                            "supervisor_runtime": {"interaction_mode": "report_back", "instance_id": "sup-strings"},
                            "slots": [{"slot_id": "slot-1", "role_id": "role-1", "display_label": "Analyst"}],
                        },
                        "runtime_agents": [
                            {"instance_id": "rt-strings", "slot_id": "slot-1", "role_id": "role-1", "display_label": "Analyst"},
                        ],
                        "collaboration_cells": [
                            {
                                "cell_id": "cell-strings",
                                "pattern": "reflection",
                                "member_instance_ids": ["rt-strings"],
                                "termination": "confidence_reached",
                            }
                        ],
                        "checkpoints": [
                            {
                                "checkpoint_id": "checkpoint-strings",
                                "kind": "approval",
                                "human_interrupt_allowed": True,
                                "supervisor_decision": "await_user",
                                "completion_signal": "final_answer_ready",
                            }
                        ],
                        "execution_graph": {"parallel_groups": [["rt-strings"]]},
                    }
                },
                created_at=base,
            ),
            make_node(
                "step-strings",
                "Step",
                payload={"run_id": "run-strings", "status": "running", "agent_id": "rt-strings"},
                created_at=base + timedelta(seconds=1),
            ),
        ]

        payload = resolve_runtime_projection(nodes=nodes, edges=[]).capability_payload()
        collaboration_item = (payload.get("collaboration") or {}).get("items", [])[0]
        checkpoint_item = (payload.get("checkpoints") or {}).get("items", [])[0]

        self.assertEqual(collaboration_item.get("termination"), "confidence_reached")
        self.assertEqual(collaboration_item.get("termination_summary"), "confidence_reached")
        self.assertEqual(checkpoint_item.get("supervisor_decision"), "await_user")
        self.assertEqual(checkpoint_item.get("supervisor_decision_summary"), "await_user")
        self.assertEqual(checkpoint_item.get("completion_signal"), "final_answer_ready")
        self.assertEqual(checkpoint_item.get("completion_signal_summary"), "final_answer_ready")


if __name__ == "__main__":
    unittest.main()
