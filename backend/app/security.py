"""Invite, session, participant authorization, consent, and CSRF primitives."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from . import db
from .db import get_db
from .models import ConsentEvent, ConsentEventType, InviteToken, Participant, ParticipantSession

SESSION_COOKIE = "tritonspend_session"
CSRF_HEADER = "X-CSRF-Token"
SESSION_MAX_AGE = timedelta(days=30)
SESSION_IDLE_TIMEOUT = timedelta(days=7)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_secret(value: str, secret: str) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def make_secret() -> str:
    return secrets.token_urlsafe(32)


def _active_session(
    session: Session,
    raw_token: str,
    now: datetime,
    session_secret: str,
) -> ParticipantSession:
    token_hash = hash_secret(raw_token, session_secret)
    record = session.scalar(
        select(ParticipantSession).where(ParticipantSession.session_token_hash == token_hash)
    )
    if record is None or record.revoked_at is not None:
        raise HTTPException(status_code=401, detail="session is invalid")
    expires_at = record.expires_at.replace(tzinfo=timezone.utc) if record.expires_at.tzinfo is None else record.expires_at
    last_seen_at = record.last_seen_at.replace(tzinfo=timezone.utc) if record.last_seen_at.tzinfo is None else record.last_seen_at
    if expires_at <= now or last_seen_at + SESSION_IDLE_TIMEOUT <= now:
        _persist_session_update(record.id, revoked_at=now)
        raise HTTPException(status_code=401, detail="session has expired")
    record.last_seen_at = now
    _persist_session_update(record.id, last_seen_at=now)
    return record


def _persist_session_update(
    session_id: str,
    *,
    last_seen_at: Optional[datetime] = None,
    revoked_at: Optional[datetime] = None,
) -> None:
    with db.get_session_factory().begin() as renewal_session:
        record = renewal_session.get(ParticipantSession, session_id)
        if record is None:
            return
        if last_seen_at is not None:
            record.last_seen_at = last_seen_at
        if revoked_at is not None:
            record.revoked_at = revoked_at


def get_current_session(
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ParticipantSession:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise HTTPException(status_code=401, detail="authentication required")
    return _active_session(session, raw_token, utc_now(), settings.session_secret)


def get_current_participant(
    current_session: ParticipantSession = Depends(get_current_session),
    session: Session = Depends(get_db),
) -> Participant:
    participant = session.get(Participant, current_session.participant_id)
    if participant is None or participant.deleted_at is not None:
        raise HTTPException(status_code=403, detail="participant is unavailable")
    return participant


def require_active_consent(
    current_session: ParticipantSession = Depends(get_current_session),
    session: Session = Depends(get_db),
) -> Participant:
    participant = session.get(Participant, current_session.participant_id)
    if participant is None or participant.deleted_at is not None:
        raise HTTPException(status_code=403, detail="participant is unavailable")
    latest = session.scalar(
        select(ConsentEvent)
        .where(ConsentEvent.participant_id == participant.id)
        .order_by(ConsentEvent.occurred_at.desc(), ConsentEvent.id.desc())
        .limit(1)
    )
    if latest is None or latest.event_type != ConsentEventType.accepted:
        raise HTTPException(status_code=403, detail="active consent is required")
    return participant


def require_csrf(
    request: Request,
    current_session: ParticipantSession = Depends(get_current_session),
    settings: Settings = Depends(get_settings),
) -> None:
    header = request.headers.get(CSRF_HEADER)
    if not header or not current_session.csrf_token_hash:
        raise HTTPException(status_code=403, detail="CSRF token is required")
    expected = hash_secret(header, settings.csrf_secret)
    if not hmac.compare_digest(expected, current_session.csrf_token_hash):
        raise HTTPException(status_code=403, detail="CSRF token is invalid")


def set_session_cookie(response: Response, raw_token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        max_age=int(SESSION_MAX_AGE.total_seconds()),
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",
    )


def revoke_session(record: ParticipantSession, now: Optional[datetime] = None) -> None:
    record.revoked_at = now or utc_now()
