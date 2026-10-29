import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier
from types import SimpleNamespace

import pytest
from app.models import AuditLog, Shift, ShiftAssignment
from app.shift_rules import ShiftInput, shift_interval
from app.shifts import AssignInput, assign_shift, revise_shift
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select, text
from test_admin import setup

DAY = {
    "name": "Ca ngày",
    "start": "08:00",
    "end": "17:00",
    "breaks": [{"start": "12:00", "end": "13:00", "paid": False}],
}


@pytest.fixture
def schedule(client):
    browser, factory = client
    headers = {"X-CSRF-Token": setup(browser)}
    people = [
        browser.post(
            "/api/admin/employees", json={"code": f"TEST{number}", "name": "Hồ sơ thử"}, headers=headers
        ).json()["id"]
        for number in range(2)
    ]

    def create(payload=None):
        response = browser.post("/api/admin/shifts", json=payload or DAY, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    def assign(shift, begin="2026-10-28", end=None, employees=None, weekdays=None):
        payload = {
            "shift_id": shift["id"],
            "employee_ids": employees or people,
            "date_from": begin,
            "date_to": end or begin,
        }
        if weekdays is not None:
            payload["weekdays"] = weekdays
        return browser.post("/api/admin/shift-assignments", json=payload, headers=headers)

    return browser, factory, headers, people, create, assign


@pytest.mark.parametrize(
    "patch",
    [
        {"start": "24:00"},
        {"end": "08:00"},
        {"breaks": [{"start": "17:00", "end": "18:00"}]},
        {"breaks": [{"start": "12:00", "end": "13:00"}, {"start": "12:30", "end": "14:00"}]},
        {"breaks": [{"start": "08:00", "end": "17:00"}]},
        {"capture_before_minutes": 721},
    ],
)
def test_invalid_shift_rules_are_rejected(patch):
    with pytest.raises(ValidationError):
        ShiftInput.model_validate(DAY | patch)


def test_unpaid_and_paid_breaks_and_overnight_offsets():
    day = ShiftInput.model_validate(DAY)
    night = ShiftInput.model_validate(
        {
            "name": "Ca đêm",
            "start": "22:00",
            "end": "06:00",
            "breaks": [
                {"start": "23:45", "end": "00:15", "paid": True},
                {"start": "02:00", "end": "02:30", "paid": False},
            ],
        }
    )
    assert day.normalized_rules()["breaks"] == [{"start_offset": 240, "end_offset": 300, "paid": False}]
    assert night.normalized_rules()["breaks"] == [
        {"start_offset": 105, "end_offset": 135, "paid": True},
        {"start_offset": 240, "end_offset": 270, "paid": False},
    ]


def test_timezone_and_overnight_year_boundary_and_dst_rejection():
    definition = SimpleNamespace(start_minute=1320, end_minute=360, timezone="Asia/Ho_Chi_Minh")
    start, end = shift_interval(definition, date(2026, 12, 31))
    assert start.isoformat() == "2026-12-31T15:00:00+00:00"
    assert end.isoformat() == "2026-12-31T23:00:00+00:00"
    ambiguous = SimpleNamespace(start_minute=90, end_minute=210, timezone="America/New_York")
    with pytest.raises(ValueError, match="mùa hè"):
        shift_interval(ambiguous, date(2026, 11, 1))


def test_access_and_csrf_and_no_client_version_override(schedule):
    browser, _, headers, _, _, _ = schedule
    assert browser.post("/api/admin/shifts", json=DAY).status_code == 403
    assert browser.post("/api/admin/shifts", json=DAY | {"revision": 99}, headers=headers).status_code == 422
    browser.cookies.clear()
    assert browser.get("/api/admin/shifts").status_code == 401
    assert browser.post("/api/admin/shifts", json=DAY, headers=headers).status_code == 401


def test_overnight_paid_break_does_not_reduce_scheduled_work_minutes(schedule):
    _, _, _, _, create, _ = schedule
    shift = create(
        {
            "name": "Ca đêm có nghỉ",
            "start": "22:00",
            "end": "06:00",
            "breaks": [
                {"start": "23:45", "end": "00:15", "paid": True},
                {"start": "02:00", "end": "02:30", "paid": False},
            ],
        }
    )
    assert shift["duration_minutes"] == 480
    assert shift["expected_work_minutes"] == 450
    assert shift["overnight"] is True


def test_batch_with_inactive_employee_does_not_create_partial_schedule(schedule):
    browser, factory, headers, people, create, assign = schedule
    shift = create()
    assert (
        browser.patch(
            f"/api/admin/employees/{people[1]}", json={"active": False}, headers=headers
        ).status_code
        == 200
    )
    assert assign(shift).status_code == 409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ShiftAssignment)) == 0


