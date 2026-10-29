"""Separate functional trials from production automatic/PAD validation."""

from alembic import op
from sqlalchemy import text

revision = "20261028_functional_trial"
down_revision = "20261028_recognition_frames"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("recognition_policies") as batch:
        batch.drop_constraint("ck_policy_mode", type_="check")
        batch.create_check_constraint(
            "ck_policy_mode", "mode IN ('disabled','supervised','automatic','functional_trial')"
        )


def downgrade():
    if op.get_bind().execute(text(
        "SELECT COUNT(*) FROM recognition_policies WHERE mode = 'functional_trial'"
    )).scalar_one():
        raise RuntimeError("Preserve trial history before downgrading")
    with op.batch_alter_table("recognition_policies") as batch:
        batch.drop_constraint("ck_policy_mode", type_="check")
        batch.create_check_constraint("ck_policy_mode", "mode IN ('disabled','supervised','automatic')")
