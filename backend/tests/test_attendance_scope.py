from datetime import UTC, date, datetime, timedelta

import pytest
from app.attendance_scope import existing_punch
from app.models import AttendanceEvent, Device, Employee, Shift, ShiftAssignment
from fastapi import HTTPException


@pytest.fixture
def scoped(client):
    _, factory = client
    with factory() as db:
        person = Employee(code="SCOPE", name="Nhân viên thử ca")
        device = Device(name="Kiosk thử")
        db.add_all([person, device])
        db.commit()
        person_id, device_id = person.id, device.id

    def shift(day, start=480, end=1020, before=0, after=0):
        with factory() as db:
            definition = Shift(name="Ca thử", start_minute=start, end_minute=end,
                               rules={"capture_before_minutes": before, "capture_after_minutes": after})
            db.add(definition)
            db.flush()
            assignment = ShiftAssignment(employee_id=person_id, shift_id=definition.id, work_date=day)
            db.add(assignment)
            db.commit()
            return assignment.id

    def punch(at, direction="in"):
        with factory() as db:
            row = AttendanceEvent(employee_id=person_id, device_id=device_id, request_id=str(at)+direction,
                                  direction=direction, server_time=at, recognition_version="test-only")
            db.add(row)
            db.commit()
            return row.id

    def find(at, direction="in"):
        with factory() as db:
            event, scope = existing_punch(db, person_id, direction, at)
            return event.id if event else None, scope

    return factory, shift, punch, find


def instant(day=29, hour=8, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC)-timedelta(hours=7)


def test_same_shift_hours_later_returns_first_punch_and_directions_are_independent(scoped):
    _, shift, punch, find = scoped
    assignment = shift(date(2026, 10, 29))
    first = punch(instant())
    assert find(instant(hour=11)) == (first, {"type": "shift", "assignment_id": assignment, "work_date": "2026-10-29"})
    assert find(instant(hour=11), "out")[0] is None
    out = punch(instant(hour=16), "out")
    assert find(instant(hour=17), "out")[0] == out


def test_next_shift_is_new_even_less_than_sixty_seconds_later(scoped):
    _, shift, punch, find = scoped
    shift(date(2026, 10, 29), end=720)
    next_shift = shift(date(2026, 10, 29), start=720)
    punch(instant(hour=11, minute=59))
    event, scope = find(instant(hour=12))
    assert event is None
    assert scope["assignment_id"] == next_shift


def test_overnight_shift_after_midnight_is_still_same_shift(scoped):
    _, shift, punch, find = scoped
    assignment = shift(date(2026, 10, 29), start=1320, end=360, before=60, after=60)
    first = punch(instant(hour=22))
    assert find(instant(day=30, hour=1))[0] == first
    assert find(instant(day=30, hour=1))[1]["assignment_id"] == assignment
    out = punch(instant(day=30, hour=5), "out")
    assert find(instant(day=30, hour=7), "out")[0] == out


def test_unassigned_workday_resets_at_local_midnight_without_swallowing_next_day(scoped):
    _, _, punch, find = scoped
    first = punch(instant(hour=8))
    assert find(instant(hour=23))[0] == first
    assert find(instant(day=30, hour=0))[0] is None


def test_unassigned_punch_is_not_reused_for_assigned_shift_on_same_day(scoped):
    _, shift, punch, find = scoped
    punch(instant(hour=7))
    shift(date(2026, 10, 29))
    assert find(instant(hour=8))[0] is None
    first = punch(instant(hour=8))
    assert find(instant(hour=12))[0] == first
    assert find(instant(hour=18))[0] != first


def test_overlapping_capture_windows_fail_without_picking_an_arbitrary_shift(scoped):
    _, shift, _, find = scoped
    shift(date(2026, 10, 29), end=720)
    shift(date(2026, 10, 29), start=780, before=120)
    with pytest.raises(HTTPException) as error:
        find(instant(hour=11))
    assert error.value.status_code == 409
