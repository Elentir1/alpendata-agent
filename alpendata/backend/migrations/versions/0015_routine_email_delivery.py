"""Fixed email envelope reviewed for a routine.

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("alpendata_conversations", sa.Column("email_delivery", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("alpendata_conversations", "email_delivery")
