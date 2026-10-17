"""Deterministic date-by-date dining budget forecasts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from fractions import Fraction
from typing import Dict, Iterable, Tuple

from .errors import InvalidForecastError
from .habits import SpendingHabit, estimate_habit, validate_habit
from .models import DateRange, WalletBalances
from .money import Money, to_stored_cents
from .timeline import iter_dates
from .validation import validate_wallet_balances
from .wallet import AllocationResult, allocate_expense
from .models import Expense


class Scenario(Enum):
    """Named placeholder spending multipliers, not calibrated probabilities."""

    FRUGAL = "frugal"
    EXPECTED = "expected"
    HIGHER = "higher"


DEFAULT_SCENARIO_MULTIPLIERS = {
    Scenario.FRUGAL: Fraction(4, 5),
    Scenario.EXPECTED: Fraction(1),
    Scenario.HIGHER: Fraction(6, 5),
}


@dataclass(frozen=True)
class SpendingScenario:
    name: Scenario
    multiplier: Fraction


def default_scenario(scenario: Scenario) -> SpendingScenario:
    if not isinstance(scenario, Scenario):
        raise InvalidForecastError("scenario must be a Scenario")
    return SpendingScenario(scenario, DEFAULT_SCENARIO_MULTIPLIERS[scenario])


@dataclass(frozen=True)
class SpendingLimits:
    daily: WalletBalances
    weekly: Dict[date, WalletBalances]


@dataclass(frozen=True)
class DailyForecast:
    day: date
    expected_spending: Money
    paid_dining_dollars: Money
    paid_triton_cash: Money
    unfunded: Money
    remaining_balances: WalletBalances
    funds_last: bool


@dataclass(frozen=True)
class ForecastResult:
    scenario: SpendingScenario
    days: Tuple[DailyForecast, ...]
    projected_balances: WalletBalances
    total_unfunded: Money
    funds_last: bool
    limits: SpendingLimits


def _validate_scenario(scenario: SpendingScenario) -> None:
    if not isinstance(scenario, SpendingScenario):
        raise InvalidForecastError("scenario configuration is required")
    if not isinstance(scenario.name, Scenario):
        raise InvalidForecastError("scenario name must be a Scenario")
    if not isinstance(scenario.multiplier, Fraction) or scenario.multiplier < 0:
        raise InvalidForecastError("scenario multiplier must be non-negative")


def _weekly_limits(
    date_list: Tuple[date, ...],
    daily: WalletBalances,
) -> Dict[date, WalletBalances]:
    counts: Dict[date, int] = {}
    for day in date_list:
        monday = day - timedelta(days=day.weekday())
        counts[monday] = counts.get(monday, 0) + 1
    return {
        monday: WalletBalances(
            Money(daily.dining_dollars.cents * count),
            Money(daily.triton_cash.cents * count),
        )
        for monday, count in counts.items()
    }


def _limits(
    balances: WalletBalances,
    date_list: Tuple[date, ...],
) -> SpendingLimits:
    day_count = len(date_list)
    daily = WalletBalances(
        Money(balances.dining_dollars.cents // day_count),
        Money(balances.triton_cash.cents // day_count),
    )
    return SpendingLimits(daily=daily, weekly=_weekly_limits(date_list, daily))


def forecast(
    date_range: DateRange,
    balances: WalletBalances,
    habits: Iterable[SpendingHabit],
    scenario: SpendingScenario,
) -> ForecastResult:
    """Forecast projected dates using explicit habit eligibility and wallets."""
    validate_wallet_balances(balances)
    _validate_scenario(scenario)
    if habits is None:
        raise InvalidForecastError("habits are required")
    habit_list = tuple(habits)
    for habit in habit_list:
        validate_habit(habit)
    date_list = tuple(iter_dates(date_range))
    if not date_list:
        raise InvalidForecastError("forecast must contain at least one date")

    current = balances
    daily_results = []
    total_unfunded = 0
    for day in date_list:
        paid_dining = 0
        paid_cash = 0
        unfunded = 0
        expected_cents = 0
        for habit in habit_list:
            expected = estimate_habit(habit) * scenario.multiplier
            amount = Money(to_stored_cents(expected))
            expected_cents += amount.cents
            allocation = allocate_expense(
                current,
                Expense(amount, habit.eligible_accounts),
            )
            current = allocation.remaining_balances
            paid_dining += allocation.paid_dining_dollars.cents
            paid_cash += allocation.paid_triton_cash.cents
            unfunded += allocation.unfunded.cents
        total_unfunded += unfunded
        daily_results.append(
            DailyForecast(
                day=day,
                expected_spending=Money(expected_cents),
                paid_dining_dollars=Money(paid_dining),
                paid_triton_cash=Money(paid_cash),
                unfunded=Money(unfunded),
                remaining_balances=current,
                funds_last=unfunded == 0,
            )
        )

    return ForecastResult(
        scenario=scenario,
        days=tuple(daily_results),
        projected_balances=current,
        total_unfunded=Money(total_unfunded),
        funds_last=total_unfunded == 0,
        limits=_limits(balances, date_list),
    )
