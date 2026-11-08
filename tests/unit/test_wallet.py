from datetime import date
from fractions import Fraction

import pytest

from tritonspend.core.errors import InvalidExpenseError
from tritonspend.core.forecast import Scenario, default_scenario, forecast
from tritonspend.core.habits import SpendingHabit
from tritonspend.core.models import DateRange, Expense, PaymentAccount, WalletBalances
from tritonspend.core.money import Money
from tritonspend.core.wallet import allocate_expense

BOTH = (PaymentAccount.DINING_DOLLARS, PaymentAccount.TRITON_CASH)


def balances(dining: int, cash: int) -> WalletBalances:
    return WalletBalances(Money(dining), Money(cash))


def test_dining_dollars_only_expense_uses_dining_dollars():
    result = allocate_expense(
        balances(500, 700),
        Expense(Money(300), (PaymentAccount.DINING_DOLLARS,)),
    )

    assert result.paid_dining_dollars == Money(300)
    assert result.paid_triton_cash == Money(0)
    assert result.remaining_balances == balances(200, 700)


def test_triton_cash_only_expense_uses_triton_cash():
    result = allocate_expense(
        balances(500, 700),
        Expense(Money(300), (PaymentAccount.TRITON_CASH,)),
    )

    assert result.paid_dining_dollars == Money(0)
    assert result.paid_triton_cash == Money(300)
    assert result.remaining_balances == balances(500, 400)


def test_multiple_eligible_accounts_split_expense_equally():
    result = allocate_expense(
        balances(200, 500),
        Expense(
            Money(300),
            (PaymentAccount.DINING_DOLLARS, PaymentAccount.TRITON_CASH),
        ),
    )

    assert result.paid_dining_dollars == Money(150)
    assert result.paid_triton_cash == Money(150)
    assert result.remaining_balances == balances(50, 350)


def test_multiple_eligible_accounts_assign_odd_cent_to_triton_cash():
    result = allocate_expense(
        balances(500, 500),
        Expense(
            Money(101),
            (PaymentAccount.DINING_DOLLARS, PaymentAccount.TRITON_CASH),
        ),
    )

    assert result.paid_dining_dollars == Money(50)
    assert result.paid_triton_cash == Money(51)
    assert result.total_paid == Money(101)


def test_insufficient_eligible_funds_report_unfunded_without_negative_balances():
    result = allocate_expense(
        balances(100, 200),
        Expense(
            Money(500),
            (PaymentAccount.DINING_DOLLARS, PaymentAccount.TRITON_CASH),
        ),
    )

    assert result.total_paid == Money(300)
    assert result.unfunded == Money(200)
    assert result.remaining_balances == balances(0, 0)


@pytest.mark.parametrize(
    "starting,dining_paid,cash_paid,remaining",
    [
        ((100, 500), 100, 200, (0, 300)),  # Dining Dollars short: Triton Cash covers the rest
        ((500, 100), 200, 100, (300, 0)),  # Triton Cash short: Dining Dollars covers the rest
    ],
)
def test_split_shortfall_spills_over_to_the_other_eligible_wallet(starting, dining_paid, cash_paid, remaining):
    result = allocate_expense(balances(*starting), Expense(Money(300), BOTH))

    assert result.paid_dining_dollars == Money(dining_paid)
    assert result.paid_triton_cash == Money(cash_paid)
    assert result.unfunded == Money(0)
    assert result.remaining_balances == balances(*remaining)


def test_spill_over_uses_only_available_funds_and_reports_the_genuine_shortfall():
    # 250/250 split; Dining Dollars is short 150, Triton Cash can add only 50 more.
    result = allocate_expense(balances(100, 300), Expense(Money(500), BOTH))

    assert result.paid_dining_dollars == Money(100)
    assert result.paid_triton_cash == Money(300)
    assert result.unfunded == Money(100)
    assert result.remaining_balances == balances(0, 0)


