"""Participant-scoped wallet, threshold, forecast, and legacy ledger routes."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from tritonspend.core.errors import TritonSpendError
from tritonspend.core.forecast import forecast

from .db import get_db
from .dependencies import pilot_today_provider
from .mapping import to_core_input, to_response
from .participant_forecast import (
    CHARTABLE_SCHEMA_VERSIONS,
    END_OF_DAY_ENGINE_VERSION,
    END_OF_DAY_SNAPSHOT_SCHEMA_VERSION,
    ENGINE_VERSION,
    MAX_PARTICIPANT_FORECAST_DAYS,
    SNAPSHOT_SCHEMA_VERSION,
    STALE_BASELINE_DAYS,
    WALLET_SOURCE,
    build_trajectory,
    forecast_start,
    wallet_start_warnings,
)
from .backtest import evaluate as evaluate_backtest
from .personal_model import build_prediction, observations_from_checkins
from .schemas import ForecastRequest
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
    UserAccount,
    ZeroSpendingConfirmation,
)
from .pilot_schemas import (
    BalanceCheckinRequest,
    BalanceCheckinResponse,
    BalanceThresholdRequest,
    BalanceWarningResponse,
    BalanceWarningsResponse,
    ConsentHistoryItem,
    DeleteForecastResponse,
    DeleteParticipantRequest,
    DeleteParticipantResponse,
    ForecastSnapshotExportItem,
    ForecastTrajectoryResponse,
    LedgerEntryRequest,
    LedgerEntryResponse,
    ParticipantExportResponse,
    ParticipantForecastDetail,
    ParticipantForecastHistoryResponse,
    ParticipantForecastRequest,
    ParticipantForecastSummary,
    PilotDataResponse,
    PredictionResponse,
    as_utc,
    PilotDayResponse,
    WalletSaveRequest,
    WalletStatusResponse,
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


WALLET_HISTORY_LIMIT = 20


@router.get("/wallet", response_model=WalletStatusResponse)
def read_wallet(
    participant: Participant = Depends(get_current_participant),
    session: Session = Depends(get_db),
    today: date = Depends(pilot_today_provider),
) -> WalletStatusResponse:
    """Latest saved wallet balances (the starting point for saved forecasts) and thresholds."""
    history = session.scalars(
        select(BalanceCheckin)
        .where(
            BalanceCheckin.participant_id == participant.id,
            BalanceCheckin.effective_date <= today,
        )
        .order_by(
            BalanceCheckin.effective_date.desc(),
            BalanceCheckin.observed_at.desc(),
            BalanceCheckin.created_at.desc(),
        )
        .limit(WALLET_HISTORY_LIMIT)
    ).all()
    latest = history[0] if history else None
    threshold = session.scalar(
        select(ParticipantBalanceThreshold).where(
            ParticipantBalanceThreshold.participant_id == participant.id
        )
    )
    days_since_update = (today - latest.effective_date).days if latest is not None else None
    return WalletStatusResponse(
        latest=_checkin_response(latest) if latest is not None else None,
        history=[_checkin_response(value) for value in history],
        days_since_update=days_since_update,
        stale=days_since_update is not None and days_since_update > STALE_BASELINE_DAYS,
        stale_after_days=STALE_BASELINE_DAYS,
        thresholds=(
            BalanceThresholdRequest(
                dining_dollars_cents=threshold.dining_dollars_cents,
                triton_cash_cents=threshold.triton_cash_cents,
            )
            if threshold is not None
            else None
        ),
        warnings=_warnings_response(threshold, latest) if threshold is not None else None,
    )


@router.post(
    "/wallet",
    response_model=BalanceCheckinResponse,
    dependencies=[Depends(require_csrf), Depends(require_active_consent)],
)
def save_wallet_balances(
    payload: WalletSaveRequest,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
) -> BalanceCheckinResponse:
    """Save both balances as accurate on their as-of date; forecasts start on that date."""
    _reject_future(payload.effective_date, "effective_date")
    value = BalanceCheckin(
        participant_id=participant.id,
        observed_at=_utc_now(),
        effective_date=payload.effective_date,
        dining_dollars_cents=payload.dining_dollars_cents,
        triton_cash_cents=payload.triton_cash_cents,
        source=WALLET_SOURCE,
    )
    session.add(value)
    session.commit()
    session.refresh(value)
    return _checkin_response(value)


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
    account = session.scalar(select(UserAccount).where(UserAccount.participant_id == participant.id))
    response.headers["Content-Disposition"] = 'attachment; filename="tritonspend-data-export.json"'
    return ParticipantExportResponse(
        participant={
            "email": account.email if account is not None else None,
            "created_at": as_utc(participant.created_at),
            "deleted_at": as_utc(participant.deleted_at) if participant.deleted_at else None,
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
        # Removes the email and password hash; the email can be registered again.
        session.execute(delete(UserAccount).where(UserAccount.participant_id == participant.id))
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


def _owned_snapshot(session: Session, participant_id: str, forecast_id: str) -> ForecastSnapshot:
    snapshot = session.scalar(
        select(ForecastSnapshot).where(
            ForecastSnapshot.id == forecast_id,
            ForecastSnapshot.participant_id == participant_id,
        )
    )
    if snapshot is None:
        # Same response for missing and other participants' snapshots.
        raise HTTPException(status_code=404, detail="forecast not found")
    return snapshot


def _optional_wallet(value: object) -> dict | None:
    if isinstance(value, dict) and all(
        isinstance(value.get(key), int) for key in ("dining_dollars_cents", "triton_cash_cents")
    ):
        return value
    return None


def _forecast_summary(snapshot: ForecastSnapshot) -> ParticipantForecastSummary:
    # Tolerates snapshots that predate this workflow (e.g. imported fixtures).
    inputs = snapshot.request_json if isinstance(snapshot.request_json, dict) else {}
    output = snapshot.response_json if isinstance(snapshot.response_json, dict) else {}
    warnings = inputs.get("warnings")
    return ParticipantForecastSummary(
        id=snapshot.id,
        created_at=snapshot.created_at,
        start_date=snapshot.start_date,
        end_date=snapshot.end_date,
        engine_version=snapshot.engine_version,
        scenario=output.get("scenario") if isinstance(output.get("scenario"), str) else None,
        funds_last=output.get("funds_last") if isinstance(output.get("funds_last"), bool) else None,
        total_unfunded_cents=(
            output.get("total_unfunded_cents")
            if isinstance(output.get("total_unfunded_cents"), int)
            else None
        ),
        # v2 snapshots store "starting_balances"; legacy v1 stored "reconciled_balances".
        starting_balances=_optional_wallet(
            inputs.get("starting_balances", inputs.get("reconciled_balances"))
        ),
        projected_balances=_optional_wallet(output.get("projected_balances")),
        warnings=[item for item in warnings if isinstance(item, str)] if isinstance(warnings, list) else [],
    )


def _forecast_detail(snapshot: ForecastSnapshot) -> ParticipantForecastDetail:
    return ParticipantForecastDetail(
        id=snapshot.id,
        created_at=snapshot.created_at,
        start_date=snapshot.start_date,
        end_date=snapshot.end_date,
        engine_version=snapshot.engine_version,
        inputs=snapshot.request_json,
        forecast=snapshot.response_json,
    )


@router.post(
    "/forecasts",
    response_model=ParticipantForecastDetail,
    dependencies=[Depends(require_csrf), Depends(require_active_consent)],
)
def create_participant_forecast(
    payload: ParticipantForecastRequest,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
    today: date = Depends(pilot_today_provider),
) -> ParticipantForecastDetail:
    """Forecast from the latest saved wallet balances and save an immutable snapshot."""
    if payload.end_date < today:
        raise HTTPException(status_code=422, detail="end_date cannot be before today")
    wallet = session.scalar(
        select(BalanceCheckin)
        .where(
            BalanceCheckin.participant_id == participant.id,
            BalanceCheckin.effective_date <= today,
        )
        .order_by(
            BalanceCheckin.effective_date.desc(),
            BalanceCheckin.observed_at.desc(),
            BalanceCheckin.created_at.desc(),
        )
        .limit(1)
    )
    if wallet is None:
        raise HTTPException(
            status_code=422,
            detail="No wallet balances are saved yet. Save your Dining Dollars and Triton Cash "
            "balances before creating a forecast.",
        )
    as_of = wallet.effective_date
    # Wallet saves start on their as-of date; older end-of-day check-ins start the next day.
    start_date = forecast_start(wallet)
    starts_on_as_of = wallet.source == WALLET_SOURCE
    if payload.end_date < start_date:
        raise HTTPException(
            status_code=422,
            detail=f"end_date must be on or after {start_date.isoformat()}, the first day of this forecast",
        )
    if (payload.end_date - start_date).days + 1 > MAX_PARTICIPANT_FORECAST_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"forecast can cover at most {MAX_PARTICIPANT_FORECAST_DAYS} days from "
            f"{start_date.isoformat()}, the first day covered by your wallet balances. "
            "Update your wallet balances or choose an earlier end date.",
        )

    starting_balances = {
        "dining_dollars_cents": wallet.dining_dollars_cents,
        "triton_cash_cents": wallet.triton_cash_cents,
    }
    core_request = {
        "start_date": start_date.isoformat(),
        "end_date": payload.end_date.isoformat(),
        **starting_balances,
        "scenario": payload.scenario,
        "habits": [habit.model_dump() for habit in payload.habits],
    }
    try:
        # The engine's reference date is the projection start, so days between the
        # as-of date and today are projected rather than skipped.
        core_input = to_core_input(ForecastRequest.model_validate(core_request), start_date)
        result = forecast(
            core_input.date_range,
            core_input.balances,
            core_input.habits,
            core_input.scenario,
        )
    except (TritonSpendError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    threshold = session.scalar(
        select(ParticipantBalanceThreshold).where(
            ParticipantBalanceThreshold.participant_id == participant.id
        )
    )
    inputs = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION if starts_on_as_of else END_OF_DAY_SNAPSHOT_SCHEMA_VERSION,
        "created_on": today.isoformat(),
        # The as-of date of the starting balances (start of day for v3, end of day for v2).
        "reference_date": as_of.isoformat(),
        "start_date": start_date.isoformat(),
        "end_date": payload.end_date.isoformat(),
        "request": payload.model_dump(mode="json"),
        "balance_source": "latest_saved_wallet_balances",
        "wallet_balances": {
            "id": wallet.id,
            "effective_date": as_of.isoformat(),
            "observed_at": as_utc(wallet.observed_at).isoformat(),
            "source": wallet.source,
            **starting_balances,
        },
        "starting_balances": starting_balances,
        "targets": (
            {
                "dining_dollars_cents": threshold.dining_dollars_cents,
                "triton_cash_cents": threshold.triton_cash_cents,
            }
            if threshold is not None
            else None
        ),
        "warnings": list(wallet_start_warnings(as_of, today, start_date)),
        "core_request": core_request,
    }
    snapshot = ForecastSnapshot(
        participant_id=participant.id,
        start_date=start_date,
        end_date=payload.end_date,
        engine_version=ENGINE_VERSION if starts_on_as_of else END_OF_DAY_ENGINE_VERSION,
        request_json=inputs,
        response_json=to_response(result).model_dump(mode="json"),
    )
    session.add(snapshot)
    session.commit()
    session.refresh(snapshot)
    return _forecast_detail(snapshot)


@router.get("/forecasts", response_model=ParticipantForecastHistoryResponse)
def list_participant_forecasts(
    limit: int = Query(20, ge=1, le=100),
    participant: Participant = Depends(get_current_participant),
    session: Session = Depends(get_db),
) -> ParticipantForecastHistoryResponse:
    snapshots = session.scalars(
        select(ForecastSnapshot)
        .where(ForecastSnapshot.participant_id == participant.id)
        .order_by(ForecastSnapshot.created_at.desc(), ForecastSnapshot.id.desc())
        .limit(limit)
    ).all()
    return ParticipantForecastHistoryResponse(forecasts=[_forecast_summary(value) for value in snapshots])


@router.get("/forecasts/{forecast_id}", response_model=ParticipantForecastDetail)
def read_participant_forecast(
    forecast_id: str,
    participant: Participant = Depends(get_current_participant),
    session: Session = Depends(get_db),
) -> ParticipantForecastDetail:
    return _forecast_detail(_owned_snapshot(session, participant.id, forecast_id))


@router.delete(
    "/forecasts/{forecast_id}",
    response_model=DeleteForecastResponse,
    dependencies=[Depends(require_csrf), Depends(require_active_consent)],
)
def delete_participant_forecast(
    forecast_id: str,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
) -> DeleteForecastResponse:
    """Delete one of the participant's saved forecasts; nothing else is touched."""
    snapshot = _owned_snapshot(session, participant.id, forecast_id)
    session.delete(snapshot)
    session.commit()
    return DeleteForecastResponse(deleted=True, id=forecast_id)


