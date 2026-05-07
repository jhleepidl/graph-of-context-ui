from __future__ import annotations
import re
from typing import Any


def _clean(value: Any = "", max_len: int = 12000) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:max_len]


def detect_language(value: Any = "") -> str:
    text = _clean(value, 8000)
    if not text:
        return "ko"
    hangul = len(re.findall(r"[가-힣]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if hangul >= 2 and hangul >= max(2, int(latin * 0.15)):
        return "ko"
    if latin >= 8 and hangul == 0:
        return "en"
    if latin >= 12 and latin > hangul * 3:
        return "en"
    return "ko"


def _hash(value: str) -> str:
    h = 0
    for ch in value:
        h = ((h << 5) - h + ord(ch)) & 0xFFFFFFFF
    return format(abs(h), "x")

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(한국어|한글).*?(간결|짧|요약).*?(답|응답|대답|작성)|간결.*?(한국어|한글).*?(답|응답|대답|작성)", re.I), "Respond concisely in Korean."),
    (re.compile(r"(영어).*?(간결|짧|요약).*?(답|응답|대답|작성)|간결.*?(영어).*?(답|응답|대답|작성)", re.I), "Respond concisely in English."),
    (re.compile(r"(계속|지속|반복|loop|루프).*?(점검|검토|개선)", re.I), "Run a bounded continuous review-and-improvement loop."),
    (re.compile(r"(매|각).*?(개선|iteration|반복).*?(review|리뷰|검토|검증)", re.I), "Review each implementation iteration."),
    (re.compile(r"(큰\s*변경|위험|리스크|삭제|배포|마이그레이션).*?(승인|허가)|승인.*?(큰\s*변경|위험|리스크|삭제|배포|마이그레이션)", re.I), "Require approval before large, risky, destructive, deployment, or migration changes."),
    (re.compile(r"(중단\s*조건|stop\s*condition|완성.*?중단|충분히.*?완성)", re.I), "Evaluate explicit stop conditions before ending the loop."),
    (re.compile(r"(국내\s*주식|한국\s*주식|주식투자|종목).*?(뉴스|가격|시세|추천|포트폴리오)", re.I), "Build or analyze a Korean stock investment product using news impact analysis, price lookup, recommendations, and portfolio management."),
    (re.compile(r"(최신\s*뉴스|뉴스).*?(영향|분석).*?(주식|종목|가격|시세)|뉴스.*?(주식|종목|가격|시세).*?(영향|분석|미치)", re.I), "Analyze recent news for its impact on stocks, affected assets, and prices."),
    (re.compile(r"(메모리|memory).*?(vector|벡터|인덱스|index|조회|저장)", re.I), "Use semantic/vector indexing for memory storage and retrieval projections."),
    (re.compile(r"(skill|스킬).*?(vector|벡터|인덱스|index|조회|검색|discovery)", re.I), "Use semantic/vector indexing for skill discovery and ranking."),
    (re.compile(r"(role|역할|agent|에이전트).*?(vector|벡터|인덱스|index|조회|검색|team|팀)", re.I), "Use structured role and team contracts with semantic indexing for discovery."),
    (re.compile(r"(원문|그대로).*?(보존|유지).*?(영어|canonical|projection|정규화)", re.I), "Preserve original user text and add a separate English canonical projection."),
]


def _terms(text: str) -> list[str]:
    rows: list[str] = []
    checks = [
        (r"(memory|메모리)", "memory"),
        (r"(skill|스킬)", "skill"),
        (r"(role|역할)", "role"),
        (r"(team|팀|agent|에이전트)", "agent team"),
        (r"(vector|벡터|embedding|임베딩|semantic|시맨틱)", "semantic/vector indexing"),
        (r"(review|리뷰|검토|검증)", "review"),
        (r"(loop|루프|반복|계속|지속)", "loop"),
        (r"(승인|approval|approve)", "approval gate"),
        (r"(주식|종목|stock|portfolio|포트폴리오|뉴스|news|가격|시세)", "financial news and stock analysis"),
    ]
    for pattern, label in checks:
        if re.search(pattern, text, re.I) and label not in rows:
            rows.append(label)
    return rows


def build_local_projection(text: Any = "", *, original_language: str = "", canonical_text_en: str = "", object_type: str = "memory") -> dict[str, Any]:
    original = _clean(text)
    lang = (original_language or detect_language(original)).lower()
    existing = _clean(canonical_text_en)
    if existing:
        return {"status": "ready", "canonical_text_en": existing, "canonical_projection_status": "ready", "projection_method": "provided", "projection_confidence": 1.0, "original_language": lang}
    if lang == "en":
        return {"status": "ready", "canonical_text_en": original, "canonical_projection_status": "ready", "projection_method": "source_is_english", "projection_confidence": 1.0, "original_language": "en"}
    hits: list[str] = []
    for pattern, phrase in _PATTERNS:
        if pattern.search(original):
            hits.append(phrase)
    terms = _terms(original)
    if hits:
        canonical = " ".join(dict.fromkeys(hits)) + ((" Key concepts: " + ", ".join(terms) + ".") if terms else "")
        return {"status": "ready", "canonical_text_en": canonical, "canonical_projection_status": "ready", "projection_method": "local_seed_glossary", "projection_confidence": min(0.88, 0.55 + len(hits) * 0.08 + len(terms) * 0.02), "original_language": lang}
    if len(terms) >= 2:
        return {"status": "ready", "canonical_text_en": f"User-provided {_clean(object_type, 80)} item about {', '.join(terms)}.", "canonical_projection_status": "ready", "projection_method": "local_keyword_summary", "projection_confidence": 0.5, "original_language": lang}
    return {"status": "pending_model_projection", "canonical_text_en": "", "canonical_projection_status": "pending_model_projection", "projection_method": "requires_model_or_human_projection", "projection_confidence": 0.0, "original_language": lang}


def build_projection_payload(row: dict[str, Any], *, object_type: str = "memory", summary: str = "") -> dict[str, Any]:
    original = _clean(row.get("source_original_text") or row.get("original_text") or row.get("text") or row.get("summary") or summary)
    lang = _clean(row.get("source_original_language") or row.get("original_language") or row.get("user_surface_locale") or detect_language(original), 20).lower()
    if lang not in {"en", "ko"}:
        lang = detect_language(original)
    projection = build_local_projection(original, original_language=lang, canonical_text_en=_clean(row.get("canonical_text_en") or row.get("canonical_summary_en") or ""), object_type=object_type)
    ref = _clean(row.get("source_id") or row.get("sourceId") or row.get("proposal_id") or row.get("id") or summary, 500)
    return {
        "source_original_text": original,
        "source_original_language": lang,
        "display_text": _clean(row.get("display_text") or original or summary),
        "canonical_language": "en",
        "canonical_text_en": projection.get("canonical_text_en", ""),
        "canonical_projection_status": projection.get("canonical_projection_status", "pending_model_projection"),
        "canonical_projection_id": row.get("canonical_projection_id") or f"projection_{_clean(object_type, 80)}_{_hash(ref + original)}",
        "projection_method": projection.get("projection_method", "requires_model_or_human_projection"),
        "projection_confidence": projection.get("projection_confidence", 0.0),
        "user_surface_locale": lang,
    }
