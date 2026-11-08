from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import db
from backend.app.config import Settings, get_settings
from backend.app.db import Base, get_db
from backend.app.main import app
from backend.app.models import Participant, ParticipantSession, UserAccount
from backend.app.security import SESSION_COOKIE

PASSWORD = "correct horse battery"


@pytest.fixture
def factory(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        database_url="sqlite:///:memory:",
        environment="test",
        consent_version="v1",
        consent_document_url="https://example.test/consent/v1",
        session_secret="session-secret",
        csrf_secret="csrf-secret",
        cors_origins=("http://localhost:3000",),
    )

    def override_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(db, "get_session_factory", lambda: session_factory)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    yield session_factory
    app.dependency_overrides.clear()


def signup(client, email="student@example.com", password=PASSWORD, confirmation=None):
    return client.post("/api/v1/auth/signup", json={
        "email": email, "password": password, "password_confirmation": password if confirmation is None else confirmation,
    })


def login(client, email="student@example.com", password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def csrf(client):
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    return response.json()["csrf_token"]


def accept_consent(client):
    token = csrf(client)
    assert client.post("/api/v1/auth/consent", json={}, headers={"X-CSRF-Token": token}).status_code == 200
    return token


def account_count(factory):
    with factory() as session:
        return session.scalar(select(func.count()).select_from(UserAccount))


def test_signup_accepts_any_email_domain_stores_only_a_hash_and_signs_in(factory):
    client = TestClient(app)

    response = signup(client, email="  New.Student@Gmail.COM ")

    assert response.status_code == 201
    assert SESSION_COOKIE in response.cookies
    status = client.get("/api/v1/auth/status").json()
    assert status["authenticated"] is True
    assert status["email"] == "new.student@gmail.com"
    assert status["consent_active"] is False
    with factory() as session:
        account = session.scalar(select(UserAccount))
        assert account.email == "new.student@gmail.com"
        assert account.participant_id == response.json()["participant_id"]
        assert account.password_hash.startswith("$argon2id$")
        assert PASSWORD not in account.password_hash


def test_signup_still_requires_consent_before_recording_data(factory):
    client = TestClient(app)
    assert signup(client).status_code == 201
    payload = {"effective_date": date.today().isoformat(), "dining_dollars_cents": 100, "triton_cash_cents": 0}

    assert client.post("/api/v1/pilot/balance-checkins", json=payload, headers={"X-CSRF-Token": csrf(client)}).status_code == 403
    token = accept_consent(client)
    assert client.post("/api/v1/pilot/balance-checkins", json=payload, headers={"X-CSRF-Token": token}).status_code == 200


@pytest.mark.parametrize("variant", ["student@example.com", "STUDENT@example.com", "  student@Example.com  "])
def test_duplicate_email_is_rejected_case_insensitively(factory, variant):
    assert signup(TestClient(app)).status_code == 201

    response = signup(TestClient(app), email=variant, password="a different password")

    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]
    assert account_count(factory) == 1


@pytest.mark.parametrize(
    "email,password,confirmation,message",
    [
        ("student@example.com", PASSWORD, PASSWORD + "x", "Passwords do not match"),
        ("student@example.com", "short", "short", "8 to 128 characters"),
        ("student@example.com", "x" * 129, "x" * 129, "8 to 128 characters"),
        ("student@example.com", "        ", "        ", "only spaces"),
        ("not-an-email", PASSWORD, PASSWORD, "valid email"),
        ("student@localhost", PASSWORD, PASSWORD, "valid email"),
        ("two@@example.com", PASSWORD, PASSWORD, "valid email"),
        ("student@example.com", "student@example.com", "student@example.com", "cannot be your email"),
    ],
)
def test_signup_validation_errors_are_reported_and_nothing_is_created(factory, email, password, confirmation, message):
    response = signup(TestClient(app), email=email, password=password, confirmation=confirmation)

    assert response.status_code == 422
    assert message in str(response.json()["detail"])
    assert account_count(factory) == 0


