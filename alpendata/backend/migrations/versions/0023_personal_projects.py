"""Personal projects and conversation organization."""

import sqlalchemy as sa
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alpendata_projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "owner_id"],
            ["alpendata_memberships.organization_id", "alpendata_memberships.user_id"],
        ),
        sa.UniqueConstraint("id", "organization_id", "owner_id"),
    )
    op.create_index("ix_alpendata_projects_organization_id", "alpendata_projects", ["organization_id"])
    op.create_index("ix_alpendata_projects_owner_id", "alpendata_projects", ["owner_id"])
    with op.batch_alter_table("alpendata_conversations") as batch:
        batch.add_column(sa.Column("project_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("archived", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch.create_foreign_key(
            "fk_conversation_project_owner",
            "alpendata_projects",
            ["project_id", "organization_id", "owner_id"],
            ["id", "organization_id", "owner_id"],
        )


def downgrade():
    with op.batch_alter_table("alpendata_conversations") as batch:
        batch.drop_constraint("fk_conversation_project_owner", type_="foreignkey")
        batch.drop_column("archived")
        batch.drop_column("project_id")
    op.drop_table("alpendata_projects")
