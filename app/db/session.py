"""SQLAlchemy engine and session management."""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def create_engine_from_url(database_url: str) -> Engine:
    """Create an engine for the provided database URL."""
    engine_kwargs: dict[str, object] = {"pool_pre_ping": True}
    if database_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    return create_engine(database_url, **engine_kwargs)


@lru_cache
def get_engine() -> Engine:
    """Create and cache the SQLAlchemy engine."""
    app_settings = get_settings()
    return create_engine_from_url(app_settings.database_url)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a SQLAlchemy session factory for the provided engine."""
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Create and cache the SQLAlchemy session factory."""
    return create_session_factory(get_engine())


def get_db_session() -> Generator[Session, None, None]:
    """Yield a database session for FastAPI dependency injection."""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
