"""Signup, login, invite redemption, session lifecycle, consent, and CSRF routes."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, StrictStr, field_validator, model_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .models import ConsentEvent, ConsentEventType, InviteToken, Participant, ParticipantSession, UserAccount
from .passwords import burn_verification_time, hash_password, needs_rehash, verify_password
from .security import (
    CSRF_HEADER,
    SESSION_COOKIE,
    get_current_participant,
    get_current_session,
    hash_secret,
    make_secret,
    require_csrf,
    revoke_session,
    set_session_cookie,
    utc_now,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _require_trusted_origin(request: Request, settings: Settings) -> None:
    origin = request.headers.get("Origin")
    if origin and origin.rstrip("/") not in settings.cors_origins:
        raise HTTPException(status_code=403, detail="untrusted origin")


class RedeemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: StrictStr


MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
# Deliberately permissive: any address with a local part, "@", and a dotted domain.
# There is no email delivery, so addresses are not verified.
_EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$")
INVALID_CREDENTIALS = "Incorrect email or password."


def _normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or not _EMAIL_PATTERN.match(email):
        raise ValueError("Enter a valid email address.")
    return email


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: StrictStr
    password: StrictStr
    password_confirmation: StrictStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_email(value)

    @field_validator("password")
    @classmethod
    def check_password(cls, value: str) -> str:
        if not MIN_PASSWORD_LENGTH <= len(value) <= MAX_PASSWORD_LENGTH:
            raise ValueError(
                f"Password must be {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters."
            )
        if not value.strip():
            raise ValueError("Password cannot be only spaces.")
        return value

    @model_validator(mode="after")
    def passwords_match(self) -> "SignupRequest":
        if self.password != self.password_confirmation:
            raise ValueError("Passwords do not match.")
        if self.password.strip().lower() == self.email:
            raise ValueError("Password cannot be your email address.")
        return self


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: StrictStr
    password: StrictStr = ""


def _start_session(
    session: Session,
    response: Response,
    participant_id: str,
    settings: Settings,
    now: datetime,
) -> None:
    """Create a fresh random session (never reusing a prior token) and set its cookie."""
    raw_session = make_secret()
    session.add(
        ParticipantSession(
            participant_id=participant_id,
            session_token_hash=hash_secret(raw_session, settings.session_secret),
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=30),
        )
    )
    session.commit()
    set_session_cookie(response, raw_session, settings)


def _session_payload(participant_id: str, settings: Settings) -> dict:
    return {
        "participant_id": participant_id,
        "consent_version": settings.consent_version,
        "consent_document_url": settings.consent_document_url,
    }


class ConsentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_version_hash: Optional[StrictStr] = None


def _expected_document_hash(settings: Settings) -> str:
    if settings.consent_document_hash:
        return settings.consent_document_hash
    return hashlib.sha256(
        f"{settings.consent_version}\n{settings.consent_document_url}".encode("utf-8")
    ).hexdigest()


@router.post("/redeem")
def redeem_invite(
    payload: RedeemRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    _require_trusted_origin(request, settings)
    now = utc_now()
    token_id = session.scalar(
        update(InviteToken)
        .where(
            InviteToken.token_hash == hash_secret(payload.token, settings.session_secret),
            InviteToken.redeemed_at.is_(None),
            InviteToken.expires_at > now,
        )
        .values(redeemed_at=now)
        .returning(InviteToken.id)
    )
    if token_id is None:
        raise HTTPException(status_code=400, detail="invite is invalid or expired")
    token = session.get(InviteToken, token_id)
    if token is None:
        raise HTTPException(status_code=400, detail="invite is invalid or expired")
    participant = Participant()
    session.add(participant)
    session.flush()
    token.participant_id = participant.id
    _start_session(session, response, participant.id, settings, now)
    return _session_payload(participant.id, settings)


@router.post("/signup", status_code=201)
def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Create an email/password account and sign it in. Consent is still required before writes."""
    _require_trusted_origin(request, settings)
    if session.scalar(select(UserAccount.id).where(UserAccount.email == payload.email)) is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists. Sign in instead.")
    now = utc_now()
    participant = Participant()
    session.add(participant)
    session.flush()
    session.add(
        UserAccount(
            participant_id=participant.id,
            email=payload.email,
            password_hash=hash_password(payload.password),
            created_at=now,
            last_login_at=now,
        )
    )
    try:
        session.flush()
    except IntegrityError:
        # A concurrent signup with the same email won the unique constraint.
        session.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists. Sign in instead.")
    _start_session(session, response, participant.id, settings, now)
    return _session_payload(participant.id, settings)


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    _require_trusted_origin(request, settings)
    email = payload.email.strip().lower()
    account = session.scalar(select(UserAccount).where(UserAccount.email == email))
    if account is None:
        burn_verification_time(payload.password)
        raise HTTPException(status_code=401, detail=INVALID_CREDENTIALS)
    if not verify_password(account.password_hash, payload.password):
        raise HTTPException(status_code=401, detail=INVALID_CREDENTIALS)
    participant = session.get(Participant, account.participant_id)
    if participant is None or participant.deleted_at is not None:
        raise HTTPException(status_code=401, detail=INVALID_CREDENTIALS)
    now = utc_now()
    if needs_rehash(account.password_hash):
        account.password_hash = hash_password(payload.password)
    account.last_login_at = now
    _start_session(session, response, participant.id, settings, now)
    return _session_payload(participant.id, settings)


