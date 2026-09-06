"""Independent AlpenData identities and durable sign-in admission limits."""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alpendata_password_accounts",
        sa.Column("user_id", sa.String(36), sa.ForeignKey("alpendata_users.id"), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(512)),
        sa.Column("activation_hash", sa.String(64), unique=True),
        sa.Column("activation_expires_at", sa.Integer()),
    )
    op.create_table(
        "alpendata_signin_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("reset_at", sa.Integer(), nullable=False),
    )
    op.create_index("ix_alpendata_signin_limits_reset_at", "alpendata_signin_limits", ["reset_at"])


def downgrade():
    op.drop_table("alpendata_signin_limits")
    op.drop_table("alpendata_password_accounts")
