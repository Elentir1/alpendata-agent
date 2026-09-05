"""Browser-bound Microsoft sign-in flows.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alpendata_signin_flows",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("encrypted_flow", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_alpendata_signin_flows_expires_at", "alpendata_signin_flows", ["expires_at"])


def downgrade():
    op.drop_index("ix_alpendata_signin_flows_expires_at", table_name="alpendata_signin_flows")
    op.drop_table("alpendata_signin_flows")
