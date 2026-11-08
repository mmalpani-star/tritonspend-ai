"""Venue star ratings and per-venue group chat; reports and the moderation log learn about messages.

Non-destructive:
- New tables `food_venue_ratings` (one rating per participant per venue) and `food_chat_messages`.
- `food_reports` gains a nullable `message_id`; its exactly-one-target check now allows a message.
- `food_moderation_actions.target_type` may now be 'message'.
- Existing *visible venue-level* review ratings are copied into `food_venue_ratings` (dish reviews
  are not venue ratings; hidden/removed reviews are not counted). Reviews, comments, votes, reports
  and the moderation log are kept unchanged; no chat messages are created from old content.

SQLite cannot alter a CHECK constraint, so on SQLite the two altered tables are rebuilt by copying
every row into a new table with the new definition (same columns, values and indexes).
"""

from alembic import op
import sqlalchemy as sa

revision = "20261108_0008"
down_revision = "20261107_0007"
branch_labels = None
depends_on = None

REVIEW_COMMENT_ONLY = "(review_id IS NOT NULL AND comment_id IS NULL) OR (review_id IS NULL AND comment_id IS NOT NULL)"
EXACTLY_ONE = (
    "(review_id IS NOT NULL AND comment_id IS NULL AND message_id IS NULL)"
    " OR (review_id IS NULL AND comment_id IS NOT NULL AND message_id IS NULL)"
    " OR (review_id IS NULL AND comment_id IS NULL AND message_id IS NOT NULL)"
)
TARGETS_OLD = "target_type IN ('review', 'comment', 'report')"
TARGETS_NEW = "target_type IN ('review', 'comment', 'report', 'message')"
REASONS = "reason IN ('spam', 'harassment', 'hate', 'sexual_content', 'misinformation', 'off_topic', 'other')"
ACTIONS = "action IN ('hide', 'restore', 'remove', 'resolve_report', 'dismiss_report')"


def _reports_table(with_message: bool) -> list:
    columns = [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("review_id", sa.String(length=36), nullable=True),
        sa.Column("comment_id", sa.String(length=36), nullable=True),
    ]
    if with_message:
        columns.append(sa.Column("message_id", sa.String(length=36), nullable=True))
    columns += [
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
        sa.CheckConstraint(EXACTLY_ONE if with_message else REVIEW_COMMENT_ONLY, name="ck_food_reports_exactly_one_target"),
        sa.CheckConstraint(REASONS, name="ck_food_reports_reason_valid"),
        sa.CheckConstraint("status IN ('open', 'actioned', 'dismissed')", name="ck_food_reports_status_valid"),
        sa.CheckConstraint("details IS NULL OR length(details) <= 2000", name="ck_food_reports_details_length"),
    ]
    if with_message:
        columns.append(sa.ForeignKeyConstraint(["message_id"], ["food_chat_messages.id"]))
        columns.append(sa.UniqueConstraint("participant_id", "message_id", name="uq_food_reports_participant_message"))
    return columns


