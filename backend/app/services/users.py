from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlmodel import Session, select

from app.db import engine
from app.models import User, utcnow


def normalize_telegram_user_id(raw: Any) -> str:
    clean = str(raw or "").strip()
    if not clean:
        raise HTTPException(400, "telegram user id is missing")
    if not clean.isdigit():
        raise HTTPException(400, "invalid telegram user id")
    return clean


def _upsert_user_in_session(
    session: Session,
    *,
    telegram_user_id: str,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    language_code: str | None = None,
    is_bot: bool | None = None,
) -> User:
    clean_telegram_user_id = normalize_telegram_user_id(telegram_user_id)
    now = utcnow()
    current = session.exec(
        select(User)
        .where(User.telegram_user_id == clean_telegram_user_id)
        .limit(1)
    ).first()
    if not current:
        current = User(
            telegram_user_id=clean_telegram_user_id,
            username=(username or "").strip() or None,
            first_name=(first_name or "").strip() or None,
            last_name=(last_name or "").strip() or None,
            language_code=(language_code or "").strip() or None,
            is_bot=bool(is_bot is True),
            created_at=now,
            updated_at=now,
            last_login_at=now,
        )
        session.add(current)
        session.flush()
        return current

    if username is not None:
        current.username = (username or "").strip() or current.username
    if first_name is not None:
        current.first_name = (first_name or "").strip() or current.first_name
    if last_name is not None:
        current.last_name = (last_name or "").strip() or current.last_name
    if language_code is not None:
        current.language_code = (language_code or "").strip() or current.language_code
    if is_bot is not None:
        current.is_bot = bool(is_bot is True)
    current.updated_at = now
    current.last_login_at = now
    session.add(current)
    session.flush()
    return current


def upsert_user_by_telegram_id(
    telegram_user_id: str,
    *,
    username: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    language_code: str | None = None,
    is_bot: bool | None = None,
) -> User:
    with Session(engine) as session:
        user = _upsert_user_in_session(
            session,
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            is_bot=is_bot,
        )
        session.commit()
        session.refresh(user)
        return user


def upsert_user_from_telegram_payload(telegram_user: dict[str, Any]) -> User:
    if not isinstance(telegram_user, dict):
        raise HTTPException(400, "telegram user payload is invalid")
    telegram_user_id = normalize_telegram_user_id(telegram_user.get("id"))
    return upsert_user_by_telegram_id(
        telegram_user_id,
        username=str(telegram_user.get("username") or "").strip() or None,
        first_name=str(telegram_user.get("first_name") or "").strip() or None,
        last_name=str(telegram_user.get("last_name") or "").strip() or None,
        language_code=str(telegram_user.get("language_code") or "").strip() or None,
        is_bot=bool(telegram_user.get("is_bot") is True),
    )
