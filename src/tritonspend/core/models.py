"""Foundational immutable domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum

from .money import Money


class PaymentAccount(Enum):
    """Accounts that may explicitly be eligible for an expense."""

    DINING_DOLLARS = "dining_dollars"
    TRITON_CASH = "triton_cash"


@dataclass(frozen=True)
class WalletBalances:
    """Independent Dining Dollars and Triton Cash balances."""

    dining_dollars: Money
    triton_cash: Money


@dataclass(frozen=True)
class Expense:
    """A cent-denominated expense with explicit eligible accounts."""

    amount: Money
    eligible_accounts: tuple[PaymentAccount, ...]


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date
    today: date


@dataclass(frozen=True)
class ValidatedDateRange:
    """The requested range and its forecastable inclusive projection start."""

    start: date
    end: date
    today: date
    projection_start: date
