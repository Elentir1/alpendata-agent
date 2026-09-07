"""Document analysis is durable and each source reference identifies an immutable version."""

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "alpendata_file_versions",
        sa.Column("analysis_status", sa.String(24), nullable=False, server_default="queued"),
    )
    op.add_column(
        "alpendata_file_versions", sa.Column("analysis_text", sa.Text(), nullable=False, server_default="")
    )
    op.add_column("alpendata_file_versions", sa.Column("analysis_pages", sa.JSON(), nullable=True))
    op.add_column("alpendata_file_versions", sa.Column("analysis_lease", sa.String(36), nullable=True))
    op.add_column("alpendata_file_versions", sa.Column("analysis_expires_at", sa.Integer(), nullable=True))
    op.add_column("alpendata_chat_turns", sa.Column("seen_at", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("alpendata_chat_turns", "seen_at")
    for name in (
        "analysis_expires_at",
        "analysis_lease",
        "analysis_pages",
        "analysis_text",
        "analysis_status",
    ):
        op.drop_column("alpendata_file_versions", name)
