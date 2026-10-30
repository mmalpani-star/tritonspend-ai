"""Numerical tests for the personalized prediction model and its API."""

from datetime import date, datetime, timedelta, timezone
from fractions import Fraction

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.dependencies import pilot_today_provider
from backend.app.main import app
from backend.app.models import BalanceCheckin, ForecastSnapshot
from backend.app.personal_model import (
    build_prediction,
    fit_account,
    observations_from_checkins,
    path,
    weighted_quantile,
)
from backend.tests.test_accounts import accept_consent, factory, login, signup  # noqa: F401

TODAY = date(2026, 12, 1)
_ids = iter(range(10_000))


def checkin(day, dining, cash, source="wallet", hour=12, minute=0):
    return BalanceCheckin(
        id=f"c{next(_ids):05d}",
        participant_id="p",
        effective_date=day,
        observed_at=datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc),
        created_at=datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc),
        dining_dollars_cents=dining,
        triton_cash_cents=cash,
        source=source,
    )


def observations(*rows, today=TODAY):
    return observations_from_checkins([checkin(*row) for row in rows], today)


def account(prediction, name):
    return next(item for item in prediction["accounts"] if item["account"] == name)


def series(prediction, name, wallet):
    return [point[name][f"{wallet}_cents"] for point in prediction["points"]]


# 1. No history.
def test_no_observations_means_no_prediction():
    result = build_prediction([], TODAY, None, None)

    assert result["observation_count"] == 0 and result["points"] == [] and result["latest"] is None
    for item in result["accounts"]:
        assert item["confidence"] == "none" and item["daily_pace_cents"] is None and item["predicted_end_cents"] is None


# 2. One observation: a starting point, no learned pace.
def test_one_observation_sets_the_start_without_claiming_a_pace():
    result = build_prediction(observations((date(2026, 10, 30), 420_000, 45_000)), date(2026, 10, 30), None, None)

    dd = account(result, "dining_dollars")
    assert dd["confidence"] == "starting" and dd["daily_pace_cents"] is None and dd["latest_cents"] == 420_000
    assert all(value is None for value in series(result, "predicted", "dining_dollars"))
    assert series(result, "actual", "dining_dollars")[0] == 420_000
    assert all(value is None for value in series(result, "actual", "dining_dollars")[1:])
    # Default 30-day horizon from the start of Oct 30: ideal goes evenly to $0.00.
    assert result["horizon"] == {"start": date(2026, 10, 30), "end_date": date(2026, 11, 28), "rule": "default", "days": 30}
    ideal = series(result, "ideal", "dining_dollars")
    assert ideal[0] == 420_000 and ideal[-1] == 0 and ideal[1] == 406_000


# 3. Two observations: preliminary pace with labelled sensitivity paths.
def test_two_observations_give_a_preliminary_pace_per_wallet():
    result = build_prediction(
        observations((date(2026, 10, 30), 420_000, 45_000), (date(2026, 11, 4), 405_000, 42_000)),
        date(2026, 11, 4), None, None,
    )

    dd, tc = account(result, "dining_dollars"), account(result, "triton_cash")
    # (4200.00 - 4050.00) / 5 days = $30.00/day; (450.00 - 420.00) / 5 = $6.00/day.
    assert (dd["daily_pace_cents"], dd["lower_pace_cents"], dd["higher_pace_cents"]) == (3000, 2250, 3750)
    assert (tc["daily_pace_cents"], tc["lower_pace_cents"], tc["higher_pace_cents"]) == (600, 450, 750)
    assert dd["confidence"] == tc["confidence"] == "preliminary" and dd["range_basis"] == "sensitivity"
    points = result["points"]
    # Axis: start of Oct 30 .. end of Dec 3 (30 days from the Nov 4 observation).
    assert (points[0]["date"], points[0]["moment"]) == (date(2026, 10, 30), "start")
    assert (points[-1]["date"], points[-1]["moment"]) == (date(2026, 12, 3), "end")
    predicted = series(result, "predicted", "dining_dollars")
    assert predicted[:5] == [None] * 5
    assert predicted[5] == 405_000 and predicted[6] == 402_000 and predicted[-1] == 405_000 - 30 * 3_000
    assert series(result, "lower", "dining_dollars")[-1] == 405_000 - 30 * 2_250 == dd["lower_end_cents"]
    assert series(result, "higher", "triton_cash")[-1] == 42_000 - 30 * 750
    # Only the two real observations are actual values.
    actual = series(result, "actual", "dining_dollars")
    assert [i for i, value in enumerate(actual) if value is not None] == [0, 5]


