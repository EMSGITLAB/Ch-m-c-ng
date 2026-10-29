"""Keep user-provided reference images separate from operational templates."""

import sqlalchemy as sa
from alembic import op

revision = "20261028_imported_photos"
down_revision = "20261028_timesheet_periods"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "imported_face_photos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("employee_id", sa.String(36), nullable=False),
        sa.Column("sample_id", sa.String(36), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("image", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(30), nullable=False),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("biometric_revision", sa.Integer(), nullable=False),
        sa.Column("quality", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"]),
        sa.ForeignKeyConstraint(["sample_id"], ["collection_samples.id"]),
    )
    # SQL Server UNIQUE permits only one NULL unless filtered explicitly.
    condition = sa.text("sample_id IS NOT NULL")
    op.create_index(
        "uq_imported_photo_sample",
        "imported_face_photos",
        ["sample_id"],
        unique=True,
        mssql_where=condition,
        sqlite_where=condition,
        postgresql_where=condition,
    )
    op.create_index("ix_imported_face_photos_employee_id", "imported_face_photos", ["employee_id"])
    op.create_index("ix_imported_face_photos_batch_id", "imported_face_photos", ["batch_id"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM imported_face_photos")).scalar_one():
        raise RuntimeError(
            "Cannot downgrade imported biometric photos; preserve data and use a compatible application"
        )
    op.drop_table("imported_face_photos")
