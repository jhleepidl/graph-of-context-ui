from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.auth import mint_ui_bearer_token
from app.config import get_env
from app.db import engine
from app.models import Service
from app.services.users import upsert_user_from_telegram_payload

router = APIRouter(prefix="/api/auth/telegram", tags=["telegram_auth"])


class TelegramWebAppLoginRequest(BaseModel):
    init_data: str
    max_age_sec: int = 86400
    ttl_sec: int | None = None


def _required_env(key: str) -> str:
    value = (get_env(key, "") or "").strip()
    if not value:
        raise HTTPException(500, f"{key} is not configured")
    return value


def _optional_env(key: str, default: str = "") -> str:
    return (get_env(key, default) or default).strip()


def _json_object_or_error(raw: str | None, name: str, *, required: bool) -> dict[str, Any] | None:
    if not raw:
        if required:
            raise HTTPException(401, f"{name} is missing")
        return None
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        raise HTTPException(401, f"invalid {name} payload") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(401, f"invalid {name} payload")
    return parsed


def _parse_allowlist_ids() -> set[str]:
    raw = _optional_env("GOC_TELEGRAM_ALLOWED_USER_IDS", "")
    if not raw:
        return set()
    return {x.strip() for x in raw.split(",") if x.strip()}


def _compute_expected_hash(init_data: str, bot_token: str) -> tuple[str, dict[str, str]]:
    items = parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    if not items:
        raise HTTPException(400, "init_data is empty")

    received_hash = ""
    values: dict[str, str] = {}
    payload_pairs: list[tuple[str, str]] = []
    for key, value in items:
        if key == "hash":
            received_hash = value.strip().lower()
            continue
        payload_pairs.append((key, value))
        if key not in values:
            values[key] = value

    if not received_hash:
        raise HTTPException(401, "missing hash")

    payload_pairs.sort(key=lambda kv: kv[0])
    data_check_string = "\n".join(f"{k}={v}" for k, v in payload_pairs)

    # Telegram WebApp 공식 검증:
    # secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise HTTPException(401, "invalid init_data signature")

    return expected_hash, values


def _check_auth_date(values: dict[str, str], max_age_sec: int) -> None:
    raw = (values.get("auth_date") or "").strip()
    try:
        auth_date = int(raw)
    except Exception as exc:
        raise HTTPException(401, "invalid auth_date") from exc

    now = int(time.time())
    max_age = max(1, int(max_age_sec))
    if auth_date > now + 300:
        raise HTTPException(401, "invalid auth_date")
    if now - auth_date > max_age:
        raise HTTPException(401, "init_data expired")


def _ensure_active_service(service_id: str) -> None:
    with Session(engine) as session:
        service = session.get(Service, service_id)
        if not service:
            # Telegram SSO only needs an active service scope for bearer verification.
            # Auto-provision the configured service_id when it does not exist yet.
            service = Service(
                id=service_id,
                name=f"telegram:{service_id}",
                status="active",
                api_key_hash="",
            )
            session.add(service)
            session.commit()
            return
        if service.status != "active":
            raise HTTPException(500, f"configured service is not active: {service_id}")


@router.post("/webapp")
def login_with_webapp(body: TelegramWebAppLoginRequest):
    init_data = (body.init_data or "").strip()
    if not init_data:
        raise HTTPException(400, "init_data is required")

    bot_token = _required_env("GOC_TELEGRAM_BOT_TOKEN")
    _, values = _compute_expected_hash(init_data, bot_token)
    _check_auth_date(values, body.max_age_sec)

    telegram_user = _json_object_or_error(values.get("user"), "user", required=True)
    telegram_chat = _json_object_or_error(values.get("chat"), "chat", required=False)
    if telegram_user is None:
        raise HTTPException(401, "user is missing")

    telegram_user_id = str(telegram_user.get("id") or "").strip()
    if not telegram_user_id:
        raise HTTPException(401, "telegram user id is missing")

    allowed_ids = _parse_allowlist_ids()
    if allowed_ids and telegram_user_id not in allowed_ids:
        raise HTTPException(403, "telegram user is not allowed")

    service_id = _optional_env("GOC_TELEGRAM_DEFAULT_SERVICE_ID", "default") or "default"
    _ensure_active_service(service_id)
    user = upsert_user_from_telegram_payload(telegram_user)
    token, exp = mint_ui_bearer_token(service_id, body.ttl_sec, user_id=user.id)

    return {
        "ok": True,
        "service_id": service_id,
        "token": token,
        "exp": exp,
        "user_id": user.id,
        "telegram_user": telegram_user,
        "telegram_chat": telegram_chat,
    }
