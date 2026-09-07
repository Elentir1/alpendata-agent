"""Freeze optional operator services with the conversation's tool schema."""

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("alpendata_conversations", sa.Column("service_features", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("alpendata_conversations", "service_features")
