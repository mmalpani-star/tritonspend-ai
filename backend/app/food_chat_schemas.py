"""Request and response models for Food Chat. Authors appear only by pseudonym; no emails or
participant IDs are ever returned."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from .pilot_schemas import UtcDateTime

MAX_REVIEW_LENGTH = 2000
MAX_COMMENT_LENGTH = 1000
MAX_REPORT_DETAILS_LENGTH = 500
MAX_MODERATION_NOTE_LENGTH = 500


def _clean_text(value: Optional[str], limit: int, field: str, required: bool = True) -> Optional[str]:
    if value is None:
        if required:
            raise ValueError(f"{field} is required")
        return None
    cleaned = value.strip()
    if required and not cleaned:
        raise ValueError(f"{field} must not be empty")
    if len(cleaned) > limit:
        raise ValueError(f"{field} must be at most {limit} characters")
    return cleaned or None


# --- Requests ------------------------------------------------------------------------------------

class ReviewCreate(BaseModel):
    """A review is about a venue: students name any dish or station in their own words.

    "menu_item" reviews (a verified dish at a station) are still accepted for backward
    compatibility with older clients, but the app no longer offers them.
    """

    model_config = ConfigDict(extra="forbid")

    target_type: Literal["venue", "menu_item"] = "venue"
    venue_id: str = Field(max_length=64)
    station_id: Optional[str] = Field(default=None, max_length=128)
    menu_item_id: Optional[str] = Field(default=None, max_length=36)
    rating: StrictInt = Field(ge=1, le=5)
    body: str

    @field_validator("body")
    @classmethod
    def clean_body(cls, value: str) -> str:
        return _clean_text(value, MAX_REVIEW_LENGTH, "review")

    @model_validator(mode="after")
    def target_shape(self) -> "ReviewCreate":
        if self.target_type == "venue" and (self.station_id or self.menu_item_id):
            raise ValueError("a venue review cannot name a station or menu item")
        if self.target_type == "menu_item" and not (self.station_id and self.menu_item_id):
            raise ValueError("a dish review needs a station and a menu item")
        return self


class ReviewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: Optional[StrictInt] = Field(default=None, ge=1, le=5)
    body: Optional[str] = None

    @field_validator("body")
    @classmethod
    def clean_body(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else _clean_text(value, MAX_REVIEW_LENGTH, "review")

    @model_validator(mode="after")
    def something_to_change(self) -> "ReviewUpdate":
        if self.rating is None and self.body is None:
            raise ValueError("send a new rating or review text")
        return self


class CommentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str
    parent_id: Optional[str] = Field(default=None, max_length=36)

    @field_validator("body")
    @classmethod
    def clean_body(cls, value: str) -> str:
        return _clean_text(value, MAX_COMMENT_LENGTH, "comment")


class CommentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str

    @field_validator("body")
    @classmethod
    def clean_body(cls, value: str) -> str:
        return _clean_text(value, MAX_COMMENT_LENGTH, "comment")


class VoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Literal[1, -1]


ReportReasonName = Literal["spam", "harassment", "hate", "sexual_content", "misinformation", "off_topic", "other"]


class ReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: Optional[str] = Field(default=None, max_length=36)
    # Older content (written reviews and comments) can still be reported.
    review_id: Optional[str] = Field(default=None, max_length=36)
    comment_id: Optional[str] = Field(default=None, max_length=36)
    reason: ReportReasonName
    details: Optional[str] = None

    @field_validator("details")
    @classmethod
    def clean_details(cls, value: Optional[str]) -> Optional[str]:
        return _clean_text(value, MAX_REPORT_DETAILS_LENGTH, "details", required=False)

    @model_validator(mode="after")
    def exactly_one_target(self) -> "ReportCreate":
        if sum(bool(target) for target in (self.message_id, self.review_id, self.comment_id)) != 1:
            raise ValueError("report exactly one message, review or comment")
        return self


class ModerationContentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["hide", "restore", "remove"]
    note: Optional[str] = None

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: Optional[str]) -> Optional[str]:
        return _clean_text(value, MAX_MODERATION_NOTE_LENGTH, "note", required=False)


class ModerationReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["resolve", "dismiss"]
    note: Optional[str] = None

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: Optional[str]) -> Optional[str]:
        return _clean_text(value, MAX_MODERATION_NOTE_LENGTH, "note", required=False)


# --- Responses -----------------------------------------------------------------------------------

class NamedRef(BaseModel):
    id: str
    name: str


class RatingBreakdownOut(BaseModel):
    review_count: int
    average_rating: Optional[float] = None  # null = "No reviews yet"
    breakdown: dict[str, int]  # "1".."5" -> count of visible reviews


class ReviewOut(BaseModel):
    id: str
    target_type: Literal["venue", "menu_item"]
    venue: NamedRef
    station: Optional[NamedRef] = None
    menu_item: Optional[NamedRef] = None
    rating: int
    body: str
    author_name: str
    is_mine: bool
    edited: bool
    comment_count: int
    # Only shown to the author and moderators.
    moderation_state: Optional[Literal["visible", "hidden", "removed"]] = None
    created_at: UtcDateTime
    updated_at: UtcDateTime


class ReviewListOut(BaseModel):
    summary: RatingBreakdownOut
    reviews: list[ReviewOut]
    my_review: Optional[ReviewOut] = None
    total: int
    limit: int
    offset: int
    sort: Literal["newest", "highest", "lowest"]


class CommentOut(BaseModel):
    id: str
    parent_id: Optional[str] = None
    # A hidden or removed comment that still has visible replies is shown only as a placeholder.
    is_placeholder: bool
    body: Optional[str] = None
    author_name: Optional[str] = None
    is_mine: bool
    score: int
    upvotes: int
    downvotes: int
    my_vote: Literal[-1, 0, 1]
    edited: bool
    created_at: UtcDateTime


class CommentListOut(BaseModel):
    review_id: str
    comments: list[CommentOut]
    sort: Literal["top", "newest", "oldest"]


class VoteOut(BaseModel):
    comment_id: str
    score: int
    upvotes: int
    downvotes: int
    my_vote: Literal[-1, 0, 1]


class ReportOut(BaseModel):
    id: str
    status: Literal["open", "actioned", "dismissed"]


class FoodMeOut(BaseModel):
    display_name: Optional[str] = None  # assigned with the first Food Chat post
    is_moderator: bool
    consent_active: bool


class MenuItemDetailOut(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    dietary_labels: Optional[list[str]] = None
    allergens: Optional[list[str]] = None
    source_url: str
    verified_at: UtcDateTime
    is_active: bool
    station: NamedRef
    venue: NamedRef
    rating: RatingBreakdownOut


class ModeratedContentOut(BaseModel):
    kind: Literal["message", "review", "comment"]
    id: str
    body: Optional[str] = None
    rating: Optional[int] = None
    author_name: str
    moderation_state: Literal["visible", "hidden", "removed"]
    review_id: Optional[str] = None  # set for older reviews and comments; chat messages have none
    venue: NamedRef
    created_at: UtcDateTime


class ModerationReportOut(BaseModel):
    id: str
    reason: ReportReasonName
    details: Optional[str] = None
    status: Literal["open", "actioned", "dismissed"]
    created_at: UtcDateTime
    resolved_at: Optional[UtcDateTime] = None
    open_reports_on_target: int
    content: ModeratedContentOut


class ModerationQueueOut(BaseModel):
    reports: list[ModerationReportOut]
    total: int


class ModerationActionOut(BaseModel):
    id: str
    moderator_name: str
    action: Literal["hide", "restore", "remove", "resolve_report", "dismiss_report"]
    target_type: Literal["review", "comment", "report", "message"]
    target_id: str
    note: Optional[str] = None
    created_at: UtcDateTime


class ModerationHistoryOut(BaseModel):
    actions: list[ModerationActionOut]


# --- Venue ratings and venue chat ----------------------------------------------------------------

MAX_MESSAGE_LENGTH = 1000


class VenueRatingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: StrictInt = Field(ge=1, le=5)


class VenueRatingOut(BaseModel):
    venue_id: str
    average_rating: Optional[float] = None  # null = "No ratings yet", never 0
    rating_count: int  # students with a current rating; each counts once
    my_rating: Optional[int] = None  # the signed-in student's rating, if any


class MessageWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str

    @field_validator("body")
    @classmethod
    def clean_body(cls, value: str) -> str:
        return _clean_text(value, MAX_MESSAGE_LENGTH, "message")


class MessageOut(BaseModel):
    id: str
    author_name: str
    is_mine: bool
    body: str
    edited: bool
    created_at: UtcDateTime
    updated_at: UtcDateTime
    # Only shown to the author and moderators (others never see hidden or removed messages).
    moderation_state: Optional[Literal["visible", "hidden", "removed"]] = None


class MessagePageOut(BaseModel):
    venue_id: str
    messages: list[MessageOut]  # oldest first
    has_older: bool
