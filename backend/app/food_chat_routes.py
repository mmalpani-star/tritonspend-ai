"""Food Chat API: venue and dish reviews, threaded comments, votes, reports and moderation.

- Reads are public and show visible content only. A signed-in viewer additionally sees which
  items are theirs, their own vote, and their own review even while it is under moderation.
- Every write needs a session, the CSRF header and active consent; edits and deletions need
  ownership. Moderation needs an account email in TRITONSPEND_FOOD_MODERATOR_EMAILS.
- Authors appear only by pseudonym. Participant IDs and emails are never returned.
- Write limits are best-effort and per process (see food_rate_limit.py).
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings, get_settings
from .db import get_db
from .food_catalog import item_belongs_to
from .food_chat import delete_comments_keeping_replies, delete_reviews
from .food_chat_schemas import (
    CommentCreate,
    CommentListOut,
    CommentUpdate,
    FoodMeOut,
    MenuItemDetailOut,
    ModerationContentRequest,
    ModerationHistoryOut,
    ModerationQueueOut,
    ModerationReportRequest,
    ReportCreate,
    ReportOut,
    ReviewCreate,
    ReviewListOut,
    ReviewOut,
    ReviewUpdate,
    VoteOut,
    VoteRequest,
)
from .food_models import (
    FoodChatMessage,
    FoodChatProfile,
    FoodComment,
    FoodCommentVote,
    FoodMenuItem,
    FoodModerationAction,
    FoodReport,
    FoodReview,
    FoodStation,
    FoodVenue,
    ModerationAction,
    ModerationState,
    ModerationTarget,
    ReportReason,
    ReportStatus,
    ReviewTarget,
)
from .food_rate_limit import food_chat_limiter
from .models import ConsentEvent, ConsentEventType, Participant, UserAccount, _now
from .pilot_schemas import as_utc
from .security import SESSION_COOKIE, _active_session, get_current_participant, require_active_consent, require_csrf, utc_now

router = APIRouter(prefix="/api/v1/food", tags=["food-chat"])

MAX_REPLY_DEPTH = 8
ANONYMOUS_NAME = "Anonymous Triton"
_ADJECTIVES = (
    "Hungry", "Sleepy", "Sunny", "Breezy", "Curious", "Cheerful", "Clever", "Cozy", "Golden", "Quiet",
    "Salty", "Spicy", "Sweet", "Swift", "Tidal", "Brave", "Calm", "Lucky", "Mellow", "Zesty",
)
_NOUNS = (
    "Otter", "Pelican", "Seal", "Gull", "Dolphin", "Heron", "Sea Lion", "Tidepool", "Torrey Pine", "Sandpiper",
    "Kelp", "Starfish", "Sardine", "Avocado", "Taco", "Boba", "Bagel", "Burrito", "Noodle", "Mango",
)

WRITE = [Depends(require_csrf)]


# --- Viewer, profile and permission helpers ----------------------------------------------------

def optional_viewer(request: Request, session: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> Optional[str]:
    """The signed-in participant's ID, or None for anonymous (or expired) visitors."""
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    try:
        record = _active_session(session, raw, utc_now(), settings.session_secret)
    except HTTPException:
        return None
    participant = session.get(Participant, record.participant_id)
    return participant.id if participant is not None and participant.deleted_at is None else None


def _is_moderator(session: Session, participant_id: Optional[str], settings: Settings) -> bool:
    if participant_id is None or not settings.food_moderator_emails:
        return False
    email = session.scalar(select(UserAccount.email).where(UserAccount.participant_id == participant_id))
    return email is not None and email.lower() in settings.food_moderator_emails


