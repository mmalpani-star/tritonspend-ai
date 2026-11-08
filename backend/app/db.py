"""SQLAlchemy engine, session management, and persistence metadata."""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache
from typing import Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import Settings, load_settings


class Base(DeclarativeBase):
    pass


def enforce_sqlite_foreign_keys(engine: Engine) -> None:
    """Turn on foreign-key enforcement for every new SQLite connection.

    SQLite ignores foreign keys unless each connection enables them; PostgreSQL always
    enforces them, so this keeps local SQLite as strict (e.g. stations inside venues).
    """

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


def create_engine_from_settings(settings: Settings):
    """Create an engine with SQLite-specific options only when needed."""
    is_sqlite = settings.database_url.startswith("sqlite")
    if is_sqlite:
        engine = create_engine(settings.database_url, future=True, connect_args={"check_same_thread": False})
        enforce_sqlite_foreign_keys(engine)
        return engine
    # Hosted PostgreSQL (e.g. Neon) closes idle connections and may suspend the compute, so
    # check each pooled connection before use, retire connections after five minutes, and keep
    # the pool small: a single web service rarely needs more than a handful of connections.
    return create_engine(
        settings.database_url,
        future=True,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=5,
        max_overflow=5,
        pool_timeout=30,
        connect_args={"connect_timeout": 10},
    )


def build_session_factory(settings: Optional[Settings] = None) -> sessionmaker[Session]:
    selected = settings or load_settings()
    return sessionmaker(
        bind=create_engine_from_settings(selected),
        autoflush=False,
        expire_on_commit=False,
    )


@lru_cache(maxsize=1)
def get_engine():
    """Return the application-scoped engine."""
    return create_engine_from_settings(load_settings())


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Return the application-scoped session factory."""
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped session for future API consumers."""
    session = get_session_factory()()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def session_scope() -> Generator[Session, None, None]:
    """Yield an application session with commit/rollback lifecycle."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
