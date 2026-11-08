"""Food Chat: venue star ratings and each venue's flat, chronological group chat.

- Ratings: one per student per venue (unique constraint), changeable any time; the average is over
  every current rating for the venue. Independent of chat messages and of older written reviews.
- Chat: free-text messages tied only to a venue (never to a station, dish or review), shown oldest
  first, with "load older" paging and polling for new ones. No replies, votes or threads.
- Reads are public. Writes need a session, the CSRF header and active consent; edits and deletions
  need ownership; limits are best-effort and per process (food_rate_limit.py). Authors appear only
  by their Food Chat pseudonym, never an email or participant ID.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .food_chat_routes import ANONYMOUS_NAME, WRITE, _edited, _ensure_profile, _is_moderator, _limit, _names, optional_viewer
from .food_chat_schemas import MessageOut, MessagePageOut, MessageWrite, VenueRatingOut, VenueRatingRequest
from .food_chat import delete_messages
from .food_models import FoodChatMessage, FoodVenue, FoodVenueRating, ModerationState
from .models import Participant, _now
from .security import require_active_consent

router = APIRouter(prefix="/api/v1/food", tags=["food-chat"])

MAX_PAGE = 100


def _venue(session: Session, venue_id: str, *, for_writing: bool = False) -> FoodVenue:
    venue = session.get(FoodVenue, venue_id)
    if venue is None or (for_writing and not venue.is_active):
        raise HTTPException(status_code=404, detail="venue not found")
    return venue


# --- Ratings -----------------------------------------------------------------------------------

def _rating_summary(session: Session, venue_id: str, viewer: Optional[str]) -> VenueRatingOut:
    count, average = session.execute(
        select(func.count(FoodVenueRating.id), func.avg(FoodVenueRating.rating)).where(FoodVenueRating.venue_id == venue_id)
    ).one()
    mine = session.scalar(select(FoodVenueRating.rating).where(
        FoodVenueRating.venue_id == venue_id, FoodVenueRating.participant_id == viewer,
    )) if viewer else None
    return VenueRatingOut(
        venue_id=venue_id,
        average_rating=round(float(average), 2) if count else None,
        rating_count=count,
        my_rating=mine,
    )


@router.get("/venues/{venue_id}/rating", response_model=VenueRatingOut)
def read_venue_rating(venue_id: str, viewer: Optional[str] = Depends(optional_viewer), session: Session = Depends(get_db)) -> VenueRatingOut:
    _venue(session, venue_id)
    return _rating_summary(session, venue_id, viewer)


@router.put("/venues/{venue_id}/rating", response_model=VenueRatingOut, dependencies=WRITE)
def rate_venue(
    venue_id: str,
    payload: VenueRatingRequest,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
) -> VenueRatingOut:
    _venue(session, venue_id, for_writing=True)
    _limit(participant.id, "rating")
    now = _now()
    existing = session.scalar(select(FoodVenueRating).where(
        FoodVenueRating.venue_id == venue_id, FoodVenueRating.participant_id == participant.id,
    ))
    if existing is not None:
        existing.rating, existing.updated_at = payload.rating, now
    else:
        session.add(FoodVenueRating(participant_id=participant.id, venue_id=venue_id, rating=payload.rating, created_at=now, updated_at=now))
    try:
        session.commit()
    except IntegrityError:  # a concurrent first rating won the unique constraint: update that one
        session.rollback()
        row = session.scalar(select(FoodVenueRating).where(
            FoodVenueRating.venue_id == venue_id, FoodVenueRating.participant_id == participant.id,
        ))
        row.rating, row.updated_at = payload.rating, now
        session.commit()
    return _rating_summary(session, venue_id, participant.id)


@router.delete("/venues/{venue_id}/rating", response_model=VenueRatingOut, dependencies=WRITE)
def clear_venue_rating(
    venue_id: str, participant: Participant = Depends(require_active_consent), session: Session = Depends(get_db),
) -> VenueRatingOut:
    _venue(session, venue_id)
    _limit(participant.id, "rating")
    session.execute(delete(FoodVenueRating).where(FoodVenueRating.venue_id == venue_id, FoodVenueRating.participant_id == participant.id))
    session.commit()
    return _rating_summary(session, venue_id, participant.id)


# --- Chat --------------------------------------------------------------------------------------

def message_out(session: Session, messages: list[FoodChatMessage], viewer: Optional[str], moderator: bool = False) -> list[dict]:
    names = _names(session, {m.participant_id for m in messages})
    result = []
    for message in messages:
        mine = viewer is not None and message.participant_id == viewer
        result.append({
            "id": message.id,
            "author_name": names.get(message.participant_id, ANONYMOUS_NAME),
            "is_mine": mine,
            "body": message.body,
            "edited": _edited(message.created_at, message.updated_at),
            "created_at": message.created_at,
            "updated_at": message.updated_at,
            "moderation_state": message.moderation_state.value if (mine or moderator) else None,
        })
    return result


@router.get("/venues/{venue_id}/messages", response_model=MessagePageOut)
def list_messages(
    venue_id: str,
    before: Optional[str] = Query(None, max_length=36, description="a message id: return messages older than it"),
    limit: int = Query(50, ge=1, le=MAX_PAGE),
    viewer: Optional[str] = Depends(optional_viewer),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> MessagePageOut:
    """The newest `limit` messages (or those before `before`), returned oldest first. Everyone sees
    visible messages; authors also see their own hidden or removed ones."""
    _venue(session, venue_id)
    shown = FoodChatMessage.moderation_state == ModerationState.visible
    if viewer:
        shown = or_(shown, FoodChatMessage.participant_id == viewer)
    conditions = [FoodChatMessage.venue_id == venue_id, shown]
    if before:
        cursor = session.get(FoodChatMessage, before)
        if cursor is None or cursor.venue_id != venue_id:
            raise HTTPException(status_code=404, detail="message not found")
        conditions.append(or_(
            FoodChatMessage.created_at < cursor.created_at,
            and_(FoodChatMessage.created_at == cursor.created_at, FoodChatMessage.id < cursor.id),
        ))
    rows = list(session.scalars(
        select(FoodChatMessage).where(*conditions)
        .order_by(FoodChatMessage.created_at.desc(), FoodChatMessage.id.desc()).limit(limit + 1)
    ))
    has_older = len(rows) > limit
    page = list(reversed(rows[:limit]))
    return MessagePageOut(venue_id=venue_id, messages=message_out(session, page, viewer, _is_moderator(session, viewer, settings)), has_older=has_older)


@router.post("/venues/{venue_id}/messages", response_model=MessageOut, status_code=201, dependencies=WRITE)
def send_message(
    venue_id: str,
    payload: MessageWrite,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
) -> MessageOut:
    _venue(session, venue_id, for_writing=True)
    _limit(participant.id, "message")
    _ensure_profile(session, participant.id)
    now = _now()
    message = FoodChatMessage(venue_id=venue_id, participant_id=participant.id, body=payload.body, created_at=now, updated_at=now)
    session.add(message)
    session.commit()
    return MessageOut(**message_out(session, [message], participant.id)[0])


def _own_message(session: Session, message_id: str, participant_id: str) -> FoodChatMessage:
    message = session.get(FoodChatMessage, message_id)
    if message is None or message.participant_id != participant_id:
        raise HTTPException(status_code=404, detail="message not found")  # never reveal others' messages
    return message


@router.patch("/messages/{message_id}", response_model=MessageOut, dependencies=WRITE)
def edit_message(
    message_id: str,
    payload: MessageWrite,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
) -> MessageOut:
    message = _own_message(session, message_id, participant.id)
    if message.moderation_state != ModerationState.visible:
        raise HTTPException(status_code=409, detail="A moderator hid this message, so it can't be edited. You can delete it.")
    _limit(participant.id, "edit")
    message.body, message.updated_at = payload.body, _now()
    session.commit()
    return MessageOut(**message_out(session, [message], participant.id)[0])


@router.delete("/messages/{message_id}", status_code=204, dependencies=WRITE)
def delete_message(
    message_id: str, participant: Participant = Depends(require_active_consent), session: Session = Depends(get_db),
) -> Response:
    message = _own_message(session, message_id, participant.id)
    _limit(participant.id, "edit")
    delete_messages(session, [message.id])
    session.commit()
    return Response(status_code=204)
