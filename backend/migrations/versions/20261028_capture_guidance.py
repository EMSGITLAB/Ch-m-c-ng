"""Version capture guidance without relabelling earlier samples."""
import sqlalchemy as sa
from alembic import op

revision = "20261028_capture_guidance"
down_revision = "20261028_face_collection"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("face_collections", sa.Column("guidance_protocol", sa.String(32), nullable=True))


def downgrade():
    op.drop_column("face_collections", "guidance_protocol")
