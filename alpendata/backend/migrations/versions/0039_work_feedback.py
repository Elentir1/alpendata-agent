"""First-result timing and explicit user feedback, without external telemetry."""

import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("started_at", "profile_completed_at", "first_useful_at"):
        op.add_column("alpendata_onboardings", sa.Column(name, sa.Integer(), nullable=True))
    op.create_table(
        "alpendata_work_feedback",
        sa.Column("turn_id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["turn_id", "organization_id", "owner_id"],
            [
                "alpendata_chat_turns.id",
                "alpendata_chat_turns.organization_id",
                "alpendata_chat_turns.owner_id",
            ],
        ),
        sa.CheckConstraint(
            "outcome IN ('useful', 'needs_changes', 'not_useful')", name="ck_work_feedback_outcome"
        ),
    )
    for column in ("organization_id", "owner_id"):
        op.create_index(f"ix_alpendata_work_feedback_{column}", "alpendata_work_feedback", [column])


def downgrade():
    op.drop_table("alpendata_work_feedback")
    for name in ("started_at", "profile_completed_at", "first_useful_at"):
        op.drop_column("alpendata_onboardings", name)
