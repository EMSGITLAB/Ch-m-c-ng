import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from uuid import uuid4

import numpy as np
import pytest
from app import attendance_api, recognition_api
from app import recognition_sequence as sequence
from app.attendance import commit_recognition
from app.devices import KIOSK_COOKIE
from app.face_engine import FaceInputError
from app.main import app
from app.models import (
    AttendanceEvent,
    Employee,
    FaceTemplate,
    RecognitionFrame,
    RecognitionPolicy,
    RecognitionSession,
)
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError
from test_admin import setup
from test_attendance import attendance as attendance

ROOT = "/api/kiosk/recognition"
QUALITY = {
    "accepted": True,
    "reason": "accepted",
    "frame_width": 960,
    "frame_height": 720,
    "box": [330, 170, 300, 340],
    "yaw_ratio": 0,
    "pitch_ratio": 0.5,
}


class Engine:
    model_id = "m"
    dimensions = 128

    def analyze(self, content):
        if content == b"no-face":
            raise FaceInputError("no_face")
        person = 1 if content.startswith(b"other") else 2 if content.startswith(b"unknown") else 0
        return np.eye(128, dtype="<f4")[person], {"quality": QUALITY}

    def inspect(self, content):
        _, metadata = self.analyze(content)
        return None, None, metadata


@pytest.fixture
def recognition(attendance, monkeypatch):
    browser, factory, now, ids, _, _ = attendance
    with factory() as db:
        policy = db.get(RecognitionPolicy, ids[1])
        policy.mode = "supervised"
        policy.evidence = {"synthetic_test_only": True, "sequence_protocol": sequence.PROTOCOL}
        other = Employee(code="OTHER", name="Hồ sơ thử thứ hai")
        db.add(other)
        db.flush()
        for person, identity in enumerate([ids[0], other.id]):
            for _ in range(3):
                db.add(
                    FaceTemplate(
                        employee_id=identity,
                        model_id="m",
                        dimensions=128,
                        vector=np.eye(128, dtype="<f4")[person].tobytes(),
                    )
                )
        db.commit()
    clock = [now]
    monkeypatch.setattr(sequence, "utcnow", lambda: clock[0])
    monkeypatch.setattr(
        attendance_api, "commit_recognition", lambda *args: commit_recognition(*args, clock=lambda: clock[0])
    )
    before = app.state.face_engine
    app.state.face_engine = Engine()
    app.state.attendance_policy_id = ids[1]
    browser.cookies.set(KIOSK_COOKIE, "test-kiosk-0")

    def start(identity=None):
        response = browser.post(
            ROOT + "/sessions",
            json={"request_id": identity or str(uuid4())},
            headers={"X-Kiosk-Intent": "start-recognition"},
        )
        assert response.status_code == 201, response.text
        return response.json()

    def frame(session, index, content):
        clock[0] += timedelta(seconds=0.5)
        return browser.post(
            f"{ROOT}/sessions/{session['request_id']}/frames/{index}",
            content=content,
            headers={
                "X-Kiosk-Intent": "capture-recognition",
                "X-Capture-Nonce": session["capture_nonce"],
                "Content-Type": "image/jpeg",
            },
        )

    try:
        yield browser, factory, ids, clock, start, frame
    finally:
        app.state.face_engine = before
        app.state.attendance_policy_id = None


def test_three_frames_require_explicit_supervisor_before_atomic_commit_and_retry(recognition):
    browser, factory, ids, _, start, frame = recognition
    session = start()
    assert start(session["request_id"]) == session
    for index in range(1, 4):
        response = frame(session, index, f"face-{index}".encode())
        assert response.status_code == 200, response.text
        assert response.json()["attendance_recorded"] is False
    assert response.json()["state"] == "verified"
    assert response.json()["anti_spoof_verified"] is False
    assert "employee_name" not in response.json()
    request_id = session["request_id"]
    endpoint = f"/api/kiosk/attendance/{request_id}/commit"
    headers = {"X-Kiosk-Intent": "record-attendance"}
    assert browser.post(endpoint, json={}, headers=headers).status_code == 409
    csrf = {"X-CSRF-Token": setup(browser)}
    pending = browser.get("/api/admin/recognition/pending").json()
    assert pending["items"][0]["request_id"] == request_id
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 0
        code = db.get(Employee, ids[0]).code
    confirm = f"/api/admin/recognition/sessions/{request_id}/confirm"
    assert (
        browser.post(
            confirm,
            json={"confirm_employee_code": "WRONG", "reason": "Đối chiếu người tại kiosk"},
            headers=csrf,
        ).status_code
        == 409
    )
    assert (
        browser.post(
            confirm, json={"confirm_employee_code": code, "reason": "Đối chiếu người tại kiosk"}, headers=csrf
        ).status_code
        == 200
    )
    recorded = browser.post(endpoint, json={}, headers=headers)
    assert recorded.status_code == 200 and recorded.json()["status"] == "recorded"
    assert browser.post(endpoint, json={}, headers=headers).json() == recorded.json()
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 1
        assert db.scalar(select(func.count()).select_from(RecognitionFrame)) == 3


