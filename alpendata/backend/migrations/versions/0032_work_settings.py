"""Freeze the user's working depth, source selection and autonomy with a conversation."""

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("alpendata_conversations", sa.Column("work_settings", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("alpendata_conversations", "work_settings")
