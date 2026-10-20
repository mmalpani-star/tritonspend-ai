from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import db
from backend.app.config import Settings, get_settings
from backend.app.db import Base, get_db
from backend.app.main import app
from backend.app.models import (
    BalanceCheckin,
    ConsentEvent,
    ConsentEventType,
    EntryType,
    ForecastSnapshot,
    InviteToken,
    LedgerEntry,
    Participant,
    ParticipantBalanceThreshold,
    ParticipantSession,
    ZeroSpendingConfirmation,
)
from backend.app.security import hash_secret, make_secret, utc_now


def _setup(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        database_url="sqlite:///:memory:",
        environment="test",
        consent_version="v1",
        consent_document_url="https://example.test/consent/v1",
        session_secret="session-secret",
        csrf_secret="csrf-secret",
        cors_origins=("http://localhost:3000",),
    )
    invite = make_secret()
    with factory.begin() as session:
        session.add(
            InviteToken(
                token_hash=hash_secret(invite, settings.session_secret),
                expires_at=utc_now() + timedelta(hours=1),
            )
        )

    def override_db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(db, "get_session_factory", lambda: factory)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app), factory, invite


def _authenticate(client: TestClient, invite: str) -> str:
    assert client.post("/api/v1/auth/redeem", json={"token": invite}).status_code == 200
    csrf = client.get("/api/v1/auth/csrf")
    assert csrf.status_code == 200
    token = csrf.json()["csrf_token"]
    assert client.post(
        "/api/v1/auth/consent",
        json={},
        headers={"X-CSRF-Token": token},
    ).status_code == 200
    return token


