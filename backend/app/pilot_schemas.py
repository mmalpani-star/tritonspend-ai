"""Validated request and response models for participant data collection."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StrictInt, StrictStr

from .schemas import HabitRequest


def as_utc(value: datetime) -> datetime:
    # SQLite returns stored UTC timestamps without an offset; label them as UTC so
    # clients never read them as local time. Aware values are normalized to UTC.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


# Every timestamp in a response is UTC with an explicit offset; requests keep plain datetime.
UtcDateTime = Annotated[datetime, AfterValidator(as_utc)]

AccountName = Literal["dining_dollars", "triton_cash"]
EntryTypeName = Literal["spending", "deposit", "refund"]


class BalanceCheckinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_date: date
    observed_at: Optional[datetime] = None
    dining_dollars_cents: StrictInt = Field(ge=0)
    triton_cash_cents: StrictInt = Field(ge=0)


class WalletSaveRequest(BaseModel):
    """Both wallet balances, accurate on ``effective_date`` before that day's spending."""

    model_config = ConfigDict(extra="forbid")

    effective_date: date
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
    observed_at: UtcDateTime
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
    recorded_at: Optional[UtcDateTime] = None


class WalletStatusResponse(BaseModel):
    """Latest saved wallet balances plus earlier saves, newest first."""

    latest: Optional[BalanceCheckinResponse] = None
    history: list[BalanceCheckinResponse]
    days_since_update: Optional[int] = None
    stale: bool
    stale_after_days: int
    thresholds: Optional[BalanceThresholdRequest] = None
    warnings: Optional[BalanceWarningsResponse] = None


class DeleteForecastResponse(BaseModel):
    deleted: bool
    id: str


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
    occurred_at: UtcDateTime


class ForecastSnapshotExportItem(BaseModel):
    created_at: UtcDateTime
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
    created_at: UtcDateTime


class ZeroSpendingResponse(BaseModel):
    id: str
    day: date
    confirmed_at: UtcDateTime


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


class ParticipantForecastRequest(BaseModel):
    """Balances are never accepted here; they come from the latest saved wallet balances."""

    model_config = ConfigDict(extra="forbid")

    end_date: date
    scenario: Literal["frugal", "expected", "higher"] = "expected"
    habits: list[HabitRequest] = Field(min_length=1, max_length=50)


class WalletAmounts(BaseModel):
    dining_dollars_cents: int
    triton_cash_cents: int


class OptionalWalletAmounts(BaseModel):
    dining_dollars_cents: Optional[int] = None
    triton_cash_cents: Optional[int] = None


class ParticipantForecastSummary(BaseModel):
    id: str
    created_at: UtcDateTime
    start_date: date
    end_date: date
    engine_version: str
    scenario: Optional[str] = None
    funds_last: Optional[bool] = None
    total_unfunded_cents: Optional[int] = None
    starting_balances: Optional[WalletAmounts] = None
    projected_balances: Optional[WalletAmounts] = None
    warnings: list[str] = []


class ParticipantForecastHistoryResponse(BaseModel):
    forecasts: list[ParticipantForecastSummary]


class ParticipantForecastDetail(BaseModel):
    id: str
    created_at: UtcDateTime
    start_date: date
    end_date: date
    engine_version: str
    inputs: dict
    forecast: dict


class TrajectoryTarget(BaseModel):
    account: AccountName
    target_cents: int
    basis: Literal["threshold", "zero"]
    ideal_available: bool
    explanation: str


class TrajectoryPoint(BaseModel):
    date: date
    # "start": start of the first forecast day (the starting balance); "end": end of ``date``.
    moment: Literal["start", "end"]
    actual: Optional[WalletAmounts] = None
    # The as-of date the student saved this observed balance for.
    actual_as_of: Optional[date] = None
    projected: Optional[WalletAmounts] = None
    ideal: OptionalWalletAmounts


class ForecastTrajectoryResponse(BaseModel):
    forecast_id: str
    schema_version: Optional[str] = None
    as_of: date
    start_date: date
    end_date: date
    starting_balances: WalletAmounts
    targets: list[TrajectoryTarget]
    points: list[TrajectoryPoint]


class OptionalWallet(BaseModel):
    dining_dollars_cents: Optional[int] = None
    triton_cash_cents: Optional[int] = None


class PredictionPoint(BaseModel):
    date: date
    moment: Literal["start", "end"]
    actual: OptionalWallet
    actual_as_of: Optional[date] = None
    predicted: OptionalWallet
    lower: OptionalWallet
    higher: OptionalWallet
    ideal: OptionalWallet
    original_plan: OptionalWallet


class BalanceChange(BaseModel):
    from_boundary: date
    to_boundary: date
    increase_cents: Optional[int] = None
    daily_pace_cents: Optional[float] = None


class AccountPrediction(BaseModel):
    account: AccountName
    latest_cents: Optional[int] = None
    confidence: Literal["none", "starting", "preliminary", "developing", "established"]
    confidence_text: str
    usable_interval_count: int
    span_days: int
    daily_pace_cents: Optional[float] = None
    lower_pace_cents: Optional[float] = None
    higher_pace_cents: Optional[float] = None
    range_basis: Optional[Literal["learned_range", "sensitivity"]] = None
    predicted_end_cents: Optional[int] = None
    lower_end_cents: Optional[int] = None
    higher_end_cents: Optional[int] = None
    runs_out_on: Optional[date] = None
    target_cents: int
    target_basis: Literal["forecast_threshold", "current_threshold", "zero"]
    ideal_available: bool
    replenishments: list[BalanceChange]
    unusual_changes: list[BalanceChange]


class PredictionLatest(BaseModel):
    as_of: date
    boundary: date
    observed_at: UtcDateTime
    balances: WalletAmounts


class PredictionHorizon(BaseModel):
    start: date
    end_date: date
    rule: Literal["selected_forecast_end", "default"]
    days: int


class PredictionComparison(BaseModel):
    id: str
    created_at: UtcDateTime
    start_date: date
    end_date: date
    scenario: Optional[str] = None


class PredictionResponse(BaseModel):
    """A personalized prediction learned only from this participant's saved balances."""

    model_version: str
    today: date
    observation_count: int
    latest: Optional[PredictionLatest] = None
    horizon: Optional[PredictionHorizon] = None
    comparison: Optional[PredictionComparison] = None
    accounts: list[AccountPrediction]
    points: list[PredictionPoint]
