"""Persist WOPI locks and the exact version held by a conflict-copy editor."""

import sqlalchemy as sa
from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("alpendata_editor_sessions", sa.Column("lock_value", sa.String(1024), nullable=True))
    op.add_column("alpendata_editor_sessions", sa.Column("lock_expires_at", sa.Integer(), nullable=True))
    op.add_column("alpendata_editor_sessions", sa.Column("conflict_version", sa.Integer(), nullable=True))
    # ONLYOFFICE credentials cannot be continued as a WOPI session.
    op.execute("UPDATE alpendata_editor_sessions SET expires_at = 0")


def downgrade():
    op.execute("UPDATE alpendata_editor_sessions SET expires_at = 0")
    for name in ("conflict_version", "lock_expires_at", "lock_value"):
        op.drop_column("alpendata_editor_sessions", name)
