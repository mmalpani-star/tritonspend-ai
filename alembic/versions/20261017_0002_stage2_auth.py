"""Add append-only consent events and participant sessions."""

from alembic import op
import sqlalchemy as sa

revision = "20261017_0002"
down_revision = "20261017_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consent_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("consent_version", sa.String(length=100), nullable=False),
        sa.Column("document_url", sa.String(length=1000), nullable=False),
        sa.Column("document_version_hash", sa.String(length=128), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('accepted', 'withdrawn')",
            name="ck_consent_events_event_type_valid",
        ),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_consent_events_participant_id", "consent_events", ["participant_id"])
    op.create_index("ix_consent_events_occurred_at", "consent_events", ["occurred_at"])

    op.create_table(
        "participant_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_token_hash", name="uq_participant_sessions_token_hash"),
    )
    op.create_index(
        "ix_participant_sessions_participant_id",
        "participant_sessions",
        ["participant_id"],
    )
    op.create_index(
        "ix_participant_sessions_expires_at",
        "participant_sessions",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_participant_sessions_expires_at", table_name="participant_sessions")
    op.drop_index("ix_participant_sessions_participant_id", table_name="participant_sessions")
    op.drop_table("participant_sessions")
    op.drop_index("ix_consent_events_occurred_at", table_name="consent_events")
    op.drop_index("ix_consent_events_participant_id", table_name="consent_events")
    op.drop_table("consent_events")
