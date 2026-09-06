"""Persist billing reconciliation deadlines and sanitized failure state."""

import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "alpendata_billing_accounts",
        sa.Column("next_sync_at", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("alpendata_billing_accounts", sa.Column("sync_error", sa.String(32), nullable=True))
    op.create_index(
        "ix_alpendata_billing_accounts_next_sync_at", "alpendata_billing_accounts", ["next_sync_at"]
    )


def downgrade():
    op.drop_index("ix_alpendata_billing_accounts_next_sync_at", table_name="alpendata_billing_accounts")
    op.drop_column("alpendata_billing_accounts", "sync_error")
    op.drop_column("alpendata_billing_accounts", "next_sync_at")
