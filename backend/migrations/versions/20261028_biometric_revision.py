"""Invalidate in-flight biometric writes when an employee's data is erased."""
import sqlalchemy as sa
from alembic import op

revision = "20261028_biometric_revision"
down_revision = "20261028_capture_guidance"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("employees", "face_templates", "face_collections"):
        op.add_column(table, sa.Column("biometric_revision", sa.Integer(), server_default="0", nullable=False))


def downgrade():
    for table in ("face_collections", "face_templates", "employees"):
        op.drop_column(table, "biometric_revision", mssql_drop_default=True)
