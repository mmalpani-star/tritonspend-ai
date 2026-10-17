"""Foundational immutable domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .money import Money


@dataclass(frozen=True)
class WalletBalances:
    """Independent Dining Dollars and Triton Cash balances."""

    dining_dollars: Money
    triton_cash: Money


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
