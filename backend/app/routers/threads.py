from __future__ import annotations
import io
import json
import logging
import zipfile
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response
from sqlalchemy import or_
from sqlmodel import Session, select

from app.db import engine
from app.models import Thread, ContextSet, ContextSetVersion, Node, Edge, NodeEmbedding
from app.schemas import (
    ThreadCreate,
    ThreadEnsureRequest,
    ThreadRead,
    NodeLayoutUpdate,
    EdgeCreate,
    NodeCreate,
    NodeCreateResponse,
    ConversationTeamConfigRequest,
    ConversationTeamConfigRead,
    ConversationTeamAgentContextPolicyPatchRequest,
    TeamManifestValidateRequest,
    TeamManifestInstallRequest,
    TeamManifestDiffRequest,
    HarnessSpecRead,
    HarnessSpecUpdateRequest,
    HarnessPackageRead,
    HarnessPackageInstallRequest,
)
from app.services.context_versions import snapshot_context_set
from app.services.embedding import rebuild_thread_index, remove_thread_index
from app.services.graph import add_edge, compile_active_context_explain, get_last_node, load_thread_graph
from app.services.run_studio import (
    build_run_studio_agent_team,
    build_run_studio_context_packs,
    build_run_studio_context_decisions,
    build_run_studio_evidence,
    build_run_studio_memory_graph,
    build_run_studio_run_bundle,
    build_run_studio_skill_usage,
    build_run_studio_summary,
    build_run_studio_trace_scope,
)
from app.services.scope_materializer import materialize_runtime_scopes
from app.services.scope_registry import get_scope_spec
from app.services.conversation_team_config import get_team_config_payload, save_team_config_payload, patch_team_config_agent_context_policy
from app.services.team_manifest import export_thread_team_manifest, install_thread_team_manifest, validate_team_manifest_payload, diff_team_manifest_payload
from app.services.team_blueprint import export_thread_team_blueprint, install_thread_team_blueprint, validate_team_blueprint_payload, diff_team_blueprint_payload
from app.services.team_publish_candidate import build_thread_team_publish_candidate
from app.services.memory_materialization import build_memory_materialization_preview, create_shadow_memory_module, list_memory_materialization_candidates, list_memory_modules, save_memory_materialization_candidates
from app.services.memory_review import build_memory_review_overview
from app.services.proposals import apply_runtime_proposal_action, build_review_inbox, list_runtime_proposals, upsert_runtime_proposals
from app.services.canonical_projection_worker import process_runtime_proposal_projections
from app.services.semantic_memory_index import search_thread_semantic_items
from app.services.watch_tasks import list_thread_watch_tasks, upsert_thread_watch_task, apply_watch_task_action
from app.services.harness_spec import get_thread_harness_spec, save_thread_harness_spec, build_harness_summary
from app.services.harness_package import build_harness_package_payload
from app.auth import get_current_principal
from app.tenant import current_service_id, require_node_access, require_thread_access, require_thread_write_access, PUBLIC_SERVICE_ID

router = APIRouter(prefix="/api/threads", tags=["threads"])
logger = logging.getLogger(__name__)


def jdump(x):
    return json.dumps(x, ensure_ascii=False)


def jload(s: str, default):
    try:
        return json.loads(s)
    except Exception:
        return default


def _normalize_external_ref(value: str | None) -> str | None:
    clean = (value or "").strip()
    return clean or None


