import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app import attendance_api
from app.attendance import commit_recognition
from app.devices import KIOSK_COOKIE
from app.main import app
from app.matching import SCORING_RULE
from app.models import AttendanceEvent, AuditLog, Device, Employee, RecognitionPolicy, RecognitionSession
from fastapi import HTTPException
from sqlalchemy import event, func, select, text, update
from sqlalchemy.exc import OperationalError


@pytest.fixture
def attendance(client):
    browser, factory = client
    now = datetime.now(UTC)
    with factory() as db:
        employee = Employee(code="TEST", name="Tên khi ghi công")
        policy = RecognitionPolicy(
            id="a" * 64,
            model_id="m",
            scoring_rule=SCORING_RULE,
            threshold=0.6,
            minimum_margin=0.1,
            enabled=True,
            mode="automatic",
            pad_verified=True,
            validated_at=now - timedelta(minutes=1),
            evidence={"synthetic_test_only": True, "real_accuracy_or_pad_validation": False},
        )
        devices = [
            Device(
                name=f"Test {number}",
                direction="in",
                active=True,
                token_hash=hashlib.sha256(f"test-kiosk-{number}".encode()).hexdigest(),
                token_expires_at=now + timedelta(hours=1),
            )
            for number in range(2)
        ]
        db.add_all([employee, policy, *devices])
        db.commit()
        ids = (
            employee.id,
            policy.id,
            [device.id for device in devices],
            [device.token_hash for device in devices],
        )

    def session(device=0, state="verified", direction="in"):
        with factory() as db:
            row = RecognitionSession(
                device_id=ids[2][device],
                policy_id=ids[1],
                direction=direction,
                state=state,
                employee_id=ids[0] if state == "verified" else None,
                biometric_revision=0 if state == "verified" else None,
                verified_model_id="m" if state == "verified" else None,
                expires_at=now + timedelta(minutes=2),
            )
            db.add(row)
            db.commit()
            return row.request_id

    def record(request, device=0, at=None):
        with factory() as db:
            return commit_recognition(
                db, request, ids[2][device], ids[3][device], ids[1], "m", 60, clock=lambda: at or now
            )

    return browser, factory, now, ids, session, record


def test_retry_is_identical_after_response_loss_profile_edit_expiry_and_policy_retirement(attendance):
    _, factory, now, ids, session, record = attendance
    request = session()
    first = record(request)
    assert first["status"] == "recorded"
    assert datetime.fromisoformat(first["server_time"]) == now
    with factory() as db:
        db.get(Employee, ids[0]).name = "Tên đã đổi"
        db.get(RecognitionPolicy, ids[1]).enabled = False
        db.get(RecognitionSession, request).expires_at = now - timedelta(seconds=1)
        db.commit()
    assert record(request) == first
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 1
        assert (
            db.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.action == "attendance_recorded")
            )
            == 1
        )


def test_cross_device_rescan_beyond_old_cooldown_preserves_original_event(attendance):
    _, factory, now, ids, session, record = attendance
    first = record(session())
    with factory() as db:
        db.get(Employee, ids[0]).name = "Tên mới"
        db.commit()
    request = session(device=1)
    duplicate = record(request, device=1, at=now + timedelta(seconds=59.9))
    assert duplicate["status"] == "duplicate"
    assert duplicate["event_id"] == first["event_id"]
    assert duplicate["employee_name"] == first["employee_name"]
    assert duplicate["server_time"] == first["server_time"]
    assert record(request, device=1) == duplicate
    boundary = record(session(device=1), device=1, at=now + timedelta(seconds=60))
    assert boundary["status"] == "duplicate"
    assert boundary["event_id"] == first["event_id"]
    assert boundary["attendance_scope"]["type"] == "workday"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 1


