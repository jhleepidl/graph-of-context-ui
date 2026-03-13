from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlmodel import Session

from app.models import Agent, ContextSet, Conversation, ConversationAgent, Node, Thread


@dataclass(frozen=True)
class FixtureNode:
    id: str
    type: str
    text: str
    payload_json: str
    created_at: datetime


@dataclass(frozen=True)
class ConversationMemberSeed:
    name: str
    role_label: str | None = None
    description: str = ""
    model: str = "gpt-4o-mini"
    overrides: dict[str, Any] | None = None


@dataclass(frozen=True)
class RuntimeContractScenario:
    name: str
    run_id: str
    authority: dict[str, Any]
    nodes: list[FixtureNode]
    membership_agents: list[ConversationMemberSeed]

    def seed_run_studio(
        self,
        session: Session,
        *,
        thread_id: str | None = None,
        context_set_id: str | None = None,
    ) -> tuple[Thread, ContextSet]:
        thread = Thread(
            id=thread_id or f"{self.name}-thread",
            service_id="svc",
            title=self.name.replace("_", " ").title(),
        )
        context_set = ContextSet(
            id=context_set_id or f"{self.name}-context",
            thread_id=thread.id,
            name="default",
            active_node_ids_json="[]",
        )
        session.add(thread)
        session.add(context_set)
        session.flush()

        if self.membership_agents:
            conversation = Conversation(
                thread_id=thread.id,
                owner_user_id="u1",
                service_id=thread.service_id,
            )
            session.add(conversation)
            session.flush()

            for index, member in enumerate(self.membership_agents):
                agent = Agent(
                    owner_user_id="u1",
                    service_id=thread.service_id,
                    name=member.name,
                    description=member.description or member.name,
                    model=member.model,
                )
                session.add(agent)
                session.flush()
                session.add(
                    ConversationAgent(
                        conversation_id=conversation.id,
                        agent_id=agent.id,
                        enabled=True,
                        order_index=index,
                        overrides_json=json.dumps(
                            {
                                "role_label": member.role_label or member.name,
                                **(member.overrides or {}),
                            }
                        ),
                    )
                )

        for raw in self.nodes:
            session.add(
                Node(
                    id=raw.id,
                    thread_id=thread.id,
                    type=raw.type,
                    text=raw.text,
                    payload_json=raw.payload_json,
                    created_at=raw.created_at,
                )
            )

        session.commit()
        return thread, context_set


def make_fixture_node(
    node_id: str,
    node_type: str,
    *,
    text: str = "",
    payload: dict[str, Any] | None = None,
    created_at: datetime | None = None,
) -> FixtureNode:
    return FixtureNode(
        id=node_id,
        type=node_type,
        text=text,
        payload_json=json.dumps(payload or {}),
        created_at=created_at or datetime.now(timezone.utc),
    )


def canonical_runtime_authority(
    *,
    mode: str,
    plan_source: str,
    context_source: str,
    agent_catalog_source: str,
    conversation_team_source: str,
    skill_catalog_source: str,
    degraded_mode: bool = False,
    fallback_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "plan_source": plan_source,
        "context_source": context_source,
        "agent_catalog_source": agent_catalog_source,
        "conversation_team_source": conversation_team_source,
        "skill_catalog_source": skill_catalog_source,
        "degraded_mode": degraded_mode,
        "fallback_reason": fallback_reason,
    }


def runtime_skill_package(
    skill_id: str,
    *,
    name: str,
    capability_tags: list[str] | None = None,
    compatible_roles: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": skill_id,
        "name": name,
        "version": "v1",
        "capability_tags": list(capability_tags or []),
        "compatible_roles": list(compatible_roles or []),
    }


