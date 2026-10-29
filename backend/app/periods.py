"""Monthly close creates immutable versions; reopen preserves every snapshot."""

import copy
import re
from calendar import monthrange
from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException
from pydantic import Field
from sqlalchemy import select

from .auth import Admin, Db, MutationAdmin
from .calendar_guard import lock_calendar
from .devices import aware
from .models import AuditLog, TimesheetPeriod, TimesheetSnapshot
from .shifts import ReasonInput
from .timesheets import build_report, summarize

router = APIRouter(prefix="/api/admin/timesheets/periods", tags=["timesheets"])


class PeriodInput(ReasonInput):
    expected_revision: int = Field(ge=0)


class CloseInput(PeriodInput):
    allow_unresolved: bool = False


def month_dates(month):
    if not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month):
        raise HTTPException(422, "Kỳ công có dạng YYYY-MM.")
    year, number = map(int, month.split("-"))
    if not 1900 <= year <= 9998:
        raise HTTPException(422, "Năm kỳ công phải thuộc 1900–9998.")
    return date(year, number, 1), date(year, number, monthrange(year, number)[1])


def describe_period(db, month):
    month_dates(month)
    period = db.get(TimesheetPeriod, month)
    snapshots = db.scalars(
        select(TimesheetSnapshot)
        .where(TimesheetSnapshot.month == month)
        .order_by(TimesheetSnapshot.revision.desc())
    ).all()
    return {
        "month": month,
        "status": period.status if period else "open",
        "revision": period.revision if period else 0,
        "locked_at": aware(period.locked_at).isoformat() if period and period.locked_at else None,
        "snapshots": [
            {
                "revision": row.revision,
                "id": row.id,
                "created_at": aware(row.created_at).isoformat(),
                "created_by": row.created_by,
                "reason": row.reason,
                "source_digest": row.source_digest,
                "summary": row.payload["summary"],
            }
            for row in snapshots
        ],
    }


def close_period(db, month, payload, user, now=None):
    begin, end = month_dates(month)
    lock_calendar(db)
    period = db.scalar(
        select(TimesheetPeriod)
        .where(TimesheetPeriod.month == month)
        .execution_options(populate_existing=True)
    )
    if period and period.status == "locked":
        raise HTTPException(409, "Kỳ đã khóa. Hãy tải lại trạng thái và bản chốt.")
    if (period.revision if period else 0) != payload.expected_revision:
        raise HTTPException(409, "Phiên bản kỳ đã thay đổi. Hãy tải lại trước khi khóa.")
    now = now or datetime.now(UTC)
    report = build_report(db, begin, end, as_of=now, unpaginated=True)
    protection = report.pop("_protection")
    if now < datetime.fromisoformat(protection["base_to"]):
        raise HTTPException(409, "Chỉ khóa kỳ đã kết thúc theo múi giờ nghiệp vụ.")
    bounds = [datetime.fromisoformat(protection["base_from"]), datetime.fromisoformat(protection["base_to"])]
    for windows in protection["windows"].values():
        for left, right in windows:
            bounds.extend([datetime.fromisoformat(left), datetime.fromisoformat(right)])
            if now <= datetime.fromisoformat(right):
                raise HTTPException(409, "Còn ca trong kỳ chưa hết cửa sổ nhận lượt quét; chưa được khóa.")
    unresolved = (
        any(row["status"] != "complete" for row in report["rows"])
        or report["summary"]["unassigned_count"]
        or report["summary"]["ambiguous_count"]
    )
    if unresolved and not payload.allow_unresolved:
        raise HTTPException(
            409,
            "Kỳ còn thiếu lượt hoặc lượt chưa gắn ca/mơ hồ. Sửa trước hoặc xác nhận khóa kèm ngoại lệ; không tự quy đổi thành đủ công.",
        )
    if not period:
        period = TimesheetPeriod(month=month, revision=0, status="open")
        db.add(period)
    period.revision += 1
    period.status, period.locked_at = "locked", now
    period.protected_from, period.protected_until = min(bounds), max(bounds)
    report.update(finalized=True, snapshot_revision=period.revision, locked_with_unresolved=bool(unresolved))
    db.flush()
    snapshot = TimesheetSnapshot(
        month=month,
        revision=period.revision,
        created_at=now,
        created_by=user.id,
        reason=payload.reason,
        source_digest=report["source_digest"],
        calculation_version=report["calculation_version"],
        payload=report,
        protection=protection,
    )
    db.add(snapshot)
    db.flush()
    db.add(
        AuditLog(
            action="timesheet_period_lock",
            entity_id=snapshot.id,
            reason=payload.reason,
            details={
                "month": month,
                "revision": period.revision,
                "admin_id": user.id,
                "allow_unresolved": payload.allow_unresolved,
                "source_digest": snapshot.source_digest,
                "before": {"status": "open", "revision": period.revision - 1},
                "after": {"status": "locked", "revision": period.revision, "snapshot_id": snapshot.id},
            },
        )
    )
    result = describe_period(db, month)
    db.commit()
    return result


