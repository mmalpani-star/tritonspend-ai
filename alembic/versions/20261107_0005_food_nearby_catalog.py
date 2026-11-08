"""Add the Food Nearby catalog (venues, stations, menu items, appearances) and Food Chat tables.

Additive only: no existing table is touched, and no catalog or user data is inserted here.
Seed the catalog separately with ``backend/scripts/seed_food_catalog.py``.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261107_0005"
down_revision = "20261029_0004"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "food_venues",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("operator", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("campus_area", sa.String(length=200), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("on_campus", sa.Boolean(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("coordinates_source", sa.JSON(), nullable=True),
        sa.Column("hours", sa.JSON(), nullable=True),
        sa.Column("menu_url", sa.String(length=1000), nullable=True),
        sa.Column("website_url", sa.String(length=1000), nullable=True),
        sa.Column("dining_dollars_acceptance", sa.String(length=32), nullable=False),
        sa.Column("dining_dollars_reason", sa.String(length=300), nullable=False),
        sa.Column("dining_dollars_source", sa.String(length=64), nullable=True),
        sa.Column("triton_cash_acceptance", sa.String(length=32), nullable=False),
        sa.Column("triton_cash_reason", sa.String(length=300), nullable=False),
        sa.Column("triton_cash_source", sa.String(length=64), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("notes", sa.JSON(), nullable=False),
        sa.Column("catalog_version", sa.String(length=64), nullable=False),
        sa.Column("verified_on", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("operator IN ('hdh', 'triton_cash_partner')", name="ck_food_venues_operator_valid"),
        sa.CheckConstraint("kind IN ('restaurant', 'market', 'merchant')", name="ck_food_venues_kind_valid"),
        sa.CheckConstraint(
            "dining_dollars_acceptance IN ('accepted', 'not_accepted', 'not_verified')",
            name="ck_food_venues_dd_acceptance_valid",
        ),
        sa.CheckConstraint(
            "triton_cash_acceptance IN ('accepted', 'not_accepted', 'not_verified')",
            name="ck_food_venues_tc_acceptance_valid",
        ),
        sa.CheckConstraint("(latitude IS NULL) = (longitude IS NULL)", name="ck_food_venues_coordinates_paired"),
        sa.CheckConstraint(
            "latitude IS NULL OR (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)",
            name="ck_food_venues_coordinates_range",
        ),
    )
    op.create_index("ix_food_venues_operator", "food_venues", ["operator"])
    op.create_index("ix_food_venues_is_active", "food_venues", ["is_active"])

    op.create_table(
        "food_stations",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("venue_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("menu_url", sa.String(length=1000), nullable=True),
        sa.Column("hours", sa.JSON(), nullable=True),
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("catalog_version", sa.String(length=64), nullable=False),
        sa.Column("verified_on", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["venue_id"], ["food_venues.id"]),
        sa.UniqueConstraint("venue_id", "name", name="uq_food_stations_venue_name"),
        sa.UniqueConstraint("id", "venue_id", name="uq_food_stations_id_venue"),
    )
    op.create_index("ix_food_stations_venue_id", "food_stations", ["venue_id"])

    op.create_table(
        "food_menu_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("station_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("name_key", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("dietary_labels", sa.JSON(), nullable=True),
        sa.Column("allergens", sa.JSON(), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["station_id"], ["food_stations.id"]),
        sa.UniqueConstraint("station_id", "name_key", name="uq_food_menu_items_station_name_key"),
        sa.UniqueConstraint("id", "station_id", name="uq_food_menu_items_id_station"),
        sa.CheckConstraint("length(name_key) > 0", name="ck_food_menu_items_name_key_nonempty"),
    )
    op.create_index("ix_food_menu_items_station_id", "food_menu_items", ["station_id"])

    op.create_table(
        "food_menu_appearances",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("menu_item_id", sa.String(length=36), nullable=False),
        sa.Column("menu_date", sa.Date(), nullable=False),
        sa.Column("meal_period", sa.String(length=32), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("availability", sa.String(length=32), server_default="unknown", nullable=False),
        sa.Column("source_url", sa.String(length=1000), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["menu_item_id"], ["food_menu_items.id"]),
        sa.UniqueConstraint("menu_item_id", "menu_date", "meal_period", name="uq_food_menu_appearances_item_date_period"),
        sa.CheckConstraint("price_cents IS NULL OR price_cents >= 0", name="ck_food_menu_appearances_price_nonnegative"),
        sa.CheckConstraint("currency = 'USD'", name="ck_food_menu_appearances_currency_usd"),
        sa.CheckConstraint(
            "availability IN ('unknown', 'available', 'sold_out', 'unavailable')",
            name="ck_food_menu_appearances_availability_valid",
        ),
        sa.CheckConstraint("length(meal_period) > 0", name="ck_food_menu_appearances_meal_period_nonempty"),
    )
    op.create_index("ix_food_menu_appearances_menu_item_id", "food_menu_appearances", ["menu_item_id"])
    op.create_index("ix_food_menu_appearances_menu_date", "food_menu_appearances", ["menu_date"])

    op.create_table(
        "food_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("venue_id", sa.String(length=64), nullable=False),
        sa.Column("station_id", sa.String(length=128), nullable=True),
        sa.Column("menu_item_id", sa.String(length=36), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("moderation_state", sa.String(length=32), server_default="visible", nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.ForeignKeyConstraint(["venue_id"], ["food_venues.id"]),
        sa.ForeignKeyConstraint(
            ["station_id", "venue_id"], ["food_stations.id", "food_stations.venue_id"],
            name="fk_food_reviews_station_in_venue",
        ),
        sa.ForeignKeyConstraint(
            ["menu_item_id", "station_id"], ["food_menu_items.id", "food_menu_items.station_id"],
            name="fk_food_reviews_item_in_station",
        ),
        sa.CheckConstraint("target_type IN ('venue', 'menu_item')", name="ck_food_reviews_target_type_valid"),
        sa.CheckConstraint(
            "(target_type = 'venue' AND station_id IS NULL AND menu_item_id IS NULL)"
            " OR (target_type = 'menu_item' AND station_id IS NOT NULL AND menu_item_id IS NOT NULL)",
            name="ck_food_reviews_target_shape",
        ),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_food_reviews_rating_range"),
        sa.CheckConstraint("length(body) <= 5000", name="ck_food_reviews_body_length"),
        sa.CheckConstraint(
            "moderation_state IN ('visible', 'hidden', 'removed')", name="ck_food_reviews_moderation_valid"
        ),
    )
    op.create_index(
        "uq_food_reviews_participant_venue", "food_reviews", ["participant_id", "venue_id"], unique=True,
        sqlite_where=sa.text("target_type = 'venue'"), postgresql_where=sa.text("target_type = 'venue'"),
    )
    op.create_index(
        "uq_food_reviews_participant_item", "food_reviews", ["participant_id", "menu_item_id"], unique=True,
        sqlite_where=sa.text("target_type = 'menu_item'"), postgresql_where=sa.text("target_type = 'menu_item'"),
    )
    op.create_index("ix_food_reviews_venue_id", "food_reviews", ["venue_id"])
    op.create_index("ix_food_reviews_menu_item_id", "food_reviews", ["menu_item_id"])

    op.create_table(
        "food_comments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("review_id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("moderation_state", sa.String(length=32), server_default="visible", nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["review_id"], ["food_reviews.id"]),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.UniqueConstraint("id", "review_id", name="uq_food_comments_id_review"),
        sa.ForeignKeyConstraint(
            ["parent_id", "review_id"], ["food_comments.id", "food_comments.review_id"],
            name="fk_food_comments_parent_same_review",
        ),
        sa.CheckConstraint("parent_id IS NULL OR parent_id <> id", name="ck_food_comments_not_own_parent"),
        sa.CheckConstraint("length(body) BETWEEN 1 AND 5000", name="ck_food_comments_body_length"),
        sa.CheckConstraint(
            "moderation_state IN ('visible', 'hidden', 'removed')", name="ck_food_comments_moderation_valid"
        ),
    )
    op.create_index("ix_food_comments_review_id", "food_comments", ["review_id"])
    op.create_index("ix_food_comments_parent_id", "food_comments", ["parent_id"])

    op.create_table(
        "food_comment_votes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("comment_id", sa.String(length=36), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("value", sa.Integer(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["comment_id"], ["food_comments.id"]),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.UniqueConstraint("comment_id", "participant_id", name="uq_food_comment_votes_comment_participant"),
        sa.CheckConstraint("value IN (-1, 1)", name="ck_food_comment_votes_value"),
    )
    op.create_index("ix_food_comment_votes_participant_id", "food_comment_votes", ["participant_id"])

    op.create_table(
        "food_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("review_id", sa.String(length=36), nullable=True),
        sa.Column("comment_id", sa.String(length=36), nullable=True),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="open", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.ForeignKeyConstraint(["review_id"], ["food_reviews.id"]),
        sa.ForeignKeyConstraint(["comment_id"], ["food_comments.id"]),
        sa.UniqueConstraint("participant_id", "review_id", name="uq_food_reports_participant_review"),
        sa.UniqueConstraint("participant_id", "comment_id", name="uq_food_reports_participant_comment"),
        sa.CheckConstraint(
            "(review_id IS NOT NULL AND comment_id IS NULL) OR (review_id IS NULL AND comment_id IS NOT NULL)",
            name="ck_food_reports_exactly_one_target",
        ),
        sa.CheckConstraint(
            "reason IN ('spam', 'harassment', 'hate', 'sexual_content', 'misinformation', 'off_topic', 'other')",
            name="ck_food_reports_reason_valid",
        ),
        sa.CheckConstraint("status IN ('open', 'actioned', 'dismissed')", name="ck_food_reports_status_valid"),
        sa.CheckConstraint("details IS NULL OR length(details) <= 2000", name="ck_food_reports_details_length"),
    )
    op.create_index("ix_food_reports_status", "food_reports", ["status"])
    op.create_index("ix_food_reports_review_id", "food_reports", ["review_id"])
    op.create_index("ix_food_reports_comment_id", "food_reports", ["comment_id"])


def downgrade() -> None:
    for table in (
        "food_reports",
        "food_comment_votes",
        "food_comments",
        "food_reviews",
        "food_menu_appearances",
        "food_menu_items",
        "food_stations",
        "food_venues",
    ):
        op.drop_table(table)
