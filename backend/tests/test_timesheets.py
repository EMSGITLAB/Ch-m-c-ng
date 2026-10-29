from datetime import UTC, datetime

from app import timesheets
from app.models import AttendanceEvent, AuditLog, Device, Employee
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from test_shifts import DAY
from test_shifts import schedule as schedule


def add_events(factory, employee, values):
    with factory() as db:
        device = Device(name="Bộ thử bảng công", direction="in")
        db.add(device)
        db.flush()
        for index, (direction, local_time) in enumerate(values):
            db.add(
                AttendanceEvent(
                    employee_id=employee,
                    device_id=device.id,
                    request_id=f"{device.id}-{index}",
                    direction=direction,
                    server_time=datetime.fromisoformat(local_time).astimezone(UTC),
                    recognition_version="domain-test-only",
                )
            )
        db.commit()


def get_report(browser, day="2025-12-31", **extra):
    response = browser.get("/api/admin/timesheets/preview", params={"date_from": day, "date_to": day} | extra)
    assert response.status_code == 200, response.text
    return response.json()


def test_report_exact_examples_is_read_only_and_revision_keeps_old_assignment(schedule):
    browser, factory, headers, people, create, assign = schedule
    original = create()
    assert assign(original, begin="2025-12-31", employees=[people[0]]).status_code == 201
    add_events(
        factory, people[0], [("in", "2025-12-31T08:07:00+07:00"), ("out", "2025-12-31T17:00:00+07:00")]
    )
    with factory() as db:
        audit_count = db.scalar(select(func.count()).select_from(AuditLog))
        updated_at = db.get(Employee, people[0]).updated_at
    report = get_report(browser)
    assert report["rows"][0]["worked_seconds"] == 473 * 60
    assert report["summary"]["worked_seconds"] == 473 * 60
    assert report["rows"][0]["is_late"]
    assert len(report["rows"][0]["events"]) == 2
    assert report["finalized"] is False
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AttendanceEvent)) == 2
        assert db.scalar(select(func.count()).select_from(AuditLog)) == audit_count
        assert db.get(Employee, people[0]).updated_at == updated_at
    assert (
        browser.post(
            f"/api/admin/shifts/{original['id']}/revisions", json=DAY | {"start": "09:00"}, headers=headers
        ).status_code
        == 201
    )
    after = get_report(browser)
    assert after["rows"][0]["worked_seconds"] == 473 * 60
    assert after["source_digest"] == report["source_digest"]


def test_overnight_shift_uses_start_date_even_when_out_is_next_month(schedule):
    browser, factory, _, people, create, assign = schedule
    night = create({"name": "Đêm", "start": "22:00", "end": "06:00"})
    assert assign(night, begin="2025-12-31", employees=[people[0]]).status_code == 201
    add_events(
        factory, people[0], [("in", "2025-12-31T22:00:00+07:00"), ("out", "2026-01-01T06:00:00+07:00")]
    )
    report = get_report(browser)
    assert report["rows"][0]["work_date"] == "2025-12-31"
    assert report["rows"][0]["worked_seconds"] == 480 * 60
    next_day = get_report(browser, day="2026-01-01")
    assert next_day["summary"]["row_count"] == 0
    assert next_day["summary"]["unassigned_count"] == 0


def test_no_schedule_surfaces_unassigned_events_and_filter_preserves_inactive_history(schedule):
    browser, factory, headers, people, _, _ = schedule
    add_events(factory, people[0], [("in", "2025-12-31T08:00:00+07:00")])
    assert (
        browser.patch(
            f"/api/admin/employees/{people[0]}", json={"active": False}, headers=headers
        ).status_code
        == 200
    )
    report = get_report(browser, employee_id=people[0])
    assert report["summary"]["row_count"] == 0
    assert report["summary"]["worked_seconds"] == 0
    assert report["summary"]["unassigned_count"] == 1
    assert report["unassigned_events"][0]["employee_id"] == people[0]
    assert get_report(browser, employee_id=people[1])["summary"]["unassigned_count"] == 0


