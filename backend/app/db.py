"""SQLAlchemy engine, session management, and persistence metadata."""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import Settings, load_settings


class Base(DeclarativeBase):
    pass


def create_engine_from_settings(settings: Settings):
    """Create an engine with SQLite-specific options only when needed."""
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(settings.database_url, future=True, connect_args=connect_args)


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
