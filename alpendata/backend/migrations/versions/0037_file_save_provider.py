"""Keep the storage provider attached to each durable save receipt."""

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "alpendata_sharepoint_saves",
        sa.Column("provider", sa.String(24), nullable=False, server_default="microsoft"),
    )


def downgrade():
    op.drop_column("alpendata_sharepoint_saves", "provider")
