"""Temporary partner identities and ordered camera captures; no SQL vectors."""

import sqlalchemy as sa
from alembic import op

revision = "20261030_partner_admission"
down_revision = "20261030_partner_batches"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("partner_batches", sa.Column("serial_number", sa.Integer(), nullable=True))
    op.create_index("uq_partner_batch_serial", "partner_batches", ["serial_number"], unique=True,
                    mssql_where=sa.text("serial_number IS NOT NULL"),
                    sqlite_where=sa.text("serial_number IS NOT NULL"),
                    postgresql_where=sa.text("serial_number IS NOT NULL"))
    table = op.create_table("partner_counter",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("next_batch", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1 AND next_batch >= 0", name="ck_partner_counter"))
    op.bulk_insert(table, [{"id": 1, "next_batch": 0}])
    op.create_table("partner_workers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("partner_batches.id"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(100), unique=True, nullable=False),
        sa.Column("admission_request_id", sa.String(36), unique=True, nullable=False),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("declared_name", sa.Unicode(160), nullable=True),
        sa.Column("name_source", sa.String(16), nullable=True),
        sa.Column("name_revision", sa.Integer(), nullable=False),
        sa.Column("name_confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reserved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pending_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("biometric_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("face_reference", sa.String(36), nullable=True),
        sa.UniqueConstraint("batch_id", "number", name="uq_partner_worker_number"),
        sa.CheckConstraint("state IN ('pending','active','completed','cancelled') AND number > 0 AND name_revision >= 0", name="ck_partner_worker_state"),
        sa.CheckConstraint("state NOT IN ('active','completed') OR (declared_name IS NOT NULL AND name_confirmed_at IS NOT NULL AND approved_at IS NOT NULL AND admitted_at IS NOT NULL)", name="ck_partner_worker_admitted"),
        sa.CheckConstraint("state <> 'completed' OR checked_out_at IS NOT NULL", name="ck_partner_worker_completed"))
    op.create_index("ix_partner_workers_batch_id", "partner_workers", ["batch_id"])
    op.create_table("partner_captures",
        sa.Column("request_id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("partner_batches.id"), nullable=False),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("worker_id", sa.String(36), sa.ForeignKey("partner_workers.id"), nullable=True),
        sa.Column("frames", sa.JSON(), nullable=False),
        sa.Column("feature_reference", sa.String(36), nullable=True),
        sa.Column("stable_frames", sa.Integer(), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("receipt", sa.JSON(none_as_null=True), nullable=True),
        sa.CheckConstraint("state IN ('pending','verified','used','rejected') AND direction IN ('in','out')", name="ck_partner_capture_state"),
        sa.CheckConstraint("stable_frames BETWEEN 0 AND 12", name="ck_partner_capture_frames"),
        sa.CheckConstraint("state NOT IN ('verified','used') OR worker_id IS NOT NULL", name="ck_partner_capture_worker"),
        sa.CheckConstraint("state <> 'used' OR receipt IS NOT NULL", name="ck_partner_capture_receipt"))
    op.create_index("ix_partner_captures_batch_id", "partner_captures", ["batch_id"])
    op.create_index("ix_partner_captures_device_id", "partner_captures", ["device_id"])
    op.create_table("partner_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("worker_id", sa.String(36), sa.ForeignKey("partner_workers.id"), nullable=False),
        sa.Column("capture_id", sa.String(36), sa.ForeignKey("partner_captures.request_id"), unique=True, nullable=False),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("server_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("declared_name", sa.Unicode(160), nullable=False),
        sa.UniqueConstraint("worker_id", "direction", name="uq_partner_worker_direction"),
        sa.CheckConstraint("direction IN ('in','out')", name="ck_partner_event_direction"))
    op.create_index("ix_partner_events_worker_id", "partner_events", ["worker_id"])


def downgrade():
    for name in ("partner_events", "partner_captures", "partner_workers", "partner_counter"):
        op.drop_table(name)
    op.drop_index("uq_partner_batch_serial", table_name="partner_batches")
    op.drop_column("partner_batches", "serial_number")
