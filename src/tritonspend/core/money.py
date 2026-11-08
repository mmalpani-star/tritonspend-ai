"""Exact integer-cent money primitives."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from numbers import Integral

from .errors import InvalidMoneyError


def _require_cents(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
        raise InvalidMoneyError("cents must be a non-negative integer")
    return int(value)


@dataclass(frozen=True)
class Money:
    """A non-negative amount represented exactly as integer cents."""

    cents: int

    def __post_init__(self) -> None:
        _require_cents(self.cents)

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        return Money(self.cents + other.cents)

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.cents < other.cents:
            raise InvalidMoneyError("money cannot become negative")
        return Money(self.cents - other.cents)

    def expected(self, frequency: Fraction) -> Fraction:
        """Return exact expected cents for a non-negative rational frequency."""
        if not isinstance(frequency, Fraction) or frequency < 0:
            raise InvalidMoneyError("frequency must be a non-negative Fraction")
        return self.cents * frequency


def to_stored_cents(amount: Fraction) -> int:
    """Round an exact expected amount to nearest cent, ties away from zero."""
    if not isinstance(amount, Fraction) or amount < 0:
        raise InvalidMoneyError("amount must be a non-negative Fraction")
    quotient, remainder = divmod(amount.numerator, amount.denominator)
    if remainder * 2 >= amount.denominator:
        quotient += 1
    return quotient
