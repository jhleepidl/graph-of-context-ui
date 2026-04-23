from __future__ import annotations

import json
import re
from typing import Any

from sqlmodel import Session, select

from app.models import Node, Thread
from app.services.graph import add_edge, get_last_node
from app.services.learning_policy import is_raw_history_payload
from app.services.runtime_snapshot import node_payload


CANDIDATE_SOURCE = "raw_history_extractor"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _jdump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _slug(value: Any) -> str:
    raw = _clean_text(value).lower()
    if not raw:
        return "item"
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return slug or "item"


def _candidate_title(prefix: str, value: str) -> str:
    clean = _clean_text(value)
    return f"{prefix} · {clean}" if clean else prefix


def _team_candidate_spec(*, stream_key: str, label: str, team_name: str, team_summary: dict[str, Any], source_phase: str) -> dict[str, Any] | None:
    clean_team_name = _clean_text(team_name) or _clean_text(label)
    if not clean_team_name:
        return None
    roles = [entry for entry in [_clean_text(v) for v in _as_list(team_summary.get("roles"))] if entry][:12]
    attached_skill_ids = [entry for entry in [_clean_text(v) for v in _as_list(team_summary.get("attached_skill_ids"))] if entry][:24]
    agent_count = int(team_summary.get("agent_count") or 0)
    candidate_key = f"{stream_key}:team:{_slug(label or clean_team_name)}"
    summary = f"{source_phase} team with {agent_count} agent(s)"
    if roles:
        summary += f" · roles: {', '.join(roles[:4])}"
    if attached_skill_ids:
        summary += f" · skills: {', '.join(attached_skill_ids[:4])}"
    return {
        "candidate_key": candidate_key,
        "resource_kind": "team_candidate",
        "candidate_kind": "team_blueprint",
        "title": _candidate_title("Team candidate", label or clean_team_name),
        "summary": summary,
        "normalized_candidate": {
            "label": label or clean_team_name,
            "team_name": clean_team_name,
            "agent_count": agent_count,
            "roles": roles,
            "attached_skill_ids": attached_skill_ids,
            "source_phase": source_phase,
        },
    }


def _skill_candidate_spec(*, stream_key: str, skill_id: str, source_phase: str, reason: str = "") -> dict[str, Any] | None:
    clean_skill_id = _clean_text(skill_id)
    if not clean_skill_id:
        return None
    candidate_key = f"{stream_key}:skill:{_slug(clean_skill_id)}"
    summary = f"Observed in {source_phase} runtime history"
    if _clean_text(reason):
        summary += f" · { _clean_text(reason) }"
    return {
        "candidate_key": candidate_key,
        "resource_kind": "skill_candidate",
        "candidate_kind": "skill_package",
        "title": _candidate_title("Skill candidate", clean_skill_id),
        "summary": summary,
        "normalized_candidate": {
            "skill_id": clean_skill_id,
            "source_phase": source_phase,
            "reason": _clean_text(reason) or None,
        },
    }