@router.get("/forecasts/{forecast_id}/trajectory", response_model=ForecastTrajectoryResponse)
def read_participant_forecast_trajectory(
    forecast_id: str,
    participant: Participant = Depends(get_current_participant),
    session: Session = Depends(get_db),
) -> ForecastTrajectoryResponse:
    """Saved wallet balances vs. the stored projection vs. an even spend-down to target."""
    snapshot = _owned_snapshot(session, participant.id, forecast_id)
    inputs = snapshot.request_json if isinstance(snapshot.request_json, dict) else {}
    if inputs.get("schema_version") not in CHARTABLE_SCHEMA_VERSIONS:
        raise HTTPException(
            status_code=409,
            detail="this forecast snapshot was not created from saved data and cannot be charted",
        )
    start_date = date.fromisoformat(inputs["start_date"])
    # An end-of-day check-in the day before the forecast describes its first day's start.
    checkins = session.scalars(
        select(BalanceCheckin).where(
            BalanceCheckin.participant_id == participant.id,
            BalanceCheckin.effective_date.between(start_date - timedelta(days=1), snapshot.end_date),
        )
    ).all()
    return ForecastTrajectoryResponse.model_validate(
        build_trajectory(snapshot.id, inputs, snapshot.response_json, checkins)
    )


def _comparison(snapshot: ForecastSnapshot) -> Optional[dict]:
    """The selected saved forecast as a read-only reference: dates, saved targets, and its plan."""
    inputs = snapshot.request_json if isinstance(snapshot.request_json, dict) else {}
    output = snapshot.response_json if isinstance(snapshot.response_json, dict) else {}
    if inputs.get("schema_version") not in CHARTABLE_SCHEMA_VERSIONS:
        return None
    starting = _optional_wallet(inputs.get("starting_balances", inputs.get("reconciled_balances")))
    # The plan's balance at the start of its first day, then at the end of each day.
    plan = {snapshot.start_date: dict(starting)} if starting else {}
    for day in output.get("days", []):
        remaining = _optional_wallet(day.get("remaining_balances"))
        if remaining is not None:
            plan[date.fromisoformat(day["date"]) + timedelta(days=1)] = dict(remaining)
    return {
        "id": snapshot.id,
        "created_at": snapshot.created_at,
        "start_date": snapshot.start_date,
        "end_date": snapshot.end_date,
        "scenario": output.get("scenario") if isinstance(output.get("scenario"), str) else None,
        "targets": _optional_wallet(inputs.get("targets")),
        "plan": plan,
    }


