"""Personal notifications committed with scheduled outcomes.

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alpendata_personal_notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("source_key", sa.String(100), nullable=False),
        sa.Column("schedule_id", sa.String(36), nullable=False),
        sa.Column("turn_id", sa.String(36), nullable=True),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id", "owner_id"],
            ["alpendata_memberships.organization_id", "alpendata_memberships.user_id"],
        ),
        sa.ForeignKeyConstraint(
            ["turn_id", "organization_id", "owner_id"],
            [
                "alpendata_chat_turns.id",
                "alpendata_chat_turns.organization_id",
                "alpendata_chat_turns.owner_id",
            ],
        ),
        sa.ForeignKeyConstraint(
            ["schedule_id", "organization_id", "owner_id"],
            [
                "alpendata_routine_schedules.id",
                "alpendata_routine_schedules.organization_id",
                "alpendata_routine_schedules.owner_id",
            ],
        ),
        sa.UniqueConstraint("organization_id", "owner_id", "source_key"),
        sa.CheckConstraint(
            "status IN ('completed', 'failed', 'interrupted', 'missed', 'blocked')",
            name="ck_personal_notification_status",
        ),
    )
    op.create_index(
        "ix_alpendata_personal_notifications_organization_id",
        "alpendata_personal_notifications",
        ["organization_id"],
    )
    op.create_index(
        "ix_alpendata_personal_notifications_owner_id", "alpendata_personal_notifications", ["owner_id"]
    )
    op.create_index(
        "ix_personal_notifications_owner_created",
        "alpendata_personal_notifications",
        ["organization_id", "owner_id", "created_at", "id"],
    )


def downgrade():
    op.drop_table("alpendata_personal_notifications")
