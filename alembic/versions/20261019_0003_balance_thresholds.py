"""Add participant balance thresholds."""

from alembic import op
import sqlalchemy as sa

revision = "20261019_0003"
down_revision = "20261017_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "participant_balance_thresholds",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("dining_dollars_cents", sa.Integer(), nullable=False),
        sa.Column("triton_cash_cents", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "dining_dollars_cents >= 0", name="ck_threshold_dining_nonnegative"
        ),
        sa.CheckConstraint("triton_cash_cents >= 0", name="ck_threshold_cash_nonnegative"),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("participant_id", name="uq_threshold_participant"),
    )
def downgrade() -> None:
    op.drop_table("participant_balance_thresholds")
