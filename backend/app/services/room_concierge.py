"""Pure Room Concierge classifier for GoC-side diagnostics.

The runtime implementation lives in ddalggak. This mirror is intentionally
small and deterministic so GoC dashboards/tests can reason about route
selection without calling model providers.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


SEARCH_NEEDLES = ["검색", "찾아봐", "찾아보고", "실제로", "최신", "현재", "공식", "메뉴판", "네이버", "인스타", "링크", "웹", "인터넷", "search", "browse", "lookup", "latest", "current", "official", "website"]
WORKBENCH_NEEDLES = ["패치", "수정해", "구현", "테스트", "파일", "zip", "번들", "첨부", "소스", "코드", "리팩터", "배포", "commit", "diff", "repo", "workspace"]
TEAM_NEEDLES = ["/team", "/loop", "팀", "여러 agent", "여러 에이전트", "multi-agent", "multi agent", "검토", "리뷰", "토론", "비판", "회의"]
HIGH_RISK_NEEDLES = ["법률", "의학", "진단", "투자", "세금", "계약서", "개인정보", "비밀번호", "credential", "secret", "법적", "의료", "처방", "금융"]
SIMPLE_NEEDLES = ["추천", "설명", "요약", "정리", "차이", "뭐", "어떻게", "왜", "아이디어", "문장", "번역", "맛집", "메뉴", "recommend", "explain", "summarize", "what", "how", "why", "translate"]


def _contains_any(text: str, needles: List[str]) -> bool:
    lower = (text or "").lower()
    return any(str(n).lower() in lower for n in needles)


def _tokenish(text: str) -> int:
    compact = (text or "").strip()
    if not compact:
        return 0
    return max(len(compact.split()), (len(compact) + 11) // 12)


@dataclass
class RoomConciergeDecision:
    kind: str
    route: str
    depth: str
    should_bypass_workbench: bool
    should_show_plan_preview: bool
    signals: List[str]
    blockers: List[str]
    reasons: List[str]
    metrics: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def classify_room_concierge_route(
    text: str,
    *,
    command: str = "/ask",
    has_attachment: bool = False,
    pending_approval: bool = False,
    busy: bool = False,
    fast_path_enabled: bool = True,
    max_chars: int = 420,
    max_tokenish_units: int = 55,
) -> Dict[str, Any]:
    message = (text or "").strip()
    signals: List[str] = []
    blockers: List[str] = []
    reasons: List[str] = []
    tokenish = _tokenish(message)

    if not message:
        blockers.append("empty_message")
    if (command or "/ask").strip().lower() != "/ask":
        blockers.append("not_ask_command")
    if has_attachment:
        blockers.append("has_attachment")
    if pending_approval:
        blockers.append("pending_approval")
    if busy:
        blockers.append("busy_chat")
    if not fast_path_enabled:
        blockers.append("fast_path_disabled")
    if len(message) > max_chars:
        blockers.append("message_too_long")
    if tokenish > max_tokenish_units:
        blockers.append("message_too_complex")

    if _contains_any(message, HIGH_RISK_NEEDLES):
        signals.append("high_risk_domain")
    if _contains_any(message, WORKBENCH_NEEDLES):
        signals.append("workbench_intent")
    if _contains_any(message, TEAM_NEEDLES):
        signals.append("team_or_review_intent")
    if _contains_any(message, SEARCH_NEEDLES):
        signals.append("search_or_freshness_intent")
    if _contains_any(message, SIMPLE_NEEDLES):
        signals.append("simple_qa_intent")

    if "team_or_review_intent" in signals:
        blockers.append("needs_team_or_review")
    if "workbench_intent" in signals:
        blockers.append("needs_workspace_or_artifact")
    if "high_risk_domain" in signals:
        blockers.append("needs_standard_safety_context")

    unique_blockers = list(dict.fromkeys(blockers))
    unique_signals = list(dict.fromkeys(signals))

    route = "standard_workbench"
    depth = "workbench"
    bypass = False
    show_plan = True
    if not unique_blockers and "search_or_freshness_intent" in unique_signals:
        route = "concierge_search_answer"
        depth = "single_agent_search"
        reasons.append("freshness_or_search_requested")
    elif not unique_blockers:
        route = "concierge_direct_answer"
        depth = "direct_answer"
        bypass = True
        show_plan = False
        reasons.append("short_low_risk_ask")
    elif "team_or_review_intent" in unique_signals:
        route = "team_orchestration"
        depth = "team"
        reasons.append("team_or_review_requested")
    elif "search_or_freshness_intent" in unique_signals:
        route = "concierge_search_answer"
        depth = "single_agent_search"
        reasons.append("freshness_or_search_requested_with_blockers")
    else:
        reasons.append("standard_pipeline_required")

    return RoomConciergeDecision(
        kind="room_concierge_route_v1",
        route=route,
        depth=depth,
        should_bypass_workbench=bypass,
        should_show_plan_preview=show_plan,
        signals=unique_signals,
        blockers=unique_blockers,
        reasons=list(dict.fromkeys(reasons)),
        metrics={"char_count": len(message), "tokenish_units": tokenish},
    ).to_dict()


def extract_room_concierge_features(decision: Dict[str, Any], *, room_footprint: Dict[str, Any] | None = None) -> Dict[str, float]:
    """Feature vector used by the learned/local Room Concierge scorer.

    GoC keeps this mirror for diagnostics only. ddalggak owns runtime routing.
    """
    d = decision or {}
    footprint = room_footprint or {}
    signals = set(d.get("signals") or [])
    blockers = set(d.get("blockers") or [])
    metrics = d.get("metrics") or {}
    task_distribution = footprint.get("task_distribution") or {}
    char_count = float(metrics.get("char_count") or 0)
    tokenish = float(metrics.get("tokenish_units") or 0)

    def clamp(value: Any) -> float:
        try:
            n = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, n))

    return {
        "bias": 1.0,
        "char_norm": max(0.0, min(1.0, char_count / 600.0)),
        "tokenish_norm": max(0.0, min(1.0, tokenish / 80.0)),
        "signal_simple_qa": 1.0 if "simple_qa_intent" in signals else 0.0,
        "signal_search": 1.0 if "search_or_freshness_intent" in signals else 0.0,
        "signal_workbench": 1.0 if "workbench_intent" in signals else 0.0,
        "signal_team": 1.0 if "team_or_review_intent" in signals else 0.0,
        "signal_high_risk": 1.0 if "high_risk_domain" in signals else 0.0,
        "has_attachment": 1.0 if "has_attachment" in blockers else 0.0,
        "pending_approval": 1.0 if "pending_approval" in blockers else 0.0,
        "busy_chat": 1.0 if "busy_chat" in blockers else 0.0,
        "room_memory_pressure": clamp(footprint.get("memory_pressure")),
        "room_governance_pressure": clamp(footprint.get("governance_pressure")),
        "room_export_boundary_risk": clamp(footprint.get("export_boundary_risk")),
        "room_handoff_need": clamp(footprint.get("handoff_need")),
        "room_search_need": clamp(footprint.get("external_search_need")),
        "room_team_need": clamp(footprint.get("team_need")),
        "task_coding": clamp(task_distribution.get("coding") or task_distribution.get("code")),
        "task_research": clamp(task_distribution.get("research")),
        "task_strategy": clamp(task_distribution.get("strategy") or task_distribution.get("product")),
        "task_casual": clamp(task_distribution.get("casual") or task_distribution.get("qa")),
    }


def score_linear_room_concierge_model(
    decision: Dict[str, Any],
    model: Dict[str, Any],
    *,
    room_footprint: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Score a local linear concierge model for GoC diagnostics."""
    features = extract_room_concierge_features(decision, room_footprint=room_footprint)
    weights_by_route = model.get("route_weights") or {}
    if not weights_by_route:
        return {"ok": False, "reason": "no_route_weights"}
    scores: Dict[str, float] = {}
    for route, weights in weights_by_route.items():
        total = float((weights or {}).get("bias") or 0.0)
        for key, value in (weights or {}).items():
            if key == "bias":
                continue
            total += float(value or 0.0) * features.get(key, 0.0)
        scores[route] = total
    if not scores:
        return {"ok": False, "reason": "no_scores"}
    route = max(scores, key=scores.get)
    return {
        "ok": True,
        "route": route,
        "raw_scores": scores,
        "features": features,
        "model": {"version": model.get("version") or "local_unversioned"},
    }
