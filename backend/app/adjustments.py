"""Audited corrections overlay original punches; raw attendance stays immutable."""

import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import AwareDatetime, Field, NaiveDatetime, model_validator
from sqlalchemy import select

from .auth import Admin, Db, MutationAdmin
from .biometric_state import lock_employee
from .calendar_guard import assert_event_writable, lock_calendar
from .config import get_settings
from .devices import aware
from .models import AttendanceAdjustment, AttendanceEvent, AuditLog, Employee
from .shift_rules import local_instant
from .shifts import ReasonInput
from .timesheet_engine import Punch

router = APIRouter(prefix="/api/admin/timesheets/adjustments", tags=["timesheets"])


class AdjustmentInput(ReasonInput):
    request_id: UUID
    employee_id: str = Field(min_length=1, max_length=36)
    kind: Literal["add", "void"]
    direction: Literal["in", "out"] | None = None
    occurred_at: AwareDatetime | None = None
    local_time: NaiveDatetime | None = None
    target_event_id: str | None = Field(default=None, min_length=1, max_length=36)
    target_adjustment_id: str | None = Field(default=None, min_length=1, max_length=36)

    @model_validator(mode="after")
    def valid_target(self):
        targets = bool(self.target_event_id) + bool(self.target_adjustment_id)
        if self.kind == "add":
            if targets or self.direction is None or (self.occurred_at is None) == (self.local_time is None):
                raise ValueError("Bổ sung lượt cần chiều và thời gian; không có lượt đích.")
            if self.local_time is not None:
                self.occurred_at = local_instant(
                    self.local_time, ZoneInfo(get_settings().business().timezone)
                )
                self.local_time = None
            self.occurred_at = self.occurred_at.astimezone(UTC)
        elif (
            targets != 1
            or self.direction is not None
            or self.occurred_at is not None
            or self.local_time is not None
        ):
            raise ValueError("Loại lượt cần đúng một lượt đích; thời gian/chiều lấy từ dữ liệu gốc.")
        return self


def describe_adjustment(row):
    return {
        "id": row.id,
        "request_id": row.request_id,
        "employee_id": row.employee_id,
        "kind": row.kind,
        "direction": row.direction,
        "occurred_at": aware(row.occurred_at).isoformat(),
        "target_event_id": row.target_event_id,
        "target_adjustment_id": row.target_adjustment_id,
        "reason": row.reason,
        "created_at": aware(row.created_at).isoformat(),
        "created_by": row.created_by,
        "revoked_at": aware(row.revoked_at).isoformat() if row.revoked_at else None,
        "revoke_reason": row.revoke_reason,
    }


def correction_overlay(db, employee_ids, lower, upper, now, events):
    rows = db.scalars(
        select(AttendanceAdjustment)
        .where(
            AttendanceAdjustment.employee_id.in_(employee_ids),
            AttendanceAdjustment.revoked_at.is_(None),
            AttendanceAdjustment.occurred_at >= lower,
            AttendanceAdjustment.occurred_at <= upper,
            AttendanceAdjustment.occurred_at <= now,
        )
        .order_by(AttendanceAdjustment.id)
        .limit(100001)
    ).all()
    if len(rows) > 100000:
        raise HTTPException(413, "Quá nhiều điều chỉnh. Hãy thu hẹp báo cáo.")
    void_events = {row.target_event_id for row in rows if row.kind == "void"}
    void_adds = {row.target_adjustment_id for row in rows if row.kind == "void"}
    punches = [
        Punch(row.id, row.employee_id, row.direction, aware(row.server_time).astimezone(UTC))
        for row in events
        if row.id not in void_events
    ]
    punches.extend(
        Punch("adjustment:" + row.id, row.employee_id, row.direction, aware(row.occurred_at).astimezone(UTC))
        for row in rows
        if row.kind == "add" and row.id not in void_adds
    )
    return punches, [describe_adjustment(row) for row in rows]


