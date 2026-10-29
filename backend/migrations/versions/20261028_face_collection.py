"""Separate capture sessions for enrollment, calibration and final evaluation."""
import sqlalchemy as sa
from alembic import op

revision = "20261028_face_collection"
down_revision = "20261028_device_pairing"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("face_collections",
        sa.Column("id",sa.String(36),nullable=False),sa.Column("employee_id",sa.String(36),nullable=False),
        sa.Column("model_id",sa.String(100),nullable=False),sa.Column("purpose",sa.String(16),nullable=False),
        sa.Column("status",sa.String(16),nullable=False),sa.Column("sample_count",sa.Integer(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("completed_at",sa.DateTime(timezone=True),nullable=True),sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["employee_id"],["employees.id"]),
        sa.CheckConstraint("purpose IN ('enrollment','calibration','evaluation')",name="ck_collection_purpose"),
        sa.CheckConstraint("status IN ('open','complete','cancelled')",name="ck_collection_status"),
        sa.CheckConstraint("sample_count BETWEEN 0 AND 10",name="ck_collection_count"))
    op.create_index("ix_face_collections_employee_id","face_collections",["employee_id"])
    op.create_table("collection_samples",
        sa.Column("id",sa.String(36),nullable=False),sa.Column("collection_id",sa.String(36),nullable=False),
        sa.Column("position",sa.Integer(),nullable=False),sa.Column("fingerprint",sa.String(64),nullable=False),
        sa.Column("model_id",sa.String(100),nullable=False),
        sa.Column("vector",sa.LargeBinary(),nullable=False),sa.Column("dimensions",sa.Integer(),nullable=False),
        sa.Column("quality",sa.JSON(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(["collection_id"],["face_collections.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collection_id","position",name="uq_collection_position"),
        sa.UniqueConstraint("model_id","fingerprint",name="uq_model_sample_fingerprint"))
    op.create_index("ix_collection_samples_collection_id","collection_samples",["collection_id"])


def downgrade():
    op.drop_index("ix_collection_samples_collection_id",table_name="collection_samples")
    op.drop_table("collection_samples")
    op.drop_index("ix_face_collections_employee_id",table_name="face_collections")
    op.drop_table("face_collections")
