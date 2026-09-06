"""Durable Stripe customer binding and Checkout idempotency."""

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alpendata_billing_accounts",
        sa.Column(
            "organization_id", sa.String(36), sa.ForeignKey("alpendata_organizations.id"), primary_key=True
        ),
        sa.Column("customer_key", sa.String(36), nullable=False, unique=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.String(255), unique=True),
        sa.Column("subscription_id", sa.String(255), unique=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("access_until", sa.Integer(), nullable=False),
        sa.Column("cancel_at", sa.Integer()),
        sa.Column("synced_at", sa.Integer()),
        sa.Column("livemode", sa.Boolean(), nullable=False),
        sa.CheckConstraint("quantity >= 0", name="ck_billing_quantity"),
    )
    op.create_table(
        "alpendata_billing_checkouts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("alpendata_billing_accounts.organization_id"),
            nullable=False,
        ),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("price_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(255), unique=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.UniqueConstraint("organization_id", "request_id"),
    )


def downgrade():
    op.drop_table("alpendata_billing_checkouts")
    op.drop_table("alpendata_billing_accounts")
