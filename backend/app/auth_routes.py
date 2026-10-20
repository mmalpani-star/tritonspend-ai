"""Invite redemption, session lifecycle, consent, and CSRF routes."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, StrictStr
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .models import ConsentEvent, ConsentEventType, InviteToken, Participant, ParticipantSession
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
    raw_session = make_secret()
    session.add(
        ParticipantSession(
            participant_id=participant.id,
            session_token_hash=hash_secret(raw_session, settings.session_secret),
            created_at=now,
            last_seen_at=now,
            expires_at=now + timedelta(days=30),
        )
    )
    session.commit()
    set_session_cookie(response, raw_session, settings)
    return {
        "participant_id": participant.id,
        "consent_version": settings.consent_version,
        "consent_document_url": settings.consent_document_url,
    }


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
    return {
        "authenticated": True,
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
