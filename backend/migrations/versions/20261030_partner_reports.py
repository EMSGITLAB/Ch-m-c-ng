"""Append-only partner report corrections and immutable batch snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "20261030_partner_reports"
down_revision = "20261030_partner_admission"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("partner_batches", sa.Column("requested_count", sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE partner_batches SET requested_count = capacity")
    op.create_table("partner_report_adjustments",
        sa.Column("request_id", sa.String(36), primary_key=True),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("partner_batches.id"), nullable=False),
        sa.Column("worker_id", sa.String(36), sa.ForeignKey("partner_workers.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("overrides", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Unicode(500), nullable=False),
        sa.Column("admin_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("worker_id", "revision", name="uq_partner_adjustment_revision"),
        sa.CheckConstraint("revision > 0", name="ck_partner_adjustment_revision"))
    op.create_index("ix_partner_report_adjustments_batch_id", "partner_report_adjustments", ["batch_id"])
    op.create_index("ix_partner_report_adjustments_worker_id", "partner_report_adjustments", ["worker_id"])
    op.create_table("partner_report_snapshots",
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("partner_batches.id"), primary_key=True),
        sa.Column("request_id", sa.String(36), unique=True, nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("reason", sa.Unicode(500), nullable=False),
        sa.Column("admin_id", sa.Integer(), sa.ForeignKey("admin_users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    op.drop_table("partner_report_snapshots")
    op.drop_table("partner_report_adjustments")
    op.drop_column("partner_batches", "requested_count", mssql_drop_default=True)
