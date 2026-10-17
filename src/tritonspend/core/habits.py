"""Structured habits and exact expected spending estimates."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable

from .errors import InvalidHabitError
from .models import PaymentAccount
from .money import Money


@dataclass(frozen=True)
class SpendingHabit:
    """A recurring expense with an exact expected frequency."""

    name: str
    frequency: Fraction
    price: Money
    eligible_accounts: tuple[PaymentAccount, ...]


def validate_habit(habit: SpendingHabit) -> SpendingHabit:
    if not isinstance(habit, SpendingHabit):
        raise InvalidHabitError("a spending habit is required")
    if not isinstance(habit.name, str) or not habit.name.strip():
        raise InvalidHabitError("habit name must be non-empty")
    if not isinstance(habit.frequency, Fraction) or habit.frequency < 0:
        raise InvalidHabitError("habit frequency must be a non-negative Fraction")
    if not isinstance(habit.price, Money):
        raise InvalidHabitError("habit price must be Money")
    if not isinstance(habit.eligible_accounts, tuple):
        raise InvalidHabitError("habit eligibility must be a tuple")
    if not habit.eligible_accounts:
        raise InvalidHabitError("habit must have eligible accounts")
    if any(not isinstance(account, PaymentAccount) for account in habit.eligible_accounts):
        raise InvalidHabitError("habit eligibility must use payment accounts")
    if len(set(habit.eligible_accounts)) != len(habit.eligible_accounts):
        raise InvalidHabitError("habit eligibility must be unique")
    return habit


def estimate_habit(habit: SpendingHabit) -> Fraction:
    """Return exact expected cents per projected day for one habit."""
    validate_habit(habit)
    return habit.price.expected(habit.frequency)


def estimate_daily_spending(habits: Iterable[SpendingHabit]) -> Fraction:
    """Return exact expected cents per projected day across all habits."""
    if habits is None:
        raise InvalidHabitError("habits are required")
    total = Fraction(0)
    for habit in habits:
        total += estimate_habit(habit)
    return total
