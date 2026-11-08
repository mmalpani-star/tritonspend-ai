"""The signed-in participant's private pages: account summary, favourites, and their own activity.

Every route here reads or changes only the caller's own data, identified by the session; there is
no way to ask for another participant's favourites or activity. Reads need a session. Saving or
removing a favourite also needs the CSRF header and active consent, like every other saved data.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .food_catalog import menu_item_ratings, venue_ratings
from .food_chat_routes import ANONYMOUS_NAME, _edited, _ensure_profile, _is_moderator, _limit, _names, _review_out, _vote_totals
from .food_models import (
    FoodChatMessage,
    FoodComment,
    FoodFavoriteDish,
    FoodFavoriteVenue,
    FoodMenuItem,
    FoodReview,
    FoodStation,
    FoodVenue,
    FoodVenueRating,
    ModerationState,
)
from .me_schemas import (
    AccountOut,
    FavoriteChangeOut,
    FavoriteDishOut,
    FavoriteVenueOut,
    FavoritesOut,
    MyCommentsOut,
    MyMessagesOut,
    MyRatingsOut,
    MyReviewsOut,
)
from .models import ConsentEvent, ConsentEventType, Participant, UserAccount, _now
from .security import get_current_participant, require_active_consent, require_csrf

router = APIRouter(prefix="/api/v1/me", tags=["me"])
WRITE = [Depends(require_csrf)]


def _rating(summary) -> dict:
    return {"review_count": summary.review_count, "average_rating": summary.average_rating}


def _count(session: Session, model, participant_id: str) -> int:
    return session.scalar(select(func.count()).select_from(model).where(model.participant_id == participant_id)) or 0


# --- Account -----------------------------------------------------------------------------------

@router.get("/account", response_model=AccountOut)
def read_account(
    participant: Participant = Depends(get_current_participant),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AccountOut:
    account = session.scalar(select(UserAccount).where(UserAccount.participant_id == participant.id))
    latest = session.scalar(
        select(ConsentEvent).where(ConsentEvent.participant_id == participant.id)
        .order_by(ConsentEvent.occurred_at.desc(), ConsentEvent.id.desc()).limit(1)
    )
    consent_active = latest is not None and latest.event_type == ConsentEventType.accepted
    # The pseudonym is generated here once consent is active, so it can be shown before the first
    # post. It is part of Food Chat data: exported, and deleted with the account.
    display_name = None
    if consent_active:
        display_name = _ensure_profile(session, participant.id).display_name
        session.commit()
    return AccountOut(
        email=account.email if account is not None else None,
        account_created_at=account.created_at if account is not None else participant.created_at,
        last_login_at=account.last_login_at if account is not None else None,
        timezone=participant.timezone,
        consent={
            "active": consent_active,
            "version": latest.consent_version if consent_active else None,
            "accepted_at": latest.occurred_at if consent_active else None,
            "document_url": latest.document_url if consent_active else None,
        },
        display_name=display_name,
        is_moderator=_is_moderator(session, participant.id, settings),
        activity={
            "ratings": _count(session, FoodVenueRating, participant.id),
            "messages": _count(session, FoodChatMessage, participant.id),
            "favorite_venues": _count(session, FoodFavoriteVenue, participant.id),
            "favorite_dishes": _count(session, FoodFavoriteDish, participant.id),
        },
    )


# --- Favourites --------------------------------------------------------------------------------

@router.get("/favorites", response_model=FavoritesOut)
def read_favorites(participant: Participant = Depends(get_current_participant), session: Session = Depends(get_db)) -> FavoritesOut:
    venue_rows = session.execute(
        select(FoodVenue, FoodFavoriteVenue.created_at)
        .join(FoodFavoriteVenue, FoodFavoriteVenue.venue_id == FoodVenue.id)
        .where(FoodFavoriteVenue.participant_id == participant.id)
        .order_by(FoodFavoriteVenue.created_at.desc(), FoodVenue.name)
    ).all()
    dish_rows = session.execute(
        select(FoodMenuItem, FoodStation, FoodVenue, FoodFavoriteDish.created_at)
        .join(FoodFavoriteDish, FoodFavoriteDish.menu_item_id == FoodMenuItem.id)
        .join(FoodStation, FoodStation.id == FoodMenuItem.station_id)
        .join(FoodVenue, FoodVenue.id == FoodStation.venue_id)
        .where(FoodFavoriteDish.participant_id == participant.id)
        .order_by(FoodFavoriteDish.created_at.desc(), FoodMenuItem.name)
    ).all()
    v_ratings = venue_ratings(session, [venue.id for venue, _ in venue_rows])
    d_ratings = menu_item_ratings(session, [item.id for item, *_ in dish_rows])
    return FavoritesOut(
        venues=[
            {
                "id": venue.id, "name": venue.name, "kind": venue.kind.value, "campus_area": venue.campus_area,
                "location": venue.location, "is_active": venue.is_active, "rating": _rating(v_ratings[venue.id]), "saved_at": saved_at,
            }
            for venue, saved_at in venue_rows
        ],
        dishes=[
            {
                "id": item.id, "name": item.name, "description": item.description,
                "station": {"id": station.id, "name": station.name}, "venue": {"id": venue.id, "name": venue.name},
                "is_active": item.is_active and station.is_active and venue.is_active,
                "rating": _rating(d_ratings[item.id]), "saved_at": saved_at,
            }
            for item, station, venue, saved_at in dish_rows
        ],
    )


def _save(session: Session, record) -> None:
    session.add(record)
    try:
        session.commit()
    except IntegrityError:  # saved concurrently by another request: already a favourite
        session.rollback()


@router.put("/favorites/venues/{venue_id}", response_model=FavoriteChangeOut, dependencies=WRITE)
def save_favorite_venue(
    venue_id: str, participant: Participant = Depends(require_active_consent), session: Session = Depends(get_db),
) -> FavoriteChangeOut:
    venue = session.get(FoodVenue, venue_id)
    if venue is None or not venue.is_active:
        raise HTTPException(status_code=404, detail="venue not found")
    _limit(participant.id, "favorite")
    if session.get(FoodFavoriteVenue, (participant.id, venue_id)) is None:
        _save(session, FoodFavoriteVenue(participant_id=participant.id, venue_id=venue_id, created_at=_now()))
    return FavoriteChangeOut(kind="venue", id=venue_id, saved=True)


@router.delete("/favorites/venues/{venue_id}", response_model=FavoriteChangeOut, dependencies=WRITE)
def remove_favorite_venue(
    venue_id: str, participant: Participant = Depends(require_active_consent), session: Session = Depends(get_db),
) -> FavoriteChangeOut:
    _limit(participant.id, "favorite")
    record = session.get(FoodFavoriteVenue, (participant.id, venue_id))
    if record is not None:
        session.delete(record)
        session.commit()
    return FavoriteChangeOut(kind="venue", id=venue_id, saved=False)


@router.put("/favorites/dishes/{menu_item_id}", response_model=FavoriteChangeOut, dependencies=WRITE)
def save_favorite_dish(
    menu_item_id: str, participant: Participant = Depends(require_active_consent), session: Session = Depends(get_db),
) -> FavoriteChangeOut:
    item = session.get(FoodMenuItem, menu_item_id)
    if item is None or not item.is_active:
        raise HTTPException(status_code=404, detail="menu item not found")
    _limit(participant.id, "favorite")
    if session.get(FoodFavoriteDish, (participant.id, menu_item_id)) is None:
        _save(session, FoodFavoriteDish(participant_id=participant.id, menu_item_id=menu_item_id, created_at=_now()))
    return FavoriteChangeOut(kind="dish", id=menu_item_id, saved=True)


@router.delete("/favorites/dishes/{menu_item_id}", response_model=FavoriteChangeOut, dependencies=WRITE)
def remove_favorite_dish(
    menu_item_id: str, participant: Participant = Depends(require_active_consent), session: Session = Depends(get_db),
) -> FavoriteChangeOut:
    _limit(participant.id, "favorite")
    record = session.get(FoodFavoriteDish, (participant.id, menu_item_id))
    if record is not None:
        session.delete(record)
        session.commit()
    return FavoriteChangeOut(kind="dish", id=menu_item_id, saved=False)


# --- Your activity -----------------------------------------------------------------------------

@router.get("/reviews", response_model=MyReviewsOut)
def read_my_reviews(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    participant: Participant = Depends(get_current_participant),
    session: Session = Depends(get_db),
) -> MyReviewsOut:
    """All of the caller's reviews, including ones under moderation (with their state)."""
    mine = FoodReview.participant_id == participant.id
    total = session.scalar(select(func.count()).select_from(FoodReview).where(mine)) or 0
    reviews = list(session.scalars(
        select(FoodReview).where(mine).order_by(FoodReview.created_at.desc(), FoodReview.id).limit(limit).offset(offset)
    ))
    return MyReviewsOut(reviews=_review_out(session, reviews, participant.id), total=total, limit=limit, offset=offset)