def test_unknown_bad_quality_replay_and_wrong_order_never_verify(recognition):
    browser, factory, _, _, start, frame = recognition
    session = start()
    assert frame(session, 2, b"face-wrong-order").status_code == 409
    assert frame(session, 1, b"no-face").json()["stable_frames"] == 0
    assert frame(session, 2, b"unknown-face").json()["stable_frames"] == 0
    first = frame(session, 3, b"face-same")
    assert first.json()["stable_frames"] == 1
    assert frame(session, 3, b"face-same").json() == first.json()
    assert frame(session, 3, b"face-different").status_code == 409
    assert frame(session, 4, b"face-same").json()["stable_frames"] == 0
    with factory() as db:
        assert db.get(RecognitionSession, session["request_id"]).state == "pending"
        assert db.scalar(select(func.count()).select_from(RecognitionFrame)) == 4
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 0
    assert browser.get(ROOT + f"/sessions/{session['request_id']}").json()["next_frame_index"] == 5


def test_face_switch_rejects_whole_session(recognition):
    _, factory, _, _, start, frame = recognition
    session = start()
    assert frame(session, 1, b"face-a").json()["frame_accepted"]
    assert frame(session, 2, b"other-b").json()["state"] == "rejected"
    assert frame(session, 3, b"face-c").status_code == 409
    with factory() as db:
        assert db.get(RecognitionSession, session["request_id"]).employee_id is None


def test_binding_expiry_auth_and_unverified_automatic_policy(recognition):
    browser, factory, ids, clock, start, frame = recognition
    session = start()
    endpoint = f"{ROOT}/sessions/{session['request_id']}/frames/1"
    assert (
        browser.post(
            endpoint,
            content=b"face-a",
            headers={"X-Kiosk-Intent": "capture-recognition", "X-Capture-Nonce": "0" * 64},
        ).status_code
        == 403
    )
    browser.cookies.set(KIOSK_COOKIE, "test-kiosk-1")
    assert browser.get(ROOT + f"/sessions/{session['request_id']}").status_code == 404
    browser.cookies.set(KIOSK_COOKIE, "test-kiosk-0")
    clock[0] += timedelta(seconds=21)
    assert frame(session, 1, b"face-a").status_code == 410
    with factory() as db:
        db.get(RecognitionPolicy, ids[1]).mode = "automatic"
        db.commit()
    denied = browser.post(
        ROOT + "/sessions", json={"request_id": str(uuid4())}, headers={"X-Kiosk-Intent": "start-recognition"}
    )
    assert denied.status_code == 503  # A PAD flag is not a real, per-session PAD check.
    browser.cookies.clear()
    assert (
        browser.post(
            ROOT + "/sessions",
            json={"request_id": str(uuid4())},
            headers={"X-Kiosk-Intent": "start-recognition"},
        ).status_code
        == 401
    )


def test_deactivated_candidate_cannot_continue_chain_and_preview_does_not_store_frames(recognition):
    browser, factory, ids, _, start, frame = recognition
    preview = browser.post(
        ROOT + "/preview", content=b"face-a", headers={"X-Kiosk-Intent": "preview-recognition"}
    )
    assert preview.status_code == 200 and preview.json()["ready"]
    session = start()
    assert frame(session, 1, b"face-a").json()["frame_accepted"]
    csrf = {"X-CSRF-Token": setup(browser)}
    assert (
        browser.patch(f"/api/admin/employees/{ids[0]}", json={"active": False}, headers=csrf).status_code
        == 200
    )
    assert frame(session, 2, b"face-b").json()["frame_accepted"] is False
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(RecognitionFrame)) == 2


