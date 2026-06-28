from __future__ import annotations

import re
from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else ([] if value is None else [value])


def _clean(value: Any = "", max_len: int = 500, lower: bool = False) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()[:max_len]
    return text.lower() if lower else text


def _slug(value: Any = "", fallback: str = "unknown") -> str:
    text = _clean(value or fallback, 120, True)
    clean = re.sub(r"[^a-z0-9가-힣._:-]+", "_", text).strip("_")
    return clean or fallback


def _has_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in patterns)


def _count_matches(text: str, patterns: list[str]) -> int:
    return sum(1 for pattern in patterns if re.search(pattern, text, re.I))


QUESTION_SPECS: dict[str, dict[str, Any]] = {
    "schema_direction_confirmation": {
        "question": "앞으로 이 room의 중심 구조를 '{candidate}' 기준으로 잡아둘까요?",
        "target_field": "schema_direction",
        "options": ["record_as_main_direction", "keep_as_candidate_only", "discard"],
    },
    "scope_confirmation": {
        "question": "이 규칙은 현재 room에만 적용할까요, 아니면 관련 AI Rooms 전체 작업방식으로 볼까요?",
        "target_field": "scope",
        "options": ["current_room", "related_ai_rooms", "global_workflow"],
    },
    "permanence_confirmation": {
        "question": "이 내용은 이번 작업에만 필요한 임시 판단인가요, 아니면 앞으로도 유지할 room 규칙으로 기록할까요?",
        "target_field": "permanence",
        "options": ["temporary_this_task", "shadow_memory_candidate", "persistent_room_rule"],
    },
    "exportability_confirmation": {
        "question": "이 내용은 다음 handoff/export package에 포함해도 될까요, 아니면 room 내부 판단 근거로만 남길까요?",
        "target_field": "exportability",
        "options": ["include_in_handoff", "internal_only", "ask_each_time"],
    },
    "package_view_confirmation": {
        "question": "다음 package는 현재 작업을 이어받는 operational view로 만들까요, 아니면 이전 결정까지 포함한 audit view로 만들까요?",
        "target_field": "package_view",
        "options": ["operational_view", "audit_view", "public_view"],
    },
}

AMBIGUITY_PATTERNS = [
    r"애매",
    r"확인",
    r"물어",
    r"clarif",
    r"uncertain",
    r"ambiguous",
    r"whether",
    r"should\s+i",
    r"should\s+we",
    r"\?",
    r"할까요",
    r"될까요",
    r"될까",
    r"어떻게 할",
]

RESOLVED_NEGATIVE_POLICY_PATTERNS = [
    r"넣지 말",
    r"포함하지 말",
    r"공유하지 말",
    r"내보내지 말",
    r"exclude",
    r"do not include",
    r"don['’]?t include",
    r"internal[-_\s]?only",
    r"내부.*남",
]


