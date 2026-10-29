import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import context  # noqa: E402
from app import models  # noqa: E402, F401
from app.config import get_settings  # noqa: E402
from app.database import Base, get_engine  # noqa: E402

config = context.config
target_metadata = Base.metadata
if context.is_offline_mode():
    context.configure(url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()

