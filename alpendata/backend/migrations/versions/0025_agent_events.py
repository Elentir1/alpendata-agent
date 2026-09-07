"""Persist user-visible execution events without tool inputs or outputs."""

import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alpendata_agent_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("turn_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["turn_id", "organization_id", "owner_id"],
            [
                "alpendata_chat_turns.id",
                "alpendata_chat_turns.organization_id",
                "alpendata_chat_turns.owner_id",
            ],
        ),
    )
    for column in ("organization_id", "owner_id", "conversation_id", "turn_id"):
        op.create_index(f"ix_alpendata_agent_events_{column}", "alpendata_agent_events", [column])


def downgrade():
    op.drop_table("alpendata_agent_events")
