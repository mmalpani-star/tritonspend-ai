from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.app.dependencies import pilot_today_provider, today_provider
from backend.app.main import app
from backend.app.models import (
    BalanceCheckin,
    EntryType,
    ForecastSnapshot,
    InviteToken,
    LedgerEntry,
    Participant,
)
from backend.app.participant_forecast import (
    ENGINE_VERSION,
    LEGACY_SNAPSHOT_SCHEMA_VERSION,
    SNAPSHOT_SCHEMA_VERSION,
    ReconciliationError,
    forecast_start,
    ideal_balance,
    reconcile,
    wallet_start_warnings,
)
from backend.app.security import hash_secret, make_secret, utc_now
from backend.tests.test_pilot import _authenticate, _setup


TODAY = pilot_today_provider()
AS_OF = date(2026, 10, 20)
MEAL = {"name": "dining meal", "frequency": "1", "price_cents": 500, "eligible_accounts": ["dining_dollars"]}


def _checkin(day, dining, cash, participant_id="p1"):
    return BalanceCheckin(
        participant_id=participant_id,
        observed_at=datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc),
        effective_date=day,
        dining_dollars_cents=dining,
        triton_cash_cents=cash,
        created_at=utc_now(),
    )


def _entry(day, account, entry_type, amount, participant_id="p1"):
    return LedgerEntry(
        participant_id=participant_id,
        occurred_on=day,
        account=account,
        entry_type=EntryType(entry_type),
        amount_cents=amount,
    )


# Pure rules: legacy (v1) reconciliation, start-date warnings, and the ideal curve.


def test_reconcile_applies_spending_deposits_and_refunds_per_wallet_after_the_checkin():
    baseline = _checkin(AS_OF - timedelta(days=3), 10_000, 2_000)
    entries = [
        _entry(AS_OF - timedelta(days=4), "dining_dollars", "spending", 9_999),  # before check-in
        _entry(AS_OF - timedelta(days=3), "dining_dollars", "spending", 500),  # check-in day
        _entry(AS_OF - timedelta(days=2), "dining_dollars", "spending", 1_250),
        _entry(AS_OF - timedelta(days=1), "triton_cash", "deposit", 1_000),
        _entry(AS_OF, "dining_dollars", "refund", 250),
        _entry(AS_OF, "triton_cash", "spending", 300),
        _entry(AS_OF + timedelta(days=1), "triton_cash", "spending", 9_999),  # after reference date
    ]

    result = reconcile(baseline, entries, AS_OF)

    assert result.balances == {"dining_dollars": 9_000, "triton_cash": 2_700}
    assert len(result.applied_entries) == 4
    assert result.warnings == (
        "1 ledger entry is dated 2026-10-17, the check-in day, and assumed to be "
        "already reflected in that check-in balance.",
    )


def test_reconcile_reports_inconsistent_wallets_instead_of_clamping():
    baseline = _checkin(AS_OF - timedelta(days=1), 1_000, 100)
    entries = [
        _entry(AS_OF, "triton_cash", "spending", 250),
        _entry(AS_OF, "dining_dollars", "spending", 400),
    ]

    with pytest.raises(ReconciliationError, match=r"Triton Cash reconciles to -\$1\.50") as error:
        reconcile(baseline, entries, AS_OF)
    assert "Dining Dollars" not in str(error.value)


def test_reconcile_never_substitutes_wallets():
    baseline = _checkin(AS_OF - timedelta(days=1), 10_000, 0)

    with pytest.raises(ReconciliationError, match="Triton Cash"):
        reconcile(baseline, [_entry(AS_OF, "triton_cash", "spending", 1)], AS_OF)


@pytest.mark.parametrize("age,stale", [(14, False), (15, True)])
def test_reconcile_flags_stale_baselines(age, stale):
    result = reconcile(_checkin(AS_OF - timedelta(days=age), 100, 100), [], AS_OF)

    assert any("days old" in warning for warning in result.warnings) is stale


def test_ideal_balance_spends_evenly_to_target_or_reports_no_path():
    end = AS_OF + timedelta(days=4)

    assert [ideal_balance(1_000, 200, AS_OF, end, AS_OF + timedelta(days=n)) for n in range(5)] == [
        1_000, 800, 600, 400, 200,
    ]
    assert ideal_balance(500, 500, AS_OF, end, end) == 500
    assert ideal_balance(100, 200, AS_OF, end, AS_OF) is None


