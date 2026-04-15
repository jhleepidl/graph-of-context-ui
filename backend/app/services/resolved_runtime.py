from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models import Agent, Conversation, ConversationAgent
from app.services.context_packs import extract_context_pack_summaries
from app.services.planning_boundary import build_planning_boundary_projection
from app.services.scope_projection import build_scope_projection, build_visibility_projection
from app.services.runtime_authority import (
    apply_runtime_authority,
    build_runtime_authority_projection,
    derive_runtime_authority,
    extract_authority_profile_id,
)
from app.services.runtime_scope import resolve_run_scoped_nodes
from app.services.conversation_team_config import get_team_config_payload
from app.services.runtime_snapshot import (
    clean_list_of_text as _clean_list_of_text,
    clean_text as _snapshot_clean_text,
    created_sort_key as _created_sort_key,
    extract_runtime_team_snapshot,
    node_payload as _node_payload,
    normalize_runtime_source_key as _normalize_runtime_source_key,
    normalize_status as _normalize_status,
)
from app.services.skill_projections import extract_attached_skills, extract_runtime_agents_with_skills, extract_skill_usage_events
from app.services.skill_registry import build_skill_registry


from app.services.runtime_projection_common import (
    EVIDENCE_NODE_TYPES,
    _boolish,
    _build_configured_team_projection,
    _clean_list,
    _clean_text,
    _first_present_value,
    _friendly_runtime_label,
    _intish,
    _jload,
    _preferred_step_source_key,
    _runtime_status_from_counts,
    _scalar_summary,
    _skill_packages_for_team_items,
    _slot_indexes,
    _step_activity_index,
    _step_activity_source_index,
    _structured_summary,
    _structured_value,
    _team_view_labels_by_instance,
    aggregate_attached_skills,
)


