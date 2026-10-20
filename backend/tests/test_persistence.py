from datetime import date, datetime, timezone

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app.config import ConfigurationError, load_settings
from backend.app import db
from backend.app.db import Base
from backend.app.models import Account, EntryType, LedgerEntry, Participant, ZeroSpendingConfirmation


def test_configuration_requires_hosted_database_url():
    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        load_settings({"TRITONSPEND_ENV": "production"})


@pytest.mark.parametrize("environ", [{}, {"TRITONSPEND_ENV": ""}, {"TRITONSPEND_ENV": "staging"}])
def test_configuration_requires_explicit_known_environment(environ):
    with pytest.raises(ConfigurationError, match="TRITONSPEND_ENV"):
        load_settings(environ)


def test_configuration_allows_local_sqlite_and_rejects_hosted_sqlite():
    assert load_settings({"TRITONSPEND_ENV": "local"}).database_url.startswith("sqlite")
    with pytest.raises(ConfigurationError, match="SQLite"):
        load_settings({"TRITONSPEND_ENV": "production", "DATABASE_URL": "sqlite:///local.db"})


@pytest.mark.parametrize(
    "environ, message",
    [
        ({"TRITONSPEND_ENV": "production", "DATABASE_URL": "postgresql://"}, "host"),
        ({"TRITONSPEND_ENV": "production", "DATABASE_URL": "mysql://db/app"}, "PostgreSQL"),
        ({"TRITONSPEND_ENV": "local", "DATABASE_URL": "redis://localhost/db"}, "SQLite"),
    ],
)
def test_configuration_rejects_invalid_database_urls(environ, message):
    with pytest.raises(ConfigurationError, match=message):
        load_settings(environ)


def test_configuration_accepts_supported_postgresql_urls():
    settings = load_settings(
        {
            "TRITONSPEND_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://user:password@db.example/app",
            "TRITONSPEND_CONSENT_VERSION": "v1",
            "TRITONSPEND_CONSENT_DOCUMENT_URL": "https://example.test/consent/v1",
            "TRITONSPEND_SESSION_SECRET": "s" * 32,
            "TRITONSPEND_CSRF_SECRET": "c" * 32,
            "TRITONSPEND_CORS_ORIGINS": "https://app.example",
            "TRITONSPEND_PUBLIC_ORIGIN": "https://app.example",
        }
    )
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_production_rejects_missing_or_weak_secrets_and_insecure_origin():
    values = {
        "TRITONSPEND_ENV": "production",
        "DATABASE_URL": "postgresql+psycopg://user:password@db.example/app",
        "TRITONSPEND_CONSENT_VERSION": "v1",
        "TRITONSPEND_CONSENT_DOCUMENT_URL": "https://example.test/consent/v1",
        "TRITONSPEND_SESSION_SECRET": "short",
        "TRITONSPEND_CSRF_SECRET": "another-short",
        "TRITONSPEND_CORS_ORIGINS": "https://app.example",
        "TRITONSPEND_PUBLIC_ORIGIN": "https://app.example",
    }
    with pytest.raises(ConfigurationError, match="at least 32"):
        load_settings(values)
    values["TRITONSPEND_SESSION_SECRET"] = "s" * 32
    values["TRITONSPEND_CSRF_SECRET"] = "c" * 32
    values.pop("TRITONSPEND_CORS_ORIGINS")
    with pytest.raises(ConfigurationError, match="CORS"):
        load_settings(values)
    values["TRITONSPEND_CORS_ORIGINS"] = "https://app.example"
    values["TRITONSPEND_PUBLIC_ORIGIN"] = "http://app.example"
    with pytest.raises(ConfigurationError, match="HTTPS"):
        load_settings(values)


