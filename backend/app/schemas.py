"""Strict JSON DTOs for the forecast adapter."""

from __future__ import annotations

from datetime import date
from typing import List

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator


class HabitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: StrictStr
    frequency: StrictStr
    price_cents: StrictInt = Field(ge=0)
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
        if not _is_fraction_string(value):
            raise ValueError("frequency must be a non-negative fraction string")
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
    habits: List[HabitRequest]
    dining_dollars_cents: StrictInt = Field(ge=0)
    triton_cash_cents: StrictInt = Field(ge=0)
    scenario: StrictStr = "expected"

    @field_validator("scenario")
    @classmethod
    def require_scenario(cls, value: str) -> str:
        if value not in {"frugal", "expected", "higher"}:
            raise ValueError("scenario must be frugal, expected, or higher")
        return value


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


def _is_fraction_string(value: str) -> bool:
    parts = value.split("/")
    if len(parts) == 1:
        return parts[0].isdigit()
    if len(parts) != 2:
        return False
    numerator, denominator = parts
    return numerator.isdigit() and denominator.isdigit() and int(denominator) > 0
