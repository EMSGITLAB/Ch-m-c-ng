"""Real API contracts for the Gemini UI, with isolated synthetic attendance only."""
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from app.devices import KIOSK_COOKIE
from app.models import AttendanceEvent, AuditLog, Device, Employee, RecognitionSession
from fastapi import HTTPException
from sqlalchemy import func, select
from test_admin import setup
from test_attendance import attendance as attendance  # noqa: F401
from test_functional_trial import trial as trial  # noqa: F401
from test_recognition_sequence import recognition as recognition  # noqa: F401


def test_overview_uses_full_roster_local_day_and_live_device_state(attendance):
    browser, factory, now, ids, _, _ = attendance
    assert browser.get("/api/admin/dashboard").status_code == 401
    setup(browser)
    zone = ZoneInfo("Asia/Ho_Chi_Minh")
    start = datetime.combine(now.astimezone(zone).date(), time(), zone).astimezone(UTC)
    with factory() as db:
        for index in range(35):
            db.add(Employee(code=f"DASH-{index}", name=f"Synthetic dashboard {index}", active=index != 0))
        for index, at in enumerate([start-timedelta(seconds=1), start, now, start+timedelta(days=1)]):
            db.add(AttendanceEvent(employee_id=ids[0], device_id=ids[2][0], request_id=f"dashboard-{index}",
                direction="in", server_time=at, recognition_version="synthetic-dashboard-only"))
        db.get(Device, ids[2][0]).last_seen_at = now
        db.get(Device, ids[2][1]).last_seen_at = now-timedelta(minutes=5)
        db.commit()
    response = browser.get("/api/admin/dashboard")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["employee_total"] == 36 and body["employee_active"] == 35
    assert body["attendance_today"] == 2 and len(body["recent"]) == 2
    assert body["paired_devices"] == 2 and body["online_devices"] == 1
    assert body["recent"][0]["employee_code"] == "TEST"
    assert datetime.fromisoformat(body["recent"][0]["occurred_at"]).tzinfo is not None
    assert "token_hash" not in response.text and "vector" not in response.text


def test_direction_change_uses_paired_device_intent_and_never_modifies_used_receipt(attendance):
    browser, factory, _, ids, session, record = attendance
    assert browser.patch("/api/kiosk/device", json={"direction": "out"}).status_code == 401
    browser.cookies.set(KIOSK_COOKIE, "test-kiosk-0")
    assert browser.patch("/api/kiosk/device", json={"direction": "out"}).status_code == 403
    headers = {"X-Kiosk-Intent": "change-direction"}
    assert browser.patch("/api/kiosk/device", json={"direction": "wrong"}, headers=headers).status_code == 422
    assert browser.patch("/api/kiosk/device", json={"direction": "out"}, headers=headers | {"Origin":"https://foreign.invalid"}).status_code == 403
    pending, verified, other, saved = session(state="pending"), session(), session(device=1), session()
    receipt = record(saved)
    changed = browser.patch("/api/kiosk/device", json={"direction": "out"}, headers=headers)
    assert changed.status_code == 200, changed.text
    assert changed.json()["direction"] == "out" and changed.json()["paired"]
    assert record(saved) == receipt  # retries remain identical after switching direction
    with pytest.raises(HTTPException):
        record(verified)
    with factory() as db:
        assert db.get(RecognitionSession, pending).state == "rejected"
        assert db.get(RecognitionSession, verified).state == "rejected"
        assert db.get(RecognitionSession, other).state == "verified"
        assert db.get(RecognitionSession, saved).state == "used"
        assert db.get(Device, ids[2][1]).direction == "in"
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 1
    same = browser.patch("/api/kiosk/device", json={"direction": "out"}, headers=headers)
    assert same.status_code == 200
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "kiosk_direction_changed")) == 1
        db.get(Device, ids[2][0]).active = False
        db.commit()
    assert browser.patch("/api/kiosk/device", json={"direction": "in"}, headers=headers).status_code == 401


def test_same_direction_preserves_recognition(attendance):
    browser, factory, _, _, session, _ = attendance
    browser.cookies.set(KIOSK_COOKIE, "test-kiosk-0")
    request_id = session()
    assert browser.patch("/api/kiosk/device", json={"direction": "in"},
        headers={"X-Kiosk-Intent":"change-direction"}).status_code == 200
    with factory() as db:
        assert db.get(RecognitionSession, request_id).state == "verified"


def test_changed_direction_is_used_by_fresh_recognition_and_real_commit(trial):
    browser, _factory, _ids, _clock, start, frame = trial
    response = browser.patch("/api/kiosk/device", json={"direction":"out"},
                             headers={"X-Kiosk-Intent":"change-direction"})
    assert response.status_code == 200, response.text
    session = start()
    for index in range(1,4):
        response = frame(session,index,f"direction-out-frame-{index}".encode())
        assert response.status_code == 200, response.text
    assert response.json()["state"] == "verified"
    receipt = browser.post(f"/api/kiosk/attendance/{session['request_id']}/commit", json={},
                           headers={"X-Kiosk-Intent":"record-attendance"})
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["direction"] == "out"
