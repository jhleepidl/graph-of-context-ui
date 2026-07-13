from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models import HarnessEvaluationRun


CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "recipe_catalog.json"
COLLABORATION_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "collaboration_profiles.json"


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _arr(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, limit: int = 2000) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_evidence(raw: Any) -> dict[str, Any]:
    row = _obj(raw)
    live_runs = max(0, int(_number(row.get("live_runs"), 0)))
    passed_runs = max(0, int(_number(row.get("passed_runs"), 0)))
    explicit_success = row.get("success_rate")
    success_rate = max(0.0, min(1.0, _number(explicit_success, passed_runs / live_runs if live_runs else 0.0)))
    average_score = row.get("average_score")
    return {
        "source": _text(row.get("source"), 300),
        "provider": _text(row.get("provider"), 80),
        "model": _text(row.get("model"), 200),
        "reasoning_effort": _text(row.get("reasoning_effort"), 80),
        "cli_version": _text(row.get("cli_version"), 300),
        "runtime_signature": _text(row.get("runtime_signature"), 900),
        "last_observed_at": _text(row.get("last_observed_at"), 100),
        "current": row.get("current") is True,
        "live_runs": live_runs,
        "passed_runs": passed_runs,
        "success_rate": success_rate,
        "average_score": _number(average_score) if average_score is not None else None,
        "policy_violations": max(0, int(_number(row.get("policy_violations"), 0))),
    }


