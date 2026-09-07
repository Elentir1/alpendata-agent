"""Explicit document publications and the individual author of editor sessions."""

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("alpendata_editor_sessions", sa.Column("editor_id", sa.String(36), nullable=True))
    op.create_table(
        "alpendata_project_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("file_id", sa.String(36), nullable=False, unique=True),
        sa.Column("source_file_id", sa.String(36), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id", "organization_id"], ["alpendata_projects.id", "alpendata_projects.organization_id"]
        ),
        sa.ForeignKeyConstraint(
            ["file_id", "organization_id", "owner_id"],
            [
                "alpendata_workspace_files.id",
                "alpendata_workspace_files.organization_id",
                "alpendata_workspace_files.owner_id",
            ],
        ),
    )
    for column in ("organization_id", "owner_id", "project_id"):
        op.create_index("ix_alpendata_project_files_" + column, "alpendata_project_files", [column])


def downgrade():
    op.drop_table("alpendata_project_files")
    op.drop_column("alpendata_editor_sessions", "editor_id")
