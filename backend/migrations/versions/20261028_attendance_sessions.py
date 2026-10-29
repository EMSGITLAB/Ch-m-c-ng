"""Server-bound recognition decisions and immutable attendance receipts."""

import sqlalchemy as sa
from alembic import op

revision = "20261028_attendance_sessions"
down_revision = "20261028_biometric_revision"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "recognition_policies",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("scoring_rule", sa.String(50), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("minimum_margin", sa.Float(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("pad_verified", sa.Boolean(), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "threshold BETWEEN -1 AND 1 AND minimum_margin BETWEEN 0 AND 2", name="ck_policy_thresholds"
        ),
        sa.CheckConstraint("mode IN ('disabled','supervised','automatic')", name="ck_policy_mode"),
        sa.CheckConstraint(
            "enabled = 0 OR (validated_at IS NOT NULL AND mode <> 'disabled')", name="ck_policy_validated"
        ),
        sa.CheckConstraint("mode <> 'automatic' OR pad_verified = 1", name="ck_policy_automatic_pad"),
    )
    op.create_table(
        "recognition_sessions",
        sa.Column("request_id", sa.String(36), primary_key=True),
        sa.Column("device_id", sa.String(36), nullable=False),
        sa.Column("policy_id", sa.String(64), nullable=False),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("employee_id", sa.String(36), nullable=True),
        sa.Column("biometric_revision", sa.Integer(), nullable=True),
        sa.Column("verified_model_id", sa.String(100), nullable=True),
        sa.Column("supervisor_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("receipt", sa.JSON(none_as_null=True), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.ForeignKeyConstraint(["policy_id"], ["recognition_policies.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.CheckConstraint("direction IN ('in','out')", name="ck_recognition_direction"),
        sa.CheckConstraint("state IN ('pending','verified','used','rejected')", name="ck_recognition_state"),
        sa.CheckConstraint(
            "state NOT IN ('verified','used') OR (employee_id IS NOT NULL AND biometric_revision IS NOT NULL AND verified_model_id IS NOT NULL)",
            name="ck_recognition_verified",
        ),
        sa.CheckConstraint("state <> 'used' OR receipt IS NOT NULL", name="ck_recognition_receipt"),
    )
    op.create_index("ix_recognition_sessions_device_id", "recognition_sessions", ["device_id"])
    op.create_index(
        "ix_attendance_person_direction_time",
        "attendance_events",
        ["employee_id", "direction", "server_time"],
    )


def downgrade():
    op.drop_index("ix_attendance_person_direction_time", table_name="attendance_events")
    op.drop_index("ix_recognition_sessions_device_id", table_name="recognition_sessions")
    op.drop_table("recognition_sessions")
    op.drop_table("recognition_policies")