def derive_recipe_evidence_status(recipe: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    evaluation = _obj(recipe.get("evaluation"))
    evidence = [_normalize_evidence(row) for row in _arr(evaluation.get("evidence"))]
    current_evidence = [row for row in evidence if row.get("current") is True]
    active_evidence = current_evidence or evidence
    totals = {
        "live_runs": sum(row["live_runs"] for row in active_evidence),
        "passed_runs": sum(row["passed_runs"] for row in active_evidence),
        "policy_violations": sum(row["policy_violations"] for row in active_evidence),
        "weighted_score": sum((row["average_score"] or 0.0) * row["live_runs"] for row in active_evidence),
    }
    success_rate = totals["passed_runs"] / totals["live_runs"] if totals["live_runs"] else 0.0
    average_score = totals["weighted_score"] / totals["live_runs"] if totals["live_runs"] else None
    scope = _text(evaluation.get("evidence_scope") or "none", 80).lower()
    status_policy = _obj(catalog.get("status_policy"))
    recommended = _obj(status_policy.get("recommended"))
    evaluated = _obj(status_policy.get("evaluated"))

    status = "experimental"
    reason = "아직 충분한 Live Scenario evidence가 없습니다."
    if evaluation.get("revalidation_required") is True and not current_evidence and totals["live_runs"] > 0:
        status = "revalidation_needed"
        reason = _text(evaluation.get("revalidation_reason") or "모델, CLI, harness 또는 recipe 버전 변경 후 재검증이 필요합니다.", 1200)
    elif (
        totals["live_runs"] >= int(_number(recommended.get("min_live_runs"), 8))
        and success_rate >= _number(recommended.get("min_success_rate"), 0.85)
        and totals["policy_violations"] <= int(_number(recommended.get("max_policy_violations"), 0))
        and scope in {_text(item, 80).lower() for item in _arr(recommended.get("required_evidence_scope"))}
    ):
        status = "recommended"
        reason = "대표성 있는 Live Scenario evidence가 현재 추천 기준을 충족합니다."
    elif (
        totals["live_runs"] >= int(_number(evaluated.get("min_live_runs"), 3))
        and success_rate >= _number(evaluated.get("min_success_rate"), 0.80)
        and totals["policy_violations"] <= int(_number(evaluated.get("max_policy_violations"), 0))
    ):
        status = "evaluated"
        reason = "제한된 범위에서 최소 Live Scenario 평가 기준을 충족했습니다." if scope == "narrow" else "Live Scenario evidence가 최소 평가 기준을 충족했습니다."

    return {
        "status": status,
        "reason": reason,
        "evidence_scope": scope,
        "live_runs": totals["live_runs"],
        "passed_runs": totals["passed_runs"],
        "success_rate": success_rate,
        "average_score": average_score,
        "policy_violations": totals["policy_violations"],
        "evidence": evidence,
        "active_runtime_signature": current_evidence[0].get("runtime_signature") if current_evidence else None,
    }




@lru_cache(maxsize=1)
def load_collaboration_profile_catalog() -> dict[str, Any]:
    data = json.loads(COLLABORATION_CATALOG_PATH.read_text(encoding="utf-8"))
    catalog = _obj(data)
    profiles: list[dict[str, Any]] = []
    for raw in _arr(catalog.get("profiles")):
        profile = _obj(raw).copy()
        if not _text(profile.get("id"), 160):
            continue
        profiles.append(profile)
    return {
        "schema_version": _text(catalog.get("schema_version") or "ai_rooms.collaboration_profile_catalog/v1", 120),
        "catalog_version": _text(catalog.get("catalog_version") or "unknown", 160),
        "profiles": profiles,
    }


def list_collaboration_profiles(*, query: str = "", include_preview: bool = True) -> list[dict[str, Any]]:
    catalog = load_collaboration_profile_catalog()
    q = _text(query, 300).lower()
    out: list[dict[str, Any]] = []
    for profile in _arr(catalog.get("profiles")):
        if not include_preview and _text(profile.get("runtime_support"), 80).lower() != "native":
            continue
        if q:
            haystack = " ".join([
                _text(profile.get("id"), 160),
                _text(profile.get("title"), 240),
                _text(profile.get("title_ko"), 240),
                _text(profile.get("description"), 1200),
                _text(profile.get("description_ko"), 1200),
                _text(profile.get("execution_pattern"), 160),
                *[_text(item, 300) for item in _arr(profile.get("good_for"))],
                *[_text(item, 300) for item in _arr(profile.get("not_for"))],
            ]).lower()
            if q not in haystack:
                continue
        out.append(profile)
    return out


def get_collaboration_profile(profile_id: str) -> dict[str, Any] | None:
    target = _text(profile_id, 160).lower()
    if not target:
        return None
    for profile in _arr(load_collaboration_profile_catalog().get("profiles")):
        if _text(profile.get("id"), 160).lower() == target:
            return profile
    return None


@lru_cache(maxsize=1)
def load_recipe_catalog() -> dict[str, Any]:
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    catalog = _obj(data)
    items: list[dict[str, Any]] = []
    for raw in _arr(catalog.get("recipes")):
        recipe = _obj(raw).copy()
        if not _text(recipe.get("id"), 160):
            continue
        recipe["evidence_summary"] = derive_recipe_evidence_status(recipe, catalog)
        items.append(recipe)
    return {
        "schema_version": _text(catalog.get("schema_version") or "ai_rooms.recipe_catalog/v1", 120),
        "catalog_version": _text(catalog.get("catalog_version") or "unknown", 160),
        "status_policy": _obj(catalog.get("status_policy")),
        "recipes": items,
    }


def _parse_dt(value: Any) -> datetime | None:
    text = _text(value, 100)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _runtime_evidence_from_runs(session: Session, *, limit: int = 200) -> dict[str, dict[str, Any]]:
    cap = max(1, min(int(limit or 200), 1000))
    rows = list(session.exec(select(HarnessEvaluationRun).order_by(HarnessEvaluationRun.ingested_at.desc()).limit(cap)).all())
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    latest_signature: dict[str, tuple[datetime, str]] = {}
    for row in rows:
        try:
            payload = json.loads(row.payload_json or "{}")
        except Exception:
            continue
        for raw_run in _arr(_obj(payload).get("runs")):
            run = _obj(raw_run)
            if run.get("dry_run") is True:
                continue
            signature = _text(run.get("runtime_signature"), 900)
            if not signature:
                continue
            completed_at = _parse_dt(run.get("completed_at")) or row.finished_at or row.ingested_at or datetime.min.replace(tzinfo=timezone.utc)
            for raw_recipe_id in _arr(run.get("recipe_ids")):
                recipe_id = _text(raw_recipe_id, 160)
                if not recipe_id:
                    continue
                key = (recipe_id, signature)
                current = grouped.setdefault(key, {
                    "source": "goc_harness_evaluation_runs",
                    "provider": _text(run.get("provider"), 80),
                    "model": _text(run.get("model"), 200),
                    "reasoning_effort": _text(run.get("reasoning_effort"), 80),
                    "cli_version": _text(run.get("cli_version"), 300),
                    "runtime_signature": signature,
                    "last_observed_at": completed_at.isoformat(),
                    "current": False,
                    "live_runs": 0,
                    "passed_runs": 0,
                    "score_total": 0.0,
                    "policy_violations": 0,
                })
                current["live_runs"] += 1
                current["passed_runs"] += 1 if run.get("passed") is True else 0
                current["score_total"] += _number(run.get("score"), 0.0)
                current["last_observed_at"] = max(_text(current.get("last_observed_at"), 100), completed_at.isoformat())
                deterministic = _obj(run.get("deterministic_evaluation"))
                explicit_violations = run.get("policy_violations")
                if explicit_violations is not None:
                    current["policy_violations"] += max(0, int(_number(explicit_violations, 0)))
                else:
                    current["policy_violations"] += sum(
                        1
                        for check in _arr(deterministic.get("checks"))
                        if _obj(check).get("passed") is False
                        and "forbidden" in _text(_obj(check).get("name"), 200).lower()
                    )
                latest = latest_signature.get(recipe_id)
                if latest is None or completed_at > latest[0]:
                    latest_signature[recipe_id] = (completed_at, signature)
    out: dict[str, dict[str, Any]] = {}
    for (recipe_id, signature), current in grouped.items():
        latest = latest_signature.get(recipe_id)
        if not latest or latest[1] != signature:
            continue
        live_runs = max(0, int(current.pop("live_runs", 0)))
        passed_runs = max(0, int(current.pop("passed_runs", 0)))
        score_total = _number(current.pop("score_total", 0.0), 0.0)
        current.update({
            "current": True,
            "live_runs": live_runs,
            "passed_runs": passed_runs,
            "success_rate": (passed_runs / live_runs) if live_runs else 0.0,
            "average_score": (score_total / live_runs) if live_runs else None,
        })
        out[recipe_id] = current
    return out


def load_recipe_catalog_with_evidence(session: Session | None = None) -> dict[str, Any]:
    catalog = json.loads(json.dumps(load_recipe_catalog(), ensure_ascii=False))
    if session is None:
        return catalog
    runtime_evidence = _runtime_evidence_from_runs(session)
    for recipe in _arr(catalog.get("recipes")):
        recipe_id = _text(_obj(recipe).get("id"), 160)
        evidence = runtime_evidence.get(recipe_id)
        if not evidence:
            continue
        evaluation = _obj(recipe.get("evaluation")).copy()
        rows = list(_arr(evaluation.get("evidence")))
        rows.append(evidence)
        evaluation["evidence"] = rows
        evaluation["revalidation_required"] = False
        evaluation.pop("revalidation_reason", None)
        recipe["evaluation"] = evaluation
        recipe["evidence_summary"] = derive_recipe_evidence_status(recipe, catalog)
    return catalog


def list_recipes(*, query: str = "", category: str = "", status: str = "", catalog: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    catalog = catalog or load_recipe_catalog()
    q = _text(query, 300).lower()
    category_key = _text(category, 100).lower()
    status_key = _text(status, 80).lower()
    out: list[dict[str, Any]] = []
    for recipe in _arr(catalog.get("recipes")):
        if category_key and _text(recipe.get("category"), 100).lower() != category_key:
            continue
        if status_key and _text(_obj(recipe.get("evidence_summary")).get("status"), 80).lower() != status_key:
            continue
        if q:
            haystack = " ".join([
                _text(recipe.get("id"), 160),
                _text(recipe.get("title"), 240),
                _text(recipe.get("title_ko"), 240),
                _text(recipe.get("category"), 100),
                _text(recipe.get("description"), 1200),
                _text(recipe.get("description_ko"), 1200),
                *[_text(tag, 100) for tag in _arr(recipe.get("tags"))],
            ]).lower()
            if q not in haystack:
                continue
        out.append(recipe)
    return out


def get_recipe(recipe_id: str, *, catalog: dict[str, Any] | None = None) -> dict[str, Any] | None:
    target = _text(recipe_id, 160).lower()
    if not target:
        return None
    source = catalog or load_recipe_catalog()
    for recipe in _arr(source.get("recipes")):
        if _text(recipe.get("id"), 160).lower() == target:
            return recipe
    return None
