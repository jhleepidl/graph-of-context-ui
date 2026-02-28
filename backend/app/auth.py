from __future__ import annotations

import contextvars
import hashlib
import hmac
import re
import secrets
import time
from dataclasses import dataclass
from typing import Literal

import bcrypt
from fastapi import HTTPException
from sqlmodel import Session

from app.config import get_env
from app.db import engine
from app.models import Service

Role = Literal["admin", "service", "ui", "anonymous"]

SERVICE_KEY_PREFIX = "svk"
UI_TOKEN_PREFIX = "gocu1"
UI_TOKEN_SIG_RE = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class Principal:
    role: Role
    service_id: str | None = None


_current_principal: contextvars.ContextVar[Principal | None] = contextvars.ContextVar(
    "current_principal",
    default=None,
)


def _env_bool(key: str, default: bool) -> bool:
    raw = (get_env(key, "true" if default else "false") or "").strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def auth_required() -> bool:
    return _env_bool("GOC_AUTH_REQUIRED", True)


def _required_env(key: str) -> str:
    value = (get_env(key, "") or "").strip()
    if not value:
        raise HTTPException(500, f"{key} is not configured")
    return value


def ensure_auth_config() -> None:
    if not auth_required():
        return
    _required_env("GOC_ADMIN_KEY")
    _required_env("GOC_UI_TOKEN_SECRET")


def set_current_principal(principal: Principal) -> contextvars.Token:
    return _current_principal.set(principal)


def reset_current_principal(token: contextvars.Token) -> None:
    _current_principal.reset(token)


def get_current_principal() -> Principal:
    principal = _current_principal.get()
    if principal is None:
        raise HTTPException(401, "principal context is missing")
    return principal


def require_admin_principal() -> Principal:
    principal = get_current_principal()
    if principal.role != "admin":
        raise HTTPException(403, "admin access required")
    return principal


def require_service_key_principal() -> Principal:
    principal = get_current_principal()
    if principal.role != "service":
        raise HTTPException(403, "ServiceKey authentication required")
    if not principal.service_id:
        raise HTTPException(401, "service scope is missing")
    return principal


def _parse_key_parts(raw_key: str) -> tuple[str, str]:
    parts = raw_key.split(".", 2)
    if len(parts) != 3 or parts[0] != SERVICE_KEY_PREFIX or not parts[1] or not parts[2]:
        raise HTTPException(401, "invalid ServiceKey format")
    return parts[1], raw_key


def hash_service_key(raw_key: str) -> str:
    pre = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return bcrypt.hashpw(pre, bcrypt.gensalt()).decode("utf-8")


def generate_service_key(service_id: str) -> str:
    # Keep service_id in the key for O(1) lookup; only the hash is stored.
    return f"{SERVICE_KEY_PREFIX}.{service_id}.{secrets.token_urlsafe(32)}"


def verify_service_key(raw_key: str) -> Service:
    service_id, raw = _parse_key_parts(raw_key.strip())
    with Session(engine) as session:
        service = session.get(Service, service_id)
        if not service or service.status != "active":
            raise HTTPException(401, "service is not active")
        hashed = (service.api_key_hash or "").encode("utf-8")
        pre = hashlib.sha256(raw.encode("utf-8")).digest()
        try:
            ok = bool(hashed) and bcrypt.checkpw(pre, hashed)
        except Exception:
            ok = False
        if not ok:
            raise HTTPException(401, "invalid ServiceKey")
        return service


def _ui_token_payload(service_id: str, exp: int) -> str:
    return f"{UI_TOKEN_PREFIX}.{service_id}.{exp}"


def mint_ui_bearer_token(service_id: str, ttl_sec: int | None = None) -> tuple[str, int]:
    secret = _required_env("GOC_UI_TOKEN_SECRET")
    default_ttl = int(get_env("GOC_UI_TOKEN_TTL_DEFAULT_SEC", "21600") or "21600")
    ttl = int(ttl_sec if ttl_sec is not None else default_ttl)
    ttl = max(60, min(ttl, 7 * 24 * 3600))
    exp = int(time.time()) + ttl
    payload = _ui_token_payload(service_id, exp)
    sig = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{sig}", exp


def verify_ui_bearer_token(raw_token: str) -> str:
    token = (raw_token or "").strip()
    parts = token.split(".")
    if len(parts) != 4 or parts[0] != UI_TOKEN_PREFIX:
        raise HTTPException(401, "invalid bearer token format")

    _, service_id, exp_raw, sig_hex = parts
    if not service_id:
        raise HTTPException(401, "missing service_id in token")
    if not UI_TOKEN_SIG_RE.fullmatch(sig_hex):
        raise HTTPException(401, "invalid bearer signature format")

    try:
        exp = int(exp_raw)
    except Exception as exc:
        raise HTTPException(401, "invalid bearer expiration") from exc

    if exp < int(time.time()):
        raise HTTPException(401, "bearer token expired")

    secret = _required_env("GOC_UI_TOKEN_SECRET")
    expected = hmac.new(
        secret.encode("utf-8"),
        _ui_token_payload(service_id, exp).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, sig_hex.lower()):
        raise HTTPException(401, "invalid bearer signature")

    with Session(engine) as session:
        service = session.get(Service, service_id)
        if not service or service.status != "active":
            raise HTTPException(401, "service is not active")

    return service_id


def resolve_principal(admin_header: str | None, authorization: str | None) -> Principal:
    if not auth_required():
        return Principal(role="admin", service_id=None)

    admin_key = (admin_header or "").strip()
    if admin_key:
        expected = _required_env("GOC_ADMIN_KEY")
        if hmac.compare_digest(admin_key, expected):
            return Principal(role="admin", service_id=None)
        raise HTTPException(401, "invalid X-Admin-Key")

    if not authorization:
        raise HTTPException(401, "missing authentication headers")

    scheme, _, raw = authorization.partition(" ")
    scheme_l = scheme.lower()
    raw = raw.strip()
    if not raw:
        raise HTTPException(401, "invalid Authorization header")

    if scheme_l == "servicekey":
        service = verify_service_key(raw)
        return Principal(role="service", service_id=service.id)

    if scheme_l == "bearer":
        service_id = verify_ui_bearer_token(raw)
        return Principal(role="ui", service_id=service_id)

    raise HTTPException(401, "unsupported Authorization scheme")
