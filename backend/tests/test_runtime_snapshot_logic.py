from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.services.runtime_snapshot import (
    extract_runtime_members_from_container,
    extract_runtime_team_snapshot,
    normalize_execution_feedback,
    normalize_runtime_source_key,
    normalize_status,
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


class RuntimeSnapshotHelperTests(unittest.TestCase):
    def test_extract_runtime_team_snapshot_prefers_canonical_source(self) -> None:
        base = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node(
                "run-legacy",
                "Run",
                payload={
                    "runtime_agents": [
                        {"runtime_instance_id": "rt-legacy", "role_label": "Legacy"},
                    ]
                },
                created_at=base,
            ),
            make_node(
                "run-canonical",
                "Run",
                payload={
                    "runtime_team_snapshot": {
                        "runtime_agents": [
                            {"runtime_instance_id": "rt-canonical", "role_label": "Planner"},
                        ]
                    }
                },
                created_at=base + timedelta(seconds=1),
            ),
        ]

        snapshot = extract_runtime_team_snapshot(nodes)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot["source_key"], "runtime_team_snapshot.runtime_agents")
        self.assertEqual(snapshot["members"][0]["runtime_instance_id"], "rt-canonical")

    def test_normalization_helpers_keep_canonical_values(self) -> None:
        self.assertEqual(normalize_status("pending"), "queued")
        self.assertEqual(normalize_status("active"), "running")
        self.assertEqual(normalize_status("success"), "done")
        self.assertEqual(normalize_status("failure"), "error")
        self.assertEqual(normalize_status(""), "unknown")

        self.assertEqual(
            normalize_runtime_source_key("runtime.runtime_team_snapshot.runtime_agents"),
            "runtime_team_snapshot.runtime_agents",
        )
        self.assertEqual(normalize_runtime_source_key("payload.team_plan.agents"), "team_plan.agents")
        self.assertEqual(normalize_runtime_source_key(""), "runtime_snapshot")

    def test_extract_runtime_members_from_container_deduplicates(self) -> None:
        container = {
            "runtime_agents": [
                {"runtime_instance_id": "rt-1", "agent_id": "planner", "role_label": "Planner"},
                {"runtime_instance_id": "rt-2", "agent_id": "critic", "role_label": "Critic"},
            ],
            "runtime_team_snapshot": {
                "runtime_agents": [
                    {"runtime_instance_id": "rt-1", "agent_id": "planner", "role_label": "Planner"},
                ]
            },
        }

        members = extract_runtime_members_from_container(container)
        self.assertEqual(len(members), 2)
        runtime_ids = {str(item.get("runtime_instance_id") or "") for item in members}
        self.assertIn("rt-1", runtime_ids)
        self.assertIn("rt-2", runtime_ids)

    def test_extract_runtime_team_snapshot_reads_team_plan_v2_metadata(self) -> None:
        snapshot = extract_runtime_team_snapshot(
            [
                make_node(
                    "run-team-plan-v2",
                    "Run",
                    payload={
                        "runtime_team_snapshot": {
                            "task_interpretation": {"summary": "Split into research and review"},
                            "team_plan": {
                                "slots": [
                                    {
                                        "slot_id": "slot-analyst",
                                        "role_id": "role-analyst",
                                        "display_label": "Analyst",
                                        "selection_reason": "Need grounded evidence gathering",
                                    }
                                ],
                                "supervisor_runtime": {
                                    "interaction_mode": "interrupt_on_completion",
                                    "instance_id": "sup-1",
                                    "enabled": True,
                                },
                            },
                            "runtime_agents": [
                                {
                                    "instance_id": "rt-1",
                                    "slot_id": "slot-analyst",
                                    "role_id": "role-analyst",
                                    "display_label": "Evidence Analyst",
                                    "preset_id": "preset.analyst",
                                    "selection_reason": "Best preset fit",
                                    "attached_skill_ids": ["skill.claim_evidence_audit.v1"],
                                    "context_pack_id": "cp-1",
                                }
                            ],
                            "collaboration_cells": [
                                {
                                    "cell_id": "cell-1",
                                    "pattern": "debate",
                                    "member_instance_ids": ["rt-1", "rt-2"],
                                    "topology": "pairwise",
                                    "max_rounds": 3,
                                    "termination": "majority_converged",
                                }
                            ],
                            "authority_graph": [
                                {
                                    "authority_id": "auth-1",
                                    "runtime_instance_id": "rt-1",
                                    "authority_profile_id": "authority.read_only",
                                    "denied_actions": ["publish"],
                                }
                            ],
                            "checkpoints": [
                                {
                                    "checkpoint_id": "checkpoint-1",
                                    "kind": "approval",
                                    "approval_required": True,
                                    "human_interrupt_allowed": True,
                                }
                            ],
                            "execution_graph": {
                                "parallel_groups": [["rt-1", "rt-2"]],
                                "sequential_after": {"rt-2": ["rt-1"]},
                                "supervisor_edges": [{"from": "sup-1", "to": "rt-1"}],
                            },
                            "selection_explanations": [
                                {"slot_id": "slot-analyst", "text": "Analyst preset covers research"}
                            ],
                            "conversation_preferences": {"tone": "concise"},
                        }
                    },
                )
            ]
        )

        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot["task_interpretation"]["summary"], "Split into research and review")
        self.assertEqual((snapshot.get("team_plan") or {}).get("slots", [])[0]["slot_id"], "slot-analyst")
        self.assertEqual((snapshot.get("team_plan") or {}).get("supervisor_runtime", {}).get("interaction_mode"), "interrupt_on_completion")
        self.assertEqual(snapshot["members"][0]["instance_id"], "rt-1")
        self.assertEqual(snapshot["members"][0]["attached_skill_ids"], ["skill.claim_evidence_audit.v1"])
        self.assertEqual((snapshot.get("collaboration_cells") or [])[0]["kind"], "debate")
        self.assertEqual((snapshot.get("collaboration_cells") or [])[0]["topology"], "pairwise")
        self.assertEqual((snapshot.get("authority_graph") or [])[0]["authority_profile_id"], "authority.read_only")
        self.assertEqual((snapshot.get("authority_graph") or [])[0]["denied_actions"], ["publish"])
        self.assertEqual((snapshot.get("checkpoints") or [])[0]["checkpoint_id"], "checkpoint-1")
        self.assertEqual((snapshot.get("checkpoints") or [])[0]["human_interrupt_allowed"], True)
        self.assertEqual((snapshot.get("execution_graph") or {}).get("sequential_after"), {"rt-2": ["rt-1"]})
        self.assertEqual((snapshot.get("selection_explanations") or [])[0]["slot_id"], "slot-analyst")
        self.assertEqual((snapshot.get("conversation_preferences") or {}).get("tone"), "concise")

    def test_normalize_execution_feedback_keeps_recommendation_fields(self) -> None:
        normalized = normalize_execution_feedback({
            "run_count": 4,
            "patterns": [
                {
                    "execution_pattern": "builder_reviewer_loop",
                    "run_count": 4,
                    "avg_participation_pct": 87.5,
                    "completion_rate_pct": 100,
                    "recommendation": "recommended",
                    "reason": "avg participation 87.5%, completion 100%",
                }
            ],
            "recommended_patterns": [
                {
                    "execution_pattern": "builder_reviewer_loop",
                    "run_count": 4,
                    "avg_participation_pct": 87.5,
                    "completion_rate_pct": 100,
                    "recommendation": "recommended",
                    "reason": "avg participation 87.5%, completion 100%",
                }
            ],
            "discouraged_overlays": [
                {
                    "overlay_id": "agency:engineering/heavy-overlay",
                    "title": "Heavy Overlay",
                    "run_count": 3,
                    "avg_participation_pct": 42,
                    "avg_overlay_tokens": 320,
                    "avg_overlay_share_pct": 24,
                    "recommendation": "discouraged",
                    "reason": "avg participation 42%, prompt share 24%",
                }
            ],
        })

        self.assertIsNotNone(normalized)
        assert normalized is not None
        self.assertEqual((normalized.get("patterns") or [])[0]["recommendation"], "recommended")
        self.assertEqual((normalized.get("recommended_patterns") or [])[0]["execution_pattern"], "builder_reviewer_loop")
        self.assertEqual((normalized.get("discouraged_overlays") or [])[0]["recommendation"], "discouraged")


if __name__ == "__main__":
    unittest.main()