def build_team_view_projection(
    *,
    runtime_agents: list[dict[str, Any]],
    runtime_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.services.runtime_projection_sections import build_team_view_projection as _impl

    return _impl(runtime_agents=runtime_agents, runtime_snapshot=runtime_snapshot)


def build_why_this_team_projection(
    *,
    team_view: dict[str, Any],
    runtime_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.services.runtime_projection_sections import build_why_this_team_projection as _impl

    return _impl(team_view=team_view, runtime_snapshot=runtime_snapshot)


def build_orchestration_projection(
    runtime_snapshot: dict[str, Any] | None,
    *,
    team_view: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.services.runtime_projection_sections import build_orchestration_projection as _impl

    return _impl(runtime_snapshot, team_view=team_view)


def build_collaboration_projection(
    runtime_snapshot: dict[str, Any] | None,
    *,
    team_view: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.services.runtime_projection_sections import build_collaboration_projection as _impl

    return _impl(runtime_snapshot=runtime_snapshot, team_view=team_view)


def build_checkpoints_projection(
    runtime_snapshot: dict[str, Any] | None,
    *,
    team_view: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.services.runtime_projection_sections import build_checkpoints_projection as _impl

    return _impl(runtime_snapshot, team_view=team_view)


def build_skill_lineage_projection(
    *,
    runtime_agents: list[dict[str, Any]],
    context_packs: list[dict[str, Any]],
    usage_events: list[dict[str, Any]],
    nodes: Iterable[Any],
    edges: Iterable[Any],
) -> dict[str, Any]:
    from app.services.runtime_projection_sections import build_skill_lineage_projection as _impl

    return _impl(
        runtime_agents=runtime_agents,
        context_packs=context_packs,
        usage_events=usage_events,
        nodes=nodes,
        edges=edges,
    )


@dataclass(slots=True)
class ResolvedRuntimeScope:
    requested_run_id: str | None
    run_id: str | None
    nodes: list[Any]
    scope: dict[str, Any]


@dataclass(slots=True)
class ResolvedConversationTeam:
    conversation_id: str | None
    snapshot_node_id: str | None
    snapshot_node_type: str | None
    snapshot_source_key: str | None
    snapshot_source_path: str | None
    items: list[dict[str, Any]]
    skill_packages: list[dict[str, Any]]
    active_count: int
    updated_at: str
    team_config: dict[str, Any] | None = None
    configured_items: list[dict[str, Any]] | None = None
    configured_scope_items: list[dict[str, Any]] | None = None

    def as_payload(self) -> dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "snapshot_node_id": self.snapshot_node_id,
            "snapshot_node_type": self.snapshot_node_type,
            "snapshot_source_key": self.snapshot_source_key,
            "snapshot_source_path": self.snapshot_source_path,
            "items": list(self.items),
            "skill_packages": list(self.skill_packages),
            "active_count": self.active_count,
            "updated_at": self.updated_at,
            "team_config": dict(self.team_config or {}),
            "configured_items": list(self.configured_items or []),
            "configured_scope_items": list(self.configured_scope_items or []),
        }


@dataclass(slots=True)
class ResolvedRunCapabilities:
    run_id: str | None
    action_source: str | None
    runtime_agents: list[dict[str, Any]]
    attached_skills: list[dict[str, Any]]
    skill_packages: list[dict[str, Any]]
    context_packs: list[dict[str, Any]]
    skill_usage: list[dict[str, Any]]
    lineage: dict[str, Any]
    task_interpretation: dict[str, Any] | None
    execution_insights: dict[str, Any] | None
    execution_feedback: dict[str, Any] | None
    team_view: dict[str, Any]
    why_this_team: dict[str, Any]
    scope_projection: dict[str, Any]
    visibility_projection: dict[str, Any]
    orchestration: dict[str, Any]
    collaboration: dict[str, Any]
    authority_projection: dict[str, Any]
    checkpoints_projection: dict[str, Any]
    counts: dict[str, int]
    updated_at: str

    def as_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "action_source": self.action_source,
            "runtime_agents": list(self.runtime_agents),
            "attached_skills": list(self.attached_skills),
            "skill_packages": list(self.skill_packages),
            "context_packs": list(self.context_packs),
            "skill_usage": list(self.skill_usage),
            "lineage": dict(self.lineage),
            "task_interpretation": dict(self.task_interpretation) if self.task_interpretation else None,
            "execution_insights": dict(self.execution_insights) if self.execution_insights else None,
            "execution_feedback": dict(self.execution_feedback) if self.execution_feedback else None,
            "team_view": dict(self.team_view),
            "why_this_team": dict(self.why_this_team),
            "scope_projection": dict(self.scope_projection),
            "visibility_projection": dict(self.visibility_projection),
            "orchestration": dict(self.orchestration),
            "collaboration": dict(self.collaboration),
            "authority": dict(self.authority_projection),
            "checkpoints": dict(self.checkpoints_projection),
            "counts": dict(self.counts),
            "updated_at": self.updated_at,
        }

    def context_pack_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "action_source": self.action_source,
            "items": list(self.context_packs),
            "count": len(self.context_packs),
            "updated_at": self.updated_at,
        }

    def skill_usage_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "action_source": self.action_source,
            "items": list(self.skill_usage),
            "count": len(self.skill_usage),
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class ResolvedRuntimeProjection:
    scope: ResolvedRuntimeScope
    authority: dict[str, Any]
    planning_boundary: dict[str, Any]
    capabilities: ResolvedRunCapabilities | None = None
    conversation_team: ResolvedConversationTeam | None = None

    @property
    def run_id(self) -> str | None:
        return self.scope.run_id

    def apply_authority(self, payload: dict[str, Any]) -> dict[str, Any]:
        return apply_runtime_authority(payload, self.authority)

    def capability_payload(self) -> dict[str, Any]:
        payload = self.capabilities.as_payload() if self.capabilities else {
            "run_id": self.run_id,
            "action_source": None,
            "runtime_agents": [],
            "attached_skills": [],
            "skill_packages": [],
            "context_packs": [],
            "skill_usage": [],
            "lineage": {
                "role_skill_links": [],
                "skill_context_links": [],
                "skill_evidence_links": [],
                "counts": {
                    "role_skill_links": 0,
                    "skill_context_links": 0,
                    "skill_evidence_links": 0,
                },
            },
            "task_interpretation": None,
            "execution_insights": None,
            "execution_feedback": None,
            "team_view": {
                "items": [],
                "count": 0,
                "preset_count": 0,
                "synthesized_count": 0,
            },
            "why_this_team": {
                "selection_explanations": [],
                "slot_reasons": [],
                "agent_reasons": [],
                "conversation_preferences": None,
                "preset_count": 0,
                "synthesized_count": 0,
            },
            "scope_projection": {
                "context_runtime_mode": "shared_memory",
                "items": [],
                "count": 0,
                "grant_counts": {},
                "visibility_counts": {},
            },
            "visibility_projection": {
                "items": [],
                "count": 0,
                "relation_counts": {},
            },
            "orchestration": {
                "mode": "runtime_managed",
                "parallel_groups": [],
                "sequential_after": {},
                "supervisor_runtime": {},
                "supervisor_mode": None,
                "supervisor_edges": [],
                "parallel_group_count": 0,
                "sequential_dependency_count": 0,
                "supervisor_edge_count": 0,
            },
            "collaboration": {
                "items": [],
                "counts": {},
                "count": 0,
            },
            "authority": {
                "items": [],
                "graph": [],
                "count": 0,
                "graph_count": 0,
            },
            "checkpoints": {
                "items": [],
                "counts": {
                    "total": 0,
                    "human_interrupts": 0,
                    "approval_required": 0,
                    "blocking": 0,
                },
            },
            "counts": {
                "runtime_agents": 0,
                "attached_skills": 0,
                "skill_packages": 0,
                "context_packs": 0,
                "skill_usage": 0,
                "team_view": 0,
                "scope_projection": 0,
                "visibility_projection": 0,
                "collaboration": 0,
                "authority": 0,
                "checkpoints": 0,
            },
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        payload = self.apply_authority(payload)
        payload["planning_boundary"] = dict(self.planning_boundary)
        return payload

    def context_pack_payload(self) -> dict[str, Any]:
        payload = self.capabilities.context_pack_payload() if self.capabilities else {
            "run_id": self.run_id,
            "action_source": None,
            "items": [],
            "count": 0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        payload = self.apply_authority(payload)
        payload["planning_boundary"] = dict(self.planning_boundary)
        return payload

    def skill_usage_payload(self) -> dict[str, Any]:
        payload = self.capabilities.skill_usage_payload() if self.capabilities else {
            "run_id": self.run_id,
            "action_source": None,
            "items": [],
            "count": 0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        payload = self.apply_authority(payload)
        payload["planning_boundary"] = dict(self.planning_boundary)
        return payload

    def conversation_team_payload(self) -> dict[str, Any]:
        payload = self.conversation_team.as_payload() if self.conversation_team else {
            "conversation_id": None,
            "snapshot_node_id": None,
            "snapshot_node_type": None,
            "snapshot_source_key": None,
            "snapshot_source_path": None,
            "items": [],
            "skill_packages": [],
            "active_count": 0,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "team_config": {},
            "configured_items": [],
            "configured_scope_items": [],
        }
        if not list(payload.get("items") or []) and self.capabilities and list(self.capabilities.runtime_agents or []):
            payload = {
                **payload,
                "items": list(self.capabilities.runtime_agents or []),
                "active_count": len(list(self.capabilities.runtime_agents or [])),
                "fallback_reason": payload.get("fallback_reason") or "runtime_agents_fallback",
            }
        if not list(payload.get("items") or []) and list(payload.get("configured_items") or []):
            payload = {
                **payload,
                "items": list(payload.get("configured_items") or []),
                "fallback_reason": payload.get("fallback_reason") or "team_config_fallback",
            }
        return self.apply_authority(payload)


def resolve_runtime_scope_state(
    *,
    nodes: Iterable[Any],
    edges: Iterable[Any],
    run_id: str | None = None,
) -> ResolvedRuntimeScope:
    nodes_list = list(nodes)
    edges_list = list(edges)
    scoped = resolve_run_scoped_nodes(nodes=nodes_list, edges=edges_list, run_id=run_id)
    return ResolvedRuntimeScope(
        requested_run_id=_clean_text(run_id),
        run_id=_clean_text(scoped.get("run_id")),
        nodes=list(scoped.get("nodes") or []),
        scope=dict(scoped.get("scope") or {}),
    )


def resolve_conversation_team(
    session: Session,
    *,
    thread_id: str,
    nodes: Iterable[Any],
) -> ResolvedConversationTeam:
    nodes_list = list(nodes)
    conversation = session.exec(
        select(Conversation)
        .where(Conversation.thread_id == thread_id)
        .limit(1)
    ).first()
    step_activity_by_agent = _step_activity_index(nodes_list)
    step_activity_sources_by_agent = _step_activity_source_index(nodes_list)
    skill_registry = build_skill_registry(nodes=nodes_list, include_defaults=True)
    team_config_payload = get_team_config_payload(session, thread_id=thread_id)
    configured_items, configured_scope_items = _build_configured_team_projection(
        team_config=team_config_payload,
        skill_registry=skill_registry,
    )

    runtime_snapshot = extract_runtime_team_snapshot(nodes_list)
    if runtime_snapshot and list(runtime_snapshot.get("members") or []):
        runtime_source_path = str(runtime_snapshot.get("source_key") or "")
        runtime_source_key = _normalize_runtime_source_key(runtime_source_path)
        runtime_items: list[dict[str, Any]] = []
        for raw_member in runtime_snapshot.get("members", []):
            if not isinstance(raw_member, dict):
                continue
            llm_block = raw_member.get("llm")
            llm_info = llm_block if isinstance(llm_block, dict) else {}
            runtime_instance_id = _clean_text(raw_member.get("runtime_instance_id") or raw_member.get("instance_id"))
            agent_id = _clean_text(raw_member.get("agent_id") or raw_member.get("id") or raw_member.get("agent"))
            template_id = _clean_text(
                raw_member.get("template_id")
                or raw_member.get("agent_template_id")
                or raw_member.get("template")
            )
            lookup_keys = [key for key in [runtime_instance_id, agent_id, template_id] if key]
            status_counts: dict[str, int] = {}
            for key in lookup_keys:
                source_counts = step_activity_by_agent.get(key, {})
                for status_key, count in source_counts.items():
                    status_counts[status_key] = status_counts.get(status_key, 0) + int(count)

            attached_skills = extract_attached_skills(raw_member, skill_lookup=skill_registry)
            context_pack_id = _clean_text(raw_member.get("context_pack_id") or raw_member.get("contextPackId"))
            if not context_pack_id:
                member_pack = raw_member.get("context_pack") or raw_member.get("contextPack")
                if isinstance(member_pack, dict):
                    context_pack_id = _clean_text(
                        member_pack.get("context_pack_id")
                        or member_pack.get("contextPackId")
                        or member_pack.get("id")
                    )

            runtime_items.append(
                {
                    "agent_id": agent_id or runtime_instance_id or template_id or "unknown-runtime-agent",
                    "runtime_instance_id": runtime_instance_id,
                    "instance_id": runtime_instance_id,
                    "name": _clean_text(
                        raw_member.get("name")
                        or raw_member.get("display_label")
                        or raw_member.get("displayLabel")
                        or raw_member.get("display_name")
                        or raw_member.get("label")
                        or agent_id
                        or runtime_instance_id
                    ),
                    "display_label": _clean_text(
                        raw_member.get("display_label")
                        or raw_member.get("displayLabel")
                        or raw_member.get("display_name")
                        or raw_member.get("label")
                        or raw_member.get("name")
                    ),
                    "slot_id": _clean_text(raw_member.get("slot_id") or raw_member.get("slotId")),
                    "role_id": _clean_text(raw_member.get("role_id") or raw_member.get("roleId")),
                    "role_label": _clean_text(raw_member.get("role_label") or raw_member.get("role") or raw_member.get("title")),
                    "template_id": template_id,
                    "preset_id": _clean_text(raw_member.get("preset_id") or raw_member.get("presetId")),
                    "authority_profile_id": extract_authority_profile_id(raw_member),
                    "provider": _clean_text(raw_member.get("provider") or raw_member.get("llm_provider") or llm_info.get("provider")),
                    "model": _clean_text(raw_member.get("model") or raw_member.get("model_name") or llm_info.get("model")),
                    "runtime_status": (
                        _normalize_status(raw_member.get("runtime_status") or raw_member.get("status") or raw_member.get("state"))
                        if (
                            raw_member.get("runtime_status") is not None
                            or raw_member.get("status") is not None
                            or raw_member.get("state") is not None
                        )
                        else _runtime_status_from_counts(status_counts)
                    ),
                    "status_counts": status_counts,
                    "source": "runtime_snapshot",
                    "source_key": runtime_source_key,
                    "source_path": runtime_source_path or None,
                    "snapshot_node_id": runtime_snapshot.get("node_id"),
                    "snapshot_node_type": runtime_snapshot.get("node_type"),
                    "enabled": bool(raw_member.get("enabled", True)),
                    "responsibilities": _clean_list_of_text(raw_member.get("responsibilities") or raw_member.get("responsibility")),
                    "capability_tags": _clean_list_of_text(raw_member.get("capability_tags") or raw_member.get("capabilities")),
                    "ephemeral": bool(raw_member.get("ephemeral") or raw_member.get("transient") or False),
                    "synthesized": _boolish(raw_member.get("synthesized")),
                    "selection_reason": _clean_text(raw_member.get("selection_reason") or raw_member.get("selectionReason")),
                    "attached_skills": attached_skills,
                    "attached_skill_ids": [
                        str(item.get("skill_id") or "").strip()
                        for item in attached_skills
                        if str(item.get("skill_id") or "").strip()
                    ],
                    "context_pack_id": context_pack_id,
                }
            )

        updated_at = datetime.now(timezone.utc).isoformat()
        return ResolvedConversationTeam(
            conversation_id=getattr(conversation, "id", None),
            snapshot_node_id=runtime_snapshot.get("node_id"),
            snapshot_node_type=runtime_snapshot.get("node_type"),
            snapshot_source_key=runtime_source_key,
            snapshot_source_path=runtime_source_path or None,
            items=runtime_items,
            skill_packages=_skill_packages_for_team_items(team_items=runtime_items, skill_registry=skill_registry),
            active_count=sum(1 for item in runtime_items if item["runtime_status"] in {"running", "queued"}),
            updated_at=updated_at,
            team_config=team_config_payload,
            configured_items=configured_items,
            configured_scope_items=configured_scope_items,
        )

    if not conversation:
        inferred_items: list[dict[str, Any]] = []
        for agent_id in sorted(step_activity_by_agent.keys()):
            status_counts = step_activity_by_agent.get(agent_id, {})
            inferred_items.append(
                {
                    "agent_id": agent_id,
                    "name": agent_id,
                    "runtime_instance_id": None,
                    "role_label": None,
                    "template_id": None,
                    "provider": None,
                    "model": None,
                    "enabled": True,
                    "order_index": None,
                    "runtime_status": _runtime_status_from_counts(status_counts),
                    "status_counts": status_counts,
                    "responsibilities": [],
                    "capability_tags": [],
                    "ephemeral": False,
                    "source": "inferred_from_steps",
                    "source_key": _preferred_step_source_key(step_activity_sources_by_agent.get(agent_id)),
                    "attached_skills": [],
                    "context_pack_id": None,
                }
            )

        updated_at = datetime.now(timezone.utc).isoformat()
        return ResolvedConversationTeam(
            conversation_id=None,
            snapshot_node_id=None,
            snapshot_node_type=None,
            snapshot_source_key=None,
            snapshot_source_path=None,
            items=inferred_items,
            skill_packages=[],
            active_count=sum(1 for item in inferred_items if item["runtime_status"] in {"running", "queued"}),
            updated_at=updated_at,
            team_config=team_config_payload,
            configured_items=configured_items,
            configured_scope_items=configured_scope_items,
        )

    memberships = session.exec(
        select(ConversationAgent)
        .where(ConversationAgent.conversation_id == conversation.id)
        .order_by(ConversationAgent.order_index.asc(), ConversationAgent.created_at.asc(), ConversationAgent.id.asc())
    ).all()
    agent_ids = [row.agent_id for row in memberships]
    agents = session.exec(select(Agent).where(Agent.id.in_(agent_ids))).all() if agent_ids else []
    agents_by_id = {agent.id: agent for agent in agents}

    items: list[dict[str, Any]] = []
    for membership in memberships:
        agent = agents_by_id.get(membership.agent_id)
        overrides = _jload(membership.overrides_json, {})
        if not isinstance(overrides, dict):
            overrides = {}

        status_counts = step_activity_by_agent.get(membership.agent_id, {})
        if not status_counts and agent:
            status_counts = step_activity_by_agent.get(agent.name, {})

        raw_responsibilities = overrides.get("responsibilities") or overrides.get("responsibility") or []
        responsibilities: list[str] = []
        if isinstance(raw_responsibilities, str):
            clean = raw_responsibilities.strip()
            if clean:
                responsibilities = [clean]
        elif isinstance(raw_responsibilities, list):
            responsibilities = [str(item).strip() for item in raw_responsibilities if str(item).strip()]

        capability_tags = _clean_list_of_text(overrides.get("capability_tags") or overrides.get("capabilities"))
        if not capability_tags and agent:
            capability_tags = _clean_list_of_text(_jload(getattr(agent, "tools_json", "[]"), []))

        configured_context_policy = overrides.get("context_policy") or overrides.get("contextPolicy") or {}
        if not isinstance(configured_context_policy, dict):
            configured_context_policy = {}
        configured_reads = configured_context_policy.get("reads") if isinstance(configured_context_policy.get("reads"), dict) else {}
        configured_writes = configured_context_policy.get("writes") if isinstance(configured_context_policy.get("writes"), dict) else {}
        attached_skills = extract_attached_skills(overrides, skill_lookup=skill_registry)

        items.append(
            {
                "membership_id": membership.id,
                "agent_id": membership.agent_id,
                "name": _clean_text(overrides.get("name") or (agent.name if agent else membership.agent_id)) or membership.agent_id,
                "runtime_instance_id": None,
                "role_label": _clean_text(
                    overrides.get("configured_role")
                    or overrides.get("role_label")
                    or overrides.get("role")
                    or overrides.get("title")
                    or (agent.name if agent else None)
                ),
                "role_id": _clean_text(overrides.get("configured_role") or overrides.get("role")),
                "template_id": _clean_text(overrides.get("template_id") or overrides.get("agent_template_id")),
                "provider": _clean_text(overrides.get("configured_provider") or overrides.get("provider") or overrides.get("llm_provider")),
                "enabled": bool(membership.enabled),
                "order_index": int(membership.order_index),
                "runtime_status": _runtime_status_from_counts(status_counts),
                "status_counts": status_counts,
                "responsibilities": responsibilities,
                "capability_tags": capability_tags,
                "ephemeral": bool(overrides.get("ephemeral") or False),
                "description": _clean_text(overrides.get("purpose") or overrides.get("description") or (agent.description if agent else "")) or "",
                "model": _clean_text(overrides.get("configured_model") or (agent.model if agent else "")) or "",
                "visibility": _clean_text(overrides.get("visibility") or (agent.visibility if agent else "")) or "",
                "source": "conversation_membership",
                "source_key": "conversation_agents",
                "attached_skills": attached_skills,
                "attached_skill_ids": [
                    str(item.get("skill_id") or "").strip()
                    for item in attached_skills
                    if str(item.get("skill_id") or "").strip()
                ],
                "context_pack_id": _clean_text(overrides.get("context_pack_id") or overrides.get("contextPackId")),
                "context_policy": configured_context_policy,
                "context_policy_summary": _structured_summary(configured_context_policy),
                "grant_labels": _clean_list(configured_reads.get("grants"), limit=12),
                "context_types": _clean_list(configured_reads.get("context_types") or configured_reads.get("contextTypes"), limit=12),
                "publish_targets": _clean_list(configured_writes.get("publish_targets") or configured_writes.get("publishTargets"), limit=12),
                "interaction_contract": overrides.get("local_interaction_contract") if isinstance(overrides.get("local_interaction_contract"), dict) else None,
            }
        )

    updated_at = datetime.now(timezone.utc).isoformat()
    return ResolvedConversationTeam(
        conversation_id=conversation.id,
        snapshot_node_id=None,
        snapshot_node_type=None,
        snapshot_source_key=None,
        snapshot_source_path=None,
        items=items,
        skill_packages=_skill_packages_for_team_items(team_items=items, skill_registry=skill_registry),
        active_count=sum(1 for item in items if item["runtime_status"] in {"running", "queued"}),
        updated_at=updated_at,
        team_config=team_config_payload,
        configured_items=configured_items,
        configured_scope_items=configured_scope_items,
    )


def resolve_run_capabilities(
    *,
    nodes: Iterable[Any],
    edges: Iterable[Any],
    run_id: str | None = None,
    scope: ResolvedRuntimeScope | None = None,
) -> ResolvedRunCapabilities:
    nodes_list = list(nodes)
    edges_list = list(edges)
    scope_state = scope or resolve_runtime_scope_state(nodes=nodes_list, edges=edges_list, run_id=run_id)
    scoped_nodes = list(scope_state.nodes)

    registry = build_skill_registry(nodes=nodes_list, include_defaults=True)
    runtime_snapshot = extract_runtime_team_snapshot(scoped_nodes) or {}
    runtime_projection = extract_runtime_agents_with_skills(scoped_nodes, skill_lookup=registry)
    runtime_agents = list(runtime_projection.get("items") or [])
    context_packs = extract_context_pack_summaries(scoped_nodes)
    usage_events = extract_skill_usage_events(scoped_nodes, skill_lookup=registry)
    attached_skill_summaries = aggregate_attached_skills(runtime_agents)
    if list(runtime_snapshot.get("scope_specs") or []) and not list(runtime_snapshot.get("materialized_scopes") or []):
        runtime_snapshot = {
            **runtime_snapshot,
            "scope_projection_note": "materialized scopes missing; projection shows plan-time scope specs only",
        }
    team_view = build_team_view_projection(runtime_agents=runtime_agents, runtime_snapshot=runtime_snapshot)
    why_this_team = build_why_this_team_projection(team_view=team_view, runtime_snapshot=runtime_snapshot)
    scope_projection = build_scope_projection(runtime_snapshot, team_view=team_view)
    visibility_projection = build_visibility_projection(runtime_snapshot, scope_projection=scope_projection)
    orchestration = build_orchestration_projection(runtime_snapshot, team_view=team_view)
    collaboration = build_collaboration_projection(runtime_snapshot=runtime_snapshot, team_view=team_view)
    authority_projection = build_runtime_authority_projection(
        runtime_agents=runtime_agents,
        authority_graph=list(runtime_snapshot.get("authority_graph") or []),
    )
    checkpoints_projection = build_checkpoints_projection(runtime_snapshot, team_view=team_view)

    referenced_skill_ids: set[str] = set()
    for item in attached_skill_summaries:
        skill_id = str(item.get("skill_id") or "").strip()
        if skill_id:
            referenced_skill_ids.add(skill_id)
    for event in usage_events:
        skill_id = str(event.get("skill_id") or "").strip()
        if skill_id:
            referenced_skill_ids.add(skill_id)
    for pack in context_packs:
        for skill_item in list(pack.get("skill_items") or []):
            skill_id = str(skill_item.get("skill_id") or "").strip()
            if skill_id:
                referenced_skill_ids.add(skill_id)

    # This remains a projection of observed/runtime-referenced packages, not execution authority.
    skill_packages = sorted(
        [registry[skill_id] for skill_id in referenced_skill_ids if skill_id in registry],
        key=lambda item: (str(item.get("name") or "").lower(), str(item.get("id") or "")),
    )

    lineage = build_skill_lineage_projection(
        runtime_agents=runtime_agents,
        context_packs=context_packs,
        usage_events=usage_events,
        nodes=scoped_nodes,
        edges=edges_list,
    )
    updated_at = datetime.now(timezone.utc).isoformat()
    return ResolvedRunCapabilities(
        run_id=scope_state.run_id,
        action_source=_clean_text(runtime_snapshot.get("action_source")),
        runtime_agents=runtime_agents,
        attached_skills=attached_skill_summaries,
        skill_packages=skill_packages,
        context_packs=context_packs,
        skill_usage=usage_events,
        lineage=lineage,
        task_interpretation=runtime_snapshot.get("task_interpretation"),
        execution_insights=runtime_snapshot.get("execution_insights"),
        execution_feedback=runtime_snapshot.get("execution_feedback"),
        team_view=team_view,
        why_this_team=why_this_team,
        scope_projection=scope_projection,
        visibility_projection=visibility_projection,
        orchestration=orchestration,
        collaboration=collaboration,
        authority_projection=authority_projection,
        checkpoints_projection=checkpoints_projection,
        counts={
            "runtime_agents": len(runtime_agents),
            "attached_skills": len(attached_skill_summaries),
            "skill_packages": len(skill_packages),
            "context_packs": len(context_packs),
            "skill_usage": len(usage_events),
            "team_view": int(team_view.get("count") or 0),
            "scope_projection": int(scope_projection.get("count") or 0),
            "visibility_projection": int(visibility_projection.get("count") or 0),
            "collaboration": int(collaboration.get("count") or 0),
            "authority": int(authority_projection.get("count") or 0),
            "checkpoints": int((checkpoints_projection.get("counts") or {}).get("total") or 0),
        },
        updated_at=updated_at,
    )


def resolve_runtime_projection(
    *,
    nodes: Iterable[Any],
    edges: Iterable[Any],
    run_id: str | None = None,
    session: Session | None = None,
    thread_id: str | None = None,
    team_nodes: Iterable[Any] | None = None,
    scope: ResolvedRuntimeScope | None = None,
    capabilities: ResolvedRunCapabilities | None = None,
    conversation_team: ResolvedConversationTeam | None = None,
    include_capabilities: bool = True,
    include_conversation_team: bool = False,
    context_source_default: str | None = None,
    plan_source_default: str | None = None,
    mode_default: str | None = None,
) -> ResolvedRuntimeProjection:
    nodes_list = list(nodes)
    edges_list = list(edges)
    scope_state = scope or resolve_runtime_scope_state(nodes=nodes_list, edges=edges_list, run_id=run_id)

    capability_state = capabilities
    if include_capabilities and capability_state is None:
        capability_state = resolve_run_capabilities(
            nodes=nodes_list,
            edges=edges_list,
            run_id=run_id,
            scope=scope_state,
        )

    team_state = conversation_team
    should_resolve_team = include_conversation_team or team_state is not None
    if should_resolve_team and team_state is None and session is not None and thread_id:
        team_state = resolve_conversation_team(
            session,
            thread_id=thread_id,
            nodes=list(team_nodes) if team_nodes is not None else nodes_list,
        )

    # All runtime-facing projections should consume the same normalized ddalggak -> GoC authority contract here.
    authority = derive_runtime_authority(
        nodes=scope_state.nodes,
        agent_team=team_state.as_payload() if team_state else None,
        skill_packages=capability_state.skill_packages if capability_state else [],
        runtime_agents=capability_state.runtime_agents if capability_state else [],
        usage_events=capability_state.skill_usage if capability_state else [],
        context_packs=capability_state.context_packs if capability_state else [],
        context_source_default=context_source_default,
        plan_source_default=plan_source_default,
        mode_default=mode_default,
    )
    planning_boundary = build_planning_boundary_projection(
        run_id=scope_state.run_id,
        runtime_authority=authority,
        runtime_snapshot=extract_runtime_team_snapshot(scope_state.nodes) or {},
        capabilities=capability_state.as_payload() if capability_state else None,
    )
    return ResolvedRuntimeProjection(
        scope=scope_state,
        authority=authority,
        planning_boundary=planning_boundary,
        capabilities=capability_state,
        conversation_team=team_state,
    )
