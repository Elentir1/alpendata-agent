"""Private conversation branches and favorites; existing histories remain intact."""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("alpendata_conversations") as batch:
        batch.add_column(sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("parent_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("branch_sequence", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("alpendata_conversations") as batch:
        batch.drop_column("branch_sequence")
        batch.drop_column("parent_id")
        batch.drop_column("pinned")