def _normalize_meta_json(value: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _clean_optional_text(value: Any) -> str | None:
    clean = str(value or '').strip()
    return clean or None


def _merge_meta(existing: dict[str, Any], incoming: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    base = existing if isinstance(existing, dict) else {}
    incoming_obj = incoming if isinstance(incoming, dict) else {}
    merged: dict[str, Any] = dict(base)

    for key, incoming_value in incoming_obj.items():
        if key == "telegram" and isinstance(incoming_value, dict):
            current_telegram = merged.get("telegram")
            telegram_merged = dict(current_telegram) if isinstance(current_telegram, dict) else {}

            incoming_chat_id = incoming_value.get("chat_id")
            if _has_value(incoming_chat_id):
                telegram_merged["chat_id"] = incoming_chat_id

            for fill_key in ("title", "type"):
                if _has_value(telegram_merged.get(fill_key)):
                    continue
                incoming_fill = incoming_value.get(fill_key)
                if _has_value(incoming_fill):
                    telegram_merged[fill_key] = incoming_fill

            for telegram_key, telegram_value in incoming_value.items():
                if telegram_key in {"chat_id", "title", "type"}:
                    continue
                if telegram_key in telegram_merged:
                    continue
                if telegram_value is None:
                    continue
                telegram_merged[telegram_key] = telegram_value

            merged["telegram"] = telegram_merged
            continue

        if key in merged:
            continue
        merged[key] = incoming_value

    return merged, merged != base


def _apply_existing_thread_updates(
    session: Session,
    thread: Thread,
    incoming_title: str | None,
    incoming_meta: dict[str, Any],
) -> Thread:
    existing_meta_raw = jload(thread.meta_json or "{}", {})
    existing_meta = existing_meta_raw if isinstance(existing_meta_raw, dict) else {}
    merged_meta, meta_changed = _merge_meta(existing_meta, incoming_meta)

    title_changed = False
    next_title = (incoming_title or "").strip()
    current_title = (thread.title or "").strip()
    if next_title and (not current_title or current_title == "Untitled" or current_title.lower().startswith("job:")):
        if thread.title != next_title:
            thread.title = next_title
            title_changed = True

    if meta_changed:
        thread.meta_json = jdump(merged_meta)

    if meta_changed or title_changed:
        session.add(thread)
        session.commit()
        session.refresh(thread)

    return thread


def _thread_to_response(thread: Thread) -> ThreadRead:
    out = thread.model_dump()
    out["meta_json"] = jload(thread.meta_json or "{}", {})
    return ThreadRead(**out)


def _resolve_target_service_id_from_body(service_id_override: str | None) -> str:
    principal = get_current_principal()
    if principal.role == "admin":
        service_id = (service_id_override or "").strip()
        if not service_id:
            raise HTTPException(400, "admin must provide service_id")
        return service_id
    return current_service_id()


def _find_thread_by_external_ref(session: Session, service_id: str, external_ref: str) -> Thread | None:
    return session.exec(
        select(Thread)
        .where(Thread.service_id == service_id)
        .where(Thread.external_ref == external_ref)
        .order_by(Thread.created_at.asc(), Thread.id.asc())
        .limit(1)
    ).first()


def _create_thread_with_default_context_set(
    session: Session,
    service_id: str,
    title: str,
    external_ref: str | None,
    meta_json: dict[str, Any],
) -> Thread:
    thread = Thread(
        title=title or "Untitled",
        service_id=service_id,
        external_ref=external_ref,
        meta_json=jdump(meta_json),
    )
    session.add(thread)
    session.flush()
    context_set = ContextSet(thread_id=thread.id, name="default")
    session.add(context_set)
    session.flush()
    snapshot_context_set(
        session,
        context_set,
        reason="create",
        meta={"name": "default", "thread_id": thread.id},
    )
    return thread


ALLOWED_EDGE_TYPES = {
    "NEXT",
    "REPLY_TO",
    "RELATED",
    "SUPPORTS",
    "INVOKES",
    "RETURNS",
    "USES",
    "IN_RUN",
    "FOLDS",
    "USED_IN_RUN",
    "HAS_PART",
    "NEXT_PART",
    "SPLIT_FROM",
    "ATTACHED_TO",
    "REFERENCES",
    "DEPENDS",
    "JOINS",
    "BELONGS_TO_RUN",
}

ALLOWED_NODE_TYPES = {
    "Message",
    "Run",
    "Step",
    "ToolCall",
    "ToolResult",
    "Artifact",
    "Resource",
    "Fold",
    "Decision",
    "Assumption",
    "Plan",
    "ContextCandidate",
    "MemoryItem",
    "Observation",
    "ContextSummary",
    "ParticipantSignal",
    "ParticipantDigest",
    "ChannelVerifierDecision",
    "ChannelPromotionApplied",
}


_CONTEXT_SET_HINT_KEYS = (
    "shared_context_set_id",
    "shared_ctx_set_id",
    "base_context_set_id",
    "context_set_id",
    "lens_context_set_id",
    "lens_ctx_set_id",
    "scope_context_set_id",
    "scope_ctx_set_id",
    "step_context_set_id",
    "agent_context_set_id",
)

_RUN_LINK_EDGE_TYPES = {"BELONGS_TO_RUN", "IN_RUN"}


def _node_payload(node: Node | None) -> dict[str, Any]:
    if not node:
        return {}
    raw = jload(node.payload_json or "{}", {})
    if isinstance(raw, dict):
        return raw
    return {}


def _thread_graph_payload(session: Session, thread_id: str) -> tuple[dict[str, Any], list[Node], list[Edge]]:
    nodes, edges = load_thread_graph(session, thread_id)
    return {
        "nodes": [n.model_dump() for n in nodes],
        "edges": [e.model_dump() for e in edges],
    }, nodes, edges


def _append_id_value(target: set[str], value: Any) -> None:
    if isinstance(value, str):
        clean = value.strip()
        if clean:
            target.add(clean)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _append_id_value(target, item)
        return
    if isinstance(value, dict):
        raw_id = value.get("id")
        if isinstance(raw_id, str):
            clean = raw_id.strip()
            if clean:
                target.add(clean)


def _collect_context_set_ids(payload: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for key in _CONTEXT_SET_HINT_KEYS:
        _append_id_value(ids, payload.get(key))
    for key, value in payload.items():
        lowered = str(key or "").strip().lower()
        if not lowered:
            continue
        if "context_set_id" in lowered or "ctx_set_id" in lowered:
            _append_id_value(ids, value)
    return ids


def _pick_context_set_id(payload: dict[str, Any], keys: list[str]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _pick_lens_spec(payload: dict[str, Any]) -> dict[str, Any] | None:
    raw = payload.get("lens_spec")
    if isinstance(raw, dict):
        return raw

    fallback: dict[str, Any] = {}
    if payload.get("lens_mode") is not None:
        fallback["mode"] = payload.get("lens_mode")
    if payload.get("lens_query") is not None:
        fallback["query"] = payload.get("lens_query")
    if payload.get("lens_budget_tokens") is not None:
        fallback["budget_tokens"] = payload.get("lens_budget_tokens")
    if payload.get("lens_budget") is not None and fallback.get("budget_tokens") is None:
        fallback["budget_tokens"] = payload.get("lens_budget")
    if payload.get("lens_closure") is not None:
        fallback["closure"] = payload.get("lens_closure")
    return fallback or None


def _pick_lens_added_count(payload: dict[str, Any]) -> int:
    for key in ("lens_added_ids_count", "lens_added_count"):
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return max(0, int(value))
    raw_ids = payload.get("lens_added_ids")
    if isinstance(raw_ids, list):
        return len(raw_ids)
    return 0




def _pick_scope_hint(payload: dict[str, Any]) -> dict[str, Any] | None:
    raw = payload.get("scope_hint")
    if isinstance(raw, dict):
        return raw
    raw = payload.get("scope")
    if isinstance(raw, dict):
        return raw
    return _pick_lens_spec(payload)


def _pick_scope_added_count(payload: dict[str, Any]) -> int:
    for key in ("scope_added_ids_count", "scope_added_count"):
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return max(0, int(value))
    raw_ids = payload.get("scope_added_ids")
    if isinstance(raw_ids, list):
        return len(raw_ids)
    return _pick_lens_added_count(payload)

def _safe_file_component(value: str) -> str:
    clean = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in (value or "").strip())
    return clean or "unknown"


def _json_text(obj: Any) -> str:
    return json.dumps(jsonable_encoder(obj), ensure_ascii=False, indent=2)


def _build_run_summaries(
    nodes: list[Node],
    edges: list[Edge],
    scoped_steps: list[Node],
    run_id_filter: str | None,
) -> dict[str, dict[str, Any]]:
    nodes_by_id = {n.id: n for n in nodes}
    run_nodes = {n.id: n for n in nodes if n.type == "Run"}
    scoped_step_ids = {s.id for s in scoped_steps}

    run_to_step_ids: dict[str, set[str]] = {}

    def add_step(run_id: str, step_id: str) -> None:
        if not run_id or step_id not in scoped_step_ids:
            return
        run_to_step_ids.setdefault(run_id, set()).add(step_id)

    for edge in edges:
        if edge.type not in _RUN_LINK_EDGE_TYPES:
            continue
        src = nodes_by_id.get(edge.from_id)
        dst = nodes_by_id.get(edge.to_id)
        if not src or not dst:
            continue
        if src.type == "Run" and dst.type == "Step":
            add_step(src.id, dst.id)
        elif src.type == "Step" and dst.type == "Run":
            add_step(dst.id, src.id)

    for step in scoped_steps:
        payload = _node_payload(step)
        payload_run_id = str(payload.get("run_id") or "").strip()
        if payload_run_id:
            add_step(payload_run_id, step.id)

    run_ids = set(run_to_step_ids.keys()) | set(run_nodes.keys())
    if run_id_filter:
        run_ids = {run_id_filter}

    out: dict[str, dict[str, Any]] = {}
    for run_id in sorted(run_ids):
        run_node = run_nodes.get(run_id)
        run_payload = _node_payload(run_node)

        step_nodes = [nodes_by_id[sid] for sid in run_to_step_ids.get(run_id, set()) if sid in nodes_by_id]
        step_nodes = [n for n in step_nodes if n.type == "Step"]
        step_nodes.sort(key=lambda n: (n.created_at, n.id))

        step_items: list[dict[str, Any]] = []
        run_context_set_ids: set[str] = set()
        scope_added_total = 0
        for step in step_nodes:
            payload = _node_payload(step)
            context_set_ids = sorted(_collect_context_set_ids(payload))
            run_context_set_ids.update(context_set_ids)
            scope_added = _pick_scope_added_count(payload)
            scope_added_total += scope_added
            step_items.append({
                "id": step.id,
                "created_at": step.created_at,
                "text": step.text,
                "status": payload.get("status"),
                "agent_id": payload.get("agent_id") or payload.get("agent") or payload.get("assignee"),
                "goal": payload.get("goal") or payload.get("title") or step.text,
                "run_id": payload.get("run_id") or run_id,
                "started_at": payload.get("started_at"),
                "ended_at": payload.get("ended_at"),
                "shared_context_set_id": _pick_context_set_id(
                    payload,
                    ["shared_context_set_id", "shared_ctx_set_id", "base_context_set_id", "context_set_id"],
                ),
                "scope_context_set_id": _pick_context_set_id(
                    payload,
                    ["scope_context_set_id", "scope_ctx_set_id", "lens_context_set_id", "lens_ctx_set_id", "step_context_set_id", "agent_context_set_id"],
                ),
                "lens_context_set_id": _pick_context_set_id(
                    payload,
                    ["lens_context_set_id", "lens_ctx_set_id", "step_context_set_id", "agent_context_set_id"],
                ),
                "context_set_ids": context_set_ids,
                "scope_hint": _pick_scope_hint(payload),
                "lens_spec": _pick_lens_spec(payload),
                "scope_added_ids_count": scope_added,
                "lens_added_ids_count": scope_added,
                "payload": payload,
            })

        out[run_id] = {
            "run_id": run_id,
            "run_node": run_node.model_dump() if run_node else None,
            "run_payload": run_payload,
            "step_count": len(step_items),
            "step_ids": [s["id"] for s in step_items],
            "context_set_ids": sorted(run_context_set_ids),
            "scope_added_ids_total": scope_added_total,
            "lens_added_ids_total": scope_added_total,
            "steps": step_items,
        }

    return out


@router.get("", response_model=list[ThreadRead])
def list_threads():
    principal = get_current_principal()
    with Session(engine) as s:
        query = select(Thread).order_by(Thread.created_at.desc())
        if principal.role != "admin":
            service_id = current_service_id()
            query = query.where(
                or_(
                    Thread.service_id == service_id,
                    Thread.service_id == PUBLIC_SERVICE_ID,
                )
            )
        threads = s.exec(query).all()
        return [_thread_to_response(t) for t in threads]


@router.post("", response_model=ThreadRead)
def create_thread(body: ThreadCreate):
    service_id = _resolve_target_service_id_from_body(body.service_id)
    external_ref = _normalize_external_ref(body.external_ref)
    meta_json = _normalize_meta_json(body.meta_json)
    with Session(engine) as s:
        if external_ref:
            existing = _find_thread_by_external_ref(s, service_id, external_ref)
            if existing:
                existing = _apply_existing_thread_updates(
                    s,
                    existing,
                    incoming_title=body.title,
                    incoming_meta=meta_json,
                )
                return _thread_to_response(existing)

        t = _create_thread_with_default_context_set(
            s,
            service_id=service_id,
            title=body.title or "Untitled",
            external_ref=external_ref,
            meta_json=meta_json,
        )
        s.commit()
        s.refresh(t)
    return _thread_to_response(t)


@router.post("/ensure", response_model=ThreadRead)
def ensure_thread(body: ThreadEnsureRequest):
    external_ref = _normalize_external_ref(body.external_ref)
    if not external_ref:
        raise HTTPException(400, "external_ref is required")
    service_id = _resolve_target_service_id_from_body(body.service_id)
    meta_json = _normalize_meta_json(body.meta_json)

    with Session(engine) as s:
        existing = _find_thread_by_external_ref(s, service_id, external_ref)
        if existing:
            existing = _apply_existing_thread_updates(
                s,
                existing,
                incoming_title=body.title,
                incoming_meta=meta_json,
            )
            return _thread_to_response(existing)

        t = _create_thread_with_default_context_set(
            s,
            service_id=service_id,
            title=body.title or "Untitled",
            external_ref=external_ref,
            meta_json=meta_json,
        )
        s.commit()
        s.refresh(t)
        return _thread_to_response(t)


@router.get("/{thread_id}", response_model=ThreadRead)
def get_thread(thread_id: str):
    with Session(engine) as s:
        thread = require_thread_access(s, thread_id)
        return _thread_to_response(thread)


@router.delete("/{thread_id}")
def delete_thread(thread_id: str):
    with Session(engine) as s:
        t = require_thread_write_access(s, thread_id)

        edges = s.exec(select(Edge).where(Edge.thread_id == thread_id)).all()
        nodes = s.exec(select(Node).where(Node.thread_id == thread_id)).all()
        ctx_sets = s.exec(select(ContextSet).where(ContextSet.thread_id == thread_id)).all()
        ctx_versions = s.exec(select(ContextSetVersion).where(ContextSetVersion.thread_id == thread_id)).all()
        embeddings = s.exec(select(NodeEmbedding).where(NodeEmbedding.thread_id == thread_id)).all()

        for e in edges:
            s.delete(e)
        for ne in embeddings:
            s.delete(ne)
        for v in ctx_versions:
            s.delete(v)
        for n in nodes:
            s.delete(n)
        for cs in ctx_sets:
            s.delete(cs)
        s.delete(t)
        s.commit()

    warning = None
    try:
        remove_thread_index(thread_id)
    except Exception as e:
        warning = f"thread index cleanup failed: {e}"
        logger.exception("thread index cleanup failed (thread_id=%s)", thread_id)

    return {
        "ok": True,
        "deleted_thread_id": thread_id,
        "deleted_node_count": len(nodes),
        "deleted_edge_count": len(edges),
        "deleted_context_set_count": len(ctx_sets),
        "deleted_context_version_count": len(ctx_versions),
        "deleted_embedding_count": len(embeddings),
        "warning": warning,
    }


@router.get("/{thread_id}/graph")
def get_graph(thread_id: str):
    with Session(engine) as s:
        t = require_thread_access(s, thread_id)
        graph, _, _ = _thread_graph_payload(s, thread_id)
        return {
            "thread": _thread_to_response(t),
            **graph,
        }


@router.get("/{thread_id}/harness_spec", response_model=HarnessSpecRead)
def get_harness_spec(thread_id: str):
    with Session(engine) as s:
        thread = require_thread_access(s, thread_id)
        spec = get_thread_harness_spec(thread)
        return HarnessSpecRead(thread_id=thread.id, harness_spec=spec, harness_summary=build_harness_summary(spec))


@router.put("/{thread_id}/harness_spec", response_model=HarnessSpecRead)
def put_harness_spec(thread_id: str, body: HarnessSpecUpdateRequest):
    with Session(engine) as s:
        thread = require_thread_write_access(s, thread_id)
        spec = save_thread_harness_spec(s, thread, body.harness_spec)
        return HarnessSpecRead(thread_id=thread.id, harness_spec=spec, harness_summary=build_harness_summary(spec))


@router.get("/{thread_id}/harness_package", response_model=HarnessPackageRead)
def get_harness_package(thread_id: str):
    with Session(engine) as s:
        thread = require_thread_access(s, thread_id)
        return HarnessPackageRead.model_validate(build_harness_package_payload(s, thread=thread))


@router.get("/{thread_id}/run_studio/summary")
def get_run_studio_summary(
    thread_id: str,
    context_set_id: str | None = Query(default=None),
):
    with Session(engine) as s:
        thread = require_thread_access(s, thread_id)
        try:
            summary = build_run_studio_summary(
                s,
                thread=thread,
                context_set_id=context_set_id,
            )
        except ValueError as exc:
            raise HTTPException(404, str(exc))
        return {"ok": True, **summary}


@router.get("/{thread_id}/run_studio/agent_team")
def get_run_studio_agent_team(thread_id: str):
    with Session(engine) as s:
        thread = require_thread_access(s, thread_id)
        team = build_run_studio_agent_team(s, thread=thread)
        return {"ok": True, **team}


@router.get("/{thread_id}/run_studio/context_decisions")
def get_run_studio_context_decisions(
    thread_id: str,
    context_set_id: str | None = Query(default=None),
):
    with Session(engine) as s:
        thread = require_thread_access(s, thread_id)
        try:
            decisions = build_run_studio_context_decisions(
                s,
                thread=thread,
                context_set_id=context_set_id,
            )
        except ValueError as exc:
            raise HTTPException(404, str(exc))
        return {"ok": True, **decisions}


@router.get("/{thread_id}/run_studio/evidence")
def get_run_studio_evidence(
    thread_id: str,
    context_set_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
):
    with Session(engine) as s:
        thread = require_thread_access(s, thread_id)
        try:
            evidence = build_run_studio_evidence(
                s,
                thread=thread,
                context_set_id=context_set_id,
                run_id=_clean_optional_text(run_id),
            )
        except ValueError as exc:
            raise HTTPException(404, str(exc))
        return {"ok": True, **evidence}


@router.get("/{thread_id}/run_studio/trace_scope")
def get_run_studio_trace_scope(
    thread_id: str,
    run_id: str | None = Query(default=None),
):
    with Session(engine) as s:
        thread = require_thread_access(s, thread_id)
        summary = build_run_studio_trace_scope(
            s,
            thread=thread,
            run_id=run_id,
        )
        return {"ok": True, **summary}


@router.get("/{thread_id}/run_studio/run_bundle")
def get_run_studio_run_bundle(
    thread_id: str,
    context_set_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
):
    with Session(engine) as s:
        thread = require_thread_access(s, thread_id)
        try:
            summary = build_run_studio_run_bundle(
                s,
                thread=thread,
                context_set_id=_clean_optional_text(context_set_id),
                run_id=_clean_optional_text(run_id),
            )
        except ValueError as exc:
            raise HTTPException(404, str(exc))
        return {"ok": True, **summary}


@router.get("/{thread_id}/run_studio/context_packs")
def get_run_studio_context_packs(
    thread_id: str,
    run_id: str | None = Query(default=None),
):
    with Session(engine) as s:
        thread = require_thread_access(s, thread_id)
        summary = build_run_studio_context_packs(
            s,
            thread=thread,
            run_id=_clean_optional_text(run_id),
        )
        return {"ok": True, **summary}


@router.get("/{thread_id}/run_studio/skill_usage")
def get_run_studio_skill_usage(
    thread_id: str,
    run_id: str | None = Query(default=None),
):
    with Session(engine) as s:
        thread = require_thread_access(s, thread_id)
        summary = build_run_studio_skill_usage(
            s,
            thread=thread,
            run_id=_clean_optional_text(run_id),
        )
        return {"ok": True, **summary}


@router.post("/{thread_id}/scope_materialize")
def post_scope_materialize(
    thread_id: str,
    body: dict[str, Any] | None = None,
):
    with Session(engine) as s:
        require_thread_access(s, thread_id)
        payload = body if isinstance(body, dict) else {}
        runtime_snapshot = payload.get("runtime_snapshot") if isinstance(payload.get("runtime_snapshot"), dict) else payload
        requested_scope_id = str(payload.get("scope_id") or payload.get("scopeId") or "").strip()
        if requested_scope_id and not get_scope_spec(runtime_snapshot, requested_scope_id):
            raise HTTPException(404, "scope_id not found in runtime snapshot")
        materialized_scopes = materialize_runtime_scopes(
            s,
            thread_id=thread_id,
            runtime_snapshot=runtime_snapshot,
            scope_id=requested_scope_id or None,
        )
        if requested_scope_id:
            materialized_scopes = [
                item for item in materialized_scopes
                if str(item.get("scope_id") or item.get("scopeId") or "").strip() == requested_scope_id
            ]
        return {
            "ok": True,
            "thread_id": thread_id,
            "materialized_scopes": materialized_scopes,
            "count": len(materialized_scopes),
        }


@router.get("/{thread_id}/skill_usage")
def get_thread_skill_usage(
    thread_id: str,
    run_id: str | None = Query(default=None),
):
    with Session(engine) as s:
        thread = require_thread_access(s, thread_id)
        summary = build_run_studio_skill_usage(
            s,
            thread=thread,
            run_id=_clean_optional_text(run_id),
        )
        return {"ok": True, **summary}


@router.get("/{thread_id}/trace_export")
def export_thread_trace(
    thread_id: str,
    run_id: str | None = Query(default=None),
    include_compiled: bool = Query(default=True),
    max_compiled_chars: int = Query(default=10000, ge=0, le=200000),
    format: str = Query(default="zip"),
):
    export_format = (format or "zip").strip().lower()
    if export_format != "zip":
        raise HTTPException(400, "unsupported format; only zip is currently supported")

    scoped_run_id = _clean_optional_text(run_id)

    with Session(engine) as s:
        thread = require_thread_access(s, thread_id)
        graph, nodes, edges = _thread_graph_payload(s, thread_id)

        all_steps = [n for n in nodes if n.type == "Step"]
        step_payload_by_id = {n.id: _node_payload(n) for n in all_steps}
        scoped_steps = all_steps
        if scoped_run_id:
            scoped_steps = [n for n in all_steps if str(step_payload_by_id.get(n.id, {}).get("run_id") or "").strip() == scoped_run_id]

        context_set_ids: set[str] = set()
        for step in scoped_steps:
            context_set_ids.update(_collect_context_set_ids(step_payload_by_id.get(step.id, {})))

        context_sets_payload: dict[str, dict[str, Any]] = {}
        compiled_payload: dict[str, str] = {}
        missing_context_set_ids: list[str] = []

        for context_set_id in sorted(context_set_ids):
            cs = s.get(ContextSet, context_set_id)
            if not cs or cs.thread_id != thread_id:
                missing_context_set_ids.append(context_set_id)
                continue

            active_node_ids = jload(cs.active_node_ids_json, [])
            context_item = cs.model_dump()
            context_item["active_node_ids"] = active_node_ids
            context_sets_payload[context_set_id] = context_item

            if include_compiled:
                compiled = compile_active_context_explain(s, cs.thread_id, active_node_ids)
                compiled_text = str(compiled.get("compiled_text") or "")
                compiled_payload[context_set_id] = compiled_text[:max_compiled_chars]

        run_summaries = _build_run_summaries(nodes, edges, scoped_steps, scoped_run_id)

        now = datetime.now(timezone.utc)
        ts = now.strftime("%Y%m%dT%H%M%SZ")
        filename = f"trace_export_{_safe_file_component(thread_id)}_{ts}.zip"

        manifest = {
            "kind": "goc_trace_export",
            "version": 1,
            "generated_at": now.isoformat(),
            "thread_id": thread_id,
            "scope": {
                "run_id": scoped_run_id,
                "scoped_step_count": len(scoped_steps),
                "total_step_count": len(all_steps),
            },
            "options": {
                "format": export_format,
                "include_compiled": include_compiled,
                "max_compiled_chars": max_compiled_chars,
            },
            "counts": {
                "nodes": len(nodes),
                "edges": len(edges),
                "runs": len(run_summaries),
                "context_sets": len(context_sets_payload),
                "compiled_files": len(compiled_payload),
            },
            "run_ids": sorted(run_summaries.keys()),
            "context_set_ids": sorted(context_sets_payload.keys()),
            "missing_context_set_ids": missing_context_set_ids,
        }

        notes_text = (
            "Graph-of-Context trace export\n"
            "- manifest.json: export metadata and options.\n"
            "- thread.json: thread metadata snapshot.\n"
            "- graph.json: full node/edge graph snapshot.\n"
            "- runs/*.json: run summary plus connected Step details.\n"
            "- context_sets/*.json: active_node_ids/version snapshot per context set.\n"
            "- compiled/*.txt: compiled context text (truncated to max_compiled_chars).\n"
            "Caution: export is a point-in-time snapshot and may contain sensitive prompts/results.\n"
        )

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", _json_text(manifest))
            archive.writestr("thread.json", _json_text(_thread_to_response(thread).model_dump()))
            archive.writestr("graph.json", _json_text(graph))
            for exported_run_id, summary in run_summaries.items():
                archive.writestr(f"runs/{_safe_file_component(exported_run_id)}.json", _json_text(summary))
            for context_set_id, payload in context_sets_payload.items():
                archive.writestr(f"context_sets/{_safe_file_component(context_set_id)}.json", _json_text(payload))
            if include_compiled:
                for context_set_id, compiled_text in compiled_payload.items():
                    archive.writestr(f"compiled/{_safe_file_component(context_set_id)}.txt", compiled_text)
            archive.writestr("notes.txt", notes_text)

        return Response(
            content=buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


@router.get("/{thread_id}/nodes")
def list_thread_nodes(
    thread_id: str,
    context_set_id: str | None = Query(default=None),
    type: str | None = Query(default=None),
    node_type: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
):
    """List thread-scoped graph nodes using the canonical create-node route family."""
    clean_context_set_id = _clean_optional_text(context_set_id)
    requested_type = _clean_optional_text(node_type) or _clean_optional_text(type)
    with Session(engine) as s:
        require_thread_access(s, thread_id)
        statement = select(Node).where(Node.thread_id == thread_id)
        if requested_type:
            statement = statement.where(Node.type == requested_type)
        rows = s.exec(statement.order_by(Node.created_at.asc(), Node.id.asc()).limit(limit)).all()
        active_ids: list[str] | None = None
        if clean_context_set_id:
            scoped_context_set = s.get(ContextSet, clean_context_set_id)
            if not scoped_context_set or scoped_context_set.thread_id != thread_id:
                raise HTTPException(404, "context set not found in thread")
            parsed_active = jload(scoped_context_set.active_node_ids_json or "[]", [])
            active_ids = [str(value).strip() for value in parsed_active if str(value).strip()] if isinstance(parsed_active, list) else []
            active_set = set(active_ids)
            rows = [row for row in rows if row.id in active_set]
            order = {node_id: index for index, node_id in enumerate(active_ids)}
            rows.sort(key=lambda row: (order.get(row.id, len(order)), row.created_at, row.id))
        items = [row.model_dump() for row in rows]
        return {"ok": True, "thread_id": thread_id, "context_set_id": clean_context_set_id, "context_set_active_node_ids": active_ids, "count": len(items), "items": items, "nodes": items}


@router.get("/{thread_id}/edges")
def list_thread_edges(
    thread_id: str,
    type: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
):
    requested_type = _clean_optional_text(type)
    with Session(engine) as s:
        require_thread_access(s, thread_id)
        statement = select(Edge).where(Edge.thread_id == thread_id)
        if requested_type:
            statement = statement.where(Edge.type == requested_type)
        rows = s.exec(statement.order_by(Edge.created_at.asc(), Edge.id.asc()).limit(limit)).all()
        items = [row.model_dump() for row in rows]
        return {"ok": True, "thread_id": thread_id, "count": len(items), "items": items, "edges": items}


@router.post("/{thread_id}/layout")
def save_layout(thread_id: str, body: NodeLayoutUpdate):
    with Session(engine) as s:
        require_thread_write_access(s, thread_id)

        ids = [p.id for p in body.positions]
        if not ids:
            return {"ok": True, "updated": 0}

        nodes = s.exec(
            select(Node)
            .where(Node.thread_id == thread_id)
            .where(Node.id.in_(ids))
        ).all()
        by_id = {n.id: n for n in nodes}

        updated = 0
        for p in body.positions:
            n = by_id.get(p.id)
            if not n:
                continue
            payload = jload(n.payload_json, {})
            payload["_ui_pos"] = {"x": float(p.x), "y": float(p.y)}
            n.payload_json = jdump(payload)
            s.add(n)
            updated += 1

        s.commit()
        return {"ok": True, "updated": updated}


@router.post("/{thread_id}/nodes", response_model=NodeCreateResponse)
def create_node(thread_id: str, body: NodeCreate):
    node_type = (body.type or "").strip()
    if not node_type:
        raise HTTPException(400, "type is required")
    if node_type not in ALLOWED_NODE_TYPES:
        raise HTTPException(400, f"invalid node type: {node_type}")

    connect_from = body.connect_from
    connect_source: Node | None = None
    connect_edge_type: str | None = None

    with Session(engine) as s:
        require_thread_write_access(s, thread_id)

        last_node_before_insert: Node | None = None
        if connect_from == "last":
            last_node_before_insert = get_last_node(s, thread_id)
            connect_edge_type = "NEXT"
        elif connect_from is not None:
            source_id = (connect_from.node_id or "").strip()
            edge_type = (connect_from.edge_type or "").strip() or "NEXT"
            if not source_id:
                raise HTTPException(400, "connect_from.node_id is required")
            if edge_type not in ALLOWED_EDGE_TYPES:
                raise HTTPException(400, f"invalid edge type: {edge_type}")

            source_node = require_node_access(s, source_id)
            if source_node.thread_id != thread_id:
                raise HTTPException(404, "source node not found in thread")
            connect_source = source_node
            connect_edge_type = edge_type

        node = Node(
            thread_id=thread_id,
            type=node_type,
            text=body.text,
            payload_json=jdump(body.payload_json if isinstance(body.payload_json, dict) else {}),
        )
        s.add(node)
        s.flush()

        if connect_from == "last" and last_node_before_insert and last_node_before_insert.id != node.id:
            s.add(add_edge(thread_id, last_node_before_insert.id, node.id, "NEXT"))
        elif connect_source and connect_edge_type and connect_source.id != node.id:
            s.add(add_edge(thread_id, connect_source.id, node.id, connect_edge_type))

        s.commit()
        s.refresh(node)
        return node.model_dump()


@router.post("/{thread_id}/edges")
def create_edge(thread_id: str, body: EdgeCreate):
    if body.type not in ALLOWED_EDGE_TYPES:
        raise HTTPException(400, f"invalid edge type: {body.type}")

    with Session(engine) as s:
        require_thread_write_access(s, thread_id)

        src = require_node_access(s, body.from_id)
        dst = require_node_access(s, body.to_id)
        if src.thread_id != thread_id:
            raise HTTPException(404, "source node not found in thread")
        if dst.thread_id != thread_id:
            raise HTTPException(404, "target node not found in thread")

        existing = s.exec(
            select(Edge)
            .where(Edge.thread_id == thread_id)
            .where(Edge.from_id == body.from_id)
            .where(Edge.to_id == body.to_id)
            .where(Edge.type == body.type)
            .limit(1)
        ).first()
        if existing:
            return existing.model_dump()

        e = Edge(
            thread_id=thread_id,
            from_id=body.from_id,
            to_id=body.to_id,
            type=body.type,
            payload_json=jdump({}),
        )
        s.add(e)
        s.commit()
        s.refresh(e)
        return e.model_dump()


@router.delete("/{thread_id}/edges/{edge_id}")
def delete_edge(thread_id: str, edge_id: str):
    with Session(engine) as s:
        require_thread_write_access(s, thread_id)

        e = s.get(Edge, edge_id)
        if not e or e.thread_id != thread_id:
            raise HTTPException(404, "edge not found")

        s.delete(e)
        s.commit()
        return {"ok": True, "deleted_edge_id": edge_id}


@router.delete("/{thread_id}/nodes/{node_id}")
def delete_node(thread_id: str, node_id: str):
    with Session(engine) as s:
        require_thread_write_access(s, thread_id)

        n = require_node_access(s, node_id)
        if n.thread_id != thread_id:
            raise HTTPException(404, "node not found")

        outgoing = s.exec(
            select(Edge)
            .where(Edge.thread_id == thread_id)
            .where(Edge.from_id == node_id)
        ).all()
        incoming = s.exec(
            select(Edge)
            .where(Edge.thread_id == thread_id)
            .where(Edge.to_id == node_id)
        ).all()
        edge_by_id = {e.id: e for e in outgoing}
        for e in incoming:
            edge_by_id[e.id] = e
        for e in edge_by_id.values():
            s.delete(e)

        sets = s.exec(select(ContextSet).where(ContextSet.thread_id == thread_id)).all()
        for cs in sets:
            active = jload(cs.active_node_ids_json, [])
            next_active = [nid for nid in active if nid != node_id]
            if len(next_active) == len(active):
                continue
            cs.active_node_ids_json = jdump(next_active)
            snapshot_context_set(s, cs, reason="delete_node", changed_node_ids=[node_id], meta={"deleted_node_id": node_id})

        ne = s.get(NodeEmbedding, node_id)
        if ne:
            s.delete(ne)

        s.delete(n)
        s.commit()
        warning = None
        try:
            rebuild_thread_index(s, thread_id)
        except Exception as e:
            warning = f"index rebuild failed: {e}"
            logger.exception("index rebuild failed after node delete (thread_id=%s, node_id=%s)", thread_id, node_id)
        return {
            "ok": True,
            "deleted_node_id": node_id,
            "deleted_edge_count": len(edge_by_id),
            "warning": warning,
        }


@router.post("/{thread_id}/rebuild_index")
def rebuild_index(thread_id: str):
    with Session(engine) as s:
        require_thread_write_access(s, thread_id)
        stats = rebuild_thread_index(s, thread_id)
        return {"ok": True, "rebuild": stats}


@router.get("/{thread_id}/team/config", response_model=ConversationTeamConfigRead)
def get_thread_team_config(thread_id: str):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        payload = get_team_config_payload(session, thread_id=thread_id)
        return ConversationTeamConfigRead(**payload)


@router.put("/{thread_id}/team/config", response_model=ConversationTeamConfigRead)
def put_thread_team_config(thread_id: str, body: ConversationTeamConfigRequest):
    with Session(engine) as session:
        require_thread_write_access(session, thread_id)
        try:
            payload = save_team_config_payload(session, thread_id=thread_id, payload=body.team_config or {})
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        return ConversationTeamConfigRead(**payload)


@router.patch("/{thread_id}/team/config/agents/context_policy", response_model=ConversationTeamConfigRead)
def patch_thread_team_agent_context_policy(thread_id: str, body: ConversationTeamAgentContextPolicyPatchRequest):
    with Session(engine) as session:
        require_thread_write_access(session, thread_id)
        try:
            payload = patch_team_config_agent_context_policy(
                session,
                thread_id=thread_id,
                team_state=body.team_state,
                agent_id=body.agent_id,
                visibility_mode=body.visibility_mode,
                grants=list(body.grants or []),
                context_types=list(body.context_types or []),
                publish_targets=list(body.publish_targets or []),
                query_template=body.query_template,
                soft_tokens=body.soft_tokens,
                hard_tokens=body.hard_tokens,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return ConversationTeamConfigRead(**payload)



@router.get("/{thread_id}/team/blueprint/templates")
def get_team_blueprint_templates(thread_id: str):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        return export_team_blueprint_templates()


@router.get("/{thread_id}/team/blueprint")
def get_thread_team_blueprint(thread_id: str):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        blueprint = export_thread_team_blueprint(session, thread)
        return {"ok": True, "manifest": blueprint}


@router.post("/{thread_id}/team/blueprint/validate")
def validate_thread_team_blueprint(thread_id: str, body: TeamManifestValidateRequest):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        result = validate_team_blueprint_payload(body.manifest or {}, apply_state=body.apply_state or "active")
        return {"ok": bool(result.get("ok")), **result}


@router.post("/{thread_id}/team/blueprint/diff")
def diff_thread_team_blueprint(thread_id: str, body: TeamManifestDiffRequest):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        current_blueprint = export_thread_team_blueprint(session, thread)
        result = diff_team_blueprint_payload(current_blueprint, body.manifest or {}, apply_state=body.apply_state or "active")
        return {"ok": True, **result}


@router.post("/{thread_id}/team/blueprint/install")
def install_team_blueprint(thread_id: str, body: TeamManifestInstallRequest):
    with Session(engine) as session:
        require_thread_write_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        try:
            manifest = install_thread_team_blueprint(session, thread, body.manifest or {}, apply_state=body.apply_state or "active")
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True, "manifest": manifest, "team_config": manifest.get("team_config") or {}}




@router.get("/{thread_id}/memory/review/overview")
def get_thread_memory_review_overview(thread_id: str):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        return build_memory_review_overview(session, thread)


@router.get("/{thread_id}/review/inbox")
def get_thread_review_inbox(thread_id: str, include_detected: bool = True, limit: int = 100):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        return build_review_inbox(session, thread, include_detected=include_detected, limit=limit)


@router.get("/{thread_id}/proposals")
def get_thread_runtime_proposals(thread_id: str, status: str | None = None, kind: str | None = None, include_closed: bool = False, limit: int = 100):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        return list_runtime_proposals(session, thread, status=status, kind=kind, include_closed=include_closed, limit=limit)


@router.post("/{thread_id}/proposals")
def post_thread_runtime_proposals(thread_id: str, body: dict[str, Any] = Body(default_factory=dict)):
    with Session(engine) as session:
        require_thread_write_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        rows = []
        if isinstance(body, dict):
            if isinstance(body.get("proposals"), list):
                rows = body.get("proposals") or []
            elif isinstance(body.get("proposal"), dict):
                rows = [body.get("proposal") or {}]
            else:
                rows = [body]
        source = str((body or {}).get("source") or "ddalggak").strip() if isinstance(body, dict) else "ddalggak"
        run_id = str((body or {}).get("run_id") or (body or {}).get("runId") or "").strip() if isinstance(body, dict) else ""
        return upsert_runtime_proposals(session, thread, rows, source=source, run_id=run_id or None)


@router.post("/{thread_id}/proposals/{proposal_id}/action")
def post_thread_runtime_proposal_action(thread_id: str, proposal_id: str, body: dict[str, Any] = Body(default_factory=dict)):
    with Session(engine) as session:
        require_thread_write_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        try:
            return apply_runtime_proposal_action(session, thread, proposal_id, body or {})
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.post("/{thread_id}/canonical-projections/worker")
def post_thread_canonical_projection_worker(thread_id: str, body: dict[str, Any] = Body(default_factory=dict)):
    with Session(engine) as session:
        require_thread_write_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        projections = body.get("projections") if isinstance(body, dict) and isinstance(body.get("projections"), list) else []
        limit = int((body or {}).get("limit") or 50) if isinstance(body, dict) else 50
        actor = str((body or {}).get("actor") or "goc_projection_worker") if isinstance(body, dict) else "goc_projection_worker"
        return process_runtime_proposal_projections(session, thread, projections=projections, limit=limit, actor=actor)


@router.get("/{thread_id}/semantic-index/search")
def get_thread_semantic_index_search(thread_id: str, query: str = "", item_type: list[str] | None = Query(default=None), limit: int = 10, include_inactive: bool = False):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        return search_thread_semantic_items(session, thread, query=query, item_types=item_type or [], limit=limit, include_inactive=include_inactive)


@router.get("/{thread_id}/watch-tasks")
def get_thread_watch_tasks(thread_id: str, limit: int = 20):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        return list_thread_watch_tasks(session, thread, limit=limit)


@router.post("/{thread_id}/watch-tasks")
def post_thread_watch_task(thread_id: str, body: dict[str, Any] = Body(default_factory=dict)):
    with Session(engine) as session:
        require_thread_write_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        return upsert_thread_watch_task(session, thread, body or {}, source=str((body or {}).get("source") or "ddalggak"))


@router.post("/{thread_id}/watch-tasks/{task_id}/action")
def post_thread_watch_task_action(thread_id: str, task_id: str, body: dict[str, Any] = Body(default_factory=dict)):
    with Session(engine) as session:
        require_thread_write_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        try:
            return apply_watch_task_action(
                session,
                thread,
                task_id,
                action=str((body or {}).get("action") or ""),
                reason=str((body or {}).get("reason") or ""),
                actor=str((body or {}).get("actor") or "goc"),
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.post("/{thread_id}/memory/materialization/preview")
def preview_thread_memory_materialization(thread_id: str, body: dict[str, Any] = Body(default_factory=dict)):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        min_score = 0.28
        max_candidates = 6
        if isinstance(body, dict):
            try:
                min_score = float(body.get("min_score", min_score))
            except Exception:
                min_score = 0.28
            try:
                max_candidates = int(body.get("max_candidates", max_candidates))
            except Exception:
                max_candidates = 6
        return build_memory_materialization_preview(session, thread, min_score=min_score, max_candidates=max_candidates)




@router.post("/{thread_id}/memory/materialization/candidates")
def save_thread_memory_materialization_candidates(thread_id: str, body: dict[str, Any] = Body(default_factory=dict)):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        min_score = 0.28
        max_candidates = 6
        if isinstance(body, dict):
            try:
                min_score = float(body.get("min_score", min_score))
            except Exception:
                min_score = 0.28
            try:
                max_candidates = int(body.get("max_candidates", max_candidates))
            except Exception:
                max_candidates = 6
        return save_memory_materialization_candidates(session, thread, min_score=min_score, max_candidates=max_candidates)


@router.get("/{thread_id}/memory/materialization/candidates")
def get_thread_memory_materialization_candidates(thread_id: str, limit: int = 20):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        return list_memory_materialization_candidates(session, thread, limit=limit)


@router.post("/{thread_id}/memory/materialization/modules/shadow")
def create_thread_shadow_memory_module(thread_id: str, body: dict[str, Any] = Body(default_factory=dict)):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        try:
            return create_shadow_memory_module(session, thread, body)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc


@router.get("/{thread_id}/memory/materialization/modules")
def get_thread_memory_modules(thread_id: str, include_rows: bool = False):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        return list_memory_modules(session, thread, include_rows=include_rows)


@router.get("/{thread_id}/team/manifest")
def get_thread_team_manifest(thread_id: str):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        manifest = export_thread_team_manifest(session, thread)
        return {"ok": True, "manifest": manifest}


@router.post("/{thread_id}/team/manifest/validate")
def validate_thread_team_manifest(thread_id: str, body: TeamManifestValidateRequest):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        result = validate_team_manifest_payload(body.manifest or {}, apply_state=body.apply_state or "active")
        return {"ok": bool(result.get("ok")), **result}




@router.post("/{thread_id}/team/manifest/diff")
def diff_thread_team_manifest(thread_id: str, body: TeamManifestDiffRequest):
    with Session(engine) as session:
        require_thread_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        current_manifest = export_thread_team_manifest(session, thread)
        result = diff_team_manifest_payload(current_manifest, body.manifest or {}, apply_state=body.apply_state or "active")
        return {"ok": True, **result}

@router.post("/{thread_id}/team/install")
def install_team_manifest(thread_id: str, body: TeamManifestInstallRequest):
    with Session(engine) as session:
        require_thread_write_access(session, thread_id)
        thread = session.get(Thread, thread_id)
        if not thread:
            raise HTTPException(404, "thread not found")
        try:
            manifest = install_thread_team_manifest(session, thread, body.manifest or {}, apply_state=body.apply_state or "active")
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"ok": True, "manifest": manifest, "team_config": manifest.get("team_config") or {}}
