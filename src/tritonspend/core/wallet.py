"""Independent wallet accounting for explicitly eligible expenses."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import InvalidExpenseError
from .models import Expense, PaymentAccount, WalletBalances
from .money import Money
from .validation import validate_wallet_balances


@dataclass(frozen=True)
class AllocationResult:
    """The complete outcome of charging one expense."""

    remaining_balances: WalletBalances
    paid_dining_dollars: Money
    paid_triton_cash: Money
    unfunded: Money

    @property
    def total_paid(self) -> Money:
        return self.paid_dining_dollars + self.paid_triton_cash


def _validate_expense(expense: Expense) -> None:
    if not isinstance(expense, Expense):
        raise InvalidExpenseError("an expense is required")
    if not isinstance(expense.amount, Money):
        raise InvalidExpenseError("expense amount must be Money")
    if not isinstance(expense.eligible_accounts, tuple):
        raise InvalidExpenseError("eligible accounts must be a tuple")
    if not expense.eligible_accounts:
        raise InvalidExpenseError("expense must have eligible accounts")
    if any(not isinstance(account, PaymentAccount) for account in expense.eligible_accounts):
        raise InvalidExpenseError("eligible accounts must be payment accounts")
    if len(set(expense.eligible_accounts)) != len(expense.eligible_accounts):
        raise InvalidExpenseError("eligible accounts must be unique")


def allocate_expense(
    balances: WalletBalances,
    expense: Expense,
) -> AllocationResult:
    """Charge an expense without cross-wallet substitution.

    When both accounts are explicitly eligible, Dining Dollars are charged
    first, followed by Triton Cash. Each account is charged only up to its
    available balance; any remainder is reported as unfunded.
    """
    validate_wallet_balances(balances)
    _validate_expense(expense)

    remaining = expense.amount.cents
    dining_paid = min(
        remaining,
        balances.dining_dollars.cents
        if PaymentAccount.DINING_DOLLARS in expense.eligible_accounts
        else 0,
    )
    remaining -= dining_paid
    cash_paid = min(
        remaining,
        balances.triton_cash.cents
        if PaymentAccount.TRITON_CASH in expense.eligible_accounts
        else 0,
    )
    remaining -= cash_paid

    return AllocationResult(
        remaining_balances=WalletBalances(
            dining_dollars=Money(balances.dining_dollars.cents - dining_paid),
            triton_cash=Money(balances.triton_cash.cents - cash_paid),
        ),
        paid_dining_dollars=Money(dining_paid),
        paid_triton_cash=Money(cash_paid),
        unfunded=Money(remaining),
    )
