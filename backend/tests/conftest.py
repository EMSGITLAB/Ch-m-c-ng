# ruff: noqa: E402
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from app.auth import limiter
from app.config import get_settings
from app.database import Base, get_session
from app.devices import pair_limiter
from app.main import app
from app.models import CalendarGate
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client(monkeypatch, tmp_path):
    test_url=os.environ.get("CHAMCONG_TEST_DATABASE_URL")
    if test_url:
        name=os.environ.get("CHAMCONG_TEST_DB_NAME","")
        assert re.fullmatch(r"ChamCong_AdminCheck_[0-9a-f]{8}",name),"Refusing a non-isolated test database"
        engine=create_engine(test_url)
        with engine.begin() as connection:
            assert connection.execute(text("SELECT DB_NAME()")).scalar_one()==name
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
    else:
        engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
        event.listen(engine,"connect",lambda conn,record:conn.execute("PRAGMA foreign_keys=ON"))
        Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(CalendarGate.__table__.insert().values(id=1))
    factory=sessionmaker(engine,expire_on_commit=False)
    def sessions():
        with factory() as session:
            yield session
    app.dependency_overrides[get_session]=sessions
    limiter.items.clear()
    pair_limiter.items.clear()
    settings=get_settings()
    monkeypatch.setattr(settings, "runtime_dir", tmp_path / "runtime")
    monkeypatch.setattr(settings, "backup_directory", None)
    # Isolated test databases must never inherit the real laptop trial selector.
    monkeypatch.setattr(settings, "functional_trial_enabled", False)
    monkeypatch.setattr(settings, "functional_trial_policy_id", None)
    old_secret=settings.session_secret
    settings.session_secret="test-secret-"*5
    try:
        with TestClient(app) as browser:
            yield browser,factory
    finally:
        settings.session_secret=old_secret
        app.dependency_overrides.clear()
        engine.dispose()