def test_missing_pair_is_not_in_total_and_pagination_summary_is_whole_result(schedule):
    browser, factory, _, people, create, assign = schedule
    shift = create()
    assert assign(shift, begin="2025-12-31").status_code == 201
    add_events(
        factory, people[0], [("in", "2025-12-31T08:00:00+07:00"), ("out", "2025-12-31T17:00:00+07:00")]
    )
    add_events(factory, people[1], [("in", "2025-12-31T08:00:00+07:00")])
    first = get_report(browser, limit=1)
    second = get_report(browser, limit=1, offset=1)
    assert first["summary"] == second["summary"]
    assert first["summary"]["worked_seconds"] == 480 * 60
    assert first["summary"]["status_counts"] == {"complete": 1, "incomplete": 1}
    assert first["has_more"]
    assert not second["has_more"]
    assert first["rows"][0]["assignment_id"] != second["rows"][0]["assignment_id"]


def test_two_day_context_prevents_silently_assigning_long_window_to_wrong_shift(schedule):
    browser, factory, _, people, create, assign = schedule
    long_shift = create(
        {
            "name": "Ca dài",
            "start": "23:00",
            "end": "22:00",
            "capture_before_minutes": 0,
            "capture_after_minutes": 0,
        }
    )
    early_shift = create(
        {
            "name": "Ca sớm",
            "start": "00:00",
            "end": "01:00",
            "capture_before_minutes": 720,
            "capture_after_minutes": 0,
        }
    )
    assert assign(long_shift, begin="2025-12-29", employees=[people[0]]).status_code == 201
    assert assign(early_shift, begin="2025-12-31", employees=[people[0]]).status_code == 201
    add_events(factory, people[0], [("in", "2025-12-30T12:00:00+07:00")])
    report = get_report(browser)
    assert report["summary"]["ambiguous_count"] == 1
    assert report["rows"][0]["worked_seconds"] is None
    assert report["rows"][0]["status"] == "needs_review"
    assert len(report["ambiguous_events"][0]["candidate_assignments"]) == 2


def test_access_range_validation_and_bounded_capacity(schedule):
    browser, _, _, _, _, _ = schedule
    assert (
        browser.get(
            "/api/admin/timesheets/preview", params={"date_from": "2025-12-01", "date_to": "2026-02-01"}
        ).status_code
        == 422
    )
    assert (
        browser.get(
            "/api/admin/timesheets/preview",
            params={"date_from": "2025-12-31", "date_to": "2025-12-31", "employee_id": "missing"},
        ).status_code
        == 404
    )
    for _ in range(2):
        assert timesheets.slots.acquire(blocking=False)
    try:
        assert (
            browser.get(
                "/api/admin/timesheets/preview", params={"date_from": "2025-12-31", "date_to": "2025-12-31"}
            ).status_code
            == 429
        )
    finally:
        for _ in range(2):
            timesheets.slots.release()
    browser.cookies.clear()
    assert (
        browser.get(
            "/api/admin/timesheets/preview", params={"date_from": "2025-12-31", "date_to": "2025-12-31"}
        ).status_code
        == 401
    )


def test_database_failure_never_returns_partial_timesheet_and_releases_capacity(schedule, monkeypatch):
    browser, _, _, _, _, _ = schedule

    def fail(*args):
        raise OperationalError("test database unavailable", {}, Exception("simulated disconnect"))

    monkeypatch.setattr(timesheets, "build_report", fail)
    response = browser.get(
        "/api/admin/timesheets/preview", params={"date_from": "2025-12-31", "date_to": "2025-12-31"}
    )
    assert response.status_code == 503
    assert "rows" not in response.json()
    acquired = 0
    try:
        for _ in range(2):
            assert timesheets.slots.acquire(blocking=False)
            acquired += 1
    finally:
        for _ in range(acquired):
            timesheets.slots.release()
