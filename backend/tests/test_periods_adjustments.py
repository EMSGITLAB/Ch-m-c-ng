import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from app.adjustments import AdjustmentInput, create_adjustment
from app.config import get_settings
from app.models import AttendanceAdjustment, AttendanceEvent, AuditLog, TimesheetSnapshot
from app.periods import CloseInput, close_period
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from test_admin import setup
from test_attendance import attendance as attendance
from test_shifts import schedule as schedule
from test_timesheets import add_events, get_report

ROOT = "/api/admin/timesheets"


def correction(browser, headers, person, **extra):
    payload = {
        "request_id": str(uuid4()),
        "employee_id": person,
        "kind": "add",
        "direction": "out",
        "occurred_at": "2025-12-31T17:00:00+07:00",
        "reason": "Bổ sung do thiếu lượt ra",
    }
    payload.update(extra)
    if payload["kind"] == "void":
        payload.pop("direction", None)
        payload.pop("occurred_at", None)
    return browser.post(ROOT + "/adjustments", headers=headers, json=payload)


def lock(browser, headers, month="2025-12", revision=0, **extra):
    return browser.post(
        f"{ROOT}/periods/{month}/lock",
        headers=headers,
        json={"reason": "Chốt kỳ thử nghiệm", "expected_revision": revision} | extra,
    )


def snapshot(browser, **params):
    response = browser.get(ROOT + "/periods/2025-12/snapshot", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def prepared(schedule, missing=False):
    browser, factory, headers, people, create, assign = schedule
    shift = create()
    assert assign(shift, begin="2025-12-31", employees=[people[0]]).status_code == 201
    events = [("in", "2025-12-31T08:00:00+07:00")]
    if not missing:
        events.append(("out", "2025-12-31T17:00:00+07:00"))
    add_events(factory, people[0], events)
    return browser, factory, headers, people, shift, assign


def test_add_void_and_revoke_preserve_raw_events_and_recalculate_with_audit(schedule):
    browser, factory, headers, people, _, _ = prepared(schedule, missing=True)
    before = get_report(browser)
    assert before["rows"][0]["worked_seconds"] is None
    added = correction(browser, headers, people[0])
    assert added.status_code == 201, added.text
    added = added.json()
    with factory() as db:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_id == added["id"], AuditLog.action == "attendance_adjustment_create"
            )
        )
        assert audit.details["before"] is None
        assert audit.details["after"]["direction"] == "out"
        assert audit.details["admin_id"] == 1 and audit.created_at
    report = get_report(browser)
    assert report["summary"]["worked_seconds"] == 480 * 60
    assert report["rows"][0]["events"][-1]["source"] == "manual"
    assert report["source_digest"] != before["source_digest"]
    removed = correction(browser, headers, people[0], kind="void", target_adjustment_id=added["id"])
    assert removed.status_code == 201, removed.text
    assert get_report(browser)["rows"][0]["worked_seconds"] is None
    assert (
        browser.post(
            f"{ROOT}/adjustments/{added['id']}/revoke",
            json={"reason": "Thu hồi lượt bổ sung"},
            headers=headers,
        ).status_code
        == 409
    )
    assert (
        browser.post(
            f"{ROOT}/adjustments/{removed.json()['id']}/revoke",
            json={"reason": "Khôi phục lượt bổ sung"},
            headers=headers,
        ).status_code
        == 200
    )
    assert get_report(browser)["summary"]["worked_seconds"] == 480 * 60
    with factory() as db:
        original = db.scalar(select(AttendanceEvent))
        original_id, original_time = original.id, original.server_time
    void_raw = correction(browser, headers, people[0], kind="void", target_event_id=original_id)
    assert void_raw.status_code == 201
    with factory() as db:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.entity_id == void_raw.json()["id"], AuditLog.action == "attendance_adjustment_create"
            )
        )
        assert audit.details["before"]["id"] == original_id
        assert audit.details["after"]["kind"] == "void"
    assert get_report(browser)["rows"][0]["worked_seconds"] is None
    assert (
        correction(browser, headers, people[0], kind="void", target_event_id=original_id).status_code == 409
    )
    assert (
        correction(browser, headers, people[1], kind="void", target_event_id=original_id).status_code == 404
    )
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 1
        assert db.get(AttendanceEvent, original_id).server_time == original_time
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "attendance_adjustment_create")
            )
            == 3
        )
    history = browser.get(
        ROOT + "/adjustments", params={"date_from": "2025-12-31", "date_to": "2025-12-31", "limit": 2}
    ).json()
    assert len(history["items"]) == 2 and history["has_more"]


