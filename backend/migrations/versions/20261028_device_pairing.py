"""Expiring, one-use device pairing and server-side token expiry."""
import sqlalchemy as sa
from alembic import op

revision = "20261028_device_pairing"
down_revision = "250101_authentication"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("devices",sa.Column("token_expires_at",sa.DateTime(timezone=True),nullable=True))
    op.create_table("device_pairings",
                    sa.Column("code_hash",sa.String(64),nullable=False),
                    sa.Column("device_id",sa.String(36),nullable=False),
                    sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),
                    sa.ForeignKeyConstraint(["device_id"],["devices.id"]),sa.PrimaryKeyConstraint("code_hash"))
    op.create_index("ix_device_pairings_device_id","device_pairings",["device_id"])
    op.create_index("ix_device_pairings_expires_at","device_pairings",["expires_at"])


def downgrade():
    op.drop_index("ix_device_pairings_expires_at",table_name="device_pairings")
    op.drop_index("ix_device_pairings_device_id",table_name="device_pairings")
    op.drop_table("device_pairings")
    op.drop_column("devices","token_expires_at")
