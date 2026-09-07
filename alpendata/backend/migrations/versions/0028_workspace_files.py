"""Private file metadata, immutable versions and bounded editor sessions."""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def owner_columns():
    return [
        sa.Column("organization_id", sa.String(36), nullable=False),
        sa.Column("owner_id", sa.String(36), nullable=False),
    ]


def file_key():
    return sa.ForeignKeyConstraint(
        ["file_id", "organization_id", "owner_id"],
        [
            "alpendata_workspace_files.id",
            "alpendata_workspace_files.organization_id",
            "alpendata_workspace_files.owner_id",
        ],
    )


def upgrade():
    op.create_table(
        "alpendata_workspace_files",
        sa.Column("id", sa.String(36), primary_key=True),
        *owner_columns(),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("filename", sa.String(180), nullable=False),
        sa.Column("media_type", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("id", "organization_id", "owner_id"),
        sa.ForeignKeyConstraint(
            ["conversation_id", "organization_id", "owner_id"],
            [
                "alpendata_conversations.id",
                "alpendata_conversations.organization_id",
                "alpendata_conversations.owner_id",
            ],
        ),
    )
    op.create_table(
        "alpendata_file_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        *owner_columns(),
        sa.Column("file_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(240), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.UniqueConstraint("file_id", "version"),
        file_key(),
    )
    op.create_table(
        "alpendata_editor_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        *owner_columns(),
        sa.Column("file_id", sa.String(36), nullable=False),
        sa.Column("base_version", sa.Integer(), nullable=False),
        sa.Column("saved_version", sa.Integer(), nullable=True),
        sa.Column("conflict_file_id", sa.String(36), nullable=True),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        file_key(),
    )
    for table in ("alpendata_workspace_files", "alpendata_file_versions", "alpendata_editor_sessions"):
        for column in ("organization_id", "owner_id"):
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_index(
        "ix_alpendata_workspace_files_conversation_id", "alpendata_workspace_files", ["conversation_id"]
    )
    op.create_index("ix_alpendata_file_versions_file_id", "alpendata_file_versions", ["file_id"])


def downgrade():
    op.drop_table("alpendata_editor_sessions")
    op.drop_table("alpendata_file_versions")
    op.drop_table("alpendata_workspace_files")