def test_readiness_uses_server_policy_and_eligible_gallery_not_a_flag(recognition):
    browser, factory, ids, _, _, _ = recognition
    status = browser.get("/api/system/status").json()
    assert status["attendance_enabled"] and status["attendance_mode"] == "supervised"
    with factory() as db:
        db.get(RecognitionPolicy, ids[1]).mode = "automatic"
        db.commit()
    assert browser.get("/api/system/status").json()["attendance_enabled"] is False


def test_preview_tracks_without_active_policy_but_cannot_start_attendance(recognition, monkeypatch):
    browser, factory, _, _, _, _ = recognition
    monkeypatch.setattr(app.state, "attendance_policy_id", None)
    monkeypatch.setitem(QUALITY, "frame_width", 1280)
    monkeypatch.setitem(QUALITY, "box", [25, 180, 150, 200])
    response = browser.post(ROOT + "/preview", content=b"face",
                            headers={"X-Kiosk-Intent": "preview-recognition"})
    assert response.status_code == 200
    assert response.json()["ready"]
    assert response.json()["face_box"] == pytest.approx([25/1280, 180/720, 150/1280, 200/720])
    assert not response.json()["attendance_recorded"]
    assert browser.post(ROOT + "/sessions", json={"request_id": str(uuid4())},
                        headers={"X-Kiosk-Intent": "start-recognition"}).status_code == 503
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(RecognitionFrame)) == 0
        assert db.scalar(select(func.count()).select_from(RecognitionSession)) == 0
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 0


def test_response_lost_after_frame_commit_can_recover_without_double_count(recognition, monkeypatch):
    browser, factory, _, _, start, frame = recognition
    session = start()
    original = recognition_api.append_frame

    def lose_response(*args):
        original(*args)
        raise OperationalError("simulated response lost", {}, Exception("test-only disconnect"))

    monkeypatch.setattr(recognition_api, "append_frame", lose_response)
    assert frame(session, 1, b"face-a").status_code == 503
    state = browser.get(ROOT + f"/sessions/{session['request_id']}")
    assert state.status_code == 200 and state.json()["next_frame_index"] == 2
    monkeypatch.setattr(recognition_api, "append_frame", original)
    retried = frame(session, 1, b"face-a")
    assert retried.status_code == 200 and retried.json()["stable_frames"] == 1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(RecognitionFrame)) == 1
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 0


def test_inference_preflight_cache_is_refreshed_after_waiting_for_previous_frame(recognition):
    _, factory, ids, clock, start, _ = recognition
    session = start()
    vector = np.eye(128, dtype="<f4")[0]
    with factory() as stale:
        cached = sequence.owned_session(stale, session["request_id"], ids[2][0], ids[3][0], clock[0])
        assert cached.last_frame_index == 0
        with factory() as fresh:
            sequence.append_frame(
                fresh, session["request_id"], 1, ids[2][0], ids[3][0], ids[1], "m", "a" * 64, vector, QUALITY
            )
        clock[0] += timedelta(seconds=0.5)
        result = sequence.append_frame(
            stale, session["request_id"], 2, ids[2][0], ids[3][0], ids[1], "m", "b" * 64, vector, QUALITY
        )
        assert result["next_frame_index"] == 3 and result["stable_frames"] == 2


@pytest.mark.skipif(
    not os.environ.get("CHAMCONG_TEST_DATABASE_URL"), reason="Requires independent SQL Server transactions"
)
def test_native_same_frame_concurrency_is_idempotent(recognition):
    _, factory, ids, clock, start, _ = recognition
    session = start()
    barrier = Barrier(2)
    vector = np.eye(128, dtype="<f4")[0]

    def worker():
        with factory() as db:
            db.execute(text("SET LOCK_TIMEOUT 5000"))
            barrier.wait(timeout=10)
            return sequence.append_frame(
                db, session["request_id"], 1, ids[2][0], ids[3][0], ids[1], "m", "a" * 64, vector, QUALITY
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(worker), pool.submit(worker)
        assert first.result(timeout=20) == second.result(timeout=20)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(RecognitionFrame)) == 1


