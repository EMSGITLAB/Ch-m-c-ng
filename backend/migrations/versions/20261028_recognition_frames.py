"""Durable frame ordering and binding to the kiosk token generation."""

import sqlalchemy as sa
from alembic import op

revision = "20261028_recognition_frames"
down_revision = "20261028_imported_photos"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("recognition_sessions", sa.Column("device_token_hash", sa.String(128), nullable=True))
    op.add_column(
        "recognition_sessions",
        sa.Column("last_frame_index", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_table(
        "recognition_frames",
        sa.Column("request_id", sa.String(36), primary_key=True),
        sa.Column("position", sa.Integer(), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("employee_id", sa.String(36), nullable=True),
        sa.Column("biometric_revision", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["recognition_sessions.request_id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.CheckConstraint("position BETWEEN 1 AND 12", name="ck_recognition_frame_position"),
        sa.CheckConstraint(
            "accepted = 0 OR (employee_id IS NOT NULL AND biometric_revision IS NOT NULL)",
            name="ck_recognition_frame_identity",
        ),
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM recognition_frames")).scalar_one():
        raise RuntimeError(
            "Cannot downgrade recognition frame history; preserve a compatible database backup"
        )
    op.drop_table("recognition_frames")
    op.drop_column("recognition_sessions", "last_frame_index", mssql_drop_default=True)
    op.drop_column("recognition_sessions", "device_token_hash")
