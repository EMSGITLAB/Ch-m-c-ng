from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from app.biometrics import PurgeInput, purge_biometrics
from app.calibration import load_samples
from app.capture_guidance import PROTOCOL
from app.gallery import load_gallery
from app.main import app
from app.models import (
    AttendanceEvent,
    AuditLog,
    CollectionSample,
    Device,
    Employee,
    FaceCollection,
    FaceTemplate,
)
from sqlalchemy import event, func, select
from test_admin import setup


@pytest.fixture
def biometric_client(client):
    browser, factory = client
    headers = {"X-CSRF-Token": setup(browser)}
    people = [browser.post("/api/admin/employees", json={"code": code, "name": "Hồ sơ thử"}, headers=headers).json()
              for code in ["TEST1", "TEST2"]]
    with factory() as db:
        for number, employee in enumerate(people):
            vector = np.eye(128, dtype="<f4")[number].tobytes()
            for _ in range(3):
                db.add(FaceTemplate(employee_id=employee["id"], model_id="m", vector=vector, dimensions=128))
            collection = FaceCollection(employee_id=employee["id"], model_id="m", purpose="enrollment",
                                        status="complete", sample_count=5, expires_at=datetime.now(UTC)+timedelta(minutes=10))
            db.add(collection)
            db.flush()
            for position in range(1, 6):
                db.add(CollectionSample(collection_id=collection.id, position=position, fingerprint=f"{number}-{position}",
                                        model_id="m", vector=vector, dimensions=128, quality={}))
        device = Device(name="Test", direction="in")
        db.add(device)
        db.flush()
        db.add(AttendanceEvent(employee_id=people[0]["id"], device_id=device.id, request_id="preserve-test",
                               direction="in", recognition_version="test-only"))
        db.commit()
    return browser, factory, headers, people


def payload(employee, revision=0):
    return {"confirm_employee_code": employee["code"], "expected_revision": revision, "reason": "Xóa dữ liệu thử"}


def test_purge_scoped_atomic_and_preserves_employee_attendance_and_other_subject(biometric_client):
    browser, factory, headers, people = biometric_client
    target, other = people
    endpoint = f"/api/admin/employees/{target['id']}/biometrics"
    preview = browser.get(endpoint)
    assert preview.status_code == 200
    assert preview.json()["templates_by_model"] == [{"model_id": "m", "count": 3}]
    assert "vector" not in preview.text
    assert browser.post(endpoint+"/purge", json=payload(target)).status_code == 403
    invalid = payload(target) | {"confirm_employee_code": "WRONG"}
    assert browser.post(endpoint+"/purge", json=invalid, headers=headers).status_code == 422
    response = browser.post(endpoint+"/purge", json=payload(target), headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["deleted"] == {"templates": 3, "collections": 1, "samples": 5}
    assert response.json()["revision"] == 1
    assert response.json()["backup_copies_deleted"] is False
    assert browser.post(endpoint+"/purge", json=payload(target), headers=headers).status_code == 409
    with factory() as db:
        assert db.get(Employee, target["id"]).active
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 1
        assert db.scalar(select(func.count()).select_from(FaceTemplate)) == 3
        assert db.scalar(select(func.count()).select_from(CollectionSample)) == 5
        assert set(load_gallery(db, "m").samples) == {other["id"]}
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "biometrics_purge"))
        assert audit.reason == "Xóa dữ liệu thử"
        assert "vector" not in str(audit.details)
    browser.cookies.clear()
    assert browser.get(endpoint).status_code == 401
    assert browser.post(endpoint+"/purge", json=payload(target), headers=headers).status_code == 401


def test_deactivation_immediately_excludes_new_gallery_and_calibration_reads(biometric_client):
    browser, factory, headers, people = biometric_client
    target = people[0]
    assert browser.patch(f"/api/admin/employees/{target['id']}", json={"active": False}, headers=headers).status_code == 200
    with factory() as db:
        assert target["id"] not in load_gallery(db, "m").samples
        assert all(sample.person != target["id"] for sample in load_samples(db, "m"))
        assert db.scalar(select(func.count()).select_from(FaceTemplate)) == 6  # Deactivation is reversible.
    assert browser.post(f"/api/admin/employees/{target['id']}/collections", json={}, headers=headers).status_code == 404


