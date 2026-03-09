from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlmodel import SQLModel, Session, create_engine

from app.models import Agent, Conversation, ConversationAgent
from app.services.graph_projections import memory_context_projection
from app.services.run_studio import _agent_team_summary, _evidence_summary, _extract_runtime_team_snapshot


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
    def test_runtime_team_snapshot_prefers_canonical_runtime_snapshot_shape(self) -> None:
        base = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node(
                "run-canonical",
                "Run",
                payload={
                    "runtime_team_snapshot": {
                        "runtime_agents": [
                            {
                                "runtime_instance_id": "rt-planner-1",
                                "role_label": "Planner",
                                "ephemeral": True,
                            }
                        ],
                    },
                    "runtime_agents": [{"agent_id": "legacy-top-level"}],
                },
                created_at=base,
            ),
        ]

        snapshot = _extract_runtime_team_snapshot(nodes)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot["source_key"], "runtime_team_snapshot.runtime_agents")
        self.assertEqual(snapshot["members"][0]["runtime_instance_id"], "rt-planner-1")
        self.assertTrue(bool(snapshot["members"][0]["ephemeral"]))

    def test_runtime_team_snapshot_uses_top_level_runtime_agents_when_needed(self) -> None:
        base = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node(
                "step-top-runtime-agents",
                "Step",
                payload={"runtime_agents": [{"runtime_instance_id": "exec-1", "role_label": "Executor"}]},
                created_at=base,
            ),
        ]

        snapshot = _extract_runtime_team_snapshot(nodes)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot["source_key"], "runtime_agents")
        self.assertEqual(snapshot["members"][0]["runtime_instance_id"], "exec-1")

    def test_runtime_team_snapshot_ignores_plain_team_plan_metadata(self) -> None:
        base = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node(
                "run-plan-only",
                "Run",
                payload={
                    "team_plan": {
                        "mode": "parallel",
                        "reason": "decompose into planner/writer",
                        "budget": {"tokens": 3200},
                        "execution_order": ["planner", "writer"],
                        "roles": {"planner": "plan first", "writer": "draft after plan"},
                    }
                },
                created_at=base,
            ),
        ]

        snapshot = _extract_runtime_team_snapshot(nodes)
        self.assertIsNone(snapshot)

    def test_runtime_team_snapshot_accepts_member_like_keyed_map(self) -> None:
        base = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node(
                "run-map",
                "Run",
                payload={
                    "team_plan": {
                        "agents": {
                            "planner": {"role_label": "Planner", "model": "gpt-4o-mini"},
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
        self.assertEqual(snapshot["source_key"], "team_plan.agents")
        member_ids = {
            str(item.get("agent_id") or item.get("runtime_instance_id") or "")
            for item in snapshot["members"]
        }
        self.assertIn("planner", member_ids)
        self.assertIn("rt-critic-1", member_ids)

    def test_agent_team_falls_back_to_conversation_membership(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            conversation = Conversation(thread_id="thread-conv", owner_user_id="u1", service_id="svc")
            session.add(conversation)
            agent = Agent(
                owner_user_id="u1",
                service_id="svc",
                name="Analyst",
                description="Conversation-level analyst",
                model="gpt-4o",
            )
            session.add(agent)
            session.commit()

            membership = ConversationAgent(
                conversation_id=conversation.id,
                agent_id=agent.id,
                enabled=True,
                order_index=0,
                overrides_json=json.dumps({"ephemeral": True}),
            )
            session.add(membership)
            session.commit()

            summary = _agent_team_summary(session, thread_id="thread-conv", nodes=[])
            self.assertEqual(len(summary["items"]), 1)
            self.assertEqual(summary["items"][0]["source"], "conversation_membership")
            self.assertTrue(bool(summary["items"][0]["ephemeral"]))

    def test_agent_team_falls_back_to_inferred_step_agents(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            nodes = [
                make_node(
                    "step-a",
                    "Step",
                    payload={"agent_id": "runtime-worker", "status": "running"},
                    created_at=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
                ),
            ]
            summary = _agent_team_summary(session, thread_id="thread-no-conversation", nodes=nodes)
            self.assertEqual(len(summary["items"]), 1)
            self.assertEqual(summary["items"][0]["source"], "inferred_from_steps")
            self.assertEqual(summary["items"][0]["agent_id"], "runtime-worker")
            self.assertEqual(summary["items"][0]["runtime_status"], "running")

    def test_agent_team_preserves_runtime_ephemeral_flag(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            nodes = [
                make_node(
                    "run-runtime",
                    "Run",
                    payload={
                        "runtime_team_snapshot": {
                            "runtime_agents": [
                                {
                                    "runtime_instance_id": "rt-ephemeral",
                                    "role_label": "Temp Planner",
                                    "status": "running",
                                    "ephemeral": True,
                                }
                            ]
                        }
                    },
                    created_at=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
                ),
            ]
            summary = _agent_team_summary(session, thread_id="thread-runtime", nodes=nodes)
            self.assertEqual(len(summary["items"]), 1)
            self.assertEqual(summary["items"][0]["source"], "runtime_snapshot")
            self.assertTrue(bool(summary["items"][0]["ephemeral"]))
            self.assertEqual(summary["items"][0]["runtime_status"], "running")

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
