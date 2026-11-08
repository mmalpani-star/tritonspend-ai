"""Food Nearby persistence: Venue -> Station -> Menu Item -> Menu Appearance, plus Food Chat.

Catalog tables (venues, stations) are seeded from ``data/food_catalog.json`` by
``food_catalog.seed_food_catalog``. Menu items and appearances are only ever written from
a verified menu source; nothing here is sample data.

Integrity is enforced by the database, not just the API:

- A station belongs to exactly one venue; a menu item to exactly one station.
- Reviews target either a whole venue (no station or item) or one menu item, and composite
  foreign keys make the chosen station belong to the venue and the item to the station.
- One review per participant per venue, and per menu item (partial unique indexes).
- Replies stay in their review's thread: (parent_id, review_id) references (id, review_id).
- One vote (+1 / -1) per participant per comment.
- A report targets exactly one review or one comment, through real foreign keys.

Ratings are never stored: they are aggregated from visible reviews when read.
SQLite enforces foreign keys only with ``PRAGMA foreign_keys=ON``; PostgreSQL always does.
"""

from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base
from .models import _id, _now


class WalletAcceptance(str, enum.Enum):
    accepted = "accepted"
    not_accepted = "not_accepted"
    not_verified = "not_verified"


class VenueOperator(str, enum.Enum):
    hdh = "hdh"
    triton_cash_partner = "triton_cash_partner"


class VenueKind(str, enum.Enum):
    restaurant = "restaurant"
    market = "market"
    merchant = "merchant"


class MenuAvailability(str, enum.Enum):
    """Being listed on a menu is not the same as being available now."""

    unknown = "unknown"
    available = "available"
    sold_out = "sold_out"
    unavailable = "unavailable"


class ReviewTarget(str, enum.Enum):
    venue = "venue"
    menu_item = "menu_item"


class ModerationState(str, enum.Enum):
    visible = "visible"
    hidden = "hidden"
    removed = "removed"


class ReportReason(str, enum.Enum):
    spam = "spam"
    harassment = "harassment"
    hate = "hate"
    sexual_content = "sexual_content"
    misinformation = "misinformation"
    off_topic = "off_topic"
    other = "other"


class ReportStatus(str, enum.Enum):
    open = "open"
    actioned = "actioned"
    dismissed = "dismissed"


# Unknown is SQL NULL, so "IS NULL" finds it (plain JSON would store the JSON text "null").
NULLABLE_JSON = JSON(none_as_null=True)


def _enum(enum_class: type[enum.Enum]) -> Enum:
    # Stored as plain strings (with the CHECK constraints below) for SQLite/PostgreSQL portability.
    return Enum(enum_class, native_enum=False, create_constraint=False, length=32)


def _in(column: str, enum_class: type[enum.Enum]) -> str:
    return f"{column} IN ({', '.join(repr(member.value) for member in enum_class)})"


# --- Catalog -----------------------------------------------------------------------------------