@router.get("/comments", response_model=MyCommentsOut)
def read_my_comments(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    participant: Participant = Depends(get_current_participant),
    session: Session = Depends(get_db),
) -> MyCommentsOut:
    """The caller's comments and replies, newest first, with the review each belongs to."""
    mine = FoodComment.participant_id == participant.id
    total = session.scalar(select(func.count()).select_from(FoodComment).where(mine)) or 0
    comments = list(session.scalars(
        select(FoodComment).where(mine).order_by(FoodComment.created_at.desc(), FoodComment.id).limit(limit).offset(offset)
    ))
    if not comments:
        return MyCommentsOut(comments=[], total=total, limit=limit, offset=offset)

    reviews = {r.id: r for r in session.scalars(select(FoodReview).where(FoodReview.id.in_({c.review_id for c in comments})))}
    review_refs = {r["id"]: r for r in _review_out(session, list(reviews.values()), participant.id)}
    parent_ids = {c.parent_id for c in comments if c.parent_id}
    parents = {p.id: p for p in session.scalars(select(FoodComment).where(FoodComment.id.in_(parent_ids)))} if parent_ids else {}
    names = _names(session, {p.participant_id for p in parents.values() if p.moderation_state == ModerationState.visible})
    replies = dict(session.execute(
        select(FoodComment.parent_id, func.count())
        .where(FoodComment.parent_id.in_([c.id for c in comments]), FoodComment.moderation_state == ModerationState.visible)
        .group_by(FoodComment.parent_id)
    ).all())
    totals = _vote_totals(session, [c.id for c in comments])

    result = []
    for comment in comments:
        review = reviews[comment.review_id]
        ref = review_refs[review.id]
        parent = parents.get(comment.parent_id) if comment.parent_id else None
        replying_to: Optional[str] = None
        if parent is not None and parent.moderation_state == ModerationState.visible:
            replying_to = "you" if parent.participant_id == participant.id else names.get(parent.participant_id, ANONYMOUS_NAME)
        up, down = totals.get(comment.id, (0, 0))
        result.append({
            "id": comment.id,
            "body": comment.body,
            "is_reply": comment.parent_id is not None,
            "replying_to": replying_to,
            "moderation_state": comment.moderation_state.value,
            "score": up - down,
            "reply_count": replies.get(comment.id, 0),
            "edited": _edited(comment.created_at, comment.updated_at),
            "created_at": comment.created_at,
            "updated_at": comment.updated_at,
            "review_id": review.id,
            "review_available": review.moderation_state == ModerationState.visible,
            "review_rating": review.rating,
            "review_author": "you" if review.participant_id == participant.id else ref["author_name"],
            "venue": ref["venue"],
            "station": ref["station"],
            "menu_item": ref["menu_item"],
        })
    return MyCommentsOut(comments=result, total=total, limit=limit, offset=offset)


