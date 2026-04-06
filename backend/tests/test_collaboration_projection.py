from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.services.run_studio import build_run_studio_summary
from sqlmodel import SQLModel, Session
from tests.db_test_utils import create_test_engine as create_engine

from app.models import ContextSet, Node, Thread


@dataclass
class FakeNode:
    id: str
    type: str
    text: str
    payload_json: str
    created_at: datetime


def make_payload() -> dict:
        return {
            "runtime_team_snapshot": {
                "team_plan": {
                    "slots": [
                        {"slot_id": "slot-a", "role_id": "role-a", "display_label": "Analyst"},
                        {"slot_id": "slot-b", "role_id": "role-b", "display_label": "Reviewer"},
                    ],
                    "supervisor_runtime": {
                        "interaction_mode": "report_back",
                        "instance_id": "sup-1",
                        "enabled": True,
                    },
                },
                "runtime_agents": [
                    {"instance_id": "rt-a", "slot_id": "slot-a", "role_id": "role-a", "display_label": "Analyst"},
                    {"instance_id": "rt-b", "slot_id": "slot-b", "role_id": "role-b", "display_label": "Reviewer"},
                ],
                "collaboration_cells": [
                    {
                        "cell_id": "cell-reflect",
                        "pattern": "reflection",
                        "member_instance_ids": ["rt-a"],
                        "topology": "self_loop",
                        "max_rounds": 2,
                        "termination": {"condition": "confidence_reached"},
                        "report_back_to_instance_id": "sup-1",
                        "selection_reason": "Force self-check before finalizing",
                    },
                    {
                        "cell_id": "cell-debate",
                        "pattern": "debate",
                        "member_instance_ids": ["rt-a", "rt-b"],
                        "topology": "pairwise",
                        "max_rounds": 3,
                        "termination": {"condition": "majority_converged", "threshold": 2},
                        "decision_mode": "majority",
                    },
                    {
                        "cell_id": "cell-committee",
                        "pattern": "committee",
                        "member_instance_ids": ["rt-a", "rt-b"],
                        "topology": "hub_and_spoke",
                        "termination": "chair_finalize",
                    },
                ],
            }
        }


class CollaborationProjectionTests(unittest.TestCase):
    def test_run_studio_summary_projects_collaboration_cells(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        base = datetime(2026, 3, 14, 0, 0, tzinfo=timezone.utc)

        with Session(engine) as session:
            thread = Thread(id="thread-collab", service_id="svc", title="Collaboration")
            context_set = ContextSet(id="ctx-collab", thread_id=thread.id, name="default", active_node_ids_json="[]")
            run_node = Node(
                id="run-collab",
                thread_id=thread.id,
                type="Run",
                text="",
                payload_json=json.dumps(make_payload()),
                created_at=base,
            )
            step_node = Node(
                id="step-collab",
                thread_id=thread.id,
                type="Step",
                text="",
                payload_json=json.dumps({"run_id": "run-collab", "status": "running", "agent_id": "rt-a"}),
                created_at=base + timedelta(seconds=1),
            )
            session.add(thread)
            session.add(context_set)
            session.add(run_node)
            session.add(step_node)
            session.commit()

            summary = build_run_studio_summary(session, thread=thread, context_set_id=context_set.id)

        collaboration = summary.get("collaboration") or {}
        self.assertEqual(collaboration.get("count"), 3)
        self.assertEqual((collaboration.get("counts") or {}).get("reflection"), 1)
        self.assertEqual((collaboration.get("counts") or {}).get("debate"), 1)
        self.assertEqual((collaboration.get("counts") or {}).get("committee"), 1)

        items = collaboration.get("items") or []
        debate = next(item for item in items if item.get("kind") == "debate")
        self.assertEqual(debate.get("member_instance_ids"), ["rt-a", "rt-b"])
        self.assertEqual(debate.get("member_labels"), ["Analyst", "Reviewer"])
        self.assertEqual(debate.get("topology"), "pairwise")
        self.assertEqual(debate.get("max_rounds"), 3)
        self.assertEqual(debate.get("termination"), {"condition": "majority_converged", "threshold": 2})
        self.assertIn("condition: majority_converged", str(debate.get("termination_summary") or ""))
        self.assertNotIn("{'", str(debate.get("termination_summary") or ""))
        reflection = next(item for item in items if item.get("kind") == "reflection")
        self.assertEqual(reflection.get("report_back_to_instance_id"), "sup-1")
        self.assertEqual(reflection.get("termination"), {"condition": "confidence_reached"})


if __name__ == "__main__":
    unittest.main()
