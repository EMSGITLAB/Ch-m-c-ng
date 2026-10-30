"""Keep employee identity and attendance history after administrative deletion."""

import sqlalchemy as sa
from alembic import op

revision = "20261029_employee_soft_delete"
down_revision = "20261028_functional_trial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("employees", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("employees", "deleted_at")
