"""Durable calendar proposals and attempts; uncertain writes are never replayed."""

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alpendata_calendar_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("turn_id", sa.String(36), nullable=False),
        sa.Column("initial_hash", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("message", sa.JSON(), nullable=False),
        sa.Column("baseline", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["turn_id", "organization_id", "owner_id"],
            [
                "alpendata_chat_turns.id",
                "alpendata_chat_turns.organization_id",
                "alpendata_chat_turns.owner_id",
            ],
        ),
        sa.UniqueConstraint("turn_id", "initial_hash"),
        sa.CheckConstraint(
            "status IN ('draft', 'dispatching', 'completed', 'failed', 'unknown')",
            name="ck_calendar_action_status",
        ),
    )
    for name in ("organization_id", "owner_id", "turn_id"):
        op.create_index("ix_alpendata_calendar_actions_" + name, "alpendata_calendar_actions", [name])


def downgrade():
    op.drop_table("alpendata_calendar_actions")
