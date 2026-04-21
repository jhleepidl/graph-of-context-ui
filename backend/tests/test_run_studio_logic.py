from __future__ import annotations

import json
import unittest
from unittest import mock
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlmodel import SQLModel, Session
from tests.db_test_utils import create_test_engine as create_engine

from app.models import Agent, ContextSet, Conversation, ConversationAgent, Edge, MemoryConflict, MemoryEdge, MemoryLifecycleEvent, MemoryNode, MemoryProjection, MemorySurface, Node, TeamSelectionEvent, Thread
from app.services.graph_projections import memory_context_projection
from app.services.context_cache import clear_global_context_cache
from app.services.conversation_team_config import save_team_config_payload
from app.services.run_studio import (
    _agent_team_summary,
    _build_run_bundle_cross_references,
    _evidence_summary,
    _extract_runtime_team_snapshot,
    _now_panel_summary,
    build_run_studio_evidence,
    build_run_studio_run_bundle,
    build_run_studio_projection_retrieval,
    build_run_studio_summary,
    build_run_studio_trace_scope,
    build_run_studio_audit_timeline,
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

    def test_run_bundle_context_cache_reuses_projection_and_compression_artifacts(self) -> None:
        clear_global_context_cache()
        engine = create_engine()
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            thread = Thread(title="cache-thread")
            session.add(thread)
            session.commit()
            session.refresh(thread)

            context_set = ContextSet(thread_id=thread.id, name="default", active_node_ids_json="[]", version=1)
            session.add(context_set)
            session.add(Node(thread_id=thread.id, type="Message", text="hello", payload_json=json.dumps({"role": "user"})))
            session.commit()

            with mock.patch('app.services.run_studio.build_run_studio_projection_retrieval', wraps=build_run_studio_projection_retrieval) as projection_mock, \
                 mock.patch('app.services.run_studio.build_run_studio_graph_compression', wraps=__import__('app.services.run_studio_graph_compression', fromlist=['build_run_studio_graph_compression']).build_run_studio_graph_compression) as compression_mock:
                first = build_run_studio_run_bundle(session, thread=thread, context_set_id=context_set.id)
                second = build_run_studio_run_bundle(session, thread=thread, context_set_id=context_set.id)

            self.assertIsNotNone(first.get('graph_version'))
            self.assertEqual(first.get('graph_version'), second.get('graph_version'))
            self.assertFalse(bool(first.get('context_cache', {}).get('bundle_cache_hit')))
            self.assertTrue(bool(second.get('context_cache', {}).get('bundle_cache_hit')))
            self.assertEqual(projection_mock.call_count, 1)
            self.assertEqual(compression_mock.call_count, 1)

    def test_cross_reference_summary_links_claims_memory_and_conflicts(self) -> None:
        summary = _build_run_bundle_cross_references(
            evidence={
                "run_id": "run-1",
                "scope": "run",
                "items": [
                    {
                        "claim_node_id": "claim-1",
                        "claim_node_type": "Plan",
                        "claim_text": "Use memory item M1 before finalization",
                        "related_node_ids": ["claim-1", "mem-1", "citation-1"],
                        "conflict_node_ids": ["mem-2"],
                        "evidence_nodes": [{"id": "citation-1", "type": "Citation"}],
                    }
                ],
            },
            memory_graph={
                "run_id": "run-1",
                "scope": "run",
                "projections": [
                    {
                        "role_id": "planner",
                        "visible_nodes": [
                            {"node_id": "mem-1", "surface_id": "shared", "status": "published", "owner_role_id": "planner"}
                        ],
                        "blocked_nodes": [
                            {"node_id": "mem-2", "surface_id": "shared", "status": "conflicted", "owner_role_id": "reviewer"}
                        ],
                    }
                ],
                "edges": [
                    {
                        "id": "edge-1",
                        "edge_type": "supports",
                        "edge_type_title": "Supports",
                        "from_node_id": "mem-1",
                        "to_node_id": "mem-2",
                        "status": "active",
                        "rationale": "mem-1 supports mem-2",
                        "supporting_claim_node_ids": ["claim-1"],
                        "supporting_memory_node_ids": ["mem-1", "mem-2"],
                        "evidence_node_ids": ["citation-1"],
                    }
                ],
                "lifecycle_events": [
                    {
                        "id": "life-1",
                        "node_id": "mem-1",
                        "surface_id": "shared",
                        "event_type": "node_published",
                        "summary": "Published mem-1 from evidence",
                        "supporting_memory_node_ids": ["mem-1"],
                        "supporting_claim_node_ids": ["claim-1"],
                        "supporting_evidence_node_ids": ["citation-1"],
                    }
                ],
                "conflicts": [
                    {
                        "id": "conf-1",
                        "surface_id": "shared",
                        "left_node_id": "mem-1",
                        "right_node_id": "mem-2",
                        "status": "pending",
                        "reason": "conflicting write",
                        "history": [
                            {"event_type": "conflict_detected", "status": "pending", "summary": "Detected conflict"}
                        ],
                        "history_count": 1,
                        "latest_history_event": {"event_type": "conflict_detected", "status": "pending", "summary": "Detected conflict"},
                    }
                ],
            },
            trace_scope={"run_id": "run-1", "scope": "run", "anchor_node_id": "mem-1"},
        )

        self.assertEqual(summary["counts"]["claims_with_memory_links"], 1)
        self.assertEqual(summary["counts"]["claims_with_conflicts"], 1)
        self.assertEqual(summary["claim_links"][0]["related_memory_node_ids"], ["mem-1", "mem-2"])
        self.assertEqual(summary["claim_links"][0]["related_memory_edge_ids"], ["edge-1"])
        self.assertEqual(summary["claim_links"][0]["related_conflict_ids"], ["conf-1"])
        self.assertIn("claim-1", summary["memory_links"][0]["related_claim_node_ids"])
        self.assertIn("edge-1", summary["memory_links"][0]["related_edge_ids"])
        self.assertIn("claim-1", summary["edge_links"][0]["related_claim_node_ids"])
        self.assertIn("conf-1", summary["edge_links"][0]["related_conflict_ids"])
        self.assertIn("claim-1", summary["conflict_links"][0]["related_claim_node_ids"])
        self.assertIn("edge-1", summary["conflict_links"][0]["related_edge_ids"])
        self.assertEqual(summary["counts"]["lifecycle_links"], 1)
        self.assertEqual(summary["counts"]["claims_with_lifecycle_links"], 1)
        self.assertEqual(summary["claim_links"][0]["related_lifecycle_event_ids"], ["life-1"])
        self.assertEqual(summary["lifecycle_links"][0]["related_claim_node_ids"], ["claim-1"])
        self.assertEqual(summary["lifecycle_links"][0]["related_evidence_node_ids"], ["citation-1"])
        self.assertEqual(summary["conflict_links"][0]["suggested_resolution"]["winning_node_id"], "mem-1")
        self.assertIn("linked_claim_support", summary["conflict_links"][0]["suggested_resolution"]["rationale_codes"])
        self.assertEqual(summary["conflict_links"][0]["history_count"], 1)
        self.assertEqual(summary["counts"]["claims_with_edge_links"], 1)
        self.assertEqual(summary["counts"]["edges_with_claims"], 1)
        self.assertEqual(summary["counts"]["conflicts_with_edges"], 1)
        self.assertEqual(summary["counts"]["conflicts_with_suggested_resolution"], 1)
        self.assertEqual(summary["counts"]["conflicts_with_history"], 1)
        self.assertEqual(summary["anchor_related"]["edge_ids"], ["edge-1"])

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
    def test_build_run_studio_evidence_can_scope_to_specific_run(self) -> None:
        engine = create_engine()
        SQLModel.metadata.create_all(engine)
        base = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)

        with Session(engine) as session:
            thread = Thread(id="thread-run-evidence", title="Run Evidence Thread")
            session.add(thread)
            context_set = ContextSet(
                id="ctx-run-evidence",
                thread_id=thread.id,
                name="default",
                active_node_ids_json=json.dumps(["claim-run-a", "evidence-run-a", "claim-run-b"]),
            )
            session.add(context_set)
            session.add(Node(id="run-a", thread_id=thread.id, type="Run", text="Run A", payload_json=json.dumps({"status": "done"}), created_at=base))
            session.add(Node(id="run-b", thread_id=thread.id, type="Run", text="Run B", payload_json=json.dumps({"status": "done"}), created_at=base + timedelta(minutes=5)))
            session.add(Node(id="claim-run-a", thread_id=thread.id, type="Decision", text="Claim A", payload_json=json.dumps({"claim": "Claim A", "run_id": "run-a"}), created_at=base + timedelta(minutes=1)))
            session.add(Node(id="evidence-run-a", thread_id=thread.id, type="Artifact", text="Evidence A", payload_json=json.dumps({"run_id": "run-a"}), created_at=base + timedelta(minutes=2)))
            session.add(Node(id="claim-run-b", thread_id=thread.id, type="Decision", text="Claim B", payload_json=json.dumps({"claim": "Claim B", "run_id": "run-b"}), created_at=base + timedelta(minutes=6)))
            session.add(Edge(id="edge-run-a-claim", thread_id=thread.id, from_id="run-a", to_id="claim-run-a", type="IN_RUN", payload_json="{}", created_at=base + timedelta(minutes=1)))
            session.add(Edge(id="edge-run-b-claim", thread_id=thread.id, from_id="run-b", to_id="claim-run-b", type="IN_RUN", payload_json="{}", created_at=base + timedelta(minutes=6)))
            session.add(Edge(id="edge-evidence-supports", thread_id=thread.id, from_id="evidence-run-a", to_id="claim-run-a", type="SUPPORTS", payload_json="{}", created_at=base + timedelta(minutes=2)))
            session.commit()

            scoped = build_run_studio_evidence(session, thread=thread, context_set_id=context_set.id, run_id="run-a")
            unscoped = build_run_studio_evidence(session, thread=thread, context_set_id=context_set.id)

        self.assertEqual(scoped.get("run_id"), "run-a")
        self.assertEqual(scoped.get("scope"), "run")
        scoped_items = scoped.get("items") or []
        self.assertEqual(len(scoped_items), 1)
        self.assertEqual(scoped_items[0].get("claim_node_id"), "claim-run-a")
        self.assertEqual((scoped_items[0].get("evidence_nodes") or [])[0].get("id"), "evidence-run-a")
        self.assertEqual((scoped.get("counts") or {}).get("claims"), 1)
        self.assertEqual((unscoped.get("counts") or {}).get("claims"), 2)


    def test_build_run_studio_trace_scope_filters_to_requested_run(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            thread = Thread(title="Trace Scope", owner_user_id="u1", service_id="svc")
            session.add(thread)
            session.commit()
            session.refresh(thread)

            run_a = Node(thread_id=thread.id, type="Run", text="Run A", payload_json=json.dumps({}))
            run_b = Node(thread_id=thread.id, type="Run", text="Run B", payload_json=json.dumps({}))
            session.add(run_a)
            session.add(run_b)
            session.flush()

            step_a = Node(thread_id=thread.id, type="Step", text="step a", payload_json=json.dumps({"run_id": run_a.id}))
            step_b = Node(thread_id=thread.id, type="Step", text="step b", payload_json=json.dumps({"run_id": run_b.id}))
            evidence_a = Node(thread_id=thread.id, type="Decision", text="evidence a", payload_json=json.dumps({"run_id": run_a.id}))
            memory_a = Node(thread_id=thread.id, type="ContextSummary", text="memory a", payload_json=json.dumps({"run_id": run_a.id, "surface_id": "surface-a"}))
            session.add(step_a)
            session.add(step_b)
            session.add(evidence_a)
            session.add(memory_a)
            session.flush()

            session.add(Edge(thread_id=thread.id, from_id=run_a.id, to_id=step_a.id, type="HAS_STEP"))
            session.add(Edge(thread_id=thread.id, from_id=step_a.id, to_id=evidence_a.id, type="SUPPORTS"))
            session.add(Edge(thread_id=thread.id, from_id=step_a.id, to_id=memory_a.id, type="DEPENDS"))
            session.add(Edge(thread_id=thread.id, from_id=run_b.id, to_id=step_b.id, type="HAS_STEP"))
            session.commit()

            summary = build_run_studio_trace_scope(session, thread=thread, run_id=run_a.id)

            self.assertEqual(summary["run_id"], run_a.id)
            self.assertEqual(summary["run_node_id"], run_a.id)
            self.assertEqual(summary["anchor_node_id"], run_a.id)
            self.assertIn(step_a.id, summary["step_node_ids"])
            self.assertNotIn(step_b.id, summary["node_ids"])
            self.assertIn(evidence_a.id, summary["evidence_node_ids"])
            self.assertIn(memory_a.id, summary["memory_node_ids"])


    def test_build_run_studio_run_bundle_scopes_all_detail_panels_to_requested_run(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            thread = Thread(title="Run Bundle", owner_user_id="u1", service_id="svc")
            session.add(thread)
            session.commit()
            session.refresh(thread)

            context_set = ContextSet(
                thread_id=thread.id,
                name="default",
                active_node_ids_json=json.dumps([]),
            )
            session.add(context_set)
            session.commit()
            session.refresh(context_set)

            run_a = Node(thread_id=thread.id, type="Run", text="Run A", payload_json=json.dumps({}))
            run_b = Node(thread_id=thread.id, type="Run", text="Run B", payload_json=json.dumps({}))
            session.add(run_a)
            session.add(run_b)
            session.flush()

            step_a = Node(thread_id=thread.id, type="Step", text="step a", payload_json=json.dumps({"run_id": run_a.id}))
            step_b = Node(thread_id=thread.id, type="Step", text="step b", payload_json=json.dumps({"run_id": run_b.id}))
            claim_a = Node(thread_id=thread.id, type="Decision", text="claim a", payload_json=json.dumps({"run_id": run_a.id, "claim": "Claim A"}))
            artifact_a = Node(thread_id=thread.id, type="Artifact", text="artifact a", payload_json=json.dumps({"run_id": run_a.id}))
            session.add(step_a)
            session.add(step_b)
            session.add(claim_a)
            session.add(artifact_a)
            session.flush()

            session.add(Edge(thread_id=thread.id, from_id=run_a.id, to_id=step_a.id, type="HAS_STEP"))
            session.add(Edge(thread_id=thread.id, from_id=run_b.id, to_id=step_b.id, type="HAS_STEP"))
            session.add(Edge(thread_id=thread.id, from_id=artifact_a.id, to_id=claim_a.id, type="SUPPORTS"))

            from app.models import MemorySurface, MemoryNode, MemoryProjection, MemoryEdge

            session.add(MemorySurface(thread_id=thread.id, surface_id="working_memory", title="Working Memory", visibility_scope="shared", policy_json=json.dumps({})))
            memory_node = MemoryNode(
                thread_id=thread.id,
                surface_id="working_memory",
                node_type="context",
                content_json=json.dumps({"summary": "run a memory"}),
                provenance_json=json.dumps({"confidence": 0.9}),
                status="published",
                trust_tier="reported",
                owner_role_id="builder",
                created_run_id=run_a.id,
            )
            session.add(memory_node)
            session.flush()
            session.add(MemoryProjection(
                thread_id=thread.id,
                run_id=run_a.id,
                role_id="builder",
                summary_json=json.dumps({"visible_surface_ids": ["working_memory"], "blocked_surface_ids": [], "surface_reason_map": {}, "node_reason_map": {memory_node.id: "visible"}}),
                visible_node_ids_json=json.dumps([memory_node.id]),
                blocked_node_ids_json=json.dumps([]),
            ))
            session.add(MemoryEdge(
                thread_id=thread.id,
                edge_type="published_from",
                from_node_id=memory_node.id,
                to_node_id=memory_node.id,
                from_surface_id="working_memory",
                to_surface_id="working_memory",
                status="active",
                rationale="final answer published from working memory",
                provenance_json=json.dumps({"supporting_memory_node_ids": [memory_node.id]}),
                created_run_id=run_a.id,
            ))
            session.commit()

            bundle = build_run_studio_run_bundle(session, thread=thread, context_set_id=context_set.id, run_id=run_a.id)

        self.assertEqual(bundle.get("run_id"), run_a.id)
        self.assertEqual((bundle.get("trace_scope") or {}).get("run_node_id"), run_a.id)
        self.assertEqual((bundle.get("evidence") or {}).get("run_id"), run_a.id)
        self.assertEqual((bundle.get("memory_graph") or {}).get("run_id"), run_a.id)
        self.assertEqual((bundle.get("memory_graph") or {}).get("projection_count"), 1)
        self.assertEqual((bundle.get("memory_graph") or {}).get("edge_count"), 1)
        self.assertIn(memory_node.id, ((bundle.get("memory_graph") or {}).get("projections") or [])[0].get("visible_node_ids", []))
        self.assertNotIn(step_b.id, (bundle.get("trace_scope") or {}).get("node_ids", []))


    def test_build_run_studio_run_bundle_reuses_loaded_graph_for_graph_backed_panels(self) -> None:
        engine = create_engine("sqlite://")
        with engine.begin() as conn:
            SQLModel.metadata.create_all(conn)
        with Session(engine) as session:
            thread = Thread(title="Bundle graph reuse")
            session.add(thread)
            session.flush()

            context_set = ContextSet(thread_id=thread.id, name="default", active_node_ids_json=json.dumps([]))
            session.add(context_set)

            run = Node(thread_id=thread.id, type="Run", text="Run", payload_json=json.dumps({"status": "running"}))
            step = Node(thread_id=thread.id, type="Step", text="Step", payload_json=json.dumps({"status": "running", "run_id": "run-1"}))
            session.add(run)
            session.add(step)
            session.flush()
            run.payload_json = json.dumps({"status": "running", "run_id": run.id})
            step.payload_json = json.dumps({"status": "running", "run_id": run.id})
            session.add(Edge(thread_id=thread.id, from_id=run.id, to_id=step.id, type="HAS_STEP"))
            session.commit()

            real_loader = build_run_studio_run_bundle.__globals__["load_thread_graph"]
            with mock.patch("app.services.run_studio.load_thread_graph", wraps=real_loader) as mocked_loader:
                bundle = build_run_studio_run_bundle(session, thread=thread, context_set_id=context_set.id, run_id=run.id)

        self.assertEqual(bundle.get("run_id"), run.id)
        self.assertEqual(mocked_loader.call_count, 1)

    def test_projection_retrieval_marks_scope_first_roles_and_surfaces_timeline(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        base = datetime(2026, 3, 12, 0, 0, tzinfo=timezone.utc)

        with Session(engine) as session:
            thread = Thread(title="Projection Retrieval", owner_user_id="u1", service_id="svc")
            session.add(thread)
            session.commit()
            session.refresh(thread)

            context_set = ContextSet(thread_id=thread.id, name="default", active_node_ids_json=json.dumps([]))
            session.add(context_set)
            session.commit()
            session.refresh(context_set)

            run = Node(
                thread_id=thread.id,
                type="Run",
                text="Run",
                payload_json=json.dumps({
                    "runtime_team_snapshot": {
                        "runtime_agents": [
                            {"instance_id": "rt-planner", "role_id": "planner", "display_label": "Planner"},
                            {"instance_id": "rt-builder", "role_id": "builder", "display_label": "Builder"},
                        ],
                        "scope_specs": [
                            {"scope_id": "scope-planner", "target_instance_id": "rt-planner", "visibility_mode": "scoped", "memory_grants": {"shared_summary": True, "global_memory": True}},
                            {"scope_id": "scope-builder", "target_instance_id": "rt-builder", "visibility_mode": "scoped", "memory_grants": {"shared_summary": True}},
                        ],
                        "materialized_scopes": [
                            {"scope_id": "scope-planner", "context_set_id": "ctx-proj", "active_node_ids": ["seed-1"], "token_estimate": 120, "lineage": {"compiler": "goc_scope_materializer", "selection_summary": "planner projection ready", "selection_confidence": "high"}},
                            {"scope_id": "scope-builder", "context_set_id": "ctx-proj", "active_node_ids": ["seed-2"], "token_estimate": 90, "lineage": {"compiler": "goc_scope_materializer", "selection_summary": "builder projection ready", "selection_confidence": "high"}},
                        ],
                        "context_runtime_mode": "scoped_context",
                    }
                }),
                created_at=base,
            )
            session.add(run)
            session.flush()

            session.add(MemorySurface(thread_id=thread.id, surface_id="working_memory", title="Working Memory", visibility_scope="shared", policy_json=json.dumps({})))
            planner_node = MemoryNode(thread_id=thread.id, surface_id="working_memory", node_type="context", content_json=json.dumps({"summary": "planner memory"}), provenance_json=json.dumps({"confidence": 0.9}), status="published", trust_tier="verified", owner_role_id="planner", created_run_id=run.id, created_at=base + timedelta(minutes=1), updated_at=base + timedelta(minutes=1))
            builder_node = MemoryNode(thread_id=thread.id, surface_id="working_memory", node_type="context", content_json=json.dumps({"summary": "builder memory"}), provenance_json=json.dumps({"confidence": 0.85}), status="published", trust_tier="reported", owner_role_id="builder", created_run_id=run.id, created_at=base + timedelta(minutes=2), updated_at=base + timedelta(minutes=2))
            session.add(planner_node)
            session.add(builder_node)
            session.flush()

            session.add(MemoryProjection(thread_id=thread.id, run_id=run.id, role_id="planner", agent_id="rt-planner", summary_json=json.dumps({"visible_surface_ids": ["working_memory"], "blocked_surface_ids": [], "surface_reason_map": {}, "node_reason_map": {planner_node.id: "visible"}}), visible_node_ids_json=json.dumps([planner_node.id]), blocked_node_ids_json=json.dumps([]), created_at=base + timedelta(minutes=3)))
            session.add(MemoryProjection(thread_id=thread.id, run_id=run.id, role_id="builder", agent_id="rt-builder", summary_json=json.dumps({"visible_surface_ids": ["working_memory"], "blocked_surface_ids": [], "surface_reason_map": {}, "node_reason_map": {builder_node.id: "visible"}}), visible_node_ids_json=json.dumps([builder_node.id]), blocked_node_ids_json=json.dumps([]), created_at=base + timedelta(minutes=3, seconds=30)))
            session.commit()

            projection = build_run_studio_projection_retrieval(session, thread=thread, run_id=run.id)
            bundle = build_run_studio_run_bundle(session, thread=thread, context_set_id=context_set.id, run_id=run.id)

        self.assertEqual(projection.get("run_id"), run.id)
        self.assertTrue(projection.get("summary", {}).get("scope_first_ready"))
        self.assertEqual(projection.get("summary", {}).get("status"), "authoritative")
        self.assertEqual(projection.get("counts", {}).get("roles"), 2)
        self.assertEqual(projection.get("counts", {}).get("authoritative_roles"), 2)
        planner_path = next(item for item in projection.get("planner_system_paths", []) if item.get("role_id") == "planner")
        self.assertEqual(planner_path.get("status"), "authoritative")
        self.assertTrue(planner_path.get("projection_authoritative"))
        timeline = bundle.get("audit_timeline", {})
        self.assertGreaterEqual(timeline.get("category_counts", {}).get("projection_retrieval", 0), 3)
        titles = [item.get("title") for item in timeline.get("items", [])]
        self.assertIn("Projection retrieval evaluated", titles)
        self.assertIn("Retrieval coverage for Planner", titles)
        self.assertIsNotNone(bundle.get("projection_retrieval"))

    def test_build_run_studio_audit_timeline_unifies_selection_trace_memory_and_conflicts(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        base = datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)

        with Session(engine) as session:
            thread = Thread(title="Audit Timeline", owner_user_id="u1", service_id="svc")
            session.add(thread)
            session.commit()
            session.refresh(thread)

            context_set = ContextSet(thread_id=thread.id, name="default", active_node_ids_json=json.dumps([]))
            session.add(context_set)
            session.commit()
            session.refresh(context_set)

            run = Node(thread_id=thread.id, type="Run", text="Run", payload_json=json.dumps({"status": "running", "task": "Audit the runtime"}), created_at=base)
            step = Node(thread_id=thread.id, type="Step", text="Inspect memory", payload_json=json.dumps({"run_id": None, "status": "done", "goal": "Inspect memory"}), created_at=base + timedelta(minutes=1))
            claim = Node(thread_id=thread.id, type="Decision", text="Prefer verified memory", payload_json=json.dumps({"run_id": None, "claim": "Prefer verified memory"}), created_at=base + timedelta(minutes=2))
            artifact = Node(thread_id=thread.id, type="Artifact", text="evidence packet", payload_json=json.dumps({"run_id": None}), created_at=base + timedelta(minutes=3))
            session.add(run)
            session.add(step)
            session.add(claim)
            session.add(artifact)
            session.flush()

            step.payload_json = json.dumps({"run_id": run.id, "status": "done", "goal": "Inspect memory", "agent_id": "planner"})
            claim.payload_json = json.dumps({"run_id": run.id, "claim": "Prefer verified memory"})
            artifact.payload_json = json.dumps({"run_id": run.id})

            session.add(Edge(thread_id=thread.id, from_id=run.id, to_id=step.id, type="HAS_STEP", created_at=base + timedelta(minutes=1)))
            session.add(Edge(thread_id=thread.id, from_id=artifact.id, to_id=claim.id, type="SUPPORTS", created_at=base + timedelta(minutes=3)))

            session.add(MemorySurface(thread_id=thread.id, surface_id="working_memory", title="Working Memory", visibility_scope="shared", policy_json=json.dumps({})))
            memory_a = MemoryNode(thread_id=thread.id, surface_id="working_memory", node_type="context", content_json=json.dumps({"summary": "verified memory node"}), provenance_json=json.dumps({"confidence": 0.9}), status="published", trust_tier="verified", owner_role_id="planner", created_run_id=run.id, created_at=base + timedelta(minutes=4), updated_at=base + timedelta(minutes=4))
            memory_b = MemoryNode(thread_id=thread.id, surface_id="working_memory", node_type="context", content_json=json.dumps({"summary": "conflicting memory node"}), provenance_json=json.dumps({"confidence": 0.5}), status="conflicted", trust_tier="reported", owner_role_id="reviewer", created_run_id=run.id, created_at=base + timedelta(minutes=5), updated_at=base + timedelta(minutes=5))
            session.add(memory_a)
            session.add(memory_b)
            session.flush()

            session.add(MemoryProjection(thread_id=thread.id, run_id=run.id, role_id="planner", summary_json=json.dumps({"visible_surface_ids": ["working_memory"], "blocked_surface_ids": [], "surface_reason_map": {}, "node_reason_map": {memory_a.id: "visible", memory_b.id: "conflict_pending"}}), visible_node_ids_json=json.dumps([memory_a.id]), blocked_node_ids_json=json.dumps([memory_b.id]), created_at=base + timedelta(minutes=6)))
            session.add(MemoryEdge(thread_id=thread.id, edge_type="supports", from_node_id=memory_a.id, to_node_id=memory_b.id, from_surface_id="working_memory", to_surface_id="working_memory", status="active", rationale="verified memory edge", provenance_json=json.dumps({"supporting_claim_node_ids": [claim.id], "evidence_node_ids": [artifact.id], "supporting_memory_node_ids": [memory_a.id, memory_b.id]}), created_run_id=run.id, created_at=base + timedelta(minutes=6, seconds=30), updated_at=base + timedelta(minutes=6, seconds=30)))
            session.add(MemoryLifecycleEvent(thread_id=thread.id, node_id=memory_a.id, surface_id='working_memory', event_type='node_published', from_status='draft', to_status='published', actor='planner', source='runtime', summary='Published verified memory', metadata_json=json.dumps({'supporting_memory_node_ids': [memory_a.id], 'supporting_claim_node_ids': [claim.id], 'supporting_evidence_node_ids': [artifact.id]}), created_run_id=run.id, created_at=base + timedelta(minutes=6, seconds=45)))
            session.add(MemoryConflict(thread_id=thread.id, surface_id="working_memory", left_node_id=memory_a.id, right_node_id=memory_b.id, status="resolved", reason="conflicting write", resolution_json=json.dumps({"status": "resolved", "winning_node_id": memory_a.id, "losing_node_ids": [memory_b.id], "summary": "Prefer verified memory", "rationale_codes": ["higher_trust_tier"], "supporting_claim_node_ids": [claim.id], "supporting_evidence_node_ids": [artifact.id], "supporting_memory_node_ids": [memory_a.id, memory_b.id], "history": [{"event_type": "conflict_detected", "status": "pending", "summary": "Detected conflict", "created_at": (base + timedelta(minutes=7)).isoformat()}, {"event_type": "conflict_resolved", "status": "resolved", "summary": "Prefer verified memory", "winning_node_id": memory_a.id, "losing_node_ids": [memory_b.id], "rationale_codes": ["higher_trust_tier"], "supporting_claim_node_ids": [claim.id], "supporting_evidence_node_ids": [artifact.id], "supporting_memory_node_ids": [memory_a.id, memory_b.id], "created_at": (base + timedelta(minutes=8)).isoformat()}], "merge_history": [{"event_type": "conflict_resolved", "status": "resolved", "summary": "Prefer verified memory", "winning_node_id": memory_a.id, "losing_node_ids": [memory_b.id], "created_at": (base + timedelta(minutes=8)).isoformat()}], "latest_event": {"event_type": "conflict_resolved", "status": "resolved", "summary": "Prefer verified memory", "winning_node_id": memory_a.id, "losing_node_ids": [memory_b.id], "created_at": (base + timedelta(minutes=8)).isoformat()}, "latest_merge_event": {"event_type": "conflict_resolved", "status": "resolved", "summary": "Prefer verified memory", "winning_node_id": memory_a.id, "losing_node_ids": [memory_b.id], "created_at": (base + timedelta(minutes=8)).isoformat()}}), created_at=base + timedelta(minutes=7), updated_at=base + timedelta(minutes=8)))
            session.add(TeamSelectionEvent(thread_id=thread.id, run_id=run.id, task_text="Audit the runtime", selected_blueprint_id="team.audit.v1", recommendation_json=json.dumps({"candidates": [{"template_id": "team.audit.v1", "score": 0.94, "task_archetype": "review_repair", "member_count": 2, "role_ids": ["planner", "reviewer"]}, {"template_id": "team.fast.v1", "score": 0.81, "task_archetype": "review_repair", "member_count": 1, "role_ids": ["builder"]}]}), outcome_json=json.dumps({"success": True, "artifact_quality": 0.92, "quality_score": 0.92}), created_at=base + timedelta(seconds=30)))
            session.commit()

            timeline = build_run_studio_audit_timeline(session, thread=thread, context_set_id=context_set.id, run_id=run.id)
            bundle = build_run_studio_run_bundle(session, thread=thread, context_set_id=context_set.id, run_id=run.id)

        self.assertEqual(timeline["run_id"], run.id)
        self.assertEqual(bundle.get("audit_timeline", {}).get("run_id"), run.id)
        self.assertGreaterEqual(timeline["count"], 7)
        categories = timeline["category_counts"]
        self.assertGreaterEqual(categories.get("selection", 0), 1)
        self.assertGreaterEqual(categories.get("run", 0), 1)
        self.assertGreaterEqual(categories.get("step", 0), 1)
        self.assertGreaterEqual(categories.get("evidence", 0), 1)
        self.assertGreaterEqual(categories.get("memory", 0), 1)
        self.assertGreaterEqual(categories.get("memory_edge", 0), 1)
        self.assertGreaterEqual(categories.get("memory_lifecycle", 0), 1)
        self.assertGreaterEqual(categories.get("conflict", 0), 1)
        self.assertGreaterEqual(categories.get("resolution", 0), 1)
        titles = [item.get("title") for item in timeline.get("items", [])]
        self.assertIn("Team selection recorded", titles)
        self.assertIn("Supports", titles)
        self.assertIn("Node published", titles)
        self.assertIn("Memory conflict detected", titles)
        self.assertIn("Conflict Resolved", titles)
        conflict_events = [item for item in timeline.get("items", []) if item.get("conflict_id")]
        self.assertTrue(any(item.get("metadata", {}).get("supporting_claim_node_ids") == [claim.id] for item in conflict_events if isinstance(item.get("metadata"), dict)))
        lifecycle_events = [item for item in timeline.get("items", []) if item.get("category") == "memory_lifecycle"]
        self.assertTrue(any(item.get("metadata", {}).get("supporting_claim_node_ids") == [claim.id] for item in lifecycle_events if isinstance(item.get("metadata"), dict)))
        self.assertEqual((bundle.get("cross_references") or {}).get("counts", {}).get("lifecycle_links"), 1)
        self.assertEqual(((bundle.get("cross_references") or {}).get("lifecycle_links") or [])[0].get("related_evidence_node_ids"), [artifact.id])
        timestamps = [item.get("timestamp") for item in timeline.get("items", [])]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_build_run_studio_audit_timeline_surfaces_adaptive_team_strategy(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        base = datetime(2026, 3, 11, 12, 0, tzinfo=timezone.utc)

        with Session(engine) as session:
            thread = Thread(title="Strategy Timeline", owner_user_id="u1", service_id="svc")
            conversation = Conversation(thread_id=thread.id, title="Strategy Conversation")
            session.add(thread)
            session.add(conversation)
            session.commit()
            session.refresh(thread)
            session.refresh(conversation)

            context_set = ContextSet(thread_id=thread.id, name="default", active_node_ids_json=json.dumps([]))
            session.add(context_set)
            session.commit()
            session.refresh(context_set)

            run = Node(thread_id=thread.id, type="Run", text="Run", payload_json=json.dumps({"status": "done", "task": "Patch the repo"}), created_at=base)
            session.add(run)
            session.commit()
            session.refresh(run)

            save_team_config_payload(session, thread_id=thread.id, payload={
                "status": "suggested",
                "composition_mode": "structured",
                "proposal_mode": "suggest",
                "active_team": {
                    "team_name": "starter_single",
                    "agents": [
                        {"agent_id": "builder_1", "name": "Builder 1", "role": "builder", "model": "gpt-5-codex"},
                    ],
                    "interaction_spec": {"execution_pattern": "single", "final_answer_owner": "Builder 1"},
                    "planner_metadata": {
                        "adaptive_expansion": {
                            "recommendation": "augment_context",
                            "augmentation": {"score": 2.4, "reasons": ["missing_memory"]},
                            "role_separation": {"score": 0.6, "reasons": ["weak_split_signal"]},
                            "quality": {"quality_gap": 1, "contradiction_pressure": 0, "followup_burden": 1},
                            "capability_gap_summary": "missing_skill:repo.context",
                            "source": "latest_run",
                            "ts": (base + timedelta(minutes=2)).isoformat(),
                        },
                    },
                },
                "pending_team": {
                    "team_name": "starter_plus_reviewer",
                    "agents": [
                        {"agent_id": "builder_1", "name": "Builder 1", "role": "builder", "model": "gpt-5-codex"},
                        {"agent_id": "reviewer_1", "name": "Reviewer 1", "role": "reviewer", "model": "gpt-5.4"},
                    ],
                    "interaction_spec": {"execution_pattern": "sequential_pipeline", "final_answer_owner": "Reviewer 1"},
                    "planner_metadata": {
                        "adaptive_expansion": {
                            "recommendation": "expand_team",
                            "rationale": ["independent_review_needed"],
                            "augmentation": {"score": 1.6, "reasons": ["memory_refresh_already_tried"]},
                            "role_separation": {"score": 3.2, "reasons": ["independent_review_needed"], "independent_review_needed": True, "persistent_split_needed": True},
                            "quality": {"quality_gap": 2, "contradiction_pressure": 1, "followup_burden": 1},
                            "capability_gap_summary": "missing_capability:review.code",
                            "auto_prepared_draft": True,
                            "source": "pending_team_draft",
                            "ts": (base + timedelta(minutes=4)).isoformat(),
                        },
                    },
                },
            })
            session.commit()

            timeline = build_run_studio_audit_timeline(session, thread=thread, context_set_id=context_set.id, run_id=run.id)

        self.assertGreaterEqual(timeline["category_counts"].get("team_strategy", 0), 1)
        linked = timeline.get("linked_summary") or {}
        adaptive = linked.get("adaptive_expansion") or {}
        self.assertEqual(adaptive.get("recommendation"), "expand_team")
        self.assertEqual((adaptive.get("role_separation") or {}).get("independent_review_needed"), True)
        strategy_events = [item for item in timeline.get("items", []) if item.get("category") == "team_strategy"]
        self.assertTrue(any(item.get("status") == "expand_team" for item in strategy_events))
        self.assertTrue(any((item.get("metadata") or {}).get("source") == "pending_team_draft" for item in strategy_events if isinstance(item.get("metadata"), dict)))

    def test_graph_native_compression_preserves_claim_neighborhoods_and_role_views(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        base = datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc)

        with Session(engine) as session:
            thread = Thread(title="Graph Compression", owner_user_id="u1", service_id="svc")
            session.add(thread)
            session.commit()
            session.refresh(thread)

            context_set = ContextSet(thread_id=thread.id, name="default", active_node_ids_json=json.dumps([]))
            session.add(context_set)
            session.commit()
            session.refresh(context_set)

            run = Node(thread_id=thread.id, type="Run", text="Run", payload_json=json.dumps({"status": "running"}), created_at=base)
            claim = Node(thread_id=thread.id, type="Decision", text="Prefer verified memory", payload_json=json.dumps({"run_id": None, "claim": "Prefer verified memory"}), created_at=base + timedelta(minutes=1))
            artifact = Node(thread_id=thread.id, type="Artifact", text="evidence packet", payload_json=json.dumps({"run_id": None}), created_at=base + timedelta(minutes=2))
            session.add(run)
            session.add(claim)
            session.add(artifact)
            session.flush()

            claim.payload_json = json.dumps({"run_id": run.id, "claim": "Prefer verified memory"})
            artifact.payload_json = json.dumps({"run_id": run.id})
            session.add(Edge(thread_id=thread.id, from_id=artifact.id, to_id=claim.id, type="SUPPORTS", created_at=base + timedelta(minutes=2)))

            session.add(MemorySurface(thread_id=thread.id, surface_id="working_memory", title="Working Memory", visibility_scope="shared", policy_json=json.dumps({})))
            preferred = MemoryNode(thread_id=thread.id, surface_id="working_memory", node_type="context", content_json=json.dumps({"summary": "verified memory node"}), provenance_json=json.dumps({"confidence": 0.93}), status="published", trust_tier="verified", owner_role_id="planner", created_run_id=run.id, created_at=base + timedelta(minutes=3), updated_at=base + timedelta(minutes=3))
            contested = MemoryNode(thread_id=thread.id, surface_id="working_memory", node_type="context", content_json=json.dumps({"summary": "reported conflicting node"}), provenance_json=json.dumps({"confidence": 0.41}), status="conflicted", trust_tier="reported", owner_role_id="reviewer", created_run_id=run.id, created_at=base + timedelta(minutes=4), updated_at=base + timedelta(minutes=4))
            extra = MemoryNode(thread_id=thread.id, surface_id="working_memory", node_type="context", content_json=json.dumps({"summary": "extra builder memory"}), provenance_json=json.dumps({"confidence": 0.72}), status="published", trust_tier="derived", owner_role_id="builder", created_run_id=run.id, created_at=base + timedelta(minutes=5), updated_at=base + timedelta(minutes=5))
            session.add(preferred)
            session.add(contested)
            session.add(extra)
            session.flush()

            session.add(MemoryProjection(thread_id=thread.id, run_id=run.id, role_id="planner", agent_id="rt-planner", summary_json=json.dumps({"visible_surface_ids": ["working_memory"], "blocked_surface_ids": [], "surface_reason_map": {}, "node_reason_map": {preferred.id: "visible", contested.id: "conflict_pending", extra.id: "visible"}}), visible_node_ids_json=json.dumps([preferred.id, extra.id]), blocked_node_ids_json=json.dumps([contested.id]), created_at=base + timedelta(minutes=6)))
            session.add(MemoryProjection(thread_id=thread.id, run_id=run.id, role_id="reviewer", agent_id="rt-reviewer", summary_json=json.dumps({"visible_surface_ids": ["working_memory"], "blocked_surface_ids": [], "surface_reason_map": {}, "node_reason_map": {preferred.id: "visible", contested.id: "visible"}}), visible_node_ids_json=json.dumps([preferred.id, contested.id]), blocked_node_ids_json=json.dumps([]), created_at=base + timedelta(minutes=6, seconds=15)))
            session.add(MemoryEdge(thread_id=thread.id, edge_type="supports", from_node_id=preferred.id, to_node_id=contested.id, from_surface_id="working_memory", to_surface_id="working_memory", status="active", rationale="verified memory supports final plan", provenance_json=json.dumps({"supporting_claim_node_ids": [claim.id], "evidence_node_ids": [artifact.id], "supporting_memory_node_ids": [preferred.id, contested.id]}), created_run_id=run.id, created_at=base + timedelta(minutes=6, seconds=30), updated_at=base + timedelta(minutes=6, seconds=30)))
            session.add(MemoryLifecycleEvent(thread_id=thread.id, node_id=preferred.id, surface_id='working_memory', event_type='node_published', from_status='draft', to_status='published', actor='planner', source='runtime', summary='Published verified memory', metadata_json=json.dumps({'supporting_memory_node_ids': [preferred.id], 'supporting_claim_node_ids': [claim.id], 'supporting_evidence_node_ids': [artifact.id]}), created_run_id=run.id, created_at=base + timedelta(minutes=6, seconds=45)))
            session.add(MemoryConflict(thread_id=thread.id, surface_id="working_memory", left_node_id=preferred.id, right_node_id=contested.id, status="pending", reason="conflicting write", resolution_json=json.dumps({"status": "pending", "supporting_claim_node_ids": [claim.id], "supporting_evidence_node_ids": [artifact.id], "supporting_memory_node_ids": [preferred.id, contested.id]}), created_at=base + timedelta(minutes=7), updated_at=base + timedelta(minutes=7)))
            run.payload_json = json.dumps({
                "status": "running",
                "run_id": run.id,
                "runtime_team_snapshot": {
                    "runtime_agents": [
                        {"instance_id": "rt-planner", "role_id": "planner", "display_label": "Planner"},
                        {"instance_id": "rt-reviewer", "role_id": "reviewer", "display_label": "Reviewer"},
                    ],
                    "scope_specs": [
                        {"scope_id": "scope-planner", "target_instance_id": "rt-planner", "visibility_mode": "scoped", "memory_grants": {"shared_summary": True}},
                        {"scope_id": "scope-reviewer", "target_instance_id": "rt-reviewer", "visibility_mode": "scoped", "memory_grants": {"shared_summary": True}},
                    ],
                    "materialized_scopes": [
                        {"scope_id": "scope-planner", "context_set_id": "ctx-graph", "active_node_ids": [claim.id], "lineage": {"compiler": "goc_scope_materializer", "selection_summary": "planner ready", "selection_confidence": "high"}},
                        {"scope_id": "scope-reviewer", "context_set_id": "ctx-graph", "active_node_ids": [claim.id], "lineage": {"compiler": "goc_scope_materializer", "selection_summary": "reviewer ready", "selection_confidence": "high"}},
                    ],
                    "context_runtime_mode": "scoped_context",
                },
            })
            session.commit()

            bundle = build_run_studio_run_bundle(session, thread=thread, context_set_id=context_set.id, run_id=run.id)

        compression = bundle.get("graph_native_compression") or {}
        self.assertEqual(compression.get("run_id"), run.id)
        self.assertEqual(compression.get("summary", {}).get("compression_mode"), "graph_native")
        self.assertGreaterEqual(compression.get("summary", {}).get("cluster_count", 0), 2)
        self.assertGreaterEqual(compression.get("summary", {}).get("core_claim_count", 0), 1)
        self.assertGreaterEqual(compression.get("summary", {}).get("unresolved_conflict_count", 0), 1)
        claim_cluster = next(cluster for cluster in (compression.get("clusters") or []) if cluster.get("cluster_type") == "claim_neighborhood")
        self.assertEqual(claim_cluster.get("representative_claim_node_ids"), [claim.id])
        self.assertIn(preferred.id, claim_cluster.get("support_frontier_node_ids", []))
        self.assertIn(artifact.id, claim_cluster.get("representative_evidence_node_ids", []))
        self.assertTrue(any(conflict_id for conflict_id in claim_cluster.get("conflict_frontier_ids", [])))
        planner_view = next(view for view in (compression.get("role_views") or []) if view.get("role_id") == "planner")
        rendered = planner_view.get("rendered_context") or ""
        self.assertIn("WORKING CLAIMS", rendered)
        self.assertIn("Prefer verified memory", rendered)
        self.assertIn(preferred.id, planner_view.get("support_frontier_node_ids", []))
        self.assertTrue(any(cluster_id.startswith("claim::") for cluster_id in planner_view.get("visible_cluster_ids", [])))


if __name__ == "__main__":
    unittest.main()
