"""Record initial invitation delivery before making an external SMTP request."""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("alpendata_invitations", sa.Column("delivery_request_id", sa.String(36), nullable=True))
    op.add_column("alpendata_invitations", sa.Column("delivery_language", sa.String(2), nullable=True))
    op.add_column("alpendata_invitations", sa.Column("delivery_started_at", sa.Integer(), nullable=True))
    op.add_column(
        "alpendata_invitations",
        sa.Column(
            "delivery_status",
            sa.String(16),
            sa.CheckConstraint(
                "delivery_status IN ('manual', 'sending', 'submitted', 'unknown')",
                name="ck_invitation_delivery",
            ),
            nullable=False,
            server_default="manual",
        ),
    )
    op.create_index(
        "uq_invitation_delivery_request",
        "alpendata_invitations",
        ["organization_id", "delivery_request_id"],
        unique=True,
    )


def downgrade():
    op.drop_index("uq_invitation_delivery_request", table_name="alpendata_invitations")
    for name in ("delivery_status", "delivery_started_at", "delivery_language", "delivery_request_id"):
        op.drop_column("alpendata_invitations", name)
