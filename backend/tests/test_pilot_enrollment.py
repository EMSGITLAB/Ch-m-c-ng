"""Functional membership tests with synthetic vectors; never real-accuracy evidence."""

from datetime import UTC, datetime, timedelta

import numpy as np
from app.config import get_settings
from app.main import app
from app.models import (
    AttendanceEvent,
    CollectionSample,
    Employee,
    FaceCollection,
    FaceTemplate,
    RecognitionPolicy,
)
from app.pilot_gallery import pin
from app.policy_selection import PILOT_PREFIX, PILOT_SCOPE
from sqlalchemy import func, select
from test_admin import setup
from test_attendance import attendance as attendance  # noqa: F401
from test_functional_trial import trial as trial  # noqa: F401
from test_recognition_sequence import QUALITY
from test_recognition_sequence import recognition as recognition  # noqa: F401

ENDPOINT = "/api/admin/recognition/pilot/employees/"


def reference(factory, person_id=None, *, index=1, purpose="enrollment"):
    with factory() as db:
        if person_id is None:
            person = Employee(code=f"PILOT-{index}", name=f"Synthetic pilot fixture {index}")
            db.add(person)
            db.flush()
            person_id = person.id
        collection = FaceCollection(employee_id=person_id, model_id="m", purpose=purpose, status="complete",
            sample_count=1, guidance_protocol="imported-photo-v1", expires_at=datetime.now(UTC)+timedelta(minutes=5),
            completed_at=datetime.now(UTC))
        db.add(collection)
        db.flush()
        db.add(CollectionSample(collection_id=collection.id, position=1, fingerprint=f"{index:064x}", model_id="m",
            dimensions=128, vector=np.eye(128, dtype="<f4")[index].tobytes(), quality={"accepted": True}))
        db.commit()
        return person_id, collection.id


def publish(browser, person_id, csrf, *, remove=False, collection_id=None, policy_id=None):
    status = browser.get(ENDPOINT+person_id).json()
    return browser.post(ENDPOINT+person_id+("/remove" if remove else "/enroll"), headers={"X-CSRF-Token": csrf},
        json={"expected_revision": status["revision"],
              "expected_policy_id": policy_id or status["policy_id"], "collection_id": collection_id})


def test_admin_promotes_completed_reference_then_camera_chain_and_removes_without_restart(trial):
    browser, factory, ids, clock, start, frame = trial
    csrf = setup(browser)
    person_id, _ = reference(factory)
    old_session = start()
    response = publish(browser, person_id, csrf)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["participants"] == 2 and body["restart_required"] is False
    assert body["threshold_changed"] is False
    assert body["metrics"]["group_accuracy_validated"] is False
    clock[0] = datetime.now(UTC)
    assert frame(old_session, 1, b"old-session").status_code == 409
    status = browser.get("/api/system/status").json()
    assert status["attendance_enabled"] and status["pilot_people"] == 2
    clock[0] = datetime.now(UTC)
    session = start()
    for index in range(1, 4):
        captured = frame(session, index, f"other-new-{index}".encode())
        assert captured.status_code == 200, captured.text
    assert captured.json()["state"] == "verified"
    receipt = browser.post(f"/api/kiosk/attendance/{session['request_id']}/commit", json={},
                           headers={"X-Kiosk-Intent": "record-attendance"})
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["employee_code"] == "PILOT-1"
    assert receipt.json()["recording_scope"] == "local_functional_pilot"
    removed = publish(browser, person_id, csrf, remove=True)
    assert removed.status_code == 200 and removed.json()["participants"] == 1
    assert browser.get(ENDPOINT+person_id).json()["included"] is False
    assert browser.post(f"/api/kiosk/attendance/{session['request_id']}/commit", json={},
                        headers={"X-Kiosk-Intent": "record-attendance"}).json() == receipt.json()
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 1
        assert db.get(Employee, ids[0]).active


def test_reference_promotion_auth_csrf_revision_stale_policy_and_eval_isolation(trial):
    browser, factory, _, _, _, _ = trial
    person_id, evaluation = reference(factory, purpose="evaluation")
    assert browser.get(ENDPOINT+person_id).status_code == 401
    csrf = setup(browser)
    status = browser.get(ENDPOINT+person_id).json()
    endpoint = ENDPOINT+person_id+"/enroll"
    payload = {"expected_revision": 0, "expected_policy_id": status["policy_id"], "collection_id": evaluation}
    assert browser.post(endpoint, json=payload).status_code == 403
    assert browser.post(endpoint, json=payload, headers={"X-CSRF-Token": csrf}).status_code == 409
    payload["threshold"] = 0.1
    assert browser.post(endpoint, json=payload, headers={"X-CSRF-Token": csrf}).status_code == 422
    reference(factory, person_id, index=2)
    assert publish(browser, person_id, csrf, policy_id="stale-policy").status_code == 409
    response = browser.post(endpoint, json={"expected_revision": 1, "expected_policy_id": status["policy_id"]},
                            headers={"X-CSRF-Token": csrf})
    assert response.status_code == 409
    assert browser.get("/api/system/status").json()["pilot_people"] == 1


def test_duplicate_people_block_new_revision_atomically(trial):
    browser, factory, ids, _, _, _ = trial
    csrf = setup(browser)
    person_id, collection_id = reference(factory)
    with factory() as db:
        sample = db.scalar(select(CollectionSample).where(CollectionSample.collection_id == collection_id))
        sample.vector = np.eye(128, dtype="<f4")[0].tobytes()
        db.commit()
    before = browser.get(ENDPOINT+person_id).json()["policy_id"]
    assert publish(browser, person_id, csrf).status_code == 409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(FaceTemplate).where(FaceTemplate.employee_id == person_id)) == 0
        assert db.get(RecognitionPolicy, before).enabled
        assert db.get(Employee, ids[0]).active


