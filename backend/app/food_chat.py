"""Food Chat deletion rules, shared by single deletions and account deletion (policy agreed 2026-11-07).

- Deleting a review deletes its whole discussion: every comment in that thread (whoever wrote
  it), the votes on those comments, and reports on the review or its comments.
- Deleting a comment deletes the votes and reports on it. Other people's replies survive: each
  moves up to its nearest surviving ancestor in the same thread, or becomes top level.

When a participant deletes their account, ``delete_participant_food_chat`` applies these rules
to all of their reviews and comments, then deletes every vote and report they made, their
Food Chat pseudonym, their private favourite venues and dishes, their venue chat messages (with the
reports on them) and their venue ratings. Other participants' unrelated content is untouched. Functions only issue
statements on the caller's session; the caller commits (or rolls back) the whole operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from .food_models import (
    FoodChatMessage, FoodChatProfile, FoodComment, FoodCommentVote, FoodFavoriteDish, FoodFavoriteVenue, FoodReport, FoodReview,
    FoodVenueRating,
)


@dataclass
class FoodChatDeletion:
    reviews: int = 0
    comments: int = 0
    votes: int = 0
    reports: int = 0
    replies_reparented: int = 0
    favorites: int = 0
    messages: int = 0
    ratings: int = 0


def _nearest_surviving_parent(comment_id: str, parents: dict[str, Optional[str]], removed: set[str]) -> Optional[str]:
    """Walk up the thread from ``comment_id`` past removed comments; None means top level."""
    parent = parents[comment_id]
    while parent is not None and parent in removed:
        parent = parents[parent]
    return parent


def delete_reviews(session: Session, review_ids: Iterable[str], result: Optional[FoodChatDeletion] = None) -> FoodChatDeletion:
    """Delete reviews with their whole discussion threads."""
    result = result or FoodChatDeletion()
    review_ids = list(review_ids)
    if not review_ids:
        return result
    thread_comment_ids = list(session.scalars(select(FoodComment.id).where(FoodComment.review_id.in_(review_ids))))
    result.reports += session.execute(delete(FoodReport).where(or_(
        FoodReport.review_id.in_(review_ids), FoodReport.comment_id.in_(thread_comment_ids),
    ))).rowcount
    if thread_comment_ids:
        result.votes += session.execute(delete(FoodCommentVote).where(FoodCommentVote.comment_id.in_(thread_comment_ids))).rowcount
        # Detach replies first so no row ever points at an already-deleted parent.
        session.execute(update(FoodComment).where(FoodComment.id.in_(thread_comment_ids)).values(parent_id=None))
        result.comments += session.execute(delete(FoodComment).where(FoodComment.id.in_(thread_comment_ids))).rowcount
    result.reviews += session.execute(delete(FoodReview).where(FoodReview.id.in_(review_ids))).rowcount
    return result


def delete_comments_keeping_replies(session: Session, comment_ids: Iterable[str], result: Optional[FoodChatDeletion] = None) -> FoodChatDeletion:
    """Delete comments (with their votes and reports); surviving replies move up their thread."""
    result = result or FoodChatDeletion()
    removed = set(comment_ids)
    if not removed:
        return result
    threads = set(session.scalars(select(FoodComment.review_id).where(FoodComment.id.in_(removed))))
    parents = dict(session.execute(select(FoodComment.id, FoodComment.parent_id).where(FoodComment.review_id.in_(threads))).all())
    for comment_id, parent_id in parents.items():
        if comment_id not in removed and parent_id in removed:
            session.execute(
                update(FoodComment).where(FoodComment.id == comment_id)
                .values(parent_id=_nearest_surviving_parent(comment_id, parents, removed))
            )
            result.replies_reparented += 1
    result.reports += session.execute(delete(FoodReport).where(FoodReport.comment_id.in_(removed))).rowcount
    result.votes += session.execute(delete(FoodCommentVote).where(FoodCommentVote.comment_id.in_(removed))).rowcount
    session.execute(update(FoodComment).where(FoodComment.id.in_(removed)).values(parent_id=None))
    result.comments += session.execute(delete(FoodComment).where(FoodComment.id.in_(removed))).rowcount
    return result


def delete_messages(session: Session, message_ids: Iterable[str]) -> int:
    """Delete venue chat messages and every report on them. The caller commits."""
    ids = list(message_ids)
    if not ids:
        return 0
    session.execute(delete(FoodReport).where(FoodReport.message_id.in_(ids)))
    return session.execute(delete(FoodChatMessage).where(FoodChatMessage.id.in_(ids))).rowcount


def delete_participant_food_chat(session: Session, participant_id: str) -> FoodChatDeletion:
    result = FoodChatDeletion()
    # 0. Their venue chat messages (with reports on them) and their venue ratings.
    result.messages += delete_messages(session, session.scalars(select(FoodChatMessage.id).where(FoodChatMessage.participant_id == participant_id)))
    result.ratings += session.execute(delete(FoodVenueRating).where(FoodVenueRating.participant_id == participant_id)).rowcount
    # 1. Their reviews and those reviews' whole discussions.
    delete_reviews(session, session.scalars(select(FoodReview.id).where(FoodReview.participant_id == participant_id)), result)
    # 2. Their comments on other people's reviews; other people's replies move up the thread.
    delete_comments_keeping_replies(session, session.scalars(select(FoodComment.id).where(FoodComment.participant_id == participant_id)), result)
    # 3. Every remaining vote and report they made, and their pseudonym.
    result.votes += session.execute(delete(FoodCommentVote).where(FoodCommentVote.participant_id == participant_id)).rowcount
    result.reports += session.execute(delete(FoodReport).where(FoodReport.participant_id == participant_id)).rowcount
    session.execute(delete(FoodChatProfile).where(FoodChatProfile.participant_id == participant_id))
    # 4. Their private favourites.
    result.favorites += session.execute(delete(FoodFavoriteVenue).where(FoodFavoriteVenue.participant_id == participant_id)).rowcount
    result.favorites += session.execute(delete(FoodFavoriteDish).where(FoodFavoriteDish.participant_id == participant_id)).rowcount
    session.flush()
    return result