def test_production_rejects_http_consent_document_url():
    values = {
        "TRITONSPEND_ENV": "production",
        "DATABASE_URL": "postgresql+psycopg://user:password@db.example/app",
        "TRITONSPEND_CONSENT_VERSION": "v1",
        "TRITONSPEND_CONSENT_DOCUMENT_URL": "http://example.test/consent/v1",
        "TRITONSPEND_SESSION_SECRET": "s" * 32,
        "TRITONSPEND_CSRF_SECRET": "c" * 32,
        "TRITONSPEND_CORS_ORIGINS": "https://app.example",
        "TRITONSPEND_PUBLIC_ORIGIN": "https://app.example",
    }
    with pytest.raises(ConfigurationError, match="absolute HTTPS URL"):
        load_settings(values)


def test_explicit_local_environment_allows_http_origin_and_sqlite():
    settings = load_settings(
        {
            "TRITONSPEND_ENV": "local",
            "DATABASE_URL": "sqlite:///local.db",
            "TRITONSPEND_CORS_ORIGINS": "http://localhost:3000",
        }
    )
    assert settings.database_url == "sqlite:///local.db"


def test_production_requires_explicit_cors_and_consent_configuration():
    base = {
        "TRITONSPEND_ENV": "production",
        "DATABASE_URL": "postgresql+psycopg://user:password@db.example/app",
        "TRITONSPEND_CONSENT_VERSION": "v1",
        "TRITONSPEND_CONSENT_DOCUMENT_URL": "https://example.test/consent/v1",
        "TRITONSPEND_SESSION_SECRET": "session-secret",
        "TRITONSPEND_CSRF_SECRET": "csrf-secret",
    }
    with pytest.raises(ConfigurationError, match="CORS"):
        load_settings(base)
    base["TRITONSPEND_CORS_ORIGINS"] = "http://app.example"
    with pytest.raises(ConfigurationError, match="HTTPS"):
        load_settings(base)


def test_metadata_initializes_all_m1_tables_with_columns_constraints_and_indexes():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    database = inspect(engine)
    expected_columns = {
        "participants": {"id", "created_at", "deleted_at", "timezone"},
        "invite_tokens": {
            "id", "token_hash", "created_at", "expires_at", "redeemed_at", "participant_id",
        },
        "consents": {
            "id", "participant_id", "consent_version", "consented_at", "withdrawn_at",
            "terms_version_hash",
        },
        "balance_checkins": {
            "id", "participant_id", "observed_at", "effective_date",
            "dining_dollars_cents", "triton_cash_cents", "source", "created_at",
        },
        "participant_balance_thresholds": {
            "id", "participant_id", "dining_dollars_cents", "triton_cash_cents",
            "created_at", "updated_at",
        },
        "ledger_entries": {
            "id", "participant_id", "occurred_on", "account", "entry_type",
            "amount_cents", "merchant_or_note", "created_at",
        },
        "zero_spending_confirmations": {
            "id", "participant_id", "day", "confirmed_at",
        },
        "forecast_snapshots": {
            "id", "participant_id", "created_at", "start_date", "end_date",
            "engine_version", "request_json", "response_json",
        },
        "consent_events": {
            "id", "participant_id", "event_type", "consent_version", "document_url",
            "document_version_hash", "occurred_at",
        },
        "participant_sessions": {
            "id", "participant_id", "session_token_hash", "csrf_token_hash",
            "created_at", "last_seen_at", "expires_at", "revoked_at",
        },
    }
    assert set(database.get_table_names()) == set(expected_columns)
    for table_name, columns in expected_columns.items():
        assert {column["name"] for column in database.get_columns(table_name)} == columns

    expected_foreign_keys = {
        "participants": [],
        "invite_tokens": [("participant_id", "participants", "id")],
        "consents": [("participant_id", "participants", "id")],
        "balance_checkins": [("participant_id", "participants", "id")],
        "participant_balance_thresholds": [("participant_id", "participants", "id")],
        "ledger_entries": [("participant_id", "participants", "id")],
        "zero_spending_confirmations": [("participant_id", "participants", "id")],
        "forecast_snapshots": [("participant_id", "participants", "id")],
        "consent_events": [("participant_id", "participants", "id")],
        "participant_sessions": [("participant_id", "participants", "id")],
    }
    for table_name, foreign_keys in expected_foreign_keys.items():
        assert [
            (key["constrained_columns"][0], key["referred_table"], key["referred_columns"][0])
            for key in database.get_foreign_keys(table_name)
        ] == foreign_keys

    assert {index["name"] for index in database.get_indexes("ledger_entries")} == {
        "ix_ledger_entries_participant_id", "ix_ledger_entries_occurred_on",
    }
    assert {check["name"] for check in database.get_check_constraints("ledger_entries")} == {
        "ck_ledger_amount_nonnegative", "ck_ledger_account_valid", "ck_ledger_entry_type_valid",
    }
    assert {
        constraint["name"]
        for constraint in database.get_unique_constraints("participant_balance_thresholds")
    } == {"uq_threshold_participant"}
    assert {
        check["name"] for check in database.get_check_constraints("participant_balance_thresholds")
    } == {
        "ck_threshold_dining_nonnegative",
        "ck_threshold_cash_nonnegative",
    }


