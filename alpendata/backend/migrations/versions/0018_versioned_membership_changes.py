"""Version membership changes reviewed by an administrator.

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "alpendata_memberships", sa.Column("version", sa.Integer(), server_default="1", nullable=False)
    )


def downgrade():
    op.drop_column("alpendata_memberships", "version")