def test_signup_rejects_unknown_fields(factory):
    response = TestClient(app).post("/api/v1/auth/signup", json={
        "email": "student@example.com", "password": PASSWORD, "password_confirmation": PASSWORD, "participant_id": "x",
    })

    assert response.status_code == 422
    assert account_count(factory) == 0


def test_login_logout_and_login_again_with_fresh_sessions(factory):
    client = TestClient(app)
    created = signup(client).json()
    token = csrf(client)

    assert client.post("/api/v1/auth/logout").status_code == 403  # logout needs CSRF
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": token}).status_code == 200
    assert client.get("/api/v1/auth/status").status_code == 401

    response = login(client, email="Student@Example.com")

    assert response.status_code == 200
    assert response.json()["participant_id"] == created["participant_id"]
    assert client.get("/api/v1/auth/status").json()["email"] == "student@example.com"
    with factory() as session:
        sessions = session.scalars(select(ParticipantSession)).all()
        assert len(sessions) == 2
        assert sum(record.revoked_at is None for record in sessions) == 1
        assert session.scalar(select(UserAccount)).last_login_at is not None


@pytest.mark.parametrize("email,password", [("student@example.com", "wrong password!"), ("nobody@example.com", PASSWORD)])
def test_wrong_password_and_unknown_email_get_the_same_generic_error(factory, email, password):
    assert signup(TestClient(app)).status_code == 201
    client = TestClient(app)

    response = login(client, email=email, password=password)

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password."
    assert SESSION_COOKIE not in response.cookies
    assert client.get("/api/v1/auth/status").status_code == 401


def test_accounts_are_isolated_from_each_other(factory):
    alice, bob = TestClient(app), TestClient(app)
    assert signup(alice, email="alice@example.com", password="alice password 1").status_code == 201
    assert signup(bob, email="bob@example.com", password="bob password 22").status_code == 201
    alice_token = accept_consent(alice)
    accept_consent(bob)
    today = date.today().isoformat()
    assert alice.post("/api/v1/pilot/ledger-entries", json={
        "occurred_on": today, "account": "triton_cash", "entry_type": "deposit", "amount_cents": 999,
    }, headers={"X-CSRF-Token": alice_token}).status_code == 200

    assert bob.get(f"/api/v1/pilot/data?start_date={today}&end_date={today}").json()["ledger_entries"] == []
    assert bob.get("/api/v1/pilot/export").json()["participant"]["email"] == "bob@example.com"
    assert alice.get("/api/v1/pilot/export").json()["participant"]["email"] == "alice@example.com"
    # One account's password never opens another account.
    assert login(TestClient(app), email="alice@example.com", password="bob password 22").status_code == 401
    assert login(TestClient(app), email="bob@example.com", password="alice password 1").status_code == 401
    # Logging out one account leaves the other signed in.
    assert alice.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf(alice)}).status_code == 200
    assert bob.get("/api/v1/auth/status").status_code == 200


def test_deleted_account_cannot_log_in_and_email_can_be_registered_again(factory):
    client = TestClient(app)
    first = signup(client).json()
    token = accept_consent(client)
    assert client.request("DELETE", "/api/v1/pilot/account", json={"confirmation": "DELETE_MY_DATA"}, headers={"X-CSRF-Token": token}).status_code == 200

    assert login(TestClient(app)).status_code == 401
    again = signup(TestClient(app))

    assert again.status_code == 201
    assert again.json()["participant_id"] != first["participant_id"]
    with factory() as session:
        assert session.get(Participant, first["participant_id"]).deleted_at is not None
        assert session.scalar(select(func.count()).select_from(UserAccount)) == 1


def test_signup_and_login_reject_untrusted_origins(factory):
    assert signup(TestClient(app)).status_code == 201
    evil = {"Origin": "https://evil.example"}

    assert TestClient(app).post("/api/v1/auth/login", json={"email": "student@example.com", "password": PASSWORD}, headers=evil).status_code == 403
    assert TestClient(app).post("/api/v1/auth/signup", json={
        "email": "other@example.com", "password": PASSWORD, "password_confirmation": PASSWORD,
    }, headers=evil).status_code == 403
    assert account_count(factory) == 1
