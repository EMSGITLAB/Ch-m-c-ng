import hashlib
import io
import json
import zipfile

import pytest
from app import native_backup
from app.private_storage import recovery_key, seal
from app.recovery_key import wrap_key


def payload(extra=None, *, version=1):
    files = {"database.bak": b"fake-native-backup-test-only", "server.env": b"test-only",
             "config/business.json": b"{}", "privacy/revocations.fernet": b"test-only"} | (extra or {})
    manifest = {"format": version, "project": native_backup.MARKER, "schema_revision": "test-only",
                "files": {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
        archive.writestr("recovery-manifest.json", json.dumps(manifest))
    return output.getvalue()


@pytest.mark.parametrize("path", ["../outside", "/absolute", "C:/outside", "models\\..\\outside"])
def test_recovery_payload_rejects_unsafe_paths_even_with_valid_checksums(path):
    with pytest.raises(ValueError, match="Unsafe"):
        native_backup.validate_payload(payload({path: b"fake-test-only"}))


def test_recovery_payload_checks_manifest_file_set_and_content():
    assert native_backup.validate_payload(payload())["project"] == native_backup.MARKER
    content = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(payload())) as source, zipfile.ZipFile(content, "w") as target:
        for name in source.namelist():
            target.writestr(name, b"changed" if name == "database.bak" else source.read(name))
    with pytest.raises(ValueError, match="checksum"):
        native_backup.validate_payload(content.getvalue())


def test_restore_refuses_existing_or_production_target_before_any_restore_sql(tmp_path, monkeypatch):
    key = recovery_key(tmp_path, create=True)
    path = tmp_path / "test.ccbackup"
    path.write_bytes(seal(payload(), key))
    key_path = tmp_path / "keys/backup.key"

    def forbidden(*args, **kwargs):
        raise AssertionError("No SQL connection allowed for unsafe target")

    monkeypatch.setattr(native_backup.pyodbc, "connect", forbidden)
    with pytest.raises(ValueError, match="isolated"):
        native_backup.restore_new_database(path, key_path=key_path, target_name="ChamCongFaceLocal")
    with pytest.raises(ValueError, match="isolated"):
        native_backup.restore_new_database(path, key_path=key_path, target_name="master")


def test_restore_accepts_protected_key_without_using_original_key_file(tmp_path, monkeypatch):
    monkeypatch.setattr(native_backup.get_settings(), "runtime_dir", tmp_path)
    key = recovery_key(tmp_path, create=True)
    archive = tmp_path / "sample.ccbackup"
    archive.write_bytes(seal(payload(), key))
    protected = tmp_path / "recovery.cckey"
    password = "Test-only local restoration password"
    protected.write_bytes(wrap_key(key, password))
    (tmp_path / "keys/backup.key").unlink()

    def forbidden(*args, **kwargs):
        raise AssertionError("decryption_completed_without_original_key")

    monkeypatch.setattr(native_backup.pyodbc, "connect", forbidden)
    target = "ChamCong_RecoveryNew_a1b2c3d4"
    with pytest.raises(AssertionError, match="decryption_completed"):
        native_backup.restore_new_database(archive, key_path=protected, key_password=password, target_name=target)
    with pytest.raises(ValueError, match="Mật khẩu"):
        native_backup.restore_new_database(archive, key_path=protected, key_password=password + "wrong", target_name=target)


def test_v2_requires_external_deletion_ledger_before_creating_database(tmp_path, monkeypatch):
    monkeypatch.setattr(native_backup.get_settings(), "runtime_dir", tmp_path)
    key = recovery_key(tmp_path, create=True)
    archive = tmp_path / "sample.ccbackup"
    archive.write_bytes(seal(payload(version=2), key))

    def forbidden(*args, **kwargs):
        raise AssertionError("A missing deletion ledger must not reach SQL")

    monkeypatch.setattr(native_backup.pyodbc, "connect", forbidden)
    with pytest.raises(ValueError, match="external deletion ledger"):
        native_backup.restore_new_database(archive, target_name="ChamCong_RecoveryNew_a1b2c3d4")
