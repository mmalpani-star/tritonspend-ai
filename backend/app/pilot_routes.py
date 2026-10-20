"""Participant-scoped Stage 3 balance, ledger, and zero-spending routes."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .db import get_db
from .models import (
    BalanceCheckin,
    Consent,
    ConsentEvent,
    EntryType,
    ForecastSnapshot,
    InviteToken,
    LedgerEntry,
    Participant,
    ParticipantBalanceThreshold,
    ParticipantSession,
    ZeroSpendingConfirmation,
)
from .pilot_schemas import (
    BalanceCheckinRequest,
    BalanceCheckinResponse,
    BalanceThresholdRequest,
    BalanceWarningResponse,
    BalanceWarningsResponse,
    ConsentHistoryItem,
    DeleteParticipantRequest,
    DeleteParticipantResponse,
    ForecastSnapshotExportItem,
    LedgerEntryRequest,
    LedgerEntryResponse,
    ParticipantExportResponse,
    PilotDataResponse,
    PilotDayResponse,
    ZeroSpendingRequest,
    ZeroSpendingResponse,
)
from .security import (
    SESSION_COOKIE,
    get_current_participant,
    get_current_session,
    require_active_consent,
    require_csrf,
)

router = APIRouter(prefix="/api/v1/pilot", tags=["pilot"])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _reject_future(value: date, field_name: str) -> None:
    if value > datetime.now(ZoneInfo("America/Los_Angeles")).date():
        raise HTTPException(status_code=422, detail=f"{field_name} cannot be in the future")


def _checkin_response(value: BalanceCheckin) -> BalanceCheckinResponse:
    return BalanceCheckinResponse(
        id=value.id,
        effective_date=value.effective_date,
        observed_at=value.observed_at,
        dining_dollars_cents=value.dining_dollars_cents,
        triton_cash_cents=value.triton_cash_cents,
        source=value.source,
    )


def _ledger_response(value: LedgerEntry) -> LedgerEntryResponse:
    return LedgerEntryResponse(
        id=value.id,
        occurred_on=value.occurred_on,
        account=value.account.value,
        entry_type=value.entry_type.value,
        amount_cents=value.amount_cents,
        merchant_or_note=value.merchant_or_note,
        created_at=value.created_at,
    )


def _zero_response(value: ZeroSpendingConfirmation) -> ZeroSpendingResponse:
    return ZeroSpendingResponse(id=value.id, day=value.day, confirmed_at=value.confirmed_at)


def _latest_checkin(session: Session, participant_id: str) -> BalanceCheckin | None:
    return session.scalar(
        select(BalanceCheckin)
        .where(BalanceCheckin.participant_id == participant_id)
        .order_by(
            BalanceCheckin.effective_date.desc(),
            BalanceCheckin.observed_at.desc(),
            BalanceCheckin.created_at.desc(),
        )
        .limit(1)
    )


def _warnings_response(
    threshold: ParticipantBalanceThreshold, latest: BalanceCheckin | None
) -> BalanceWarningsResponse:
    def warning(account: str, current: int | None, configured: int) -> BalanceWarningResponse:
        if current is None:
            return BalanceWarningResponse(
                account=account,
                warning=False,
                current_balance_cents=None,
                threshold_cents=configured,
                explanation="Unknown: no balance has been recorded yet; no warning is issued.",
            )
        is_warning = current <= configured
        return BalanceWarningResponse(
            account=account,
            warning=is_warning,
            current_balance_cents=current,
            threshold_cents=configured,
            explanation=(
                f"Warning: the latest recorded balance is at or below your "
                f"{configured} cent threshold."
                if is_warning
                else f"No warning: the latest recorded balance is above your "
                f"{configured} cent threshold."
            ),
        )

    return BalanceWarningsResponse(
        dining_dollars=warning(
            "dining_dollars",
            latest.dining_dollars_cents if latest else None,
            threshold.dining_dollars_cents,
        ),
        triton_cash=warning(
            "triton_cash",
            latest.triton_cash_cents if latest else None,
            threshold.triton_cash_cents,
        ),
        recorded_at=latest.observed_at if latest else None,
    )


@router.get("/export", response_model=ParticipantExportResponse)
def export_participant_data(
    response: Response,
    participant: Participant = Depends(get_current_participant),
    session: Session = Depends(get_db),
) -> ParticipantExportResponse:
    checkins = session.scalars(
        select(BalanceCheckin)
        .where(BalanceCheckin.participant_id == participant.id)
        .order_by(BalanceCheckin.effective_date, BalanceCheckin.created_at)
    ).all()
    ledger = session.scalars(
        select(LedgerEntry)
        .where(LedgerEntry.participant_id == participant.id)
        .order_by(LedgerEntry.occurred_on, LedgerEntry.created_at)
    ).all()
    confirmations = session.scalars(
        select(ZeroSpendingConfirmation)
        .where(ZeroSpendingConfirmation.participant_id == participant.id)
        .order_by(ZeroSpendingConfirmation.day)
    ).all()
    threshold = session.scalar(
        select(ParticipantBalanceThreshold).where(
            ParticipantBalanceThreshold.participant_id == participant.id
        )
    )
    consent_events = session.scalars(
        select(ConsentEvent)
        .where(ConsentEvent.participant_id == participant.id)
        .order_by(ConsentEvent.occurred_at, ConsentEvent.id)
    ).all()
    snapshots = session.scalars(
        select(ForecastSnapshot)
        .where(ForecastSnapshot.participant_id == participant.id)
        .order_by(ForecastSnapshot.created_at, ForecastSnapshot.id)
    ).all()
    response.headers["Content-Disposition"] = 'attachment; filename="tritonspend-data-export.json"'
    return ParticipantExportResponse(
        participant={
            "created_at": participant.created_at,
            "deleted_at": participant.deleted_at,
            "timezone": participant.timezone,
        },
        balance_checkins=[_checkin_response(value) for value in checkins],
        ledger_entries=[_ledger_response(value) for value in ledger],
        zero_spending_confirmations=[_zero_response(value) for value in confirmations],
        thresholds=(
            BalanceThresholdRequest(
                dining_dollars_cents=threshold.dining_dollars_cents,
                triton_cash_cents=threshold.triton_cash_cents,
            )
            if threshold is not None
            else None
        ),
        consent_history=[
            ConsentHistoryItem(
                event_type=value.event_type.value,
                consent_version=value.consent_version,
                document_url=value.document_url,
                document_version_hash=value.document_version_hash,
                occurred_at=value.occurred_at,
            )
            for value in consent_events
        ],
        forecast_snapshots=[
            ForecastSnapshotExportItem(
                created_at=value.created_at,
                start_date=value.start_date,
                end_date=value.end_date,
                engine_version=value.engine_version,
                request_json=value.request_json,
                response_json=value.response_json,
            )
            for value in snapshots
        ],
    )


@router.delete(
    "/account",
    response_model=DeleteParticipantResponse,
    dependencies=[Depends(require_csrf)],
)
def delete_participant_account(
    payload: DeleteParticipantRequest,
    response: Response,
    current_session=Depends(get_current_session),
    session: Session = Depends(get_db),
) -> DeleteParticipantResponse:
    participant = session.get(Participant, current_session.participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="participant is unavailable")
    already_deleted = participant.deleted_at is not None
    if not already_deleted:
        deleted_at = _utc_now()
        session.execute(
            delete(BalanceCheckin).where(BalanceCheckin.participant_id == participant.id)
        )
        session.execute(delete(LedgerEntry).where(LedgerEntry.participant_id == participant.id))
        session.execute(
            delete(ZeroSpendingConfirmation).where(
                ZeroSpendingConfirmation.participant_id == participant.id
            )
        )
        session.execute(
            delete(ParticipantBalanceThreshold).where(
                ParticipantBalanceThreshold.participant_id == participant.id
            )
        )
        session.execute(
            delete(ForecastSnapshot).where(ForecastSnapshot.participant_id == participant.id)
        )
        session.execute(delete(Consent).where(Consent.participant_id == participant.id))
        session.execute(delete(InviteToken).where(InviteToken.participant_id == participant.id))
        participant.deleted_at = deleted_at
    session.execute(
        update(ParticipantSession)
        .where(
            ParticipantSession.participant_id == participant.id,
            ParticipantSession.revoked_at.is_(None),
        )
        .values(revoked_at=_utc_now())
    )
    session.execute(
        update(ParticipantSession)
        .where(ParticipantSession.participant_id == participant.id)
        .values(csrf_token_hash=None)
    )
    session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return DeleteParticipantResponse(
        deleted=True,
        already_deleted=already_deleted,
        message="Your participant data was deleted. Sign in again only if you receive a new invitation.",
    )


@router.post(
    "/balance-thresholds",
    response_model=BalanceWarningsResponse,
    dependencies=[Depends(require_csrf), Depends(require_active_consent)],
)
def set_balance_thresholds(
    payload: BalanceThresholdRequest,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
) -> BalanceWarningsResponse:
    threshold = session.scalar(
        select(ParticipantBalanceThreshold).where(
            ParticipantBalanceThreshold.participant_id == participant.id
        )
    )
    if threshold is None:
        threshold = ParticipantBalanceThreshold(participant_id=participant.id)
        session.add(threshold)
    threshold.dining_dollars_cents = payload.dining_dollars_cents
    threshold.triton_cash_cents = payload.triton_cash_cents
    session.commit()
    session.refresh(threshold)
    return _warnings_response(threshold, _latest_checkin(session, participant.id))


@router.get("/balance-warnings", response_model=BalanceWarningsResponse)
def read_balance_warnings(
    participant: Participant = Depends(get_current_participant),
    session: Session = Depends(get_db),
) -> BalanceWarningsResponse:
    threshold = session.scalar(
        select(ParticipantBalanceThreshold).where(
            ParticipantBalanceThreshold.participant_id == participant.id
        )
    )
    if threshold is None:
        raise HTTPException(status_code=404, detail="balance thresholds are not configured")
    return _warnings_response(threshold, _latest_checkin(session, participant.id))


@router.post(
    "/balance-checkins",
    response_model=BalanceCheckinResponse,
    dependencies=[Depends(require_csrf), Depends(require_active_consent)],
)
def create_balance_checkin(
    payload: BalanceCheckinRequest,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
) -> BalanceCheckinResponse:
    _reject_future(payload.effective_date, "effective_date")
    observed_at = payload.observed_at or _utc_now()
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    value = BalanceCheckin(
        participant_id=participant.id,
        observed_at=observed_at,
        effective_date=payload.effective_date,
        dining_dollars_cents=payload.dining_dollars_cents,
        triton_cash_cents=payload.triton_cash_cents,
        source="manual",
    )
    session.add(value)
    session.commit()
    session.refresh(value)
    return _checkin_response(value)


@router.post(
    "/ledger-entries",
    response_model=LedgerEntryResponse,
    dependencies=[Depends(require_csrf), Depends(require_active_consent)],
)
def create_ledger_entry(
    payload: LedgerEntryRequest,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
) -> LedgerEntryResponse:
    _reject_future(payload.occurred_on, "occurred_on")
    value = LedgerEntry(
        participant_id=participant.id,
        occurred_on=payload.occurred_on,
        account=payload.account,
        entry_type=EntryType(payload.entry_type),
        amount_cents=payload.amount_cents,
        merchant_or_note=payload.merchant_or_note,
    )
    session.add(value)
    session.commit()
    session.refresh(value)
    return _ledger_response(value)


@router.post(
    "/zero-spending-confirmations",
    response_model=ZeroSpendingResponse,
    dependencies=[Depends(require_csrf), Depends(require_active_consent)],
)
def create_zero_spending_confirmation(
    payload: ZeroSpendingRequest,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
) -> ZeroSpendingResponse:
    _reject_future(payload.day, "day")
    existing = session.scalar(
        select(ZeroSpendingConfirmation).where(
            ZeroSpendingConfirmation.participant_id == participant.id,
            ZeroSpendingConfirmation.day == payload.day,
        )
    )
    if existing is not None:
        return _zero_response(existing)
    value = ZeroSpendingConfirmation(participant_id=participant.id, day=payload.day)
    session.add(value)
    session.commit()
    session.refresh(value)
    return _zero_response(value)


@router.get("/data", response_model=PilotDataResponse)
def read_pilot_data(
    start_date: date = Query(...),
    end_date: date = Query(...),
    participant: Participant = Depends(get_current_participant),
    session: Session = Depends(get_db),
) -> PilotDataResponse:
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date must be on or after start_date")
    if (end_date - start_date).days > 366:
        raise HTTPException(status_code=422, detail="date range cannot exceed 366 days")
    checkins = session.scalars(
        select(BalanceCheckin)
        .where(
            BalanceCheckin.participant_id == participant.id,
            BalanceCheckin.effective_date.between(start_date, end_date),
        )
        .order_by(BalanceCheckin.effective_date, BalanceCheckin.created_at.desc())
    ).all()
    zeros = session.scalars(
        select(ZeroSpendingConfirmation).where(
            ZeroSpendingConfirmation.participant_id == participant.id,
            ZeroSpendingConfirmation.day.between(start_date, end_date),
        )
    ).all()
    ledger = session.scalars(
        select(LedgerEntry)
        .where(
            LedgerEntry.participant_id == participant.id,
            LedgerEntry.occurred_on.between(start_date, end_date),
        )
        .order_by(LedgerEntry.occurred_on, LedgerEntry.created_at)
    ).all()
    latest_checkins: dict[date, BalanceCheckin] = {}
    for value in checkins:
        latest_checkins.setdefault(value.effective_date, value)
    zero_by_day = {value.day: value for value in zeros}
    days = []
    for offset in range((end_date - start_date).days + 1):
        day = start_date.fromordinal(start_date.toordinal() + offset)
        if day in latest_checkins:
            days.append(PilotDayResponse(day=day, status="checkin", checkin=_checkin_response(latest_checkins[day])))
        elif day in zero_by_day:
            days.append(PilotDayResponse(day=day, status="zero_spending", zero_spending=_zero_response(zero_by_day[day])))
        else:
            days.append(PilotDayResponse(day=day, status="unknown"))
    return PilotDataResponse(
        start_date=start_date,
        end_date=end_date,
        days=days,
        ledger_entries=[_ledger_response(value) for value in ledger],
    )
