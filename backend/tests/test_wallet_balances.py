from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.dependencies import pilot_today_provider
from backend.app.main import app
from backend.app.models import BalanceCheckin, LedgerEntry
from backend.tests.test_accounts import PASSWORD, accept_consent, csrf, factory, login, signup  # noqa: F401

TODAY = pilot_today_provider()
MEAL = {"name": "dining meal", "frequency": "1", "price_cents": 500, "eligible_accounts": ["dining_dollars"]}


@pytest.fixture
def student(factory):  # noqa: F811
    app.dependency_overrides[pilot_today_provider] = lambda: TODAY
    client = TestClient(app)
    assert signup(client).status_code == 201
    return client, accept_consent(client), factory


def _save_wallet(client, token, days_ago=0, dining=12_345, cash=6_789):
    return client.post("/api/v1/pilot/wallet", json={
        "effective_date": (TODAY - timedelta(days=days_ago)).isoformat(),
        "dining_dollars_cents": dining,
        "triton_cash_cents": cash,
    }, headers={"X-CSRF-Token": token})


def _wallet(client):
    response = client.get("/api/v1/pilot/wallet")
    assert response.status_code == 200, response.text
    return response.json()


def _count(factory, model):  # noqa: F811
    with factory() as session:
        return session.scalar(select(func.count()).select_from(model))


def test_first_time_student_has_no_wallet_and_can_save_one_without_ledger_entries(student):
    client, token, factory = student  # noqa: F811

    empty = _wallet(client)
    assert empty == {
        "latest": None, "history": [], "days_since_update": None, "stale": False,
        "stale_after_days": 14, "thresholds": None, "warnings": None,
    }

    saved = _save_wallet(client, token)
    assert saved.status_code == 200, saved.text

    wallet = _wallet(client)
    assert wallet["latest"]["id"] == saved.json()["id"]
    assert wallet["latest"]["effective_date"] == TODAY.isoformat()
    assert (wallet["latest"]["dining_dollars_cents"], wallet["latest"]["triton_cash_cents"]) == (12_345, 6_789)
    assert wallet["days_since_update"] == 0 and wallet["stale"] is False
    assert _count(factory, LedgerEntry) == 0
    forecast = client.post("/api/v1/pilot/forecasts", json={
        "end_date": (TODAY + timedelta(days=2)).isoformat(), "habits": [MEAL],
    }, headers={"X-CSRF-Token": token})
    assert forecast.status_code == 200, forecast.text
    assert forecast.json()["inputs"]["starting_balances"] == {"dining_dollars_cents": 12_345, "triton_cash_cents": 6_789}


def test_wallet_thresholds_and_forecasts_persist_after_logout_and_login(student):
    client, token, _ = student
    assert _save_wallet(client, token).status_code == 200
    assert client.post("/api/v1/pilot/balance-thresholds", json={
        "dining_dollars_cents": 20_000, "triton_cash_cents": 1_000,
    }, headers={"X-CSRF-Token": token}).status_code == 200
    created = client.post("/api/v1/pilot/forecasts", json={
        "end_date": (TODAY + timedelta(days=3)).isoformat(), "habits": [MEAL],
    }, headers={"X-CSRF-Token": token}).json()
    before = _wallet(client)
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": token}).status_code == 200
    assert client.get("/api/v1/pilot/wallet").status_code == 401

    returning = TestClient(app)
    assert login(returning).status_code == 200

    after = _wallet(returning)
    assert after == before
    assert after["thresholds"] == {"dining_dollars_cents": 20_000, "triton_cash_cents": 1_000}
    assert after["warnings"]["dining_dollars"]["warning"] is True  # 123.45 is at or below 200.00
    assert after["warnings"]["triton_cash"]["warning"] is False
    history = returning.get("/api/v1/pilot/forecasts").json()["forecasts"]
    assert [item["id"] for item in history] == [created["id"]]
    assert returning.get(f"/api/v1/pilot/forecasts/{created['id']}").json() == created


