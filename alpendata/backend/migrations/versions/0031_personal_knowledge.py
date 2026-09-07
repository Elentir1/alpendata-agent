"""Personal preferences and reusable methods never inherit legacy client notes."""

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("alpendata_conversations", sa.Column("context_project_id", sa.String(36), nullable=True))
    op.execute("UPDATE alpendata_conversations SET context_project_id = project_id")
    op.create_table(
        "alpendata_personal_knowledge",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "owner_id"],
            ["alpendata_memberships.organization_id", "alpendata_memberships.user_id"],
        ),
        sa.CheckConstraint("kind IN ('preference', 'method')", name="ck_knowledge_kind"),
    )
    for column in ("organization_id", "owner_id"):
        op.create_index(f"ix_alpendata_personal_knowledge_{column}", "alpendata_personal_knowledge", [column])


def downgrade():
    op.drop_table("alpendata_personal_knowledge")
    op.drop_column("alpendata_conversations", "context_project_id")
