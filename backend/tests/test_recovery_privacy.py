from uuid import uuid4

import pytest
from app import biometrics
from app.config import get_settings
from app.models import AttendanceEvent, Employee, FaceTemplate
from app.private_storage import recovery_key, seal, unseal
from app.revocation_ledger import apply_to_restored_database, merge_ledger, read_ledger
from cryptography.fernet import InvalidToken
from sqlalchemy import func, select
from test_biometrics import biometric_client as biometric_client
from test_biometrics import payload


def test_authenticated_encryption_rejects_tampering_wrong_key_and_size(tmp_path, monkeypatch):
    key = recovery_key(tmp_path, create=True)
    assert recovery_key(tmp_path) == key
    ciphertext = seal(b"private-test-only", key)
    assert b"private-test-only" not in ciphertext
    assert unseal(ciphertext, key) == b"private-test-only"
    with pytest.raises(InvalidToken):
        unseal(ciphertext[:-2] + b"aa", key)
    with pytest.raises(InvalidToken):
        unseal(ciphertext, recovery_key(tmp_path / "other", create=True))
    monkeypatch.setattr("app.private_storage.MAX_PLAINTEXT", 2)
    with pytest.raises(ValueError):
        seal(b"large", key)


def test_revocation_ledger_is_monotonic_encrypted_and_fails_closed_if_corrupted(tmp_path):
    subject = str(uuid4())
    assert merge_ledger(tmp_path, {subject: 3}) == {subject: 3}
    assert merge_ledger(tmp_path, {subject: 1}) == {subject: 3}
    path = tmp_path / "privacy/revocations.fernet"
    assert subject.encode() not in path.read_bytes()
    assert read_ledger(tmp_path) == {subject: 3}
    path.write_bytes(path.read_bytes()[:-2] + b"aa")
    with pytest.raises(ValueError, match="authentication"):
        read_ledger(tmp_path)


def test_real_purge_persists_external_deletion_floor(biometric_client):
    browser, _, headers, people = biometric_client
    target = people[0]
    response = browser.post(f"/api/admin/employees/{target['id']}/biometrics/purge",
                            json=payload(target), headers=headers)
    assert response.status_code == 200, response.text
    assert read_ledger(get_settings().runtime_dir) == {target["id"]: 1}


def test_ledger_failure_does_not_report_or_commit_purge(biometric_client, monkeypatch):
    browser, factory, headers, people = biometric_client
    target = people[0]

    def fail(*args, **kwargs):
        raise OSError("test disk failure")

    monkeypatch.setattr(biometrics, "merge_ledger", fail)
    response = browser.post(f"/api/admin/employees/{target['id']}/biometrics/purge",
                            json=payload(target), headers=headers)
    assert response.status_code == 503
    with factory() as db:
        assert db.get(Employee, target["id"]).biometric_revision == 0
        assert db.scalar(select(func.count()).select_from(FaceTemplate)) == 6


def test_recovery_removes_revoked_templates_preserves_new_revision_and_attendance(biometric_client):
    _, factory, _, people = biometric_client
    target, other = people
    with factory() as db:
        old = db.scalar(select(FaceTemplate).where(FaceTemplate.employee_id == target["id"]))
        db.add(FaceTemplate(employee_id=target["id"], model_id=old.model_id, biometric_revision=1,
                            dimensions=old.dimensions, vector=old.vector))
        db.flush()
        assert apply_to_restored_database(db, {target["id"]: 1}) == 1
        db.commit()
    with factory() as db:
        assert db.get(Employee, target["id"]).biometric_revision == 1
        assert db.scalar(select(func.count()).select_from(FaceTemplate).where(FaceTemplate.employee_id == target["id"])) == 1
        assert db.scalar(select(func.count()).select_from(FaceTemplate).where(FaceTemplate.employee_id == other["id"])) == 3
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 1


def test_external_ledger_keeps_newer_floor_when_local_copy_is_lost(tmp_path):
    subject = str(uuid4())
    external = tmp_path / "usb"
    external.mkdir()
    local = tmp_path / "local"
    merge_ledger(local, {subject: 3}, mirror_directory=external)
    (local / "privacy/revocations.fernet").unlink()
    assert merge_ledger(local, {subject: 1}, mirror_directory=external) == {subject: 3}
    assert read_ledger(local) == {subject: 3}


def test_unavailable_external_ledger_prevents_purge_commit(biometric_client, monkeypatch, tmp_path):
    browser, factory, headers, people = biometric_client
    target = people[0]
    monkeypatch.setattr(get_settings(), "backup_directory", tmp_path / "unplugged/backup")
    response = browser.post(f"/api/admin/employees/{target['id']}/biometrics/purge",
                            json=payload(target), headers=headers)
    assert response.status_code == 503
    with factory() as db:
        assert db.get(Employee, target["id"]).biometric_revision == 0
        assert db.scalar(select(func.count()).select_from(FaceTemplate)) == 6
