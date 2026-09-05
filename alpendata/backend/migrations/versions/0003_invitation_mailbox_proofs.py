"""Fresh mailbox proofs bound to a sign-in identity and invitation.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "alpendata_invitation_proofs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("invitation_id", sa.String(36), sa.ForeignKey("alpendata_invitations.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("alpendata_users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.Integer(), nullable=False),
        sa.Column("consumed_at", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_alpendata_invitation_proofs_invitation_id", "alpendata_invitation_proofs", ["invitation_id"]
    )
    op.create_index("ix_alpendata_invitation_proofs_user_id", "alpendata_invitation_proofs", ["user_id"])


def downgrade():
    op.drop_index("ix_alpendata_invitation_proofs_user_id", table_name="alpendata_invitation_proofs")
    op.drop_index("ix_alpendata_invitation_proofs_invitation_id", table_name="alpendata_invitation_proofs")
    op.drop_table("alpendata_invitation_proofs")
