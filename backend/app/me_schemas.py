"""Responses for the signed-in participant's private pages: account, favourites and activity."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

from .food_chat_schemas import NamedRef, ReviewOut
from .pilot_schemas import UtcDateTime


class ConsentSummaryOut(BaseModel):
    active: bool
    version: Optional[str] = None
    accepted_at: Optional[UtcDateTime] = None
    document_url: Optional[str] = None


class ActivityCountsOut(BaseModel):
    ratings: int
    messages: int
    favorite_venues: int
    favorite_dishes: int


class AccountOut(BaseModel):
    """Private to the account holder. The email is never shown to other users."""

    email: Optional[str] = None
    account_created_at: UtcDateTime
    last_login_at: Optional[UtcDateTime] = None
    timezone: str
    consent: ConsentSummaryOut
    display_name: Optional[str] = None  # Food Chat pseudonym; assigned once consent is active
    is_moderator: bool
    activity: ActivityCountsOut


class RatingOut(BaseModel):
    review_count: int
    average_rating: Optional[float] = None


class FavoriteVenueOut(BaseModel):
    id: str
    name: str
    kind: str
    campus_area: Optional[str] = None
    location: Optional[str] = None
    is_active: bool
    rating: RatingOut
    saved_at: UtcDateTime


class FavoriteDishOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    station: NamedRef
    venue: NamedRef
    is_active: bool
    rating: RatingOut
    saved_at: UtcDateTime


class FavoritesOut(BaseModel):
    venues: list[FavoriteVenueOut]
    dishes: list[FavoriteDishOut]


class FavoriteChangeOut(BaseModel):
    kind: Literal["venue", "dish"]
    id: str
    saved: bool


class MyReviewsOut(BaseModel):
    reviews: list[ReviewOut]
    total: int
    limit: int
    offset: int


class MyCommentOut(BaseModel):
    id: str
    body: str
    is_reply: bool
    replying_to: Optional[str] = None  # pseudonym of the comment being answered, if still available
    moderation_state: Literal["visible", "hidden", "removed"]
    score: int
    reply_count: int
    edited: bool
    created_at: UtcDateTime
    updated_at: UtcDateTime
    review_id: str
    review_available: bool  # False when the review it belongs to is hidden or removed
    review_rating: int
    review_author: str
    venue: NamedRef
    station: Optional[NamedRef] = None
    menu_item: Optional[NamedRef] = None


class MyCommentsOut(BaseModel):
    comments: list[MyCommentOut]
    total: int
    limit: int
    offset: int


class MyRatingOut(BaseModel):
    venue: NamedRef
    rating: int
    venue_average: Optional[float] = None
    venue_rating_count: int
    updated_at: UtcDateTime


class MyRatingsOut(BaseModel):
    ratings: list[MyRatingOut]


class MyMessageOut(BaseModel):
    id: str
    venue: NamedRef
    body: str
    edited: bool
    moderation_state: Literal["visible", "hidden", "removed"]
    created_at: UtcDateTime
    updated_at: UtcDateTime


class MyMessagesOut(BaseModel):
    messages: list[MyMessageOut]
    total: int
    limit: int
    offset: int
