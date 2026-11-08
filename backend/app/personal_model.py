"""Personalized wallet-balance prediction learned from one student's saved balances.

This is a deterministic, per-student statistical model (documented in HANDOFF.md):

- Inputs are only the student's own saved wallet balances (``balance_checkins``),
  never ledger entries, habits, or anyone else's data. For each as-of date the
  latest save wins; every save stays stored. Each save is placed on the day
  boundary it describes (wallet saves: start of their as-of day; older end-of-day
  check-ins: start of the following day) and sorted chronologically.
- Each wallet is modelled separately. Between consecutive observations the net
  daily depletion is (previous - new) / elapsed days. An interval where the
  balance went UP is a possible deposit, refund, or transfer: it is reported as a
  replenishment and excluded from the pace, never treated as negative spending.
- The predicted pace is a recency-weighted median of interval paces. Each
  interval's weight is its length in days times 0.5 ** (age / 21 days), where
  age is measured from the interval's end to the latest observation. The median
  limits the pull of extreme intervals without dropping them; unusually fast
  intervals (pace > median + 3 * max(MAD, median / 2)) are flagged.
- With 3+ usable intervals, the slower and faster paths are the weighted 25th
  and 75th percentile paces ("learned range"). With 1-2 intervals they are
  +/-25% sensitivity paths around the preliminary pace and labelled as such.
- Every path starts at the latest observed balance, drops by its pace each day,
  and never goes below $0.00. Amounts are integer cents (ties round away from 0).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
from typing import Optional, Sequence

from tritonspend.core.money import to_stored_cents

from .models import BalanceCheckin
from .participant_forecast import ACCOUNTS, observation_boundary

MODEL_VERSION = "personal-pace.v1"
HALF_LIFE_DAYS = 21
SENSITIVITY = Fraction(1, 4)
MIN_INTERVALS_FOR_RANGE = 3
UNUSUAL_SPREAD_MULTIPLIER = 3


@dataclass(frozen=True)
class Observation:
    boundary: date  # the day whose start this balance describes
    as_of: date
    observed_at: datetime
    balances: dict[str, int]


@dataclass(frozen=True)
class Interval:
    start: date
    end: date
    days: int
    start_cents: int
    end_cents: int

    @property
    def change_cents(self) -> int:
        return self.end_cents - self.start_cents

    @property
    def pace(self) -> Optional[Fraction]:
        """Net depletion in cents per day; None for a balance increase."""
        if self.change_cents > 0:
            return None
        return Fraction(-self.change_cents, self.days)


@dataclass(frozen=True)
class AccountModel:
    account: str
    latest_cents: Optional[int]
    confidence: str  # none | starting | preliminary | developing | established
    usable_intervals: tuple[Interval, ...]
    replenishments: tuple[Interval, ...]
    unusual: tuple[Interval, ...]
    pace: Optional[Fraction]
    lower_pace: Optional[Fraction]
    higher_pace: Optional[Fraction]
    range_basis: Optional[str]  # learned_range | sensitivity
    span_days: int


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def observations_from_checkins(checkins: Sequence[BalanceCheckin], today: date) -> list[Observation]:
    """The latest valid save per as-of date, placed on its boundary and sorted."""
    order = lambda value: (value.effective_date, _utc(value.observed_at), _utc(value.created_at), value.id)  # noqa: E731
    latest_per_date: dict[date, BalanceCheckin] = {}
    for value in sorted((c for c in checkins if c.effective_date <= today), key=order):
        latest_per_date[value.effective_date] = value
    # Two dates can describe the same boundary (an end-of-day check-in and the next
    # day's wallet save); the later save wins there too.
    by_boundary: dict[date, BalanceCheckin] = {}
    for value in sorted(latest_per_date.values(), key=lambda v: (_utc(v.observed_at), _utc(v.created_at), v.id)):
        by_boundary[observation_boundary(value)] = value
    return [
        Observation(
            boundary=boundary,
            as_of=value.effective_date,
            observed_at=_utc(value.observed_at),
            balances={"dining_dollars": value.dining_dollars_cents, "triton_cash": value.triton_cash_cents},
        )
        for boundary, value in sorted(by_boundary.items())
    ]


def weighted_quantile(values: Sequence[Fraction], weights: Sequence[float], q: Fraction) -> Fraction:
    """The smallest value whose cumulative weight reaches ``q`` of the total."""
    pairs = sorted(zip(values, weights), key=lambda pair: pair[0])
    total = sum(weight for _, weight in pairs)
    cumulative = 0.0
    for value, weight in pairs:
        cumulative += weight
        if cumulative >= float(q) * total - 1e-12:
            return value
    return pairs[-1][0]


def fit_account(observations: Sequence[Observation], account: str) -> AccountModel:
    if not observations:
        return AccountModel(account, None, "none", (), (), (), None, None, None, None, 0)
    latest = observations[-1]
    span = (latest.boundary - observations[0].boundary).days
    intervals = [
        Interval(a.boundary, b.boundary, (b.boundary - a.boundary).days, a.balances[account], b.balances[account])
        for a, b in zip(observations, observations[1:])
    ]
    usable = tuple(item for item in intervals if item.pace is not None)
    replenishments = tuple(item for item in intervals if item.pace is None)
    if not usable:
        return AccountModel(account, latest.balances[account], "starting", (), replenishments, (), None, None, None, None, span)

    paces = [item.pace for item in usable]
    weights = [item.days * 0.5 ** ((latest.boundary - item.end).days / HALF_LIFE_DAYS) for item in usable]
    pace = weighted_quantile(paces, weights, Fraction(1, 2))
    if len(usable) >= MIN_INTERVALS_FOR_RANGE:
        lower, higher, basis = weighted_quantile(paces, weights, Fraction(1, 4)), weighted_quantile(paces, weights, Fraction(3, 4)), "learned_range"
    else:
        lower, higher, basis = pace * (1 - SENSITIVITY), pace * (1 + SENSITIVITY), "sensitivity"
    spread = weighted_quantile([abs(value - pace) for value in paces], weights, Fraction(1, 2))
    limit = pace + UNUSUAL_SPREAD_MULTIPLIER * max(spread, pace / 2)
    unusual = tuple(item for item in usable if item.pace > limit)

    if len(usable) <= 2 or span < 7:
        confidence = "preliminary"
    elif len(usable) >= 5 and span >= 21 and higher - lower <= max(pace, Fraction(1)):
        confidence = "established"
    else:
        confidence = "developing"
    return AccountModel(account, latest.balances[account], confidence, usable, replenishments, unusual, pace, lower, higher, basis, span)


def path(start_cents: int, pace: Fraction, steps: int) -> list[int]:
    """Balances at boundaries 0..steps when dropping by ``pace`` per day, floored at $0.00."""
    return [to_stored_cents(max(Fraction(0), Fraction(start_cents) - pace * step)) for step in range(steps + 1)]


def cents_per_day(value: Optional[Fraction]) -> Optional[float]:
    return None if value is None else round(float(value), 2)


CONFIDENCE_TEXT = {
    "none": "No saved balances yet, so there's nothing to learn from.",
    "starting": "Your starting balance is saved. Save another balance on a later day so the model can see how it changes.",
    "preliminary": "A first estimate from very little history. Keep updating your balances to make it more personal.",
    "developing": "Learning from several balance updates. More updates over more weeks will make it steadier.",
    "established": "Based on a consistent history of balance updates over several weeks.",
}


def build_prediction(
    observations: Sequence[Observation],
    today: date,
    comparison: Optional[dict],
    current_targets: Optional[dict[str, int]],
    default_horizon_days: int = 30,
    lookback_days: int = 90,
) -> dict:
    """Chart-ready prediction. ``comparison`` describes the selected saved forecast (or None).

    Date rule: points are day boundaries. Point 0 is the start of the axis' first
    day and point k is the end of day (axis start + k - 1). Predictions and the
    ideal line start at the latest observation's boundary and end at the end of
    the horizon: the selected forecast's end date when it is on or after the
    latest observation, otherwise ``default_horizon_days`` from it.
    """
    models = {account: fit_account(observations, account) for account in ACCOUNTS}
    if comparison is not None and comparison.get("targets") is not None:
        targets, target_basis = comparison["targets"], "forecast_threshold"
    elif comparison is not None:
        targets, target_basis = None, "zero"
    elif current_targets is not None:
        targets, target_basis = current_targets, "current_threshold"
    else:
        targets, target_basis = None, "zero"
    target_cents = {account: (targets[f"{account}_cents"] if targets else 0) for account in ACCOUNTS}

    result = {
        "model_version": MODEL_VERSION,
        "today": today,
        "observation_count": len(observations),
        "latest": None,
        "horizon": None,
        "comparison": comparison and {key: comparison[key] for key in ("id", "created_at", "start_date", "end_date", "scenario")},
        "accounts": [],
        "points": [],
    }
    if not observations:
        result["accounts"] = [_account_summary(models[a], target_cents[a], target_basis, None, None, None) for a in ACCOUNTS]
        return result

    latest = observations[-1]
    first_boundary = latest.boundary
    if comparison is not None and comparison["end_date"] >= latest.boundary:
        horizon_end, horizon_rule = comparison["end_date"], "selected_forecast_end"
    else:
        horizon_end, horizon_rule = latest.boundary + timedelta(days=default_horizon_days - 1), "default"
    final = horizon_end + timedelta(days=1)
    axis_start = max(observations[0].boundary, latest.boundary - timedelta(days=lookback_days))
    if comparison is not None:
        axis_start = min(axis_start, comparison["start_date"])
    axis_start = max(axis_start, final - timedelta(days=730))
    steps = (final - axis_start).days
    offset = (first_boundary - axis_start).days
    ahead = (final - first_boundary).days

    plan = comparison.get("plan", {}) if comparison else {}
    observed = {item.boundary: item for item in observations if item.boundary >= axis_start}
    series = {}
    for account in ACCOUNTS:
        model = models[account]
        start = latest.balances[account]
        series[account] = {
            "predicted": path(start, model.pace, ahead) if model.pace is not None else None,
            "lower": path(start, model.lower_pace, ahead) if model.lower_pace is not None else None,
            "higher": path(start, model.higher_pace, ahead) if model.higher_pace is not None else None,
            "ideal": (
                [_even(start, target_cents[account], step, ahead) for step in range(ahead + 1)]
                if start >= target_cents[account]
                else None
            ),
        }

    points = []
    for k in range(steps + 1):
        boundary = axis_start + timedelta(days=k)
        day, moment = (axis_start, "start") if k == 0 else (boundary - timedelta(days=1), "end")
        seen = observed.get(boundary)
        j = k - offset
        point = {"date": day, "moment": moment, "actual_as_of": seen.as_of if seen else None}
        for name in ("actual", "predicted", "lower", "higher", "ideal", "original_plan"):
            point[name] = {}
        for account in ACCOUNTS:
            key = f"{account}_cents"
            point["actual"][key] = seen.balances[account] if seen else None
            for name in ("predicted", "lower", "higher", "ideal"):
                values = series[account][name]
                point[name][key] = values[j] if values is not None and j >= 0 else None
            point["original_plan"][key] = plan.get(boundary, {}).get(key)
        points.append(point)

    result["latest"] = {
        "as_of": latest.as_of,
        "boundary": latest.boundary,
        "observed_at": latest.observed_at,
        "balances": {f"{a}_cents": latest.balances[a] for a in ACCOUNTS},
    }
    result["horizon"] = {"start": latest.boundary, "end_date": horizon_end, "rule": horizon_rule, "days": ahead}
    result["accounts"] = [
        _account_summary(models[a], target_cents[a], target_basis, series[a], latest.boundary, horizon_end) for a in ACCOUNTS
    ]
    result["points"] = points
    return result


def _even(start: int, target: int, step: int, steps: int) -> int:
    if steps == 0:
        return start
    return to_stored_cents(Fraction(start) - Fraction(start - target) * step / steps)


def _account_summary(model: AccountModel, target: int, target_basis: str, series, start: Optional[date], end: Optional[date]) -> dict:
    predicted = series["predicted"] if series else None
    runs_out_on = None
    if predicted is not None and start is not None:
        for step, value in enumerate(predicted):
            if value == 0 and step > 0:
                runs_out_on = start + timedelta(days=step - 1)  # end of that day
                break
    return {
        "account": model.account,
        "latest_cents": model.latest_cents,
        "confidence": model.confidence,
        "confidence_text": CONFIDENCE_TEXT[model.confidence],
        "usable_interval_count": len(model.usable_intervals),
        "span_days": model.span_days,
        "daily_pace_cents": cents_per_day(model.pace),
        "lower_pace_cents": cents_per_day(model.lower_pace),
        "higher_pace_cents": cents_per_day(model.higher_pace),
        "range_basis": model.range_basis,
        "predicted_end_cents": predicted[-1] if predicted else None,
        "lower_end_cents": series["lower"][-1] if series and series["lower"] else None,
        "higher_end_cents": series["higher"][-1] if series and series["higher"] else None,
        "runs_out_on": runs_out_on,
        "target_cents": target,
        "target_basis": target_basis,
        "ideal_available": model.latest_cents is not None and model.latest_cents >= target,
        "replenishments": [
            {"from_boundary": item.start, "to_boundary": item.end, "increase_cents": item.change_cents} for item in model.replenishments
        ],
        "unusual_changes": [
            {"from_boundary": item.start, "to_boundary": item.end, "daily_pace_cents": cents_per_day(item.pace)} for item in model.unusual
        ],
    }