# 4-6. Several observations, unequal intervals, different wallets.
def test_multiple_unequal_intervals_learn_each_wallet_separately():
    rows = [
        (date(2026, 10, 1), 100_000, 20_000),
        (date(2026, 10, 3), 98_000, 20_000),   # 2 days: DD 1000/day, TC 0/day
        (date(2026, 10, 10), 91_000, 16_500),  # 7 days: DD 1000, TC 500
        (date(2026, 10, 11), 90_000, 16_300),  # 1 day:  DD 1000, TC 200
        (date(2026, 10, 20), 81_000, 13_600),  # 9 days: DD 1000, TC 300
    ]
    obs = observations(*rows)
    dd, tc = fit_account(obs, "dining_dollars"), fit_account(obs, "triton_cash")

    assert [item.days for item in dd.usable_intervals] == [2, 7, 1, 9]
    assert dd.pace == dd.lower_pace == dd.higher_pace == 1_000
    # TC weights = days * 0.5**(age/21): 0 -> 1.14, 500 -> 5.03, 200 -> 0.74, 300 -> 9.0 (total 15.92).
    # Sorted cumulative: 0:1.14, 200:1.88, 300:10.88, 500:15.92 -> q25 = 300, median = 300, q75 = 500.
    assert (tc.lower_pace, tc.pace, tc.higher_pace) == (300, 300, 500)
    assert tc.range_basis == "learned_range"
    assert dd.confidence == tc.confidence == "developing"  # 4 intervals over 19 days


def test_confidence_grows_with_a_longer_consistent_history():
    start = date(2026, 10, 1)
    rows = [(start + timedelta(days=7 * n), 100_000 - 7_000 * n, 10_000) for n in range(6)]
    model = fit_account(observations(*rows), "dining_dollars")

    assert model.pace == 1_000 and model.confidence == "established"  # 5 intervals over 35 days
    assert fit_account(observations(*rows[:2]), "dining_dollars").confidence == "preliminary"
    assert fit_account(observations(*rows[:4]), "dining_dollars").confidence == "developing"


# 7. Duplicate dates: the latest save for a date is used; history is kept.
def test_duplicate_dates_use_the_latest_save_deterministically():
    early = checkin(date(2026, 10, 1), 100_000, 10_000, hour=8)
    late = checkin(date(2026, 10, 1), 95_000, 9_000, hour=20)
    obs = observations_from_checkins([late, early], TODAY)  # input order does not matter

    assert len(obs) == 1 and obs[0].balances == {"dining_dollars": 95_000, "triton_cash": 9_000}
    # An end-of-day check-in on Sep 30 and a wallet save on Oct 1 describe the same moment.
    eod = checkin(date(2026, 9, 30), 70_000, 7_000, source="manual", hour=23)
    merged = observations_from_checkins([eod, early], TODAY)
    assert len(merged) == 1 and merged[0].balances["dining_dollars"] == 100_000  # the Oct 1 save is later
    # Future-dated saves are ignored.
    assert observations_from_checkins([checkin(TODAY + timedelta(days=1), 1, 1)], TODAY) == []


# 8. Increases are replenishments, not negative spending.
def test_balance_increases_are_replenishments_excluded_from_the_pace():
    obs = observations(
        (date(2026, 10, 1), 50_000, 10_000),
        (date(2026, 10, 8), 49_300, 9_300),    # TC -100/day
        (date(2026, 10, 15), 48_600, 15_000),  # TC +5,700 (deposit/refund?)
        (date(2026, 10, 22), 47_900, 14_300),  # TC -100/day
    )
    tc = fit_account(obs, "triton_cash")

    assert tc.pace == 100 and len(tc.usable_intervals) == 2
    assert [(item.start, item.end, item.change_cents) for item in tc.replenishments] == [(date(2026, 10, 8), date(2026, 10, 15), 5_700)]
    summary = account(build_prediction(obs, TODAY, None, None), "triton_cash")
    assert summary["replenishments"] == [{"from_boundary": date(2026, 10, 8), "to_boundary": date(2026, 10, 15), "increase_cents": 5_700}]


# 9. Outliers are kept and flagged but barely move the pace.
def test_outliers_are_flagged_without_dominating():
    rows = [(date(2026, 10, 1) + timedelta(days=7 * n), 100_000 - 7_000 * n, 0) for n in range(5)]
    rows.append((date(2026, 10, 30), 72_000 - 20_000, 0))  # one day, $200/day
    model = fit_account(observations(*rows), "dining_dollars")

    assert model.pace == 1_000
    assert len(model.usable_intervals) == 5  # the outlier is still an observation
    assert [(item.end, item.pace) for item in model.unusual] == [(date(2026, 10, 30), 20_000)]


