from datetime import date, datetime

import pytest

from tritonspend.core.errors import InvalidDateRangeError, InvalidMoneyError
from tritonspend.core.models import DateRange, WalletBalances
from tritonspend.core.money import Money
from tritonspend.core.validation import validate_date_range, validate_wallet_balances


TODAY = date(2026, 10, 16)


def test_validates_independent_wallet_balances():
    balances = WalletBalances(Money(1_000), Money(2_000))

    assert validate_wallet_balances(balances) == balances


def test_zero_wallet_balances_are_valid():
    balances = WalletBalances(Money(0), Money(0))

    assert validate_wallet_balances(balances) == balances


@pytest.mark.parametrize(
    "balances",
    [
        WalletBalances(None, Money(100)),
        WalletBalances(Money(100), 100),
        WalletBalances(Money(100), "100"),
    ],
)
def test_rejects_non_money_wallet_fields(balances):
    with pytest.raises(InvalidMoneyError):
        validate_wallet_balances(balances)


def test_rejects_missing_wallet_balances():
    with pytest.raises(InvalidMoneyError):
        validate_wallet_balances(None)


def test_rejects_reversed_dates():
    dates = DateRange(date(2026, 10, 17), date(2026, 10, 16), TODAY)

    with pytest.raises(InvalidDateRangeError):
        validate_date_range(dates)


def test_rejects_range_ending_before_injected_today():
    dates = DateRange(date(2026, 10, 1), date(2026, 10, 15), TODAY)

    with pytest.raises(InvalidDateRangeError):
        validate_date_range(dates)


@pytest.mark.parametrize(
    "start,end",
    [
        (datetime(2026, 10, 16, 9), date(2026, 10, 17)),
        (date(2026, 10, 16), datetime(2026, 10, 17, 9)),
    ],
)
def test_rejects_datetime_date_endpoints(start, end):
    with pytest.raises(InvalidDateRangeError):
        validate_date_range(DateRange(start, end, TODAY))