class FoodVenue(Base):
    __tablename__ = "food_venues"
    __table_args__ = (
        CheckConstraint(_in("operator", VenueOperator), name="ck_food_venues_operator_valid"),
        CheckConstraint(_in("kind", VenueKind), name="ck_food_venues_kind_valid"),
        CheckConstraint(_in("dining_dollars_acceptance", WalletAcceptance), name="ck_food_venues_dd_acceptance_valid"),
        CheckConstraint(_in("triton_cash_acceptance", WalletAcceptance), name="ck_food_venues_tc_acceptance_valid"),
        # Coordinates come as a verified pair or not at all.
        CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="ck_food_venues_coordinates_paired"),
        CheckConstraint(
            "latitude IS NULL OR (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)",
            name="ck_food_venues_coordinates_range",
        ),
        Index("ix_food_venues_operator", "operator"),
        Index("ix_food_venues_is_active", "is_active"),
    )

    # Stable catalog slug, e.g. "64-degrees" (kept from the original frontend catalog).
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    operator: Mapped[VenueOperator] = mapped_column(_enum(VenueOperator), nullable=False)
    kind: Mapped[VenueKind] = mapped_column(_enum(VenueKind), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    campus_area: Mapped[Optional[str]] = mapped_column(String(200))
    location: Mapped[Optional[str]] = mapped_column(String(200))
    on_campus: Mapped[bool] = mapped_column(Boolean, nullable=False)
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)
    # Where the coordinates came from: {"layer", "feature", "building"} on the official campus map.
    coordinates_source: Mapped[Optional[dict]] = mapped_column(NULLABLE_JSON)
    # Published weekly hours: {"mon": [["07:00", "23:00"]], ...}; null when not verified.
    hours: Mapped[Optional[dict]] = mapped_column(NULLABLE_JSON)
    menu_url: Mapped[Optional[str]] = mapped_column(String(1000))
    website_url: Mapped[Optional[str]] = mapped_column(String(1000))
    dining_dollars_acceptance: Mapped[WalletAcceptance] = mapped_column(_enum(WalletAcceptance), nullable=False)
    dining_dollars_reason: Mapped[str] = mapped_column(String(300), nullable=False)
    dining_dollars_source: Mapped[Optional[str]] = mapped_column(String(64))
    triton_cash_acceptance: Mapped[WalletAcceptance] = mapped_column(_enum(WalletAcceptance), nullable=False)
    triton_cash_reason: Mapped[str] = mapped_column(String(300), nullable=False)
    triton_cash_source: Mapped[Optional[str]] = mapped_column(String(64))
    # [{"key", "label", "url"}] for every official source behind this record.
    sources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    catalog_version: Mapped[str] = mapped_column(String(64), nullable=False)
    verified_on: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class FoodStation(Base):
    __tablename__ = "food_stations"
    __table_args__ = (
        UniqueConstraint("venue_id", "name", name="uq_food_stations_venue_name"),
        # Target of the composite foreign key that keeps a review's station inside its venue.
        UniqueConstraint("id", "venue_id", name="uq_food_stations_id_venue"),
        Index("ix_food_stations_venue_id", "venue_id"),
    )

    # Deterministic: "<venue id>--<station slug>", e.g. "64-degrees--triton-grill".
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    venue_id: Mapped[str] = mapped_column(ForeignKey("food_venues.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    menu_url: Mapped[Optional[str]] = mapped_column(String(1000))
    hours: Mapped[Optional[dict]] = mapped_column(NULLABLE_JSON)
    sources: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    catalog_version: Mapped[str] = mapped_column(String(64), nullable=False)
    verified_on: Mapped[date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class FoodMenuItem(Base):
    """A dish with a stable identity at one station, across all of its dated appearances."""

    __tablename__ = "food_menu_items"
    __table_args__ = (
        # The identity rule: one item per normalized name per station (see food_catalog.menu_name_key).
        UniqueConstraint("station_id", "name_key", name="uq_food_menu_items_station_name_key"),
        UniqueConstraint("id", "station_id", name="uq_food_menu_items_id_station"),
        CheckConstraint("length(name_key) > 0", name="ck_food_menu_items_name_key_nonempty"),
        Index("ix_food_menu_items_station_id", "station_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    station_id: Mapped[str] = mapped_column(ForeignKey("food_stations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    name_key: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # Only labels published by the source (e.g. ["vegan"]); null when the source gives none.
    dietary_labels: Mapped[Optional[list]] = mapped_column(NULLABLE_JSON)
    allergens: Mapped[Optional[list]] = mapped_column(NULLABLE_JSON)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class FoodMenuAppearance(Base):
    """One dated listing of a menu item. Price and availability are unknown unless the source says."""

    __tablename__ = "food_menu_appearances"
    __table_args__ = (
        UniqueConstraint("menu_item_id", "menu_date", "meal_period", name="uq_food_menu_appearances_item_date_period"),
        CheckConstraint("price_cents IS NULL OR price_cents >= 0", name="ck_food_menu_appearances_price_nonnegative"),
        CheckConstraint("currency = 'USD'", name="ck_food_menu_appearances_currency_usd"),
        CheckConstraint(_in("availability", MenuAvailability), name="ck_food_menu_appearances_availability_valid"),
        CheckConstraint("length(meal_period) > 0", name="ck_food_menu_appearances_meal_period_nonempty"),
        Index("ix_food_menu_appearances_menu_item_id", "menu_item_id"),
        Index("ix_food_menu_appearances_menu_date", "menu_date"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    menu_item_id: Mapped[str] = mapped_column(ForeignKey("food_menu_items.id"), nullable=False)
    menu_date: Mapped[date] = mapped_column(Date, nullable=False)
    # As published (normalized lowercase), e.g. "breakfast", "lunch", "dinner", "late night".
    meal_period: Mapped[str] = mapped_column(String(32), nullable=False)
    price_cents: Mapped[Optional[int]] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD", server_default="USD")
    availability: Mapped[MenuAvailability] = mapped_column(
        _enum(MenuAvailability), nullable=False, default=MenuAvailability.unknown, server_default="unknown"
    )
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


# --- Food Chat ---------------------------------------------------------------------------------

class FoodReview(Base):
    __tablename__ = "food_reviews"
    __table_args__ = (
        CheckConstraint(_in("target_type", ReviewTarget), name="ck_food_reviews_target_type_valid"),
        CheckConstraint(
            "(target_type = 'venue' AND station_id IS NULL AND menu_item_id IS NULL)"
            " OR (target_type = 'menu_item' AND station_id IS NOT NULL AND menu_item_id IS NOT NULL)",
            name="ck_food_reviews_target_shape",
        ),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_food_reviews_rating_range"),
        CheckConstraint("length(body) <= 5000", name="ck_food_reviews_body_length"),
        CheckConstraint(_in("moderation_state", ModerationState), name="ck_food_reviews_moderation_valid"),
        # The station must belong to the venue, and the item to the station.
        ForeignKeyConstraint(
            ["station_id", "venue_id"], ["food_stations.id", "food_stations.venue_id"],
            name="fk_food_reviews_station_in_venue",
        ),
        ForeignKeyConstraint(
            ["menu_item_id", "station_id"], ["food_menu_items.id", "food_menu_items.station_id"],
            name="fk_food_reviews_item_in_station",
        ),
        # One review per participant per target; a second submission updates the first.
        Index(
            "uq_food_reviews_participant_venue", "participant_id", "venue_id", unique=True,
            sqlite_where=text("target_type = 'venue'"), postgresql_where=text("target_type = 'venue'"),
        ),
        Index(
            "uq_food_reviews_participant_item", "participant_id", "menu_item_id", unique=True,
            sqlite_where=text("target_type = 'menu_item'"), postgresql_where=text("target_type = 'menu_item'"),
        ),
        Index("ix_food_reviews_venue_id", "venue_id"),
        Index("ix_food_reviews_menu_item_id", "menu_item_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), nullable=False)
    target_type: Mapped[ReviewTarget] = mapped_column(_enum(ReviewTarget), nullable=False)
    venue_id: Mapped[str] = mapped_column(ForeignKey("food_venues.id"), nullable=False)
    station_id: Mapped[Optional[str]] = mapped_column(String(128))
    menu_item_id: Mapped[Optional[str]] = mapped_column(String(36))
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    moderation_state: Mapped[ModerationState] = mapped_column(
        _enum(ModerationState), nullable=False, default=ModerationState.visible, server_default="visible"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class FoodComment(Base):
    __tablename__ = "food_comments"
    __table_args__ = (
        UniqueConstraint("id", "review_id", name="uq_food_comments_id_review"),
        # A reply's parent must be a comment on the same review.
        ForeignKeyConstraint(
            ["parent_id", "review_id"], ["food_comments.id", "food_comments.review_id"],
            name="fk_food_comments_parent_same_review",
        ),
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_food_comments_not_own_parent"),
        CheckConstraint("length(body) BETWEEN 1 AND 5000", name="ck_food_comments_body_length"),
        CheckConstraint(_in("moderation_state", ModerationState), name="ck_food_comments_moderation_valid"),
        Index("ix_food_comments_review_id", "review_id"),
        Index("ix_food_comments_parent_id", "parent_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    review_id: Mapped[str] = mapped_column(ForeignKey("food_reviews.id"), nullable=False)
    parent_id: Mapped[Optional[str]] = mapped_column(String(36))
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    moderation_state: Mapped[ModerationState] = mapped_column(
        _enum(ModerationState), nullable=False, default=ModerationState.visible, server_default="visible"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class FoodCommentVote(Base):
    __tablename__ = "food_comment_votes"
    __table_args__ = (
        UniqueConstraint("comment_id", "participant_id", name="uq_food_comment_votes_comment_participant"),
        CheckConstraint("value IN (-1, 1)", name="ck_food_comment_votes_value"),
        Index("ix_food_comment_votes_participant_id", "participant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    comment_id: Mapped[str] = mapped_column(ForeignKey("food_comments.id"), nullable=False)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), nullable=False)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


REPORT_EXACTLY_ONE_TARGET = (
    "(review_id IS NOT NULL AND comment_id IS NULL AND message_id IS NULL)"
    " OR (review_id IS NULL AND comment_id IS NOT NULL AND message_id IS NULL)"
    " OR (review_id IS NULL AND comment_id IS NULL AND message_id IS NOT NULL)"
)


class FoodReport(Base):
    """A report on exactly one chat message (or, historically, one review or comment); each target
    is a real foreign key."""

    __tablename__ = "food_reports"
    __table_args__ = (
        CheckConstraint(REPORT_EXACTLY_ONE_TARGET, name="ck_food_reports_exactly_one_target"),
        CheckConstraint(_in("reason", ReportReason), name="ck_food_reports_reason_valid"),
        CheckConstraint(_in("status", ReportStatus), name="ck_food_reports_status_valid"),
        CheckConstraint("details IS NULL OR length(details) <= 2000", name="ck_food_reports_details_length"),
        # One open-or-closed report per reporter per target (NULL targets never collide).
        UniqueConstraint("participant_id", "review_id", name="uq_food_reports_participant_review"),
        UniqueConstraint("participant_id", "comment_id", name="uq_food_reports_participant_comment"),
        UniqueConstraint("participant_id", "message_id", name="uq_food_reports_participant_message"),
        Index("ix_food_reports_status", "status"),
        Index("ix_food_reports_review_id", "review_id"),
        Index("ix_food_reports_comment_id", "comment_id"),
        Index("ix_food_reports_message_id", "message_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), nullable=False)
    review_id: Mapped[Optional[str]] = mapped_column(ForeignKey("food_reviews.id"))
    comment_id: Mapped[Optional[str]] = mapped_column(ForeignKey("food_comments.id"))
    message_id: Mapped[Optional[str]] = mapped_column(ForeignKey("food_chat_messages.id"))
    reason: Mapped[ReportReason] = mapped_column(_enum(ReportReason), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[ReportStatus] = mapped_column(
        _enum(ReportStatus), nullable=False, default=ReportStatus.open, server_default="open"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class FoodChatProfile(Base):
    """A participant's public Food Chat pseudonym (e.g. "Hungry Otter 4821"); never their email or ID."""

    __tablename__ = "food_chat_profiles"
    __table_args__ = (UniqueConstraint("display_name", name="uq_food_chat_profiles_display_name"),)

    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class ModerationAction(str, enum.Enum):
    hide = "hide"
    restore = "restore"
    remove = "remove"
    resolve_report = "resolve_report"
    dismiss_report = "dismiss_report"


class ModerationTarget(str, enum.Enum):
    review = "review"
    comment = "comment"
    report = "report"
    message = "message"


class FoodModerationAction(Base):
    """Audit log of moderator actions. Targets are plain IDs (no foreign keys) so the log outlives
    content that is later deleted; it stores no copy of the content itself."""

    __tablename__ = "food_moderation_actions"
    __table_args__ = (
        CheckConstraint(_in("action", ModerationAction), name="ck_food_moderation_actions_action_valid"),
        CheckConstraint(_in("target_type", ModerationTarget), name="ck_food_moderation_actions_target_valid"),
        CheckConstraint("note IS NULL OR length(note) <= 1000", name="ck_food_moderation_actions_note_length"),
        Index("ix_food_moderation_actions_created_at", "created_at"),
        Index("ix_food_moderation_actions_target", "target_type", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    moderator_participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), nullable=False)
    action: Mapped[ModerationAction] = mapped_column(_enum(ModerationAction), nullable=False)
    target_type: Mapped[ModerationTarget] = mapped_column(_enum(ModerationTarget), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class FoodFavoriteVenue(Base):
    """A venue a participant saved. Private to them; never shown to anyone else."""

    __tablename__ = "food_favorite_venues"

    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), primary_key=True)
    venue_id: Mapped[str] = mapped_column(ForeignKey("food_venues.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class FoodFavoriteDish(Base):
    """A verified menu item a participant saved. Private to them; never shown to anyone else."""

    __tablename__ = "food_favorite_dishes"
    __table_args__ = (Index("ix_food_favorite_dishes_menu_item_id", "menu_item_id"),)

    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), primary_key=True)
    menu_item_id: Mapped[str] = mapped_column(ForeignKey("food_menu_items.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class FoodVenueRating(Base):
    """A student's current star rating of a venue: one per participant per venue, changeable any
    time. Independent of chat messages and of the older written reviews."""

    __tablename__ = "food_venue_ratings"
    __table_args__ = (
        UniqueConstraint("participant_id", "venue_id", name="uq_food_venue_ratings_participant_venue"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="ck_food_venue_ratings_rating_range"),
        Index("ix_food_venue_ratings_venue_id", "venue_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), nullable=False)
    venue_id: Mapped[str] = mapped_column(ForeignKey("food_venues.id"), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class FoodChatMessage(Base):
    """One message in a venue's flat, chronological group chat. Free text: it never references a
    station, menu item or review."""

    __tablename__ = "food_chat_messages"
    __table_args__ = (
        CheckConstraint(_in("moderation_state", ModerationState), name="ck_food_chat_messages_moderation_state_valid"),
        CheckConstraint("length(body) > 0 AND length(body) <= 1000", name="ck_food_chat_messages_body_length"),
        Index("ix_food_chat_messages_venue_created", "venue_id", "created_at"),
        Index("ix_food_chat_messages_participant_id", "participant_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    venue_id: Mapped[str] = mapped_column(ForeignKey("food_venues.id"), nullable=False)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    moderation_state: Mapped[ModerationState] = mapped_column(
        _enum(ModerationState), nullable=False, default=ModerationState.visible, server_default="visible"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


# Every participant-owned Food table, for export, deletion and test-safety checks.
FOOD_USER_CONTENT_MODELS = (
    FoodReview, FoodComment, FoodCommentVote, FoodReport, FoodChatProfile, FoodFavoriteVenue, FoodFavoriteDish,
    FoodVenueRating, FoodChatMessage,
)