def extract_candidates_from_raw_history(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    row = payload if isinstance(payload, dict) else {}
    if not row or not is_raw_history_payload(row):
        return []
    stream_key = _clean_text(row.get("history_stream_key") or row.get("uri") or row.get("chat_id") or "default")
    provenance = _as_dict(row.get("provenance"))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def push(spec: dict[str, Any] | None) -> None:
        item = spec if isinstance(spec, dict) else None
        if not item:
            return
        key = _clean_text(item.get("candidate_key"))
        if not key or key in seen:
            return
        seen.add(key)
        out.append(item)

    for artifact in _as_list(row.get("extracted_artifacts")):
        entry = _as_dict(artifact)
        kind = _clean_text(entry.get("kind")).lower()
        if kind == "team_blueprint_reference":
            label = _clean_text(entry.get("label") or entry.get("team_name") or entry.get("name"))
            phase = "runtime"
            if label.startswith("active:"):
                phase = "active"
            elif label.startswith("pending:"):
                phase = "pending"
            push(_team_candidate_spec(
                stream_key=stream_key,
                label=label,
                team_name=_clean_text(entry.get("team_name") or label.split(":", 1)[-1]),
                team_summary={
                    "agent_count": entry.get("agent_count"),
                    "roles": entry.get("roles") or [],
                    "attached_skill_ids": entry.get("attached_skill_ids") or [],
                },
                source_phase=phase,
            ))
            for skill_id in _as_list(entry.get("attached_skill_ids")):
                push(_skill_candidate_spec(stream_key=stream_key, skill_id=skill_id, source_phase=phase, reason=f"attached to {label or 'team'}"))
        elif kind in {"skill_package_reference", "skill_reference"}:
            push(_skill_candidate_spec(
                stream_key=stream_key,
                skill_id=_clean_text(entry.get("skill_id") or entry.get("id")),
                source_phase=_clean_text(entry.get("source_phase") or entry.get("phase") or "runtime") or "runtime",
                reason=_clean_text(entry.get("reason") or entry.get("label")),
            ))

    for provenance_key, phase in (("active_team", "active"), ("pending_team", "pending")):
        team_summary = _as_dict(provenance.get(provenance_key))
        push(_team_candidate_spec(
            stream_key=stream_key,
            label=f"{phase}:{_clean_text(team_summary.get('team_name') or team_summary.get('name') or phase)}",
            team_name=_clean_text(team_summary.get("team_name") or team_summary.get("name") or phase),
            team_summary=team_summary,
            source_phase=phase,
        ))
        for skill_id in _as_list(team_summary.get("attached_skill_ids")):
            push(_skill_candidate_spec(stream_key=stream_key, skill_id=skill_id, source_phase=phase, reason=f"attached to {phase} team"))

    return out


def _build_candidate_text(spec: dict[str, Any], raw_history_payload: dict[str, Any]) -> str:
    details = _as_dict(spec.get("normalized_candidate"))
    lines = [
        f"# { _clean_text(spec.get('title')) or 'Promotion candidate' }",
        "",
        f"candidate_key: { _clean_text(spec.get('candidate_key')) or '-' }",
        f"candidate_kind: { _clean_text(spec.get('candidate_kind')) or '-' }",
        f"resource_kind: { _clean_text(spec.get('resource_kind')) or '-' }",
        f"promotion_status: candidate",
        f"review_status: review_required",
        f"source_stream: { _clean_text(raw_history_payload.get('history_stream_key')) or '-' }",
        f"source_history_title: { _clean_text(raw_history_payload.get('name') or raw_history_payload.get('title')) or '-' }",
        "",
        _clean_text(spec.get("summary")) or "No summary.",
    ]
    if details:
        lines.extend(["", "## normalized candidate", _jdump(details)])
    return "\n".join(lines).strip()


def sync_candidates_for_raw_history(
    session: Session,
    *,
    thread: Thread,
    raw_history_node: Node,
) -> dict[str, Any]:
    raw_payload = node_payload(raw_history_node)
    specs = extract_candidates_from_raw_history(raw_payload)
    stream_key = _clean_text(raw_payload.get("history_stream_key") or raw_payload.get("uri") or raw_history_node.id)
    existing_rows = session.exec(
        select(Node)
        .where(Node.thread_id == thread.id, Node.type == "Resource")
        .order_by(Node.created_at.desc(), Node.id.desc())
    ).all()
    existing_by_key: dict[str, Node] = {}
    tracked_nodes: list[Node] = []
    for row in existing_rows:
        payload = node_payload(row)
        if _clean_text(payload.get("derived_by")) != CANDIDATE_SOURCE:
            continue
        if _clean_text(payload.get("derived_from_history_stream_key")) != stream_key:
            continue
        key = _clean_text(payload.get("candidate_key"))
        if not key:
            continue
        existing_by_key[key] = row
        tracked_nodes.append(row)

    active_keys: set[str] = set()
    created = 0
    updated = 0
    superseded = 0
    items: list[dict[str, Any]] = []

    for spec in specs:
        candidate_key = _clean_text(spec.get("candidate_key"))
        if not candidate_key:
            continue
        active_keys.add(candidate_key)
        node = existing_by_key.get(candidate_key)
        payload = {
            "name": _clean_text(spec.get("title")) or candidate_key,
            "title": _clean_text(spec.get("title")) or candidate_key,
            "summary": _clean_text(spec.get("summary")) or None,
            "resource_kind": _clean_text(spec.get("resource_kind")) or "workflow_candidate",
            "candidate_kind": _clean_text(spec.get("candidate_kind")) or None,
            "candidate_key": candidate_key,
            "candidate_for_promotion": True,
            "promotion_status": "candidate",
            "review_status": "review_required",
            "learning_excluded": True,
            "reuse_mode": "review_only",
            "board_visible": True,
            "shareability": "review_required",
            "privacy_class": "structured_candidate",
            "source": CANDIDATE_SOURCE,
            "derived_by": CANDIDATE_SOURCE,
            "derived_from_raw_history_node_id": raw_history_node.id,
            "derived_from_history_stream_key": stream_key,
            "derived_from_history_title": _clean_text(raw_payload.get("name") or raw_payload.get("title")) or None,
            "normalized_candidate": _as_dict(spec.get("normalized_candidate")),
            "stale": False,
            "tag": "RESOURCE",
        }
        node_text = _build_candidate_text(spec, raw_payload)
        if node:
            current = node_payload(node)
            current.update(payload)
            node.text = node_text
            node.payload_json = _jdump(current)
            session.add(node)
            updated += 1
        else:
            last = get_last_node(session, thread.id)
            node = Node(
                thread_id=thread.id,
                type="Resource",
                text=node_text,
                payload_json=_jdump(payload),
            )
            session.add(node)
            session.flush()
            if last and last.id != node.id:
                session.add(add_edge(thread.id, last.id, node.id, "NEXT"))
            session.add(add_edge(thread.id, raw_history_node.id, node.id, "DERIVED"))
            created += 1
        items.append({
            "candidate_key": candidate_key,
            "resource_kind": payload["resource_kind"],
            "title": payload["title"],
            "promotion_status": payload["promotion_status"],
            "review_status": payload["review_status"],
        })

    for node in tracked_nodes:
        payload = node_payload(node)
        candidate_key = _clean_text(payload.get("candidate_key"))
        if not candidate_key or candidate_key in active_keys:
            continue
        payload.update({
            "stale": True,
            "review_status": "superseded",
            "promotion_status": "candidate",
        })
        node.payload_json = _jdump(payload)
        session.add(node)
        superseded += 1

    return {
        "count": len(items),
        "created": created,
        "updated": updated,
        "superseded": superseded,
        "items": items[:12],
    }
