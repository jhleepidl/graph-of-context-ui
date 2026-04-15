from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable

def jload(raw: str | None, default: Any) -> Any:
    try:
        return json.loads(raw or "")
    except Exception:
        return default

def node_payload(node: Any | None) -> dict[str, Any]:
    if not node:
        return {}
    payload = jload(getattr(node, "payload_json", "{}"), {})
    if isinstance(payload, dict):
        return payload
    return {}

def created_sort_key(node: Any) -> tuple[str, str]:
    created_at = getattr(node, "created_at", None)
    if isinstance(created_at, datetime):
        return created_at.isoformat(), str(getattr(node, "id", ""))
    return str(created_at or ""), str(getattr(node, "id", ""))

def normalize_status(raw: Any) -> str:
    clean = str(raw or "").strip().lower()
    if not clean:
        return "unknown"
    if clean in {"queued", "pending", "waiting"}:
        return "queued"
    if clean in {"running", "in_progress", "active"}:
        return "running"
    if clean in {"done", "completed", "success", "ok"}:
        return "done"
    if clean in {"error", "failed", "failure", "blocked"}:
        return "error"
    return clean

def has_non_empty_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True

def clean_list_of_text(value: Any, *, limit: int = 16) -> list[str]:
    if isinstance(value, str):
        clean = value.strip()
        return [clean] if clean else []
    if not isinstance(value, (list, tuple, set)):
        return []
    out: list[str] = []
    for item in value:
        clean = str(item or "").strip()
        if not clean:
            continue
        out.append(clean)
        if len(out) >= limit:
            break
    return out

def clean_text(value: Any) -> str | None:
    clean = str(value or "").strip()
    return clean or None

def coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        clean = value.strip().lower()
        if clean in {"1", "true", "yes", "y", "on"}:
            return True
        if clean in {"0", "false", "no", "n", "off"}:
            return False
    return None

def coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        clean = value.strip()
        if clean and clean.lstrip("-").isdigit():
            return int(clean)
    return None

def preserve_structured_value(value: Any) -> Any:
    raw = parse_jsonish(value)
    if raw is None:
        return None
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, list):
        return list(raw)
    if isinstance(raw, tuple):
        return list(raw)
    if isinstance(raw, set):
        return list(raw)
    if isinstance(raw, str):
        return clean_text(raw)
    return raw

def parse_jsonish(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return value
    clean = value.strip()
    if not clean:
        return None
    if clean.startswith("{") or clean.startswith("["):
        parsed = jload(clean, None)
        if parsed is not None:
            return parsed
    return value

def first_present(mapping: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) is not None:
            return mapping.get(key)
    return None

def normalize_record_list(
    value: Any,
    *,
    id_field: str = "id",
    hint_keys: Iterable[str] | None = None,
    value_field: str = "value",
    max_items: int = 32,
) -> list[dict[str, Any]]:
    raw = parse_jsonish(value)
    out: list[dict[str, Any]] = []
    hints = tuple(hint_keys or ())

    if isinstance(raw, list):
        for item in raw:
            if len(out) >= max_items:
                break
            if isinstance(item, dict):
                out.append(dict(item))
                continue
            clean = clean_text(item)
            if clean:
                out.append({id_field: clean})
        return out

    if isinstance(raw, tuple):
        return normalize_record_list(list(raw), id_field=id_field, hint_keys=hints, value_field=value_field, max_items=max_items)

    if isinstance(raw, dict):
        if not hints or any(has_non_empty_value(raw.get(key)) for key in hints):
            return [dict(raw)]

        for map_key, map_value in raw.items():
            if len(out) >= max_items:
                break
            if isinstance(map_value, dict):
                entry = dict(map_value)
                clean_key = clean_text(map_key)
                if clean_key and not has_non_empty_value(entry.get(id_field)):
                    entry[id_field] = clean_key
                out.append(entry)
                continue

            clean_key = clean_text(map_key)
            clean_value = clean_text(map_value)
            if clean_key and clean_value:
                out.append({id_field: clean_key, value_field: clean_value})
        return out

    clean = clean_text(raw)
    if clean:
        return [{id_field: clean}]
    return out

def normalize_mapping(value: Any) -> dict[str, Any] | None:
    raw = parse_jsonish(value)
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        clean = raw.strip()
        if clean:
            return {"summary": clean}
    return None