def require_moderator(
    participant: Participant = Depends(get_current_participant),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Participant:
    if not _is_moderator(session, participant.id, settings):
        raise HTTPException(status_code=403, detail="Food Chat moderators only")
    return participant


def _ensure_profile(session: Session, participant_id: str) -> FoodChatProfile:
    profile = session.get(FoodChatProfile, participant_id)
    if profile is not None:
        return profile
    for _ in range(20):
        name = f"{secrets.choice(_ADJECTIVES)} {secrets.choice(_NOUNS)} {secrets.randbelow(9000) + 1000}"
        if session.scalar(select(FoodChatProfile.participant_id).where(FoodChatProfile.display_name == name)) is None:
            profile = FoodChatProfile(participant_id=participant_id, display_name=name, created_at=_now())
            session.add(profile)
            session.flush()
            return profile
    raise HTTPException(status_code=503, detail="Couldn't assign a Food Chat name; please try again")


def _names(session: Session, participant_ids: set[str]) -> dict[str, str]:
    if not participant_ids:
        return {}
    return dict(session.execute(
        select(FoodChatProfile.participant_id, FoodChatProfile.display_name).where(FoodChatProfile.participant_id.in_(participant_ids))
    ).all())


def _limit(participant_id: str, action: str) -> None:
    food_chat_limiter.check(participant_id, action)


def _edited(created_at: datetime, updated_at: datetime) -> bool:
    # SQLite returns naive UTC timestamps; values set in this request are aware.
    if created_at is None or updated_at is None:
        return False
    return as_utc(updated_at) > as_utc(created_at)


# --- Rating summaries --------------------------------------------------------------------------

def _rating_breakdown(session: Session, column, target_id: str, target: ReviewTarget) -> dict:
    rows = session.execute(
        select(FoodReview.rating, func.count())
        .where(column == target_id, FoodReview.target_type == target, FoodReview.moderation_state == ModerationState.visible)
        .group_by(FoodReview.rating)
    ).all()
    counts = {str(star): 0 for star in range(1, 6)}
    for rating, count in rows:
        counts[str(rating)] = count
    total = sum(counts.values())
    average = round(sum(int(star) * count for star, count in counts.items()) / total, 2) if total else None
    return {"review_count": total, "average_rating": average, "breakdown": counts}


# --- Review serialization ----------------------------------------------------------------------

def _review_out(session: Session, reviews: list[FoodReview], viewer: Optional[str], moderator: bool = False) -> list[dict]:
    if not reviews:
        return []
    venues = dict(session.execute(select(FoodVenue.id, FoodVenue.name).where(FoodVenue.id.in_({r.venue_id for r in reviews}))).all())
    station_ids = {r.station_id for r in reviews if r.station_id}
    stations = dict(session.execute(select(FoodStation.id, FoodStation.name).where(FoodStation.id.in_(station_ids))).all()) if station_ids else {}
    item_ids = {r.menu_item_id for r in reviews if r.menu_item_id}
    items = dict(session.execute(select(FoodMenuItem.id, FoodMenuItem.name).where(FoodMenuItem.id.in_(item_ids))).all()) if item_ids else {}
    names = _names(session, {r.participant_id for r in reviews})
    comment_counts = dict(session.execute(
        select(FoodComment.review_id, func.count())
        .where(FoodComment.review_id.in_([r.id for r in reviews]), FoodComment.moderation_state == ModerationState.visible)
        .group_by(FoodComment.review_id)
    ).all())
    result = []
    for review in reviews:
        mine = viewer is not None and review.participant_id == viewer
        result.append({
            "id": review.id,
            "target_type": review.target_type.value,
            "venue": {"id": review.venue_id, "name": venues.get(review.venue_id, review.venue_id)},
            "station": {"id": review.station_id, "name": stations[review.station_id]} if review.station_id else None,
            "menu_item": {"id": review.menu_item_id, "name": items[review.menu_item_id]} if review.menu_item_id else None,
            "rating": review.rating,
            "body": review.body,
            "author_name": names.get(review.participant_id, ANONYMOUS_NAME),
            "is_mine": mine,
            "edited": _edited(review.created_at, review.updated_at),
            "comment_count": comment_counts.get(review.id, 0),
            "moderation_state": review.moderation_state.value if (mine or moderator) else None,
            "created_at": review.created_at,
            "updated_at": review.updated_at,
        })
    return result


ReviewSort = Literal["newest", "highest", "lowest"]
_REVIEW_ORDER = {
    "newest": (FoodReview.created_at.desc(), FoodReview.id),
    "highest": (FoodReview.rating.desc(), FoodReview.created_at.desc(), FoodReview.id),
    "lowest": (FoodReview.rating.asc(), FoodReview.created_at.desc(), FoodReview.id),
}


def _review_list(session: Session, column, target_id: str, target: ReviewTarget, viewer: Optional[str],
                 sort: str, limit: int, offset: int) -> ReviewListOut:
    visible = (column == target_id, FoodReview.target_type == target, FoodReview.moderation_state == ModerationState.visible)
    total = session.scalar(select(func.count()).select_from(FoodReview).where(*visible))
    reviews = list(session.scalars(select(FoodReview).where(*visible).order_by(*_REVIEW_ORDER[sort]).limit(limit).offset(offset)))
    mine = None
    if viewer is not None:
        own = session.scalar(select(FoodReview).where(column == target_id, FoodReview.target_type == target, FoodReview.participant_id == viewer))
        mine = _review_out(session, [own], viewer)[0] if own is not None else None
    return ReviewListOut(
        summary=_rating_breakdown(session, column, target_id, target),
        reviews=_review_out(session, reviews, viewer),
        my_review=mine,
        total=total,
        limit=limit,
        offset=offset,
        sort=sort,
    )


def _visible_review(session: Session, review_id: str) -> FoodReview:
    review = session.get(FoodReview, review_id)
    if review is None or review.moderation_state != ModerationState.visible:
        raise HTTPException(status_code=404, detail="review not found")
    return review


def _own_review(session: Session, review_id: str, participant_id: str) -> FoodReview:
    review = session.get(FoodReview, review_id)
    if review is None or review.participant_id != participant_id:
        raise HTTPException(status_code=404, detail="review not found")  # never reveal others' reviews
    return review


# --- Public reads ------------------------------------------------------------------------------

@router.get("/me", response_model=FoodMeOut)
def read_food_me(
    participant: Participant = Depends(get_current_participant),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FoodMeOut:
    profile = session.get(FoodChatProfile, participant.id)
    latest = session.scalar(
        select(ConsentEvent.event_type).where(ConsentEvent.participant_id == participant.id)
        .order_by(ConsentEvent.occurred_at.desc(), ConsentEvent.id.desc()).limit(1)
    )
    return FoodMeOut(
        display_name=profile.display_name if profile else None,
        is_moderator=_is_moderator(session, participant.id, settings),
        consent_active=latest == ConsentEventType.accepted,
    )


@router.get("/venues/{venue_id}/reviews", response_model=ReviewListOut)
def list_venue_reviews(
    venue_id: str,
    sort: ReviewSort = Query("newest"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    viewer: Optional[str] = Depends(optional_viewer),
    session: Session = Depends(get_db),
) -> ReviewListOut:
    if session.get(FoodVenue, venue_id) is None:
        raise HTTPException(status_code=404, detail="venue not found")
    return _review_list(session, FoodReview.venue_id, venue_id, ReviewTarget.venue, viewer, sort, limit, offset)


@router.get("/menu-items/{menu_item_id}", response_model=MenuItemDetailOut)
def read_menu_item(menu_item_id: str, session: Session = Depends(get_db)) -> MenuItemDetailOut:
    item = session.get(FoodMenuItem, menu_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="menu item not found")
    station = session.get(FoodStation, item.station_id)
    venue = session.get(FoodVenue, station.venue_id)
    return MenuItemDetailOut(
        id=item.id, name=item.name, description=item.description, dietary_labels=item.dietary_labels,
        allergens=item.allergens, source_url=item.source_url, verified_at=item.verified_at, is_active=item.is_active,
        station={"id": station.id, "name": station.name}, venue={"id": venue.id, "name": venue.name},
        rating=_rating_breakdown(session, FoodReview.menu_item_id, item.id, ReviewTarget.menu_item),
    )


@router.get("/menu-items/{menu_item_id}/reviews", response_model=ReviewListOut)
def list_menu_item_reviews(
    menu_item_id: str,
    sort: ReviewSort = Query("newest"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    viewer: Optional[str] = Depends(optional_viewer),
    session: Session = Depends(get_db),
) -> ReviewListOut:
    if session.get(FoodMenuItem, menu_item_id) is None:
        raise HTTPException(status_code=404, detail="menu item not found")
    return _review_list(session, FoodReview.menu_item_id, menu_item_id, ReviewTarget.menu_item, viewer, sort, limit, offset)


@router.get("/reviews/{review_id}", response_model=ReviewOut)
def read_review(
    review_id: str,
    viewer: Optional[str] = Depends(optional_viewer),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ReviewOut:
    review = session.get(FoodReview, review_id)
    moderator = _is_moderator(session, viewer, settings)
    if review is None or (review.moderation_state != ModerationState.visible and review.participant_id != viewer and not moderator):
        raise HTTPException(status_code=404, detail="review not found")
    return ReviewOut(**_review_out(session, [review], viewer, moderator)[0])


CommentSort = Literal["top", "newest", "oldest"]


def _vote_totals(session: Session, comment_ids: list[str]) -> dict[str, tuple[int, int]]:
    if not comment_ids:
        return {}
    rows = session.execute(
        select(
            FoodCommentVote.comment_id,
            func.sum(case((FoodCommentVote.value == 1, 1), else_=0)),
            func.sum(case((FoodCommentVote.value == -1, 1), else_=0)),
        ).where(FoodCommentVote.comment_id.in_(comment_ids)).group_by(FoodCommentVote.comment_id)
    ).all()
    return {comment_id: (int(up or 0), int(down or 0)) for comment_id, up, down in rows}


@router.get("/reviews/{review_id}/comments", response_model=CommentListOut)
def list_review_comments(
    review_id: str,
    sort: CommentSort = Query("top"),
    viewer: Optional[str] = Depends(optional_viewer),
    session: Session = Depends(get_db),
) -> CommentListOut:
    _visible_review(session, review_id)
    comments = list(session.scalars(select(FoodComment).where(FoodComment.review_id == review_id)))
    by_id = {comment.id: comment for comment in comments}
    shown = {c.id for c in comments if c.moderation_state == ModerationState.visible}
    # Unavailable comments stay only as empty placeholders, and only when visible replies hang off them.
    placeholders: set[str] = set()
    for comment_id in shown:
        parent = by_id[comment_id].parent_id
        while parent is not None and parent not in shown:
            placeholders.add(parent)
            parent = by_id[parent].parent_id
    listed = [by_id[c] for c in shown | placeholders]
    totals = _vote_totals(session, [c.id for c in listed])
    mine = dict(session.execute(
        select(FoodCommentVote.comment_id, FoodCommentVote.value)
        .where(FoodCommentVote.participant_id == viewer, FoodCommentVote.comment_id.in_([c.id for c in listed]))
    ).all()) if viewer else {}
    names = _names(session, {c.participant_id for c in listed if c.id in shown})

    def score(comment):
        up, down = totals.get(comment.id, (0, 0))
        return up - down

    order = {
        "top": lambda c: (-score(c), as_utc(c.created_at), c.id),
        "newest": lambda c: (-as_utc(c.created_at).timestamp(), c.id),
        "oldest": lambda c: (as_utc(c.created_at), c.id),
    }[sort]
    result = []
    for comment in sorted(listed, key=order):
        placeholder = comment.id in placeholders
        up, down = totals.get(comment.id, (0, 0))
        result.append({
            "id": comment.id,
            "parent_id": comment.parent_id,
            "is_placeholder": placeholder,
            "body": None if placeholder else comment.body,
            "author_name": None if placeholder else names.get(comment.participant_id, ANONYMOUS_NAME),
            "is_mine": not placeholder and viewer is not None and comment.participant_id == viewer,
            "score": up - down,
            "upvotes": up,
            "downvotes": down,
            "my_vote": mine.get(comment.id, 0),
            "edited": not placeholder and _edited(comment.created_at, comment.updated_at),
            "created_at": comment.created_at,
        })
    return CommentListOut(review_id=review_id, comments=result, sort=sort)


# --- Reviews: create, edit, delete -------------------------------------------------------------

@router.post("/reviews", response_model=ReviewOut, status_code=201, dependencies=WRITE)
def create_review(
    payload: ReviewCreate,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
) -> ReviewOut:
    venue = session.get(FoodVenue, payload.venue_id)
    if venue is None or not venue.is_active:
        raise HTTPException(status_code=404, detail="venue not found")
    target = ReviewTarget(payload.target_type)
    if target == ReviewTarget.menu_item:
        item = session.get(FoodMenuItem, payload.menu_item_id)
        if item is None or not item.is_active or not item_belongs_to(session, venue.id, payload.station_id, item.id):
            raise HTTPException(status_code=422, detail="that menu item isn't on this station's verified menu at this venue")
        existing_filter = (FoodReview.menu_item_id == item.id,)
    else:
        existing_filter = (FoodReview.venue_id == venue.id,)
    existing = session.scalar(select(FoodReview.id).where(
        FoodReview.participant_id == participant.id, FoodReview.target_type == target, *existing_filter,
    ))
    if existing is not None:
        raise HTTPException(status_code=409, detail="You've already reviewed this. Edit your existing review instead.")
    _limit(participant.id, "review")
    _ensure_profile(session, participant.id)
    now = _now()
    review = FoodReview(
        participant_id=participant.id, target_type=target, venue_id=venue.id,
        station_id=payload.station_id if target == ReviewTarget.menu_item else None,
        menu_item_id=payload.menu_item_id if target == ReviewTarget.menu_item else None,
        rating=payload.rating, body=payload.body, created_at=now, updated_at=now,
    )
    session.add(review)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()  # a concurrent duplicate lost the unique index
        raise HTTPException(status_code=409, detail="You've already reviewed this. Edit your existing review instead.")
    return ReviewOut(**_review_out(session, [review], participant.id)[0])


@router.patch("/reviews/{review_id}", response_model=ReviewOut, dependencies=WRITE)
def update_review(
    review_id: str,
    payload: ReviewUpdate,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
) -> ReviewOut:
    review = _own_review(session, review_id, participant.id)
    if review.moderation_state != ModerationState.visible:
        raise HTTPException(status_code=409, detail="This review is under moderation and can't be edited.")
    _limit(participant.id, "edit")
    if payload.rating is not None:
        review.rating = payload.rating
    if payload.body is not None:
        review.body = payload.body
    review.updated_at = _now()
    session.commit()
    return ReviewOut(**_review_out(session, [review], participant.id)[0])


@router.delete("/reviews/{review_id}", status_code=204, dependencies=WRITE)
def delete_review(
    review_id: str,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
) -> Response:
    review = _own_review(session, review_id, participant.id)
    delete_reviews(session, [review.id])  # its discussion goes with it
    session.commit()
    return Response(status_code=204)


# --- Comments ----------------------------------------------------------------------------------

def _depth(session: Session, comment: FoodComment) -> int:
    depth, parent = 1, comment.parent_id
    while parent is not None:
        depth += 1
        parent = session.scalar(select(FoodComment.parent_id).where(FoodComment.id == parent))
    return depth


@router.post("/reviews/{review_id}/comments", status_code=201, dependencies=WRITE)
def create_comment(
    review_id: str,
    payload: CommentCreate,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
) -> dict:
    review = _visible_review(session, review_id)
    if payload.parent_id is not None:
        parent = session.get(FoodComment, payload.parent_id)
        if parent is None or parent.review_id != review.id or parent.moderation_state != ModerationState.visible:
            raise HTTPException(status_code=422, detail="you can only reply to a visible comment in this discussion")
        if _depth(session, parent) >= MAX_REPLY_DEPTH:
            raise HTTPException(status_code=422, detail=f"replies can be nested at most {MAX_REPLY_DEPTH} levels deep")
    _limit(participant.id, "comment")
    _ensure_profile(session, participant.id)
    now = _now()
    comment = FoodComment(review_id=review.id, parent_id=payload.parent_id, participant_id=participant.id,
                          body=payload.body, created_at=now, updated_at=now)
    session.add(comment)
    session.commit()
    return {"id": comment.id, "parent_id": comment.parent_id}


def _own_comment(session: Session, comment_id: str, participant_id: str) -> FoodComment:
    comment = session.get(FoodComment, comment_id)
    if comment is None or comment.participant_id != participant_id:
        raise HTTPException(status_code=404, detail="comment not found")
    return comment


@router.patch("/comments/{comment_id}", dependencies=WRITE)
def update_comment(
    comment_id: str,
    payload: CommentUpdate,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
) -> dict:
    comment = _own_comment(session, comment_id, participant.id)
    if comment.moderation_state != ModerationState.visible:
        raise HTTPException(status_code=409, detail="This comment is under moderation and can't be edited.")
    _limit(participant.id, "edit")
    comment.body = payload.body
    comment.updated_at = _now()
    session.commit()
    return {"id": comment.id, "body": comment.body}


@router.delete("/comments/{comment_id}", status_code=204, dependencies=WRITE)
def delete_comment(
    comment_id: str,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
) -> Response:
    comment = _own_comment(session, comment_id, participant.id)
    delete_comments_keeping_replies(session, [comment.id])  # other people's replies move up
    session.commit()
    return Response(status_code=204)


# --- Votes -------------------------------------------------------------------------------------

def _votable_comment(session: Session, comment_id: str, participant_id: str) -> FoodComment:
    comment = session.get(FoodComment, comment_id)
    if comment is None or comment.moderation_state != ModerationState.visible:
        raise HTTPException(status_code=404, detail="comment not found")
    _visible_review(session, comment.review_id)
    if comment.participant_id == participant_id:
        raise HTTPException(status_code=422, detail="you can't vote on your own comment")
    return comment


def _vote_out(session: Session, comment_id: str, participant_id: str) -> VoteOut:
    up, down = _vote_totals(session, [comment_id]).get(comment_id, (0, 0))
    mine = session.scalar(select(FoodCommentVote.value).where(FoodCommentVote.comment_id == comment_id, FoodCommentVote.participant_id == participant_id))
    return VoteOut(comment_id=comment_id, score=up - down, upvotes=up, downvotes=down, my_vote=mine or 0)


@router.put("/comments/{comment_id}/vote", response_model=VoteOut, dependencies=WRITE)
def vote_comment(
    comment_id: str,
    payload: VoteRequest,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
) -> VoteOut:
    comment = _votable_comment(session, comment_id, participant.id)
    _limit(participant.id, "vote")
    vote = session.scalar(select(FoodCommentVote).where(FoodCommentVote.comment_id == comment.id, FoodCommentVote.participant_id == participant.id))
    now = _now()
    if vote is None:
        session.add(FoodCommentVote(comment_id=comment.id, participant_id=participant.id, value=payload.value, created_at=now, updated_at=now))
    else:
        vote.value, vote.updated_at = payload.value, now
    session.commit()
    return _vote_out(session, comment.id, participant.id)


@router.delete("/comments/{comment_id}/vote", response_model=VoteOut, dependencies=WRITE)
def remove_vote(
    comment_id: str,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
) -> VoteOut:
    comment = session.get(FoodComment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="comment not found")
    vote = session.scalar(select(FoodCommentVote).where(FoodCommentVote.comment_id == comment.id, FoodCommentVote.participant_id == participant.id))
    if vote is not None:
        session.delete(vote)
        session.commit()
    return _vote_out(session, comment.id, participant.id)


# --- Reports -----------------------------------------------------------------------------------

@router.post("/reports", response_model=ReportOut, status_code=201, dependencies=WRITE)
def create_report(
    payload: ReportCreate,
    participant: Participant = Depends(require_active_consent),
    session: Session = Depends(get_db),
) -> ReportOut:
    if payload.message_id:
        target = session.get(FoodChatMessage, payload.message_id)
        if target is None or target.moderation_state != ModerationState.visible:
            raise HTTPException(status_code=404, detail="message not found")
        duplicate = FoodReport.message_id == target.id
    elif payload.review_id:
        target = _visible_review(session, payload.review_id)
        duplicate = FoodReport.review_id == target.id
    else:
        target = session.get(FoodComment, payload.comment_id)
        if target is None or target.moderation_state != ModerationState.visible:
            raise HTTPException(status_code=404, detail="comment not found")
        _visible_review(session, target.review_id)
        duplicate = FoodReport.comment_id == target.id
    if target.participant_id == participant.id:
        raise HTTPException(status_code=422, detail="you can't report your own post")
    if session.scalar(select(FoodReport.id).where(FoodReport.participant_id == participant.id, duplicate)) is not None:
        raise HTTPException(status_code=409, detail="You've already reported this. Thanks, a moderator will look at it.")
    _limit(participant.id, "report")
    report = FoodReport(participant_id=participant.id, message_id=payload.message_id, review_id=payload.review_id, comment_id=payload.comment_id,
                        reason=ReportReason(payload.reason), details=payload.details, created_at=_now())
    session.add(report)
    session.commit()
    return ReportOut(id=report.id, status=report.status.value)


# --- Moderation --------------------------------------------------------------------------------

def _record(session: Session, moderator_id: str, action: ModerationAction, target: ModerationTarget, target_id: str, note: Optional[str]) -> None:
    session.add(FoodModerationAction(moderator_participant_id=moderator_id, action=action, target_type=target,
                                     target_id=target_id, note=note, created_at=_now()))


_STATE_FOR_ACTION = {"hide": ModerationState.hidden, "restore": ModerationState.visible, "remove": ModerationState.removed}


@router.get("/moderation/reports", response_model=ModerationQueueOut)
def moderation_queue(
    status: Literal["open", "actioned", "dismissed", "all"] = Query("open"),
    limit: int = Query(50, ge=1, le=200),
    moderator: Participant = Depends(require_moderator),
    session: Session = Depends(get_db),
) -> ModerationQueueOut:
    condition = () if status == "all" else (FoodReport.status == ReportStatus(status),)
    total = session.scalar(select(func.count()).select_from(FoodReport).where(*condition))
    reports = list(session.scalars(select(FoodReport).where(*condition).order_by(FoodReport.created_at.asc(), FoodReport.id).limit(limit)))
    reviews = {r.id: r for r in session.scalars(select(FoodReview).where(FoodReview.id.in_({x.review_id for x in reports if x.review_id})))}
    comments = {c.id: c for c in session.scalars(select(FoodComment).where(FoodComment.id.in_({x.comment_id for x in reports if x.comment_id})))}
    messages = {m.id: m for m in session.scalars(select(FoodChatMessage).where(FoodChatMessage.id.in_({x.message_id for x in reports if x.message_id})))}
    parent_reviews = {r.id: r for r in session.scalars(select(FoodReview).where(FoodReview.id.in_({c.review_id for c in comments.values()})))}
    all_reviews = {**reviews, **parent_reviews}
    venue_ids = {r.venue_id for r in all_reviews.values()} | {m.venue_id for m in messages.values()}
    venues = dict(session.execute(select(FoodVenue.id, FoodVenue.name).where(FoodVenue.id.in_(venue_ids))).all())
    names = _names(session, {r.participant_id for r in reviews.values()} | {c.participant_id for c in comments.values()}
                   | {m.participant_id for m in messages.values()})
    target_key = func.coalesce(FoodReport.message_id, FoodReport.review_id, FoodReport.comment_id)
    open_counts = dict(session.execute(
        select(target_key, func.count()).where(FoodReport.status == ReportStatus.open).group_by(target_key)
    ).all())
    items = []
    for report in reports:
        if report.message_id:
            content = messages[report.message_id]
            items.append({
                "id": report.id, "reason": report.reason.value, "details": report.details, "status": report.status.value,
                "created_at": report.created_at, "resolved_at": report.resolved_at,
                "open_reports_on_target": open_counts.get(content.id, 0),
                "content": {
                    "kind": "message", "id": content.id, "body": content.body, "rating": None,
                    "author_name": names.get(content.participant_id, ANONYMOUS_NAME),
                    "moderation_state": content.moderation_state.value, "review_id": None,
                    "venue": {"id": content.venue_id, "name": venues.get(content.venue_id, content.venue_id)},
                    "created_at": content.created_at,
                },
            })
            continue
        if report.review_id:
            content = reviews[report.review_id]
            review = content
            kind, rating = "review", content.rating
        else:
            content = comments[report.comment_id]
            review = all_reviews[content.review_id]
            kind, rating = "comment", None
        items.append({
            "id": report.id, "reason": report.reason.value, "details": report.details, "status": report.status.value,
            "created_at": report.created_at, "resolved_at": report.resolved_at,
            "open_reports_on_target": open_counts.get(content.id, 0),
            "content": {
                "kind": kind, "id": content.id, "body": content.body, "rating": rating,
                "author_name": names.get(content.participant_id, ANONYMOUS_NAME),
                "moderation_state": content.moderation_state.value, "review_id": review.id,
                "venue": {"id": review.venue_id, "name": venues.get(review.venue_id, review.venue_id)},
                "created_at": content.created_at,
            },
        })
    return ModerationQueueOut(reports=items, total=total)


def _moderate(session: Session, model, content_id: str, payload: ModerationContentRequest, moderator: Participant, target: ModerationTarget) -> dict:
    content = session.get(model, content_id)
    if content is None:
        raise HTTPException(status_code=404, detail=f"{target.value} not found")
    content.moderation_state = _STATE_FOR_ACTION[payload.action]
    _record(session, moderator.id, ModerationAction(payload.action), target, content.id, payload.note)
    session.commit()
    return {"id": content.id, "moderation_state": content.moderation_state.value}


@router.post("/moderation/messages/{message_id}", dependencies=WRITE)
def moderate_message(
    message_id: str,
    payload: ModerationContentRequest,
    moderator: Participant = Depends(require_moderator),
    session: Session = Depends(get_db),
) -> dict:
    return _moderate(session, FoodChatMessage, message_id, payload, moderator, ModerationTarget.message)


@router.post("/moderation/reviews/{review_id}", dependencies=WRITE)
def moderate_review(
    review_id: str,
    payload: ModerationContentRequest,
    moderator: Participant = Depends(require_moderator),
    session: Session = Depends(get_db),
) -> dict:
    return _moderate(session, FoodReview, review_id, payload, moderator, ModerationTarget.review)


@router.post("/moderation/comments/{comment_id}", dependencies=WRITE)
def moderate_comment(
    comment_id: str,
    payload: ModerationContentRequest,
    moderator: Participant = Depends(require_moderator),
    session: Session = Depends(get_db),
) -> dict:
    return _moderate(session, FoodComment, comment_id, payload, moderator, ModerationTarget.comment)


@router.post("/moderation/reports/{report_id}", dependencies=WRITE)
def resolve_report(
    report_id: str,
    payload: ModerationReportRequest,
    moderator: Participant = Depends(require_moderator),
    session: Session = Depends(get_db),
) -> dict:
    report = session.get(FoodReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    report.status = ReportStatus.actioned if payload.action == "resolve" else ReportStatus.dismissed
    report.resolved_at = _now()
    _record(session, moderator.id, ModerationAction.resolve_report if payload.action == "resolve" else ModerationAction.dismiss_report,
            ModerationTarget.report, report.id, payload.note)
    session.commit()
    return {"id": report.id, "status": report.status.value}


@router.get("/moderation/actions", response_model=ModerationHistoryOut)
def moderation_history(
    limit: int = Query(50, ge=1, le=200),
    moderator: Participant = Depends(require_moderator),
    session: Session = Depends(get_db),
) -> ModerationHistoryOut:
    actions = list(session.scalars(select(FoodModerationAction).order_by(FoodModerationAction.created_at.desc(), FoodModerationAction.id).limit(limit)))
    names = _names(session, {a.moderator_participant_id for a in actions})
    return ModerationHistoryOut(actions=[
        {"id": a.id, "moderator_name": names.get(a.moderator_participant_id, "Moderator"), "action": a.action.value,
         "target_type": a.target_type.value, "target_id": a.target_id, "note": a.note, "created_at": a.created_at}
        for a in actions
    ])
