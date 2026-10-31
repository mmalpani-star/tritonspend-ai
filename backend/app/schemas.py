"""Strict JSON DTOs for the forecast adapter."""

from __future__ import annotations

from datetime import date
from fractions import Fraction
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator, model_validator


# API input limits, shared by anonymous and signed-in forecasts and by saved balances.
# They bound per-request work, keep amounts inside the 32-bit cents columns, and keep
# every response amount far below JavaScript's Number.MAX_SAFE_INTEGER (about 9.0e15):
# the worst case is MAX_PRICE_CENTS * MAX_FREQUENCY_PER_DAY * 6/5 * MAX_FORECAST_DAYS
# * MAX_HABITS, about 5.3e10 cents. See README "API input limits".
MAX_FORECAST_DAYS = 366
MAX_HABITS = 50
MAX_FREQUENCY_LENGTH = 9
MAX_FREQUENCY_DENOMINATOR = 365
MAX_FREQUENCY_PER_DAY = 24
MAX_BALANCE_CENTS = 10_000_000
MAX_PRICE_CENTS = 100_000


class HabitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: StrictStr
    # max_length runs before require_fraction_string, so oversized strings never reach int().
    frequency: StrictStr = Field(max_length=MAX_FREQUENCY_LENGTH)
    price_cents: StrictInt = Field(ge=0, le=MAX_PRICE_CENTS)
    eligible_accounts: List[StrictStr] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def require_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be empty")
        return value

    @field_validator("frequency")
    @classmethod
    def require_fraction_string(cls, value: str) -> str:
        error = frequency_error(value)
        if error:
            raise ValueError(error)
        return value

    @field_validator("eligible_accounts")
    @classmethod
    def require_unique_accounts(cls, value: List[str]) -> List[str]:
        if len(set(value)) != len(value):
            raise ValueError("eligible_accounts must not contain duplicates")
        allowed = {"dining_dollars", "triton_cash"}
        if any(account not in allowed for account in value):
            raise ValueError("eligible_accounts contains an unknown account")
        return value


class ForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date
    end_date: date
    habits: List[HabitRequest] = Field(max_length=MAX_HABITS)
    dining_dollars_cents: StrictInt = Field(ge=0, le=MAX_BALANCE_CENTS)
    triton_cash_cents: StrictInt = Field(ge=0, le=MAX_BALANCE_CENTS)
    scenario: StrictStr = "expected"

    @field_validator("scenario")
    @classmethod
    def require_scenario(cls, value: str) -> str:
        if value not in {"frugal", "expected", "higher"}:
            raise ValueError("scenario must be frugal, expected, or higher")
        return value

    @model_validator(mode="after")
    def limit_date_span(self) -> "ForecastRequest":
        # Reversed ranges are left to the core, which reports them as 422.
        if (self.end_date - self.start_date).days + 1 > MAX_FORECAST_DAYS:
            raise ValueError(f"date range must span at most {MAX_FORECAST_DAYS} days")
        return self


class WalletResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dining_dollars_cents: int
    triton_cash_cents: int


class DailyForecastResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    expected_spending_cents: int
    paid_dining_dollars_cents: int
    paid_triton_cash_cents: int
    unfunded_cents: int
    remaining_balances: WalletResponse
    funds_last: bool


class LimitsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_wallet_runway_caps: WalletResponse
    weekly_wallet_runway_caps: dict[date, WalletResponse]


class ForecastResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: str
    multiplier: str
    days: list[DailyForecastResponse]
    projected_balances: WalletResponse
    total_unfunded_cents: int
    funds_last: bool
    limits: LimitsResponse


def _is_ascii_digits(value: str) -> bool:
    # str.isdigit() alone accepts Unicode digits such as "²" (which int() rejects) and "١".
    return value.isascii() and value.isdigit()


def frequency_error(value: str) -> Optional[str]:
    """Why a frequency string ("n" or "n/d", per day) breaks the contract, or None if valid."""
    if len(value) > MAX_FREQUENCY_LENGTH:
        return f"frequency must be at most {MAX_FREQUENCY_LENGTH} characters"
    parts = value.split("/")
    if len(parts) > 2 or not all(_is_ascii_digits(part) for part in parts):
        return "frequency must be a non-negative fraction string"
    denominator = int(parts[1]) if len(parts) == 2 else 1
    if not 0 < denominator <= MAX_FREQUENCY_DENOMINATOR:
        return f"frequency denominator must be between 1 and {MAX_FREQUENCY_DENOMINATOR}"
    if Fraction(int(parts[0]), denominator) > MAX_FREQUENCY_PER_DAY:
        return f"frequency must be at most {MAX_FREQUENCY_PER_DAY} per day"
    return None
