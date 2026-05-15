from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.models import SemanticBoardCard, SemanticBoardLink, SemanticBoardEvent, Thread, utcnow


def _clean(value: Any = '', max_len: int = 4000) -> str:
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    return text[:max_len]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def _loads(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or '')
    except Exception:
        return default


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = str(value or '').strip()
    if raw:
        try:
            parsed = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return utcnow()


def _float(value: Any, default: float = 0.0) -> float:
    try:
        n = float(value)
        if n != n:
            return default
        return n
    except Exception:
        return default


def _card_id(row: dict[str, Any]) -> str:
    return _clean(row.get('id') or row.get('card_id') or row.get('cardId') or row.get('skill_id') or row.get('rule_id') or row.get('title'), 200)


def _link_id(row: dict[str, Any]) -> str:
    return _clean(row.get('id') or row.get('link_id') or row.get('linkId') or f"{row.get('from') or row.get('from_card_id')}:{row.get('type') or row.get('link_type')}:{row.get('to') or row.get('to_card_id')}", 240)


def _normalize_card(raw: dict[str, Any], *, thread: Thread, run_id: str | None = None, source: str = 'ddalggak') -> dict[str, Any] | None:
    row = _as_dict(raw)
    card_id = _card_id(row)
    if not card_id:
        return None
    card_type = _clean(row.get('type') or row.get('kind') or row.get('card_type') or row.get('cardType') or 'memory_card', 80)
    content = _as_dict(row.get('content'))
    performance = _as_dict(row.get('performance'))
    reuse_score = _float(row.get('reuse_score') or row.get('reuseScore') or performance.get('reuse_score') or performance.get('reuseScore'), 0.0)
    confidence = _float(row.get('confidence'), 0.0)
    return {
        'thread_id': thread.id,
        'run_id': run_id,
        'card_id': card_id,
        'card_type': card_type,
        'title': _clean(row.get('title') or row.get('name') or card_id, 300),
        'status': _clean(row.get('status') or 'candidate', 80),
        'source': _clean(row.get('source') or source, 100),
        'source_ref': _clean(row.get('source_ref') or row.get('sourceRef') or '', 1000),
        'confidence': confidence,
        'reuse_score': reuse_score,
        'tags_json': _dumps(_as_list(row.get('tags'))),
        'content_json': _dumps(content),
        'scope_json': _dumps(_as_dict(row.get('scope'))),
        'performance_json': _dumps(performance),
        'card_json': _dumps(row),
        'created_at': _parse_dt(row.get('created_at') or row.get('createdAt')),
        'updated_at': _parse_dt(row.get('updated_at') or row.get('updatedAt')),
    }


def _normalize_link(raw: dict[str, Any], *, thread: Thread, run_id: str | None = None) -> dict[str, Any] | None:
    row = _as_dict(raw)
    from_id = _clean(row.get('from') or row.get('from_id') or row.get('fromId') or row.get('from_card_id') or row.get('fromCardId'), 200)
    to_id = _clean(row.get('to') or row.get('to_id') or row.get('toId') or row.get('to_card_id') or row.get('toCardId'), 200)
    if not from_id or not to_id:
        return None
    link_id = _link_id(row)
    return {
        'thread_id': thread.id,
        'run_id': run_id,
        'link_id': link_id,
        'from_card_id': from_id,
        'to_card_id': to_id,
        'link_type': _clean(row.get('type') or row.get('kind') or row.get('link_type') or row.get('linkType') or 'related_to', 80),
        'status': _clean(row.get('status') or 'active', 80),
        'weight': _float(row.get('weight'), 0.0),
        'reason': _clean(row.get('reason') or row.get('summary') or '', 1000),
        'link_json': _dumps(row),
        'created_at': _parse_dt(row.get('created_at') or row.get('createdAt')),
        'updated_at': _parse_dt(row.get('updated_at') or row.get('updatedAt')),
    }


def _card_to_dict(card: SemanticBoardCard) -> dict[str, Any]:
    return {
        'id': card.card_id,
        'card_id': card.card_id,
        'type': card.card_type,
        'title': card.title,
        'status': card.status,
        'source': card.source,
        'source_ref': card.source_ref,
        'confidence': card.confidence,
        'reuse_score': card.reuse_score,
        'tags': _loads(card.tags_json, []),
        'content': _loads(card.content_json, {}),
        'scope': _loads(card.scope_json, {}),
        'performance': _loads(card.performance_json, {}),
        'raw': _loads(card.card_json, {}),
        'created_at': card.created_at.isoformat() if isinstance(card.created_at, datetime) else str(card.created_at),
        'updated_at': card.updated_at.isoformat() if isinstance(card.updated_at, datetime) else str(card.updated_at),
    }


