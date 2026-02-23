from __future__ import annotations

import math
from typing import Optional

from fastapi import APIRouter

from app.schemas import TokenEstimateRequest

router = APIRouter(prefix="/api/tokens", tags=["tokens"])

try:
    import tiktoken
except Exception:
    tiktoken = None


def has_hangul(text: str) -> bool:
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            return True
    return False


def count_with_tiktoken(text: str, model: Optional[str]) -> int:
    if tiktoken is None:
        raise RuntimeError("tiktoken unavailable")
    try:
        if model:
            enc = tiktoken.encoding_for_model(model)
        else:
            enc = tiktoken.get_encoding("cl100k_base")
    except Exception:
        enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def count_with_heuristic(text: str) -> int:
    if not text:
        return 0
    divisor = 3.0 if has_hangul(text) else 4.0
    return int(math.ceil(len(text) / divisor))


@router.post("/estimate")
def estimate_tokens(body: TokenEstimateRequest):
    text = body.text or ""
    try:
        tokens = count_with_tiktoken(text, body.model)
        return {"tokens": int(tokens), "method": "tiktoken"}
    except Exception:
        return {"tokens": count_with_heuristic(text), "method": "heuristic"}
