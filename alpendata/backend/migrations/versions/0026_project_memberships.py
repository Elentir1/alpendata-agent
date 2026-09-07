"""Explicit project membership, independently owned conversations and published notes."""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("alpendata_projects") as batch:
        batch.create_unique_constraint("uq_project_organization", ["id", "organization_id"])
    with op.batch_alter_table("alpendata_conversations") as batch:
        batch.drop_constraint("fk_conversation_project_owner", type_="foreignkey")
        batch.create_foreign_key(
            "fk_conversation_project_organization",
            "alpendata_projects",
            ["project_id", "organization_id"],
            ["id", "organization_id"],
        )
    op.create_table(
        "alpendata_project_members",
        sa.Column("project_id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id", "organization_id"], ["alpendata_projects.id", "alpendata_projects.organization_id"]
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["alpendata_memberships.organization_id", "alpendata_memberships.user_id"],
        ),
        sa.CheckConstraint("role IN ('reader', 'contributor')", name="ck_project_member_role"),
    )
    op.create_index(
        "ix_alpendata_project_members_organization_id", "alpendata_project_members", ["organization_id"]
    )
    op.create_table(
        "alpendata_project_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "owner_id"],
            ["alpendata_memberships.organization_id", "alpendata_memberships.user_id"],
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "organization_id"], ["alpendata_projects.id", "alpendata_projects.organization_id"]
        ),
    )
    for column in ("organization_id", "owner_id", "project_id"):
        op.create_index(f"ix_alpendata_project_entries_{column}", "alpendata_project_entries", [column])


def downgrade():
    # Shared projects may contain independently owned conversations. Refuse a
    # lossy downgrade; deploy the compatible previous UI instead.
    raise RuntimeError("project_membership_migration_requires_forward_recovery")
