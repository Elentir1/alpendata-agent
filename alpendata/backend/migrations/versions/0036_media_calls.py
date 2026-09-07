"""Persistent specialist results, without retaining raw dictation audio."""

import sqlalchemy as sa
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alpendata_media_calls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("turn_id", sa.String(36), nullable=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id", "organization_id", "owner_id"],
            [
                "alpendata_conversations.id",
                "alpendata_conversations.organization_id",
                "alpendata_conversations.owner_id",
            ],
        ),
    )
    for name in ("organization_id", "owner_id", "conversation_id"):
        op.create_index("ix_alpendata_media_calls_" + name, "alpendata_media_calls", [name])


def downgrade():
    op.drop_table("alpendata_media_calls")
