"""Hide deleted conversations while retaining durable action and usage receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("alpendata_conversations", sa.Column("deleted_at", sa.Integer(), nullable=True))


def downgrade():
    # Removing this marker could make previously deleted content visible again.
    raise RuntimeError(
        "Deleted conversations require forward recovery, not removal of their visibility marker"
    )
