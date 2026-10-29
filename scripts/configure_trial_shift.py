"""Apply the user-approved sample shift to one trial profile's existing punch dates."""

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.calendar_guard import lock_calendar  # noqa: E402
from app.database import session_factory  # noqa: E402
from app.devices import aware  # noqa: E402
from app.models import AttendanceEvent, AuditLog, Employee, Shift, ShiftAssignment  # noqa: E402
from app.shift_rules import ShiftInput, describe_shift  # noqa: E402
from app.shifts import AssignInput, assign_shift, configured_timezone, create_definition  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--employee-code", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    payload = ShiftInput(name="Ca thử 08–17 (nghỉ 12–13)", start="08:00", end="17:00",
                         breaks=[{"start": "12:00", "end": "13:00", "paid": False}])
    timezone = configured_timezone()
    with session_factory()() as db:
        if db.bind.dialect.name != "mssql" or db.scalar(text(
            "SELECT CAST(value AS nvarchar(100)) FROM sys.extended_properties "
            "WHERE class=0 AND name=N'chamcong_project'")) != "chamcong-face-local":
            raise ValueError("Refusing an unmarked or non-SQL Server database")
        if args.apply:
            lock_calendar(db)
        person = db.scalar(select(Employee).where(Employee.code == args.employee_code, Employee.active == True))  # noqa: E712
        if person is None:
            raise ValueError("No active, explicitly selected trial profile")
        events = db.scalars(select(AttendanceEvent).where(AttendanceEvent.employee_id == person.id)).all()
        if not events or any(not event.recognition_version.startswith("trial-") for event in events):
            raise ValueError("This helper only configures profiles whose existing punches are all trial records")
        dates = sorted({aware(event.server_time).astimezone(ZoneInfo(timezone)).date() for event in events})
        candidates = db.scalars(select(Shift).where(Shift.name == payload.name, Shift.archived_at.is_(None))).all()
        shift = next((row for row in candidates if row.start_minute == 480 and row.end_minute == 1020
                      and row.timezone == timezone and row.rules == payload.normalized_rules()), None)
        assigned = set(db.scalars(select(ShiftAssignment.work_date).where(
            ShiftAssignment.employee_id == person.id, ShiftAssignment.cancelled_at.is_(None),
            ShiftAssignment.shift_id == shift.id)).all()) if shift else set()
        missing = [day for day in dates if day not in assigned]
        if missing:
            weekdays = sorted({day.weekday() for day in missing})
            generated = {missing[0]+timedelta(days=i) for i in range((missing[-1]-missing[0]).days+1)
                         if (missing[0]+timedelta(days=i)).weekday() in weekdays}
            if generated != set(missing):
                raise ValueError("Refusing to assign extra dates; use explicit date groups in the admin UI")
            if (missing[-1]-missing[0]).days > 30:
                raise ValueError("Trial date span exceeds a single atomic assignment request")
        created = 0
        if args.apply and missing:
            if shift is None:
                shift = create_definition(payload, timezone)
                db.add(shift)
                db.flush()
                db.add(AuditLog(action="shift_create", entity_id=shift.id, details=describe_shift(shift)))
            db.add(AuditLog(action="trial_shift_setup", entity_id=person.id,
                reason="Người dùng đồng ý ca mẫu 08:00–17:00 cho hồ sơ thử; nghỉ 12:00–13:00 theo đề xuất.",
                details={"source": "codex_local_cli", "scope": "one_approved_trial_profile",
                         "work_dates": [day.isoformat() for day in missing], "shift_id": shift.id}))
            # Reuse the API's locking, closed-period, overlap and atomicity rules.
            # The trusted local command has no human account to impersonate;
            # authorization was supplied in this thread, and this handler does not use its user argument.
            created = assign_shift(AssignInput(shift_id=shift.id, employee_ids=[person.id],
                date_from=missing[0], date_to=missing[-1], weekdays=weekdays), db, None)["created_count"]
        else:
            db.rollback()
        result = {"applied": args.apply, "profile_count": 1, "existing_trial_events": len(events),
                  "existing_punch_date_count": len(dates), "assignments_to_add": len(missing),
                  "assignments_created": created, "start": "08:00", "end": "17:00",
                  "unpaid_break": ["12:00", "13:00"], "expected_work_minutes": 480,
                  "other_employee_schedules_modified": False, "recognition_policy_modified": False,
                  "attendance_events_modified_by_tool": False, "payroll_period_finalized": False}
    print(json.dumps(result))


if __name__ == "__main__":
    main()
