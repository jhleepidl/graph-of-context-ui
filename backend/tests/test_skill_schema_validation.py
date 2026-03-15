from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlmodel import SQLModel, Session, create_engine

from app.schemas import RunCapabilityProjection
from app.models import ContextSet, Node, Thread
from app.services import run_studio as run_studio_service
from app.services import runtime_snapshot as runtime_snapshot_service
from app.services.context_packs import extract_context_pack_summaries
from app.services.run_skill_summary import (
    build_run_skill_summary,
    build_thread_context_pack_summary,
    build_thread_skill_usage_summary,
)
from app.services.run_studio import _extract_runtime_team_snapshot, build_run_studio_summary
from app.services.skill_projections import (
    extract_runtime_agents_with_skills,
    extract_runtime_snapshot_with_members,
    extract_skill_usage_events,
)
from app.services.skill_registry import get_skill_package, list_skill_registry


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


class SkillSchemaValidationTests(unittest.TestCase):
    def test_runtime_team_items_include_attached_skills_and_no_skill_member(self) -> None:
        base = datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node(
                "run-runtime-team",
                "Run",
                payload={
                    "runtime_team_snapshot": {
                        "runtime_agents": [
                            {
                                "runtime_instance_id": "rt-analyst-1",
                                "role_label": "Analyst",
                                "context_pack_id": "cp-analyst",
                                "attached_skills": [
                                    {
                                        "skill_id": "skill.claim_evidence_audit.v1",
                                        "load_level": "instructions",
                                        "selected_by": "policy",
                                        "selection_reason": "confidence dropped",
                                    }
                                ],
                            },
                            {
                                "runtime_instance_id": "rt-writer-1",
                                "role_label": "Writer",
                                "status": "running",
                            },
                        ]
                    }
                },
                created_at=base,
            )
        ]

        projection = extract_runtime_agents_with_skills(nodes)
        items = projection.get("items", [])
        self.assertEqual(len(items), 2)

        analyst = next(item for item in items if item.get("runtime_instance_id") == "rt-analyst-1")
        writer = next(item for item in items if item.get("runtime_instance_id") == "rt-writer-1")

        self.assertEqual(len(analyst.get("attached_skills") or []), 1)
        self.assertEqual(analyst["attached_skills"][0]["skill_id"], "skill.claim_evidence_audit.v1")
        self.assertEqual(analyst["attached_skills"][0]["load_level"], "instructions")
        self.assertEqual(analyst.get("context_pack_id"), "cp-analyst")

        self.assertEqual(writer.get("attached_skills"), [])
        self.assertEqual(writer.get("runtime_status"), "running")

    def test_runtime_team_items_accept_team_plan_v2_agent_fields(self) -> None:
        nodes = [
            make_node(
                "run-runtime-team-v2",
                "Run",
                payload={
                    "runtime_team_snapshot": {
                        "runtime_agents": [
                            {
                                "instance_id": "rt-v2-1",
                                "slot_id": "slot-1",
                                "role_id": "role-1",
                                "display_label": "Analyst",
                                "preset_id": "preset.analyst",
                                "synthesized": False,
                                "selection_reason": "Preset covers research",
                                "attached_skill_ids": ["skill.claim_evidence_audit.v1"],
                                "context_pack_id": "cp-v2-1",
                                "authority_profile_id": "authority.read_only",
                            }
                        ]
                    }
                },
            )
        ]

        projection = extract_runtime_agents_with_skills(nodes)
        item = (projection.get("items") or [])[0]
        self.assertEqual(item.get("runtime_instance_id"), "rt-v2-1")
        self.assertEqual(item.get("slot_id"), "slot-1")
        self.assertEqual(item.get("role_id"), "role-1")
        self.assertEqual(item.get("display_label"), "Analyst")
        self.assertEqual(item.get("preset_id"), "preset.analyst")
        self.assertFalse(bool(item.get("synthesized")))
        self.assertEqual(item.get("selection_reason"), "Preset covers research")
        self.assertEqual(item.get("attached_skill_ids"), ["skill.claim_evidence_audit.v1"])
        self.assertEqual(item.get("context_pack_id"), "cp-v2-1")
        self.assertEqual(item.get("authority_profile_id"), "authority.read_only")

    def test_context_pack_summaries_include_skill_levels_and_degrade_gracefully(self) -> None:
        base = datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node(
                "run-context-pack",
                "Run",
                payload={
                    "run_id": "run-context-pack",
                    "context_packs": [
                        {
                            "context_pack_id": "cp-rich",
                            "scope": "runtime",
                            "target_runtime_agent_instance_id": "rt-analyst-1",
                            "shared_items_count": 2,
                            "role_specific_items_count": 1,
                            "skill_items": [
                                {
                                    "skill_id": "skill.context_selection_policy.v1",
                                    "load_level": "instructions",
                                    "count": 3,
                                }
                            ],
                            "missing_items": ["market-data"],
                            "conflicts": ["policy-mismatch"],
                        },
                        {"context_pack_id": "cp-empty"},
                    ],
                },
                created_at=base,
            )
        ]

        items = extract_context_pack_summaries(nodes)
        self.assertGreaterEqual(len(items), 2)

        rich = next(item for item in items if item.get("context_pack_id") == "cp-rich")
        empty = next(item for item in items if item.get("context_pack_id") == "cp-empty")

        self.assertEqual(rich.get("scope"), "runtime")
        self.assertEqual(rich.get("shared_items_count"), 2)
        self.assertEqual(rich.get("role_specific_items_count"), 1)
        self.assertEqual(rich["skill_items"][0]["skill_id"], "skill.context_selection_policy.v1")
        self.assertEqual(rich["skill_items"][0]["load_level"], "instructions")
        self.assertIn("market-data", rich.get("missing_items") or [])
        self.assertIn("policy-mismatch", rich.get("conflicts") or [])

        self.assertEqual(empty.get("shared_items_count"), 0)
        self.assertEqual(empty.get("role_specific_items_count"), 0)
        self.assertEqual(empty.get("skill_items"), [])
        self.assertEqual(empty.get("missing_items"), [])
        self.assertEqual(empty.get("conflicts"), [])

    def test_skill_usage_events_normalize_sparse_and_mixed_payloads(self) -> None:
        base = datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node(
                "run-usage-main",
                "Run",
                payload={"run_id": "run-usage-main", "status": "running"},
                created_at=base,
            ),
            make_node(
                "step-usage-1",
                "Step",
                payload={
                    "run_id": "run-usage-main",
                    "skill_usage_events": [
                        {
                            "skill_id": "skill.context_selection_policy.v1",
                            "type": "selected",
                            "reason": "policy gate triggered",
                            "loadLevel": "instruction",
                        }
                    ],
                },
                created_at=base + timedelta(seconds=1),
            ),
            make_node(
                "step-usage-2",
                "Step",
                payload={
                    "run_id": "run-usage-main",
                    "skill_usage": {
                        "skill.claim_evidence_audit.v1": "escalated",
                    },
                },
                created_at=base + timedelta(seconds=2),
            ),
            make_node(
                "step-usage-3",
                "Step",
                payload={
                    "run_id": "run-usage-main",
                    "skill_id": "skill.telegram_briefing.v1",
                    "skill_event_type": "used",
                    "summary": "brief sent",
                },
                created_at=base + timedelta(seconds=3),
            ),
        ]

        events = extract_skill_usage_events(nodes)
        self.assertGreaterEqual(len(events), 3)

        selected = next(event for event in events if event.get("skill_id") == "skill.context_selection_policy.v1")
        escalated = next(event for event in events if event.get("skill_id") == "skill.claim_evidence_audit.v1")
        used = next(event for event in events if event.get("skill_id") == "skill.telegram_briefing.v1")

        self.assertEqual(selected.get("event_type"), "selected")
        self.assertEqual(selected.get("load_level"), "instructions")
        self.assertIn("policy gate", str(selected.get("selection_reason") or ""))
        self.assertTrue(str(escalated.get("timestamp") or "").strip())
        self.assertEqual(escalated.get("event_type"), "escalated")
        self.assertEqual(used.get("event_type"), "used")
        self.assertIn("brief", str(used.get("payload_summary") or ""))

    def test_run_skill_summary_and_detail_shapes_with_and_without_skill_payloads(self) -> None:
        base = datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc)
        nodes_with_skills = [
            make_node(
                "run-schema-main",
                "Run",
                payload={
                    "runtime_team_snapshot": {
                        "runtime_agents": [
                            {
                                "runtime_instance_id": "rt-1",
                                "role_label": "Analyst",
                                "attached_skills": [{"skill_id": "skill.claim_evidence_audit.v1"}],
                            }
                        ]
                    },
                    "context_pack": {
                        "context_pack_id": "cp-schema",
                        "scope": "runtime",
                        "skill_items": [{"skill_id": "skill.claim_evidence_audit.v1", "load_level": "resources", "count": 2}],
                    },
                },
                created_at=base,
            ),
            make_node(
                "step-schema-main",
                "Step",
                payload={
                    "run_id": "run-schema-main",
                    "status": "running",
                    "skill_usage_events": [{"skill_id": "skill.claim_evidence_audit.v1", "event_type": "used"}],
                },
                created_at=base + timedelta(seconds=1),
            ),
        ]

        run_summary = build_run_skill_summary(nodes=nodes_with_skills, edges=[], run_id="run-schema-main")
        validated = RunCapabilityProjection.model_validate(run_summary)
        self.assertEqual(run_summary.get("run_id"), "run-schema-main")
        self.assertEqual(validated.run_id, "run-schema-main")
        self.assertGreaterEqual(len(run_summary.get("runtime_agents") or []), 1)
        self.assertGreaterEqual(len(run_summary.get("attached_skills") or []), 1)
        self.assertGreaterEqual(len(run_summary.get("context_packs") or []), 1)
        self.assertGreaterEqual(len(run_summary.get("skill_usage") or []), 1)
        self.assertIsNotNone(validated.team_view)

        packs_detail = build_thread_context_pack_summary(nodes=nodes_with_skills, edges=[], run_id="run-schema-main")
        usage_detail = build_thread_skill_usage_summary(nodes=nodes_with_skills, edges=[], run_id="run-schema-main")
        self.assertEqual(packs_detail.get("run_id"), "run-schema-main")
        self.assertIn("items", packs_detail)
        self.assertIn("count", packs_detail)
        self.assertEqual(usage_detail.get("run_id"), "run-schema-main")
        self.assertIn("items", usage_detail)
        self.assertIn("count", usage_detail)

        nodes_without_skills = [
            make_node(
                "run-no-skill",
                "Run",
                payload={"status": "running"},
                created_at=base + timedelta(seconds=5),
            ),
            make_node(
                "step-no-skill",
                "Step",
                payload={"run_id": "run-no-skill", "status": "done"},
                created_at=base + timedelta(seconds=6),
            ),
        ]
        no_skill_summary = build_run_skill_summary(nodes=nodes_without_skills, edges=[], run_id="run-no-skill")
        self.assertEqual(no_skill_summary.get("attached_skills"), [])
        self.assertEqual(no_skill_summary.get("context_packs"), [])
        self.assertEqual(no_skill_summary.get("skill_usage"), [])

    def test_run_studio_summary_is_stable_when_skill_fields_absent(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        base = datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc)

        with Session(engine) as session:
            thread = Thread(id="thread-no-skill-summary", service_id="svc", title="No Skill Summary")
            context_set = ContextSet(id="ctx-no-skill-summary", thread_id=thread.id, name="default", active_node_ids_json="[]")
            run_node = Node(
                id="run-no-skill-summary",
                thread_id=thread.id,
                type="Run",
                text="run",
                payload_json=json.dumps({"status": "running"}),
                created_at=base,
            )
            step_node = Node(
                id="step-no-skill-summary",
                thread_id=thread.id,
                type="Step",
                text="step",
                payload_json=json.dumps({"run_id": "run-no-skill-summary", "status": "running", "agent_id": "worker-a"}),
                created_at=base + timedelta(seconds=1),
            )
            session.add(thread)
            session.add(context_set)
            session.add(run_node)
            session.add(step_node)
            session.commit()

            summary = build_run_studio_summary(session, thread=thread, context_set_id=context_set.id)
            self.assertIn("current_run_skills", summary)
            self.assertIn("skill_counts", summary)
            self.assertEqual(summary["current_run_skills"].get("attached_skills"), [])
            self.assertEqual(summary["current_run_skills"].get("context_packs"), [])
            self.assertEqual(summary["current_run_skills"].get("skill_usage"), [])
            self.assertIn("agent_team", summary)

    def test_run_studio_summary_includes_skill_aware_fields_when_present(self) -> None:
        engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(engine)
        base = datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc)

        with Session(engine) as session:
            thread = Thread(id="thread-skill-summary", service_id="svc", title="Skill Summary")
            context_set = ContextSet(id="ctx-skill-summary", thread_id=thread.id, name="default", active_node_ids_json="[]")
            run_node = Node(
                id="run-skill-summary",
                thread_id=thread.id,
                type="Run",
                text="run",
                payload_json=json.dumps(
                    {
                        "runtime_team_snapshot": {
                            "runtime_agents": [
                                {
                                    "runtime_instance_id": "rt-skill-1",
                                    "role_label": "Analyst",
                                    "attached_skills": [{"skill_id": "skill.claim_evidence_audit.v1", "load_level": "instruction"}],
                                }
                            ]
                        },
                        "context_packs": [
                            {
                                "context_pack_id": "cp-skill-summary",
                                "scope": "runtime",
                                "skill_items": [
                                    {"skill_id": "skill.claim_evidence_audit.v1", "load_level": "instruction", "count": 2}
                                ],
                            }
                        ],
                    }
                ),
                created_at=base,
            )
            step_node = Node(
                id="step-skill-summary",
                thread_id=thread.id,
                type="Step",
                text="step",
                payload_json=json.dumps(
                    {
                        "run_id": "run-skill-summary",
                        "status": "running",
                        "agent_id": "rt-skill-1",
                        "skill_usage_events": [
                            {"skill_id": "skill.claim_evidence_audit.v1", "event_type": "used", "summary": "audited claims"}
                        ],
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
            current_run_skills = summary.get("current_run_skills") or {}
            self.assertEqual(current_run_skills.get("run_id"), "run-skill-summary")
            self.assertGreaterEqual(len(current_run_skills.get("attached_skills") or []), 1)
            self.assertGreaterEqual(len(current_run_skills.get("context_packs") or []), 1)
            self.assertGreaterEqual(len(current_run_skills.get("skill_usage") or []), 1)
            self.assertGreaterEqual(len(current_run_skills.get("skill_packages") or []), 1)

            attached = (current_run_skills.get("attached_skills") or [])[0]
            context_pack = (current_run_skills.get("context_packs") or [])[0]
            usage = (current_run_skills.get("skill_usage") or [])[0]
            self.assertEqual(attached.get("skill_id"), "skill.claim_evidence_audit.v1")
            self.assertEqual(attached.get("load_level"), "instructions")
            self.assertEqual(context_pack.get("context_pack_id"), "cp-skill-summary")
            self.assertEqual((context_pack.get("skill_items") or [])[0].get("load_level"), "instructions")
            self.assertEqual(usage.get("event_type"), "used")

    def test_skill_registry_metadata_shapes_and_fallback(self) -> None:
        listed = list_skill_registry(include_defaults=True)
        self.assertGreater(len(listed), 0)
        first = listed[0]
        self.assertTrue(str(first.get("id") or "").strip())
        self.assertTrue(str(first.get("slug") or "").strip())
        self.assertTrue(str(first.get("name") or "").strip())
        self.assertTrue(str(first.get("status") or "").strip())

        fallback = get_skill_package("skill.unknown.runtime_case.v1", include_defaults=True)
        self.assertIsNotNone(fallback)
        assert fallback is not None
        self.assertEqual(fallback.get("id"), "skill.unknown.runtime_case.v1")
        self.assertEqual(fallback.get("slug"), "skill.unknown.runtime_case.v1")

    def test_runtime_snapshot_centralization_consistency(self) -> None:
        # run_studio consumes the centralized runtime snapshot helper directly
        self.assertIs(
            run_studio_service._extract_runtime_team_snapshot,
            runtime_snapshot_service.extract_runtime_team_snapshot,
        )

        base = datetime(2026, 3, 11, 0, 0, tzinfo=timezone.utc)
        nodes = [
            make_node(
                "run-runtime-centralized",
                "Run",
                payload={
                    "runtime_agents": [{"runtime_instance_id": "rt-fallback", "role_label": "Fallback"}],
                    "runtime_team_snapshot": {
                        "runtime_agents": [{"runtime_instance_id": "rt-canonical", "role_label": "Canonical"}],
                    },
                },
                created_at=base,
            )
        ]

        snapshot_from_run_studio = _extract_runtime_team_snapshot(nodes)
        snapshot_from_skill_projection = extract_runtime_snapshot_with_members(nodes)
        self.assertEqual(snapshot_from_run_studio, snapshot_from_skill_projection)
        assert snapshot_from_run_studio is not None

        skill_projection = extract_runtime_agents_with_skills(nodes)
        self.assertEqual(skill_projection.get("snapshot_source_key"), "runtime_team_snapshot.runtime_agents")
        self.assertEqual(skill_projection["items"][0]["runtime_instance_id"], "rt-canonical")


if __name__ == "__main__":
    unittest.main()