@router.get("/prediction", response_model=PredictionResponse)
def read_personal_prediction(
    forecast_id: Optional[str] = Query(None),
    participant: Participant = Depends(get_current_participant),
    session: Session = Depends(get_db),
    today: date = Depends(pilot_today_provider),
) -> PredictionResponse:
    """Personalized prediction computed on request from this participant's saved balances only."""
    comparison = _comparison(_owned_snapshot(session, participant.id, forecast_id)) if forecast_id else None
    checkins = session.scalars(
        select(BalanceCheckin).where(BalanceCheckin.participant_id == participant.id)
    ).all()
    threshold = session.scalar(
        select(ParticipantBalanceThreshold).where(
            ParticipantBalanceThreshold.participant_id == participant.id
        )
    )
    current_targets = (
        {"dining_dollars_cents": threshold.dining_dollars_cents, "triton_cash_cents": threshold.triton_cash_cents}
        if threshold is not None
        else None
    )
    return PredictionResponse.model_validate(
        build_prediction(observations_from_checkins(checkins, today), today, comparison, current_targets)
    )


@router.get("/prediction/backtest")
def read_prediction_backtest(
    include_pairs: bool = Query(False),
    participant: Participant = Depends(get_current_participant),
    session: Session = Depends(get_db),
    today: date = Depends(pilot_today_provider),
) -> dict:
    """Developer diagnostic: rolling-origin backtest of the current model on this participant's own balances.

    Read-only and computed on request; nothing is stored. Not used by the student UI.
    """
    checkins = session.scalars(
        select(BalanceCheckin).where(BalanceCheckin.participant_id == participant.id)
    ).all()
    return evaluate_backtest(checkins, today, include_pairs=include_pairs)
