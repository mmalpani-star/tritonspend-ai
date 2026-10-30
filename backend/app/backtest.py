"""Rolling-origin backtest of the personalized prediction model on one student's saved balances.

This is a retrospective simulation, not a record of what students were shown:
predictions served by ``GET /prediction`` are computed on request and never
stored, so there are no issued predictions to score. Every number here answers
"what would the current algorithm have predicted, given only the balances that
had actually been saved by the end of a past day?" (documented in HANDOFF.md).

- Truth: the student's current observation series from ``observations_from_checkins``
  (latest save per as-of date, placed on its day boundary). Nothing is fabricated
  for days without a save, and nothing is dropped: replenishments stay in.
- Availability: a check-in exists from the moment it was persisted (``created_at``,
  set by the server; ``observed_at`` can be client-supplied on the legacy route).
  Cutoffs are the ends of the Pacific days on which something was saved. At a
  cutoff the model gets only the check-ins saved by then (and dated no later than
  that day), through the same production dedup and day-boundary rules, and the
  production ``build_prediction``. A backdated balance or a same-date correction
  saved after the cutoff therefore cannot influence it.
- Origins: the latest boundary the model had at a cutoff. When several cutoffs
  share it (e.g. a later backdated save or a same-date correction of an older
  day), the last of them is used, so each origin is scored once with everything
  known before any later day was saved.
- Targets: each truth observation after the origin and within ``MAX_HORIZON_DAYS``.
  No check-in for a later boundary had been saved by the cutoff (or it would be
  the origin), so the target cannot have leaked into the input. The origin
  balance is the one known at the cutoff; the target is the current best value.
- Baseline: persistence, i.e. the balance stays at the origin balance. It is
  scored on exactly the same (origin, target, account) pairs as the model.
- Errors are predicted - actual in cents (positive = predicted more money left
  than there was). MAE, median absolute error, and mean signed error are reported
  per account, horizon bucket, replenishment split, and history size. Groups with
  fewer than ``min_samples`` pairs report counts only, never accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
from statistics import median
from typing import Callable, Optional, Sequence
from zoneinfo import ZoneInfo

from .models import BalanceCheckin
from .participant_forecast import ACCOUNTS, observation_boundary
from .personal_model import MODEL_VERSION, Observation, build_prediction, observations_from_checkins

EVALUATOR_VERSION = "rolling-origin.v2"
CAMPUS_TIME_ZONE = ZoneInfo("America/Los_Angeles")
# (label, shortest, longest) elapsed days; each bucket brackets its nominal horizon.
HORIZON_BUCKETS = (("1 day", 1, 1), ("3 days", 2, 4), ("7 days", 5, 10), ("14 days", 11, 21))
MAX_HORIZON_DAYS = HORIZON_BUCKETS[-1][2]
HISTORY_BUCKETS = (("1 observation", 1, 1), ("2 observations", 2, 2), ("3-4 observations", 3, 4), ("5-9 observations", 5, 9), ("10+ observations", 10, None))
MIN_SAMPLES = 5
# MAEs within 5% of each other (or 1 cent) are reported as about the same.
SAME_TOLERANCE = Fraction(1, 20)

# (observations the model may see, the origin day, days ahead it must cover) -> build_prediction-shaped result
Predictor = Callable[[Sequence[Observation], date, int], dict]


def production_predictor(observations: Sequence[Observation], today: date, horizon_days: int) -> dict:
    """The production model with no forecast selected, long enough to reach every target."""
    return build_prediction(observations, today, None, None, default_horizon_days=horizon_days)


@dataclass(frozen=True)
class Pair:
    account: str
    cutoff: date  # end of this Pacific day: only check-ins saved by then were visible
    origin: date  # boundary of the latest observation the model saw
    target: date  # boundary of the later observation it is scored against
    elapsed_days: int
    history_count: int  # observations the model saw
    origin_cents: int
    actual_cents: int
    predicted_cents: Optional[int]  # None when the model had no pace to predict with
    replenishment: bool  # the balance rose somewhere between origin and target
    model_version: str

    @property
    def baseline_cents(self) -> int:
        return self.origin_cents

    @property
    def model_error(self) -> Optional[int]:
        return None if self.predicted_cents is None else self.predicted_cents - self.actual_cents

    @property
    def baseline_error(self) -> int:
        return self.baseline_cents - self.actual_cents


def _point_boundary(point: dict) -> date:
    return point["date"] if point["moment"] == "start" else point["date"] + timedelta(days=1)


def _predicted_at(prediction: dict, account: str, boundary: date) -> Optional[int]:
    key = f"{account}_cents"
    for point in prediction["points"]:
        if _point_boundary(point) == boundary:
            return point["predicted"][key]
    return None


def _bucket(elapsed: int) -> Optional[str]:
    return next((label for label, low, high in HORIZON_BUCKETS if low <= elapsed <= high), None)


def _history_bucket(count: int) -> str:
    return next(label for label, low, high in HISTORY_BUCKETS if count >= low and (high is None or count <= high))


def saved_on(checkin: BalanceCheckin) -> date:
    """The Pacific calendar day the check-in was persisted, i.e. when it became available."""
    value = checkin.created_at
    value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return value.astimezone(CAMPUS_TIME_ZONE).date()


def backtest_pairs(
    checkins: Sequence[BalanceCheckin],
    today: date,
    predictor: Predictor = production_predictor,
) -> tuple[list[Observation], list[Pair], int]:
    """Truth series, scored pairs, and how many later observations fell beyond the longest horizon."""
    truth = observations_from_checkins(checkins, today)
    # What the model would have had at the end of each day something was saved; the last cutoff per origin wins.
    by_origin: dict[date, tuple[date, list[Observation]]] = {}
    for cutoff in sorted({saved_on(c) for c in checkins if saved_on(c) <= today}):
        visible = [c for c in checkins if saved_on(c) <= cutoff]
        history = observations_from_checkins(visible, min(cutoff, today))
        if history:
            by_origin[history[-1].boundary] = (cutoff, history)

    pairs: list[Pair] = []
    beyond = 0
    for origin, (cutoff, history) in sorted(by_origin.items()):
        latest = history[-1]
        later = [item for item in truth if item.boundary > origin]
        targets = [item for item in later if (item.boundary - origin).days <= MAX_HORIZON_DAYS]
        beyond += len(later) - len(targets)
        if not targets:
            continue
        saved_later = {observation_boundary(c) for c in checkins if saved_on(c) > cutoff}
        if any(item.boundary not in saved_later for item in targets):
            raise RuntimeError("backtest targets must come from check-ins saved after the cutoff")
        prediction = predictor(history, cutoff, (targets[-1].boundary - origin).days)
        for target in targets:
            steps = [latest.balances] + [item.balances for item in later if item.boundary <= target.boundary]
            for account in ACCOUNTS:
                pairs.append(Pair(
                    account=account,
                    cutoff=cutoff,
                    origin=origin,
                    target=target.boundary,
                    elapsed_days=(target.boundary - origin).days,
                    history_count=len(history),
                    origin_cents=latest.balances[account],
                    actual_cents=target.balances[account],
                    predicted_cents=_predicted_at(prediction, account, target.boundary),
                    replenishment=any(b[account] > a[account] for a, b in zip(steps, steps[1:])),
                    model_version=prediction["model_version"],
                ))
    return truth, pairs, beyond


def _errors(values: Sequence[int]) -> dict:
    absolute = [abs(value) for value in values]
    mae = Fraction(sum(absolute), len(absolute))
    signed = Fraction(sum(values), len(values))
    middle = Fraction(median(absolute))
    return {
        "mae_cents": round(float(mae), 2),
        "mae_dollars": round(float(mae) / 100, 2),
        "median_abs_error_cents": round(float(middle), 2),
        "median_abs_error_dollars": round(float(middle) / 100, 2),
        "mean_signed_error_cents": round(float(signed), 2),
        "mean_signed_error_dollars": round(float(signed) / 100, 2),
    }


def _verdict(model_mae: Fraction, baseline_mae: Fraction) -> str:
    if abs(model_mae - baseline_mae) <= max(SAME_TOLERANCE * baseline_mae, Fraction(1)):
        return "about_the_same"
    return "better" if model_mae < baseline_mae else "worse"


def summarize(pairs: Sequence[Pair], min_samples: int = MIN_SAMPLES) -> dict:
    """Model vs. baseline on the pairs where the model made a prediction."""
    scored = [pair for pair in pairs if pair.predicted_cents is not None]
    result = {
        "pairs": len(pairs),
        "scored_pairs": len(scored),
        "pairs_without_model_prediction": len(pairs) - len(scored),
        "elapsed_days_observed": sorted({pair.elapsed_days for pair in pairs}),
        "status": "ok" if len(scored) >= min_samples else "insufficient_data",
        "model": None,
        "baseline": None,
        "model_closer_pairs": None,
        "baseline_closer_pairs": None,
        "tied_pairs": None,
        "verdict": None,
    }
    if result["status"] != "ok":
        return result
    model = [pair.model_error for pair in scored]
    baseline = [pair.baseline_error for pair in scored]
    result["model"], result["baseline"] = _errors(model), _errors(baseline)
    result["model_closer_pairs"] = sum(abs(m) < abs(b) for m, b in zip(model, baseline))
    result["baseline_closer_pairs"] = sum(abs(m) > abs(b) for m, b in zip(model, baseline))
    result["tied_pairs"] = sum(abs(m) == abs(b) for m, b in zip(model, baseline))
    result["verdict"] = _verdict(
        Fraction(sum(map(abs, model)), len(model)), Fraction(sum(map(abs, baseline)), len(baseline))
    )
    return result


def _with_splits(pairs: Sequence[Pair], min_samples: int) -> dict:
    return {
        **summarize(pairs, min_samples),
        "replenishment": summarize([p for p in pairs if p.replenishment], min_samples),
        "non_replenishment": summarize([p for p in pairs if not p.replenishment], min_samples),
    }


def _pair_row(pair: Pair) -> dict:
    return {
        "account": pair.account,
        "cutoff": pair.cutoff,
        "origin": pair.origin,
        "target": pair.target,
        "elapsed_days": pair.elapsed_days,
        "horizon_bucket": _bucket(pair.elapsed_days),
        "history_count": pair.history_count,
        "origin_cents": pair.origin_cents,
        "actual_cents": pair.actual_cents,
        "predicted_cents": pair.predicted_cents,
        "baseline_cents": pair.baseline_cents,
        "model_error_cents": pair.model_error,
        "baseline_error_cents": pair.baseline_error,
        "replenishment": pair.replenishment,
        "model_version": pair.model_version,
    }


def evaluate(
    checkins: Sequence[BalanceCheckin],
    today: date,
    predictor: Predictor = production_predictor,
    min_samples: int = MIN_SAMPLES,
    include_pairs: bool = False,
) -> dict:
    """Backtest report for ONE participant's check-ins. Callers must pass only that participant's rows."""
    truth, pairs, beyond = backtest_pairs(checkins, today, predictor)
    versions = sorted({pair.model_version for pair in pairs})
    accounts = []
    for account in ACCOUNTS:
        mine = [pair for pair in pairs if pair.account == account]
        accounts.append({
            "account": account,
            "overall": _with_splits(mine, min_samples),
            "horizons": [
                {"bucket": label, "min_days": low, "max_days": high, **_with_splits([p for p in mine if low <= p.elapsed_days <= high], min_samples)}
                for label, low, high in HORIZON_BUCKETS
            ],
            "by_history": [
                {"bucket": label, **summarize([p for p in mine if _history_bucket(p.history_count) == label], min_samples)}
                for label, _, _ in HISTORY_BUCKETS
            ],
        })
    report = {
        "evaluation_type": "retrospective_backtest",
        "description": (
            "Simulated predictions from the current algorithm using only balances that had been saved by each past "
            "cutoff. These are not predictions that were shown at the time; those are not stored."
        ),
        "evaluator_version": EVALUATOR_VERSION,
        # Recorded per pair from the predictor's own output; a mix would mean the predictor changed mid-run.
        "model_version": versions[0] if len(versions) == 1 else (MODEL_VERSION if not versions and predictor is production_predictor else None),
        "model_versions": versions,
        "persisted_predictions_evaluated": 0,
        "today": today,
        "settings": {
            "horizon_buckets": [{"bucket": label, "min_days": low, "max_days": high} for label, low, high in HORIZON_BUCKETS],
            "max_horizon_days": MAX_HORIZON_DAYS,
            "min_samples": min_samples,
            "same_tolerance": float(SAME_TOLERANCE),
            "error_sign": "predicted minus actual; positive means the prediction left more money than there was",
            "baseline": "persistence: the balance stays at the origin balance",
            "availability": "a check-in counts from the end of the Pacific day it was saved (created_at), whatever its as-of date",
        },
        "observation_count": len(truth),
        "first_boundary": truth[0].boundary if truth else None,
        "last_boundary": truth[-1].boundary if truth else None,
        "origins": sorted({pair.origin for pair in pairs}),
        "later_observations_beyond_max_horizon": beyond,
        "status": "ok" if any(item["overall"]["status"] == "ok" for item in accounts) else "insufficient_data",
        "accounts": accounts,
    }
    if include_pairs:
        report["pairs"] = [_pair_row(pair) for pair in pairs]
    return report