def test_existing_independent_control_must_still_match_after_membership_change(trial):
    browser, factory, ids, _, _, _ = trial
    csrf = setup(browser)
    person_id, reference_id = reference(factory)
    _, probe_id = reference(factory, ids[0], index=77, purpose="calibration")
    with factory() as db:
        candidate = db.scalar(select(CollectionSample).where(CollectionSample.collection_id == reference_id))
        candidate.vector = np.asarray([.9, (.19 ** .5)]+[0]*126, dtype="<f4").tobytes()
        control = db.scalar(select(CollectionSample).where(CollectionSample.collection_id == probe_id))
        control.vector = np.asarray([.8, .6]+[0]*126, dtype="<f4").tobytes()
        db.commit()
    before = browser.get(ENDPOINT+person_id).json()["policy_id"]
    response = publish(browser, person_id, csrf)
    assert response.status_code == 409 and "ảnh hiệu chỉnh" in response.json()["detail"]
    assert browser.get(ENDPOINT+person_id).json()["policy_id"] == before
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(FaceTemplate).where(FaceTemplate.employee_id == person_id)) == 0


def test_deactivation_excludes_only_that_person_and_last_removal_can_resume(trial):
    browser, factory, ids, _, _, _ = trial
    csrf = setup(browser)
    person_id, _ = reference(factory)
    assert publish(browser, person_id, csrf).status_code == 200
    with factory() as db:
        db.get(Employee, person_id).active = False
        db.commit()
    status = browser.get("/api/system/status").json()
    assert status["attendance_enabled"] and status["pilot_people"] == 1
    assert publish(browser, ids[0], csrf, remove=True).status_code == 200
    assert browser.get("/api/system/status").json()["attendance_enabled"] is False
    reference(factory, ids[0], index=0)
    response = publish(browser, ids[0], csrf)
    assert response.status_code == 200, response.text
    assert browser.get("/api/system/status").json()["attendance_enabled"] is True


def test_after_restore_admin_can_republish_saved_trial_without_restoring_old_access(trial, monkeypatch):
    browser, factory, ids, _, _, _ = trial
    csrf = setup(browser)
    reference(factory, ids[0], index=0)
    with factory() as db:
        db.get(RecognitionPolicy, app.state.attendance_policy_id).enabled = False
        db.commit()
    monkeypatch.setattr(app.state, "attendance_policy_id", None)
    monkeypatch.setattr(get_settings(), "functional_trial_enabled", False)
    assert browser.get("/api/system/status").json()["attendance_enabled"] is False
    status = browser.get(ENDPOINT+ids[0]).json()
    assert status["policy_id"] and not status["enabled"]
    response = publish(browser, ids[0], csrf)
    assert response.status_code == 200, response.text
    assert response.json()["threshold_changed"] is False
    assert browser.get("/api/system/status").json()["attendance_enabled"] is True


def test_hundred_person_catalog_and_publishing_hundredth_keeps_threshold(trial, monkeypatch):
    browser, factory, ids, clock, start, frame = trial
    csrf = setup(browser)
    pins = []
    with factory() as db:
        source = db.get(RecognitionPolicy, app.state.attendance_policy_id)
        pins.append(pin(db.get(FaceTemplate, source.evidence["template_id"])))
        for index in range(1, 99):
            person = Employee(code=f"LOAD-{index}", name=f"Synthetic fixture {index}")
            db.add(person)
            db.flush()
            template = FaceTemplate(employee_id=person.id, model_id="m", dimensions=128,
                                    vector=np.eye(128, dtype="<f4")[index].tobytes())
            db.add(template)
            db.flush()
            pins.append(pin(template))
        source.enabled = False
        db.add(RecognitionPolicy(id=PILOT_PREFIX+"hundred-fixture", model_id="m", scoring_rule=source.scoring_rule,
            threshold=source.threshold, minimum_margin=source.minimum_margin, enabled=True, mode="functional_trial",
            pad_verified=False, validated_at=datetime.now(UTC), evidence={"scope": PILOT_SCOPE,
            "sequence_protocol": "stable-three-v1", "templates": pins, "synthetic_vectors_only": True}))
        db.commit()
    person_id, _ = reference(factory, index=99)
    response = publish(browser, person_id, csrf)
    assert response.status_code == 200, response.text
    assert response.json()["participants"] == 100 and response.json()["threshold_changed"] is False
    assert browser.get("/api/system/status").json()["pilot_people"] == 100
    assert browser.get(ENDPOINT+ids[0]).json()["included"] is True
    assert "template_sha256" not in response.text and "vector" not in response.text

    class IndexedEngine:
        model_id = "m"
        dimensions = 128

        def analyze(self, content):
            index = int(content.decode().split("-")[1])
            return np.eye(128, dtype="<f4")[index], {"quality": QUALITY}

    monkeypatch.setattr(app.state, "face_engine", IndexedEngine())
    clock[0] = datetime.now(UTC)
    event_ids = set()
    for person in range(100):
        session = start()
        for index in range(1, 4):
            response = frame(session, index, f"load-{person}-{index}".encode())
            assert response.status_code == 200 and response.json()["anti_spoof_verified"] is False
        assert response.json()["state"] == "verified"
        receipt = browser.post(f"/api/kiosk/attendance/{session['request_id']}/commit", json={},
                               headers={"X-Kiosk-Intent": "record-attendance"})
        assert receipt.status_code == 200, receipt.text
        expected = "TEST" if person == 0 else "PILOT-99" if person == 99 else f"LOAD-{person}"
        assert receipt.json()["employee_code"] == expected
        event_ids.add(receipt.json()["event_id"])
    assert len(event_ids) == 100
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 100
