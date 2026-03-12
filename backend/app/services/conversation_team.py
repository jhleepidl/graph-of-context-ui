from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models import Agent, Conversation, ConversationAgent, Node
from app.services.runtime_snapshot import (
    clean_list_of_text as _clean_list_of_text,
    extract_runtime_team_snapshot as _extract_runtime_team_snapshot,
    normalize_runtime_source_key as _normalize_runtime_source_key,
    normalize_status as _normalize_status,
)
from app.services.skill_projections import extract_attached_skills
from app.services.skill_registry import build_skill_registry


def _jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return default


def _node_payload(node: Node | None) -> dict[str, Any]:
    if not node:
        return {}
    payload = _jload(node.payload_json, {})
    if isinstance(payload, dict):
        return payload
    return {}


def _created_sort_key(node: Node) -> tuple[str, str]:
    created_at = getattr(node, "created_at", None)
    if hasattr(created_at, "isoformat"):
        return created_at.isoformat(), str(getattr(node, "id", ""))
    return str(created_at or ""), str(getattr(node, "id", ""))


def _step_activity_index(nodes: list[Node]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for step in sorted([node for node in nodes if node.type == "Step"], key=_created_sort_key):
        payload = _node_payload(step)
        status = _normalize_status(payload.get("status"))
        keys = {
            str(payload.get("agent_id") or "").strip(),
            str(payload.get("agent") or "").strip(),
            str(payload.get("assignee") or "").strip(),
            str(payload.get("runtime_instance_id") or "").strip(),
            str(payload.get("instance_id") or "").strip(),
            str(payload.get("executor_id") or "").strip(),
            str(payload.get("template_id") or "").strip(),
        }
        keys = {k for k in keys if k}
        for key in keys:
            row = out.setdefault(key, {})
            row[status] = row.get(status, 0) + 1
    return out


def _step_activity_source_index(nodes: list[Node]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    field_names = (
        "agent_id",
        "agent",
        "assignee",
        "runtime_instance_id",
        "instance_id",
        "executor_id",
        "template_id",
    )
    for step in sorted([node for node in nodes if node.type == "Step"], key=_created_sort_key):
        payload = _node_payload(step)
        for field_name in field_names:
            key = str(payload.get(field_name) or "").strip()
            if not key:
                continue
            row = out.setdefault(key, {})
            row[field_name] = row.get(field_name, 0) + 1
    return out


def _preferred_step_source_key(field_counts: dict[str, int] | None) -> str:
    if not field_counts:
        return "step_payload.agent_id"
    for field_name in (
        "agent_id",
        "agent",
        "assignee",
        "runtime_instance_id",
        "instance_id",
        "executor_id",
        "template_id",
    ):
        if int(field_counts.get(field_name, 0)) > 0:
            return f"step_payload.{field_name}"
    return "step_payload.agent_id"


def _runtime_status_from_counts(status_counts: dict[str, int]) -> str:
    if status_counts.get("running", 0) > 0:
        return "running"
    if status_counts.get("error", 0) > 0:
        return "error"
    if status_counts.get("queued", 0) > 0:
        return "queued"
    if sum(status_counts.values()) > 0:
        return "done"
    return "idle"


def build_conversation_team_projection(
    session: Session,
    *,
    thread_id: str,
    nodes: list[Node],
) -> dict[str, Any]:
    conversation = session.exec(
        select(Conversation)
        .where(Conversation.thread_id == thread_id)
        .limit(1)
    ).first()
    step_activity_by_agent = _step_activity_index(nodes)
    step_activity_sources_by_agent = _step_activity_source_index(nodes)
    skill_registry = build_skill_registry(nodes=nodes, include_defaults=True)

    def _skill_packages_for_items(team_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        skill_ids: set[str] = set()
        for team_item in team_items:
            for attached in list(team_item.get("attached_skills") or []):
                skill_id = str(attached.get("skill_id") or "").strip()
                if skill_id:
                    skill_ids.add(skill_id)
        return sorted(
            [skill_registry[skill_id] for skill_id in skill_ids if skill_id in skill_registry],
            key=lambda item: (str(item.get("name") or "").lower(), str(item.get("id") or "")),
        )

    runtime_snapshot = _extract_runtime_team_snapshot(nodes)
    if runtime_snapshot:
        runtime_source_path = str(runtime_snapshot.get("source_key") or "")
        runtime_source_key = _normalize_runtime_source_key(runtime_source_path)
        runtime_items: list[dict[str, Any]] = []
        for raw_member in runtime_snapshot.get("members", []):
            if not isinstance(raw_member, dict):
                continue
            llm_block = raw_member.get("llm")
            llm_info = llm_block if isinstance(llm_block, dict) else {}
            runtime_instance_id = str(raw_member.get("runtime_instance_id") or raw_member.get("instance_id") or "").strip() or None
            agent_id = str(raw_member.get("agent_id") or raw_member.get("id") or raw_member.get("agent") or "").strip() or None
            template_id = str(
                raw_member.get("template_id")
                or raw_member.get("agent_template_id")
                or raw_member.get("template")
                or ""
            ).strip() or None
            lookup_keys = [key for key in [runtime_instance_id, agent_id, template_id] if key]
            status_counts: dict[str, int] = {}
            for key in lookup_keys:
                source_counts = step_activity_by_agent.get(key, {})
                for status_key, count in source_counts.items():
                    status_counts[status_key] = status_counts.get(status_key, 0) + int(count)

            attached_skills = extract_attached_skills(raw_member, skill_lookup=skill_registry)
            context_pack_id = str(raw_member.get("context_pack_id") or raw_member.get("contextPackId") or "").strip() or None
            if not context_pack_id:
                member_pack = raw_member.get("context_pack") or raw_member.get("contextPack")
                if isinstance(member_pack, dict):
                    context_pack_id = str(
                        member_pack.get("context_pack_id")
                        or member_pack.get("contextPackId")
                        or member_pack.get("id")
                        or ""
                    ).strip() or None

            runtime_items.append(
                {
                    "agent_id": agent_id or runtime_instance_id or template_id or "unknown-runtime-agent",
                    "runtime_instance_id": runtime_instance_id,
                    "name": str(raw_member.get("name") or raw_member.get("display_name") or raw_member.get("label") or agent_id or runtime_instance_id or "").strip() or None,
                    "role_label": str(raw_member.get("role_label") or raw_member.get("role") or raw_member.get("title") or "").strip() or None,
                    "template_id": template_id,
                    "provider": str(raw_member.get("provider") or raw_member.get("llm_provider") or llm_info.get("provider") or "").strip() or None,
                    "model": str(raw_member.get("model") or raw_member.get("model_name") or llm_info.get("model") or "").strip() or None,
                    "runtime_status": _normalize_status(raw_member.get("runtime_status") or raw_member.get("status") or raw_member.get("state")) if (
                        raw_member.get("runtime_status") is not None
                        or raw_member.get("status") is not None
                        or raw_member.get("state") is not None
                    ) else _runtime_status_from_counts(status_counts),
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
                    "attached_skills": attached_skills,
                    "context_pack_id": context_pack_id,
                }
            )

        return {
            "conversation_id": conversation.id if conversation else None,
            "snapshot_node_id": runtime_snapshot.get("node_id"),
            "snapshot_node_type": runtime_snapshot.get("node_type"),
            "snapshot_source_key": runtime_source_key,
            "snapshot_source_path": runtime_source_path or None,
            "items": runtime_items,
            "skill_packages": _skill_packages_for_items(runtime_items),
            "active_count": sum(1 for item in runtime_items if item["runtime_status"] in {"running", "queued"}),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    if not conversation:
        inferred_items = []
        for agent_id in sorted(step_activity_by_agent.keys()):
            status_counts = step_activity_by_agent.get(agent_id, {})
            runtime_status = _runtime_status_from_counts(status_counts)
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
                    "runtime_status": runtime_status,
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
        return {
            "conversation_id": None,
            "snapshot_node_id": None,
            "snapshot_node_type": None,
            "snapshot_source_key": None,
            "snapshot_source_path": None,
            "items": inferred_items,
            "skill_packages": [],
            "active_count": sum(1 for item in inferred_items if item["runtime_status"] in {"running", "queued"}),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

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
        runtime_status = _runtime_status_from_counts(status_counts)

        raw_responsibilities = overrides.get("responsibilities") or overrides.get("responsibility") or []
        responsibilities: list[str] = []
        if isinstance(raw_responsibilities, str):
            clean = raw_responsibilities.strip()
            if clean:
                responsibilities = [clean]
        elif isinstance(raw_responsibilities, list):
            responsibilities = [str(item).strip() for item in raw_responsibilities if str(item).strip()]

        role_label = str(
            overrides.get("role_label")
            or overrides.get("role")
            or overrides.get("title")
            or agent.name
            or ""
        ).strip() or None
        capability_tags = _clean_list_of_text(overrides.get("capability_tags") or overrides.get("capabilities"))
        if not capability_tags and agent:
            capability_tags = _clean_list_of_text(_jload(getattr(agent, "tools_json", "[]"), []))

        items.append(
            {
                "membership_id": membership.id,
                "agent_id": membership.agent_id,
                "name": agent.name if agent else membership.agent_id,
                "runtime_instance_id": None,
                "role_label": role_label,
                "template_id": str(overrides.get("template_id") or overrides.get("agent_template_id") or "").strip() or None,
                "provider": str(overrides.get("provider") or overrides.get("llm_provider") or "").strip() or None,
                "enabled": bool(membership.enabled),
                "order_index": int(membership.order_index),
                "runtime_status": runtime_status,
                "status_counts": status_counts,
                "responsibilities": responsibilities,
                "capability_tags": capability_tags,
                "ephemeral": bool(overrides.get("ephemeral") or False),
                "description": agent.description if agent else "",
                "model": agent.model if agent else "",
                "visibility": agent.visibility if agent else "",
                "source": "conversation_membership",
                "source_key": "conversation_agents",
                "attached_skills": extract_attached_skills(overrides, skill_lookup=skill_registry),
                "context_pack_id": str(
                    overrides.get("context_pack_id")
                    or overrides.get("contextPackId")
                    or ""
                ).strip() or None,
            }
        )

    return {
        "conversation_id": conversation.id,
        "snapshot_node_id": None,
        "snapshot_node_type": None,
        "snapshot_source_key": None,
        "snapshot_source_path": None,
        "items": items,
        "skill_packages": _skill_packages_for_items(items),
        "active_count": sum(1 for item in items if item["runtime_status"] in {"running", "queued"}),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