def reopen_period(db, month, payload, user):
    month_dates(month)
    lock_calendar(db)
    period = db.scalar(
        select(TimesheetPeriod)
        .where(TimesheetPeriod.month == month)
        .execution_options(populate_existing=True)
    )
    if not period or period.status != "locked" or period.revision != payload.expected_revision:
        raise HTTPException(409, "Kỳ không còn ở trạng thái/phiên bản đã chọn. Hãy tải lại.")
    period.status = "open"
    db.add(
        AuditLog(
            action="timesheet_period_reopen",
            entity_id=month,
            reason=payload.reason,
            details={
                "revision": period.revision,
                "admin_id": user.id,
                "before": {"status": "locked", "revision": period.revision},
                "after": {"status": "open", "revision": period.revision},
            },
        )
    )
    result = describe_period(db, month)
    db.commit()
    return result


def snapshot_report(db, month, revision=None, employee_id=None, offset=0, limit=100, *, unpaginated=False):
    month_dates(month)
    if offset < 0 or not 1 <= limit <= 300 or (revision is not None and revision < 1):
        raise HTTPException(422, "Trang bản chốt phải có 1–300 ca và phiên bản hợp lệ.")
    query = select(TimesheetSnapshot).where(TimesheetSnapshot.month == month)
    if revision is not None:
        query = query.where(TimesheetSnapshot.revision == revision)
    row = db.scalar(query.order_by(TimesheetSnapshot.revision.desc()).limit(1))
    if not row:
        raise HTTPException(404, "Chưa có bản chốt của kỳ/phiên bản này.")
    period = db.get(TimesheetPeriod, month)
    report = copy.deepcopy(row.payload)
    catalog = report.pop("employee_catalog")
    if employee_id and employee_id not in catalog:
        raise HTTPException(404, "Nhân viên không thuộc danh sách trong bản chốt.")
    rows = [item for item in report["rows"] if not employee_id or item["employee_id"] == employee_id]
    unassigned = [
        item for item in report["unassigned_events"] if not employee_id or item["employee_id"] == employee_id
    ]
    ambiguous = [
        item for item in report["ambiguous_events"] if not employee_id or item["employee_id"] == employee_id
    ]
    report.update(
        rows=rows if unpaginated else rows[offset : offset + limit],
        unassigned_events=unassigned if unpaginated else unassigned[:300],
        ambiguous_events=ambiguous if unpaginated else ambiguous[:300],
        summary=summarize(rows, unassigned, ambiguous),
        offset=offset,
        limit=limit,
        has_more=False if unpaginated else offset + limit < len(rows),
        exception_list_limit=None if unpaginated else 300,
        exception_lists_truncated=False if unpaginated else len(unassigned) > 300 or len(ambiguous) > 300,
        snapshot_id=row.id,
        snapshot_revision=row.revision,
        snapshot_reason=row.reason,
        is_current=period.status == "locked" and period.revision == row.revision,
        employee_catalog=catalog,
    )
    report["period"].update(
        employee_id=employee_id, employee_name=catalog[employee_id]["name"] if employee_id else None
    )
    return report


@router.get("/{month}")
def state(month: str, db: Db, user: Admin):
    return describe_period(db, month)


@router.post("/{month}/lock")
def close(month: str, payload: CloseInput, db: Db, user: MutationAdmin):
    return close_period(db, month, payload, user)


@router.post("/{month}/reopen")
def reopen(month: str, payload: PeriodInput, db: Db, user: MutationAdmin):
    return reopen_period(db, month, payload, user)


@router.get("/{month}/snapshot")
def snapshot(
    month: str,
    db: Db,
    user: Admin,
    revision: int | None = None,
    employee_id: str | None = None,
    offset: int = 0,
    limit: int = 100,
):
    return snapshot_report(db, month, revision, employee_id, offset, limit)