def create_adjustment(db, payload, user, now=None):
    now = now or datetime.now(UTC)
    lock_calendar(db)
    digest = hashlib.sha256(json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    previous = db.scalar(
        select(AttendanceAdjustment).where(AttendanceAdjustment.request_id == str(payload.request_id))
    )
    if previous:
        if previous.request_digest != digest:
            raise HTTPException(409, "Mã yêu cầu đã dùng cho nội dung khác. Hãy tải lại lịch sử điều chỉnh.")
        result = describe_adjustment(previous)
        db.commit()
        return result
    if not db.get(Employee, payload.employee_id):
        raise HTTPException(404, "Không có hồ sơ nhân viên.")
    lock_employee(db, payload.employee_id)
    direction, occurred_at = payload.direction, payload.occurred_at
    before = None
    if payload.kind == "void":
        target = (
            db.get(AttendanceEvent, payload.target_event_id)
            if payload.target_event_id
            else db.get(AttendanceAdjustment, payload.target_adjustment_id)
        )
        if not target or target.employee_id != payload.employee_id:
            raise HTTPException(404, "Không có lượt đích của nhân viên này.")
        if isinstance(target, AttendanceAdjustment) and (target.kind != "add" or target.revoked_at):
            raise HTTPException(409, "Chỉ loại được lượt bổ sung còn hiệu lực.")
        exists = db.scalar(
            select(AttendanceAdjustment.id).where(
                AttendanceAdjustment.kind == "void",
                AttendanceAdjustment.revoked_at.is_(None),
                (AttendanceAdjustment.target_event_id == payload.target_event_id)
                if payload.target_event_id
                else (AttendanceAdjustment.target_adjustment_id == payload.target_adjustment_id),
            )
        )
        if exists:
            raise HTTPException(409, "Lượt đã được loại bởi một điều chỉnh còn hiệu lực.")
        direction = target.direction
        occurred_at = aware(
            target.server_time if isinstance(target, AttendanceEvent) else target.occurred_at
        ).astimezone(UTC)
        before = {
            "id": target.id,
            "employee_id": target.employee_id,
            "direction": direction,
            "occurred_at": occurred_at.isoformat(),
            "included": True,
            "source": "manual" if isinstance(target, AttendanceAdjustment) else "camera",
        }
    if occurred_at > now:
        raise HTTPException(422, "Không bổ sung hoặc loại lượt ở thời điểm tương lai.")
    assert_event_writable(db, payload.employee_id, occurred_at)
    row = AttendanceAdjustment(
        request_id=str(payload.request_id),
        request_digest=digest,
        employee_id=payload.employee_id,
        kind=payload.kind,
        direction=direction,
        occurred_at=occurred_at,
        target_event_id=payload.target_event_id,
        target_adjustment_id=payload.target_adjustment_id,
        reason=payload.reason,
        created_at=now,
        created_by=user.id,
    )
    db.add(row)
    db.flush()
    result = describe_adjustment(row)
    db.add(
        AuditLog(
            action="attendance_adjustment_create",
            entity_id=row.id,
            reason=payload.reason,
            details={
                "kind": row.kind,
                "employee_id": row.employee_id,
                "admin_id": user.id,
                "before": before,
                "after": result,
            },
        )
    )
    db.commit()
    return result


def revoke_adjustment(db, identity, payload, user):
    lock_calendar(db)
    row = db.get(AttendanceAdjustment, identity)
    if not row:
        raise HTTPException(404, "Không có điều chỉnh này.")
    lock_employee(db, row.employee_id)
    if row.revoked_at is None:
        assert_event_writable(db, row.employee_id, aware(row.occurred_at).astimezone(UTC))
        if row.kind == "add" and db.scalar(
            select(AttendanceAdjustment.id).where(
                AttendanceAdjustment.target_adjustment_id == row.id, AttendanceAdjustment.revoked_at.is_(None)
            )
        ):
            raise HTTPException(409, "Cần thu hồi điều chỉnh loại lượt này trước khi thu hồi lượt bổ sung.")
        before = describe_adjustment(row)
        row.revoked_at, row.revoke_reason = datetime.now(UTC), payload.reason
        db.add(
            AuditLog(
                action="attendance_adjustment_revoke",
                entity_id=row.id,
                reason=payload.reason,
                details={"admin_id": user.id, "before": before, "after": describe_adjustment(row)},
            )
        )
    result = describe_adjustment(row)
    db.commit()
    return result


@router.post("", status_code=201)
def create(payload: AdjustmentInput, db: Db, user: MutationAdmin):
    return create_adjustment(db, payload, user)


@router.post("/{identity}/revoke")
def revoke(identity: str, payload: ReasonInput, db: Db, user: MutationAdmin):
    return revoke_adjustment(db, identity, payload, user)


@router.get("")
def history(
    date_from: date,
    date_to: date,
    db: Db,
    user: Admin,
    employee_id: str | None = None,
    offset: int = 0,
    limit: int = 100,
):
    if not 0 <= (date_to - date_from).days <= 30 or offset < 0 or not 1 <= limit <= 300:
        raise HTTPException(422, "Tra cứu tối đa 31 ngày; mỗi trang 1–300 điều chỉnh.")
    zone = ZoneInfo(get_settings().business().timezone)
    begin = datetime.combine(date_from, time(), tzinfo=zone).astimezone(UTC)
    end = datetime.combine(date_to + timedelta(days=1), time(), tzinfo=zone).astimezone(UTC)
    query = (
        select(AttendanceAdjustment, Employee)
        .join(Employee)
        .where(AttendanceAdjustment.occurred_at >= begin, AttendanceAdjustment.occurred_at < end)
    )
    if employee_id:
        query = query.where(Employee.id == employee_id)
    rows = db.execute(
        query.order_by(AttendanceAdjustment.created_at.desc(), AttendanceAdjustment.id)
        .offset(offset)
        .limit(limit + 1)
    ).all()
    return {
        "items": [
            describe_adjustment(row) | {"employee_code": person.code, "employee_name": person.name}
            for row, person in rows[:limit]
        ],
        "has_more": len(rows) > limit,
        "offset": offset,
        "limit": limit,
    }


@router.get("/events")
def raw_events(
    date_from: date,
    date_to: date,
    db: Db,
    user: Admin,
    employee_id: str | None = None,
    offset: int = 0,
    limit: int = 100,
):
    if (
        not 0 <= (date_to - date_from).days <= 30
        or date_to.year >= 9999
        or offset < 0
        or not 1 <= limit <= 300
    ):
        raise HTTPException(422, "Tra cứu tối đa 31 ngày; mỗi trang 1–300 lượt.")
    zone = ZoneInfo(get_settings().business().timezone)
    begin = datetime.combine(date_from, time(), tzinfo=zone).astimezone(UTC)
    end = datetime.combine(date_to + timedelta(days=1), time(), tzinfo=zone).astimezone(UTC)
    query = (
        select(AttendanceEvent, Employee)
        .join(Employee)
        .where(AttendanceEvent.server_time >= begin, AttendanceEvent.server_time < end)
    )
    if employee_id:
        query = query.where(Employee.id == employee_id)
    rows = db.execute(
        query.order_by(AttendanceEvent.server_time.desc(), AttendanceEvent.id).offset(offset).limit(limit + 1)
    ).all()
    ids = [row.id for row, _ in rows[:limit]]
    voided = set(
        db.scalars(
            select(AttendanceAdjustment.target_event_id).where(
                AttendanceAdjustment.target_event_id.in_(ids), AttendanceAdjustment.revoked_at.is_(None)
            )
        ).all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "employee_id": person.id,
                "employee_code": person.code,
                "employee_name": person.name,
                "direction": row.direction,
                "occurred_at": aware(row.server_time).isoformat(),
                "voided": row.id in voided,
            }
            for row, person in rows[:limit]
        ],
        "has_more": len(rows) > limit,
        "offset": offset,
        "limit": limit,
    }
