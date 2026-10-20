"""Minimum M1 persistence schema.

Identifiers are stored as strings for portability: PostgreSQL deployments may
use UUID-shaped opaque values, while SQLite has no native UUID type.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Account(str, enum.Enum):
    dining_dollars = "dining_dollars"
    triton_cash = "triton_cash"


class EntryType(str, enum.Enum):
    spending = "spending"
    deposit = "deposit"
    refund = "refund"


class ConsentEventType(str, enum.Enum):
    accepted = "accepted"
    withdrawn = "withdrawn"


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64), default="America/Los_Angeles", nullable=False)


class InviteToken(Base):
    __tablename__ = "invite_tokens"
    __table_args__ = (
        Index("ix_invite_tokens_expires_at", "expires_at"),
        Index("ix_invite_tokens_participant_id", "participant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    participant_id: Mapped[Optional[str]] = mapped_column(ForeignKey("participants.id"))


class Consent(Base):
    __tablename__ = "consents"
    __table_args__ = (Index("ix_consents_participant_id", "participant_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(100), nullable=False)
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    withdrawn_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    terms_version_hash: Mapped[Optional[str]] = mapped_column(String(128))


class BalanceCheckin(Base):
    __tablename__ = "balance_checkins"
    __table_args__ = (
        CheckConstraint("dining_dollars_cents >= 0", name="ck_balance_dining_nonnegative"),
        CheckConstraint("triton_cash_cents >= 0", name="ck_balance_cash_nonnegative"),
        Index("ix_balance_checkins_participant_id", "participant_id"),
        Index("ix_balance_checkins_effective_date", "effective_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    dining_dollars_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    triton_cash_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class ParticipantBalanceThreshold(Base):
    __tablename__ = "participant_balance_thresholds"
    __table_args__ = (
        CheckConstraint("dining_dollars_cents >= 0", name="ck_threshold_dining_nonnegative"),
        CheckConstraint("triton_cash_cents >= 0", name="ck_threshold_cash_nonnegative"),
        UniqueConstraint("participant_id", name="uq_threshold_participant"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), nullable=False)
    dining_dollars_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    triton_cash_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("amount_cents >= 0", name="ck_ledger_amount_nonnegative"),
        CheckConstraint(
            "account IN ('dining_dollars', 'triton_cash')",
            name="ck_ledger_account_valid",
        ),
        CheckConstraint(
            "entry_type IN ('spending', 'deposit', 'refund')",
            name="ck_ledger_entry_type_valid",
        ),
        Index("ix_ledger_entries_participant_id", "participant_id"),
        Index("ix_ledger_entries_occurred_on", "occurred_on"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    account: Mapped[Account] = mapped_column(Enum(Account, native_enum=False), nullable=False)
    entry_type: Mapped[EntryType] = mapped_column(Enum(EntryType, native_enum=False), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    merchant_or_note: Mapped[Optional[str]] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class ZeroSpendingConfirmation(Base):
    __tablename__ = "zero_spending_confirmations"
    __table_args__ = (
        UniqueConstraint("participant_id", "day", name="uq_zero_spending_participant_day"),
        Index("ix_zero_spending_confirmations_day", "day"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), nullable=False)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class ForecastSnapshot(Base):
    __tablename__ = "forecast_snapshots"
    __table_args__ = (
        Index("ix_forecast_snapshots_participant_id", "participant_id"),
        Index("ix_forecast_snapshots_created_at", "created_at"),
        Index("ix_forecast_snapshots_start_date", "start_date"),
        Index("ix_forecast_snapshots_end_date", "end_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(100), nullable=False)
    request_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False)


class ConsentEvent(Base):
    __tablename__ = "consent_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('accepted', 'withdrawn')",
            name="ck_consent_events_event_type_valid",
        ),
        Index("ix_consent_events_participant_id", "participant_id"),
        Index("ix_consent_events_occurred_at", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), nullable=False)
    event_type: Mapped[ConsentEventType] = mapped_column(
        Enum(ConsentEventType, native_enum=False), nullable=False
    )
    consent_version: Mapped[str] = mapped_column(String(100), nullable=False)
    document_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    document_version_hash: Mapped[Optional[str]] = mapped_column(String(128))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class ParticipantSession(Base):
    __tablename__ = "participant_sessions"
    __table_args__ = (
        Index("ix_participant_sessions_participant_id", "participant_id"),
        Index("ix_participant_sessions_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), nullable=False)
    session_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_token_hash: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
