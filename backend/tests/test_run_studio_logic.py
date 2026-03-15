from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlmodel import SQLModel, Session, create_engine

from app.models import Agent, ContextSet, Conversation, ConversationAgent, Node, Thread
from app.services.graph_projections import memory_context_projection
from app.services.run_studio import (
    _agent_team_summary,
    _evidence_summary,
    _extract_runtime_team_snapshot,
    _now_panel_summary,
    build_run_studio_summary,
)


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

    def test_runtime_team_snapshot_accepts_camel_case_runtime_team_snapshot(self) -> None:
        base = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node(
                "run-camel",
                "Run",
                payload={
                    "runtimeTeamSnapshot": {
                        "runtime_agents": [{"runtime_instance_id": "rt-camel-1", "role_label": "Executor"}]
                    }
                },
                created_at=base,
            ),
        ]
        snapshot = _extract_runtime_team_snapshot(nodes)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(snapshot["source_key"], "runtime_team_snapshot.runtime_agents")
        self.assertEqual(snapshot["members"][0]["runtime_instance_id"], "rt-camel-1")

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
            self.assertEqual(summary["items"][0]["source_key"], "conversation_agents")
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
            self.assertEqual(summary["items"][0]["source_key"], "step_payload.agent_id")

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
            self.assertEqual(summary["items"][0]["source_key"], "runtime_team_snapshot.runtime_agents")
            self.assertTrue(bool(summary["items"][0]["ephemeral"]))
            self.assertEqual(summary["items"][0]["runtime_status"], "running")

    def test_agent_team_runtime_snapshot_precedes_conversation_membership(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            conversation = Conversation(thread_id="thread-priority", owner_user_id="u1", service_id="svc")
            session.add(conversation)
            agent = Agent(owner_user_id="u1", service_id="svc", name="StaticAgent")
            session.add(agent)
            session.commit()
            session.add(
                ConversationAgent(
                    conversation_id=conversation.id,
                    agent_id=agent.id,
                    enabled=True,
                    order_index=0,
                    overrides_json="{}",
                )
            )
            session.commit()

            nodes = [
                make_node(
                    "run-priority",
                    "Run",
                    payload={
                        "runtime_team_snapshot": {
                            "runtime_agents": [{"runtime_instance_id": "rt-priority-1", "role_label": "LiveAgent"}]
                        }
                    },
                    created_at=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
                ),
            ]
            summary = _agent_team_summary(session, thread_id="thread-priority", nodes=nodes)
            self.assertEqual(len(summary["items"]), 1)
            self.assertEqual(summary["items"][0]["source"], "runtime_snapshot")
            self.assertEqual(summary["items"][0]["source_key"], "runtime_team_snapshot.runtime_agents")

    def test_agent_team_runtime_source_key_normalizes_nested_source_path(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            nodes = [
                make_node(
                    "run-nested-source",
                    "Run",
                    payload={
                        "runtime": {
                            "runtimeTeamSnapshot": {
                                "runtime_agents": [{"runtime_instance_id": "rt-nested-1", "role_label": "Nested"}]
                            }
                        }
                    },
                    created_at=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
                ),
            ]
            summary = _agent_team_summary(session, thread_id="thread-nested-source", nodes=nodes)
            self.assertEqual(len(summary["items"]), 1)
            item = summary["items"][0]
            self.assertEqual(item["source"], "runtime_snapshot")
            self.assertEqual(item["source_key"], "runtime_team_snapshot.runtime_agents")
            self.assertEqual(item["source_path"], "runtime.runtime_team_snapshot.runtime_agents")
            self.assertEqual(summary.get("snapshot_source_key"), "runtime_team_snapshot.runtime_agents")

    def test_run_studio_summary_exposes_team_plan_v2_runtime_projections(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        base = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)

        with Session(engine) as session:
            thread = Thread(id="thread-v2", service_id="svc", title="V2")
            context_set = ContextSet(id="ctx-v2", thread_id=thread.id, name="default", active_node_ids_json="[]")
            run_node = Node(
                id="run-v2",
                thread_id=thread.id,
                type="Run",
                text="run",
                payload_json=json.dumps(
                    {
                        "runtime_team_snapshot": {
                            "task_interpretation": {"summary": "Research and review"},
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
                                    "user_visible": True,
                                },
                            },
                            "runtime_agents": [
                                {"instance_id": "rt-1", "slot_id": "slot-1", "role_id": "role-1", "display_label": "Analyst"},
                                {"instance_id": "rt-2", "slot_id": "slot-2", "role_id": "role-2", "display_label": "Reviewer", "synthesized": True},
                            ],
                            "collaboration_cells": [
                                {
                                    "cell_id": "cell-1",
                                    "pattern": "debate",
                                    "member_instance_ids": ["rt-1", "rt-2"],
                                    "topology": "pairwise",
                                    "max_rounds": 3,
                                    "termination": {"condition": "majority_converged", "threshold": 2},
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
                                    "supervisor_decision": {"mode": "await_user", "condition": "final_review_ready"},
                                    "completion_signal": {"signal": "final_answer_ready"},
                                }
                            ],
                            "execution_graph": {
                                "parallel_groups": [
                                    {"group_id": "group-1", "label": "research pair", "member_instance_ids": ["rt-1", "rt-2"]}
                                ],
                                "supervisor_edges": [{"from": "sup-1", "to": "rt-1"}],
                            },
                            "selection_explanations": [{"slot_id": "slot-1", "text": "Analyst covers the research phase"}],
                        }
                    }
                ),
                created_at=base,
            )
            step_node = Node(
                id="step-v2",
                thread_id=thread.id,
                type="Step",
                text="step",
                payload_json=json.dumps({"run_id": "run-v2", "status": "running", "agent_id": "rt-1"}),
                created_at=base + timedelta(seconds=1),
            )
            session.add(thread)
            session.add(context_set)
            session.add(run_node)
            session.add(step_node)
            session.commit()

            summary = build_run_studio_summary(session, thread=thread, context_set_id=context_set.id)

        self.assertIn("team_view", summary)
        self.assertIn("why_this_team", summary)
        self.assertIn("orchestration", summary)
        self.assertIn("collaboration", summary)
        self.assertIn("authority", summary)
        self.assertIn("checkpoints", summary)
        self.assertEqual((summary.get("team_view") or {}).get("count"), 2)
        self.assertEqual((summary.get("orchestration") or {}).get("mode"), "parallel")
        self.assertEqual((summary.get("orchestration") or {}).get("supervisor_mode"), "interrupt_on_completion")
        self.assertEqual((summary.get("orchestration") or {}).get("parallel_groups", [])[0].get("member_labels"), ["Analyst", "Reviewer"])
        self.assertEqual((summary.get("orchestration") or {}).get("supervisor_edges", [])[0].get("edge_summary"), "sup-1 -> Analyst")
        self.assertEqual((summary.get("collaboration") or {}).get("count"), 1)
        self.assertEqual((summary.get("collaboration") or {}).get("items", [])[0].get("kind"), "debate")
        self.assertEqual((summary.get("collaboration") or {}).get("items", [])[0].get("topology"), "pairwise")
        self.assertEqual((summary.get("collaboration") or {}).get("items", [])[0].get("termination"), {"condition": "majority_converged", "threshold": 2})
        self.assertEqual((summary.get("collaboration") or {}).get("items", [])[0].get("termination_summary"), "condition: majority_converged")
        self.assertEqual((summary.get("authority") or {}).get("graph_count"), 1)
        self.assertIn("publish", (summary.get("authority") or {}).get("items", [])[0].get("denied_actions") or [])
        self.assertEqual((summary.get("checkpoints") or {}).get("items", [])[0].get("human_interrupt_allowed"), True)
        self.assertEqual((summary.get("checkpoints") or {}).get("items", [])[0].get("supervisor_decision"), {"mode": "await_user", "condition": "final_review_ready"})
        self.assertEqual((summary.get("checkpoints") or {}).get("items", [])[0].get("supervisor_decision_summary"), "condition: final_review_ready | mode: await_user")
        self.assertEqual((summary.get("checkpoints") or {}).get("items", [])[0].get("completion_signal"), {"signal": "final_answer_ready"})
        self.assertEqual((summary.get("checkpoints") or {}).get("items", [])[0].get("completion_signal_summary"), "signal: final_answer_ready")
        self.assertEqual((summary.get("checkpoints") or {}).get("counts", {}).get("approval_required"), 1)

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

    def test_now_panel_prefers_latest_relevant_run_over_older_queued_run(self) -> None:
        base = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
        thread = Thread(id="thread-now", service_id="svc", title="Now Test")
        nodes = [
            make_node("run-old", "Run", payload={"status": "queued"}, created_at=base),
            make_node(
                "step-old-queued",
                "Step",
                payload={"run_id": "run-old", "status": "queued", "title": "Old queued step"},
                created_at=base + timedelta(seconds=1),
            ),
            make_node("run-new", "Run", payload={"status": "done"}, created_at=base + timedelta(seconds=10)),
            make_node(
                "step-new-done",
                "Step",
                payload={"run_id": "run-new", "status": "done", "title": "New completed step"},
                created_at=base + timedelta(seconds=11),
            ),
        ]

        summary = _now_panel_summary(thread=thread, nodes=nodes, edges=[], active_ids=[])
        state = summary["state"]
        self.assertEqual(state["run_status"], "done")
        self.assertEqual(state["current_run_id"], "run-new")
        self.assertEqual(state["current_run_step_status_counts"].get("done"), 1)
        self.assertEqual(state["stale_queued_step_count"], 1)
        self.assertEqual(summary["task"]["current_step_id"], "step-new-done")

    def test_now_panel_exposes_current_pending_approval_separately_from_old_runs(self) -> None:
        base = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)
        thread = Thread(id="thread-now-pending", service_id="svc", title="Now Pending Test")
        nodes = [
            make_node("run-old", "Run", payload={"status": "queued"}, created_at=base),
            make_node(
                "step-old-pending",
                "Step",
                payload={
                    "run_id": "run-old",
                    "status": "queued",
                    "pending_approval": True,
                    "title": "Old pending step",
                },
                created_at=base + timedelta(seconds=1),
            ),
            make_node("run-new", "Run", payload={"status": "done"}, created_at=base + timedelta(seconds=10)),
            make_node(
                "step-new-done",
                "Step",
                payload={"run_id": "run-new", "status": "done"},
                created_at=base + timedelta(seconds=11),
            ),
        ]

        summary = _now_panel_summary(thread=thread, nodes=nodes, edges=[], active_ids=[])
        state = summary["state"]
        self.assertTrue(state["pending_approval"])
        self.assertFalse(state["current_pending_approval"])
        self.assertEqual(state["current_run_id"], "run-new")
        self.assertEqual(state["stale_queued_step_count"], 1)

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

    def test_run_studio_summary_includes_agent_team_and_skill_fields(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        base = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)

        with Session(engine) as session:
            thread = Thread(id="thread-summary", service_id="svc", title="Summary Test")
            context_set = ContextSet(
                id="ctx-summary",
                thread_id=thread.id,
                name="default",
                active_node_ids_json="[]",
            )
            run_node = Node(
                id="run-summary",
                thread_id=thread.id,
                type="Run",
                text="run",
                payload_json=json.dumps(
                    {
                        "runtime_team_snapshot": {
                            "runtime_agents": [
                                {
                                    "runtime_instance_id": "rt-summary-1",
                                    "role_label": "Analyst",
                                    "attached_skills": [
                                        {
                                            "skill_id": "skill.claim_evidence_audit.v1",
                                            "load_level": "instructions",
                                            "selected_by": "policy",
                                            "selection_reason": "confidence drop",
                                        }
                                    ],
                                }
                            ]
                        }
                    }
                ),
                created_at=base,
            )
            step_node = Node(
                id="step-summary",
                thread_id=thread.id,
                type="Step",
                text="step",
                payload_json=json.dumps(
                    {
                        "run_id": "run-summary",
                        "status": "running",
                        "agent_id": "rt-summary-1",
                    }
                ),
                created_at=base + timedelta(seconds=1),
            )

            session.add(thread)
            session.add(context_set)
            session.add(run_node)
            session.add(step_node)
            session.commit()

            summary = build_run_studio_summary(session, thread=thread, context_set_id=context_set.id)
            self.assertIn("agent_team", summary)
            self.assertIn("current_run_skills", summary)
            self.assertGreaterEqual(len(summary["agent_team"].get("items", [])), 1)
            self.assertEqual(summary["agent_team"]["items"][0]["source"], "runtime_snapshot")
            self.assertGreaterEqual(len(summary["current_run_skills"].get("attached_skills", [])), 1)
            self.assertIn("skill_counts", summary)

    def test_run_studio_summary_is_safe_for_legacy_agent_team_only_state(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        base = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)

        with Session(engine) as session:
            thread = Thread(id="thread-legacy-team-only", service_id="svc", title="Legacy Team Only")
            context_set = ContextSet(
                id="ctx-legacy-team-only",
                thread_id=thread.id,
                name="default",
                active_node_ids_json="[]",
            )
            conversation = Conversation(thread_id=thread.id, owner_user_id="u1", service_id="svc")
            agent = Agent(owner_user_id="u1", service_id="svc", name="Research Preset", description="preset", model="gpt-4o-mini")
            session.add(thread)
            session.add(context_set)
            session.add(conversation)
            session.add(agent)
            session.commit()

            session.add(
                ConversationAgent(
                    conversation_id=conversation.id,
                    agent_id=agent.id,
                    enabled=True,
                    order_index=0,
                    overrides_json=json.dumps({"role_label": "Researcher"}),
                )
            )
            session.add(
                Node(
                    id="run-legacy-team-only",
                    thread_id=thread.id,
                    type="Run",
                    text="run",
                    payload_json=json.dumps({"status": "queued"}),
                    created_at=base,
                )
            )
            session.commit()

            summary = build_run_studio_summary(session, thread=thread, context_set_id=context_set.id)

        self.assertEqual(len((summary.get("agent_team") or {}).get("items", [])), 1)
        self.assertEqual((summary.get("team_view") or {}).get("count"), 0)
        self.assertEqual((summary.get("why_this_team") or {}).get("selection_explanations"), [])
        self.assertEqual((summary.get("orchestration") or {}).get("mode"), "runtime_managed")
        self.assertEqual((summary.get("collaboration") or {}).get("count"), 0)
        self.assertEqual((summary.get("authority") or {}).get("count"), 0)
        self.assertEqual((summary.get("checkpoints") or {}).get("counts", {}).get("total"), 0)


if __name__ == "__main__":
    unittest.main()
