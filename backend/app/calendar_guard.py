"""Serialize time-ledger writes before any employee locks are acquired."""

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select, update

from .models import CalendarGate, TimesheetPeriod, TimesheetSnapshot


def lock_calendar(db):
    value = db.execute(
        update(CalendarGate)
        .where(CalendarGate.id == 1)
        .values(id=CalendarGate.id)
        .returning(CalendarGate.id)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    if value is None:
        raise HTTPException(
            503, "Chưa khởi tạo khóa sổ thời gian. Cần nâng cấp database trước khi sửa công/lịch."
        )


def protections(db, begin, end):
    return db.execute(
        select(TimesheetPeriod.month, TimesheetSnapshot.protection)
        .join(
            TimesheetSnapshot,
            (TimesheetSnapshot.month == TimesheetPeriod.month)
            & (TimesheetSnapshot.revision == TimesheetPeriod.revision),
        )
        .where(
            TimesheetPeriod.status == "locked",
            TimesheetPeriod.protected_from <= end,
            TimesheetPeriod.protected_until >= begin,
        )
    ).all()


def fail_locked(month):
    raise HTTPException(
        409, f"Thay đổi ảnh hưởng kỳ {month} đã khóa. Cần mở lại kỳ và ghi lý do trước khi thay đổi."
    )


def assert_event_writable(db, employee_id, at):
    for month, protection in protections(db, at, at):
        if (
            datetime.fromisoformat(protection["base_from"])
            <= at
            < datetime.fromisoformat(protection["base_to"])
        ):
            fail_locked(month)
        for begin, end in protection["windows"].get(employee_id, []):
            if datetime.fromisoformat(begin) <= at <= datetime.fromisoformat(end):
                fail_locked(month)


def assert_schedule_writable(db, employee_ids, shift, work_dates):
    from .shift_rules import shift_interval
    spans = []
    rules = shift.rules or {}
    for work_date in work_dates:
        begin, end = shift_interval(shift, work_date)
        spans.append(
            (
                begin - timedelta(minutes=rules.get("capture_before_minutes", 120)),
                end + timedelta(minutes=rules.get("capture_after_minutes", 120)),
            )
        )
    if not spans:
        return
    candidates = protections(db, min(begin for begin, _ in spans), max(end for _, end in spans))
    for month, protection in candidates:
        base = (
            datetime.fromisoformat(protection["base_from"]),
            datetime.fromisoformat(protection["base_to"]),
        )
        for begin, end in spans:
            if begin <= base[1] and base[0] <= end:
                fail_locked(month)
            for person in employee_ids:
                for left, right in protection["windows"].get(person, []):
                    if begin <= datetime.fromisoformat(right) and datetime.fromisoformat(left) <= end:
                        fail_locked(month)
