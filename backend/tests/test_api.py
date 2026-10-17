from datetime import date
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.dependencies import today_provider
from backend.app.main import app


TODAY = date(2026, 10, 16)
client = TestClient(app)


@pytest.fixture(autouse=True)
def fixed_today():
    app.dependency_overrides[today_provider] = lambda: TODAY
    yield
    app.dependency_overrides.clear()


def payload(**overrides):
    value = {
        "start_date": "2026-10-16",
        "end_date": "2026-10-18",
        "dining_dollars_cents": 300,
        "triton_cash_cents": 200,
        "habits": [
            {
                "name": "dining meal",
                "frequency": "1",
                "price_cents": 75,
                "eligible_accounts": ["dining_dollars"],
            },
            {
                "name": "cash meal",
                "frequency": "1",
                "price_cents": 50,
                "eligible_accounts": ["triton_cash"],
            },
        ],
    }
    value.update(overrides)
    return value


def post(**overrides):
    return client.post("/api/v1/forecasts", json=payload(**overrides))


def test_successful_response_has_complete_structure_and_fixed_today():
    response = post()

    assert response.status_code == 200
    body = response.json()
    assert body["scenario"] == "expected"
    assert body["multiplier"] == "1"
    assert [day["date"] for day in body["days"]] == [
        "2026-10-16",
        "2026-10-17",
        "2026-10-18",
    ]
    assert body["days"][0]["remaining_balances"] == {
        "dining_dollars_cents": 225,
        "triton_cash_cents": 150,
    }
    assert body["projected_balances"] == {
        "dining_dollars_cents": 75,
        "triton_cash_cents": 50,
    }
    assert body["total_unfunded_cents"] == 0
    assert body["funds_last"] is True
    assert "daily_wallet_runway_caps" in body["limits"]
    assert "weekly_wallet_runway_caps" in body["limits"]


@pytest.mark.parametrize(
    "scenario,expected_cents",
    [("frugal", 60), ("higher", 90)],
)
def test_explicit_scenarios_are_forwarded(scenario, expected_cents):
    response = post(
        scenario=scenario,
        habits=[
            {
                "name": "meal",
                "frequency": "1",
                "price_cents": 75,
                "eligible_accounts": ["dining_dollars"],
            }
        ],
        end_date="2026-10-16",
    )

    assert response.status_code == 200
    assert response.json()["days"][0]["expected_spending_cents"] == expected_cents


@pytest.mark.parametrize(
    "change",
    [
        {"start_date": "2026-10-19"},
        {"end_date": "2026-10-15"},
        {"start_date": "2026-10-18", "end_date": "2026-10-17"},
        {"dining_dollars_cents": True},
        {"triton_cash_cents": 1.5},
        {"dining_dollars_cents": -1},
        {"habits": [{"name": "meal", "frequency": "0.5", "price_cents": 10, "eligible_accounts": ["dining_dollars"]}]},
        {"habits": [{"name": "meal", "frequency": "1/0", "price_cents": 10, "eligible_accounts": ["dining_dollars"]}]},
        {"habits": [{"name": "meal", "frequency": "1", "price_cents": 10, "eligible_accounts": []}]},
        {"habits": [{"name": "meal", "frequency": "1", "price_cents": 10, "eligible_accounts": ["dining_dollars", "dining_dollars"]}]},
        {"today": "2026-10-16"},
    ],
)
def test_invalid_inputs_return_422(change):
    assert post(**change).status_code == 422


def test_insufficient_funds_and_wallet_continuity_are_reported():
    response = post(
        dining_dollars_cents=100,
        triton_cash_cents=50,
        habits=[
            {
                "name": "dining meal",
                "frequency": "1",
                "price_cents": 75,
                "eligible_accounts": ["dining_dollars"],
            },
            {
                "name": "cash meal",
                "frequency": "1",
                "price_cents": 75,
                "eligible_accounts": ["triton_cash"],
            },
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["funds_last"] is False
    assert body["total_unfunded_cents"] == 300
    previous = {"dining_dollars_cents": 100, "triton_cash_cents": 50}
    for day in body["days"]:
        current = day["remaining_balances"]
        assert previous["dining_dollars_cents"] - current["dining_dollars_cents"] == day["paid_dining_dollars_cents"]
        assert previous["triton_cash_cents"] - current["triton_cash_cents"] == day["paid_triton_cash_cents"]
        previous = current


def test_cors_allows_local_frontend_and_rejects_unapproved_origin():
    allowed = client.options(
        "/api/v1/forecasts",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    rejected = client.options(
        "/api/v1/forecasts",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in rejected.headers


def test_forecast_core_is_called_once_per_successful_request():
    with patch("backend.app.main.forecast", wraps=__import__(
        "tritonspend.core.forecast", fromlist=["forecast"]
    ).forecast) as forecast_spy:
        response = post()

    assert response.status_code == 200
    forecast_spy.assert_called_once()
