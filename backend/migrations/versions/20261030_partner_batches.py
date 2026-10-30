"""Separate partner vendors, work batches and kiosk bindings from employees."""

import sqlalchemy as sa
from alembic import op

revision = "20261030_partner_batches"
down_revision = "20261029_employee_soft_delete"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("partner_vendors",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(32), unique=True, nullable=False),
        sa.Column("name", sa.Unicode(160), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("partner_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(36), unique=True, nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("partner_id", sa.String(36), sa.ForeignKey("partner_vendors.id"), nullable=False),
        sa.Column("name", sa.Unicode(100), nullable=False),
        sa.Column("site", sa.Unicode(120), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("admission_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checkout_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rules", sa.JSON(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False),
        sa.Column("retention_hours", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("policy_id", sa.String(64), sa.ForeignKey("recognition_policies.id"), nullable=True),
        sa.Column("model_id", sa.String(100), nullable=True),
        sa.Column("threshold", sa.Float(), nullable=True),
        sa.Column("minimum_margin", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("capacity BETWEEN 1 AND 5000 AND next_number >= 0 AND retention_hours = 48", name="ck_partner_batch_limits"),
        sa.CheckConstraint("state IN ('draft','open','running','review','closed')", name="ck_partner_batch_state"),
        sa.CheckConstraint("admission_from <= starts_at AND starts_at < ends_at AND ends_at <= checkout_until", name="ck_partner_batch_times"),
        sa.CheckConstraint("state = 'draft' OR (policy_id IS NOT NULL AND model_id IS NOT NULL AND threshold IS NOT NULL AND minimum_margin IS NOT NULL)", name="ck_partner_batch_policy"))
    op.create_index("ix_partner_batches_partner_id", "partner_batches", ["partner_id"])
    op.create_index("ix_partner_batches_work_date", "partner_batches", ["work_date"])
    op.create_table("partner_device_bindings",
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id"), primary_key=True),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("partner_batches.id"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_partner_device_bindings_batch_id", "partner_device_bindings", ["batch_id"])


def downgrade():
    op.drop_table("partner_device_bindings")
    op.drop_table("partner_batches")
    op.drop_table("partner_vendors")