@pytest.mark.parametrize("operation", ["preview", "frame", "commit"])
def test_waiting_database_preflight_does_not_block_server_liveness(recognition, monkeypatch, operation):
    browser, _, _, _, start, _ = recognition
    session = start()
    entered, release = Event(), Event()
    module = attendance_api if operation == "commit" else recognition_api
    name = "selected_policy" if operation == "commit" else "context"
    original = getattr(module, name)

    def delayed(*args, **kwargs):
        entered.set()
        if not release.wait(timeout=10):
            raise RuntimeError("Test preflight gate was not released")
        return original(*args, **kwargs)

    monkeypatch.setattr(module, name, delayed)

    def request():
        if operation == "commit":
            return browser.post(f"/api/kiosk/attendance/{session['request_id']}/commit", json={},
                                headers={"X-Kiosk-Intent": "record-attendance"})
        path = ROOT + ("/preview" if operation == "preview" else f"/sessions/{session['request_id']}/frames/1")
        return browser.post(path, content=b"valid-test-frame", headers={
            "Content-Type": "image/jpeg", "X-Capture-Nonce": session["capture_nonce"],
            "X-Kiosk-Intent": "preview-recognition" if operation == "preview" else "capture-recognition"})

    with ThreadPoolExecutor(max_workers=2) as pool:
        waiting = pool.submit(request)
        try:
            assert entered.wait(timeout=5)
            live = pool.submit(browser.get, "/health/live")
            assert live.result(timeout=2).status_code == 200
            assert not waiting.done()
        finally:
            release.set()
        response = waiting.result(timeout=5)
        assert response.status_code == (409 if operation == "commit" else 200)


def test_stability_uses_server_receive_times_despite_variable_inference_latency(recognition):
    _, factory, ids, clock, start, _ = recognition
    session = start()
    begin = clock[0]
    vector = np.eye(128, dtype="<f4")[0]
    for index, received, processed in [(1, .1, .6), (2, .6, .9), (3, 1.1, 1.2)]:
        clock[0] = begin + timedelta(seconds=processed)
        with factory() as db:
            result = sequence.append_frame(db, session["request_id"], index, ids[2][0], ids[3][0], ids[1],
                "m", str(index)*64, vector, QUALITY, begin+timedelta(seconds=received))
    assert result["state"] == "verified" and result["stable_frames"] == 3
    with factory() as db:
        frames = db.scalars(select(RecognitionFrame).where(
            RecognitionFrame.request_id == session["request_id"]).order_by(RecognitionFrame.position)).all()
        assert sequence.aware(frames[-1].created_at)-sequence.aware(frames[0].created_at) == timedelta(seconds=1)


def test_server_receive_time_cannot_bypass_spacing_expiry_or_challenge_time(recognition):
    _, factory, ids, clock, start, _ = recognition
    session = start()
    begin = clock[0]
    vector = np.eye(128, dtype="<f4")[0]

    def append(index, received):
        with factory() as db:
            return sequence.append_frame(db, session["request_id"], index, ids[2][0], ids[3][0], ids[1],
                "m", str(index)*64, vector, QUALITY, begin+timedelta(seconds=received))

    clock[0] = begin+timedelta(seconds=.6)
    assert append(1, .1)["frame_accepted"]
    clock[0] = begin+timedelta(seconds=1.5)
    with pytest.raises(HTTPException) as too_fast:
        append(2, .2)
    assert too_fast.value.status_code == 429
    for invalid in (-1, 2):
        with pytest.raises(HTTPException) as invalid_time:
            append(2, invalid)
        assert invalid_time.value.status_code == 503
    clock[0] = begin+timedelta(seconds=21)
    with pytest.raises(HTTPException) as expired:
        append(2, 1.1)
    assert expired.value.status_code == 410


def test_frame_api_stamps_receive_time_but_checks_expiry_after_inference(recognition, monkeypatch):
    _, factory, _, clock, start, frame = recognition
    session = start()
    begin = clock[0]
    original = app.state.face_engine.analyze
    delay = [timedelta(seconds=.4)]

    def analyze(content):
        clock[0] += delay[0]
        return original(content)

    monkeypatch.setattr(app.state.face_engine, "analyze", analyze)
    assert frame(session, 1, b"first-frame").status_code == 200
    with factory() as db:
        row = db.get(RecognitionFrame, (session["request_id"], 1))
        assert sequence.aware(row.created_at) == begin+timedelta(seconds=.5)
    delay[0] = timedelta(seconds=21)
    assert frame(session, 2, b"second-frame").status_code == 410
    with factory() as db:
        assert db.get(RecognitionFrame, (session["request_id"], 2)) is None