def test_wallet_start_warnings_explain_the_gap_and_staleness():
    assert wallet_start_warnings(AS_OF, AS_OF, AS_OF) == ()
    gap = wallet_start_warnings(AS_OF - timedelta(days=2), AS_OF, AS_OF - timedelta(days=2))
    assert len(gap) == 1 and "starts on 2026-10-18" in gap[0] and "not observed" in gap[0]
    assert any("days old" in w for w in wallet_start_warnings(AS_OF - timedelta(days=15), AS_OF, AS_OF))
    assert not any("days old" in w for w in wallet_start_warnings(AS_OF - timedelta(days=14), AS_OF, AS_OF))


def test_wallet_saves_start_on_their_as_of_date_and_older_check_ins_the_day_after():
    wallet = _checkin(AS_OF, 1, 1)
    wallet.source = "wallet"
    legacy = _checkin(AS_OF, 1, 1)
    legacy.source = "manual"

    assert forecast_start(wallet) == AS_OF
    assert forecast_start(legacy) == AS_OF + timedelta(days=1)


# API workflow: saved forecasts start from the latest saved wallet balances.


@pytest.fixture
def pilot(monkeypatch):
    client, factory, invite = _setup(monkeypatch)
    app.dependency_overrides[pilot_today_provider] = lambda: TODAY
    try:
        csrf = _authenticate(client, invite)
        yield client, factory, csrf
    finally:
        app.dependency_overrides.clear()