def _build_run_step_nodes(
    *,
    name: str,
    authority: dict[str, Any],
    base: datetime,
    step_agent_id: str,
    runtime_team_snapshot: dict[str, Any] | None = None,
    context_packs: list[dict[str, Any]] | None = None,
    runtime_skill_packages: list[dict[str, Any]] | None = None,
    skill_usage_events: list[dict[str, Any]] | None = None,
    step_authority: dict[str, Any] | None = None,
    run_extra_payload: dict[str, Any] | None = None,
    step_extra_payload: dict[str, Any] | None = None,
) -> list[FixtureNode]:
    run_id = f"run-{name}"
    run_payload: dict[str, Any] = {
        "status": "running",
        "runtime_authority": authority,
    }
    if runtime_team_snapshot is not None:
        run_payload["runtime_team_snapshot"] = runtime_team_snapshot
    if context_packs:
        run_payload["context_packs"] = context_packs
    if runtime_skill_packages:
        run_payload["runtime"] = {"skill_packages": runtime_skill_packages}
    if run_extra_payload:
        run_payload.update(run_extra_payload)

    step_payload: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "agent_id": step_agent_id,
    }
    if skill_usage_events:
        step_payload["skill_usage_events"] = skill_usage_events
    if step_authority is not None:
        step_payload["runtime_authority"] = step_authority
    if step_extra_payload:
        step_payload.update(step_extra_payload)

    return [
        make_fixture_node(
            run_id,
            "Run",
            text=f"{name} run",
            payload=run_payload,
            created_at=base,
        ),
        make_fixture_node(
            f"step-{name}",
            "Step",
            text=f"{name} step",
            payload=step_payload,
            created_at=base + timedelta(seconds=1),
        ),
    ]


def standalone_runtime_contract_scenario(*, base: datetime | None = None) -> RuntimeContractScenario:
    base = base or datetime(2026, 3, 13, 0, 0, tzinfo=timezone.utc)
    authority = canonical_runtime_authority(
        mode="standalone",
        plan_source="local",
        context_source="local",
        agent_catalog_source="local",
        conversation_team_source="local",
        skill_catalog_source="local",
    )
    custom_skill_id = "skill.runtime_custom_audit.v1"
    nodes = _build_run_step_nodes(
        name="standalone",
        authority=authority,
        base=base,
        step_agent_id="rt-standalone-1",
        runtime_team_snapshot={
            "runtime_agents": [
                {
                    "runtime_instance_id": "rt-standalone-1",
                    "role_label": "Standalone Worker",
                    "attached_skills": [
                        {
                            "skill_id": custom_skill_id,
                            "load_level": "instructions",
                            "selected_by": "runtime",
                        }
                    ],
                    "context_pack_id": "cp-standalone",
                }
            ]
        },
        context_packs=[
            {
                "context_pack_id": "cp-standalone",
                "scope": "runtime",
                "target_runtime_agent_instance_id": "rt-standalone-1",
                "shared_items_count": 1,
                "role_specific_items_count": 1,
                "skill_items": [{"skill_id": custom_skill_id, "load_level": "instructions", "count": 1}],
            }
        ],
        runtime_skill_packages=[
            runtime_skill_package(
                custom_skill_id,
                name="Runtime Custom Audit",
                capability_tags=["runtime", "audit"],
                compatible_roles=["analyst"],
            )
        ],
        skill_usage_events=[
            {
                "skill_id": custom_skill_id,
                "event_type": "used",
                "timestamp": "2026-03-13T00:00:01Z",
                "summary": "local runtime audit executed",
            }
        ],
    )
    return RuntimeContractScenario(
        name="standalone_contract",
        run_id="run-standalone",
        authority=authority,
        nodes=nodes,
        membership_agents=[],
    )


def goc_runtime_contract_scenario(*, base: datetime | None = None) -> RuntimeContractScenario:
    base = base or datetime(2026, 3, 13, 1, 0, tzinfo=timezone.utc)
    authority = canonical_runtime_authority(
        mode="goc",
        plan_source="goc",
        context_source="goc",
        agent_catalog_source="goc",
        conversation_team_source="goc",
        skill_catalog_source="goc",
    )
    nodes = _build_run_step_nodes(
        name="goc",
        authority=authority,
        base=base,
        step_agent_id="Research Coordinator",
        context_packs=[
            {
                "context_pack_id": "cp-goc",
                "scope": "runtime",
                "shared_items_count": 2,
                "role_specific_items_count": 0,
                "skill_items": [{"skill_id": "skill.claim_evidence_audit.v1", "load_level": "instructions", "count": 2}],
            }
        ],
        skill_usage_events=[
            {
                "skill_id": "skill.claim_evidence_audit.v1",
                "event_type": "used",
                "timestamp": "2026-03-13T01:00:01Z",
                "summary": "goc contract audit executed",
            }
        ],
    )
    return RuntimeContractScenario(
        name="goc_contract",
        run_id="run-goc",
        authority=authority,
        nodes=nodes,
        membership_agents=[
            ConversationMemberSeed(
                name="Research Coordinator",
                role_label="Research Coordinator",
                overrides={"attached_skills": [{"skill_id": "skill.claim_evidence_audit.v1"}]},
            )
        ],
    )