@pytest.mark.parametrize(
    "change,expected",
    [
        ("inactive", 409),
        ("revision", 409),
        ("expired", 409),
        ("revoked", 401),
        ("rotated", 401),
        ("policy_off", 503),
        ("model", 409),
        ("direction", 409),
        ("unverified", 409),
        ("supervised", 409),
    ],
)
def test_invalid_server_decision_never_records(attendance, change, expected):
    _, factory, now, ids, session, record = attendance
    request = session(state="pending" if change == "unverified" else "verified")
    with factory() as db:
        if change == "inactive":
            db.get(Employee, ids[0]).active = False
        if change == "revision":
            db.get(Employee, ids[0]).biometric_revision = 1
        if change == "expired":
            db.get(RecognitionSession, request).expires_at = now - timedelta(seconds=1)
        if change == "revoked":
            db.get(Device, ids[2][0]).active = False
        if change == "rotated":
            db.get(Device, ids[2][0]).token_hash = "replacement"
        if change == "policy_off":
            db.get(RecognitionPolicy, ids[1]).enabled = False
        if change == "model":
            db.get(RecognitionSession, request).verified_model_id = "old"
        if change == "direction":
            db.get(Device, ids[2][0]).direction = "out"
        if change == "supervised":
            db.get(RecognitionPolicy, ids[1]).mode = "supervised"
        db.commit()
    with pytest.raises(HTTPException) as error:
        record(request)
    assert error.value.status_code == expected
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 0
        assert db.get(RecognitionSession, request).receipt is None


def test_in_and_out_are_independent_and_clock_regression_is_not_success(attendance):
    _, factory, now, ids, session, record = attendance
    record(session())
    with factory() as db:
        db.get(Device, ids[2][1]).direction = "out"
        db.commit()
    assert record(session(device=1, direction="out"), device=1)["status"] == "recorded"
    with pytest.raises(HTTPException) as error:
        record(session(), at=now - timedelta(seconds=1))
    assert error.value.status_code == 503


def test_delete_preserves_original_punch_and_blocks_pending_recognition(attendance):
    from test_admin import setup

    browser, factory, _, ids, session, record = attendance
    first = record(session())
    pending = session()
    headers = {"X-CSRF-Token": setup(browser)}
    assert browser.delete("/api/admin/employees/"+ids[0], headers=headers).status_code == 200
    with pytest.raises(HTTPException) as error:
        record(pending)
    assert error.value.status_code == 409
    with factory() as db:
        original = db.get(AttendanceEvent, first["event_id"])
        assert original.employee_id == ids[0]
        assert original.server_time.isoformat().startswith(first["server_time"][:19])
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 1


def test_failure_rolls_back_event_receipt_and_audit_together(attendance):
    _, factory, _, _, session, record = attendance
    request = session()

    def reject(mapper, connection, row):
        if row.action == "attendance_recorded":
            raise RuntimeError("test audit failure")

    event.listen(AuditLog, "before_insert", reject)
    try:
        with pytest.raises(RuntimeError, match="test audit failure"):
            record(request)
    finally:
        event.remove(AuditLog, "before_insert", reject)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 0
        assert db.get(RecognitionSession, request).state == "verified"
        assert db.get(RecognitionSession, request).receipt is None


def test_kiosk_api_is_disabled_by_default_rejects_client_identity_and_scopes_receipts(attendance):
    browser, factory, _, ids, session, record = attendance
    request = session()
    endpoint = f"/api/kiosk/attendance/{request}"
    assert browser.get(endpoint).status_code == 401
    browser.cookies.set(KIOSK_COOKIE, "test-kiosk-0")
    assert browser.get(endpoint).status_code == 202
    headers = {"X-Kiosk-Intent": "record-attendance"}
    assert browser.post(endpoint + "/commit", json={}).status_code == 403
    assert (
        browser.post(endpoint + "/commit", json={"employee_id": ids[0]}, headers=headers).status_code == 422
    )
    assert browser.post(endpoint + "/commit", json={}, headers=headers).status_code == 503
    original_engine = app.state.face_engine
    try:
        app.state.attendance_policy_id = ids[1]
        app.state.face_engine = SimpleNamespace(model_id="m")
        assert (
            browser.post(
                endpoint + "/commit", json={}, headers=headers | {"Origin": "https://outside.invalid"}
            ).status_code
            == 403
        )
        response = browser.post(endpoint + "/commit", json={}, headers=headers)
        assert response.status_code == 200, response.text
        assert browser.get(endpoint).json() == response.json()
        assert browser.post(endpoint + "/commit", json={}, headers=headers).json() == response.json()
    finally:
        app.state.attendance_policy_id = None
        app.state.face_engine = original_engine
    browser.cookies.set(KIOSK_COOKIE, "test-kiosk-1")
    assert browser.get(endpoint).status_code == 404
    assert browser.get(f"/api/kiosk/attendance/{uuid4()}").status_code == 404
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 1


