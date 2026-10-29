"""Live previews apply audited corrections; immutable snapshots are separate."""

import hashlib
import json
import threading
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from .adjustments import correction_overlay
from .auth import Admin, Db
from .biometric_state import lock_employee
from .config import get_settings
from .models import AttendanceEvent, Employee, Shift, ShiftAssignment
from .shift_rules import describe_shift, shift_interval
from .timesheet_engine import Schedule, calculate, rules_for

router = APIRouter(prefix="/api/admin/timesheets", tags=["timesheets"])
slots = threading.BoundedSemaphore(2)


def summarize(rows, unassigned, ambiguous):
    return {
        "row_count": len(rows),
        "status_counts": dict(Counter(row["status"] for row in rows)),
        "worked_seconds": round(
            sum(round(row["worked_seconds"] * 1_000_000) for row in rows if row["worked_seconds"] is not None)
            / 1_000_000,
            6,
        ),
        "late_count": sum(row["is_late"] for row in rows),
        "early_count": sum(row["is_early"] for row in rows),
        "unassigned_count": len(unassigned),
        "ambiguous_count": len(ambiguous),
    }


def build_report(
    db, date_from, date_to, employee_id=None, offset=0, limit=100, as_of=None, *, unpaginated=False
):
    if not 0 <= (date_to - date_from).days <= 30 or offset < 0 or not 1 <= limit <= 300:
        raise HTTPException(422, "Mỗi lượt xem tối đa 31 ngày, mỗi trang 1–300 ca.")
    query = select(Employee).order_by(Employee.code)
    if employee_id:
        query = query.where(Employee.id == employee_id)
    people = db.scalars(query.limit(1001)).all()
    if employee_id and not people:
        raise HTTPException(404, "Không có hồ sơ nhân viên.")
    if len(people) > 1000:
        raise HTTPException(413, "Danh sách quá lớn. Hãy chọn một nhân viên để thu hẹp báo cáo.")
    ids = [person.id for person in people]
    for selected in sorted(ids):
        # Shares the mutation lock used by attendance and schedule changes.
        # This keeps the selected employees' live data consistent during read.
        lock_employee(db, selected)
    people = db.scalars(
        select(Employee).where(Employee.id.in_(ids)).execution_options(populate_existing=True)
    ).all()
    now = as_of or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("as_of_requires_timezone")
    now = now.astimezone(UTC)
    context_from = date.fromordinal(max(date.min.toordinal(), date_from.toordinal() - 2))
    context_to = date.fromordinal(min(date.max.toordinal(), date_to.toordinal() + 2))
    assignments = db.execute(
        select(ShiftAssignment, Shift)
        .join(Shift)
        .where(
            ShiftAssignment.employee_id.in_(ids),
            ShiftAssignment.cancelled_at.is_(None),
            ShiftAssignment.work_date.between(context_from, context_to),
        )
        .limit(50001)
    ).all()
    if len(assignments) > 50000:
        raise HTTPException(413, "Quá nhiều lịch ca. Hãy thu hẹp báo cáo.")
    schedules = [Schedule(row.id, row.employee_id, row.work_date, shift) for row, shift in assignments]
    zone = ZoneInfo(get_settings().business().timezone)
    lower = datetime.combine(date_from, time(), tzinfo=zone).astimezone(UTC)
    upper = datetime.combine(date_to + timedelta(days=1), time(), tzinfo=zone).astimezone(UTC)
    for schedule in schedules:
        start, end = shift_interval(schedule.shift, schedule.work_date)
        rules, _ = rules_for(schedule)
        lower = min(lower, start - timedelta(minutes=rules.get("capture_before_minutes", 120)))
        upper = max(upper, end + timedelta(minutes=rules.get("capture_after_minutes", 120)))
    events = db.scalars(
        select(AttendanceEvent)
        .where(
            AttendanceEvent.employee_id.in_(ids),
            AttendanceEvent.server_time >= lower,
            AttendanceEvent.server_time <= upper,
            AttendanceEvent.server_time <= now,
        )
        .order_by(AttendanceEvent.server_time, AttendanceEvent.id)
        .limit(100001)
    ).all()
    if len(events) > 100000:
        raise HTTPException(413, "Quá nhiều lượt quét. Hãy thu hẹp báo cáo.")
    punches, corrections = correction_overlay(db, ids, lower, upper, now, events)
    report = calculate(schedules, punches, now)
    trial_event_ids = sorted(event.id for event in events if event.recognition_version.startswith("trial-"))
    report["source_digest"] = hashlib.sha256(
        json.dumps(
            {
                "calculation": report["source_digest"],
                "corrections": corrections,
                "people": sorted((person.id, person.code, person.name) for person in people),
                "functional_trial_event_ids": trial_event_ids,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    core = {row.id for row in schedules if date_from <= row.work_date <= date_to}
    rows = [row for row in report["rows"] if row["assignment_id"] in core]
    people_by_id = {person.id: person for person in people}
    shifts_by_assignment = {row.id: row.shift for row in schedules}
    punches_by_id = {punch.id: punch for punch in punches}

    def decorate_event(value):
        person = people_by_id[value["employee_id"]]
        return value | {"employee_code": person.code, "employee_name": person.name}

    def decorate_row(row):
        person = people_by_id[row["employee_id"]]
        return row | {
            "employee_code": person.code,
            "employee_name": person.name,
            "shift": describe_shift(shifts_by_assignment[row["assignment_id"]]),
            "events": [
                {
                    "id": identity,
                    "direction": punches_by_id[identity].direction,
                    "at": punches_by_id[identity].at.isoformat(),
                    "source": "manual" if identity.startswith("adjustment:") else "camera",
                }
                for identity in row["event_ids"]
            ],
        }

    unassigned = [
        decorate_event(row)
        for row in report["unassigned_events"]
        if date_from <= datetime.fromisoformat(row["at"]).astimezone(zone).date() <= date_to
    ]
    ambiguous = [
        decorate_event(row)
        for row in report["ambiguous_events"]
        if core.intersection(row["candidate_assignments"])
    ]
    report.update(
        rows=[decorate_row(row) for row in (rows if unpaginated else rows[offset : offset + limit])],
        unassigned_events=unassigned if unpaginated else unassigned[:300],
        ambiguous_events=ambiguous if unpaginated else ambiguous[:300],
        summary=summarize(rows, unassigned, ambiguous),
        period={
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "timezone": str(zone),
            "employee_id": employee_id,
            "employee_name": people[0].name if employee_id else None,
        },
        offset=offset,
        limit=limit,
        has_more=False if unpaginated else offset + limit < len(rows),
        exception_list_limit=None if unpaginated else 300,
        exception_lists_truncated=False if unpaginated else len(unassigned) > 300 or len(ambiguous) > 300,
        source_event_count=len(events),
        functional_trial_event_count=len(trial_event_ids),
        source_assignment_count=len(assignments),
        source_adjustment_count=len(corrections),
    )
    if unpaginated:
        protection = {
            "base_from": datetime.combine(date_from, time(), tzinfo=zone).astimezone(UTC).isoformat(),
            "base_to": datetime.combine(date_to + timedelta(days=1), time(), tzinfo=zone)
            .astimezone(UTC)
            .isoformat(),
            "windows": {},
        }
        for schedule in schedules:
            if schedule.id not in core:
                continue
            start, end = shift_interval(schedule.shift, schedule.work_date)
            rules, _ = rules_for(schedule)
            window = [
                (start - timedelta(minutes=rules.get("capture_before_minutes", 120))).isoformat(),
                (end + timedelta(minutes=rules.get("capture_after_minutes", 120))).isoformat(),
            ]
            protection["windows"].setdefault(schedule.employee_id, []).append(window)
        report["_protection"] = protection
        report["employee_catalog"] = {
            person.id: {"code": person.code, "name": person.name} for person in people
        }
    return report


@router.get("/preview")
async def preview(
    date_from: date,
    date_to: date,
    db: Db,
    user: Admin,
    employee_id: str | None = None,
    offset: int = 0,
    limit: int = 100,
):
    if not slots.acquire(blocking=False):
        raise HTTPException(
            429, "Đang tính các bảng công khác. Vui lòng thử lại sau một chút.", headers={"Retry-After": "1"}
        )
    try:
        return await run_in_threadpool(build_report, db, date_from, date_to, employee_id, offset, limit)
    except (ValueError, OverflowError, ZoneInfoNotFoundError) as error:
        raise HTTPException(
            422, "Quy tắc ca, ngày hoặc múi giờ chưa hợp lệ; chưa tạo kết quả bảng công."
        ) from error
    except SQLAlchemyError as error:
        raise HTTPException(
            503, "Chưa đọc đủ dữ liệu từ database; chưa có kết quả bảng công hợp lệ. Vui lòng thử lại."
        ) from error
    finally:
        slots.release()
