"""Personal Infomaniak credentials and frozen source provider per conversation."""

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "alpendata_conversations",
        sa.Column("integration_provider", sa.String(24), nullable=False, server_default="microsoft"),
    )
    op.create_table(
        "alpendata_infomaniak_connections",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("encrypted_credentials", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id", "owner_id"],
            ["alpendata_memberships.organization_id", "alpendata_memberships.user_id"],
        ),
        sa.UniqueConstraint("organization_id", "owner_id"),
    )
    for column in ("organization_id", "owner_id"):
        op.create_index(
            f"ix_alpendata_infomaniak_connections_{column}", "alpendata_infomaniak_connections", [column]
        )


def downgrade():
    op.drop_table("alpendata_infomaniak_connections")
    op.drop_column("alpendata_conversations", "integration_provider")
