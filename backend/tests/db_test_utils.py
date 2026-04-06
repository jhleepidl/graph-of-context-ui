from __future__ import annotations

import atexit
import weakref

from sqlalchemy.pool import StaticPool
from sqlmodel import create_engine as sqlmodel_create_engine

_TRACKED_ENGINES = []


def create_test_engine(url: str = 'sqlite://', **kwargs):
    if url.startswith('sqlite://'):
        kwargs.setdefault('connect_args', {'check_same_thread': False})
        kwargs.setdefault('poolclass', StaticPool)
    engine = sqlmodel_create_engine(url, **kwargs)
    _TRACKED_ENGINES.append(engine)
    weakref.finalize(engine, engine.dispose)
    return engine


def dispose_tracked_engines() -> None:
    while _TRACKED_ENGINES:
        engine = _TRACKED_ENGINES.pop()
        try:
            engine.dispose()
        except Exception:
            pass


atexit.register(dispose_tracked_engines)
