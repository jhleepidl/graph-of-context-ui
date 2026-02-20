from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_LOADED = False
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_DOTENV_PATH = _BACKEND_DIR / ".env"


def load_environment() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    load_dotenv(dotenv_path=_DOTENV_PATH, override=False)
    _ENV_LOADED = True


def get_env(key: str, default: str | None = None) -> str | None:
    load_environment()
    return os.getenv(key, default)
