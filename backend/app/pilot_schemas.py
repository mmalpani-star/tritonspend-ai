"""Validated request and response models for participant data collection."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr


AccountName = Literal["dining_dollars", "triton_cash"]
EntryTypeName = Literal["spending", "deposit", "refund"]


class BalanceCheckinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_date: date
    observed_at: Optional[datetime] = None
    dining_dollars_cents: StrictInt = Field(ge=0)
    triton_cash_cents: StrictInt = Field(ge=0)


class LedgerEntryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurred_on: date
    account: AccountName
    entry_type: EntryTypeName
    amount_cents: StrictInt = Field(gt=0)
    merchant_or_note: Optional[StrictStr] = Field(default=None, max_length=500)


class ZeroSpendingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: date


class BalanceCheckinResponse(BaseModel):
    id: str
    effective_date: date
    observed_at: datetime
    dining_dollars_cents: int
    triton_cash_cents: int
    source: str


class BalanceThresholdRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dining_dollars_cents: StrictInt = Field(ge=0)
    triton_cash_cents: StrictInt = Field(ge=0)


class BalanceWarningResponse(BaseModel):
    account: AccountName
    warning: bool
    current_balance_cents: Optional[int] = None
    threshold_cents: int
    explanation: str


class BalanceWarningsResponse(BaseModel):
    dining_dollars: BalanceWarningResponse
    triton_cash: BalanceWarningResponse
    recorded_at: Optional[datetime] = None


class DeleteParticipantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: Literal["DELETE_MY_DATA"]


class DeleteParticipantResponse(BaseModel):
    deleted: bool
    already_deleted: bool
    message: str


class ConsentHistoryItem(BaseModel):
    event_type: Literal["accepted", "withdrawn"]
    consent_version: str
    document_url: str
    document_version_hash: Optional[str] = None
    occurred_at: datetime


class ForecastSnapshotExportItem(BaseModel):
    created_at: datetime
    start_date: date
    end_date: date
    engine_version: str
    request_json: dict
    response_json: dict


class LedgerEntryResponse(BaseModel):
    id: str
    occurred_on: date
    account: AccountName
    entry_type: EntryTypeName
    amount_cents: int
    merchant_or_note: Optional[str]
    created_at: datetime


class ZeroSpendingResponse(BaseModel):
    id: str
    day: date
    confirmed_at: datetime


class PilotDayResponse(BaseModel):
    day: date
    status: Literal["checkin", "zero_spending", "unknown"]
    checkin: Optional[BalanceCheckinResponse] = None
    zero_spending: Optional[ZeroSpendingResponse] = None


class PilotDataResponse(BaseModel):
    start_date: date
    end_date: date
    days: list[PilotDayResponse]
    ledger_entries: list[LedgerEntryResponse]


class ParticipantExportResponse(BaseModel):
    schema_version: Literal["stage5.v1"] = "stage5.v1"
    participant: dict
    balance_checkins: list[BalanceCheckinResponse]
    ledger_entries: list[LedgerEntryResponse]
    zero_spending_confirmations: list[ZeroSpendingResponse]
    thresholds: Optional[BalanceThresholdRequest] = None
    consent_history: list[ConsentHistoryItem]
    forecast_snapshots: list[ForecastSnapshotExportItem]