def test_idempotent_request_conflict_and_revocation_does_not_resurrect_on_retry(schedule):
    browser, factory, headers, people, _, _ = prepared(schedule, missing=True)
    request = str(uuid4())
    first = correction(browser, headers, people[0], request_id=request).json()
    assert correction(browser, headers, people[0], request_id=request).json() == first
    assert (
        correction(
            browser, headers, people[0], request_id=request, reason="Nội dung khác cùng yêu cầu"
        ).status_code
        == 409
    )
    endpoint = f"{ROOT}/adjustments/{first['id']}/revoke"
    assert (
        browser.post(endpoint, json={"reason": "Đã đối chiếu cần thu hồi"}, headers=headers).status_code
        == 200
    )
    assert (
        browser.post(endpoint, json={"reason": "Thử lại sau mất phản hồi"}, headers=headers).status_code
        == 200
    )
    assert correction(browser, headers, people[0], request_id=request).json()["revoked_at"]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceAdjustment)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "attendance_adjustment_revoke")
            )
            == 1
        )


@pytest.mark.parametrize(
    "patch",
    [
        {"occurred_at": "2025-12-31T17:00:00"},
        {"occurred_at": "9998-12-31T17:00:00Z"},
        {"reason": "  "},
        {"employee_id": "missing"},
        {"kind": "void"},
        {"kind": "add", "target_event_id": "unexpected"},
        {"extra": "forbidden"},
    ],
)
def test_correction_rejects_invalid_ambiguous_or_future_input(schedule, patch):
    browser, _, headers, people, _, _ = schedule
    assert correction(browser, headers, people[0], **patch).status_code in (404, 422)


def test_locked_period_blocks_all_ledger_writes_and_preserves_snapshot_names(schedule):
    browser, factory, headers, people, shift, assign = prepared(schedule)
    added = correction(browser, headers, people[0], occurred_at="2025-12-30T17:00:00+07:00").json()
    # An unassigned manual event must be acknowledged explicitly before closing.
    assert lock(browser, headers).status_code == 409
    result = lock(browser, headers, allow_unresolved=True)
    assert result.status_code == 200, result.text
    assert result.json()["revision"] == 1
    frozen = snapshot(browser)
    assert frozen["finalized"] and frozen["is_current"] and frozen["locked_with_unresolved"]
    with factory() as db:
        original = db.scalar(select(AttendanceEvent.id))
    assert correction(browser, headers, people[0]).status_code == 409
    assert correction(browser, headers, people[0], kind="void", target_event_id=original).status_code == 409
    assert (
        browser.post(
            f"{ROOT}/adjustments/{added['id']}/revoke",
            json={"reason": "Thu hồi sau khóa kỳ"},
            headers=headers,
        ).status_code
        == 409
    )
    assignment = frozen["rows"][0]["assignment_id"]
    assert (
        browser.post(
            f"/api/admin/shift-assignments/{assignment}/cancel",
            json={"reason": "Hủy lịch sau chốt"},
            headers=headers,
        ).status_code
        == 409
    )
    assert assign(shift, begin="2025-12-30", employees=[people[1]]).status_code == 409
    # A normal following-day shift has no intersecting window and remains writable.
    assert assign(shift, begin="2026-01-01", employees=[people[1]]).status_code == 201
    assert (
        browser.patch(
            f"/api/admin/employees/{people[0]}", headers=headers, json={"name": "Tên sửa sau chốt"}
        ).status_code
        == 200
    )
    assert snapshot(browser) == frozen
    assert snapshot(browser, employee_id=people[0])["period"]["employee_name"] != "Tên sửa sau chốt"
    assert lock(browser, headers, revision=1).status_code == 409
    reopened = browser.post(
        ROOT + "/periods/2025-12/reopen",
        headers=headers,
        json={"reason": "Mở để đối chiếu lại công", "expected_revision": 1},
    )
    assert reopened.status_code == 200
    assert snapshot(browser)["is_current"] is False
    assert (
        browser.post(
            f"{ROOT}/adjustments/{added['id']}/revoke",
            json={"reason": "Loại lượt ngoài lịch ca"},
            headers=headers,
        ).status_code
        == 200
    )
    assert lock(browser, headers, revision=0).status_code == 409
    assert lock(browser, headers, revision=1).status_code == 200
    assert snapshot(browser)["snapshot_revision"] == 2
    assert snapshot(browser)["rows"][0]["employee_name"] == "Tên sửa sau chốt"
    old = snapshot(browser, revision=1)
    assert old["rows"] == frozen["rows"] and old["source_digest"] == frozen["source_digest"]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(TimesheetSnapshot)) == 2


