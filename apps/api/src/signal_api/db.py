from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def init_engine(database_url: str) -> Engine:
    global _engine, _session_factory
    _engine = create_engine(database_url, pool_pre_ping=True)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    assert _engine is not None, "engine 未初始化"
    return _engine


def make_session() -> Session:
    assert _session_factory is not None, "engine 未初始化"
    return _session_factory()


def get_session() -> Iterator[Session]:
    """FastAPI 依赖。"""
    with make_session() as session:
        yield session