@pytest.mark.parametrize("same_request", [False, True])
def test_native_sqlserver_concurrent_kiosks_or_retries_record_once(attendance, same_request):
    if not os.environ.get("CHAMCONG_TEST_DATABASE_URL"):
        pytest.skip("Row locking must be proven on SQL Server, not SQLite")
    _, factory, now, ids, session, _ = attendance
    first = session()
    second = first if same_request else session(device=1)
    barrier = Barrier(2)

    def worker(request, device):
        with factory() as db:
            db.execute(text("SET LOCK_TIMEOUT 5000"))
            barrier.wait(timeout=5)
            return commit_recognition(
                db, request, ids[2][device], ids[3][device], ids[1], "m", 60, clock=lambda: now
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(worker, first, 0),
            executor.submit(worker, second, 0 if same_request else 1),
        ]
        results = [future.result(timeout=15) for future in futures]
    assert len({result["event_id"] for result in results}) == 1
    assert sorted(result["status"] for result in results) == (
        ["recorded", "recorded"] if same_request else ["duplicate", "recorded"]
    )
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 1


def test_database_response_loss_after_commit_is_recoverable_by_request_id(attendance, monkeypatch):
    browser, factory, _, ids, session, _ = attendance
    request = session()
    browser.cookies.set(KIOSK_COOKIE, "test-kiosk-0")
    endpoint = f"/api/kiosk/attendance/{request}"
    original = attendance_api.commit_recognition

    def lose_response(*args):
        original(*args)
        raise OperationalError("test response lost after commit", {}, Exception("simulated connection loss"))

    monkeypatch.setattr(attendance_api, "commit_recognition", lose_response)
    original_engine = app.state.face_engine
    try:
        app.state.attendance_policy_id = ids[1]
        app.state.face_engine = SimpleNamespace(model_id="m")
        headers = {"X-Kiosk-Intent": "record-attendance"}
        assert browser.post(endpoint + "/commit", json={}, headers=headers).status_code == 503
        receipt = browser.get(endpoint)
        assert receipt.status_code == 200
        assert receipt.json()["status"] == "recorded"
        monkeypatch.setattr(attendance_api, "commit_recognition", original)
        assert browser.post(endpoint + "/commit", json={}, headers=headers).json() == receipt.json()
    finally:
        app.state.attendance_policy_id = None
        app.state.face_engine = original_engine
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 1


def test_bounded_commit_capacity_never_reports_unrecorded_work_as_success(attendance):
    browser, factory, _, ids, session, _ = attendance
    request = session()
    browser.cookies.set(KIOSK_COOKIE, "test-kiosk-0")
    original_engine = app.state.face_engine
    for _ in range(4):
        assert attendance_api.commit_slots.acquire(blocking=False)
    try:
        app.state.attendance_policy_id = ids[1]
        app.state.face_engine = SimpleNamespace(model_id="m")
        response = browser.post(
            f"/api/kiosk/attendance/{request}/commit",
            json={},
            headers={"X-Kiosk-Intent": "record-attendance"},
        )
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "1"
    finally:
        for _ in range(4):
            attendance_api.commit_slots.release()
        app.state.attendance_policy_id = None
        app.state.face_engine = original_engine
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 0


def test_pending_expired_and_rejected_receipts_never_imply_recorded(attendance):
    browser, factory, now, _, session, _ = attendance
    request = session(state="pending")
    browser.cookies.set(KIOSK_COOKIE, "test-kiosk-0")
    endpoint = f"/api/kiosk/attendance/{request}"
    assert browser.get(endpoint).status_code == 202
    with factory() as db:
        db.get(RecognitionSession, request).state = "rejected"
        db.commit()
    assert browser.get(endpoint).status_code == 422
    with factory() as db:
        db.get(RecognitionSession, request).expires_at = now - timedelta(seconds=1)
        db.commit()
    assert browser.get(endpoint).status_code == 410


def test_cached_policy_cannot_bypass_new_supervision_requirement(attendance):
    _, factory, now, ids, session, _ = attendance
    request = session()
    with factory() as db:
        cached = db.get(RecognitionPolicy, ids[1])
        assert cached.mode == "automatic"
        db.execute(
            update(RecognitionPolicy)
            .where(RecognitionPolicy.id == ids[1])
            .values(mode="supervised")
            .execution_options(synchronize_session=False)
        )
        db.commit()
        assert cached.mode == "automatic"  # Simulate an already-loaded ORM object.
        with pytest.raises(HTTPException) as error:
            commit_recognition(db, request, ids[2][0], ids[3][0], ids[1], "m", 60, clock=lambda: now)
        assert error.value.status_code == 409
