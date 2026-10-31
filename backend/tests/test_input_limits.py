"""API input limits (README "API input limits"), shared by anonymous and signed-in endpoints.

Every rejected value must be a clean 422, never a 500, and must save nothing.
"""

from datetime import timedelta
from fractions import Fraction

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.dependencies import today_provider
from backend.app.main import app
from backend.app.mapping import parse_frequency
from backend.app.models import BalanceCheckin, LedgerEntry, ParticipantBalanceThreshold
from backend.app.schemas import (
    MAX_BALANCE_CENTS,
    MAX_FORECAST_DAYS,
    MAX_FREQUENCY_DENOMINATOR,
    MAX_FREQUENCY_LENGTH,
    MAX_FREQUENCY_PER_DAY,
    MAX_HABITS,
    MAX_PRICE_CENTS,
    frequency_error,
)
from backend.tests.test_api import TODAY as ANONYMOUS_TODAY, payload
from backend.tests.test_participant_forecast import TODAY, _forecast, _save_wallet, _snapshot_count, pilot  # noqa: F401

# Never let a server error surface as an exception: the assertion is on the status code.
anonymous = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def fixed_anonymous_today():
    # test_api's payload dates assume its fixed "today".
    app.dependency_overrides[today_provider] = lambda: ANONYMOUS_TODAY
    yield
    app.dependency_overrides.pop(today_provider, None)


def habit(**overrides):
    return {"name": "meal", "frequency": "1", "price_cents": 10, "eligible_accounts": ["dining_dollars"], **overrides}


def post_anonymous(**overrides):
    return anonymous.post("/api/v1/forecasts", json=payload(**overrides))


def test_limits_have_the_documented_values():
    assert (MAX_FORECAST_DAYS, MAX_HABITS, MAX_FREQUENCY_LENGTH, MAX_FREQUENCY_DENOMINATOR, MAX_FREQUENCY_PER_DAY) == (366, 50, 9, 365, 24)
    assert (MAX_BALANCE_CENTS, MAX_PRICE_CENTS) == (10_000_000, 100_000)


# --- Shared frequency rule -------------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    ("0", Fraction(0)), ("1", Fraction(1)), ("1/2", Fraction(1, 2)), ("24", Fraction(24)),
    ("1/365", Fraction(1, 365)), ("8760/365", Fraction(24)), ("0/7", Fraction(0)), ("000000001", Fraction(1)),
])
def test_valid_frequencies_parse_exactly(value, expected):
    assert frequency_error(value) is None
    assert parse_frequency(value) == expected


@pytest.mark.parametrize("value, reason", [
    ("25", "per day"),
    ("8761/365", "per day"),
    ("1/366", "denominator"),
    ("1/0", "denominator"),
    ("0/0", "denominator"),
    ("0000000001", "characters"),  # 10 characters
    ("9" * 100_000, "characters"),
    ("1/" + "9" * 100_000, "characters"),
    ("²", "fraction"), ("1/²", "fraction"), ("١", "fraction"), ("١/٢", "fraction"), ("１", "fraction"),  # Unicode digits
    ("", "fraction"), ("/", "fraction"), ("1/", "fraction"), ("/2", "fraction"), ("1/2/3", "fraction"),
    ("0.5", "fraction"), ("-1", "fraction"), ("+1", "fraction"), (" 1", "fraction"), ("1 /2", "fraction"),
])
def test_invalid_frequencies_are_rejected_with_a_reason(value, reason):
    error = frequency_error(value)
    assert error is not None and reason in error
    with pytest.raises(ValueError):
        parse_frequency(value)


# --- Anonymous forecasts ---------------------------------------------------------------------

@pytest.mark.parametrize("change", [
    {"start_date": "2026-10-16", "end_date": "2027-10-16"},  # 366 inclusive days
    {"dining_dollars_cents": MAX_BALANCE_CENTS, "triton_cash_cents": MAX_BALANCE_CENTS},
    {"dining_dollars_cents": 0, "triton_cash_cents": 0},
    {"habits": [habit(price_cents=MAX_PRICE_CENTS)]},
    {"habits": [habit(price_cents=0)]},
    {"habits": [habit(frequency="24")]},
    {"habits": [habit(frequency="1/365")]},
    {"habits": [habit(frequency="0")]},
    {"habits": [habit() for _ in range(MAX_HABITS)]},
])
def test_anonymous_inputs_at_the_limits_are_accepted(change):
    assert post_anonymous(**change).status_code == 200


@pytest.mark.parametrize("change", [
    {"start_date": "2026-10-16", "end_date": "2027-10-17"},  # 367 inclusive days
    {"start_date": "2026-01-01", "end_date": "9999-12-31"},  # used to be a 500
    {"dining_dollars_cents": MAX_BALANCE_CENTS + 1},
    {"triton_cash_cents": MAX_BALANCE_CENTS + 1},
    {"dining_dollars_cents": 2**63},
    {"habits": [habit(price_cents=MAX_PRICE_CENTS + 1)]},
    {"habits": [habit(frequency="25")]},
    {"habits": [habit(frequency="1/366")]},
    {"habits": [habit(frequency="1/0")]},
    {"habits": [habit(frequency="9" * 100_000)]},
    {"habits": [habit(frequency="1/" + "9" * 100_000)]},
    {"habits": [habit(frequency="")]},
    {"habits": [habit(frequency="1 /2")]},
    {"habits": [habit() for _ in range(MAX_HABITS + 1)]},
])
def test_anonymous_inputs_beyond_the_limits_return_422(change):
    response = post_anonymous(**change)
    assert response.status_code == 422, response.text