# --- Venue ratings and chat messages (the current Food Chat) ------------------------------------

@router.get("/ratings", response_model=MyRatingsOut)
def read_my_ratings(participant: Participant = Depends(get_current_participant), session: Session = Depends(get_db)) -> MyRatingsOut:
    """The caller's current venue ratings, most recently changed first, with each venue's average."""
    rows = session.execute(
        select(FoodVenueRating, FoodVenue.name).join(FoodVenue, FoodVenue.id == FoodVenueRating.venue_id)
        .where(FoodVenueRating.participant_id == participant.id)
        .order_by(FoodVenueRating.updated_at.desc(), FoodVenue.name)
    ).all()
    summaries = venue_ratings(session, [rating.venue_id for rating, _ in rows])
    return MyRatingsOut(ratings=[
        {"venue": {"id": rating.venue_id, "name": name}, "rating": rating.rating,
         "venue_average": summaries[rating.venue_id].average_rating, "venue_rating_count": summaries[rating.venue_id].review_count,
         "updated_at": rating.updated_at}
        for rating, name in rows
    ])


@router.get("/messages", response_model=MyMessagesOut)
def read_my_messages(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    participant: Participant = Depends(get_current_participant),
    session: Session = Depends(get_db),
) -> MyMessagesOut:
    """The caller's venue chat messages, newest first, including any a moderator hid."""
    mine = FoodChatMessage.participant_id == participant.id
    total = session.scalar(select(func.count()).select_from(FoodChatMessage).where(mine)) or 0
    rows = session.execute(
        select(FoodChatMessage, FoodVenue.name).join(FoodVenue, FoodVenue.id == FoodChatMessage.venue_id).where(mine)
        .order_by(FoodChatMessage.created_at.desc(), FoodChatMessage.id).limit(limit).offset(offset)
    ).all()
    return MyMessagesOut(messages=[
        {"id": m.id, "venue": {"id": m.venue_id, "name": name}, "body": m.body, "edited": _edited(m.created_at, m.updated_at),
         "moderation_state": m.moderation_state.value, "created_at": m.created_at, "updated_at": m.updated_at}
        for m, name in rows
    ], total=total, limit=limit, offset=offset)
