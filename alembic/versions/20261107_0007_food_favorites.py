"""Add private favourite venues and favourite dishes.

Additive only: two new tables, no change to existing tables or data.
"""

from alembic import op
import sqlalchemy as sa

revision = "20261107_0007"
down_revision = "20261107_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "food_favorite_venues",
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("venue_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("participant_id", "venue_id"),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.ForeignKeyConstraint(["venue_id"], ["food_venues.id"]),
    )
    op.create_table(
        "food_favorite_dishes",
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("menu_item_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("participant_id", "menu_item_id"),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.ForeignKeyConstraint(["menu_item_id"], ["food_menu_items.id"]),
    )
    op.create_index("ix_food_favorite_dishes_menu_item_id", "food_favorite_dishes", ["menu_item_id"])


def downgrade() -> None:
    op.drop_table("food_favorite_dishes")
    op.drop_table("food_favorite_venues")