def test_alembic_upgrade_and_downgrade_create_and_remove_schema(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"
    monkeypatch.setenv("TRITONSPEND_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    database = inspect(engine)
    assert "forecast_snapshots" in database.get_table_names()
    assert {
        "consent_events",
        "participant_sessions",
        "participant_balance_thresholds",
    } <= set(database.get_table_names())
    assert "ix_forecast_snapshots_start_date" in {
        index["name"] for index in database.get_indexes("forecast_snapshots")
    }
    command.downgrade(config, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]


def test_transaction_rolls_back_and_unique_confirmation_is_enforced():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    participant = Participant()
    with factory.begin() as session:
        session.add(participant)
    with pytest.raises(RuntimeError):
        with factory.begin() as session:
            session.add(
                ZeroSpendingConfirmation(
                    participant_id=participant.id,
                    day=date(2026, 10, 17),
                    confirmed_at=datetime.now(timezone.utc),
                )
            )
            raise RuntimeError("rollback")
    with factory() as session:
        assert session.scalar(select(ZeroSpendingConfirmation)) is None
        session.add(
            ZeroSpendingConfirmation(
                participant_id=participant.id,
                day=date(2026, 10, 17),
                confirmed_at=datetime.now(timezone.utc),
            )
        )
        session.commit()
        session.add(
            ZeroSpendingConfirmation(
                participant_id=participant.id,
                day=date(2026, 10, 17),
                confirmed_at=datetime.now(timezone.utc),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_request_session_rolls_back_on_exception(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db, "get_session_factory", lambda: factory)
    request_session = db.get_db()
    session = next(request_session)
    session.add(Participant())
    with pytest.raises(RuntimeError):
        request_session.throw(RuntimeError("request failed"))
    with factory() as verify:
        assert verify.scalar(select(Participant)) is None


def test_monetary_and_enum_checks_reject_invalid_values():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory.begin() as session:
        participant = Participant()
        session.add(participant)
        session.flush()
        session.add(
            LedgerEntry(
                participant_id=participant.id,
                occurred_on=date(2026, 10, 17),
                account=Account.dining_dollars,
                entry_type=EntryType.spending,
                amount_cents=1,
            )
        )
    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.execute(
                text(
                    "INSERT INTO ledger_entries "
                    "(id, participant_id, occurred_on, account, entry_type, amount_cents, created_at) "
                    "VALUES ('bad-money', :participant_id, :day, 'dining_dollars', "
                    "'spending', -1, :created_at)"
                ),
                {"participant_id": participant.id, "day": date(2026, 10, 17), "created_at": datetime.now(timezone.utc)},
            )
    with pytest.raises(IntegrityError):
        with factory.begin() as session:
            session.execute(
                text(
                    "INSERT INTO ledger_entries "
                    "(id, participant_id, occurred_on, account, entry_type, amount_cents, created_at) "
                    "VALUES ('bad-enum', :participant_id, :day, 'invalid', "
                    "'spending', 1, :created_at)"
                ),
                {"participant_id": participant.id, "day": date(2026, 10, 17), "created_at": datetime.now(timezone.utc)},
            )
