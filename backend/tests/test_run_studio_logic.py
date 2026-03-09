from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.services.graph_projections import memory_context_projection
from app.services.run_studio import _evidence_summary, _extract_runtime_team_snapshot


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


def make_edge(edge_id: str, from_id: str, to_id: str, edge_type: str) -> FakeEdge:
    return FakeEdge(id=edge_id, from_id=from_id, to_id=to_id, type=edge_type)


class RunStudioLogicTests(unittest.TestCase):
    def test_runtime_team_snapshot_prefers_latest_valid_snapshot(self) -> None:
        base = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node(
                "run-old",
                "Run",
                payload={"runtime_team_snapshot": [{"agent_id": "planner", "role": "Planner"}]},
                created_at=base,
            ),
            make_node(
                "step-new",
                "Step",
                payload={"runtime_agents": [{"runtime_instance_id": "exec-1", "role_label": "Executor"}]},
                created_at=base + timedelta(seconds=10),
            ),
        ]

        snapshot = _extract_runtime_team_snapshot(nodes)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot["node_id"], "step-new")
        self.assertEqual(snapshot["source_key"], "runtime_agents")
        self.assertEqual(snapshot["members"][0]["runtime_instance_id"], "exec-1")

    def test_runtime_team_snapshot_accepts_keyed_member_map(self) -> None:
        base = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node(
                "run-map",
                "Run",
                payload={
                    "team_plan": {
                        "agents": {
                            "planner": {"role_label": "Planner"},
                            "critic": {"role_label": "Critic", "runtime_instance_id": "rt-critic-1"},
                        }
                    }
                },
                created_at=base,
            ),
        ]

        snapshot = _extract_runtime_team_snapshot(nodes)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot["source_key"], "team_plan")
        member_ids = {
            str(item.get("agent_id") or item.get("runtime_instance_id") or "")
            for item in snapshot["members"]
        }
        self.assertIn("planner", member_ids)
        self.assertIn("rt-critic-1", member_ids)

    def test_evidence_ranking_prioritizes_supported_selected_claims(self) -> None:
        base = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
        decision = make_node(
            "n-decision",
            "Decision",
            text="Use batched retrieval with provenance checks.",
            payload={"provenance": "design-doc-7"},
            created_at=base,
        )
        support = make_node(
            "n-support",
            "Observation",
            text="Offline eval improved answer relevance by 14%.",
            created_at=base + timedelta(seconds=1),
        )
        noise = make_node(
            "n-msg",
            "Message",
            text="I think this might work.",
            payload={"role": "assistant"},
            created_at=base + timedelta(seconds=2),
        )
        nodes = [decision, support, noise]
        edges = [
            make_edge("e1", "n-support", "n-decision", "SUPPORTS"),
        ]

        summary = _evidence_summary(nodes=nodes, edges=edges, active_ids=["n-decision"])
        items = summary["items"]

        self.assertGreaterEqual(len(items), 2)
        self.assertEqual(items[0]["claim_node_id"], "n-decision")
        self.assertTrue(items[0]["selected_in_context"])
        self.assertGreater(len(items[0]["evidence_nodes"]), 0)
        self.assertGreaterEqual(items[0]["score"], items[-1]["score"])

    def test_context_projection_splits_core_supporting_execution(self) -> None:
        base = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node("c1", "Decision", text="Choose strategy A", created_at=base),
            make_node("s1", "Artifact", text="spec.md", created_at=base + timedelta(seconds=1)),
            make_node("x1", "Step", text="Run experiment", created_at=base + timedelta(seconds=2)),
            make_node("x2", "Message", text="assistant note", payload={"role": "assistant"}, created_at=base + timedelta(seconds=3)),
        ]
        projection = memory_context_projection(nodes, [], active_node_ids=["c1", "x1"])

        core_ids = {item["id"] for item in projection["core_items"]}
        supporting_ids = {item["id"] for item in projection["supporting_items"]}
        execution_ids = {item["id"] for item in projection["execution_items"]}
        recent_ids = {item["id"] for item in projection["recent_items"]}

        self.assertIn("c1", core_ids)
        self.assertIn("s1", supporting_ids)
        self.assertIn("x1", execution_ids)
        self.assertIn("x2", execution_ids)
        self.assertEqual(projection["core_count"], 1)
        self.assertEqual(projection["supporting_count"], 1)
        self.assertEqual(projection["execution_count"], 2)
        self.assertIn("c1", recent_ids)
        self.assertIn("s1", recent_ids)
        self.assertNotIn("x1", recent_ids)


if __name__ == "__main__":
    unittest.main()
