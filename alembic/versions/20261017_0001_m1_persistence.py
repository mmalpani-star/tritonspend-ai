"""Create the minimum M1 persistence schema."""

from alembic import op
import sqlalchemy as sa

revision = "20261017_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "participants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(length=64), server_default="America/Los_Angeles", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "invite_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("participant_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_invite_tokens_token_hash"),
    )
    op.create_table(
        "consents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("consent_version", sa.String(length=100), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("terms_version_hash", sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "balance_checkins",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("dining_dollars_cents", sa.Integer(), nullable=False),
        sa.Column("triton_cash_cents", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), server_default="manual", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("dining_dollars_cents >= 0", name="ck_balance_dining_nonnegative"),
        sa.CheckConstraint("triton_cash_cents >= 0", name="ck_balance_cash_nonnegative"),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("account", sa.String(length=32), nullable=False),
        sa.Column("entry_type", sa.String(length=32), nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("merchant_or_note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("amount_cents >= 0", name="ck_ledger_amount_nonnegative"),
        sa.CheckConstraint(
            "account IN ('dining_dollars', 'triton_cash')",
            name="ck_ledger_account_valid",
        ),
        sa.CheckConstraint(
            "entry_type IN ('spending', 'deposit', 'refund')",
            name="ck_ledger_entry_type_valid",
        ),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "zero_spending_confirmations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "participant_id",
            "day",
            name="uq_zero_spending_participant_day",
        ),
    )
    op.create_table(
        "forecast_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("participant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("engine_version", sa.String(length=100), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for table, name, column in (
        ("invite_tokens", "ix_invite_tokens_expires_at", "expires_at"),
        ("invite_tokens", "ix_invite_tokens_participant_id", "participant_id"),
        ("consents", "ix_consents_participant_id", "participant_id"),
        ("balance_checkins", "ix_balance_checkins_participant_id", "participant_id"),
        ("balance_checkins", "ix_balance_checkins_effective_date", "effective_date"),
        ("ledger_entries", "ix_ledger_entries_participant_id", "participant_id"),
        ("ledger_entries", "ix_ledger_entries_occurred_on", "occurred_on"),
        ("zero_spending_confirmations", "ix_zero_spending_confirmations_day", "day"),
        ("forecast_snapshots", "ix_forecast_snapshots_participant_id", "participant_id"),
        ("forecast_snapshots", "ix_forecast_snapshots_created_at", "created_at"),
        ("forecast_snapshots", "ix_forecast_snapshots_start_date", "start_date"),
        ("forecast_snapshots", "ix_forecast_snapshots_end_date", "end_date"),
    ):
        op.create_index(name, table, [column])


def downgrade() -> None:
    for table, name in (
        ("forecast_snapshots", "ix_forecast_snapshots_end_date"),
        ("forecast_snapshots", "ix_forecast_snapshots_start_date"),
        ("forecast_snapshots", "ix_forecast_snapshots_created_at"),
        ("forecast_snapshots", "ix_forecast_snapshots_participant_id"),
        ("zero_spending_confirmations", "ix_zero_spending_confirmations_day"),
        ("ledger_entries", "ix_ledger_entries_occurred_on"),
        ("ledger_entries", "ix_ledger_entries_participant_id"),
        ("balance_checkins", "ix_balance_checkins_effective_date"),
        ("balance_checkins", "ix_balance_checkins_participant_id"),
        ("consents", "ix_consents_participant_id"),
        ("invite_tokens", "ix_invite_tokens_participant_id"),
        ("invite_tokens", "ix_invite_tokens_expires_at"),
    ):
        op.drop_index(name, table_name=table)
    for table in (
        "forecast_snapshots",
        "zero_spending_confirmations",
        "ledger_entries",
        "balance_checkins",
        "consents",
        "invite_tokens",
        "participants",
    ):
        op.drop_table(table)