def classify_room_package_question_signals(
    *,
    recent_turns: list[dict[str, Any]] | None = None,
    candidate_memory_writes: list[dict[str, Any]] | None = None,
    room_package: dict[str, Any] | None = None,
    task_text: str = "",
) -> dict[str, Any]:
    pkg = _as_dict(room_package)
    memory = _as_dict(pkg.get("memory_schema") or pkg.get("memorySchema"))
    texts: list[str] = [task_text]
    candidate_rows = [_as_dict(row) for row in _as_list(candidate_memory_writes)]
    for turn in _as_list(recent_turns):
        row = _as_dict(turn)
        texts.append(f"{row.get('role', '')} {row.get('text') or row.get('content') or row.get('message') or ''}")
    for row in candidate_rows:
        texts.append(
            f"{row.get('object_type') or row.get('objectType') or ''} "
            f"{row.get('text') or row.get('summary') or ''} "
            f"{row.get('privacy_scope') or row.get('privacyScope') or ''} "
            f"{row.get('package_view') or row.get('packageView') or ''}"
        )
    text = _clean(" ".join(texts), 6000, True)
    uncertain_memory_count = sum(
        1
        for row in candidate_rows
        if row.get("requires_confirmation")
        or row.get("needs_confirmation")
        or row.get("uncertain")
        or row.get("status") == "needs_confirmation"
    )
    risky_memory_count = sum(
        1
        for row in candidate_rows
        if _slug(row.get("privacy_scope") or row.get("privacyScope") or "")
        in {"no_export", "private", "room_private", "sensitive"}
    )
    has_room_package = _has_any(text, [r"room package", r"handoff", r"export", r"bundle", r"zip", r"패키지", r"번들", r"공유", r"내보"])
    has_paper_direction = _has_any(text, [r"paper\s*[345]", r"논문", r"topic", r"토픽", r"novelty", r"아이디어", r"실험"])
    has_memory_structure = _has_any(text, [r"memory schema", r"memory structure", r"projection", r"room[-\s]?special", r"기억 구조", r"메모리 구조", r"schema", r"스키마"])
    has_global_scope_risk = _has_any(text, [r"앞으로", r"항상", r"다음부터", r"전체", r"every time", r"from now on", r"default"])
    has_privacy_risk = _has_any(text, [r"private", r"no[-_\s]?export", r"secret", r"pricing", r"credential", r"비공개", r"민감", r"공유하면 안"]) or risky_memory_count > 0
    has_temporary_risk = _has_any(text, [r"이번", r"임시", r"temporary", r"for this run", r"이번 실험", r"smoke"])
    has_explicit_ambiguity = _has_any(text, AMBIGUITY_PATTERNS) or uncertain_memory_count > 0
    has_resolved_negative_policy = _has_any(text, RESOLVED_NEGATIVE_POLICY_PATTERNS)
    has_schema_recording_request = has_paper_direction and has_memory_structure and _has_any(
        text, [r"기록", r"확정", r"잡아둘", r"중심.*기준", r"main direction", r"record", r"make.*canonical"]
    )
    has_scope_ambiguity = has_global_scope_risk and (
        has_explicit_ambiguity or _count_matches(text, [r"현재 room", r"room에만", r"전체", r"global", r"관련 ai rooms"]) >= 2
    )
    has_export_decision_request = has_room_package and has_privacy_risk and has_explicit_ambiguity and not has_resolved_negative_policy
    has_package_view_ambiguity = has_room_package and has_explicit_ambiguity and _count_matches(
        text, [r"operational", r"audit", r"public", r"handoff", r"export", r"package view"]
    ) >= 2
    has_permanence_ambiguity = has_explicit_ambiguity and (
        (has_temporary_risk and has_global_scope_risk)
        or _has_any(text, [r"이번.*앞으로", r"임시.*규칙", r"temporary.*persistent", r"persistent.*temporary"])
    )
    return {
        "domain": _slug(pkg.get("domain_label") or pkg.get("domainLabel") or pkg.get("domain") or "general_workbench"),
        "object_types": [_slug(v) for v in _as_list(memory.get("object_types") or memory.get("objectTypes"))][:32],
        "has_room_package": has_room_package,
        "has_paper_direction": has_paper_direction,
        "has_memory_structure": has_memory_structure,
        "has_global_scope_risk": has_global_scope_risk,
        "has_privacy_risk": has_privacy_risk,
        "has_temporary_risk": has_temporary_risk,
        "has_explicit_ambiguity": has_explicit_ambiguity,
        "has_resolved_negative_policy": has_resolved_negative_policy,
        "has_schema_recording_request": has_schema_recording_request,
        "has_scope_ambiguity": has_scope_ambiguity,
        "has_export_decision_request": has_export_decision_request,
        "has_package_view_ambiguity": has_package_view_ambiguity,
        "has_permanence_ambiguity": has_permanence_ambiguity,
        "uncertain_memory_count": uncertain_memory_count,
        "risky_memory_count": risky_memory_count,
    }


def _render_question(question_type: str, *, candidate: str = "room별 specialized memory structure") -> str:
    spec = QUESTION_SPECS[question_type]
    return str(spec["question"]).replace("{candidate}", candidate)


