"""Strict translation between API DTOs and existing core models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from fractions import Fraction

from tritonspend.core.forecast import (
    DEFAULT_SCENARIO_MULTIPLIERS,
    ForecastResult,
    Scenario,
    SpendingScenario,
)
from tritonspend.core.habits import SpendingHabit
from tritonspend.core.models import DateRange, PaymentAccount, WalletBalances
from tritonspend.core.money import Money

from .schemas import (
    DailyForecastResponse,
    ForecastRequest,
    ForecastResponse,
    HabitRequest,
    LimitsResponse,
    WalletResponse,
    frequency_error,
)


@dataclass(frozen=True)
class CoreForecastInput:
    """Adapter-owned arguments for the existing core forecast function."""

    date_range: DateRange
    balances: WalletBalances
    habits: tuple[SpendingHabit, ...]
    scenario: SpendingScenario


def parse_frequency(value: str) -> Fraction:
    """Parse the strict fraction syntax accepted by the JSON contract."""
    if not isinstance(value, str):
        raise ValueError("frequency must be a string")
    error = frequency_error(value)
    if error:
        raise ValueError(error)
    parts = value.split("/")
    if len(parts) == 1:
        return Fraction(int(parts[0]), 1)
    return Fraction(int(parts[0]), int(parts[1]))


def _account(value: str) -> PaymentAccount:
    try:
        return PaymentAccount(value)
    except ValueError as exc:
        raise ValueError("unknown payment account") from exc


def _habit(value: HabitRequest) -> SpendingHabit:
    return SpendingHabit(
        name=value.name,
        frequency=parse_frequency(value.frequency),
        price=Money(value.price_cents),
        eligible_accounts=tuple(_account(account) for account in value.eligible_accounts),
    )


def _scenario(value: str) -> SpendingScenario:
    try:
        scenario = Scenario(value)
        return SpendingScenario(scenario, DEFAULT_SCENARIO_MULTIPLIERS[scenario])
    except (KeyError, ValueError) as exc:
        raise ValueError("unknown scenario") from exc


def to_core_input(request: ForecastRequest, today: date) -> CoreForecastInput:
    """Map a validated request and injected reference date into core inputs."""
    return CoreForecastInput(
        date_range=DateRange(request.start_date, request.end_date, today),
        balances=WalletBalances(
            dining_dollars=Money(request.dining_dollars_cents),
            triton_cash=Money(request.triton_cash_cents),
        ),
        habits=tuple(_habit(habit) for habit in request.habits),
        scenario=_scenario(request.scenario),
    )


def _wallet(value: WalletBalances) -> WalletResponse:
    return WalletResponse(
        dining_dollars_cents=value.dining_dollars.cents,
        triton_cash_cents=value.triton_cash.cents,
    )


def to_response(result: ForecastResult) -> ForecastResponse:
    """Map an existing core result without recalculating forecast values."""
    return ForecastResponse(
        scenario=result.scenario.name.value,
        multiplier=str(result.scenario.multiplier),
        days=[
            DailyForecastResponse(
                date=item.day,
                expected_spending_cents=item.expected_spending.cents,
                paid_dining_dollars_cents=item.paid_dining_dollars.cents,
                paid_triton_cash_cents=item.paid_triton_cash.cents,
                unfunded_cents=item.unfunded.cents,
                remaining_balances=_wallet(item.remaining_balances),
                funds_last=item.funds_last,
            )
            for item in result.days
        ],
        projected_balances=_wallet(result.projected_balances),
        total_unfunded_cents=result.total_unfunded.cents,
        funds_last=result.funds_last,
        limits=LimitsResponse(
            daily_wallet_runway_caps=_wallet(result.limits.daily),
            weekly_wallet_runway_caps={
                monday: _wallet(value)
                for monday, value in result.limits.weekly.items()
            },
        ),
    )