def test_participant_can_submit_and_read_collection_data(monkeypatch):
    client, factory, invite = _setup(monkeypatch)
    try:
        csrf = _authenticate(client, invite)
        today = date.today().isoformat()
        checkin = client.post(
            "/api/v1/pilot/balance-checkins",
            json={
                "effective_date": today,
                "dining_dollars_cents": 1250,
                "triton_cash_cents": 300,
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert checkin.status_code == 200
        ledger = client.post(
            "/api/v1/pilot/ledger-entries",
            json={
                "occurred_on": today,
                "account": "dining_dollars",
                "entry_type": "spending",
                "amount_cents": 125,
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert ledger.status_code == 200
        zero = client.post(
            "/api/v1/pilot/zero-spending-confirmations",
            json={"day": (date.today() - timedelta(days=1)).isoformat()},
            headers={"X-CSRF-Token": csrf},
        )
        assert zero.status_code == 200
        response = client.get(
            f"/api/v1/pilot/data?start_date={(date.today() - timedelta(days=1)).isoformat()}&end_date={today}"
        )
        assert response.status_code == 200
        assert [day["status"] for day in response.json()["days"]] == ["zero_spending", "checkin"]
        assert len(response.json()["ledger_entries"]) == 1
        with factory() as session:
            assert session.scalar(select(ConsentEvent)).event_type == ConsentEventType.accepted
    finally:
        app.dependency_overrides.clear()


def test_missing_days_are_unknown_and_invalid_writes_are_rejected(monkeypatch):
    client, factory, invite = _setup(monkeypatch)
    try:
        csrf = _authenticate(client, invite)
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        with factory.begin() as session:
            other = Participant()
            session.add(other)
            session.flush()
            session.add(
                LedgerEntry(
                    participant_id=other.id,
                    occurred_on=date.today(),
                    account="triton_cash",
                    entry_type=EntryType.deposit,
                    amount_cents=999,
                )
            )
        response = client.get(f"/api/v1/pilot/data?start_date={yesterday}&end_date={date.today().isoformat()}")
        assert [day["status"] for day in response.json()["days"]] == ["unknown", "unknown"]
        assert response.json()["ledger_entries"] == []
        invalid = client.post(
            "/api/v1/pilot/ledger-entries",
            json={
                "occurred_on": yesterday,
                "account": "dining_dollars",
                "entry_type": "spending",
                "amount_cents": 0,
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert invalid.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_writes_require_auth_csrf_and_active_consent(monkeypatch):
    client, factory, invite = _setup(monkeypatch)
    try:
        assert client.post(
            "/api/v1/pilot/ledger-entries",
            json={
                "occurred_on": date.today().isoformat(),
                "account": "triton_cash",
                "entry_type": "deposit",
                "amount_cents": 10,
            },
        ).status_code == 401
        csrf = _authenticate(client, invite)
        assert client.post(
            "/api/v1/auth/consent/withdraw",
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200
        blocked = client.post(
            "/api/v1/pilot/balance-checkins",
            json={
                "effective_date": date.today().isoformat(),
                "dining_dollars_cents": 1,
                "triton_cash_cents": 1,
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert blocked.status_code == 403
        assert client.get(
            f"/api/v1/pilot/data?start_date={date.today().isoformat()}&end_date={date.today().isoformat()}"
        ).status_code == 200
        with factory() as session:
            participant_count = session.query(Participant).count()
            assert participant_count == 1
    finally:
        app.dependency_overrides.clear()


def test_balance_warnings_cover_missing_above_equal_and_below(monkeypatch):
    client, _, invite = _setup(monkeypatch)
    try:
        csrf = _authenticate(client, invite)
        missing = client.post(
            "/api/v1/pilot/balance-thresholds",
            json={"dining_dollars_cents": 1000, "triton_cash_cents": 500},
            headers={"X-CSRF-Token": csrf},
        )
        assert missing.status_code == 200
        assert missing.json()["dining_dollars"]["warning"] is False
        assert missing.json()["dining_dollars"]["current_balance_cents"] is None
        assert missing.json()["dining_dollars"]["explanation"].startswith("Unknown:")

        today = date.today().isoformat()
        assert client.post(
            "/api/v1/pilot/balance-checkins",
            json={
                "effective_date": today,
                "dining_dollars_cents": 1000,
                "triton_cash_cents": 600,
            },
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200
        warning = client.get("/api/v1/pilot/balance-warnings")
        assert warning.status_code == 200
        body = warning.json()
        assert body["dining_dollars"]["warning"] is True
        assert body["dining_dollars"]["current_balance_cents"] == 1000
        assert body["triton_cash"]["warning"] is False
        assert body["triton_cash"]["current_balance_cents"] == 600
        assert client.post(
            "/api/v1/pilot/balance-checkins",
            json={
                "effective_date": today,
                "dining_dollars_cents": 900,
                "triton_cash_cents": 400,
            },
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200
        below = client.get("/api/v1/pilot/balance-warnings").json()
        assert below["dining_dollars"]["warning"] is True
        assert below["triton_cash"]["warning"] is True
        assert below["triton_cash"]["current_balance_cents"] == 400
    finally:
        app.dependency_overrides.clear()


def test_balance_thresholds_validate_and_are_participant_scoped(monkeypatch):
    client, factory, invite = _setup(monkeypatch)
    try:
        csrf = _authenticate(client, invite)
        invalid = client.post(
            "/api/v1/pilot/balance-thresholds",
            json={"dining_dollars_cents": -1, "triton_cash_cents": 0},
            headers={"X-CSRF-Token": csrf},
        )
        assert invalid.status_code == 422
        with factory.begin() as session:
            other = Participant()
            session.add(other)
            session.flush()
            session.add(
                ParticipantBalanceThreshold(
                    participant_id=other.id,
                    dining_dollars_cents=1,
                    triton_cash_cents=1,
                )
            )
        assert client.get("/api/v1/pilot/balance-warnings").status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_export_contains_only_participant_data_and_allows_withdrawn_consent(monkeypatch):
    client, factory, invite = _setup(monkeypatch)
    try:
        csrf = _authenticate(client, invite)
        today = date.today().isoformat()
        assert client.post(
            "/api/v1/pilot/balance-checkins",
            json={
                "effective_date": today,
                "dining_dollars_cents": 1200,
                "triton_cash_cents": 300,
            },
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200
        assert client.post(
            "/api/v1/pilot/ledger-entries",
            json={
                "occurred_on": today,
                "account": "dining_dollars",
                "entry_type": "refund",
                "amount_cents": 75,
                "merchant_or_note": "meal refund",
            },
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200
        assert client.post(
            "/api/v1/pilot/zero-spending-confirmations",
            json={"day": (date.today() - timedelta(days=1)).isoformat()},
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200
        assert client.post(
            "/api/v1/pilot/balance-thresholds",
            json={"dining_dollars_cents": 500, "triton_cash_cents": 100},
            headers={"X-CSRF-Token": csrf},
        ).status_code == 200
        assert client.post("/api/v1/auth/consent/withdraw", headers={"X-CSRF-Token": csrf}).status_code == 200

        response = client.get("/api/v1/pilot/export")
        assert response.status_code == 200
        body = response.json()
        assert body["schema_version"] == "stage5.v1"
        assert len(body["balance_checkins"]) == 1
        assert body["ledger_entries"][0]["entry_type"] == "refund"
        assert len(body["zero_spending_confirmations"]) == 1
        assert body["thresholds"]["dining_dollars_cents"] == 500
        with factory.begin() as session:
            owner = session.scalar(select(Participant))
            session.add(
                ForecastSnapshot(
                    participant_id=owner.id,
                    start_date=date.today(),
                    end_date=date.today(),
                    engine_version="test-v1",
                    request_json={"example": True},
                    response_json={"days": []},
                )
            )
        export_with_snapshot = client.get("/api/v1/pilot/export")
        assert export_with_snapshot.status_code == 200
        assert export_with_snapshot.json()["forecast_snapshots"][0]["engine_version"] == "test-v1"
        assert [event["event_type"] for event in body["consent_history"]] == ["accepted", "withdrawn"]
        serialized = response.text
        assert "token_hash" not in serialized
        assert "session_token_hash" not in serialized
        assert "csrf_token_hash" not in serialized
    finally:
        app.dependency_overrides.clear()


def test_delete_requires_auth_csrf_and_confirmation_and_preserves_other_participant(monkeypatch):
    client, factory, invite = _setup(monkeypatch)
    try:
        assert client.request(
            "DELETE",
            "/api/v1/pilot/account",
            json={"confirmation": "DELETE_MY_DATA"},
        ).status_code == 401
        csrf = _authenticate(client, invite)
        assert client.request(
            "DELETE",
            "/api/v1/pilot/account",
            json={"confirmation": "DELETE_MY_DATA"},
        ).status_code == 403
        assert client.request(
            "DELETE",
            "/api/v1/pilot/account",
            json={"confirmation": "WRONG"},
            headers={"X-CSRF-Token": csrf},
        ).status_code == 422
        with factory.begin() as session:
            owner = session.scalar(select(Participant))
            other = Participant()
            session.add(other)
            session.flush()
            session.add_all(
                [
                    BalanceCheckin(
                        participant_id=owner.id,
                        observed_at=utc_now(),
                        effective_date=date.today(),
                        dining_dollars_cents=1,
                        triton_cash_cents=1,
                    ),
                    ParticipantBalanceThreshold(
                        participant_id=owner.id,
                        dining_dollars_cents=1,
                        triton_cash_cents=1,
                    ),
                    LedgerEntry(
                        participant_id=owner.id,
                        occurred_on=date.today(),
                        account="dining_dollars",
                        entry_type=EntryType.spending,
                        amount_cents=1,
                    ),
                    ZeroSpendingConfirmation(
                        participant_id=owner.id,
                        day=date.today() - timedelta(days=1),
                    ),
                    ForecastSnapshot(
                        participant_id=owner.id,
                        start_date=date.today(),
                        end_date=date.today(),
                        engine_version="test",
                        request_json={},
                        response_json={},
                    ),
                    BalanceCheckin(
                        participant_id=other.id,
                        observed_at=utc_now(),
                        effective_date=date.today(),
                        dining_dollars_cents=2,
                        triton_cash_cents=2,
                    ),
                ]
            )
        deleted = client.request(
            "DELETE",
            "/api/v1/pilot/account",
            json={"confirmation": "DELETE_MY_DATA"},
            headers={"X-CSRF-Token": csrf},
        )
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True
        with factory() as session:
            assert session.query(BalanceCheckin).filter_by(participant_id=owner.id).count() == 0
            assert session.query(ParticipantBalanceThreshold).filter_by(participant_id=owner.id).count() == 0
            assert session.query(LedgerEntry).filter_by(participant_id=owner.id).count() == 0
            assert session.query(ZeroSpendingConfirmation).filter_by(participant_id=owner.id).count() == 0
            assert session.query(ForecastSnapshot).filter_by(participant_id=owner.id).count() == 0
            assert session.query(InviteToken).filter_by(participant_id=owner.id).count() == 0
            assert session.query(ConsentEvent).filter_by(participant_id=owner.id).count() == 1
            assert session.query(BalanceCheckin).filter_by(participant_id=other.id).count() == 1
            assert session.query(Participant).filter_by(id=owner.id).one().deleted_at is not None
            assert all(
                row.revoked_at is not None
                for row in session.query(ParticipantSession)
                .filter_by(participant_id=owner.id)
                .all()
            )
        assert client.get("/api/v1/pilot/export").status_code == 401
        assert client.request(
            "DELETE",
            "/api/v1/pilot/account",
            json={"confirmation": "DELETE_MY_DATA"},
            headers={"X-CSRF-Token": csrf},
        ).status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_delete_failure_rolls_back_data_changes(monkeypatch):
    client, factory, invite = _setup(monkeypatch)
    try:
        csrf = _authenticate(client, invite)
        with factory.begin() as session:
            participant = session.scalar(select(Participant))
            session.add(
                BalanceCheckin(
                    participant_id=participant.id,
                    observed_at=utc_now(),
                    effective_date=date.today(),
                    dining_dollars_cents=10,
                    triton_cash_cents=20,
                )
            )

        def failing_db():
            session = factory()
            session.commit = lambda: (_ for _ in ()).throw(RuntimeError("commit failed"))
            try:
                yield session
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        app.dependency_overrides[get_db] = failing_db
        with pytest.raises(RuntimeError, match="commit failed"):
            client.request(
                "DELETE",
                "/api/v1/pilot/account",
                json={"confirmation": "DELETE_MY_DATA"},
                headers={"X-CSRF-Token": csrf},
            )
        with factory() as session:
            assert session.query(BalanceCheckin).count() == 1
            assert session.query(Participant).one().deleted_at is None
    finally:
        app.dependency_overrides.clear()
