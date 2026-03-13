from __future__ import annotations

import unittest

from app.models import Agent, Conversation, ConversationAgent, utcnow
from app.routers.agents import _conversation_payload


def make_agent(agent_id: str, *, name: str, owner_user_id: str = "user-1") -> Agent:
    now = utcnow()
    return Agent(
        id=agent_id,
        owner_user_id=owner_user_id,
        service_id="svc-1",
        name=name,
        description="",
        system_prompt="",
        instruction="",
        tools_json="[]",
        model="",
        visibility="private",
        source_agent_id=None,
        system_key=None,
        is_system_default=False,
        is_archived=False,
        created_at=now,
        updated_at=now,
    )


class ThreadTeamSemanticsTests(unittest.TestCase):
    def test_conversation_team_payload_makes_explicit_membership_canonical(self) -> None:
        now = utcnow()
        conversation = Conversation(
            id="conv-1",
            thread_id="thread-1",
            owner_user_id="user-1",
            service_id="svc-1",
            created_at=now,
            updated_at=now,
        )
        planner = make_agent("agent-1", name="Planner")
        reviewer = make_agent("agent-2", name="Reviewer")
        memberships = [
            ConversationAgent(
                id="member-1",
                conversation_id="conv-1",
                agent_id="agent-1",
                enabled=True,
                order_index=0,
                overrides_json='{"role":"planner"}',
                created_at=now,
                updated_at=now,
            ),
            ConversationAgent(
                id="member-2",
                conversation_id="conv-1",
                agent_id="agent-2",
                enabled=False,
                order_index=1,
                overrides_json="{}",
                created_at=now,
                updated_at=now,
            ),
        ]

        payload = _conversation_payload(
            conversation,
            memberships=memberships,
            agents_by_id={"agent-1": planner, "agent-2": reviewer},
            current_user_id="user-1",
            is_admin=False,
        )

        self.assertEqual(payload.get("thread_id"), "thread-1")
        self.assertEqual(payload.get("id"), "conv-1")
        self.assertEqual(payload.get("conversation_team_source"), "goc")
        self.assertEqual(payload.get("agents"), payload.get("team", {}).get("members"))

        team = payload.get("team") or {}
        self.assertEqual(team.get("thread_id"), "thread-1")
        self.assertEqual(team.get("conversation_id"), "conv-1")
        self.assertEqual(team.get("membership_kind"), "explicit")
        self.assertEqual(team.get("counts"), {
            "explicit_memberships": 2,
            "enabled_members": 1,
            "disabled_members": 1,
        })
        self.assertEqual([item.get("agent_id") for item in team.get("enabled_members") or []], ["agent-1"])
        self.assertEqual([item.get("agent_id") for item in team.get("disabled_members") or []], ["agent-2"])
        self.assertEqual(team.get("baseline_policy"), {"mode": "not_modeled"})
        self.assertIsNone(team.get("baseline_agent_ids"))
        self.assertIsNone(team.get("baseline_agents"))

    def test_conversation_team_payload_does_not_imply_missing_baseline_agents_are_errors(self) -> None:
        now = utcnow()
        conversation = Conversation(
            id="conv-empty",
            thread_id="thread-empty",
            owner_user_id="user-1",
            service_id="svc-1",
            created_at=now,
            updated_at=now,
        )

        payload = _conversation_payload(
            conversation,
            memberships=[],
            agents_by_id={},
            current_user_id="user-1",
            is_admin=False,
        )

        team = payload.get("team") or {}
        self.assertEqual(team.get("membership_kind"), "explicit")
        self.assertEqual(team.get("members"), [])
        self.assertEqual(team.get("enabled_members"), [])
        self.assertEqual(team.get("disabled_members"), [])
        self.assertEqual(team.get("counts"), {
            "explicit_memberships": 0,
            "enabled_members": 0,
            "disabled_members": 0,
        })
        self.assertEqual(team.get("baseline_policy"), {"mode": "not_modeled"})
        self.assertNotIn("warnings", team)


if __name__ == "__main__":
    unittest.main()
