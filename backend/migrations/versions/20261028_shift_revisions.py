"""Version shift definitions and preserve cancelled assignment history."""

import sqlalchemy as sa
from alembic import op

revision = "20261028_shift_revisions"
down_revision = "20261028_attendance_sessions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("shifts", sa.Column("family_id", sa.String(36), nullable=True))
    op.execute("UPDATE shifts SET family_id = id")
    op.alter_column("shifts", "family_id", existing_type=sa.String(36), nullable=False)
    op.add_column("shifts", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.add_column(
        "shifts", sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Ho_Chi_Minh")
    )
    op.add_column("shifts", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_shift_family_revision", "shifts", ["family_id", "revision"])
    op.add_column("shift_assignments", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("shift_assignments", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("shift_assignments", sa.Column("cancel_reason", sa.UnicodeText(), nullable=True))
    op.drop_constraint("uq_employee_shift_date", "shift_assignments", type_="unique")
    op.create_index(
        "uq_active_employee_shift_date",
        "shift_assignments",
        ["employee_id", "shift_id", "work_date"],
        unique=True,
        mssql_where=sa.text("cancelled_at IS NULL"),
        sqlite_where=sa.text("cancelled_at IS NULL"),
        postgresql_where=sa.text("cancelled_at IS NULL"),
    )


def downgrade():
    # A base-schema rollback cannot represent repeated cancelled history.
    # Refuse rather than dropping records to make a downgrade fit.
    duplicates = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT TOP 1 employee_id FROM shift_assignments GROUP BY employee_id,shift_id,work_date HAVING COUNT(*) > 1"
            )
            if op.get_bind().dialect.name == "mssql"
            else sa.text(
                "SELECT employee_id FROM shift_assignments GROUP BY employee_id,shift_id,work_date HAVING COUNT(*) > 1 LIMIT 1"
            )
        )
        .first()
    )
    versioned = (
        op.get_bind()
        .execute(sa.text("SELECT COUNT(*) FROM shifts WHERE archived_at IS NOT NULL OR revision > 1"))
        .scalar_one()
    )
    cancelled = (
        op.get_bind()
        .execute(sa.text("SELECT COUNT(*) FROM shift_assignments WHERE cancelled_at IS NOT NULL"))
        .scalar_one()
    )
    if duplicates or versioned or cancelled:
        raise RuntimeError(
            "Cannot downgrade versioned or cancelled shift history; preserve data and restore a compatible app version"
        )
    op.drop_index("uq_active_employee_shift_date", table_name="shift_assignments")
    op.create_unique_constraint(
        "uq_employee_shift_date", "shift_assignments", ["employee_id", "shift_id", "work_date"]
    )
    for column in ("cancel_reason", "cancelled_at", "created_at"):
        op.drop_column("shift_assignments", column)
    op.drop_constraint("uq_shift_family_revision", "shifts", type_="unique")
    for column in ("archived_at", "timezone", "revision", "family_id"):
        op.drop_column("shifts", column, mssql_drop_default=column in {"timezone", "revision"})
