"""Opt-in PostgreSQL integration coverage for the migrated disposable database.

This module deliberately refuses every target except the disposable database
defined by compose.postgres-test.yml, identified by the exact database comment
written by backend/tests/postgres/init/01-disposable-marker.sql. The target,
marker, Alembic revision, and empty tables are verified before any write. Most
tests use an outer transaction and roll it back. The
concurrent-redemption case needs independent committed connections, so it has
its own opt-in and deletes only records reachable from its registered invite.
An abrupt process termination can still leave that test's committed synthetic
data behind; run it only against a freshly verified disposable database.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from backend.app import db
from backend.app.config import Settings, get_settings
from backend.app.db import get_db
from backend.app.dependencies import pilot_today_provider
from backend.app.main import app
from backend.app.models import (
    BalanceCheckin,
    Consent,
    ConsentEvent,
    ForecastSnapshot,
    InviteToken,
    LedgerEntry,
    Participant,
    ParticipantBalanceThreshold,
    ParticipantSession,
    UserAccount,
    ZeroSpendingConfirmation,
)
from backend.app.food_catalog import menu_name_key, seed_food_catalog
from backend.app.food_models import (
    FOOD_USER_CONTENT_MODELS, FoodMenuItem, FoodReview, FoodStation, FoodVenue, FoodVenueRating, ReviewTarget,
)
from backend.app.security import hash_secret, make_secret, utc_now


EXPECTED_REVISION = "20261108_0008"
EXPECTED_HOST = "127.0.0.1"
EXPECTED_PORT = 5434
EXPECTED_DATABASE = "tritonspend_test"
EXPECTED_USER = "tritonspend"
EXPECTED_DATABASE_COMMENT = "tritonspend-disposable-test"
# Fail fast instead of hanging on an unreachable server or a held lock.
CONNECT_ARGS = {
    "connect_timeout": 5,
    "options": "-c lock_timeout=5000 -c statement_timeout=30000",
}
APPLICATION_MODELS = (
    Participant,
    InviteToken,
    Consent,
    BalanceCheckin,
    ParticipantBalanceThreshold,
    LedgerEntry,
    ZeroSpendingConfirmation,
    ForecastSnapshot,
    ConsentEvent,
    ParticipantSession,
    UserAccount,
    # Food Chat content is participant data too; the catalog tables may already be seeded.
    *FOOD_USER_CONTENT_MODELS,
)


def _integration_url() -> URL:
    if os.environ.get("TRITONSPEND_POSTGRES_INTEGRATION") != "1":
        pytest.skip("set TRITONSPEND_POSTGRES_INTEGRATION=1 to run PostgreSQL integration tests")
    if os.environ.get("TRITONSPEND_ENV") != "test":
        pytest.fail("PostgreSQL integration tests require TRITONSPEND_ENV=test")

    raw_url = os.environ.get("DATABASE_URL")
    if not raw_url:
        pytest.fail("PostgreSQL integration tests require DATABASE_URL")
    url = make_url(raw_url)
    if (
        url.drivername != "postgresql+psycopg"
        or url.username != EXPECTED_USER
        or url.host != EXPECTED_HOST
        or url.port != EXPECTED_PORT
        or url.database != EXPECTED_DATABASE
        or url.query
    ):
        pytest.fail(
            "PostgreSQL integration tests only permit "
            "postgresql+psycopg://tritonspend@127.0.0.1:5434/tritonspend_test "
            "without query parameters"
        )
    return url


def _engine(url: URL) -> Engine:
    return create_engine(url, future=True, connect_args=CONNECT_ARGS)


def _assert_migrated_and_empty(engine: Engine) -> None:
    """Read-only checks that must all pass before a test writes anything."""
    with engine.connect() as connection:
        database, user = connection.execute(
            text("SELECT current_database(), current_user")
        ).one()
        if database != EXPECTED_DATABASE or user != EXPECTED_USER:
            pytest.fail(
                "connected PostgreSQL identity does not match the approved "
                "tritonspend_test test target"
            )
        comment = connection.scalar(
            text(
                "SELECT shobj_description(oid, 'pg_database') "
                "FROM pg_database WHERE datname = current_database()"
            )
        )
        if comment != EXPECTED_DATABASE_COMMENT:
            pytest.fail(
                "refusing a database without the disposable-test marker comment; "
                "provision it with compose.postgres-test.yml"
            )
        if not connection.scalar(text("SELECT to_regclass('alembic_version') IS NOT NULL")):
            pytest.fail(
                "alembic_version table is missing; run `alembic upgrade head` "
                "against the disposable test database first"
            )
        revisions = connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        if revisions != [EXPECTED_REVISION]:
            pytest.fail(f"expected Alembic revision {EXPECTED_REVISION}, found {revisions!r}")
        populated = [
            model.__tablename__
            for model in APPLICATION_MODELS
            if connection.scalar(select(func.count()).select_from(model))
        ]
    if populated:
        pytest.fail(
            "refusing to write to a database with existing application rows: "
            + ", ".join(populated)
        )


def _settings(url: URL) -> Settings:
    return Settings(
        database_url=url.render_as_string(hide_password=False),
        environment="test",
        consent_version="postgres-integration-v1",
        consent_document_url="https://example.test/consent/postgres-integration-v1",
        session_secret="postgres-integration-session-secret",
        csrf_secret="postgres-integration-csrf-secret",
        cors_origins=("http://localhost:3000",),
    )


def _install_app_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    factory: sessionmaker[Session],
    settings: Settings,
) -> dict:
    previous_overrides = app.dependency_overrides.copy()

    def override_db():
        session = factory()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    monkeypatch.setattr(db, "get_session_factory", lambda: factory)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    return previous_overrides


def _restore_app_dependencies(previous_overrides: dict) -> None:
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous_overrides)


@pytest.fixture
def postgres_client(monkeypatch: pytest.MonkeyPatch):
    """Use a real PostgreSQL connection inside a rollback-only outer transaction."""
    url = _integration_url()
    engine = None
    connection = None
    outer_transaction = None
    client = None
    previous_overrides = app.dependency_overrides.copy()
    try:
        engine = _engine(url)
        _assert_migrated_and_empty(engine)
        connection = engine.connect()
        outer_transaction = connection.begin()
        factory = sessionmaker(
            bind=connection,
            autoflush=False,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        _install_app_dependencies(monkeypatch, factory, _settings(url))
        client = TestClient(app)
        yield client, factory
    finally:
        if client is not None:
            client.close()
        _restore_app_dependencies(previous_overrides)
        if outer_transaction is not None and outer_transaction.is_active:
            outer_transaction.rollback()
        if connection is not None:
            connection.close()
        if engine is not None:
            engine.dispose()


@pytest.fixture
def postgres_concurrent_context(monkeypatch: pytest.MonkeyPatch):
    """Use independent connections only for the separately opted-in concurrency test."""
    if os.environ.get("TRITONSPEND_POSTGRES_CONCURRENCY") != "1":
        pytest.skip(
            "set TRITONSPEND_POSTGRES_CONCURRENCY=1 to run committed concurrency coverage"
        )
    url = _integration_url()
    engine = None
    previous_overrides = app.dependency_overrides.copy()
    try:
        engine = _engine(url)
        _assert_migrated_and_empty(engine)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        _install_app_dependencies(monkeypatch, factory, _settings(url))
        yield engine, factory
    finally:
        _restore_app_dependencies(previous_overrides)
        if engine is not None:
            engine.dispose()


def _create_invite(factory: sessionmaker[Session]) -> tuple[str, str]:
    raw_token = make_secret()
    with factory.begin() as session:
        invite = InviteToken(
            token_hash=hash_secret(raw_token, "postgres-integration-session-secret"),
            expires_at=utc_now() + timedelta(hours=1),
        )
        session.add(invite)
        session.flush()
        return raw_token, invite.id


def _authenticate(client: TestClient, raw_invite: str) -> tuple[str, str]:
    redeemed = client.post("/api/v1/auth/redeem", json={"token": raw_invite})
    assert redeemed.status_code == 200
    participant_id = redeemed.json()["participant_id"]
    csrf = client.get("/api/v1/auth/csrf")
    assert csrf.status_code == 200
    csrf_token = csrf.json()["csrf_token"]
    accepted = client.post("/api/v1/auth/consent", json={}, headers={"X-CSRF-Token": csrf_token})
    assert accepted.status_code == 200
    return participant_id, csrf_token


def test_postgres_persists_and_retrieves_pilot_data(postgres_client):
    client, factory = postgres_client
    raw_invite, _ = _create_invite(factory)
    participant_id, csrf = _authenticate(client, raw_invite)
    today = date.today().isoformat()

    assert client.post(
        "/api/v1/pilot/balance-checkins",
        json={
            "effective_date": today,
            "dining_dollars_cents": 1250,
            "triton_cash_cents": 300,
        },
        headers={"X-CSRF-Token": csrf},
    ).status_code == 200
    assert client.post(
        "/api/v1/pilot/ledger-entries",
        json={
            "occurred_on": today,
            "account": "dining_dollars",
            "entry_type": "spending",
            "amount_cents": 125,
        },
        headers={"X-CSRF-Token": csrf},
    ).status_code == 200

    response = client.get(f"/api/v1/pilot/data?start_date={today}&end_date={today}")
    assert response.status_code == 200
    assert response.json()["days"][0]["checkin"]["dining_dollars_cents"] == 1250
    assert response.json()["ledger_entries"][0]["amount_cents"] == 125
    with factory() as session:
        assert session.scalar(
            select(func.count()).select_from(BalanceCheckin).where(
                BalanceCheckin.participant_id == participant_id
            )
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(LedgerEntry).where(
                LedgerEntry.participant_id == participant_id
            )
        ) == 1


def test_postgres_requires_authentication_and_csrf(postgres_client):
    client, factory = postgres_client
    today = date.today().isoformat()
    payload = {
        "effective_date": today,
        "dining_dollars_cents": 1,
        "triton_cash_cents": 1,
    }
    assert client.post("/api/v1/pilot/balance-checkins", json=payload).status_code == 401

    raw_invite, _ = _create_invite(factory)
    redeemed = client.post("/api/v1/auth/redeem", json={"token": raw_invite})
    assert redeemed.status_code == 200
    assert client.post("/api/v1/pilot/balance-checkins", json=payload).status_code == 403
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    assert client.post(
        "/api/v1/pilot/balance-checkins",
        json=payload,
        headers={"X-CSRF-Token": "invalid"},
    ).status_code == 403
    assert client.post("/api/v1/auth/consent", json={}, headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.post(
        "/api/v1/pilot/balance-checkins", json=payload, headers={"X-CSRF-Token": csrf}
    ).status_code == 200


def test_postgres_isolates_participants_and_exports_only_owner_data(postgres_client):
    _, factory = postgres_client
    owner_invite, _ = _create_invite(factory)
    other_invite, _ = _create_invite(factory)
    with TestClient(app) as owner, TestClient(app) as other:
        _, owner_csrf = _authenticate(owner, owner_invite)
        _authenticate(other, other_invite)
        today = date.today().isoformat()
        assert owner.post(
            "/api/v1/pilot/ledger-entries",
            json={
                "occurred_on": today,
                "account": "triton_cash",
                "entry_type": "deposit",
                "amount_cents": 999,
            },
            headers={"X-CSRF-Token": owner_csrf},
        ).status_code == 200

        other_data = other.get(f"/api/v1/pilot/data?start_date={today}&end_date={today}")
        assert other_data.status_code == 200
        assert other_data.json()["ledger_entries"] == []
        other_export = other.get("/api/v1/pilot/export")
        assert other_export.status_code == 200
        assert other_export.json()["ledger_entries"] == []


def test_postgres_exports_and_deletes_only_the_authenticated_participant(postgres_client):
    client, factory = postgres_client
    raw_invite, _ = _create_invite(factory)
    participant_id, csrf = _authenticate(client, raw_invite)
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
        },
        headers={"X-CSRF-Token": csrf},
    ).status_code == 200

    exported = client.get("/api/v1/pilot/export")
    assert exported.status_code == 200
    body = exported.json()
    assert body["ledger_entries"][0]["amount_cents"] == 75
    serialized = exported.text
    assert "token_hash" not in serialized
    assert "session_token_hash" not in serialized
    assert "csrf_token_hash" not in serialized

    assert client.request(
        "DELETE",
        "/api/v1/pilot/account",
        json={"confirmation": "DELETE_MY_DATA"},
        headers={"X-CSRF-Token": csrf},
    ).status_code == 200
    with factory() as session:
        assert session.scalar(
            select(func.count()).select_from(BalanceCheckin).where(
                BalanceCheckin.participant_id == participant_id
            )
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(LedgerEntry).where(
                LedgerEntry.participant_id == participant_id
            )
        ) == 0
        assert session.get(Participant, participant_id).deleted_at is not None
        assert session.scalar(
            select(func.count()).select_from(ConsentEvent).where(
                ConsentEvent.participant_id == participant_id
            )
        ) == 1


def test_postgres_food_catalog_seed_hierarchy_and_api(postgres_client):
    """Catalog seeding, composite-key integrity and the public API on PostgreSQL (rolled back)."""
    from sqlalchemy.exc import IntegrityError

    client, factory = postgres_client
    with factory() as session:
        first = seed_food_catalog(session)
        session.commit()
        assert (first.venues_inserted, first.stations_inserted) == (68, 45)
        again = seed_food_catalog(session)
        session.commit()
        assert (again.venues_unchanged, again.stations_unchanged) == (68, 45)
        assert session.scalar(select(func.count()).select_from(FoodVenue).where(FoodVenue.hours.is_(None))) == 52

        participant = Participant()
        session.add(participant)
        session.flush()
        item = FoodMenuItem(
            station_id="64-degrees--triton-grill", name="Chicken Rice Bowl", name_key=menu_name_key("Chicken Rice Bowl"),
            source_url="https://hdh-web.ucsd.edu/dining/apps/diningservices", verified_at=utc_now(),
        )
        session.add(item)
        session.flush()
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.add(FoodReview(
                    participant_id=participant.id, target_type=ReviewTarget.menu_item, venue_id="pines",
                    station_id=item.station_id, menu_item_id=item.id, rating=4, body="",
                ))
                session.flush()
        session.add(FoodReview(participant_id=participant.id, target_type=ReviewTarget.venue, venue_id="pines", rating=4, body=""))
        # Since 0008 a venue's stars come from venue ratings, not from the older written reviews.
        session.add(FoodVenueRating(participant_id=participant.id, venue_id="pines", rating=4))
        session.commit()
        assert session.get(FoodStation, "pines--slice-at-pines").venue_id == "pines"

    venues = client.get("/api/v1/food/venues", params={"operator": "hdh"}).json()
    assert venues["total"] == 16
    assert client.get("/api/v1/food/venues/pines").json()["rating"] == {"review_count": 1, "average_rating": 4.0}
    assert client.get("/api/v1/food/stations/pines--slice-at-pines/menu-items").json()["menu_status"] == "no_verified_menu_data"


def test_postgres_persists_participant_forecast_snapshots(postgres_client):
    client, factory = postgres_client
    raw_invite, _ = _create_invite(factory)
    participant_id, csrf = _authenticate(client, raw_invite)
    today = pilot_today_provider()
    app.dependency_overrides[pilot_today_provider] = lambda: today
    assert client.post(
        "/api/v1/pilot/balance-checkins",
        json={
            "effective_date": (today - timedelta(days=1)).isoformat(),
            "dining_dollars_cents": 5000,
            "triton_cash_cents": 1000,
        },
        headers={"X-CSRF-Token": csrf},
    ).status_code == 200

    created = client.post(
        "/api/v1/pilot/forecasts",
        json={
            "end_date": (today + timedelta(days=3)).isoformat(),
            "habits": [{"name": "meal", "frequency": "1", "price_cents": 500, "eligible_accounts": ["dining_dollars"]}],
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 200
    body = created.json()
    # Saved forecasts start from the latest saved wallet balances, without ledger entries.
    assert body["inputs"]["starting_balances"] == {"dining_dollars_cents": 5000, "triton_cash_cents": 1000}
    assert client.get("/api/v1/pilot/forecasts").json()["forecasts"][0]["id"] == body["id"]
    trajectory = client.get(f"/api/v1/pilot/forecasts/{body['id']}/trajectory")
    assert trajectory.status_code == 200
    # From the as-of date (yesterday) through the end date.
    assert len(trajectory.json()["points"]) == 5
    with factory() as session:
        snapshot = session.get(ForecastSnapshot, body["id"])
        assert snapshot.participant_id == participant_id
        assert snapshot.request_json == body["inputs"]
        assert snapshot.response_json == body["forecast"]


def _cleanup_concurrent_redemption(factory: sessionmaker[Session], invite_id: str) -> None:
    """Delete only records linked to the explicitly registered synthetic invite."""
    with factory.begin() as session:
        invite = session.get(InviteToken, invite_id)
        participant_id = invite.participant_id if invite is not None else None
        if participant_id is not None:
            session.execute(delete(ParticipantSession).where(ParticipantSession.participant_id == participant_id))
            session.execute(delete(ConsentEvent).where(ConsentEvent.participant_id == participant_id))
            session.execute(delete(Consent).where(Consent.participant_id == participant_id))
            session.execute(delete(BalanceCheckin).where(BalanceCheckin.participant_id == participant_id))
            session.execute(
                delete(ParticipantBalanceThreshold).where(
                    ParticipantBalanceThreshold.participant_id == participant_id
                )
            )
            session.execute(delete(LedgerEntry).where(LedgerEntry.participant_id == participant_id))
            session.execute(
                delete(ZeroSpendingConfirmation).where(
                    ZeroSpendingConfirmation.participant_id == participant_id
                )
            )
            session.execute(delete(ForecastSnapshot).where(ForecastSnapshot.participant_id == participant_id))
            session.execute(delete(UserAccount).where(UserAccount.participant_id == participant_id))
        session.execute(delete(InviteToken).where(InviteToken.id == invite_id))
        if participant_id is not None:
            session.execute(delete(Participant).where(Participant.id == participant_id))


def test_postgres_redeems_one_invite_once_under_concurrency(postgres_concurrent_context):
    engine, factory = postgres_concurrent_context
    invite_id = None

    def redeem() -> int:
        with TestClient(app) as client:
            return client.post("/api/v1/auth/redeem", json={"token": raw_invite}).status_code

    try:
        raw_invite, invite_id = _create_invite(factory)
        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(lambda _: redeem(), range(2)))
        assert sorted(statuses) == [200, 400]
        with factory() as session:
            invite = session.get(InviteToken, invite_id)
            assert invite is not None and invite.participant_id is not None
            assert session.scalar(
                select(func.count())
                .select_from(ParticipantSession)
                .where(ParticipantSession.participant_id == invite.participant_id)
            ) == 1
    finally:
        cleanup_error = None
        try:
            if invite_id is not None:
                _cleanup_concurrent_redemption(factory, invite_id)
        except BaseException as error:
            cleanup_error = error
        try:
            _assert_migrated_and_empty(engine)
        except BaseException as state_error:
            if cleanup_error is not None:
                raise RuntimeError(
                    "concurrent redemption cleanup failed and the final database-state check failed"
                ) from cleanup_error
            raise state_error
        if cleanup_error is not None:
            raise RuntimeError("concurrent redemption cleanup failed") from cleanup_error
