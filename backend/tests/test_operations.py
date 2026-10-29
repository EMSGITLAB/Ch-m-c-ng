import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app import operations
from app.config import get_settings
from app.database import get_session
from app.main import app
from sqlalchemy.exc import OperationalError
from test_admin import setup


def test_status_requires_admin_and_contains_only_aggregate_diagnostics(client, monkeypatch, tmp_path):
    browser, _ = client
    monkeypatch.setattr(get_settings(), "runtime_dir", tmp_path)
    assert browser.get("/api/admin/operations/status").status_code == 401
    setup(browser)
    response = browser.get("/api/admin/operations/status")
    assert response.status_code == 200
    result = response.json()
    assert result["database_ok"] is True
    assert result["backup"]["available"] is False
    assert "backup_missing" in result["alerts"]
    assert "instance_nonce" not in response.text and "database_url" not in response.text
    assert "participant_id" not in response.text and "employee_name" not in response.text


def test_snapshot_reports_failed_dependencies_and_disk_without_sql_details(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "runtime_dir", tmp_path)
    monkeypatch.setattr(operations, "database_probe", lambda db: False)
    monkeypatch.setattr(operations.shutil, "disk_usage", lambda path: SimpleNamespace(free=100, total=1000))
    result = operations.snapshot(None, None, None, None)
    assert {"disk_low", "database_unavailable", "recognition_unavailable"} <= set(result["alerts"])
    assert result["attendance_enabled"] is False
    (tmp_path / "backups").mkdir()
    (tmp_path / "backups/last-backup-error.json").write_text('{"error_type":"OSError"}')
    assert "backup_failed" in operations.snapshot(None, None, None, None)["alerts"]


def test_backup_metadata_handles_age_encryption_invalid_time_and_private_path(tmp_path):
    now = datetime.now(UTC)
    backups = tmp_path / "backups"
    backups.mkdir()
    path = backups / "last-backup.json"
    path.write_text(json.dumps({"completed_at": (now - timedelta(hours=25)).isoformat(),
                                "encrypted": True, "checksum_verified": True, "archive_path": "private-path"}))
    result = operations.backup_state(tmp_path, now)
    assert result["overdue"] and result["encrypted"] and result["checksum_verified"]
    assert "private-path" not in json.dumps(result)
    path.write_text(json.dumps({"completed_at": (now + timedelta(hours=1)).isoformat()}))
    assert operations.backup_state(tmp_path, now)["kind"] == "invalid_metadata"


def test_database_errors_are_503_without_leaking_credentials_or_sql_parameters(client):
    browser, _ = client
    original = app.dependency_overrides[get_session]

    class Broken:
        def get(self, *args, **kwargs):
            raise OperationalError("SELECT private-vector", {"password": "private-password"}, Exception("private-driver"))

    def broken():
        yield Broken()

    app.dependency_overrides[get_session] = broken
    try:
        response = browser.get("/api/auth/setup")
        assert response.status_code == 503
        assert "private-" not in response.text
    finally:
        app.dependency_overrides[get_session] = original
