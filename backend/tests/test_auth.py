import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import Response
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.config import Settings
from backend.app.db import Base, get_db
from backend.app.main import app
from backend.app.models import ConsentEvent, InviteToken, ParticipantSession
from backend.app import db
from backend.app.security import (
    SESSION_COOKIE,
    _active_session,
    hash_secret,
    make_secret,
    set_session_cookie,
    utc_now,
)


def setup_client(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    raw_invite = make_secret()
    settings = Settings(
        database_url="sqlite:///:memory:",
        environment="test",
        consent_version="v1",
        consent_document_url="https://example.test/consent/v1",
        session_secret="session-secret",
        csrf_secret="csrf-secret",
        cors_origins=("http://localhost:3000",),
    )
    with factory.begin() as session:
        session.add(
            InviteToken(
                token_hash=hash_secret(raw_invite, settings.session_secret),
                expires_at=utc_now() + timedelta(hours=1),
            )
        )
    def override_db():
        yield from _session(factory)

    monkeypatch.setattr(db, "get_session_factory", lambda: factory)
    app.dependency_overrides[get_db] = override_db
    from backend.app.config import get_settings

    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app), factory, raw_invite


def _session(factory):
    session = factory()
    try:
        yield session
    finally:
        session.close()


def test_invite_redeem_csrf_consent_withdraw_and_logout(monkeypatch):
    client, factory, raw_invite = setup_client(monkeypatch)
    try:
        redeemed = client.post("/api/v1/auth/redeem", json={"token": raw_invite})
        assert redeemed.status_code == 200
        csrf = client.get("/api/v1/auth/csrf")
        assert csrf.status_code == 200
        csrf_token = csrf.json()["csrf_token"]

        accepted = client.post(
            "/api/v1/auth/consent",
            json={
                "document_version_hash": hashlib.sha256(
                    b"v1\nhttps://example.test/consent/v1"
                ).hexdigest()
            },
            headers={"X-CSRF-Token": csrf_token},
        )
        assert accepted.status_code == 200

        withdrawn = client.post(
            "/api/v1/auth/consent/withdraw",
            headers={"X-CSRF-Token": csrf_token},
        )
        assert withdrawn.status_code == 200
        with factory() as session:
            assert session.scalars(select(ConsentEvent)).all()

        logged_out = client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": csrf_token},
        )
        assert logged_out.status_code == 200
        assert client.get("/api/v1/auth/csrf").status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_consent_rejects_unexpected_document_hash(monkeypatch):
    client, _, raw_invite = setup_client(monkeypatch)
    try:
        assert client.post("/api/v1/auth/redeem", json={"token": raw_invite}).status_code == 200
        csrf_token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
        response = client.post(
            "/api/v1/auth/consent",
            json={"document_version_hash": "client-controlled"},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_cookie_auth_state_change_requires_csrf_and_invites_are_single_use(monkeypatch):
    client, factory, raw_invite = setup_client(monkeypatch)
    try:
        assert client.post("/api/v1/auth/redeem", json={"token": raw_invite}).status_code == 200
        assert client.post("/api/v1/auth/consent", json={}).status_code == 403
        assert client.post("/api/v1/auth/redeem", json={"token": raw_invite}).status_code == 400
        with factory() as session:
            assert len(session.scalars(select(ParticipantSession)).all()) == 1
    finally:
        app.dependency_overrides.clear()


def test_invite_redemption_rejects_untrusted_origin(monkeypatch):
    client, _, raw_invite = setup_client(monkeypatch)
    try:
        response = client.post(
            "/api/v1/auth/redeem",
            json={"token": raw_invite},
            headers={"Origin": "https://evil.example"},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_session_renewal_persists_without_request_session_commit(monkeypatch):
    client, factory, raw_invite = setup_client(monkeypatch)
    try:
        assert client.post("/api/v1/auth/redeem", json={"token": raw_invite}).status_code == 200
        with factory() as session:
            record = session.query(ParticipantSession).one()
            old_seen = record.last_seen_at
            raw_token = client.cookies.get(SESSION_COOKIE)
        renewed_at = old_seen.replace(tzinfo=timezone.utc) + timedelta(minutes=5)
        request_session = factory()
        try:
            _active_session(request_session, raw_token, renewed_at, "session-secret")
        finally:
            request_session.close()
        with factory() as session:
            persisted = session.query(ParticipantSession).one().last_seen_at
            assert persisted.replace(tzinfo=timezone.utc) == renewed_at
    finally:
        app.dependency_overrides.clear()


def test_expired_session_is_rejected_and_revoked(monkeypatch):
    client, factory, raw_invite = setup_client(monkeypatch)
    try:
        assert client.post("/api/v1/auth/redeem", json={"token": raw_invite}).status_code == 200
        raw_token = client.cookies.get(SESSION_COOKIE)
        with factory() as session:
            record = session.query(ParticipantSession).one()
            record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            session.commit()
        response = client.get("/api/v1/auth/csrf")
        assert response.status_code == 401
        with factory() as session:
            assert session.query(ParticipantSession).one().revoked_at is not None
    finally:
        app.dependency_overrides.clear()


def test_idle_expired_session_is_rejected(monkeypatch):
    client, factory, raw_invite = setup_client(monkeypatch)
    try:
        assert client.post("/api/v1/auth/redeem", json={"token": raw_invite}).status_code == 200
        with factory() as session:
            record = session.query(ParticipantSession).one()
            record.last_seen_at = datetime.now(timezone.utc) - timedelta(days=7, seconds=1)
            session.commit()
        assert client.get("/api/v1/auth/csrf").status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_production_cookie_is_secure_and_local_cookie_allows_http():
    response = Response()
    settings = Settings(database_url="postgresql://db/app", environment="production")
    set_session_cookie(response, "secret", settings)
    assert "Secure" in response.headers["set-cookie"]
    local_response = Response()
    set_session_cookie(
        local_response,
        "secret",
        Settings(database_url="sqlite:///local.db", environment="local"),
    )
    assert "Secure" not in local_response.headers["set-cookie"]