def _post(client, csrf, path, payload):
    response = client.post(path, json=payload, headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200, response.text
    return response.json()


def _save_wallet(client, csrf, days_ago=0, dining=10_000, cash=2_000):
    return _post(client, csrf, "/api/v1/pilot/wallet", {
        "effective_date": (TODAY - timedelta(days=days_ago)).isoformat(),
        "dining_dollars_cents": dining,
        "triton_cash_cents": cash,
    })


def _save_end_of_day_checkin(client, csrf, days_ago=0, dining=10_000, cash=2_000):
    """The older check-in endpoint: an end-of-day balance."""
    return _post(client, csrf, "/api/v1/pilot/balance-checkins", {
        "effective_date": (TODAY - timedelta(days=days_ago)).isoformat(),
        "dining_dollars_cents": dining,
        "triton_cash_cents": cash,
    })


def _forecast(client, csrf, days=3, habits=None, **overrides):
    payload = {"end_date": (TODAY + timedelta(days=days)).isoformat(), "habits": [MEAL] if habits is None else habits}
    payload.update(overrides)
    return client.post("/api/v1/pilot/forecasts", json=payload, headers={"X-CSRF-Token": csrf})


def _trajectory(client, forecast_id):
    response = client.get(f"/api/v1/pilot/forecasts/{forecast_id}/trajectory")
    assert response.status_code == 200, response.text
    return response.json()


def _snapshot_count(factory):
    with factory() as session:
        return session.scalar(select(func.count()).select_from(ForecastSnapshot))


def _ledger_count(factory):
    with factory() as session:
        return session.scalar(select(func.count()).select_from(LedgerEntry))


def _dates(start, count):
    return [(start + timedelta(days=n)).isoformat() for n in range(count)]


def _second_participant(factory):
    invite = make_secret()
    with factory.begin() as session:
        session.add(InviteToken(
            token_hash=hash_secret(invite, "session-secret"),
            expires_at=utc_now() + timedelta(hours=1),
        ))
    other = TestClient(app)
    return other, _authenticate(other, invite)


def test_wallet_balances_dated_today_start_the_forecast_today(pilot):
    client, factory, csrf = pilot
    wallet = _save_wallet(client, csrf)
    with factory.begin() as session:  # another participant's data must not leak in
        stranger = Participant()
        session.add(stranger)
        session.flush()
        session.add(_checkin(TODAY, 99_999, 99_999, stranger.id))

    response = _forecast(client, csrf)

    assert response.status_code == 200, response.text
    assert _ledger_count(factory) == 0
    body = response.json()
    # As-of TODAY -> the forecast starts TODAY (not tomorrow) and ends on the chosen end date.
    assert body["start_date"] == TODAY.isoformat()
    assert body["end_date"] == (TODAY + timedelta(days=3)).isoformat()
    assert body["engine_version"] == ENGINE_VERSION
    inputs = body["inputs"]
    assert inputs["schema_version"] == SNAPSHOT_SCHEMA_VERSION == "participant-forecast.v3"
    assert inputs["reference_date"] == TODAY.isoformat()
    assert inputs["created_on"] == TODAY.isoformat()
    assert inputs["balance_source"] == "latest_saved_wallet_balances"
    assert inputs["wallet_balances"]["id"] == wallet["id"]
    assert inputs["wallet_balances"]["source"] == "wallet"
    assert inputs["starting_balances"] == {"dining_dollars_cents": 10_000, "triton_cash_cents": 2_000}
    assert inputs["targets"] is None
    assert inputs["warnings"] == []
    days = body["forecast"]["days"]
    assert [day["date"] for day in days] == _dates(TODAY, 4)
    assert days[0]["remaining_balances"] == {"dining_dollars_cents": 9_500, "triton_cash_cents": 2_000}
    with factory() as session:
        snapshot = session.get(ForecastSnapshot, body["id"])
        assert snapshot.participant_id != stranger.id
        assert snapshot.start_date == TODAY
        assert snapshot.response_json == body["forecast"]
        assert snapshot.request_json == inputs


def test_older_wallet_balances_start_on_their_as_of_date(pilot):
    client, _, csrf = pilot
    _save_wallet(client, csrf, days_ago=3)

    body = _forecast(client, csrf, days=2).json()

    as_of = TODAY - timedelta(days=3)
    assert body["inputs"]["reference_date"] == as_of.isoformat()
    assert body["start_date"] == as_of.isoformat()
    # Days between the as-of date and today are projected, not assumed spend-free.
    days = body["forecast"]["days"]
    assert [day["date"] for day in days] == _dates(as_of, 6)
    assert days[-1]["remaining_balances"]["dining_dollars_cents"] == 10_000 - 6 * 500
    assert any("not observed" in warning for warning in body["inputs"]["warnings"])
    assert not any("days old" in warning for warning in body["inputs"]["warnings"])


def test_end_of_day_check_ins_keep_starting_the_next_day(pilot):
    client, _, csrf = pilot
    _save_end_of_day_checkin(client, csrf, days_ago=1)

    body = _forecast(client, csrf, days=2).json()

    assert body["start_date"] == TODAY.isoformat()
    assert body["inputs"]["schema_version"] == "participant-forecast.v2"
    assert body["engine_version"].endswith("participant-forecast.v2")
    assert [day["date"] for day in body["forecast"]["days"]] == _dates(TODAY, 3)


def test_one_day_forecast_ending_today_is_allowed(pilot):
    client, _, csrf = pilot
    _save_wallet(client, csrf)

    body = _forecast(client, csrf, days=0).json()

    assert body["start_date"] == body["end_date"] == TODAY.isoformat()
    assert len(body["forecast"]["days"]) == 1


def test_stale_balances_get_a_reminder_but_are_never_adjusted(pilot):
    client, _, csrf = pilot
    _save_wallet(client, csrf, days_ago=20)

    body = _forecast(client, csrf).json()

    assert body["inputs"]["starting_balances"] == {"dining_dollars_cents": 10_000, "triton_cash_cents": 2_000}
    assert any("20 days old" in warning for warning in body["inputs"]["warnings"])


def test_latest_saved_balances_win_and_historical_ledger_entries_are_not_applied(pilot):
    client, factory, csrf = pilot
    _save_wallet(client, csrf, days_ago=2, dining=50_000, cash=50_000)
    _save_wallet(client, csrf, days_ago=1, dining=7_000, cash=1_500)
    # Historical ledger rows (from the retired workflow) stay stored but do not change balances.
    _post(client, csrf, "/api/v1/pilot/ledger-entries", {
        "occurred_on": TODAY.isoformat(), "account": "dining_dollars", "entry_type": "spending", "amount_cents": 400,
    })

    body = _forecast(client, csrf).json()

    assert body["inputs"]["starting_balances"] == {"dining_dollars_cents": 7_000, "triton_cash_cents": 1_500}
    assert "applied_ledger_entries" not in body["inputs"]
    assert _ledger_count(factory) == 1
    exported = client.get("/api/v1/pilot/export").json()
    assert [entry["amount_cents"] for entry in exported["ledger_entries"]] == [400]


def test_missing_wallet_balances_are_rejected_and_nothing_is_saved(pilot):
    client, factory, csrf = pilot

    response = _forecast(client, csrf)

    assert response.status_code == 422
    assert "No wallet balances are saved yet" in response.json()["detail"]
    assert _snapshot_count(factory) == 0


@pytest.mark.parametrize(
    "overrides",
    [
        {"end_date": (TODAY - timedelta(days=1)).isoformat()},
        {"end_date": (TODAY + timedelta(days=366)).isoformat()},
        {"habits": []},
        {"dining_dollars_cents": 999_999},
        {"scenario": "reckless"},
        {"habits": [{**MEAL, "frequency": "²"}]},
        {"habits": [{**MEAL, "frequency": "1/0"}]},
    ],
)
def test_invalid_requests_return_422_and_save_nothing(pilot, overrides):
    client, factory, csrf = pilot
    _save_wallet(client, csrf)

    assert _forecast(client, csrf, **overrides).status_code == 422
    assert _snapshot_count(factory) == 0


def test_366_day_forecast_is_accepted(pilot):
    client, _, csrf = pilot
    _save_wallet(client, csrf)

    body = _forecast(client, csrf, days=365).json()

    assert len(body["forecast"]["days"]) == 366


def test_window_from_old_balances_is_limited_with_an_update_hint(pilot):
    client, factory, csrf = pilot
    _save_wallet(client, csrf, days_ago=10)

    response = _forecast(client, csrf, days=360)

    assert response.status_code == 422
    assert "Update your wallet balances" in response.json()["detail"]
    assert _snapshot_count(factory) == 0


def test_generation_requires_authentication_csrf_and_consent(pilot):
    client, factory, csrf = pilot
    _save_wallet(client, csrf)
    payload = {"end_date": (TODAY + timedelta(days=2)).isoformat(), "habits": [MEAL]}

    assert TestClient(app).post("/api/v1/pilot/forecasts", json=payload).status_code == 401
    assert client.post("/api/v1/pilot/forecasts", json=payload).status_code == 403
    assert client.post("/api/v1/auth/consent/withdraw", json={}, headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.post("/api/v1/pilot/forecasts", json=payload, headers={"X-CSRF-Token": csrf}).status_code == 403
    assert _snapshot_count(factory) == 0


def test_history_is_newest_first_and_detail_round_trips(pilot):
    client, _, csrf = pilot
    _save_wallet(client, csrf)
    first = _forecast(client, csrf, days=2).json()
    second = _forecast(client, csrf, days=5, scenario="frugal").json()

    history = client.get("/api/v1/pilot/forecasts")

    assert history.status_code == 200
    summaries = history.json()["forecasts"]
    assert [item["id"] for item in summaries] == [second["id"], first["id"]]
    assert summaries[0]["scenario"] == "frugal"
    assert summaries[0]["starting_balances"] == {"dining_dollars_cents": 10_000, "triton_cash_cents": 2_000}
    assert summaries[0]["projected_balances"] == second["forecast"]["projected_balances"]
    assert summaries[0]["funds_last"] is True
    assert client.get("/api/v1/pilot/forecasts?limit=1").json()["forecasts"][0]["id"] == second["id"]
    assert client.get("/api/v1/pilot/forecasts?limit=0").status_code == 422
    detail = client.get(f"/api/v1/pilot/forecasts/{first['id']}")
    assert detail.status_code == 200
    assert detail.json() == first


def test_saved_forecasts_do_not_change_when_wallets_thresholds_or_habits_change(pilot):
    client, _, csrf = pilot
    _save_wallet(client, csrf, days_ago=1)
    original = _forecast(client, csrf, days=4).json()
    original_summary = client.get("/api/v1/pilot/forecasts").json()["forecasts"][0]
    original_trajectory = _trajectory(client, original["id"])

    _save_wallet(client, csrf, dining=1_234, cash=567)
    _post(client, csrf, "/api/v1/pilot/balance-thresholds", {"dining_dollars_cents": 100, "triton_cash_cents": 100})
    lunch = {"name": "lunch", "frequency": "2", "price_cents": 900, "eligible_accounts": ["dining_dollars", "triton_cash"]}
    newer = _forecast(client, csrf, days=4, habits=[lunch], scenario="higher").json()

    assert newer["inputs"]["starting_balances"] == {"dining_dollars_cents": 1_234, "triton_cash_cents": 567}
    assert client.get(f"/api/v1/pilot/forecasts/{original['id']}").json() == original
    summaries = {item["id"]: item for item in client.get("/api/v1/pilot/forecasts").json()["forecasts"]}
    assert summaries[original["id"]] == original_summary
    after = _trajectory(client, original["id"])
    # Projected, ideal, targets, and dates are frozen; only a newly saved balance inside
    # the original period may appear as an observation.
    for key in ("start_date", "end_date", "starting_balances", "targets"):
        assert after[key] == original_trajectory[key]
    assert [(p["date"], p["moment"], p["projected"], p["ideal"]) for p in after["points"]] == [
        (p["date"], p["moment"], p["projected"], p["ideal"]) for p in original_trajectory["points"]
    ]


def test_participants_cannot_see_each_others_forecasts_or_wallets(pilot):
    client, factory, csrf = pilot
    _save_wallet(client, csrf)
    owned = _forecast(client, csrf).json()
    other, other_csrf = _second_participant(factory)

    assert other.get("/api/v1/pilot/forecasts").json() == {"forecasts": []}
    assert other.get("/api/v1/pilot/wallet").json()["latest"] is None
    assert other.get(f"/api/v1/pilot/forecasts/{owned['id']}").status_code == 404
    assert other.get(f"/api/v1/pilot/forecasts/{owned['id']}/trajectory").status_code == 404
    # Another participant's balances never become this participant's starting point.
    assert _forecast(other, other_csrf).status_code == 422
    assert client.get("/api/v1/pilot/forecasts/does-not-exist").status_code == 404
    unauthenticated = TestClient(app)
    for path in ["/api/v1/pilot/wallet", "/api/v1/pilot/forecasts", f"/api/v1/pilot/forecasts/{owned['id']}", f"/api/v1/pilot/forecasts/{owned['id']}/trajectory"]:
        assert unauthenticated.get(path).status_code == 401


def test_trajectory_uses_the_forecast_dates_stored_output_and_only_saved_observations(pilot):
    client, _, csrf = pilot
    _save_wallet(client, csrf, days_ago=1)
    _post(client, csrf, "/api/v1/pilot/balance-thresholds", {"dining_dollars_cents": 1_000, "triton_cash_cents": 5_000})
    created = _forecast(client, csrf, days=2).json()
    # A balance saved later for a day inside the window is a real observation.
    _save_wallet(client, csrf, dining=8_800, cash=2_600)

    body = _trajectory(client, created["id"])

    start = TODAY - timedelta(days=1)
    assert body["start_date"] == start.isoformat() == created["start_date"]
    assert body["end_date"] == created["end_date"]
    assert body["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert body["starting_balances"] == {"dining_dollars_cents": 10_000, "triton_cash_cents": 2_000}
    points = body["points"]
    # The axis is exactly the forecast period: start of the first day, then the end of each day.
    assert [(p["date"], p["moment"]) for p in points] == [(start.isoformat(), "start")] + [
        (day, "end") for day in _dates(start, 4)
    ]
    assert points[0]["date"] == created["start_date"] and points[-1]["date"] == created["end_date"]
    # Projected: the starting balance, then exactly the stored daily output, matched by date.
    assert points[0]["projected"] == body["starting_balances"]
    stored = {day["date"]: day["remaining_balances"] for day in created["forecast"]["days"]}
    assert [p["projected"] for p in points[1:]] == [stored[p["date"]] for p in points[1:]]
    assert points[-1]["projected"] == created["forecast"]["projected_balances"]
    # Actual: only the two saved balances, each at the start of its as-of day.
    assert points[0]["actual"] == {"dining_dollars_cents": 10_000, "triton_cash_cents": 2_000}
    assert points[0]["actual_as_of"] == start.isoformat()
    assert points[1]["actual"] == {"dining_dollars_cents": 8_800, "triton_cash_cents": 2_600}
    assert points[1]["actual_as_of"] == TODAY.isoformat()
    assert all(p["actual"] is None and p["actual_as_of"] is None for p in points[2:])
    # Ideal: from the starting balance to the stored target, evenly, with exact endpoints.
    assert [p["ideal"]["dining_dollars_cents"] for p in points] == [10_000, 7_750, 5_500, 3_250, 1_000]
    targets = {item["account"]: item for item in body["targets"]}
    assert targets["dining_dollars"]["basis"] == "threshold" and targets["dining_dollars"]["target_cents"] == 1_000
    assert targets["triton_cash"]["ideal_available"] is False
    assert "already below" in targets["triton_cash"]["explanation"]
    assert all(p["ideal"]["triton_cash_cents"] is None for p in points)


def test_each_forecast_trajectory_reflects_only_that_forecast(pilot):
    client, _, csrf = pilot
    _save_wallet(client, csrf, days_ago=2, dining=20_000, cash=3_000)
    _post(client, csrf, "/api/v1/pilot/balance-thresholds", {"dining_dollars_cents": 2_000, "triton_cash_cents": 0})
    older = _forecast(client, csrf, days=3).json()
    _save_wallet(client, csrf, dining=6_000, cash=4_000)
    _post(client, csrf, "/api/v1/pilot/balance-thresholds", {"dining_dollars_cents": 500, "triton_cash_cents": 1_000})
    cash_meal = {"name": "market", "frequency": "1", "price_cents": 750, "eligible_accounts": ["triton_cash"]}
    newer = _forecast(client, csrf, days=6, habits=[cash_meal], scenario="frugal").json()

    first, second = _trajectory(client, older["id"]), _trajectory(client, newer["id"])

    for created, body in [(older, first), (newer, second)]:
        points = body["points"]
        assert body["forecast_id"] == created["id"]
        assert points[0]["date"] == created["start_date"] and points[-1]["date"] == created["end_date"]
        assert len(points) == len(created["forecast"]["days"]) + 1
        stored = {day["date"]: day["remaining_balances"] for day in created["forecast"]["days"]}
        assert all(p["projected"] == stored[p["date"]] for p in points[1:])
        assert points[0]["projected"] == created["inputs"]["starting_balances"]
        for account in ("dining_dollars", "triton_cash"):
            key = f"{account}_cents"
            target = created["inputs"]["targets"][key]
            if created["inputs"]["starting_balances"][key] >= target:
                assert points[0]["ideal"][key] == created["inputs"]["starting_balances"][key]
                assert points[-1]["ideal"][key] == target
    assert first["start_date"] == (TODAY - timedelta(days=2)).isoformat()
    assert second["start_date"] == TODAY.isoformat()
    assert first["starting_balances"] != second["starting_balances"]
    assert {t["account"]: t["target_cents"] for t in first["targets"]} == {"dining_dollars": 2_000, "triton_cash": 0}
    assert {t["account"]: t["target_cents"] for t in second["targets"]} == {"dining_dollars": 500, "triton_cash": 1_000}
    # The newer forecast spends only Triton Cash, so its Dining Dollars line stays flat.
    assert {p["projected"]["dining_dollars_cents"] for p in second["points"]} == {6_000}
    assert second["points"][-1]["projected"]["triton_cash_cents"] == newer["forecast"]["projected_balances"]["triton_cash_cents"]


def test_end_of_day_check_in_forecasts_chart_the_check_in_as_their_starting_point(pilot):
    client, _, csrf = pilot
    _save_end_of_day_checkin(client, csrf, days_ago=1)
    created = _forecast(client, csrf, days=1).json()

    points = _trajectory(client, created["id"])["points"]

    assert [(p["date"], p["moment"]) for p in points] == [
        (TODAY.isoformat(), "start"), (TODAY.isoformat(), "end"), ((TODAY + timedelta(days=1)).isoformat(), "end"),
    ]
    # The end-of-day balance from yesterday is the start of today.
    assert points[0]["actual"] == {"dining_dollars_cents": 10_000, "triton_cash_cents": 2_000}
    assert points[0]["actual_as_of"] == (TODAY - timedelta(days=1)).isoformat()


def test_trajectory_targets_zero_when_no_threshold_was_saved(pilot):
    client, _, csrf = pilot
    _save_wallet(client, csrf)
    created = _forecast(client, csrf, days=1).json()

    body = _trajectory(client, created["id"])

    assert {item["basis"] for item in body["targets"]} == {"zero"}
    assert body["points"][-1]["ideal"] == {"dining_dollars_cents": 0, "triton_cash_cents": 0}


def _add_snapshot(factory, request_json, response_json, created_at=None):
    with factory.begin() as session:
        participant_id = session.scalar(select(InviteToken.participant_id).where(InviteToken.participant_id.is_not(None)))
        snapshot = ForecastSnapshot(
            participant_id=participant_id,
            start_date=TODAY + timedelta(days=1),
            end_date=TODAY + timedelta(days=1),
            engine_version="fixture",
            request_json=request_json,
            response_json=response_json,
            **({"created_at": created_at} if created_at else {}),
        )
        session.add(snapshot)
        session.flush()
        return snapshot.id


def test_v1_ledger_reconciled_snapshots_stay_listed_readable_and_chartable(pilot):
    client, factory, _ = pilot
    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    reconciled = {"dining_dollars_cents": 9_000, "triton_cash_cents": 2_700}
    after_day = {"dining_dollars_cents": 8_500, "triton_cash_cents": 2_700}
    request_json = {
        "schema_version": LEGACY_SNAPSHOT_SCHEMA_VERSION,
        "reference_date": TODAY.isoformat(),
        "start_date": tomorrow,
        "end_date": tomorrow,
        "reconciled_balances": reconciled,
        "applied_ledger_entries": [{"id": "x", "amount_cents": 1_000}],
        "targets": None,
        "warnings": [],
    }
    response_json = {"scenario": "expected", "funds_last": True, "total_unfunded_cents": 0, "projected_balances": after_day,
                     "days": [{"date": tomorrow, "remaining_balances": after_day}]}
    legacy_id = _add_snapshot(factory, request_json, response_json)

    summary = client.get("/api/v1/pilot/forecasts").json()["forecasts"][0]
    trajectory = _trajectory(client, legacy_id)

    assert summary["id"] == legacy_id and summary["starting_balances"] == reconciled
    assert client.get(f"/api/v1/pilot/forecasts/{legacy_id}").json()["inputs"] == request_json
    assert trajectory["starting_balances"] == reconciled
    assert [(p["date"], p["projected"]) for p in trajectory["points"]] == [(tomorrow, reconciled), (tomorrow, after_day)]


def test_unversioned_snapshots_are_listed_and_readable_but_not_charted(pilot):
    client, factory, _ = pilot
    legacy_id = _add_snapshot(factory, {"note": "imported"}, {"anything": True})

    summary = client.get("/api/v1/pilot/forecasts").json()["forecasts"][0]

    assert summary["id"] == legacy_id
    assert summary["scenario"] is None and summary["starting_balances"] is None and summary["warnings"] == []
    assert client.get(f"/api/v1/pilot/forecasts/{legacy_id}").status_code == 200
    assert client.get(f"/api/v1/pilot/forecasts/{legacy_id}/trajectory").status_code == 409


def test_timestamps_are_returned_as_explicit_utc(pilot):
    client, factory, csrf = pilot
    # SQLite hands back stored UTC without an offset; the API must label it UTC.
    stored = datetime(2026, 10, 30, 7, 49, 12)
    snapshot_id = _add_snapshot(factory, {"note": "imported"}, {}, created_at=stored)
    saved = _save_wallet(client, csrf)

    summary = client.get("/api/v1/pilot/forecasts").json()["forecasts"][0]
    detail = client.get(f"/api/v1/pilot/forecasts/{snapshot_id}").json()
    wallet = client.get("/api/v1/pilot/wallet").json()["latest"]

    assert summary["created_at"] == detail["created_at"] == "2026-10-30T07:49:12Z"
    for value in (saved["observed_at"], wallet["observed_at"]):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        assert parsed.utcoffset() == timedelta(0)
    exported = client.get("/api/v1/pilot/export").json()
    assert exported["forecast_snapshots"][0]["created_at"] == "2026-10-30T07:49:12Z"
    assert datetime.fromisoformat(exported["participant"]["created_at"].replace("Z", "+00:00")).utcoffset() == timedelta(0)


def test_export_includes_saved_forecasts_and_deletion_removes_them(pilot):
    client, factory, csrf = pilot
    _save_wallet(client, csrf)
    created = _forecast(client, csrf).json()

    exported = client.get("/api/v1/pilot/export").json()["forecast_snapshots"]

    assert len(exported) == 1
    assert exported[0]["request_json"]["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert exported[0]["response_json"] == created["forecast"]
    assert client.request(
        "DELETE", "/api/v1/pilot/account", json={"confirmation": "DELETE_MY_DATA"}, headers={"X-CSRF-Token": csrf}
    ).status_code == 200
    assert _snapshot_count(factory) == 0
    assert client.get("/api/v1/pilot/forecasts").status_code == 401


def test_anonymous_forecast_endpoint_is_unchanged_and_saves_nothing(pilot):
    _, factory, _ = pilot
    fixed = date(2026, 10, 16)
    app.dependency_overrides[today_provider] = lambda: fixed

    response = TestClient(app).post("/api/v1/forecasts", json={
        "start_date": "2026-10-16",
        "end_date": "2026-10-18",
        "dining_dollars_cents": 300,
        "triton_cash_cents": 200,
        "habits": [MEAL],
    })

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"scenario", "multiplier", "days", "projected_balances", "total_unfunded_cents", "funds_last", "limits"}
    assert body["projected_balances"] == {"dining_dollars_cents": 0, "triton_cash_cents": 200}
    assert _snapshot_count(factory) == 0


# Deleting individual saved forecasts.


def _delete(client, forecast_id, csrf=None):
    headers = {"X-CSRF-Token": csrf} if csrf else {}
    return client.delete(f"/api/v1/pilot/forecasts/{forecast_id}", headers=headers)


def test_deleting_a_forecast_removes_only_that_snapshot(pilot):
    client, factory, csrf = pilot
    _save_wallet(client, csrf, days_ago=1)
    _save_wallet(client, csrf, dining=9_000)
    _post(client, csrf, "/api/v1/pilot/balance-thresholds", {"dining_dollars_cents": 100, "triton_cash_cents": 100})
    keep = _forecast(client, csrf, days=2).json()
    doomed = _forecast(client, csrf, days=5).json()
    wallet_before = client.get("/api/v1/pilot/wallet").json()

    response = _delete(client, doomed["id"], csrf)

    assert response.status_code == 200
    assert response.json() == {"deleted": True, "id": doomed["id"]}
    assert [item["id"] for item in client.get("/api/v1/pilot/forecasts").json()["forecasts"]] == [keep["id"]]
    assert client.get(f"/api/v1/pilot/forecasts/{doomed['id']}").status_code == 404
    assert client.get(f"/api/v1/pilot/forecasts/{doomed['id']}/trajectory").status_code == 404
    assert client.get(f"/api/v1/pilot/forecasts/{keep['id']}").json() == keep
    assert client.get("/api/v1/pilot/wallet").json() == wallet_before  # balances, history, thresholds intact
    assert client.get("/api/v1/auth/status").json()["authenticated"] is True
    assert _delete(client, doomed["id"], csrf).status_code == 404  # already gone


def test_forecast_deletion_requires_session_csrf_and_consent(pilot):
    client, factory, csrf = pilot
    _save_wallet(client, csrf)
    created = _forecast(client, csrf).json()

    assert _delete(TestClient(app), created["id"], csrf).status_code == 401
    assert _delete(client, created["id"]).status_code == 403
    assert _delete(client, created["id"], "wrong-token").status_code == 403
    assert client.post("/api/v1/auth/consent/withdraw", json={}, headers={"X-CSRF-Token": csrf}).status_code == 200
    assert _delete(client, created["id"], csrf).status_code == 403
    assert _snapshot_count(factory) == 1


def test_participants_cannot_delete_each_others_forecasts(pilot):
    client, factory, csrf = pilot
    _save_wallet(client, csrf)
    owned = _forecast(client, csrf).json()
    other, other_csrf = _second_participant(factory)

    assert _delete(other, owned["id"], other_csrf).status_code == 404
    assert _delete(other, "does-not-exist", other_csrf).status_code == 404
    assert client.get(f"/api/v1/pilot/forecasts/{owned['id']}").status_code == 200
    assert _snapshot_count(factory) == 1