def plan_room_package_questions(
    *,
    recent_turns: list[dict[str, Any]] | None = None,
    candidate_memory_writes: list[dict[str, Any]] | None = None,
    room_package: dict[str, Any] | None = None,
    task_text: str = "",
    previous_questions: list[str | dict[str, Any]] | None = None,
    max_questions: int = 1,
    min_score: float = 0.85,
) -> dict[str, Any]:
    signals = classify_room_package_question_signals(
        recent_turns=recent_turns,
        candidate_memory_writes=candidate_memory_writes,
        room_package=room_package,
        task_text=task_text,
    )
    asked = {_slug(q.get("question_type") if isinstance(q, dict) else q) for q in _as_list(previous_questions)}
    candidates: list[dict[str, Any]] = []

    def add(
        question_type: str,
        score: float,
        reasons: list[str],
        candidate: str = "room별 specialized memory structure를 footprint로 학습/추천하는 방향",
        impact_level: str = "medium",
    ) -> None:
        if score < min_score or _slug(question_type) in asked:
            return
        spec = QUESTION_SPECS[question_type]
        candidates.append({
            "question_type": question_type,
            "score": score,
            "question": _render_question(question_type, candidate=candidate),
            "target_field": spec["target_field"],
            "options": list(spec["options"]),
            "reason_codes": reasons,
            "can_defer": True,
            "interaction_style": "inline_only_when_confirmation_needed",
            "requires_user_confirmation": True,
            "ambiguity_level": "explicit",
            "impact_level": impact_level,
        })

    if signals["has_export_decision_request"]:
        add("exportability_confirmation", 0.94, ["explicit_export_ambiguity", "sensitive_or_private_signal"], impact_level="high")
    if signals["has_schema_recording_request"]:
        add("schema_direction_confirmation", 0.90, ["explicit_schema_recording_request", "paper_direction_shift"], impact_level="high")
    if signals["has_scope_ambiguity"]:
        add("scope_confirmation", 0.88, ["explicit_scope_ambiguity", "future_default_language"], impact_level="high")
    if signals["has_package_view_ambiguity"] and not signals["has_export_decision_request"]:
        add("package_view_confirmation", 0.87, ["explicit_package_view_ambiguity", "handoff_or_export_signal"], impact_level="high")
    if signals["has_permanence_ambiguity"]:
        add("permanence_confirmation", 0.86, ["explicit_permanence_ambiguity"], impact_level="medium")

    candidates.sort(key=lambda row: row["score"], reverse=True)
    selected = candidates[: max(0, int(max_questions or 1))]
    return {
        "kind": "room_package_question_plan_v1",
        "should_ask": bool(selected),
        "signals": signals,
        "suppressed_reason": "" if selected else "no_explicit_high_impact_ambiguity",
        "policy": {
            "max_questions_per_turn": max(0, int(max_questions or 1)),
            "ask_only_when_confirmation_is_required": True,
            "suppress_passive_learning_questions": True,
            "user_can_ignore": True,
            "no_blocking_required": True,
            "default_min_score": min_score,
        },
        "questions": [
            {
                "question_id": f"rpq:{row['question_type']}:{idx + 1}",
                **row,
                "candidate_updates": [{
                    "object_type": "room_package_policy",
                    "field": row["target_field"],
                    "options": row["options"],
                    "status": "shadow_until_user_confirms",
                }],
            }
            for idx, row in enumerate(selected)
        ],
    }


def summarize_question_plans(plans: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    asked = 0
    suppressed = 0
    for plan in plans:
        plan_dict = _as_dict(plan)
        if not plan_dict.get("questions"):
            suppressed += 1
        for question in _as_list(plan_dict.get("questions")):
            qtype = str(_as_dict(question).get("question_type") or "unknown")
            by_type[qtype] = by_type.get(qtype, 0) + 1
            asked += 1
    return {
        "kind": "room_package_question_summary_v1",
        "plan_count": len(plans),
        "question_count": asked,
        "suppressed_plan_count": suppressed,
        "by_question_type": by_type,
        "low_friction_policy": "ask only when explicit high-impact ambiguity requires user confirmation; user can ignore",
    }
