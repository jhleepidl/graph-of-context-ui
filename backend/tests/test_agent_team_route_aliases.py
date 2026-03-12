from __future__ import annotations

import unittest
from unittest.mock import patch

from app.routers import agents as agents_router
from app.schemas import (
    ConversationAgentCreateRequest,
    ConversationAgentPatchRequest,
    ConversationAgentReorderRequest,
)


class AgentTeamRouteAliasTests(unittest.TestCase):
    def test_thread_team_canonical_routes_delegate_to_existing_thread_handlers(self) -> None:
        create_body = ConversationAgentCreateRequest(agent_id="agent-1")
        reorder_body = ConversationAgentReorderRequest(agent_ids=["agent-1"])
        patch_body = ConversationAgentPatchRequest(enabled=True)

        with patch("app.routers.agents.list_conversation_agents", return_value={"ok": True}) as mocked_list:
            out = agents_router.list_thread_team("thread-1")
            self.assertEqual(out, {"ok": True})
            mocked_list.assert_called_once_with("thread-1")

        with patch("app.routers.agents.add_conversation_agent", return_value={"ok": True}) as mocked_add:
            out = agents_router.add_thread_team_member("thread-1", create_body)
            self.assertEqual(out, {"ok": True})
            mocked_add.assert_called_once_with("thread-1", create_body)

        with patch("app.routers.agents.reorder_conversation_agents", return_value={"ok": True}) as mocked_reorder:
            out = agents_router.reorder_thread_team("thread-1", reorder_body)
            self.assertEqual(out, {"ok": True})
            mocked_reorder.assert_called_once_with("thread-1", reorder_body)

        with patch("app.routers.agents.patch_conversation_agent", return_value={"ok": True}) as mocked_patch:
            out = agents_router.patch_thread_team_member("thread-1", "agent-1", patch_body)
            self.assertEqual(out, {"ok": True})
            mocked_patch.assert_called_once_with("thread-1", "agent-1", patch_body)

        with patch("app.routers.agents.delete_conversation_agent", return_value={"ok": True}) as mocked_delete:
            out = agents_router.delete_thread_team_member("thread-1", "agent-1")
            self.assertEqual(out, {"ok": True})
            mocked_delete.assert_called_once_with("thread-1", "agent-1")

    def test_conversation_team_paths_remain_compatibility_aliases(self) -> None:
        create_body = ConversationAgentCreateRequest(agent_id="agent-1")
        reorder_body = ConversationAgentReorderRequest(agent_ids=["agent-1"])
        patch_body = ConversationAgentPatchRequest(enabled=True)

        with patch("app.routers.agents.list_thread_team", return_value={"ok": True}) as mocked_list:
            out = agents_router.get_conversation_team("thread-1")
            self.assertEqual(out, {"ok": True})
            mocked_list.assert_called_once_with("thread-1")

        with patch("app.routers.agents.add_thread_team_member", return_value={"ok": True}) as mocked_add:
            out = agents_router.add_conversation_team_member("thread-1", create_body)
            self.assertEqual(out, {"ok": True})
            mocked_add.assert_called_once_with("thread-1", create_body)

        with patch("app.routers.agents.reorder_thread_team", return_value={"ok": True}) as mocked_reorder:
            out = agents_router.reorder_conversation_team("thread-1", reorder_body)
            self.assertEqual(out, {"ok": True})
            mocked_reorder.assert_called_once_with("thread-1", reorder_body)

        with patch("app.routers.agents.patch_thread_team_member", return_value={"ok": True}) as mocked_patch:
            out = agents_router.patch_conversation_team_member("thread-1", "agent-1", patch_body)
            self.assertEqual(out, {"ok": True})
            mocked_patch.assert_called_once_with("thread-1", "agent-1", patch_body)

        with patch("app.routers.agents.delete_thread_team_member", return_value={"ok": True}) as mocked_delete:
            out = agents_router.delete_conversation_team_member("thread-1", "agent-1")
            self.assertEqual(out, {"ok": True})
            mocked_delete.assert_called_once_with("thread-1", "agent-1")


if __name__ == "__main__":
    unittest.main()