def _actions_table(targets: str) -> list:
    return [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("moderator_participant_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["moderator_participant_id"], ["participants.id"]),
        sa.CheckConstraint(ACTIONS, name="ck_food_moderation_actions_action_valid"),
        sa.CheckConstraint(targets, name="ck_food_moderation_actions_target_valid"),
        sa.CheckConstraint("note IS NULL OR length(note) <= 1000", name="ck_food_moderation_actions_note_length"),
    ]


def _report_indexes(with_message: bool) -> None:
    op.create_index("ix_food_reports_status", "food_reports", ["status"])
    op.create_index("ix_food_reports_review_id", "food_reports", ["review_id"])
    op.create_index("ix_food_reports_comment_id", "food_reports", ["comment_id"])
    if with_message:
        op.create_index("ix_food_reports_message_id", "food_reports", ["message_id"])


def _action_indexes() -> None:
    op.create_index("ix_food_moderation_actions_created_at", "food_moderation_actions", ["created_at"])
    op.create_index("ix_food_moderation_actions_target", "food_moderation_actions", ["target_type", "target_id"])


def _rebuild_sqlite(old: str, definition: list, columns: list, make_indexes) -> None:
    """Copy every row of `old` into a new table with `definition`, then swap it in under the old name."""
    temporary = f"{old}_rebuild"
    op.create_table(temporary, *definition)
    names = ", ".join(columns)
    op.execute(f"INSERT INTO {temporary} ({names}) SELECT {names} FROM {old}")
    op.drop_table(old)
    op.rename_table(temporary, old)
    make_indexes()


REPORT_COLUMNS = ["id", "participant_id", "review_id", "comment_id", "reason", "details", "status", "created_at", "resolved_at"]
ACTION_COLUMNS = ["id", "moderator_participant_id", "action", "target_type", "target_id", "note", "created_at"]


def upgrade() -> None:
    op.create_table(
        "food_chat_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("venue_id", sa.String(length=64), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("moderation_state", sa.String(length=32), server_default="visible", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["venue_id"], ["food_venues.id"]),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.CheckConstraint("moderation_state IN ('visible', 'hidden', 'removed')", name="ck_food_chat_messages_moderation_state_valid"),
        sa.CheckConstraint("length(body) > 0 AND length(body) <= 1000", name="ck_food_chat_messages_body_length"),
    )
    op.create_index("ix_food_chat_messages_venue_created", "food_chat_messages", ["venue_id", "created_at"])
    op.create_index("ix_food_chat_messages_participant_id", "food_chat_messages", ["participant_id"])

    op.create_table(
        "food_venue_ratings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("venue_id", sa.String(length=64), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.ForeignKeyConstraint(["venue_id"], ["food_venues.id"]),
        sa.UniqueConstraint("participant_id", "venue_id", name="uq_food_venue_ratings_participant_venue"),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_food_venue_ratings_rating_range"),
    )
    op.create_index("ix_food_venue_ratings_venue_id", "food_venue_ratings", ["venue_id"])

    if op.get_bind().dialect.name == "sqlite":
        _rebuild_sqlite("food_reports", _reports_table(True), REPORT_COLUMNS, lambda: _report_indexes(True))
        _rebuild_sqlite("food_moderation_actions", _actions_table(TARGETS_NEW), ACTION_COLUMNS, _action_indexes)
    else:
        op.add_column("food_reports", sa.Column("message_id", sa.String(length=36), nullable=True))
        op.create_foreign_key("fk_food_reports_message_id", "food_reports", "food_chat_messages", ["message_id"], ["id"])
        op.drop_constraint("ck_food_reports_exactly_one_target", "food_reports", type_="check")
        op.create_check_constraint("ck_food_reports_exactly_one_target", "food_reports", EXACTLY_ONE)
        op.create_unique_constraint("uq_food_reports_participant_message", "food_reports", ["participant_id", "message_id"])
        op.create_index("ix_food_reports_message_id", "food_reports", ["message_id"])
        op.drop_constraint("ck_food_moderation_actions_target_valid", "food_moderation_actions", type_="check")
        op.create_check_constraint("ck_food_moderation_actions_target_valid", "food_moderation_actions", TARGETS_NEW)

    # Each participant's current, visible venue-level review rating becomes their venue rating.
    # (At most one per participant per venue, enforced by the reviews' partial unique index.)
    op.execute(
        "INSERT INTO food_venue_ratings (id, participant_id, venue_id, rating, created_at, updated_at) "
        "SELECT id, participant_id, venue_id, rating, created_at, updated_at FROM food_reviews "
        "WHERE target_type = 'venue' AND moderation_state = 'visible'"
    )


def downgrade() -> None:
    # Message reports and message moderation entries cannot exist without messages.
    op.execute("DELETE FROM food_reports WHERE message_id IS NOT NULL")
    op.execute("DELETE FROM food_moderation_actions WHERE target_type = 'message'")
    if op.get_bind().dialect.name == "sqlite":
        _rebuild_sqlite("food_reports", _reports_table(False), REPORT_COLUMNS, lambda: _report_indexes(False))
        _rebuild_sqlite("food_moderation_actions", _actions_table(TARGETS_OLD), ACTION_COLUMNS, _action_indexes)
    else:
        op.drop_index("ix_food_reports_message_id", table_name="food_reports")
        op.drop_constraint("uq_food_reports_participant_message", "food_reports", type_="unique")
        op.drop_constraint("ck_food_reports_exactly_one_target", "food_reports", type_="check")
        op.create_check_constraint("ck_food_reports_exactly_one_target", "food_reports", REVIEW_COMMENT_ONLY)
        op.drop_constraint("fk_food_reports_message_id", "food_reports", type_="foreignkey")
        op.drop_column("food_reports", "message_id")
        op.drop_constraint("ck_food_moderation_actions_target_valid", "food_moderation_actions", type_="check")
        op.create_check_constraint("ck_food_moderation_actions_target_valid", "food_moderation_actions", TARGETS_OLD)
    op.drop_table("food_venue_ratings")
    op.drop_table("food_chat_messages")