def test_overnight_protection_includes_next_month_without_blocking_unrelated_employee(schedule):
    browser, _, headers, people, create, assign = schedule
    shift = create({"name": "Ca đêm", "start": "22:00", "end": "06:00"})
    assert assign(shift, begin="2025-12-31", employees=[people[0]]).status_code == 201
    assert lock(browser, headers, allow_unresolved=True).status_code == 200
    assert correction(browser, headers, people[0], occurred_at="2026-01-01T06:00:00+07:00").status_code == 409
    assert correction(browser, headers, people[1], occurred_at="2026-01-01T06:00:00+07:00").status_code == 201
    early = create({"name": "Ca đầu năm", "start": "07:00", "end": "10:00", "capture_before_minutes": 120})
    assert assign(early, begin="2026-01-01", employees=[people[0]]).status_code == 409
    assert assign(early, begin="2026-01-01", employees=[people[1]]).status_code == 201


def test_close_rejects_current_period_and_open_capture_window_and_keeps_missing_null(schedule):
    browser, factory, headers, people, create, assign = schedule
    shift = create({"name": "Ca đêm", "start": "22:00", "end": "06:00"})
    assert assign(shift, begin="2025-12-31", employees=[people[0]]).status_code == 201
    for now in [datetime(2025, 12, 15, tzinfo=UTC), datetime(2026, 1, 1, 0, tzinfo=UTC)]:
        with factory() as db, pytest.raises(HTTPException) as error:
            close_period(
                db,
                "2025-12",
                CloseInput(reason="Thử khóa kỳ chưa kết thúc", expected_revision=0, allow_unresolved=True),
                SimpleNamespace(id=1),
                now=now,
            )
        assert error.value.status_code == 409
    assert lock(browser, headers).status_code == 409
    assert lock(browser, headers, allow_unresolved=True).status_code == 200
    frozen = snapshot(browser)
    assert frozen["rows"][0]["worked_seconds"] is None
    assert frozen["summary"]["status_counts"] == {"incomplete": 1}


def test_period_and_adjustment_access_and_validation(schedule):
    browser, _, headers, people, _, _ = schedule
    assert browser.get(ROOT + "/periods/2025-13").status_code == 422
    assert browser.get(ROOT + "/periods/2025-12/snapshot").status_code == 404
    assert browser.get(ROOT + "/periods/2025-12").json()["revision"] == 0
    assert (
        browser.post(
            ROOT + "/periods/2025-12/lock", json={"expected_revision": 0, "reason": "Đủ lý do chốt"}
        ).status_code
        == 403
    )
    browser.cookies.clear()
    assert browser.get(ROOT + "/periods/2025-12").status_code == 401
    assert correction(browser, headers, people[0]).status_code == 401


