"""Validation for foundational money, wallet, and date inputs."""

from __future__ import annotations

from datetime import date, datetime
from numbers import Integral

from .errors import InvalidDateRangeError, InvalidMoneyError
from .money import Money
from .models import DateRange, WalletBalances


def validate_cents(cents: int) -> int:
    if isinstance(cents, bool) or not isinstance(cents, Integral) or cents < 0:
        raise InvalidMoneyError("cents must be a non-negative integer")
    return int(cents)


def validate_wallet_balances(balances: WalletBalances) -> WalletBalances:
    if not isinstance(balances, WalletBalances):
        raise InvalidMoneyError("wallet balances are required")
    if not isinstance(balances.dining_dollars, Money):
        raise InvalidMoneyError("dining dollars must be Money")
    if not isinstance(balances.triton_cash, Money):
        raise InvalidMoneyError("triton cash must be Money")
    validate_cents(balances.dining_dollars.cents)
    validate_cents(balances.triton_cash.cents)
    return balances


def validate_date_range(date_range: DateRange) -> DateRange:
    if not isinstance(date_range, DateRange):
        raise InvalidDateRangeError("a date range is required")
    if not all(isinstance(value, date) and not isinstance(value, datetime) for value in (
        date_range.start,
        date_range.end,
        date_range.today,
    )):
        raise InvalidDateRangeError("start, end, and today must be dates")
    if date_range.start > date_range.end:
        raise InvalidDateRangeError("start date cannot be after end date")
    if date_range.end < date_range.today:
        raise InvalidDateRangeError("end date must be on or after today")
    return date_range
