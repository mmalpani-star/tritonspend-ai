from fractions import Fraction

import pytest

from tritonspend.core.errors import InvalidMoneyError
from tritonspend.core.money import Money, to_stored_cents


def test_money_keeps_integer_cents_and_exact_fractional_expectation():
    meal = Money(375)

    assert meal.expected(Fraction(1, 2)) == Fraction(375, 2)
    assert to_stored_cents(Fraction(375, 2)) == 188


@pytest.mark.parametrize("value", [-1, 1.5, True])
def test_money_rejects_invalid_cents(value):
    with pytest.raises(InvalidMoneyError):
        Money(value)


def test_money_subtraction_cannot_cross_zero():
    with pytest.raises(InvalidMoneyError):
        Money(10) - Money(11)
