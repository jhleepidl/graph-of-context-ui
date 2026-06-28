from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

FORBIDDEN_KEYS = {
    'text', 'raw_text', 'rawtext', 'body', 'content', 'message', 'prompt', 'answer', 'response',
    'transcript', 'attachment_bytes', 'raw_prompt', 'raw_response', 'input', 'output',
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _hash(value: str) -> str:
    return hashlib.sha256(str(value or '').encode('utf-8')).hexdigest()[:24]


def _num(value: Any, default: float = 0) -> float:
    try:
        n = float(value)
        if n != n:
            return default
        return n
    except Exception:
        return default


def _strip_raw(value: Any) -> Any:
    if isinstance(value, list):
        return [_strip_raw(item) for item in value]
    if not isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    for key, raw in value.items():
        lower = str(key or '').lower()
        if lower in FORBIDDEN_KEYS:
            continue
        if 'transcript' in lower or 'attachment_bytes' in lower:
            continue
        out[key] = _strip_raw(raw)
    return out


def normalize_usage(*, provider: str = '', api: str = '', usage: dict[str, Any] | None = None, prompt_chars: int = 0, output_chars: int = 0) -> dict[str, Any]:
    usage = _as_dict(usage)
    provider_id = str(provider or '').strip().lower()
    api_id = str(api or '').strip().lower()
    if provider_id == 'openai' and (api_id in {'responses', 'chat_completions'} or 'input_tokens' in usage or 'prompt_tokens' in usage):
        input_details = _as_dict(usage.get('input_tokens_details') or usage.get('prompt_tokens_details') or usage.get('input_details'))
        output_details = _as_dict(usage.get('output_tokens_details') or usage.get('completion_tokens_details') or usage.get('output_details'))
        input_tokens = int(_num(usage.get('input_tokens', usage.get('prompt_tokens', 0))))
        output_tokens = int(_num(usage.get('output_tokens', usage.get('completion_tokens', 0))))
        total_tokens = int(_num(usage.get('total_tokens'), input_tokens + output_tokens))
        return {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': total_tokens,
            'cached_input_tokens': int(_num(input_details.get('cached_tokens', usage.get('cached_tokens', 0)))),
            'reasoning_tokens': int(_num(output_details.get('reasoning_tokens', usage.get('reasoning_tokens', 0)))),
            'token_source': 'actual_api_response',
        }
    estimated_input = int((_num(prompt_chars) + 3) // 4)
    estimated_output = int((_num(output_chars) + 3) // 4)
    return {
        'input_tokens': estimated_input,
        'output_tokens': estimated_output,
        'total_tokens': estimated_input + estimated_output,
        'cached_input_tokens': 0,
        'reasoning_tokens': 0,
        'token_source': 'estimated_from_chars',
    }


def estimate_cost_usd(tokens: dict[str, Any], pricing: dict[str, Any] | None = None) -> float | None:
    pricing = _as_dict(pricing)
    input_per_million = _num(pricing.get('input_per_million_usd'))
    cached_per_million = _num(pricing.get('cached_input_per_million_usd'), input_per_million)
    output_per_million = _num(pricing.get('output_per_million_usd'))
    if input_per_million == 0 and cached_per_million == 0 and output_per_million == 0:
        return None
    cached = _num(tokens.get('cached_input_tokens'))
    input_tokens = max(0, _num(tokens.get('input_tokens')) - cached)
    output_tokens = _num(tokens.get('output_tokens'))
    return round((input_tokens * input_per_million + cached * cached_per_million + output_tokens * output_per_million) / 1_000_000, 8)


def build_runtime_telemetry_event(
    *,
    thread_id: str = '',
    room_id: str = '',
    run_id: str = '',
    turn_id: str = '',
    provider: str = '',
    api: str = '',
    model: str = '',
    usage: dict[str, Any] | None = None,
    prompt_chars: int = 0,
    output_chars: int = 0,
    latency_ms: int = 0,
    route: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    room_memory_trials: dict[str, Any] | None = None,
    outcome: dict[str, Any] | None = None,
    pricing: dict[str, Any] | None = None,
    source: str = 'goc_backend',
    trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    route_row = _strip_raw(_as_dict(route))
    tokens = normalize_usage(provider=provider, api=api, usage=usage, prompt_chars=prompt_chars, output_chars=output_chars)
    cost = estimate_cost_usd(tokens, pricing)
    event: dict[str, Any] = {
        'kind': 'runtime_telemetry_event_v1',
        'ts': datetime.now(timezone.utc).isoformat(),
        'source': source,
        'ids': {
            'run_id': str(run_id or '')[:160],
            'thread_id_hash': _hash(thread_id or room_id or 'thread'),
            'room_id_hash': _hash(room_id or thread_id or 'room'),
            'turn_id': str(turn_id or '')[:160],
        },
        'provider': str(provider or '').strip().lower()[:80],
        'api': str(api or '').strip().lower()[:80],
        'model': str(model or '')[:160],
        'routing': {
            'depth': route_row.get('depth') or route_row.get('work_mode') or '',
            'execution_shape': route_row.get('execution_shape') or '',
            'reason_codes': _as_list(route_row.get('reason_codes'))[:20],
        },
        'tokens': tokens,
        'latency': {
            'duration_ms': int(_num(latency_ms)),
        },
        'context': _strip_raw(context or {}),
        'room_memory_trials': _strip_raw(room_memory_trials or {}),
        'outcome': _strip_raw(outcome or {}),
        'trace': _strip_raw(trace or {}),
        'cost': None if cost is None else {
            'estimated_usd': cost,
            'pricing_snapshot': str(_as_dict(pricing).get('snapshot') or '')[:80],
            'source': 'usage_times_pricing_snapshot',
        },
        'privacy': {
            'raw_prompt_logged': False,
            'raw_response_logged': False,
            'includes_raw_text': False,
            'ids_are_hashed': True,
        },
    }
    return event


def validate_runtime_telemetry_event(event: dict[str, Any]) -> tuple[bool, str]:
    encoded = json.dumps(event, ensure_ascii=False)
    for key in FORBIDDEN_KEYS:
        if f'"{key}"' in encoded:
            return False, f'forbidden_key:{key}'
    privacy = _as_dict(event.get('privacy'))
    if privacy.get('raw_prompt_logged') is True or privacy.get('raw_response_logged') is True or privacy.get('includes_raw_text') is True:
        return False, 'raw_text_marked_present'
    return True, ''


def summarize_runtime_telemetry(events: list[dict[str, Any]]) -> dict[str, Any]:
    clean_events: list[dict[str, Any]] = []
    for event in events:
        ok, _ = validate_runtime_telemetry_event(event)
        if ok:
            clean_events.append(event)
    total_tokens = sum(int(_num(_as_dict(row.get('tokens')).get('total_tokens'))) for row in clean_events)
    actual_events = sum(1 for row in clean_events if _as_dict(row.get('tokens')).get('token_source') == 'actual_api_response')
    total_latency = sum(int(_num(_as_dict(row.get('latency')).get('duration_ms'))) for row in clean_events)
    total_cost = sum(_num(_as_dict(row.get('cost')).get('estimated_usd')) for row in clean_events if isinstance(row.get('cost'), dict))
    return {
        'kind': 'runtime_telemetry_summary_v1',
        'event_count': len(clean_events),
        'actual_usage_event_count': actual_events,
        'total_tokens': total_tokens,
        'total_latency_ms': total_latency,
        'estimated_cost_usd': round(total_cost, 8),
    }
