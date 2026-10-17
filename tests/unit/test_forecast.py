from datetime import date
from fractions import Fraction

import pytest

from tritonspend.core.errors import InvalidForecastError
from tritonspend.core.forecast import (
    DEFAULT_SCENARIO_MULTIPLIERS,
    Scenario,
    SpendingScenario,
    default_scenario,
    forecast,
)
from tritonspend.core.habits import SpendingHabit
from tritonspend.core.models import DateRange, PaymentAccount, WalletBalances
from tritonspend.core.money import Money


TODAY = date(2026, 10, 16)


def balances(dining, cash):
    return WalletBalances(Money(dining), Money(cash))


def meal(price=100, accounts=(PaymentAccount.DINING_DOLLARS,)):
    return SpendingHabit("meal", Fraction(1), Money(price), accounts)


def test_forecast_includes_today_and_end_and_handles_start_before_today():
    result = forecast(
        DateRange(date(2026, 10, 1), date(2026, 10, 17), TODAY),
        balances(500, 0),
        [meal()],
        default_scenario(Scenario.EXPECTED),
    )

    assert [item.day for item in result.days] == [TODAY, date(2026, 10, 17)]


def test_scenarios_are_ordered_by_placeholder_multiplier():
    results = [
        forecast(
            DateRange(TODAY, TODAY, TODAY),
            balances(1_000, 0),
            [meal(100)],
            default_scenario(scenario),
        )
        for scenario in (Scenario.FRUGAL, Scenario.EXPECTED, Scenario.HIGHER)
    ]

    assert [result.days[0].expected_spending.cents for result in results] == [80, 100, 120]
    assert DEFAULT_SCENARIO_MULTIPLIERS[Scenario.FRUGAL] < DEFAULT_SCENARIO_MULTIPLIERS[Scenario.EXPECTED]


def test_forecast_uses_only_each_habits_eligible_account():
    result = forecast(
        DateRange(TODAY, TODAY, TODAY),
        balances(100, 500),
        [meal(200, (PaymentAccount.DINING_DOLLARS,))],
        default_scenario(Scenario.EXPECTED),
    )

    assert result.days[0].unfunded == Money(100)
    assert result.projected_balances == balances(0, 500)


def test_insufficient_funds_and_invariant_are_reported():
    result = forecast(
        DateRange(TODAY, date(2026, 10, 17), TODAY),
        balances(100, 0),
        [meal(75)],
        default_scenario(Scenario.EXPECTED),
    )

    assert result.total_unfunded == Money(50)
    assert result.funds_last is False
    assert all(
        item.expected_spending
        == item.paid_dining_dollars + item.paid_triton_cash + item.unfunded
        for item in result.days
    )


def test_daily_and_monday_weekly_limits_prorate_partial_weeks():
    result = forecast(
        DateRange(date(2026, 10, 16), date(2026, 10, 20), TODAY),
        balances(1_000, 500),
        [],
        default_scenario(Scenario.EXPECTED),
    )

    assert result.limits.daily == balances(200, 100)
    assert result.limits.weekly == {
        date(2026, 10, 12): balances(600, 300),
        date(2026, 10, 19): balances(400, 200),
    }


def test_rejects_missing_habits():
    with pytest.raises(InvalidForecastError):
        forecast(
            DateRange(TODAY, TODAY, TODAY),
            balances(100, 100),
            None,
            default_scenario(Scenario.EXPECTED),
        )


def test_custom_scenario_multiplier_is_supported():
    result = forecast(
        DateRange(TODAY, TODAY, TODAY),
        balances(100, 100),
        [meal(101)],
        SpendingScenario(Scenario.EXPECTED, Fraction(1, 2)),
    )

    assert result.days[0].expected_spending == Money(51)


def test_each_fractional_habit_is_rounded_before_separate_allocation():
    fractional_meal = SpendingHabit(
        "fractional meal",
        Fraction(1, 2),
        Money(1),
        (PaymentAccount.DINING_DOLLARS,),
    )
    result = forecast(
        DateRange(TODAY, TODAY, TODAY),
        balances(10, 0),
        [fractional_meal, fractional_meal],
        default_scenario(Scenario.EXPECTED),
    )

    assert result.days[0].expected_spending == Money(2)
    assert result.days[0].paid_dining_dollars == Money(2)
    assert result.days[0].unfunded == Money(0)


def test_adjacent_balance_decreases_equal_daily_funded_spending():
    result = forecast(
        DateRange(TODAY, date(2026, 10, 18), TODAY),
        balances(150, 100),
        [
            meal(75, (PaymentAccount.DINING_DOLLARS,)),
            meal(50, (PaymentAccount.TRITON_CASH,)),
        ],
        default_scenario(Scenario.EXPECTED),
    )

    previous = balances(150, 100)
    for item in result.days:
        assert previous.dining_dollars.cents - item.remaining_balances.dining_dollars.cents == item.paid_dining_dollars.cents
        assert previous.triton_cash.cents - item.remaining_balances.triton_cash.cents == item.paid_triton_cash.cents
        previous = item.remaining_balances
