"""Validated database configuration for local, test, and hosted environments."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional
from urllib.parse import urlparse


class ConfigurationError(ValueError):
    """Raised when required runtime configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    database_url: str
    environment: str
    timezone: str = "America/Los_Angeles"
    consent_version: str = ""
    consent_document_url: str = ""
    consent_document_hash: str = ""
    session_secret: str = ""
    csrf_secret: str = ""
    cors_origins: tuple[str, ...] = ()
    # Food Chat moderators, by account email (lowercase). Server configuration only; empty by default.
    food_moderator_emails: tuple[str, ...] = ()


def load_settings(environ: Optional[dict[str, str]] = None) -> Settings:
    """Load database settings without ever silently falling back in production."""
    values = os.environ if environ is None else environ
    raw_environment = values.get("TRITONSPEND_ENV")
    if raw_environment is None or not raw_environment.strip():
        raise ConfigurationError("TRITONSPEND_ENV must be explicitly set")
    environment = raw_environment.strip().lower()
    if environment not in {"local", "test", "production"}:
        raise ConfigurationError("TRITONSPEND_ENV must be local, test, or production")

    database_url = values.get("DATABASE_URL", "").strip()
    if not database_url:
        if environment == "production":
            raise ConfigurationError("DATABASE_URL is required in production")
        database_url = (
            "sqlite:///./tritonspend-test.db"
            if environment == "test"
            else "sqlite:///./tritonspend.db"
        )
    _validate_database_url(database_url, environment)
    database_url = _with_installed_postgres_driver(database_url)

    timezone = values.get("TRITONSPEND_TIMEZONE", "America/Los_Angeles").strip()
    if timezone != "America/Los_Angeles":
        raise ConfigurationError("TRITONSPEND_TIMEZONE must be America/Los_Angeles")
    consent_version = values.get("TRITONSPEND_CONSENT_VERSION", "").strip()
    consent_document_url = values.get("TRITONSPEND_CONSENT_DOCUMENT_URL", "").strip()
    consent_document_hash = values.get("TRITONSPEND_CONSENT_DOCUMENT_HASH", "").strip()
    session_secret = values.get("TRITONSPEND_SESSION_SECRET", "").strip()
    csrf_secret = values.get("TRITONSPEND_CSRF_SECRET", "").strip()
    cors_value = values.get("TRITONSPEND_CORS_ORIGINS", "").strip()
    cors_origins = tuple(origin.strip().rstrip("/") for origin in cors_value.split(",") if origin.strip())
    moderator_value = values.get("TRITONSPEND_FOOD_MODERATOR_EMAILS", "")
    food_moderator_emails = tuple(sorted({email.strip().lower() for email in moderator_value.split(",") if email.strip()}))
    if environment == "production":
        for name, value in (
            ("TRITONSPEND_CONSENT_VERSION", consent_version),
            ("TRITONSPEND_CONSENT_DOCUMENT_URL", consent_document_url),
            ("TRITONSPEND_SESSION_SECRET", session_secret),
            ("TRITONSPEND_CSRF_SECRET", csrf_secret),
        ):
            if not value:
                raise ConfigurationError(f"{name} is required in production")
        parsed_consent_url = urlparse(consent_document_url)
        if (
            parsed_consent_url.scheme != "https"
            or not parsed_consent_url.hostname
            or parsed_consent_url.username
            or parsed_consent_url.password
        ):
            raise ConfigurationError(
                "TRITONSPEND_CONSENT_DOCUMENT_URL must be an absolute HTTPS URL"
            )
        if not cors_origins:
            raise ConfigurationError("TRITONSPEND_CORS_ORIGINS is required in production")
        if any(not _is_origin(origin, "https") for origin in cors_origins):
            raise ConfigurationError("production CORS origins must use HTTPS")
        public_origin = values.get("TRITONSPEND_PUBLIC_ORIGIN", "").strip().rstrip("/")
        if not public_origin:
            raise ConfigurationError("TRITONSPEND_PUBLIC_ORIGIN is required in production")
        if not _is_origin(public_origin, "https"):
            raise ConfigurationError("TRITONSPEND_PUBLIC_ORIGIN must use HTTPS")
        if public_origin not in cors_origins:
            raise ConfigurationError("TRITONSPEND_PUBLIC_ORIGIN must be in TRITONSPEND_CORS_ORIGINS")
    if not session_secret:
        session_secret = secrets.token_urlsafe(32)
    if not csrf_secret:
        csrf_secret = secrets.token_urlsafe(32)
    if environment == "production":
        for name, value in (
            ("TRITONSPEND_SESSION_SECRET", session_secret),
            ("TRITONSPEND_CSRF_SECRET", csrf_secret),
        ):
            if len(value) < 32:
                raise ConfigurationError(f"{name} must be at least 32 characters")
        if session_secret == csrf_secret:
            raise ConfigurationError("TRITONSPEND_SESSION_SECRET and TRITONSPEND_CSRF_SECRET must differ")
    return Settings(
        database_url=database_url,
        environment=environment,
        timezone=timezone,
        consent_version=consent_version,
        consent_document_url=consent_document_url,
        consent_document_hash=consent_document_hash,
        session_secret=session_secret,
        csrf_secret=csrf_secret,
        cors_origins=cors_origins,
        food_moderator_emails=food_moderator_emails,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """FastAPI-safe dependency for process environment configuration."""
    return load_settings()


def _validate_database_url(database_url: str, environment: str) -> None:
    parsed = urlparse(database_url)
    scheme = parsed.scheme.lower()
    if scheme == "sqlite":
        if environment == "production":
            raise ConfigurationError("SQLite is supported only in local and test environments")
        if not parsed.path:
            raise ConfigurationError("DATABASE_URL SQLite URL must include a database path")
        return
    if environment != "production":
        if scheme not in {
            "postgresql",
            "postgres",
            "postgresql+psycopg",
            "postgresql+psycopg2",
        }:
            raise ConfigurationError(
                "DATABASE_URL must use SQLite locally/test or PostgreSQL when configured"
            )
    if scheme not in {
        "postgresql",
        "postgres",
        "postgresql+psycopg",
        "postgresql+psycopg2",
    }:
        raise ConfigurationError("DATABASE_URL must use a supported PostgreSQL URL")
    if not parsed.hostname:
        raise ConfigurationError("DATABASE_URL PostgreSQL URL must include a host")
    if not parsed.path or parsed.path == "/":
        raise ConfigurationError("DATABASE_URL PostgreSQL URL must include a database name")


def _with_installed_postgres_driver(database_url: str) -> str:
    """Point bare PostgreSQL URLs at psycopg 3, the driver this project installs.

    Hosted providers such as Neon hand out ``postgresql://`` (or ``postgres://``) URLs.
    SQLAlchemy maps the bare scheme to psycopg2, which is not a dependency, and rejects
    ``postgres://`` outright, so both are rewritten. Explicit driver choices are kept.
    """
    scheme, separator, rest = database_url.partition("://")
    if separator and scheme.lower() in {"postgresql", "postgres"}:
        return f"postgresql+psycopg://{rest}"
    return database_url


def _is_origin(value: str, scheme: str) -> bool:
    parsed = urlparse(value)
    return (
        parsed.scheme == scheme
        and bool(parsed.hostname)
        and parsed.path in {"", "/"}
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )
