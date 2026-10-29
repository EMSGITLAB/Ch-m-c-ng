from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .auth import Admin, Db, MutationAdmin
from .biometric_state import lock_employee
from .calendar_guard import assert_schedule_writable, lock_calendar
from .config import get_settings
from .models import AuditLog, Employee, Shift, ShiftAssignment
from .shift_rules import ShiftInput, describe_shift, minute, overlaps, shift_interval

router = APIRouter(prefix="/api/admin", tags=["shifts"])


class ReasonInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=5, max_length=500)


class AssignInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shift_id: str = Field(min_length=1, max_length=36)
    employee_ids: list[str] = Field(min_length=1, max_length=100)
    date_from: date
    date_to: date
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)), min_length=1, max_length=7)

    @model_validator(mode="after")
    def validate_selection(self):
        if len(set(self.employee_ids)) != len(self.employee_ids) or any(
            len(value) > 36 for value in self.employee_ids
        ):
            raise ValueError("Danh sách nhân viên phải duy nhất và hợp lệ.")
        if len(set(self.weekdays)) != len(self.weekdays) or any(day not in range(7) for day in self.weekdays):
            raise ValueError("Thứ trong tuần phải duy nhất và thuộc 0..6 (thứ Hai..Chủ nhật).")
        if not 0 <= (self.date_to - self.date_from).days <= 30:
            raise ValueError("Mỗi lần phân ca trong khoảng 1–31 ngày.")
        return self


def configured_timezone():
    timezone = get_settings().business().timezone
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as error:
        raise HTTPException(503, "Múi giờ nghiệp vụ chưa hợp lệ.") from error
    return timezone


def create_definition(payload, timezone, **version):
    return Shift(
        name=payload.name,
        start_minute=minute(payload.start),
        end_minute=minute(payload.end),
        rules=payload.normalized_rules(),
        timezone=timezone,
        **version,
    )


@router.get("/shifts")
def list_shifts(db: Db, user: Admin, include_archived: bool = False):
    query = select(Shift).order_by(Shift.name, Shift.revision.desc())
    if not include_archived:
        query = query.where(Shift.archived_at.is_(None))
    return {"items": [describe_shift(row) for row in db.scalars(query).all()]}


@router.post("/shifts", status_code=201)
def create_shift(payload: ShiftInput, db: Db, user: MutationAdmin):
    row = create_definition(payload, configured_timezone())
    db.add(row)
    db.flush()
    db.add(AuditLog(action="shift_create", entity_id=row.id, details=describe_shift(row)))
    db.commit()
    return describe_shift(row)


@router.post("/shifts/{shift_id}/revisions", status_code=201)
def revise_shift(shift_id: str, payload: ShiftInput, db: Db, user: MutationAdmin):
    previous = db.get(Shift, shift_id)
    if not previous:
        raise HTTPException(404, "Không có ca làm.")
    changed = db.execute(
        update(Shift)
        .where(Shift.id == shift_id, Shift.archived_at.is_(None))
        .values(archived_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "Phiên bản ca đã thay đổi hoặc ngừng dùng. Hãy tải lại danh sách.")
    row = create_definition(
        payload, previous.timezone, family_id=previous.family_id, revision=previous.revision + 1
    )
    db.add(row)
    try:
        db.flush()
        db.add(
            AuditLog(
                action="shift_revise",
                entity_id=row.id,
                details={"previous_id": shift_id, "revision": row.revision},
            )
        )
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Ca đã có phiên bản mới. Hãy tải lại danh sách.") from error
    return describe_shift(row)


@router.post("/shifts/{shift_id}/archive")
def archive_shift(shift_id: str, payload: ReasonInput, db: Db, user: MutationAdmin):
    row = db.get(Shift, shift_id)
    if not row:
        raise HTTPException(404, "Không có ca làm.")
    changed = db.execute(
        update(Shift)
        .where(Shift.id == shift_id, Shift.archived_at.is_(None))
        .values(archived_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
    if changed.rowcount:
        db.add(AuditLog(action="shift_archive", entity_id=shift_id, reason=payload.reason, details={}))
    db.refresh(row)
    result = describe_shift(row)
    db.commit()
    return result


@router.post("/shift-assignments", status_code=201)
def assign_shift(payload: AssignInput, db: Db, user: MutationAdmin):
    lock_calendar(db)
    employees = db.scalars(select(Employee).where(Employee.id.in_(payload.employee_ids))).all()
    if len(employees) != len(payload.employee_ids):
        raise HTTPException(404, "Có hồ sơ nhân viên không tồn tại; chưa phân ca nào.")
    for employee_id in sorted(payload.employee_ids):
        lock_employee(db, employee_id, active_only=True)
    locked = db.execute(
        update(Shift)
        .where(Shift.id == payload.shift_id, Shift.archived_at.is_(None))
        .values(name=Shift.name)
        .returning(Shift.id)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    if not locked:
        raise HTTPException(409, "Ca đã ngừng dùng hoặc thay phiên bản. Hãy chọn ca hiện tại.")
    shift = db.get(Shift, payload.shift_id)
    dates = [
        payload.date_from + timedelta(days=offset)
        for offset in range((payload.date_to - payload.date_from).days + 1)
    ]
    assert_schedule_writable(
        db, payload.employee_ids, shift, [day for day in dates if day.weekday() in payload.weekdays]
    )
    existing = db.execute(
        select(ShiftAssignment, Shift)
        .join(Shift)
        .where(
            ShiftAssignment.employee_id.in_(payload.employee_ids),
            ShiftAssignment.cancelled_at.is_(None),
            ShiftAssignment.work_date.between(
                payload.date_from - timedelta(days=1) if payload.date_from > date.min else date.min,
                payload.date_to + timedelta(days=1) if payload.date_to < date.max else date.max,
            ),
        )
    ).all()
    occupied = {employee_id: [] for employee_id in payload.employee_ids}
    try:
        for assignment, definition in existing:
            occupied[assignment.employee_id].append(shift_interval(definition, assignment.work_date))
        rows = []
        for offset in range((payload.date_to - payload.date_from).days + 1):
            work_date = payload.date_from + timedelta(days=offset)
            if work_date.weekday() not in payload.weekdays:
                continue
            interval = shift_interval(shift, work_date)
            for employee_id in sorted(payload.employee_ids):
                if any(overlaps(interval, current) for current in occupied[employee_id]):
                    raise HTTPException(
                        409, f"Có lịch chồng ca vào ngày {work_date.isoformat()}; chưa phân ca nào."
                    )
                occupied[employee_id].append(interval)
                rows.append(ShiftAssignment(employee_id=employee_id, shift_id=shift.id, work_date=work_date))
    except (ValueError, OverflowError) as error:
        raise HTTPException(422, str(error)) from error
    if not rows:
        raise HTTPException(422, "Khoảng ngày không có thứ đã chọn; chưa phân ca nào.")
    db.add_all(rows)
    db.add(
        AuditLog(
            action="shift_assign",
            details={
                "shift_id": shift.id,
                "count": len(rows),
                "date_from": payload.date_from.isoformat(),
                "date_to": payload.date_to.isoformat(),
            },
        )
    )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            409, "Lịch đã thay đổi hoặc trùng; chưa phân ca nào. Hãy tải lại lịch."
        ) from error
    return {"created_count": len(rows)}


@router.get("/shift-assignments")
def list_assignments(
    date_from: date,
    date_to: date,
    db: Db,
    user: Admin,
    employee_id: str | None = None,
    include_cancelled: bool = False,
    offset: int = 0,
    limit: int = 100,
):
    if not 0 <= (date_to - date_from).days <= 92 or offset < 0 or not 1 <= limit <= 300:
        raise HTTPException(422, "Tra cứu tối đa 93 ngày, mỗi trang 1–300 lịch.")
    query = (
        select(ShiftAssignment, Shift, Employee)
        .join(Shift)
        .join(Employee, Employee.id == ShiftAssignment.employee_id)
    )
    query = query.where(ShiftAssignment.work_date.between(date_from, date_to))
    if employee_id:
        query = query.where(ShiftAssignment.employee_id == employee_id)
    if not include_cancelled:
        query = query.where(ShiftAssignment.cancelled_at.is_(None))
    rows = db.execute(
        query.order_by(ShiftAssignment.work_date, Employee.code, Shift.start_minute, ShiftAssignment.id)
        .offset(offset)
        .limit(limit + 1)
    ).all()
    result = []
    for assignment, shift, employee in rows[:limit]:
        begin, end = shift_interval(shift, assignment.work_date)
        result.append(
            {
                "id": assignment.id,
                "employee_id": employee.id,
                "employee_code": employee.code,
                "employee_name": employee.name,
                "work_date": assignment.work_date.isoformat(),
                "shift": describe_shift(shift),
                "start_at": begin.isoformat(),
                "end_at": end.isoformat(),
                "cancelled": assignment.cancelled_at is not None,
                "cancel_reason": assignment.cancel_reason,
            }
        )
    return {"items": result, "has_more": len(rows) > limit, "offset": offset, "limit": limit}


@router.post("/shift-assignments/{assignment_id}/cancel")
def cancel_assignment(assignment_id: str, payload: ReasonInput, db: Db, user: MutationAdmin):
    lock_calendar(db)
    row = db.get(ShiftAssignment, assignment_id)
    if not row:
        raise HTTPException(404, "Không có lịch phân ca.")
    lock_employee(db, row.employee_id)
    db.refresh(row)
    if row.cancelled_at is None:
        assert_schedule_writable(db, [row.employee_id], db.get(Shift, row.shift_id), [row.work_date])
        row.cancelled_at = datetime.now(UTC)
        row.cancel_reason = payload.reason
        db.add(
            AuditLog(
                action="shift_assignment_cancel",
                entity_id=row.id,
                reason=payload.reason,
                details={"work_date": row.work_date.isoformat()},
            )
        )
    db.commit()
    return {"id": row.id, "cancelled": True}