@router.get("/status")
def auth_status(
    current_session: ParticipantSession = Depends(get_current_session),
    participant: Participant = Depends(get_current_participant),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    latest = session.scalar(
        select(ConsentEvent)
        .where(ConsentEvent.participant_id == participant.id)
        .order_by(ConsentEvent.occurred_at.desc(), ConsentEvent.id.desc())
        .limit(1)
    )
    account = session.scalar(select(UserAccount).where(UserAccount.participant_id == participant.id))
    return {
        "authenticated": True,
        "email": account.email if account is not None else None,
        "consent_active": latest is not None and latest.event_type == ConsentEventType.accepted,
        "consent_version": settings.consent_version,
        "consent_document_url": settings.consent_document_url,
    }


@router.get("/csrf")
def issue_csrf(
    response: Response,
    current_session: ParticipantSession = Depends(get_current_session),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    raw_csrf = make_secret()
    current_session.csrf_token_hash = hash_secret(raw_csrf, settings.csrf_secret)
    session.commit()
    return {"csrf_token": raw_csrf, "header": CSRF_HEADER}


@router.post("/consent", dependencies=[Depends(require_csrf)])
def accept_consent(
    payload: ConsentRequest,
    current_participant: Participant = Depends(get_current_participant),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if not settings.consent_version or not settings.consent_document_url:
        raise HTTPException(status_code=503, detail="consent configuration is unavailable")
    expected_hash = _expected_document_hash(settings)
    if payload.document_version_hash is not None and payload.document_version_hash != expected_hash:
        raise HTTPException(status_code=422, detail="document version hash does not match configured consent")
    event = ConsentEvent(
        participant_id=current_participant.id,
        event_type=ConsentEventType.accepted,
        consent_version=settings.consent_version,
        document_url=settings.consent_document_url,
        document_version_hash=expected_hash,
    )
    session.add(event)
    session.commit()
    return {"consent_version": event.consent_version, "document_url": event.document_url}


@router.post("/consent/withdraw", dependencies=[Depends(require_csrf)])
def withdraw_consent(
    current_participant: Participant = Depends(get_current_participant),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    latest = session.scalar(
        select(ConsentEvent)
        .where(ConsentEvent.participant_id == current_participant.id)
        .order_by(ConsentEvent.occurred_at.desc(), ConsentEvent.id.desc())
        .limit(1)
    )
    if latest is None or latest.event_type != ConsentEventType.accepted:
        raise HTTPException(status_code=409, detail="active consent is not present")
    session.add(
        ConsentEvent(
            participant_id=current_participant.id,
            event_type=ConsentEventType.withdrawn,
            consent_version=settings.consent_version,
            document_url=settings.consent_document_url,
        )
    )
    session.commit()
    return {"withdrawn": True}


@router.post("/logout", dependencies=[Depends(require_csrf)])
def logout(
    response: Response,
    current_session: ParticipantSession = Depends(get_current_session),
    session: Session = Depends(get_db),
):
    revoke_session(current_session)
    session.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"logged_out": True}
