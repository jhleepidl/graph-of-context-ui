from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import SQLModel, Session, create_engine

from app.services.run_skill_summary import build_run_skill_summary, build_thread_skill_usage_summary
from app.services.run_studio import _agent_team_summary
from app.services.skill_registry import build_skill_registry


@dataclass
class FakeNode:
    id: str
    type: str
    text: str
    payload_json: str
    created_at: datetime


@dataclass
class FakeEdge:
    id: str
    from_id: str
    to_id: str
    type: str


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


class SkillLayerProjectionTests(unittest.TestCase):
    def test_skill_registry_extracts_runtime_skill_packages(self) -> None:
        node = make_node(
            "run-registry",
            "Run",
            payload={
                "runtime": {
                    "skill_packages": [
                        {
                            "id": "skill.custom_planner.v2",
                            "name": "Custom Planner",
                            "version": "v2",
                            "capability_tags": ["planning", "decomposition"],
                            "compatible_roles": ["planner"],
                        }
                    ]
                }
            },
            created_at=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
        )

        registry = build_skill_registry(nodes=[node], include_defaults=False)
        self.assertIn("skill.custom_planner.v2", registry)
        self.assertEqual(registry["skill.custom_planner.v2"]["name"], "Custom Planner")
        self.assertIn("planning", registry["skill.custom_planner.v2"]["capability_tags"])

    def test_agent_team_runtime_item_includes_attached_skills(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            nodes = [
                make_node(
                    "run-skills",
                    "Run",
                    payload={
                        "runtime_team_snapshot": {
                            "runtime_agents": [
                                {
                                    "runtime_instance_id": "rt-analyst-1",
                                    "role_label": "Analyst",
                                    "status": "running",
                                    "context_pack_id": "cp-analyst",
                                    "attached_skills": [
                                        {
                                            "skill_id": "skill.claim_evidence_audit.v1",
                                            "load_level": "instructions",
                                            "selected_by": "policy",
                                            "selection_reason": "Claim confidence dropped below threshold",
                                            "status": "active",
                                        }
                                    ],
                                }
                            ]
                        }
                    },
                    created_at=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
                )
            ]

            summary = _agent_team_summary(session, thread_id="thread-skills", nodes=nodes)
            self.assertEqual(len(summary["items"]), 1)
            item = summary["items"][0]
            self.assertEqual(item["context_pack_id"], "cp-analyst")
            self.assertEqual(len(item["attached_skills"]), 1)
            self.assertEqual(item["attached_skills"][0]["skill_id"], "skill.claim_evidence_audit.v1")
            self.assertEqual(item["attached_skills"][0]["load_level"], "instructions")
            self.assertEqual(item["attached_skills"][0]["selected_by"], "policy")

    def test_run_skill_summary_context_packs_keep_skill_load_levels(self) -> None:
        nodes = [
            make_node(
                "run-ctx-pack",
                "Run",
                payload={
                    "runtime_team_snapshot": {
                        "runtime_agents": [
                            {
                                "runtime_instance_id": "rt-1",
                                "role_label": "Evidence Analyst",
                                "attached_skills": [
                                    {
                                        "skill_id": "skill.claim_evidence_audit.v1",
                                        "load_level": "instructions",
                                        "selected_by": "policy",
                                        "selection_reason": "Evidence confidence dropped",
                                    }
                                ],
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
                                    "count": 3,
                                }
                            ],
                        }
                    ],
                },
                created_at=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
            )
        ]

        summary = build_run_skill_summary(nodes=nodes, edges=[], run_id="run-ctx-pack")
        self.assertEqual(summary["run_id"], "run-ctx-pack")
        self.assertEqual(summary["counts"]["context_packs"], 1)
        context_pack = summary["context_packs"][0]
        self.assertEqual(context_pack["context_pack_id"], "cp-1")
        self.assertEqual(context_pack["skill_items"][0]["skill_id"], "skill.claim_evidence_audit.v1")
        self.assertEqual(context_pack["skill_items"][0]["load_level"], "instructions")

    def test_skill_usage_projection_extracts_events(self) -> None:
        nodes = [
            make_node(
                "run-main",
                "Run",
                payload={"status": "running"},
                created_at=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
            ),
            make_node(
                "step-usage",
                "Step",
                payload={
                    "run_id": "run-main",
                    "skill_usage_events": [
                        {
                            "skill_id": "skill.context_selection_policy.v1",
                            "event_type": "selected",
                            "timestamp": "2026-03-10T00:00:05Z",
                            "payload_summary": "Context policy escalated to instructions level",
                        }
                    ],
                },
                created_at=datetime(2026, 3, 10, 0, 0, 5, tzinfo=timezone.utc),
            ),
        ]

        summary = build_thread_skill_usage_summary(nodes=nodes, edges=[], run_id="run-main")
        self.assertEqual(summary["count"], 1)
        event = summary["items"][0]
        self.assertEqual(event["skill_id"], "skill.context_selection_policy.v1")
        self.assertEqual(event["event_type"], "selected")
        self.assertIn("escalated", event["payload_summary"])

    def test_non_skill_flow_keeps_backward_compatible_agent_items(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            nodes = [
                make_node(
                    "step-no-skills",
                    "Step",
                    payload={"agent_id": "worker-a", "status": "running"},
                    created_at=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
                ),
            ]

            summary = _agent_team_summary(session, thread_id="thread-no-skills", nodes=nodes)
            self.assertEqual(len(summary["items"]), 1)
            item = summary["items"][0]
            self.assertEqual(item["source"], "inferred_from_steps")
            self.assertEqual(item["runtime_status"], "running")
            self.assertEqual(item["attached_skills"], [])
            self.assertIsNone(item["context_pack_id"])


if __name__ == "__main__":
    unittest.main()