def test_returning_student_updates_balances_and_history_is_kept(student):
    client, token, factory = student  # noqa: F811
    first = _save_wallet(client, token, days_ago=5, dining=30_000, cash=4_000).json()
    second = _save_wallet(client, token, days_ago=0, dining=25_000, cash=3_500).json()
    # A save for an earlier day is kept as history but does not replace newer balances.
    earlier = _save_wallet(client, token, days_ago=9, dining=40_000, cash=5_000).json()

    wallet = _wallet(client)

    assert wallet["latest"]["id"] == second["id"]
    assert [item["id"] for item in wallet["history"]] == [second["id"], first["id"], earlier["id"]]
    assert _count(factory, BalanceCheckin) == 3


def test_same_day_update_replaces_the_latest_balance_and_keeps_the_old_one(student):
    client, token, _ = student
    morning = _save_wallet(client, token, dining=10_000).json()
    evening = _save_wallet(client, token, dining=9_000).json()

    wallet = _wallet(client)

    assert wallet["latest"]["id"] == evening["id"]
    assert {item["id"] for item in wallet["history"]} == {morning["id"], evening["id"]}


def test_threshold_updates_persist_and_change_warnings(student):
    client, token, _ = student
    _save_wallet(client, token)
    for dining, cash in [(0, 0), (50_000, 50_000)]:
        assert client.post("/api/v1/pilot/balance-thresholds", json={
            "dining_dollars_cents": dining, "triton_cash_cents": cash,
        }, headers={"X-CSRF-Token": token}).status_code == 200

    wallet = _wallet(client)

    assert wallet["thresholds"] == {"dining_dollars_cents": 50_000, "triton_cash_cents": 50_000}
    assert wallet["warnings"]["dining_dollars"]["warning"] is True
    assert wallet["warnings"]["triton_cash"]["warning"] is True


def test_stale_wallets_are_flagged_but_not_changed(student):
    client, token, _ = student
    _save_wallet(client, token, days_ago=15)

    wallet = _wallet(client)

    assert wallet["days_since_update"] == 15 and wallet["stale"] is True
    assert wallet["latest"]["dining_dollars_cents"] == 12_345


def test_wallet_saves_require_csrf_consent_and_valid_values(student):
    client, token, factory = student  # noqa: F811
    payload = {"effective_date": TODAY.isoformat(), "dining_dollars_cents": 1, "triton_cash_cents": 1}

    assert TestClient(app).post("/api/v1/pilot/wallet", json=payload).status_code == 401
    assert client.post("/api/v1/pilot/wallet", json=payload).status_code == 403
    future = _save_wallet(client, token, days_ago=-2)
    assert future.status_code == 422 and "future" in future.json()["detail"]
    assert client.post("/api/v1/pilot/wallet", json={**payload, "dining_dollars_cents": -1},
                       headers={"X-CSRF-Token": token}).status_code == 422
    assert client.post("/api/v1/auth/consent/withdraw", json={}, headers={"X-CSRF-Token": token}).status_code == 200
    assert client.post("/api/v1/pilot/wallet", json=payload, headers={"X-CSRF-Token": token}).status_code == 403
    assert _count(factory, BalanceCheckin) == 0


def test_wallets_are_isolated_between_accounts(student):
    alice, alice_token, _ = student
    _save_wallet(alice, alice_token, dining=11_111, cash=2_222)
    bob = TestClient(app)
    assert signup(bob, email="bob@example.com", password="bob password 22").status_code == 201
    accept_consent(bob)

    assert _wallet(bob)["latest"] is None
    assert _wallet(alice)["latest"]["dining_dollars_cents"] == 11_111
    assert TestClient(app).get("/api/v1/pilot/wallet").status_code == 401


def test_wallet_saves_are_tagged_and_the_older_check_in_endpoint_still_works(student):
    client, token, factory = student  # noqa: F811
    wallet = _save_wallet(client, token).json()
    legacy = client.post("/api/v1/pilot/balance-checkins", json={
        "effective_date": TODAY.isoformat(), "dining_dollars_cents": 1, "triton_cash_cents": 1,
    }, headers={"X-CSRF-Token": token})
    assert legacy.status_code == 200

    assert wallet["source"] == "wallet"
    assert legacy.json()["source"] == "manual"
    extra = client.post("/api/v1/pilot/wallet", json={
        "effective_date": TODAY.isoformat(), "dining_dollars_cents": 1, "triton_cash_cents": 1, "source": "manual",
    }, headers={"X-CSRF-Token": token})
    assert extra.status_code == 422
