"""Rolling-origin backtest of the personalized model, checked against hand-calculated fixtures.

Fixture (wallet saves, so each describes the start of its as-of day):

    boundary   DD      TC
    Nov 1   10_000   5_000
    Nov 2    9_000   5_000
    Nov 4    8_000   4_400
    Nov 5    8_500   4_400   <- DD rose by $5.00 (replenishment)

Origin Nov 1 (1 observation): no pace, so no model prediction for Nov 2, 4, 5.
Origin Nov 2 (Nov 1-2): DD pace 1000/day, TC pace 0/day.
    Nov 4 (2 days): DD 7_000 vs 8_000 -> -1_000 (baseline 9_000 -> +1_000); TC 5_000 vs 4_400 -> +600 (baseline +600)
    Nov 5 (3 days): DD 6_000 vs 8_500 -> -2_500 (baseline +500, replenishment); TC 5_000 vs 4_400 -> +600 (+600)
Origin Nov 4 (Nov 1-4): intervals 1000/day (1 day, ended 2 days earlier: weight 0.5**(2/21) = 0.936)
    and 500/day (2 days, weight 2). Weighted median of DD = 500; TC paces 0 (0.936) and 300 (2) -> 300.
    Nov 5 (1 day): DD 7_500 vs 8_500 -> -1_000 (baseline -500, replenishment); TC 4_100 vs 4_400 -> -300 (baseline 0)
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from backend.app.backtest import EVALUATOR_VERSION, backtest_pairs, evaluate, production_predictor, summarize, Pair
from backend.app.dependencies import pilot_today_provider
from backend.app.main import app
from backend.app.models import BalanceCheckin
from backend.app.personal_model import MODEL_VERSION
from backend.tests.test_accounts import accept_consent, factory, signup  # noqa: F401

TODAY = date(2026, 12, 1)
_ids = iter(range(10_000))
NOV = lambda day: date(2026, 11, day)  # noqa: E731


def checkin(day, dining, cash, source="wallet", hour=12, participant="p", saved=None):
    """A save for as-of ``day``; ``saved`` (UTC) is when it was persisted, by default the same day."""
    moment = datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc)
    saved = saved or moment
    return BalanceCheckin(
        id=f"b{next(_ids):05d}", participant_id=participant, effective_date=day, observed_at=saved, created_at=saved,
        dining_dollars_cents=dining, triton_cash_cents=cash, source=source,
    )


def fixture_rows():
    return [checkin(NOV(1), 10_000, 5_000), checkin(NOV(2), 9_000, 5_000), checkin(NOV(4), 8_000, 4_400), checkin(NOV(5), 8_500, 4_400)]


def rows(pairs, account):
    return sorted(
        ((p.origin, p.target, p.elapsed_days, p.predicted_cents, p.actual_cents, p.model_error, p.baseline_error, p.replenishment)
         for p in pairs if p.account == account),
    )


def account(report, name):
    return next(item for item in report["accounts"] if item["account"] == name)


EXPECTED_DD = [
    (NOV(1), NOV(2), 1, None, 9_000, None, 1_000, False),
    (NOV(1), NOV(4), 3, None, 8_000, None, 2_000, False),
    (NOV(1), NOV(5), 4, None, 8_500, None, 1_500, True),
    (NOV(2), NOV(4), 2, 7_000, 8_000, -1_000, 1_000, False),
    (NOV(2), NOV(5), 3, 6_000, 8_500, -2_500, 500, True),
    (NOV(4), NOV(5), 1, 7_500, 8_500, -1_000, -500, True),
]
EXPECTED_TC = [
    (NOV(1), NOV(2), 1, None, 5_000, None, 0, False),
    (NOV(1), NOV(4), 3, None, 4_400, None, 600, False),
    (NOV(1), NOV(5), 4, None, 4_400, None, 600, False),
    (NOV(2), NOV(4), 2, 5_000, 4_400, 600, 600, False),
    (NOV(2), NOV(5), 3, 5_000, 4_400, 600, 600, False),
    (NOV(4), NOV(5), 1, 4_100, 4_400, -300, 0, False),
]


# 4. Each later actual balance is compared with the prediction for that same day.
def test_actual_future_balances_are_compared_with_the_matching_prediction():
    truth, pairs, beyond = backtest_pairs(fixture_rows(), TODAY)

    assert [item.boundary for item in truth] == [NOV(1), NOV(2), NOV(4), NOV(5)] and beyond == 0
    assert rows(pairs, "dining_dollars") == EXPECTED_DD


# 1-2. Each prediction sees only what was dated on or before its origin; later saves cannot change it.
def test_predictions_only_see_observations_up_to_their_cutoff():
    seen = []

    def spy(observations, origin, days):
        seen.append((origin, [item.boundary for item in observations]))
        return production_predictor(observations, origin, days)

    backtest_pairs(fixture_rows(), TODAY, spy)

    assert seen == [(NOV(1), [NOV(1)]), (NOV(2), [NOV(1), NOV(2)]), (NOV(4), [NOV(1), NOV(2), NOV(4)])]
    assert all(max(boundaries) == origin for origin, boundaries in seen)


def test_future_observations_cannot_leak_into_earlier_predictions():
    _, before, _ = backtest_pairs(fixture_rows(), TODAY)
    # Wildly different later saves. The Nov 6 end-of-day check-in and the Nov 7 wallet save share boundary Nov 7
    # (the later save wins), so the truth series becomes Nov 1, 2, 4, 5, 7 and Dec 1.
    extra = [checkin(NOV(6), 100, 100, source="manual"), checkin(NOV(7), 99_999, 99_999), checkin(TODAY, 1, 1)]
    _, after, beyond = backtest_pairs(fixture_rows() + extra, TODAY)

    for pair in before:
        twin = next(p for p in after if (p.account, p.origin, p.target) == (pair.account, pair.origin, pair.target))
        assert twin == pair
    # No observation is ever scored by a prediction that already contained it.
    assert all(p.target > p.origin for p in after)
    # Dec 1 is 24-30 days after each of the 5 earlier origins: counted, never scored.
    assert beyond == 5 and all(p.target != TODAY for p in after)


# 3. Same-day saves: the latest one for a date is used, and a date is one observation, not extra intervals.
def test_same_day_duplicates_follow_the_production_rules():
    duplicates = fixture_rows() + [checkin(NOV(4), 1_000, 1, hour=8), checkin(NOV(2), 2, 2, hour=6)]
    truth, pairs, _ = backtest_pairs(duplicates, TODAY)

    assert len(truth) == 4 and sorted({p.origin for p in pairs}) == [NOV(1), NOV(2), NOV(4)]
    assert rows(pairs, "dining_dollars") == EXPECTED_DD and rows(pairs, "triton_cash") == EXPECTED_TC


# 5. Horizons: scored against the real later save date and grouped into buckets.
def test_multiple_horizons_use_actual_elapsed_days():
    report = evaluate(fixture_rows(), TODAY, min_samples=1)
    one, three, seven, fourteen = account(report, "dining_dollars")["horizons"]

    assert (one["bucket"], one["pairs"], one["scored_pairs"], one["elapsed_days_observed"]) == ("1 day", 2, 1, [1])
    assert one["model"]["mae_cents"] == 1_000 and one["baseline"]["mae_cents"] == 500 and one["verdict"] == "worse"
    assert (three["bucket"], three["pairs"], three["scored_pairs"], three["elapsed_days_observed"]) == ("3 days", 4, 2, [2, 3, 4])
    assert three["model"] == {
        "mae_cents": 1_750, "mae_dollars": 17.5, "median_abs_error_cents": 1_750, "median_abs_error_dollars": 17.5,
        "mean_signed_error_cents": -1_750, "mean_signed_error_dollars": -17.5,
    }
    assert three["baseline"]["mae_cents"] == 750 and three["baseline"]["mean_signed_error_cents"] == 750
    for empty in (seven, fourteen):
        assert empty["pairs"] == 0 and empty["status"] == "insufficient_data" and empty["model"] is None


def test_observations_past_the_longest_horizon_are_counted_not_scored():
    report = evaluate([checkin(NOV(1), 10_000, 1_000), checkin(NOV(2), 9_000, 1_000), checkin(NOV(30), 1_000, 1_000)], TODAY)

    assert report["later_observations_beyond_max_horizon"] == 2  # Nov 1 -> 30 and Nov 2 -> 30 (28-29 days)
    assert account(report, "dining_dollars")["overall"]["pairs"] == 1


# 6. Wallets are independent.
def test_dining_dollars_and_triton_cash_are_evaluated_independently():
    _, pairs, _ = backtest_pairs(fixture_rows(), TODAY)
    changed = [checkin(NOV(1), 10_000, 900), checkin(NOV(2), 9_000, 50_000), checkin(NOV(4), 8_000, 1), checkin(NOV(5), 8_500, 77_777)]
    _, other, _ = backtest_pairs(changed, TODAY)

    assert rows(pairs, "triton_cash") == EXPECTED_TC
    assert rows(other, "dining_dollars") == EXPECTED_DD and rows(other, "triton_cash") != EXPECTED_TC


# 7-9. Replenishments stay in the overall error; baseline is scored on the same pairs; exact metrics.
def test_replenishments_are_flagged_and_kept_in_overall_error():
    report = evaluate(fixture_rows(), TODAY, min_samples=1)
    dd = account(report, "dining_dollars")["overall"]
    tc = account(report, "triton_cash")["overall"]

    assert (dd["pairs"], dd["scored_pairs"], dd["pairs_without_model_prediction"]) == (6, 3, 3)
    assert dd["model"]["mae_cents"] == 1_500 and dd["model"]["median_abs_error_cents"] == 1_000
    assert dd["model"]["mean_signed_error_cents"] == -1_500
    assert dd["baseline"]["mae_cents"] == 666.67 and dd["baseline"]["median_abs_error_cents"] == 500
    assert dd["baseline"]["mean_signed_error_cents"] == 333.33
    assert (dd["model_closer_pairs"], dd["baseline_closer_pairs"], dd["tied_pairs"], dd["verdict"]) == (0, 2, 1, "worse")
    assert dd["replenishment"]["scored_pairs"] == 2 and dd["replenishment"]["model"]["mae_cents"] == 1_750
    assert dd["replenishment"]["baseline"]["mae_cents"] == 500
    assert dd["non_replenishment"]["scored_pairs"] == 1 and dd["non_replenishment"]["verdict"] == "about_the_same"

    assert tc["replenishment"]["pairs"] == 0
    assert tc["model"]["mae_cents"] == 500 and tc["model"]["median_abs_error_cents"] == 600 and tc["model"]["mean_signed_error_cents"] == 300
    assert tc["baseline"]["mae_cents"] == 400 and tc["baseline"]["mean_signed_error_cents"] == 400 and tc["verdict"] == "worse"


def test_baseline_uses_exactly_the_same_pairs_as_the_model():
    _, pairs, _ = backtest_pairs(fixture_rows(), TODAY)
    report = evaluate(fixture_rows(), TODAY, min_samples=1, include_pairs=True)

    for pair in pairs:
        assert pair.baseline_cents == pair.origin_cents and pair.baseline_error == pair.origin_cents - pair.actual_cents
    scored = [row for row in report["pairs"] if row["predicted_cents"] is not None]
    assert len(scored) == sum(item["overall"]["scored_pairs"] for item in report["accounts"]) == 6
    assert all(row["baseline_error_cents"] == row["baseline_cents"] - row["actual_cents"] for row in scored)


def _pair(model_error, baseline_error, replenishment=False):
    return Pair("dining_dollars", NOV(1), NOV(1), NOV(2), 1, 2, 10_000 + baseline_error, 10_000, 10_000 + model_error, replenishment, MODEL_VERSION)


def test_metrics_are_exact_on_a_hand_calculated_sample():
    summary = summarize([_pair(100, -200), _pair(-300, 200), _pair(200, 200), _pair(1_000, -600), _pair(-400, 300)])

    # Model |e| = 100, 300, 200, 1000, 400; baseline |e| = 200, 200, 200, 600, 300.
    assert summary["model"] == {
        "mae_cents": 400, "mae_dollars": 4.0, "median_abs_error_cents": 300, "median_abs_error_dollars": 3.0,
        "mean_signed_error_cents": 120, "mean_signed_error_dollars": 1.2,
    }
    assert summary["baseline"]["mae_cents"] == 300 and summary["baseline"]["median_abs_error_cents"] == 200
    assert summary["baseline"]["mean_signed_error_cents"] == -20
    assert (summary["model_closer_pairs"], summary["baseline_closer_pairs"], summary["tied_pairs"]) == (1, 3, 1)
    assert summary["verdict"] == "worse"
    # Even count: the median averages the two middle values.
    assert summarize([_pair(100, 0), _pair(300, 0)], min_samples=2)["model"]["median_abs_error_cents"] == 200
    # Within 5%: about the same, in either direction.
    assert summarize([_pair(1_000, 1_040)], min_samples=1)["verdict"] == "about_the_same"
    assert summarize([_pair(900, 1_000)], min_samples=1)["verdict"] == "better"


# 10. Not enough history: counts only, never accuracy.
def test_insufficient_history_reports_no_accuracy():
    report = evaluate(fixture_rows(), TODAY)  # default minimum of 5 scored pairs; this history has 3 per wallet
    dd = account(report, "dining_dollars")["overall"]
    assert report["status"] == "insufficient_data"
    assert (dd["status"], dd["pairs"], dd["scored_pairs"]) == ("insufficient_data", 6, 3)
    assert dd["model"] is dd["baseline"] is dd["verdict"] is None

    for history in ([], [checkin(NOV(1), 10_000, 1_000)], [checkin(NOV(1), 10_000, 1_000), checkin(NOV(1), 9_000, 1_000, hour=20)]):
        empty = evaluate(history, TODAY, min_samples=1)
        assert empty["status"] == "insufficient_data" and empty["origins"] == []
        assert all(item["overall"]["pairs"] == 0 and item["overall"]["model"] is None for item in empty["accounts"])


# 12. Versions: recorded from the predictor's own output, with the same cutoffs for a new algorithm.
def test_model_versions_are_recorded():
    report = evaluate(fixture_rows(), TODAY, min_samples=1, include_pairs=True)
    assert report["evaluation_type"] == "retrospective_backtest" and report["persisted_predictions_evaluated"] == 0
    assert report["model_version"] == MODEL_VERSION and report["model_versions"] == [MODEL_VERSION]
    assert report["evaluator_version"] == EVALUATOR_VERSION
    assert {row["model_version"] for row in report["pairs"]} == {MODEL_VERSION}
    assert evaluate([], TODAY)["model_version"] == MODEL_VERSION

    def candidate(observations, origin, days):
        return {**production_predictor(observations, origin, days), "model_version": "candidate.v2"}

    other = evaluate(fixture_rows(), TODAY, predictor=candidate, min_samples=1, include_pairs=True)
    assert other["model_version"] == "candidate.v2" and other["origins"] == report["origins"]
    assert [(r["origin"], r["target"], r["account"]) for r in other["pairs"]] == [(r["origin"], r["target"], r["account"]) for r in report["pairs"]]


# 11. API: each student gets only their own report; it is read-only and needs a session.
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


def test_api_reports_are_isolated_per_participant_and_read_only(students):
    today, (alice, a_token), (bob, b_token), factory = students  # noqa: F811
    for offset, dd, tc in ((4, 10_000, 5_000), (3, 9_000, 5_000), (1, 8_000, 4_400), (0, 8_500, 4_400)):
        _save(alice, a_token, today - timedelta(days=offset), dd, tc)
    _save(bob, b_token, today - timedelta(days=2), 777_777, 1)
    _save(bob, b_token, today, 700_000, 1)

    # Everything was just saved, so no earlier cutoff existed: nothing to score, however the dates look.
    backfilled = alice.get("/api/v1/pilot/prediction/backtest").json()
    assert backfilled["observation_count"] == 4 and backfilled["origins"] == [] and backfilled["status"] == "insufficient_data"

    # As if each balance had been saved on its own as-of day (noon Pacific).
    with factory() as session:
        for row in session.scalars(select(BalanceCheckin)).all():
            session.execute(update(BalanceCheckin).where(BalanceCheckin.id == row.id).values(
                created_at=datetime.combine(row.effective_date, datetime.min.time(), timezone.utc) + timedelta(hours=20)))
        session.commit()
        stored = session.scalar(select(func.count()).select_from(BalanceCheckin))

    mine = alice.get("/api/v1/pilot/prediction/backtest", params={"include_pairs": True})
    assert mine.status_code == 200, mine.text
    report = mine.json()
    assert report["observation_count"] == 4 and len(report["origins"]) == 3
    dd_rows = {(r["elapsed_days"], r["predicted_cents"], r["actual_cents"]) for r in report["pairs"] if r["account"] == "dining_dollars"}
    assert (2, 7_000, 8_000) in dd_rows and (1, 7_500, 8_500) in dd_rows
    assert all(r["actual_cents"] < 700_000 and r["origin_cents"] < 700_000 for r in report["pairs"])

    theirs = bob.get("/api/v1/pilot/prediction/backtest", params={"include_pairs": True}).json()
    assert theirs["observation_count"] == 2
    assert {r["actual_cents"] for r in theirs["pairs"]} == {700_000, 1}

    assert TestClient(app).get("/api/v1/pilot/prediction/backtest").status_code == 401
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(BalanceCheckin)) == stored


# Save-time availability: a backdated balance and a same-date correction saved after a cutoff cannot leak into it.
def test_late_backdated_saves_and_corrections_do_not_leak_into_earlier_cutoffs():
    late = datetime(2026, 11, 6, 20, tzinfo=timezone.utc)  # Nov 6, noon Pacific
    rows_ = fixture_rows() + [
        checkin(NOV(2), 9_500, 5_000, saved=late),  # same-date correction of Nov 2
        checkin(NOV(3), 8_200, 4_700, saved=late),  # backdated balance for Nov 3
    ]
    seen = {}

    def spy(observations, cutoff, days):
        seen[cutoff] = [(item.boundary, item.balances["dining_dollars"]) for item in observations]
        return production_predictor(observations, cutoff, days)

    truth, pairs, _ = backtest_pairs(rows_, TODAY, spy)

    # The corrections are part of today's truth...
    assert [(item.boundary, item.balances["dining_dollars"]) for item in truth] == [
        (NOV(1), 10_000), (NOV(2), 9_500), (NOV(3), 8_200), (NOV(4), 8_000), (NOV(5), 8_500)]
    # ...but the earlier cutoffs saw exactly what had been saved by then.
    assert seen == {
        NOV(1): [(NOV(1), 10_000)],
        NOV(2): [(NOV(1), 10_000), (NOV(2), 9_000)],
        NOV(4): [(NOV(1), 10_000), (NOV(2), 9_000), (NOV(4), 8_000)],
    }
    dd = {(p.origin, p.target): p for p in pairs if p.account == "dining_dollars"}
    # Predictions at those cutoffs are unchanged (Nov 3 is never an origin: it was never the latest known day).
    for origin, target, _, predicted, _, _, _, _ in EXPECTED_DD:
        assert dd[(origin, target)].predicted_cents == predicted
    assert {p.origin for p in pairs} == {NOV(1), NOV(2), NOV(4)}
    # The origin balance is the one known then (9_000, not the later 9_500); targets use today's best values.
    assert dd[(NOV(2), NOV(4))].origin_cents == 9_000 and dd[(NOV(2), NOV(4))].baseline_error == 1_000
    assert dd[(NOV(1), NOV(2))].actual_cents == 9_500
    # The backdated Nov 3 balance is still a legitimate later target: 9_000 - 1_000/day = 8_000 vs. 8_200.
    assert (dd[(NOV(2), NOV(3))].predicted_cents, dd[(NOV(2), NOV(3))].actual_cents, dd[(NOV(2), NOV(3))].model_error) == (8_000, 8_200, -200)
    assert dd[(NOV(2), NOV(3))].cutoff == NOV(2)


def test_a_late_correction_of_the_latest_day_moves_that_origin_to_the_later_cutoff():
    # Nov 2 is corrected on Nov 3, before any later day was saved: the Nov 2 origin uses the corrected value.
    rows_ = fixture_rows() + [checkin(NOV(2), 9_400, 5_000, saved=datetime(2026, 11, 3, 20, tzinfo=timezone.utc))]
    _, pairs, _ = backtest_pairs(rows_, TODAY)

    nov2 = [p for p in pairs if p.account == "dining_dollars" and p.origin == NOV(2)]
    assert {p.cutoff for p in nov2} == {NOV(3)} and {p.origin_cents for p in nov2} == {9_400}
    # Nov 1 -> 2 pace is now 600/day: 9_400 - 1_200 = 8_200 predicted for Nov 4.
    assert next(p for p in nov2 if p.target == NOV(4)).predicted_cents == 8_200
