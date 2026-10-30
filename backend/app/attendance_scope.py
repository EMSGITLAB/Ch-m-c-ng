"""Find an existing punch in the same assigned shift and direction.

Uses the report's capture windows, including overnight shifts. Without an
assignment, the configured local workday is the fallback; never toggle direction.
Caller holds the calendar and employee locks until the receipt commits.
"""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select

from .config import get_settings
from .devices import aware
from .models import AttendanceEvent, Shift, ShiftAssignment
from .shift_rules import shift_interval


def existing_punch(db, employee_id, direction, now):
    zone = ZoneInfo(get_settings().business().timezone)
    day = now.astimezone(zone).date()
    assignments = db.execute(
        select(ShiftAssignment, Shift).join(Shift)
        .where(ShiftAssignment.employee_id == employee_id,
               ShiftAssignment.cancelled_at.is_(None),
               ShiftAssignment.work_date.between(day-timedelta(days=3), day+timedelta(days=3)))
    ).all()
    windows = []
    for assignment, shift in assignments:
        start, end = shift_interval(shift, assignment.work_date)
        rules = shift.rules or {}
        windows.append((assignment, start, end,
                        start-timedelta(minutes=rules.get("capture_before_minutes", 120)),
                        end+timedelta(minutes=rules.get("capture_after_minutes", 120))))

    def candidates(at):
        return [row for row in windows if
                (row[3] <= at < row[2] if direction == "in" else row[1] < at <= row[4])]

    current = candidates(now)
    if len(current) > 1:
        raise HTTPException(409, "Thời gian ghi nhận thuộc nhiều ca. Cần điều chỉnh khoảng nhận ca trước khi chấm công.")
    if current:
        assignment, start, end, before, after = current[0]
        begin, finish = (before, end) if direction == "in" else (start, after)
        scope = {"type": "shift", "assignment_id": assignment.id,
                 "work_date": assignment.work_date.isoformat()}
    else:
        begin = datetime.combine(day, time(), zone).astimezone(UTC)
        finish = datetime.combine(day+timedelta(days=1), time(), zone).astimezone(UTC)
        scope = {"type": "workday", "assignment_id": None, "work_date": day.isoformat()}

    events = db.scalars(select(AttendanceEvent).where(
        AttendanceEvent.employee_id == employee_id, AttendanceEvent.direction == direction,
        AttendanceEvent.server_time >= begin, AttendanceEvent.server_time <= min(finish, now),
    ).order_by(AttendanceEvent.server_time, AttendanceEvent.id)).all()
    for event in events:
        at = aware(event.server_time)
        previous = candidates(at)
        if scope["type"] == "shift":
            same = len(previous) == 1 and previous[0][0].id == scope["assignment_id"]
        else:
            same = not previous and at.astimezone(zone).date() == day
        if same:
            return event, scope
    return None, scope