# 10. Recent behaviour outweighs old behaviour.
def test_recent_intervals_weigh_more_than_old_ones():
    rows = [(date(2026, 9, 1), 100_000, 0), (date(2026, 9, 11), 80_000, 0), (date(2026, 9, 21), 60_000, 0),
            (date(2026, 10, 1), 40_000, 0), (date(2026, 10, 11), 35_000, 0), (date(2026, 10, 21), 30_000, 0)]
    model = fit_account(observations(*rows), "dining_dollars")

    paces = sorted(item.pace for item in model.usable_intervals)
    assert paces[len(paces) // 2] == 2_000  # the unweighted median would say $20/day
    assert model.pace == 500  # the two most recent 10-day intervals dominate


def test_weighted_quantile_and_paths_are_exact():
    assert weighted_quantile([Fraction(3), Fraction(1), Fraction(2)], [1.0, 1.0, 1.0], Fraction(1, 2)) == 2
    assert weighted_quantile([Fraction(1), Fraction(9)], [1.0, 3.0], Fraction(1, 2)) == 9
    # Never below $0.00; ties round away from zero.
    assert path(10_000, Fraction(3_000), 5) == [10_000, 7_000, 4_000, 1_000, 0, 0]
    assert path(101, Fraction(1, 2), 1) == [101, 101]  # 100.5 -> 101


# 11-13. Scenarios, start point, ideal endpoints, horizon from a selected forecast.
def test_paths_start_at_the_latest_observation_and_ideal_hits_the_saved_target():
    obs = observations((date(2026, 11, 20), 50_000, 9_000), (date(2026, 11, 25), 45_000, 8_000))
    comparison = {
        "id": "f1", "created_at": datetime(2026, 11, 20, 8, tzinfo=timezone.utc), "scenario": "expected",
        "start_date": date(2026, 11, 20), "end_date": date(2026, 12, 4),
        "targets": {"dining_dollars_cents": 5_000, "triton_cash_cents": 10_000},
        "plan": {date(2026, 11, 20): {"dining_dollars_cents": 50_000, "triton_cash_cents": 9_000},
                 date(2026, 11, 21): {"dining_dollars_cents": 49_000, "triton_cash_cents": 9_000}},
    }
    result = build_prediction(obs, date(2026, 11, 25), comparison, {"dining_dollars_cents": 1, "triton_cash_cents": 1})

    assert result["horizon"] == {"start": date(2026, 11, 25), "end_date": date(2026, 12, 4), "rule": "selected_forecast_end", "days": 10}
    offset = 5  # Nov 20 -> Nov 25
    for name in ("predicted", "lower", "higher", "ideal"):
        values = series(result, name, "dining_dollars")
        assert values[:offset] == [None] * offset and values[offset] == 45_000
    # $10/day expected, $7.50 / $12.50 sensitivity, over 10 days.
    assert series(result, "predicted", "dining_dollars")[-1] == 35_000
    assert series(result, "lower", "dining_dollars")[-1] == 37_500
    assert series(result, "higher", "dining_dollars")[-1] == 32_500
    dd, tc = account(result, "dining_dollars"), account(result, "triton_cash")
    # The selected forecast's saved targets win over the current warning amounts.
    assert dd["target_cents"] == 5_000 and dd["target_basis"] == "forecast_threshold"
    ideal = series(result, "ideal", "dining_dollars")
    assert ideal[-1] == 5_000 and ideal[offset + 5] == 45_000 - 5 * 4_000
    assert tc["ideal_available"] is False and all(v is None for v in series(result, "ideal", "triton_cash"))
    # The original plan appears only on its own saved boundaries.
    plan = series(result, "original_plan", "dining_dollars")
    assert plan[:2] == [50_000, 49_000] and all(value is None for value in plan[2:])


def test_runs_out_date_is_the_end_of_the_day_the_balance_reaches_zero():
    obs = observations((date(2026, 11, 1), 13_000, 0), (date(2026, 11, 4), 10_000, 0))  # $10/day
    dd = account(build_prediction(obs, date(2026, 11, 4), None, None), "dining_dollars")

    # 10,000 cents at the start of Nov 4 -> 0 at the end of the 10th day (Nov 13).
    assert dd["runs_out_on"] == date(2026, 11, 13) and dd["predicted_end_cents"] == 0


# API: isolation, learning from new saves, privacy, and saved forecasts staying unchanged.


@pytest.fixture
def students(factory):  # noqa: F811
    today = pilot_today_provider()
    app.dependency_overrides[pilot_today_provider] = lambda: today
    alice, bob = TestClient(app), TestClient(app)
    assert signup(alice).status_code == 201
    assert signup(bob, email="bob@example.com", password="bob password 22").status_code == 201
    return today, (alice, accept_consent(alice)), (bob, accept_consent(bob)), factory


def _save(client, token, day, dining, cash):
    response = client.post("/api/v1/pilot/wallet", json={
        "effective_date": day.isoformat(), "dining_dollars_cents": dining, "triton_cash_cents": cash,
    }, headers={"X-CSRF-Token": token})
    assert response.status_code == 200, response.text


def _prediction(client, **params):
    response = client.get("/api/v1/pilot/prediction", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_api_learns_from_each_new_save_and_students_are_isolated(students):
    today, (alice, a_token), (bob, b_token), _ = students
    assert _prediction(alice)["observation_count"] == 0

    _save(alice, a_token, today - timedelta(days=10), 100_000, 20_000)
    assert account(_prediction(alice), "dining_dollars")["confidence"] == "starting"
    _save(alice, a_token, today - timedelta(days=5), 95_000, 19_500)
    first = account(_prediction(alice), "dining_dollars")
    assert first["daily_pace_cents"] == 1_000 and first["confidence"] == "preliminary"
    _save(alice, a_token, today, 85_000, 19_000)  # faster: $20/day recently
    second = account(_prediction(alice), "dining_dollars")
    assert second["daily_pace_cents"] == 2_000 and second["latest_cents"] == 85_000

    _save(bob, b_token, today - timedelta(days=2), 5_000, 1_000)
    _save(bob, b_token, today, 4_000, 1_000)
    bob_view = _prediction(bob)
    assert bob_view["observation_count"] == 2
    assert account(bob_view, "dining_dollars")["daily_pace_cents"] == 500  # Bob's own history only
    assert account(_prediction(alice), "dining_dollars")["daily_pace_cents"] == 2_000
    assert TestClient(app).get("/api/v1/pilot/prediction").status_code == 401


def test_api_compares_with_a_selected_forecast_without_changing_it(students):
    today, (alice, token), (bob, _), _ = students
    _save(alice, token, today - timedelta(days=3), 60_000, 9_000)
    alice.post("/api/v1/pilot/balance-thresholds", json={"dining_dollars_cents": 2_000, "triton_cash_cents": 0},
               headers={"X-CSRF-Token": token})
    meal = {"name": "meal", "frequency": "1", "price_cents": 1_500, "eligible_accounts": ["dining_dollars"]}
    created = alice.post("/api/v1/pilot/forecasts", json={"end_date": (today + timedelta(days=6)).isoformat(), "habits": [meal]},
                         headers={"X-CSRF-Token": token}).json()
    before = alice.get(f"/api/v1/pilot/forecasts/{created['id']}").json()
    _save(alice, token, today, 57_000, 8_700)  # $10/day observed, not the plan's $15/day

    result = _prediction(alice, forecast_id=created["id"])

    assert result["comparison"]["id"] == created["id"]
    assert result["horizon"]["end_date"] == created["end_date"]
    dd = account(result, "dining_dollars")
    assert dd["daily_pace_cents"] == 1_000 and dd["target_cents"] == 2_000
    points = result["points"]
    assert points[0]["date"] == created["start_date"]
    stored = {day["date"]: day["remaining_balances"]["dining_dollars_cents"] for day in created["forecast"]["days"]}
    plan = series(result, "original_plan", "dining_dollars")
    assert plan[0] == 60_000
    assert [plan[k] for k in range(1, len(points))] == [stored[str(points[k]["date"])] for k in range(1, len(points))]
    assert series(result, "predicted", "dining_dollars")[3] == 57_000  # starts at the latest save, not the plan
    assert alice.get(f"/api/v1/pilot/forecasts/{created['id']}").json() == before
    assert bob.get("/api/v1/pilot/prediction", params={"forecast_id": created["id"]}).status_code == 404


def test_prediction_data_is_exported_and_deleted_with_the_account(students):
    today, (alice, token), (bob, b_token), factory = students  # noqa: F811
    _save(alice, token, today - timedelta(days=1), 10_000, 1_000)
    _save(alice, token, today - timedelta(days=1), 9_000, 1_000)  # same date: both kept
    _save(bob, b_token, today, 1, 1)

    exported = alice.get("/api/v1/pilot/export").json()["balance_checkins"]
    assert [item["dining_dollars_cents"] for item in exported] == [10_000, 9_000]
    assert account(_prediction(alice), "dining_dollars")["latest_cents"] == 9_000

    assert alice.request("DELETE", "/api/v1/pilot/account", json={"confirmation": "DELETE_MY_DATA"},
                         headers={"X-CSRF-Token": token}).status_code == 200
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(BalanceCheckin)) == 1  # only Bob's remains
        assert session.scalar(select(func.count()).select_from(ForecastSnapshot)) == 0
    assert login(TestClient(app)).status_code == 401
    assert _prediction(bob)["observation_count"] == 1
