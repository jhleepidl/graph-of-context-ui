from __future__ import annotations

from typing import Any


def _clean(value: Any) -> str:
    return str(value or '').strip()


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean(v) for v in value if _clean(v)]
    if isinstance(value, str):
        return [_clean(v) for v in value.split(',') if _clean(v)]
    return []


def summarize_knowledge_route_event(event: dict[str, Any]) -> dict[str, Any]:
    row = event if isinstance(event, dict) else {}
    surfaces = _list(row.get('knowledge_surfaces') or row.get('knowledgeSurfaces'))
    route = _clean(row.get('route')) or 'unknown'
    blockers = _list(row.get('blockers'))
    signals = _list(row.get('signals'))
    provider = _clean((row.get('model_policy') or row.get('modelPolicy') or {}).get('provider') if isinstance(row.get('model_policy') or row.get('modelPolicy'), dict) else '')
    return {
        'schema_version': 'goc.knowledge_route_event/v1',
        'route': route,
        'depth': _clean(row.get('depth')) or None,
        'knowledge_surfaces': surfaces or ['standard_context'],
        'signals': signals,
        'blockers': blockers,
        'provider': provider or None,
        'executor': _clean(row.get('executor')) or None,
        'outcome': _clean(row.get('outcome')) or 'unknown',
        'query_excerpt': _clean(row.get('query_excerpt') or row.get('queryExcerpt'))[:300] or None,
        'needs_attention': bool({'artifact_reference_intent', 'search_or_freshness_intent', 'high_risk_domain'} & set(signals)) or bool(blockers),
    }


def summarize_knowledge_route_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [summarize_knowledge_route_event(e) for e in (events or [])]
    by_surface: dict[str, int] = {}
    by_route: dict[str, int] = {}
    attention = 0
    by_outcome: dict[str, int] = {}
    for row in rows:
        by_route[row['route']] = by_route.get(row['route'], 0) + 1
        if row.get('needs_attention'):
            attention += 1
        outcome = row.get('outcome') or 'unknown'
        by_outcome[outcome] = by_outcome.get(outcome, 0) + 1
        for surface in row.get('knowledge_surfaces') or []:
            by_surface[surface] = by_surface.get(surface, 0) + 1
    return {
        'schema_version': 'goc.knowledge_route_summary/v1',
        'event_count': len(rows),
        'needs_attention_count': attention,
        'by_route': by_route,
        'by_surface': by_surface,
        'by_outcome': by_outcome,
        'items': rows[-20:],
    }
