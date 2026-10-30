"""Database-free tests for the PostgreSQL integration-test safety gates.

These never open a database connection: the URL gate is driven by environment
variables, and the pre-write checks run against a scripted fake connection.
"""

from __future__ import annotations

import re
from contextlib import contextmanager

import pytest

from backend.tests.test_postgres_integration import (
    APPLICATION_MODELS,
    EXPECTED_DATABASE_COMMENT,
    EXPECTED_REVISION,
    _assert_migrated_and_empty,
    _integration_url,
    _settings,
)


VALID_URL = "postgresql+psycopg://tritonspend:not-a-real-password@127.0.0.1:5433/tritonspend_test"


@pytest.fixture
def integration_env(monkeypatch):
    monkeypatch.setenv("TRITONSPEND_POSTGRES_INTEGRATION", "1")
    monkeypatch.setenv("TRITONSPEND_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", VALID_URL)
    return monkeypatch


@pytest.mark.parametrize("flag", [None, "", "0", "true", "yes"])
def test_url_gate_skips_unless_flag_is_exactly_1(integration_env, flag):
    if flag is None:
        integration_env.delenv("TRITONSPEND_POSTGRES_INTEGRATION")
    else:
        integration_env.setenv("TRITONSPEND_POSTGRES_INTEGRATION", flag)
    with pytest.raises(pytest.skip.Exception):
        _integration_url()


@pytest.mark.parametrize("environment", [None, "local", "production", "TEST"])
def test_url_gate_requires_test_environment(integration_env, environment):
    if environment is None:
        integration_env.delenv("TRITONSPEND_ENV")
    else:
        integration_env.setenv("TRITONSPEND_ENV", environment)
    with pytest.raises(pytest.fail.Exception, match="TRITONSPEND_ENV=test"):
        _integration_url()


def test_url_gate_requires_database_url(integration_env):
    integration_env.delenv("DATABASE_URL")
    with pytest.raises(pytest.fail.Exception, match="DATABASE_URL"):
        _integration_url()


@pytest.mark.parametrize(
    "url",
    [
        "sqlite:///./tritonspend-test.db",
        "postgresql://tritonspend:pw@127.0.0.1:5433/tritonspend_test",
        "postgresql+psycopg2://tritonspend:pw@127.0.0.1:5433/tritonspend_test",
        "postgresql+psycopg://postgres:pw@127.0.0.1:5433/tritonspend_test",
        "postgresql+psycopg://tritonspend:pw@localhost:5433/tritonspend_test",
        "postgresql+psycopg://tritonspend:pw@db.example.com:5433/tritonspend_test",
        "postgresql+psycopg://tritonspend:pw@127.0.0.1:5432/tritonspend_test",
        "postgresql+psycopg://tritonspend:pw@127.0.0.1/tritonspend_test",
        "postgresql+psycopg://tritonspend:pw@127.0.0.1:5433/tritonspend",
        "postgresql+psycopg://tritonspend:pw@127.0.0.1:5433/tritonspend_test?sslmode=disable",
        "postgresql+psycopg://tritonspend:pw@127.0.0.1:5433/tritonspend_test?host=db.example.com",
    ],
)
def test_url_gate_rejects_every_other_target(integration_env, url):
    integration_env.setenv("DATABASE_URL", url)
    with pytest.raises(pytest.fail.Exception, match="only permit"):
        _integration_url()


def test_url_gate_accepts_only_the_disposable_target_and_settings_use_it(integration_env):
    url = _integration_url()

    assert (url.host, url.port, url.database, url.username) == ("127.0.0.1", 5433, "tritonspend_test", "tritonspend")
    assert _settings(url).database_url == VALID_URL


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def one(self):
        assert len(self._rows) == 1
        return self._rows[0]

    def scalars(self):
        return _Result([(row[0],) for row in self._rows])

    def all(self):
        return [row[0] for row in self._rows]


class _FakeConnection:
    """Answers the read-only pre-write queries from a scripted database state."""

    def __init__(self, *, identity, comment, has_alembic, revisions, counts):
        self.identity = identity
        self.comment = comment
        self.has_alembic = has_alembic
        self.revisions = revisions
        self.counts = counts
        self.statements: list[str] = []

    def execute(self, statement):
        sql = str(statement)
        self.statements.append(sql)
        if "current_database(), current_user" in sql:
            return _Result([self.identity])
        if "FROM alembic_version" in sql:
            assert self.has_alembic, "queried alembic_version after it was reported missing"
            return _Result([(revision,) for revision in self.revisions])
        raise AssertionError(f"unexpected execute: {sql}")

    def scalar(self, statement):
        sql = str(statement)
        self.statements.append(sql)
        if "shobj_description" in sql:
            return self.comment
        if "to_regclass('alembic_version')" in sql:
            return self.has_alembic
        if "count(" in sql:
            return self.counts.get(re.search(r"FROM (\w+)", sql).group(1), 0)
        raise AssertionError(f"unexpected scalar: {sql}")


class _FakeEngine:
    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def connect(self):
        yield self.connection


def _state(**overrides):
    values = {
        "identity": ("tritonspend_test", "tritonspend"),
        "comment": EXPECTED_DATABASE_COMMENT,
        "has_alembic": True,
        "revisions": [EXPECTED_REVISION],
        "counts": {},
    }
    values.update(overrides)
    return _FakeConnection(**values)


def test_pre_write_checks_pass_for_marked_migrated_empty_database():
    connection = _state()

    _assert_migrated_and_empty(_FakeEngine(connection))

    assert "current_database()" in connection.statements[0]
    assert "shobj_description" in connection.statements[1]
    assert sum("count(" in sql for sql in connection.statements) == len(APPLICATION_MODELS)


@pytest.mark.parametrize("identity", [("postgres", "tritonspend"), ("tritonspend_test", "postgres")])
def test_pre_write_checks_reject_wrong_server_identity_before_anything_else(identity):
    connection = _state(identity=identity)

    with pytest.raises(pytest.fail.Exception, match="identity"):
        _assert_migrated_and_empty(_FakeEngine(connection))
    assert len(connection.statements) == 1


@pytest.mark.parametrize(
    "comment",
    [None, "", "tritonspend-disposable-test ", "TRITONSPEND-DISPOSABLE-TEST", "production"],
)
def test_pre_write_checks_require_the_exact_disposable_marker(comment):
    connection = _state(comment=comment)

    with pytest.raises(pytest.fail.Exception, match="disposable-test marker"):
        _assert_migrated_and_empty(_FakeEngine(connection))
    assert not any("alembic_version" in sql or "count(" in sql for sql in connection.statements)


def test_pre_write_checks_report_missing_alembic_version_clearly():
    connection = _state(has_alembic=False)

    with pytest.raises(pytest.fail.Exception, match="alembic_version table is missing"):
        _assert_migrated_and_empty(_FakeEngine(connection))
    assert not any("SELECT version_num" in sql for sql in connection.statements)


@pytest.mark.parametrize(
    "revisions",
    [[], ["20261017_0002"], [EXPECTED_REVISION, "20261020_0004"]],
)
def test_pre_write_checks_require_exactly_the_expected_revision(revisions):
    with pytest.raises(pytest.fail.Exception, match="expected Alembic revision"):
        _assert_migrated_and_empty(_FakeEngine(_state(revisions=revisions)))


def test_pre_write_checks_refuse_databases_with_application_rows():
    connection = _state(counts={"ledger_entries": 3})

    with pytest.raises(pytest.fail.Exception, match="ledger_entries"):
        _assert_migrated_and_empty(_FakeEngine(connection))
