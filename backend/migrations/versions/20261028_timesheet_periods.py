"""Append-only correction history and immutable period snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "20261028_timesheet_periods"
down_revision = "20261028_shift_revisions"
branch_labels = None
depends_on = None


def upgrade():
    gate = op.create_table(
        "calendar_gate",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.CheckConstraint("id = 1", name="ck_calendar_gate_singleton"),
    )
    op.bulk_insert(gate, [{"id": 1}])
    op.create_table(
        "timesheet_periods",
        sa.Column("month", sa.String(7), primary_key=True),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("protected_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("protected_until", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('open','locked') AND revision >= 0", name="ck_period_state"),
        sa.CheckConstraint(
            "status <> 'locked' OR (revision > 0 AND locked_at IS NOT NULL AND protected_from IS NOT NULL AND protected_until IS NOT NULL)",
            name="ck_period_locked",
        ),
    )
    op.create_index("ix_timesheet_periods_protected_from", "timesheet_periods", ["protected_from"])
    op.create_table(
        "timesheet_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("reason", sa.UnicodeText(), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("calculation_version", sa.String(50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("protection", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["month"], ["timesheet_periods.month"]),
        sa.ForeignKeyConstraint(["created_by"], ["admin_users.id"]),
        sa.UniqueConstraint("month", "revision", name="uq_snapshot_month_revision"),
    )
    op.create_table(
        "attendance_adjustments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(36), nullable=False, unique=True),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("employee_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(4), nullable=False),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("target_event_id", sa.String(36), nullable=True),
        sa.Column("target_adjustment_id", sa.String(36), nullable=True),
        sa.Column("reason", sa.UnicodeText(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.UnicodeText(), nullable=True),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.ForeignKeyConstraint(["target_event_id"], ["attendance_events.id"]),
        sa.ForeignKeyConstraint(["target_adjustment_id"], ["attendance_adjustments.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["admin_users.id"]),
        sa.CheckConstraint(
            "kind IN ('add','void') AND direction IN ('in','out')", name="ck_adjustment_kind_direction"
        ),
        sa.CheckConstraint(
            "(kind = 'add' AND target_event_id IS NULL AND target_adjustment_id IS NULL) OR (kind = 'void' AND ((target_event_id IS NOT NULL AND target_adjustment_id IS NULL) OR (target_event_id IS NULL AND target_adjustment_id IS NOT NULL)))",
            name="ck_adjustment_target",
        ),
    )
    for name, column in [
        ("ix_attendance_adjustments_employee_id", "employee_id"),
        ("ix_attendance_adjustments_occurred_at", "occurred_at"),
    ]:
        op.create_index(name, "attendance_adjustments", [column])
    for name, column in [
        ("uq_active_void_event", "target_event_id"),
        ("uq_active_void_adjustment", "target_adjustment_id"),
    ]:
        condition = sa.text(f"kind = 'void' AND revoked_at IS NULL AND {column} IS NOT NULL")
        op.create_index(
            name,
            "attendance_adjustments",
            [column],
            unique=True,
            mssql_where=condition,
            sqlite_where=condition,
            postgresql_where=condition,
        )


def downgrade():
    for table in ("attendance_adjustments", "timesheet_snapshots", "timesheet_periods"):
        if op.get_bind().execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one():
            raise RuntimeError(
                "Cannot downgrade correction or period history; retain a compatible application and database backup"
            )
    op.drop_table("attendance_adjustments")
    op.drop_table("timesheet_snapshots")
    op.drop_table("timesheet_periods")
    op.drop_table("calendar_gate")
