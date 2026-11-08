"""Turn saved participant wallet balances into forecast inputs and trajectories.

Policies (also documented in HANDOFF.md):

- Saved forecasts start from the latest saved balances exactly as entered;
  ledger entries are not applied and nothing is inferred (no balances, no forecast).
- Balances saved through the wallet (``source == "wallet"``) are accurate on
  their as-of date before that day's spending, so the forecast starts ON the
  as-of date (snapshot schema v3).
- Older check-ins (any other source) are end-of-day balances, so forecasts from
  them start the day AFTER the as-of date (schema v2), as before.
- Days between the as-of date and today are projected from habits, never
  assumed to have had no spending.
- Snapshot schema v1 (legacy) reconciled the latest check-in with later ledger
  entries via ``reconcile``; v1 and v2 snapshots stay readable and chartable.

Trajectories are plotted on balance "boundaries": boundary 0 is the start of
the first forecast day (the starting balance) and boundary k is the end of
forecast day k, so the axis covers exactly the forecast's dates.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from typing import Optional, Sequence

from tritonspend.core.money import to_stored_cents

from .models import Account, BalanceCheckin, EntryType, LedgerEntry
from .schemas import MAX_FORECAST_DAYS


WALLET_SOURCE = "wallet"
SNAPSHOT_SCHEMA_VERSION = "participant-forecast.v3"
END_OF_DAY_SNAPSHOT_SCHEMA_VERSION = "participant-forecast.v2"
LEGACY_SNAPSHOT_SCHEMA_VERSION = "participant-forecast.v1"
CHARTABLE_SCHEMA_VERSIONS = frozenset(
    {SNAPSHOT_SCHEMA_VERSION, END_OF_DAY_SNAPSHOT_SCHEMA_VERSION, LEGACY_SNAPSHOT_SCHEMA_VERSION}
)
# Bump when the core engine or the starting-balance policy above changes output.
ENGINE_VERSION = "tritonspend-core-0.1.0+participant-forecast.v3"
END_OF_DAY_ENGINE_VERSION = "tritonspend-core-0.1.0+participant-forecast.v2"
STALE_BASELINE_DAYS = 14
MAX_PARTICIPANT_FORECAST_DAYS = MAX_FORECAST_DAYS  # same limit as anonymous forecasts
ACCOUNTS = ("dining_dollars", "triton_cash")
ACCOUNT_LABELS = {"dining_dollars": "Dining Dollars", "triton_cash": "Triton Cash"}
_SIGN = {EntryType.spending: -1, EntryType.deposit: 1, EntryType.refund: 1}


class ReconciliationError(ValueError):
    """Recorded data cannot produce a trustworthy starting balance."""


@dataclass(frozen=True)
class Reconciliation:
    baseline: BalanceCheckin
    applied_entries: tuple[LedgerEntry, ...]
    balances: dict[str, int]
    warnings: tuple[str, ...]


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) // 100}.{abs(cents) % 100:02d}"


def forecast_start(checkin: BalanceCheckin) -> date:
    """First forecast day for balances saved in ``checkin`` (see the module policy)."""
    if checkin.source == WALLET_SOURCE:
        return checkin.effective_date
    return checkin.effective_date + timedelta(days=1)


def observation_boundary(checkin: BalanceCheckin) -> date:
    """The day whose START this saved balance describes."""
    return forecast_start(checkin)


def wallet_start_warnings(as_of: date, today: date, start: date) -> tuple[str, ...]:
    """Plain-language notes about starting a forecast on ``start`` from balances saved on ``as_of``."""
    age = (today - as_of).days
    warnings = []
    if age > STALE_BASELINE_DAYS:
        warnings.append(
            f"Your saved wallet balances are {age} days old (as of {as_of.isoformat()}). "
            "Update them for a more reliable forecast."
        )
    if age > 0:
        warnings.append(
            f"Your wallet balances are as of {as_of.isoformat()}, so this forecast starts on "
            f"{start.isoformat()}. Spending since then is projected from your habits, not observed."
        )
    return tuple(warnings)


def reconcile(
    baseline: BalanceCheckin,
    entries: Sequence[LedgerEntry],
    as_of: date,
) -> Reconciliation:
    """Legacy (v1): apply ledger entries recorded after ``baseline`` through ``as_of``."""
    if baseline.effective_date > as_of:
        raise ReconciliationError("the balance check-in is dated after the forecast reference date")
    balances = {
        "dining_dollars": baseline.dining_dollars_cents,
        "triton_cash": baseline.triton_cash_cents,
    }
    applied = []
    same_day = 0
    for entry in entries:
        if entry.occurred_on < baseline.effective_date or entry.occurred_on > as_of:
            continue
        if entry.occurred_on == baseline.effective_date:
            same_day += 1
            continue
        balances[Account(entry.account).value] += _SIGN[EntryType(entry.entry_type)] * entry.amount_cents
        applied.append(entry)

    inconsistent = [account for account in ACCOUNTS if balances[account] < 0]
    if inconsistent:
        raise ReconciliationError(
            " ".join(
                f"{ACCOUNT_LABELS[account]} reconciles to {format_cents(balances[account])}: "
                f"ledger entries after the {baseline.effective_date.isoformat()} check-in "
                "exceed the recorded balance."
                for account in inconsistent
            )
            + " Record a new balance check-in or correct the ledger before forecasting."
        )

    warnings = []
    age = (as_of - baseline.effective_date).days
    if age > STALE_BASELINE_DAYS:
        warnings.append(
            f"The latest balance check-in is {age} days old "
            f"({baseline.effective_date.isoformat()}). Record a new check-in for a more reliable forecast."
        )
    if same_day:
        noun = "ledger entry is" if same_day == 1 else "ledger entries are"
        warnings.append(
            f"{same_day} {noun} dated {baseline.effective_date.isoformat()}, the check-in day, "
            "and assumed to be already reflected in that check-in balance."
        )
    return Reconciliation(baseline, tuple(applied), balances, tuple(warnings))


def ideal_balance(start: int, target: int, as_of: date, end: date, day: date) -> Optional[int]:
    """Even spend-down from ``start`` on ``as_of`` to ``target`` on ``end``.

    Returns None when the start is already below the target, because no
    spend-down path exists.
    """
    if start < target:
        return None
    span = (end - as_of).days
    elapsed = (day - as_of).days
    return to_stored_cents(Fraction(start) - Fraction(start - target) * elapsed / span)


def _wallet_or_none(value: object) -> Optional[dict[str, int]]:
    if isinstance(value, dict) and all(isinstance(value.get(f"{account}_cents"), int) for account in ACCOUNTS):
        return {f"{account}_cents": value[f"{account}_cents"] for account in ACCOUNTS}
    return None


def build_trajectory(
    forecast_id: str,
    inputs: dict,
    forecast: dict,
    checkins: Sequence[BalanceCheckin],
) -> dict:
    """Combine one stored snapshot with saved balances into chart points.

    Every value comes from this snapshot or from saved balances: ``projected``
    is the stored daily output, ``ideal`` uses the stored starting balances and
    targets, and ``actual`` holds only balances saved for that exact boundary
    (never interpolated).
    """
    start_date = date.fromisoformat(inputs["start_date"])
    end_date = date.fromisoformat(inputs["end_date"])
    # v2/v3 store "starting_balances"; legacy v1 snapshots stored "reconciled_balances".
    starting = _wallet_or_none(inputs.get("starting_balances", inputs.get("reconciled_balances")))
    if starting is None:
        raise ValueError("snapshot is missing starting balances")
    stored_targets = _wallet_or_none(inputs.get("targets"))

    targets = []
    for account in ACCOUNTS:
        start = starting[f"{account}_cents"]
        if stored_targets is not None:
            target, basis = stored_targets[f"{account}_cents"], "threshold"
            described = f"the {format_cents(target)} warning amount saved with this forecast"
        else:
            target, basis = 0, "zero"
            described = "$0.00 because no warning amount was set when this forecast was saved"
        available = start >= target
        targets.append({
            "account": account,
            "target_cents": target,
            "basis": basis,
            "ideal_available": available,
            "explanation": (
                f"Ideal: spend evenly from {format_cents(start)} at the start of {start_date.isoformat()} "
                f"down to {described} by the end of {end_date.isoformat()}."
                if available
                else f"No ideal path: the starting balance {format_cents(start)} is already below {described}."
            ),
        })

    projected = {
        date.fromisoformat(day["date"]): _wallet_or_none(day.get("remaining_balances"))
        for day in forecast.get("days", [])
    }
    final_boundary = end_date + timedelta(days=1)
    latest_by_boundary: dict[date, BalanceCheckin] = {}
    for checkin in sorted(checkins, key=lambda value: (value.observed_at, value.created_at)):
        boundary = observation_boundary(checkin)
        if start_date <= boundary <= final_boundary:
            latest_by_boundary[boundary] = checkin

    span = (final_boundary - start_date).days
    points = []
    for offset in range(span + 1):
        boundary = start_date + timedelta(days=offset)
        # Boundary 0 is the start of the first day; boundary k is the end of day k.
        day, moment = (start_date, "start") if offset == 0 else (boundary - timedelta(days=1), "end")
        checkin = latest_by_boundary.get(boundary)
        points.append({
            "date": day,
            "moment": moment,
            "actual": (
                {
                    "dining_dollars_cents": checkin.dining_dollars_cents,
                    "triton_cash_cents": checkin.triton_cash_cents,
                }
                if checkin is not None
                else None
            ),
            "actual_as_of": checkin.effective_date if checkin is not None else None,
            "projected": dict(starting) if offset == 0 else projected.get(day),
            "ideal": {
                f"{item['account']}_cents": ideal_balance(
                    starting[f"{item['account']}_cents"], item["target_cents"], start_date, final_boundary, boundary
                )
                for item in targets
            },
        })
    return {
        "forecast_id": forecast_id,
        "schema_version": inputs.get("schema_version"),
        "as_of": date.fromisoformat(inputs["reference_date"]),
        "start_date": start_date,
        "end_date": end_date,
        "starting_balances": starting,
        "targets": targets,
        "points": points,
    }
