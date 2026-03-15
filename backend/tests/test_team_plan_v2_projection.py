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


class TeamPlanV2ProjectionTests(unittest.TestCase):
    def test_runtime_projection_surfaces_team_plan_v2_fields(self) -> None:
        base = datetime(2026, 3, 14, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node(
                "run-team-plan-v2",
                "Run",
                payload={
                    "runtime_team_snapshot": {
                        "task_interpretation": {"summary": "Research first, then challenge the result"},
                        "team_plan": {
                            "mode": "parallel",
                            "slots": [
                                {
                                    "slot_id": "slot-analyst",
                                    "role_id": "role-analyst",
                                    "display_label": "Analyst",
                                    "selection_reason": "Need structured research coverage",
                                    "preset_id": "preset.analyst",
                                },
                                {
                                    "slot_id": "slot-reviewer",
                                    "role_id": "role-reviewer",
                                    "display_label": "Reviewer",
                                    "selection_reason": "Need adversarial review",
                                },
                            ],
                            "supervisor_runtime": {"mode": "oversight", "instance_id": "sup-1"},
                        },
                        "runtime_agents": [
                            {
                                "instance_id": "rt-1",
                                "slot_id": "slot-analyst",
                                "role_id": "role-analyst",
                                "display_label": "Evidence Analyst",
                                "preset_id": "preset.analyst",
                                "selection_reason": "Preset analyst matches the task",
                                "attached_skill_ids": ["skill.claim_evidence_audit.v1"],
                                "context_pack_id": "cp-1",
                                "authority_profile_id": "authority.read_only",
                            },
                            {
                                "instance_id": "rt-2",
                                "slot_id": "slot-reviewer",
                                "role_id": "role-reviewer",
                                "display_label": "Skeptical Reviewer",
                                "synthesized": True,
                                "selection_reason": "Synthesized to create challenge pressure",
                                "attached_skill_ids": ["skill.context_selection_policy.v1"],
                                "authority_profile_id": "authority.review",
                            },
                        ],
                        "authority_graph": [
                            {
                                "authority_id": "auth-1",
                                "runtime_instance_id": "rt-1",
                                "authority_profile_id": "authority.read_only",
                                "allowed_actions": ["research"],
                                "restricted_actions": ["publish"],
                                "approval_required_for": ["publish"],
                            },
                            {
                                "authority_id": "auth-2",
                                "runtime_instance_id": "rt-2",
                                "authority_profile_id": "authority.review",
                                "allowed_actions": ["critique"],
                            },
                        ],
                        "checkpoints": [
                            {
                                "checkpoint_id": "checkpoint-1",
                                "kind": "approval",
                                "label": "Approve final answer",
                                "requires_approval": True,
                                "blocking": True,
                            }
                        ],
                        "execution_graph": {
                            "parallel_groups": [["rt-1", "rt-2"]],
                            "sequential_after": {"rt-2": ["rt-1"]},
                            "supervisor_edges": [{"from": "sup-1", "to": "rt-1"}],
                        },
                        "selection_explanations": [
                            {"slot_id": "slot-analyst", "text": "Preset analyst is best for retrieval"},
                            {"slot_id": "slot-reviewer", "text": "Synthesized reviewer improves quality control"},
                        ],
                        "conversation_preferences": {"tone": "concise"},
                    },
                    "context_packs": [
                        {
                            "context_pack_id": "cp-1",
                            "target_runtime_agent_instance_id": "rt-1",
                            "shared_items_count": 2,
                        }
                    ],
                },
                created_at=base,
            ),
            make_node(
                "step-team-plan-v2",
                "Step",
                payload={"run_id": "run-team-plan-v2", "status": "running", "agent_id": "rt-1"},
                created_at=base + timedelta(seconds=1),
            ),
        ]

        projection = resolve_runtime_projection(nodes=nodes, edges=[])
        payload = projection.capability_payload()

        self.assertEqual(payload.get("task_interpretation", {}).get("summary"), "Research first, then challenge the result")
        self.assertEqual(payload.get("team_view", {}).get("count"), 2)
        self.assertEqual((payload.get("team_view", {}).get("items") or [])[0].get("slot_id"), "slot-analyst")
        self.assertEqual(payload.get("why_this_team", {}).get("preset_count"), 1)
        self.assertEqual(payload.get("why_this_team", {}).get("synthesized_count"), 1)
        self.assertEqual(payload.get("why_this_team", {}).get("conversation_preferences", {}).get("tone"), "concise")
        self.assertEqual(payload.get("orchestration", {}).get("mode"), "parallel")
        self.assertEqual(payload.get("orchestration", {}).get("parallel_group_count"), 1)
        self.assertEqual(payload.get("orchestration", {}).get("sequential_after"), {"rt-2": ["rt-1"]})
        self.assertEqual(payload.get("authority", {}).get("graph_count"), 2)
        self.assertEqual((payload.get("authority", {}).get("items") or [])[0].get("authority_profile_id"), "authority.read_only")
        self.assertEqual((payload.get("checkpoints", {}).get("counts") or {}).get("approval_required"), 1)
        self.assertEqual((payload.get("planning_boundary", {}).get("stages") or [])[0].get("stage"), "task_interpretation")
        self.assertTrue(bool(payload.get("planning_boundary", {}).get("ready_for_goc_control_plane")))

    def test_runtime_projection_prefers_team_plan_v2_over_legacy_runtime_fields_in_mixed_payload(self) -> None:
        base = datetime(2026, 3, 14, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node(
                "run-mixed-runtime",
                "Run",
                payload={
                    "runtime_agents": [
                        {
                            "runtime_instance_id": "legacy-rt-1",
                            "role_label": "Legacy Worker",
                            "template_id": "legacy-template",
                        }
                    ],
                    "runtime_team_snapshot": {
                        "team_plan": {
                            "slots": [
                                {
                                    "slot_id": "slot-reviewer",
                                    "role_id": "role-reviewer",
                                    "display_label": "Reviewer",
                                    "selection_reason": "Need structured critique",
                                }
                            ],
                            "supervisor_runtime": {"mode": "oversight", "instance_id": "sup-mixed"},
                        },
                        "runtime_agents": [
                            {
                                "instance_id": "rt-mixed-1",
                                "slot_id": "slot-reviewer",
                                "role_id": "role-reviewer",
                                "display_label": "Structured Reviewer",
                                "synthesized": True,
                                "selection_reason": "Synthesized from critique requirement",
                            }
                        ],
                        "execution_graph": {
                            "parallel_groups": [["rt-mixed-1"]],
                            "supervisor_edges": [{"from": "sup-mixed", "to": "rt-mixed-1"}],
                        },
                    },
                },
                created_at=base,
            ),
            make_node(
                "step-mixed-runtime",
                "Step",
                payload={"run_id": "run-mixed-runtime", "status": "running", "agent_id": "rt-mixed-1"},
                created_at=base + timedelta(seconds=1),
            ),
        ]

        payload = resolve_runtime_projection(nodes=nodes, edges=[]).capability_payload()

        self.assertEqual((payload.get("team_view") or {}).get("count"), 1)
        item = (payload.get("team_view") or {}).get("items", [])[0]
        self.assertEqual(item.get("runtime_instance_id"), "rt-mixed-1")
        self.assertEqual(item.get("display_label"), "Structured Reviewer")
        self.assertTrue(bool(item.get("synthesized")))
        self.assertEqual((payload.get("orchestration") or {}).get("supervisor_mode"), "oversight")


if __name__ == "__main__":
    unittest.main()
