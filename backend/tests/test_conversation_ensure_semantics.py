from __future__ import annotations

import unittest
from contextlib import ExitStack
from unittest.mock import patch

from fastapi import HTTPException
from sqlmodel import SQLModel, Session, select
from tests.db_test_utils import create_test_engine as create_engine

from app.auth import Principal
from app.models import Agent, Conversation, ConversationAgent, Thread
from app.routers import agents as agents_router
from app.schemas import AgentBootstrapDefaultsRequest, ConversationEnsureRequest


class ConversationEnsureSemanticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(self.engine)
        with Session(self.engine) as session:
            session.add(Thread(id="thread-1", service_id="svc-1", title="Thread 1"))
            session.commit()

    def _require_thread_access(self, session: Session, thread_id: str) -> Thread:
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        return thread

    def _route_patches(self) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(patch("app.routers.agents.engine", self.engine))
        stack.enter_context(
            patch(
                "app.routers.agents.get_current_principal",
                return_value=Principal(role="service", service_id="svc-1", user_id="user-1"),
            )
        )
        stack.enter_context(patch("app.routers.agents.get_current_user_id", return_value="user-1"))
        stack.enter_context(patch("app.routers.agents.require_thread_access", side_effect=self._require_thread_access))
        stack.enter_context(patch("app.routers.agents._enforce_conversation_owner_check", return_value=False))
        return stack

    def test_ensure_defaults_to_existence_only(self) -> None:
        with self._route_patches():
            out = agents_router.ensure_conversation(ConversationEnsureRequest(thread_id="thread-1"))

        self.assertEqual(
            out.get("ensure"),
            {
                "conversation_created": True,
                "bootstrap_defaults_requested": False,
                "add_to_conversation_requested": False,
                "bootstrapped_defaults_count": 0,
                "explicit_membership_seeded": False,
            },
        )
        self.assertEqual((out.get("conversation") or {}).get("team", {}).get("members"), [])

        with Session(self.engine) as session:
            self.assertEqual(len(session.exec(select(Conversation)).all()), 1)
            self.assertEqual(len(session.exec(select(ConversationAgent)).all()), 0)
            self.assertEqual(
                len(
                    session.exec(
                        select(Agent)
                        .where(Agent.owner_user_id == "user-1")
                        .where(Agent.source_agent_id.is_not(None))
                    ).all()
                ),
                0,
            )

    def test_ensure_can_bootstrap_defaults_without_creating_explicit_membership(self) -> None:
        with self._route_patches():
            out = agents_router.ensure_conversation(
                ConversationEnsureRequest(
                    thread_id="thread-1",
                    bootstrap_defaults=True,
                )
            )

        ensure = out.get("ensure") or {}
        self.assertTrue(bool(ensure.get("conversation_created")))
        self.assertTrue(bool(ensure.get("bootstrap_defaults_requested")))
        self.assertFalse(bool(ensure.get("add_to_conversation_requested")))
        self.assertGreater(int(ensure.get("bootstrapped_defaults_count") or 0), 0)
        self.assertFalse(bool(ensure.get("explicit_membership_seeded")))
        self.assertEqual((out.get("conversation") or {}).get("team", {}).get("members"), [])

        with Session(self.engine) as session:
            defaults = session.exec(
                select(Agent).where(Agent.is_system_default == True)  # noqa: E712
            ).all()
            installed = session.exec(
                select(Agent)
                .where(Agent.owner_user_id == "user-1")
                .where(Agent.source_agent_id.is_not(None))
                .order_by(Agent.id.asc())
            ).all()
            public_defaults = {row.id: row for row in defaults}

            self.assertGreaterEqual(len(installed), 1)
            self.assertEqual(len(session.exec(select(ConversationAgent)).all()), 0)
            for item in installed:
                self.assertFalse(bool(item.is_system_default))
                self.assertEqual(item.service_id, "svc-1")
                self.assertIn(str(item.source_agent_id or ""), public_defaults)
                self.assertTrue(bool(public_defaults[str(item.source_agent_id)].system_key))

    def test_ensure_can_seed_explicit_membership_when_requested(self) -> None:
        with self._route_patches():
            out = agents_router.ensure_conversation(
                ConversationEnsureRequest(
                    thread_id="thread-1",
                    bootstrap_defaults=True,
                    add_to_conversation=True,
                )
            )

        ensure = out.get("ensure") or {}
        team = (out.get("conversation") or {}).get("team") or {}
        self.assertTrue(bool(ensure.get("bootstrap_defaults_requested")))
        self.assertTrue(bool(ensure.get("add_to_conversation_requested")))
        self.assertTrue(bool(ensure.get("explicit_membership_seeded")))
        self.assertGreater(len(team.get("members") or []), 0)
        self.assertEqual(
            len(team.get("members") or []),
            int((team.get("counts") or {}).get("explicit_memberships") or 0),
        )

        with Session(self.engine) as session:
            installed = session.exec(
                select(Agent)
                .where(Agent.owner_user_id == "user-1")
                .where(Agent.source_agent_id.is_not(None))
            ).all()
            memberships = session.exec(select(ConversationAgent)).all()
            self.assertEqual(len(memberships), len(installed))

    def test_ensure_rejects_membership_seeding_without_bootstrap(self) -> None:
        with self._route_patches():
            with self.assertRaises(HTTPException) as raised:
                agents_router.ensure_conversation(
                    ConversationEnsureRequest(
                        thread_id="thread-1",
                        add_to_conversation=True,
                    )
                )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.detail, "add_to_conversation requires bootstrap_defaults=true")

    def test_thread_team_read_stays_passive_after_non_bootstrap_ensure(self) -> None:
        with self._route_patches():
            agents_router.ensure_conversation(ConversationEnsureRequest(thread_id="thread-1"))
            with Session(self.engine) as session:
                before_memberships = len(session.exec(select(ConversationAgent)).all())
                before_private_copies = len(
                    session.exec(
                        select(Agent)
                        .where(Agent.owner_user_id == "user-1")
                        .where(Agent.source_agent_id.is_not(None))
                    ).all()
                )

            out = agents_router.list_thread_team("thread-1")

            with Session(self.engine) as session:
                after_memberships = len(session.exec(select(ConversationAgent)).all())
                after_private_copies = len(
                    session.exec(
                        select(Agent)
                        .where(Agent.owner_user_id == "user-1")
                        .where(Agent.source_agent_id.is_not(None))
                    ).all()
                )

        self.assertEqual((out.get("conversation") or {}).get("team", {}).get("members"), [])
        self.assertEqual(before_memberships, 0)
        self.assertEqual(after_memberships, 0)
        self.assertEqual(before_private_copies, 0)
        self.assertEqual(after_private_copies, 0)

    def test_bootstrap_defaults_response_preserves_default_copy_lineage(self) -> None:
        with self._route_patches():
            out = agents_router.bootstrap_default_agents(AgentBootstrapDefaultsRequest())

        installed = out.get("installed") or []
        self.assertGreaterEqual(len(installed), 1)

        with Session(self.engine) as session:
            public_defaults = {
                row.id: row
                for row in session.exec(
                    select(Agent).where(Agent.is_system_default == True)  # noqa: E712
                ).all()
            }

        for item in installed:
            source_agent_id = str(item.get("source_agent_id") or "")
            self.assertTrue(source_agent_id)
            self.assertFalse(bool(item.get("is_system_default")))
            self.assertEqual(item.get("service_id"), "svc-1")
            self.assertIn(source_agent_id, public_defaults)
            self.assertTrue(bool(public_defaults[source_agent_id].system_key))


if __name__ == "__main__":
    unittest.main()