def test_local_wall_time_is_resolved_by_server_business_timezone(schedule):
    browser, _, headers, people, _, _ = prepared(schedule, missing=True)
    response = correction(browser, headers, people[0], occurred_at=None, local_time="2025-12-31T17:00:00")
    assert response.status_code == 201, response.text
    assert datetime.fromisoformat(response.json()["occurred_at"]) == datetime(2025, 12, 31, 10, tzinfo=UTC)
    assert get_report(browser)["rows"][0]["worked_seconds"] == 28800
    assert correction(browser, headers, people[0], local_time="2025-12-31T17:00:00").status_code == 422


def test_ambiguous_or_nonexistent_local_time_is_rejected(tmp_path, monkeypatch):
    import json

    path = tmp_path / "business.json"
    path.write_text(json.dumps({"timezone": "America/New_York"}), encoding="utf-8")
    monkeypatch.setattr(get_settings(), "business_config_path", path)
    for local in ["2025-11-02T01:30:00", "2025-03-09T02:30:00"]:
        with pytest.raises(ValidationError):
            AdjustmentInput(
                request_id=uuid4(),
                employee_id="test",
                kind="add",
                direction="out",
                local_time=local,
                reason="Thử mốc đổi giờ mùa hè",
            )


def test_recording_cannot_write_closed_month_but_existing_receipt_still_retries(attendance):
    browser, factory, now, ids, session, record = attendance
    setup(browser)
    first_id = session()
    first = record(first_id)
    pending = session(device=1)
    month = now.astimezone(ZoneInfo(get_settings().business().timezone)).strftime("%Y-%m")
    with factory() as db:
        close_period(
            db,
            month,
            CloseInput(expected_revision=0, reason="Đối chiếu commit kỳ khóa", allow_unresolved=True),
            SimpleNamespace(id=1),
            now=now + timedelta(days=40),
        )
    with pytest.raises(HTTPException) as error:
        record(pending, device=1, at=now + timedelta(seconds=61))
    assert error.value.status_code == 409
    assert record(first_id) == first
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 1


@pytest.mark.skipif(
    not os.environ.get("CHAMCONG_TEST_DATABASE_URL"), reason="Requires independent SQL Server transactions"
)
def test_concurrent_close_and_correction_are_serialized_to_consistent_snapshot(schedule):
    _, factory, _, people, _, _ = prepared(schedule, missing=True)
    barrier = Barrier(2)
    payload = AdjustmentInput(
        request_id=uuid4(),
        employee_id=people[0],
        kind="add",
        direction="out",
        occurred_at="2025-12-31T17:00:00+07:00",
        reason="Bổ sung đồng thời chốt kỳ",
    )

    def change():
        barrier.wait(timeout=10)
        with factory() as db:
            try:
                return create_adjustment(db, payload, SimpleNamespace(id=1))["id"]
            except HTTPException as error:
                assert error.status_code == 409
                return None

    def close():
        barrier.wait(timeout=10)
        with factory() as db:
            return close_period(
                db,
                "2025-12",
                CloseInput(expected_revision=0, reason="Chốt đồng thời điều chỉnh", allow_unresolved=True),
                SimpleNamespace(id=1),
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        changing, closing = pool.submit(change), pool.submit(close)
        added = changing.result(timeout=30)
        assert closing.result(timeout=30)["status"] == "locked"
    with factory() as db:
        report = db.scalar(select(TimesheetSnapshot)).payload
        assert report["rows"][0]["worked_seconds"] == (480 * 60 if added else None)
        assert db.scalar(select(func.count()).select_from(AttendanceAdjustment)) == (1 if added else 0)
