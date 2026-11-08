"""Add Food Chat pseudonymous profiles and the moderation action log.

Additive only: two new tables, no change to existing tables or data.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261107_0006"
down_revision = "20261107_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "food_chat_profiles",
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("participant_id"),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.UniqueConstraint("display_name", name="uq_food_chat_profiles_display_name"),
    )
    op.create_table(
        "food_moderation_actions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("moderator_participant_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["moderator_participant_id"], ["participants.id"]),
        sa.CheckConstraint(
            "action IN ('hide', 'restore', 'remove', 'resolve_report', 'dismiss_report')",
            name="ck_food_moderation_actions_action_valid",
        ),
        sa.CheckConstraint("target_type IN ('review', 'comment', 'report')", name="ck_food_moderation_actions_target_valid"),
        sa.CheckConstraint("note IS NULL OR length(note) <= 1000", name="ck_food_moderation_actions_note_length"),
    )
    op.create_index("ix_food_moderation_actions_created_at", "food_moderation_actions", ["created_at"])
    op.create_index("ix_food_moderation_actions_target", "food_moderation_actions", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_table("food_moderation_actions")
    op.drop_table("food_chat_profiles")
