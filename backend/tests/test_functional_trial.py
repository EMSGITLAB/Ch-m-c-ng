"""Single-person automatic functional flow, distinct from production PAD approval."""

import hashlib
import io
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from app.config import get_settings
from app.functional_trial import MODE, SCOPE
from app.main import app
from app.models import AttendanceEvent, Device, Employee, FaceTemplate, RecognitionPolicy, RecognitionSession
from app.timesheet_exports import serialize_export
from app.timesheets import build_report
from openpyxl import load_workbook
from sqlalchemy import func, select
from test_attendance import attendance as attendance  # noqa: F401
from test_recognition_sequence import ROOT  # noqa: F401
from test_recognition_sequence import recognition as recognition


@pytest.fixture
def trial(recognition, monkeypatch):
    browser, factory, ids, clock, start, frame = recognition
    policy_id = "trial-functional-test"
    with factory() as db:
        old = db.get(RecognitionPolicy, ids[1])
        template = db.scalar(select(FaceTemplate).where(FaceTemplate.employee_id == ids[0]))
        db.add(RecognitionPolicy(id=policy_id, model_id=old.model_id, scoring_rule=old.scoring_rule,
                                 threshold=old.threshold, minimum_margin=0, enabled=True,
                                 mode=MODE, pad_verified=False, validated_at=old.validated_at,
                                 evidence={"scope": SCOPE, "sequence_protocol": "stable-three-v1",
                                           "participant_id": ids[0], "biometric_revision": 0,
                                           "template_id": template.id,
                                           "template_sha256": hashlib.sha256(template.vector).hexdigest()}))
        db.commit()
    monkeypatch.setattr(get_settings(), "functional_trial_enabled", True)
    monkeypatch.setattr(get_settings(), "functional_trial_policy_id", policy_id)
    app.state.attendance_policy_id = policy_id
    return browser, factory, ids, clock, start, frame


def test_one_person_three_frames_automatic_commit_receipt_retry_and_cooldown(trial):
    browser, factory, _, _, start, frame = trial
    status = browser.get("/api/system/status").json()
    assert status["attendance_enabled"] is True
    assert status["attendance_mode"] == MODE
    for attempt in range(2):
        session = start()
        for index in range(1, 4):
            response = frame(session, index, f"new-{attempt}-{index}".encode())
            assert response.status_code == 200, response.text
        result = response.json()
        assert result["state"] == "verified"
        assert result["needs_supervisor"] is False
        assert result["anti_spoof_verified"] is False
        assert browser.get(ROOT + "/sessions/" + session["request_id"]).json()["needs_supervisor"] is False
        endpoint = "/api/kiosk/attendance/" + session["request_id"] + "/commit"
        response = browser.post(endpoint, json={}, headers={"X-Kiosk-Intent": "record-attendance"})
        assert response.status_code == 200, response.text
        receipt = response.json()
        assert receipt["status"] == ("recorded" if attempt == 0 else "duplicate")
        assert receipt["recording_scope"] == "single_person_functional_trial"
        assert receipt["employee_code"] == "TEST"
        assert browser.post(endpoint, json={}, headers={"X-Kiosk-Intent": "record-attendance"}).json() == receipt
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 1


@pytest.mark.parametrize("fault", ["disabled", "wrong_selector", "purged", "inactive", "revision", "template", "scope"])
def test_trial_cannot_bypass_configuration_or_biometric_revocation(trial, monkeypatch, fault):
    browser, factory, ids, _, _, _ = trial
    with factory() as db:
        policy = db.get(RecognitionPolicy, app.state.attendance_policy_id)
        template = db.get(FaceTemplate, policy.evidence["template_id"])
        if fault == "disabled":
            monkeypatch.setattr(get_settings(), "functional_trial_enabled", False)
        elif fault == "wrong_selector":
            monkeypatch.setattr(get_settings(), "functional_trial_policy_id", "trial-other")
        elif fault == "purged":
            db.delete(template)
        elif fault == "inactive":
            db.get(Employee, ids[0]).active = False
        elif fault == "revision":
            db.get(Employee, ids[0]).biometric_revision = 1
        elif fault == "template":
            template.vector = bytes(len(template.vector))
        else:
            policy.evidence = policy.evidence | {"scope": "wrong"}
        db.commit()
    status = browser.get("/api/system/status").json()
    assert status["attendance_enabled"] is False
    response = browser.post(ROOT + "/sessions", json={"request_id": "10787818-f642-44d9-8231-88e1ac9d9090"},
                            headers={"X-Kiosk-Intent": "start-recognition"})
    assert response.status_code == 503


def test_unknown_face_does_not_record_in_single_person_trial(trial):
    _, factory, _, _, start, frame = trial
    session = start()
    for index in range(1, 4):
        response = frame(session, index, f"unknown-{index}".encode())
        assert response.json()["frame_accepted"] is False
    with factory() as db:
        assert db.get(RecognitionSession, session["request_id"]).state == "pending"
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 0


def test_in_out_trial_receipts_are_available_in_report_and_exports(trial):
    browser, factory, ids, clock, start, frame = trial
    for direction in ("in", "out"):
        with factory() as db:
            db.get(Device, ids[2][0]).direction = direction
            db.commit()
        session = start()
        for index in range(1, 4):
            assert frame(session, index, f"{direction}-{index}".encode()).json()["needs_supervisor"] is False
        response = browser.post("/api/kiosk/attendance/" + session["request_id"] + "/commit", json={},
                                headers={"X-Kiosk-Intent": "record-attendance"})
        assert response.status_code == 200, response.text
        assert response.json()["direction"] == direction
    # Frozen test clock, no claimed camera/model validation.
    with factory() as db:
        day = clock[0].astimezone(ZoneInfo("Asia/Ho_Chi_Minh")).date()
        report = build_report(db, day, day, ids[0], as_of=clock[0] + timedelta(seconds=1), unpaginated=True)
        assert report["source_event_count"] == 2
        assert report["functional_trial_event_count"] == 2
        assert len(report["unassigned_events"]) == 2
        assert {row["direction"] for row in report["unassigned_events"]} == {"in", "out"}
        report["finalized"] = False
        csv, _ = serialize_export(report, "csv")
        assert "Số lượt thử chức năng" in csv.decode("utf-8-sig")
        xlsx, _ = serialize_export(report, "xlsx")
        book = load_workbook(io.BytesIO(xlsx), read_only=True)
        assert next(row[1] for row in book["Thông tin"].values
                    if row[0] == "Số lượt thử chức năng") == 2
        book.close()


@pytest.mark.parametrize("fault", ["switch_off", "different_employee"])
def test_verification_cannot_bypass_trial_guard_at_commit(trial, monkeypatch, fault):
    browser, factory, _, _, start, frame = trial
    session = start()
    for index in range(1, 4):
        assert frame(session, index, f"capture-{index}".encode()).status_code == 200
    if fault == "switch_off":
        monkeypatch.setattr(get_settings(), "functional_trial_enabled", False)
    else:
        with factory() as db:
            other = db.scalar(select(Employee).where(Employee.code == "OTHER"))
            db.get(RecognitionSession, session["request_id"]).employee_id = other.id
            db.commit()
    response = browser.post("/api/kiosk/attendance/" + session["request_id"] + "/commit", json={},
                            headers={"X-Kiosk-Intent": "record-attendance"})
    assert response.status_code == (503 if fault == "switch_off" else 409), response.text
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 0