def degraded_local_fallback_runtime_contract_scenario(*, base: datetime | None = None) -> RuntimeContractScenario:
    base = base or datetime(2026, 3, 13, 2, 0, tzinfo=timezone.utc)
    authority = canonical_runtime_authority(
        mode="goc",
        plan_source="local_fallback",
        context_source="goc",
        agent_catalog_source="goc",
        conversation_team_source="goc",
        skill_catalog_source="mixed",
        degraded_mode=True,
        fallback_reason="planner service unavailable",
    )
    custom_skill_id = "skill.runtime_fallback_planner.v1"
    nodes = _build_run_step_nodes(
        name="local-fallback",
        authority=authority,
        base=base,
        step_agent_id="Fallback Planner",
        context_packs=[
            {
                "context_pack_id": "cp-fallback",
                "scope": "runtime",
                "shared_items_count": 2,
                "role_specific_items_count": 1,
                "skill_items": [
                    {"skill_id": "skill.claim_evidence_audit.v1", "load_level": "instructions", "count": 1},
                    {"skill_id": custom_skill_id, "load_level": "resources", "count": 1},
                ],
            }
        ],
        runtime_skill_packages=[
            runtime_skill_package(
                custom_skill_id,
                name="Runtime Fallback Planner",
                capability_tags=["planning", "fallback"],
                compatible_roles=["planner"],
            )
        ],
        skill_usage_events=[
            {
                "skill_id": "skill.claim_evidence_audit.v1",
                "event_type": "used",
                "timestamp": "2026-03-13T02:00:01Z",
                "summary": "fallback audit executed",
            },
            {
                "skill_id": custom_skill_id,
                "event_type": "selected",
                "timestamp": "2026-03-13T02:00:02Z",
                "summary": "runtime fallback planner selected",
            },
        ],
    )
    return RuntimeContractScenario(
        name="local_fallback_contract",
        run_id="run-local-fallback",
        authority=authority,
        nodes=nodes,
        membership_agents=[
            ConversationMemberSeed(name="Fallback Planner", role_label="Fallback Planner"),
        ],
    )


def mixed_skill_authority_runtime_contract_scenario(*, base: datetime | None = None) -> RuntimeContractScenario:
    base = base or datetime(2026, 3, 13, 3, 0, tzinfo=timezone.utc)
    authority = canonical_runtime_authority(
        mode="goc",
        plan_source="goc",
        context_source="goc",
        agent_catalog_source="goc",
        conversation_team_source="goc",
        skill_catalog_source="mixed",
    )
    custom_skill_id = "skill.runtime_hybrid_briefing.v1"
    nodes = _build_run_step_nodes(
        name="mixed-skill",
        authority=authority,
        base=base,
        step_agent_id="Hybrid Analyst",
        context_packs=[
            {
                "context_pack_id": "cp-mixed",
                "scope": "runtime",
                "shared_items_count": 1,
                "role_specific_items_count": 1,
                "skill_items": [
                    {"skill_id": "skill.context_selection_policy.v1", "load_level": "instructions", "count": 1},
                    {"skill_id": custom_skill_id, "load_level": "resources", "count": 1},
                ],
            }
        ],
        runtime_skill_packages=[
            runtime_skill_package(
                custom_skill_id,
                name="Runtime Hybrid Briefing",
                capability_tags=["runtime", "briefing"],
                compatible_roles=["writer", "analyst"],
            )
        ],
        skill_usage_events=[
            {
                "skill_id": "skill.context_selection_policy.v1",
                "event_type": "used",
                "timestamp": "2026-03-13T03:00:01Z",
                "summary": "default policy skill used",
            },
            {
                "skill_id": custom_skill_id,
                "event_type": "used",
                "timestamp": "2026-03-13T03:00:02Z",
                "summary": "runtime hybrid briefing used",
            },
        ],
    )
    return RuntimeContractScenario(
        name="mixed_skill_contract",
        run_id="run-mixed-skill",
        authority=authority,
        nodes=nodes,
        membership_agents=[
            ConversationMemberSeed(name="Hybrid Analyst", role_label="Hybrid Analyst"),
        ],
    )