def test_revision_preserves_previously_assigned_rules(schedule):
    browser, factory, headers, _, create, assign = schedule
    original = create()
    assert original["expected_work_minutes"] == 480
    assert assign(original).status_code == 201
    changed = browser.post(
        f"/api/admin/shifts/{original['id']}/revisions", json=DAY | {"start": "09:00"}, headers=headers
    )
    assert changed.status_code == 201, changed.text
    latest = changed.json()
    assert latest["family_id"] == original["family_id"]
    assert latest["revision"] == 2
    assert latest["expected_work_minutes"] == 420
    assert (
        browser.post(f"/api/admin/shifts/{original['id']}/revisions", json=DAY, headers=headers).status_code
        == 409
    )
    assert assign(original, begin="2026-10-29").status_code == 409
    listed = browser.get(
        "/api/admin/shift-assignments", params={"date_from": "2026-10-28", "date_to": "2026-10-28"}
    ).json()
    assert len(listed["items"]) == 2
    assert all(
        row["shift"]["id"] == original["id"] and row["shift"]["expected_work_minutes"] == 480
        for row in listed["items"]
    )
    assert [row["id"] for row in browser.get("/api/admin/shifts").json()["items"]] == [latest["id"]]
    with factory() as db:
        assert db.get(Shift, original["id"]).start_minute == 480
        assert db.scalar(select(func.count()).select_from(Shift)) == 2


def test_batch_weekdays_and_pagination_are_complete_and_atomic(schedule):
    browser, factory, _, _, create, assign = schedule
    shift = create()
    result = assign(shift, begin="2026-10-26", end="2026-11-01", weekdays=[0, 1, 2, 3, 4])
    assert result.status_code == 201, result.text
    assert result.json()["created_count"] == 10
    query = {"date_from": "2026-10-26", "date_to": "2026-11-01", "limit": 3}
    first = browser.get("/api/admin/shift-assignments", params=query).json()
    second = browser.get("/api/admin/shift-assignments", params=query | {"offset": 3}).json()
    assert first["has_more"]
    assert not {row["id"] for row in first["items"]} & {row["id"] for row in second["items"]}
    assert assign(shift, begin="2026-10-27", employees=["missing"]).status_code == 404
    assert assign(shift, begin="2026-11-02", end="2026-12-31").status_code == 422
    assert assign(shift, begin="2026-11-02", weekdays=[0, 0]).status_code == 422
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ShiftAssignment)) == 10


def test_overnight_overlap_rolls_back_whole_batch_but_adjacent_shift_is_allowed(schedule):
    _, factory, _, people, create, assign = schedule
    night = create({"name": "Đêm", "start": "22:00", "end": "06:00"})
    morning = create({"name": "Sớm", "start": "05:00", "end": "10:00"})
    adjacent = create({"name": "Liền ca", "start": "06:00", "end": "10:00"})
    assert assign(night, begin="2026-12-31", employees=[people[0]]).status_code == 201
    assert assign(morning, begin="2027-01-01").status_code == 409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ShiftAssignment)) == 1
    assert assign(adjacent, begin="2027-01-01", employees=[people[0]]).status_code == 201


def test_cancel_keeps_history_allows_reassignment_and_archive_keeps_old_schedule(schedule):
    browser, factory, headers, _, create, assign = schedule
    shift = create()
    assert assign(shift, employees=None).status_code == 201
    query = {"date_from": "2026-10-28", "date_to": "2026-10-28"}
    rows = browser.get("/api/admin/shift-assignments", params=query).json()["items"]
    target = rows[0]
    assert (
        browser.post(
            f"/api/admin/shift-assignments/{target['id']}/cancel",
            json={"reason": "Đổi lịch thử"},
            headers=headers,
        ).status_code
        == 200
    )
    assert assign(shift, employees=[target["employee_id"]]).status_code == 201
    assert (
        browser.post(
            f"/api/admin/shifts/{shift['id']}/archive", json={"reason": "Ngừng dùng ca thử"}, headers=headers
        ).status_code
        == 200
    )
    assert assign(shift, begin="2026-10-29").status_code == 409
    history = browser.get("/api/admin/shift-assignments", params=query | {"include_cancelled": True}).json()[
        "items"
    ]
    assert len(history) == 3
    assert sum(row["cancelled"] for row in history) == 1
    with factory() as db:
        assert (
            db.scalar(
                select(func.count()).select_from(AuditLog).where(AuditLog.action == "shift_assignment_cancel")
            )
            == 1
        )


@pytest.mark.parametrize("operation", ["assign", "revise"])
def test_native_concurrent_assignment_or_revision_is_serialized(schedule, operation):
    if not os.environ.get("CHAMCONG_TEST_DATABASE_URL"):
        pytest.skip("Concurrent row locks must be checked on SQL Server")
    _, factory, _, people, create, _ = schedule
    shift = create()
    barrier = Barrier(2)

    def worker():
        with factory() as db:
            db.execute(text("SET LOCK_TIMEOUT 5000"))
            barrier.wait(timeout=5)
            try:
                if operation == "assign":
                    assign_shift(
                        AssignInput(
                            shift_id=shift["id"],
                            employee_ids=[people[0]],
                            date_from=date(2026, 10, 28),
                            date_to=date(2026, 10, 28),
                        ),
                        db,
                        None,
                    )
                else:
                    revise_shift(shift["id"], ShiftInput.model_validate(DAY | {"start": "09:00"}), db, None)
                return "created"
            except HTTPException as error:
                assert error.status_code == 409
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(worker) for _ in range(2)]
        results = [future.result(timeout=15) for future in futures]
    assert sorted(results) == ["conflict", "created"]
    with factory() as db:
        if operation == "assign":
            assert db.scalar(select(func.count()).select_from(ShiftAssignment)) == 1
        else:
            assert db.scalar(select(func.count()).select_from(Shift)) == 2
            assert db.scalar(select(func.count()).select_from(Shift).where(Shift.archived_at.is_(None))) == 1
