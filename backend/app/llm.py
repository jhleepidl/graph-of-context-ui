from __future__ import annotations
import hashlib
from typing import List, Optional
import numpy as np

from app.config import get_env

OPENAI_API_KEY = get_env("OPENAI_API_KEY")
OPENAI_MODEL = get_env("OPENAI_MODEL", "gpt-5") or "gpt-5"
OPENAI_EMBED_MODEL = get_env("OPENAI_EMBED_MODEL", "text-embedding-3-small") or "text-embedding-3-small"
GOC_EMBED_DIM = int(get_env("GOC_EMBED_DIM", "1536") or "1536")

def llm_available() -> bool:
    return bool(OPENAI_API_KEY)

def call_openai(instructions: str, user_input: str, model: Optional[str] = None) -> str:
    if not llm_available():
        return (
            "[LLM 미연결 상태]\n"
            "OPENAI_API_KEY가 설정되지 않아 더미 응답을 반환합니다.\n\n"
            + user_input[:800]
        )
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    model_name = model or OPENAI_MODEL
    req = {
        "model": model_name,
        "instructions": instructions,
        "input": user_input,
        "truncation": "disabled",
        "temperature": 0.2,
    }
    try:
        resp = client.responses.create(**req)
    except Exception as e:
        msg = str(e)
        if "Unsupported parameter: 'temperature'" not in msg:
            raise
        req.pop("temperature", None)
        resp = client.responses.create(**req)
    return resp.output_text

def _hash_embed(text: str, dim: Optional[int] = None) -> List[float]:
    if dim is None:
        dim = GOC_EMBED_DIM
    vec = np.zeros(dim, dtype=np.float32)
    for token in text.lower().split():
        h = hashlib.md5(token.encode("utf-8")).digest()
        idx = int.from_bytes(h[:4], "little") % dim
        vec[idx] += 1.0
    norm = np.linalg.norm(vec) + 1e-9
    vec = vec / norm
    return vec.astype(float).tolist()

def embed_text(text: str) -> List[float]:
    text = (text or "").strip()
    if not text:
        return []
    if not llm_available():
        return _hash_embed(text, dim=GOC_EMBED_DIM)

    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    kwargs = {}
    if GOC_EMBED_DIM:
        kwargs["dimensions"] = GOC_EMBED_DIM

    emb = client.embeddings.create(model=OPENAI_EMBED_MODEL, input=text, **kwargs)
    return emb.data[0].embedding
