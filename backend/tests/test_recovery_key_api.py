import json

from app.config import get_settings
from app.models import AuditLog
from app.operations import key_slots
from app.private_storage import recovery_key
from app.recovery_key import unwrap_key
from app.recovery_key_files import preserved_key
from sqlalchemy import select
from test_admin import setup

PASSWORD = "Test-only local recovery password"
ENDPOINT = "/api/admin/operations/recovery-key/export"


def test_export_requires_admin_csrf_and_configured_destination(client, tmp_path, monkeypatch):
    browser, _ = client
    body = {"password": PASSWORD, "confirmation": PASSWORD}
    assert browser.post(ENDPOINT, json=body).status_code == 401
    headers = {"X-CSRF-Token": setup(browser)}
    assert browser.post(ENDPOINT, json=body).status_code == 403
    assert browser.post(ENDPOINT, json=body, headers=headers).status_code == 409
    destination = tmp_path / "backup"
    destination.mkdir()
    monkeypatch.setattr(get_settings(), "backup_directory", destination)
    assert key_slots.acquire(blocking=False)
    try:
        assert browser.post(ENDPOINT, json=body, headers=headers).status_code == 429
    finally:
        key_slots.release()
    response = browser.post(ENDPOINT, json=body | {"confirmation": "different"}, headers=headers)
    assert response.status_code == 422 and PASSWORD not in response.text
    assert not list(destination.iterdir())


def test_export_round_trip_uses_only_protected_file_and_never_logs_password(client, tmp_path, monkeypatch):
    browser, factory = client
    headers = {"X-CSRF-Token": setup(browser)}
    settings = get_settings()
    destination = tmp_path / "external-device"
    destination.mkdir()
    monkeypatch.setattr(settings, "backup_directory", destination)
    original = recovery_key(settings.runtime_dir, create=True)
    response = browser.post(ENDPOINT, json={"password": PASSWORD, "confirmation": PASSWORD}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["plaintext_key_exported"] is False
    path = destination / response.json()["filename"]
    assert path.suffix == ".cckey"
    assert original not in path.read_bytes() and PASSWORD.encode() not in path.read_bytes()
    assert unwrap_key(path.read_bytes(), PASSWORD) == original
    assert preserved_key(settings.runtime_dir)
    assert browser.get("/api/admin/operations/status").json()["recovery_key_preserved"] is True
    with factory() as db:
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "recovery_key_export"))
        assert audit is not None
        assert PASSWORD not in json.dumps(audit.details)
        assert original.decode() not in json.dumps(audit.details)
    path.write_bytes(b"tampered")
    assert preserved_key(settings.runtime_dir) is False


def test_short_password_is_generic_and_missing_media_does_not_create_directory(client, tmp_path, monkeypatch):
    browser, _ = client
    headers = {"X-CSRF-Token": setup(browser)}
    response = browser.post(ENDPOINT, json={"password": "short", "confirmation": "short"}, headers=headers)
    assert response.status_code == 422 and '"input"' not in response.text
    missing = tmp_path / "unplugged-device/backup"
    monkeypatch.setattr(get_settings(), "backup_directory", missing)
    recovery_key(get_settings().runtime_dir, create=True)
    response = browser.post(ENDPOINT, json={"password": PASSWORD, "confirmation": PASSWORD}, headers=headers)
    assert response.status_code == 503
    assert PASSWORD not in response.text and not missing.exists()
