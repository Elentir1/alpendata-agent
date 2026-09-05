"""Personal delegated Microsoft connections and browser-bound consent flows."""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def ownership():
    return sa.ForeignKeyConstraint(
        ["organization_id", "owner_id"],
        ["alpendata_memberships.organization_id", "alpendata_memberships.user_id"],
    )


def upgrade():
    op.create_table(
        "alpendata_microsoft_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("encrypted_cache", sa.Text(), nullable=True),
        sa.Column("connected_at", sa.Integer(), nullable=True),
        ownership(),
        sa.UniqueConstraint("organization_id", "owner_id"),
        sa.CheckConstraint(
            "status IN ('disconnected', 'connected', 'reconnect_required')", name="ck_microsoft_status"
        ),
    )
    op.create_table(
        "alpendata_microsoft_connection_flows",
        sa.Column("state_hash", sa.String(64), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column(
            "connection_id",
            sa.String(36),
            sa.ForeignKey("alpendata_microsoft_connections.id"),
            nullable=False,
        ),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column(
            "session_hash", sa.String(64), sa.ForeignKey("alpendata_auth_sessions.token_hash"), nullable=False
        ),
        sa.Column("browser_hash", sa.String(64), nullable=False),
        sa.Column("encrypted_flow", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        ownership(),
    )
    for table in ("alpendata_microsoft_connections", "alpendata_microsoft_connection_flows"):
        for column in ("organization_id", "owner_id"):
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index(
        "ix_alpendata_microsoft_connection_flows_expires_at",
        "alpendata_microsoft_connection_flows",
        ["expires_at"],
    )


def downgrade():
    op.drop_table("alpendata_microsoft_connection_flows")
    op.drop_table("alpendata_microsoft_connections")