def test_purge_rolls_back_everything_if_audit_cannot_be_written(biometric_client):
    browser, factory, headers, people = biometric_client
    target = people[0]
    def reject(mapper, connection, record):
        if record.action == "biometrics_purge":
            raise RuntimeError("test audit failure")
    event.listen(AuditLog, "before_insert", reject)
    try:
        with pytest.raises(RuntimeError, match="test audit failure"):
            browser.post(f"/api/admin/employees/{target['id']}/biometrics/purge", json=payload(target), headers=headers)
    finally:
        event.remove(AuditLog, "before_insert", reject)
    with factory() as db:
        assert db.get(Employee, target["id"]).biometric_revision == 0
        assert db.scalar(select(func.count()).select_from(FaceTemplate)) == 6
        assert db.scalar(select(func.count()).select_from(CollectionSample)) == 10


@pytest.mark.parametrize("action", ["deactivate", "purge"])
def test_capture_in_flight_cannot_write_after_deactivation_or_purge(biometric_client, action):
    browser, factory, headers, people = biometric_client
    target = people[0]
    with factory() as db:
        collection = FaceCollection(employee_id=target["id"], model_id="m", purpose="calibration", status="open",
                                    guidance_protocol=PROTOCOL, expires_at=datetime.now(UTC)+timedelta(minutes=10))
        db.add(collection)
        db.commit()
        collection_id = collection.id
    class RacingEngine:
        model_id = "m"
        def analyze(self, content, max_bytes):
            with factory() as db:
                if action == "purge":
                    purge_biometrics(target["id"], PurgeInput(**payload(target)), db, None)
                else:
                    db.get(Employee, target["id"]).active = False
                    db.commit()
            vector = np.eye(128, dtype=np.float32)[0]
            return vector, {"quality": {"accepted": True, "yaw_ratio": 0, "pitch_ratio": .5, "roll_degrees": 0}}
    app.state.face_engine = RacingEngine()
    response = browser.post(f"/api/admin/collections/{collection_id}/samples", content=b"new-photo", headers=headers)
    assert response.status_code == 409, response.text
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CollectionSample)
                         .where(CollectionSample.collection_id == collection_id)) == 0


def test_only_current_revision_and_model_are_loaded_even_if_old_rows_reappear(biometric_client):
    _, factory, _, people = biometric_client
    target = people[0]
    with factory() as db:
        db.get(Employee, target["id"]).biometric_revision = 1
        db.commit()
        assert target["id"] not in load_gallery(db, "m").samples
        assert all(sample.person != target["id"] for sample in load_samples(db, "m"))
        assert not load_gallery(db, "other-model").samples


def test_gallery_rejects_corrupted_current_template(biometric_client):
    _, factory, _, _ = biometric_client
    with factory() as db:
        row = db.scalar(select(FaceTemplate))
        row.vector = b"bad"
        db.commit()
        with pytest.raises(ValueError, match="invalid_template_dimensions"):
            load_gallery(db, "m")


def test_fresh_capture_after_purge_uses_new_revision(biometric_client):
    browser, factory, headers, people = biometric_client
    target = people[0]
    assert browser.post(f"/api/admin/employees/{target['id']}/biometrics/purge", json=payload(target), headers=headers).status_code == 200
    class FreshEngine:
        model_id = "m"
        def analyze(self, content, max_bytes):
            return np.eye(128, dtype=np.float32)[0], {"quality": {"accepted": True, "yaw_ratio": 0, "pitch_ratio": .5, "roll_degrees": 0}}
    app.state.face_engine = FreshEngine()
    response = browser.post(f"/api/admin/employees/{target['id']}/collections", json={}, headers=headers)
    assert response.status_code == 201, response.text
    collection = response.json()
    assert collection["biometric_revision"] == 1
    assert browser.post(f"/api/admin/collections/{collection['id']}/samples", content=b"fresh", headers=headers).status_code == 201
    with factory() as db:
        assert db.get(FaceCollection, collection["id"]).biometric_revision == 1
