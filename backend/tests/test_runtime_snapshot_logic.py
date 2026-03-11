from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.services.runtime_snapshot import (
    extract_runtime_members_from_container,
    extract_runtime_team_snapshot,
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


if __name__ == "__main__":
    unittest.main()