@pytest.mark.parametrize(
    "account,starting,remaining",
    [
        (PaymentAccount.DINING_DOLLARS, (100, 1_000), (0, 1_000)),
        (PaymentAccount.TRITON_CASH, (1_000, 100), (1_000, 0)),
    ],
)
def test_ineligible_wallet_never_covers_a_shortfall(account, starting, remaining):
    result = allocate_expense(balances(*starting), Expense(Money(300), (account,)))

    assert result.total_paid == Money(100)
    assert result.unfunded == Money(200)
    assert result.remaining_balances == balances(*remaining)


def test_dashboard_example_spills_over_instead_of_reporting_false_unfunded_spending():
    # $4,200 DD, $420 TC, $5/day breakfast eligible for both, Oct 26 2026 - Jun 11 2027.
    start = date(2026, 10, 26)
    result = forecast(
        DateRange(start, date(2027, 6, 11), start),
        balances(420_000, 42_000),
        [SpendingHabit("breakfast", Fraction(1), Money(500), BOTH)],
        default_scenario(Scenario.EXPECTED),
    )

    assert len(result.days) == 229
    assert sum(day.expected_spending.cents for day in result.days) == 114_500
    assert result.projected_balances == balances(347_500, 0)
    assert result.total_unfunded == Money(0)
    assert result.funds_last is True
    # Triton Cash covers its $2.50 share for 168 days; then Dining Dollars pays the full $5.
    assert result.days[167].paid_triton_cash == Money(250)
    assert result.days[168].paid_dining_dollars == Money(500)
    assert result.days[168].paid_triton_cash == Money(0)


def test_exact_balance_spending_has_no_unfunded_amount():
    result = allocate_expense(
        balances(250, 900),
        Expense(Money(250), (PaymentAccount.DINING_DOLLARS,)),
    )

    assert result.total_paid == Money(250)
    assert result.unfunded == Money(0)
    assert result.remaining_balances == balances(0, 900)


def test_zero_cost_expense_does_not_change_balances():
    starting = balances(250, 900)

    result = allocate_expense(
        starting,
        Expense(Money(0), (PaymentAccount.TRITON_CASH,)),
    )

    assert result.total_paid == Money(0)
    assert result.unfunded == Money(0)
    assert result.remaining_balances == starting


@pytest.mark.parametrize(
    "expense",
    [
        Expense(Money(100), ()),
        Expense(Money(100), ("dining_dollars",)),
        Expense(Money(100), (PaymentAccount.DINING_DOLLARS,) * 2),
        Expense(None, (PaymentAccount.DINING_DOLLARS,)),
    ],
)
def test_rejects_invalid_expense_or_eligibility(expense):
    with pytest.raises(InvalidExpenseError):
        allocate_expense(balances(500, 500), expense)


def test_independent_balances_do_not_fund_ineligible_account():
    result = allocate_expense(
        balances(0, 1_000),
        Expense(Money(250), (PaymentAccount.DINING_DOLLARS,)),
    )

    assert result.paid_dining_dollars == Money(0)
    assert result.paid_triton_cash == Money(0)
    assert result.unfunded == Money(250)
    assert result.remaining_balances == balances(0, 1_000)


@pytest.mark.parametrize(
    "amount,dining_paid,cash_paid,unfunded",
    [(0, 0, 0, 0), (150, 75, 75, 0), (500, 100, 200, 200)],
)
def test_total_spending_equals_funded_plus_unfunded(
    amount, dining_paid, cash_paid, unfunded
):
    result = allocate_expense(
        balances(100, 200),
        Expense(
            Money(amount),
            (PaymentAccount.DINING_DOLLARS, PaymentAccount.TRITON_CASH),
        ),
    )

    assert Money(amount) == result.total_paid + result.unfunded
    assert result.paid_dining_dollars == Money(dining_paid)
    assert result.paid_triton_cash == Money(cash_paid)
    assert result.unfunded == Money(unfunded)
