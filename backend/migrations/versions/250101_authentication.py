"""Local administrator and revocable server-side sessions."""
import sqlalchemy as sa
from alembic import op

revision = "250101_authentication"
down_revision = "15e5e1460f75"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("admin_users",
                    sa.Column("id",sa.Integer(),autoincrement=False,nullable=False),
                    sa.Column("username",sa.Unicode(80),nullable=False),
                    sa.Column("password_hash",sa.String(512),nullable=False),
                    sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
                    sa.CheckConstraint("id = 1",name="ck_single_admin"),
                    sa.PrimaryKeyConstraint("id"),sa.UniqueConstraint("username"))
    op.create_table("auth_sessions",
                    sa.Column("token_hash",sa.String(64),nullable=False),
                    sa.Column("user_id",sa.Integer(),nullable=False),
                    sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),
                    sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
                    sa.ForeignKeyConstraint(["user_id"],["admin_users.id"]),sa.PrimaryKeyConstraint("token_hash"))
    op.create_index("ix_auth_sessions_expires_at","auth_sessions",["expires_at"])


def downgrade():
    op.drop_index("ix_auth_sessions_expires_at",table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("admin_users")