def _link_to_dict(link: SemanticBoardLink) -> dict[str, Any]:
    return {
        'id': link.link_id,
        'link_id': link.link_id,
        'from': link.from_card_id,
        'to': link.to_card_id,
        'type': link.link_type,
        'status': link.status,
        'weight': link.weight,
        'reason': link.reason,
        'raw': _loads(link.link_json, {}),
        'created_at': link.created_at.isoformat() if isinstance(link.created_at, datetime) else str(link.created_at),
        'updated_at': link.updated_at.isoformat() if isinstance(link.updated_at, datetime) else str(link.updated_at),
    }


def summarize_semantic_board(cards: list[SemanticBoardCard], links: list[SemanticBoardLink]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for card in cards:
        by_type[card.card_type] = by_type.get(card.card_type, 0) + 1
        by_status[card.status] = by_status.get(card.status, 0) + 1
    top = sorted(cards, key=lambda row: float(row.reuse_score or 0.0), reverse=True)[:8]
    return {
        'kind': 'semantic_board_summary_v1',
        'card_count': len(cards),
        'link_count': len(links),
        'by_type': by_type,
        'by_status': by_status,
        'top_reusable': [
            {'id': row.card_id, 'title': row.title, 'type': row.card_type, 'reuse_score': row.reuse_score}
            for row in top if row.reuse_score
        ],
    }


def list_semantic_board(session: Session, thread: Thread, *, limit: int = 200, card_type: str | None = None) -> dict[str, Any]:
    stmt = select(SemanticBoardCard).where(SemanticBoardCard.thread_id == thread.id)
    if card_type:
        stmt = stmt.where(SemanticBoardCard.card_type == card_type)
    cards = list(session.exec(stmt.order_by(SemanticBoardCard.updated_at.desc()).limit(max(1, min(int(limit or 200), 1000)))))
    links = list(session.exec(select(SemanticBoardLink).where(SemanticBoardLink.thread_id == thread.id).order_by(SemanticBoardLink.updated_at.desc()).limit(1000)))
    return {'ok': True, 'thread_id': thread.id, 'summary': summarize_semantic_board(cards, links), 'cards': [_card_to_dict(row) for row in cards], 'links': [_link_to_dict(row) for row in links]}


def upsert_semantic_board(session: Session, thread: Thread, payload: dict[str, Any], *, source: str = 'ddalggak') -> dict[str, Any]:
    body = _as_dict(payload)
    run_id = _clean(body.get('run_id') or body.get('runId') or '', 160) or None
    raw_cards = _as_list(body.get('cards')) or _as_list(body.get('memory_cards')) + _as_list(body.get('skill_cards')) + _as_list(body.get('rule_cards'))
    raw_links = _as_list(body.get('links'))
    if not raw_cards and (body.get('id') or body.get('card_id') or body.get('title')):
        raw_cards = [body]

    saved_cards: list[SemanticBoardCard] = []
    for raw in raw_cards:
        normalized = _normalize_card(_as_dict(raw), thread=thread, run_id=run_id, source=source)
        if not normalized:
            continue
        existing = session.exec(select(SemanticBoardCard).where(SemanticBoardCard.thread_id == thread.id).where(SemanticBoardCard.card_id == normalized['card_id'])).first()
        if existing:
            for key, value in normalized.items():
                setattr(existing, key, value)
            card = existing
        else:
            card = SemanticBoardCard(**normalized)
        session.add(card)
        saved_cards.append(card)

    saved_links: list[SemanticBoardLink] = []
    for raw in raw_links:
        normalized = _normalize_link(_as_dict(raw), thread=thread, run_id=run_id)
        if not normalized:
            continue
        existing = session.exec(select(SemanticBoardLink).where(SemanticBoardLink.thread_id == thread.id).where(SemanticBoardLink.link_id == normalized['link_id'])).first()
        if existing:
            for key, value in normalized.items():
                setattr(existing, key, value)
            link = existing
        else:
            link = SemanticBoardLink(**normalized)
        session.add(link)
        saved_links.append(link)

    if body.get('events'):
        for raw in _as_list(body.get('events')):
            event = SemanticBoardEvent(
                thread_id=thread.id,
                run_id=run_id,
                event_id=_clean(_as_dict(raw).get('event_id') or _as_dict(raw).get('id'), 200),
                event_type=_clean(_as_dict(raw).get('type') or _as_dict(raw).get('event') or 'event', 100),
                source=source,
                payload_json=_dumps(raw),
                created_at=_parse_dt(_as_dict(raw).get('created_at') or _as_dict(raw).get('createdAt')),
            )
            session.add(event)

    session.commit()
    cards = list(session.exec(select(SemanticBoardCard).where(SemanticBoardCard.thread_id == thread.id).order_by(SemanticBoardCard.updated_at.desc()).limit(500)))
    links = list(session.exec(select(SemanticBoardLink).where(SemanticBoardLink.thread_id == thread.id).order_by(SemanticBoardLink.updated_at.desc()).limit(1000)))
    return {'ok': True, 'created_or_updated_cards': len(saved_cards), 'created_or_updated_links': len(saved_links), 'summary': summarize_semantic_board(cards, links), 'cards': [_card_to_dict(row) for row in saved_cards], 'links': [_link_to_dict(row) for row in saved_links]}
