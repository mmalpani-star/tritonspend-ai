from fractions import Fraction

import pytest

from tritonspend.core.errors import InvalidHabitError
from tritonspend.core.habits import (
    SpendingHabit,
    estimate_daily_spending,
    estimate_habit,
)
from tritonspend.core.models import PaymentAccount
from tritonspend.core.money import Money


def habit(frequency=Fraction(1, 2)):
    return SpendingHabit(
        "breakfast",
        frequency,
        Money(375),
        (PaymentAccount.DINING_DOLLARS,),
    )


def test_fractional_frequency_preserves_exact_expected_cents():
    assert estimate_habit(habit()) == Fraction(375, 2)


def test_daily_estimate_sums_multiple_habits_exactly():
    assert estimate_daily_spending([habit(), habit(Fraction(1, 3))]) == Fraction(625, 2)


@pytest.mark.parametrize(
    "invalid",
    [
        SpendingHabit("", Fraction(1), Money(100), (PaymentAccount.DINING_DOLLARS,)),
        SpendingHabit("meal", Fraction(-1), Money(100), (PaymentAccount.DINING_DOLLARS,)),
        SpendingHabit("meal", Fraction(1), Money(100), ()),
        SpendingHabit("meal", Fraction(1), Money(100), ("dining_dollars",)),
    ],
)
def test_invalid_habits_are_rejected(invalid):
    with pytest.raises(InvalidHabitError):
        estimate_habit(invalid)