@pytest.mark.parametrize("frequency", ["²", "1/²", "١", "١/٢", "１"])
def test_unicode_digit_frequencies_return_422_not_500(frequency):
    # "²" passes str.isdigit() but int() rejects it; "١" is accepted by int(). Both are refused.
    assert post_anonymous(habits=[habit(frequency=frequency)]).status_code == 422


def test_a_mapping_value_error_is_a_client_error(monkeypatch):
    def reject(*_args, **_kwargs):
        raise ValueError("bad client value")

    monkeypatch.setattr("backend.app.main.to_core_input", reject)
    response = post_anonymous()
    assert response.status_code == 422 and response.json()["detail"] == "bad client value"


# --- Signed-in forecasts ---------------------------------------------------------------------

@pytest.mark.parametrize("change", [
    {"habits": [habit(price_cents=MAX_PRICE_CENTS)]},
    {"habits": [habit(frequency="24")]},
    {"habits": [habit(frequency="1/365")]},
    {"habits": [habit(frequency="0", price_cents=0)]},
    {"habits": [habit() for _ in range(MAX_HABITS)]},
    {"days": MAX_FORECAST_DAYS - 1},  # starts today, so 366 inclusive days
])
def test_signed_in_inputs_at_the_limits_are_accepted(pilot, change):  # noqa: F811
    client, factory, csrf = pilot
    _save_wallet(client, csrf, dining=MAX_BALANCE_CENTS, cash=MAX_BALANCE_CENTS)

    response = _forecast(client, csrf, **change)

    assert response.status_code == 200, response.text
    assert _snapshot_count(factory) == 1


@pytest.mark.parametrize("change", [
    {"days": MAX_FORECAST_DAYS},  # 367 inclusive days
    {"end_date": "9999-12-31"},
    {"habits": [habit(price_cents=MAX_PRICE_CENTS + 1)]},
    {"habits": [habit(frequency="25")]},
    {"habits": [habit(frequency="1/366")]},
    {"habits": [habit(frequency="1/0")]},
    {"habits": [habit(frequency="9" * 100_000)]},
    {"habits": [habit(frequency="١")]},
    {"habits": [habit(frequency="²")]},
    {"habits": [habit() for _ in range(MAX_HABITS + 1)]},
])
def test_signed_in_inputs_beyond_the_limits_return_422_and_save_nothing(pilot, change):  # noqa: F811
    client, factory, csrf = pilot
    _save_wallet(client, csrf)

    response = _forecast(client, csrf, **change)

    assert response.status_code == 422, response.text
    assert _snapshot_count(factory) == 0


# --- Saved balances, warning amounts, older check-ins and ledger entries ----------------------

def _count(factory, model):
    with factory() as session:
        return session.scalar(select(func.count()).select_from(model))


def _send(client, csrf, path, body):
    return client.post(path, json=body, headers={"X-CSRF-Token": csrf})


@pytest.mark.parametrize("path, model", [
    ("/api/v1/pilot/wallet", BalanceCheckin),
    ("/api/v1/pilot/balance-checkins", BalanceCheckin),
    ("/api/v1/pilot/balance-thresholds", ParticipantBalanceThreshold),
])
@pytest.mark.parametrize("field", ["dining_dollars_cents", "triton_cash_cents"])
def test_balances_and_warning_amounts_are_capped_at_100000_dollars(pilot, path, model, field):  # noqa: F811
    client, factory, csrf = pilot
    base = {"dining_dollars_cents": 1, "triton_cash_cents": 1}
    if path != "/api/v1/pilot/balance-thresholds":
        base["effective_date"] = TODAY.isoformat()

    for value in (MAX_BALANCE_CENTS + 1, 2**31, 2**63):
        response = _send(client, csrf, path, {**base, field: value})
        assert response.status_code == 422, response.text
        assert any(item["loc"][-1] == field for item in response.json()["detail"])
    assert _count(factory, model) == 0

    assert _send(client, csrf, path, {**base, field: MAX_BALANCE_CENTS}).status_code == 200
    assert _count(factory, model) == 1


def test_ledger_amounts_are_capped_too(pilot):  # noqa: F811
    client, factory, csrf = pilot
    entry = {"occurred_on": TODAY.isoformat(), "account": "dining_dollars", "entry_type": "spending"}

    assert _send(client, csrf, "/api/v1/pilot/ledger-entries", {**entry, "amount_cents": MAX_BALANCE_CENTS + 1}).status_code == 422
    assert _count(factory, LedgerEntry) == 0
    assert _send(client, csrf, "/api/v1/pilot/ledger-entries", {**entry, "amount_cents": MAX_BALANCE_CENTS}).status_code == 200
