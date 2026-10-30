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
    """Charge an expense to its eligible accounts only.

    When both accounts are explicitly eligible, the expense is split equally,
    with any odd cent assigned to Triton Cash. If one account cannot cover its
    share, the uncovered part is charged to the other eligible account, up to
    that account's available balance. An ineligible account is never charged,
    no account goes negative, and only the amount no eligible account can
    cover is reported as unfunded.
    """
    validate_wallet_balances(balances)
    _validate_expense(expense)

    dining_eligible = PaymentAccount.DINING_DOLLARS in expense.eligible_accounts
    cash_eligible = PaymentAccount.TRITON_CASH in expense.eligible_accounts
    if dining_eligible and cash_eligible:
        dining_target = expense.amount.cents // 2
        cash_target = expense.amount.cents - dining_target
    elif dining_eligible:
        dining_target = expense.amount.cents
        cash_target = 0
    else:
        dining_target = 0
        cash_target = expense.amount.cents

    dining_paid = min(dining_target, balances.dining_dollars.cents)
    cash_paid = min(cash_target, balances.triton_cash.cents)
    if dining_eligible and cash_eligible:
        # Spill each account's uncovered share onto the other's remaining balance.
        dining_shortfall = dining_target - dining_paid
        cash_shortfall = cash_target - cash_paid
        dining_paid += min(cash_shortfall, balances.dining_dollars.cents - dining_paid)
        cash_paid += min(dining_shortfall, balances.triton_cash.cents - cash_paid)
    remaining = expense.amount.cents - dining_paid - cash_paid

    return AllocationResult(
        remaining_balances=WalletBalances(
            dining_dollars=Money(balances.dining_dollars.cents - dining_paid),
            triton_cash=Money(balances.triton_cash.cents - cash_paid),
        ),
        paid_dining_dollars=Money(dining_paid),
        paid_triton_cash=Money(cash_paid),
        unfunded=Money(remaining),
    )
