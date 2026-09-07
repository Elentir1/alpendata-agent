"""Recover a streamed answer after browser reconnection."""

import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("alpendata_chat_turns", sa.Column("partial_response", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("alpendata_chat_turns", "partial_response")
