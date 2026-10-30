"""Administrative setup for isolated partner attendance batches."""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .auth import Admin, Db, MutationAdmin
from .calendar_guard import lock_calendar
from .devices import aware
from .employees import EmployeeInput
from .models import AuditLog, Device, PartnerBatch, PartnerDeviceBinding, PartnerVendor
from .policy_selection import selected_policy
from .recognition_sequence import require_policy
from .shift_rules import ShiftInput, minute, shift_interval
from .shifts import configured_timezone

router = APIRouter(prefix="/api/admin/partners", tags=["partner-attendance"])


class VendorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=160)

    @field_validator("code", mode="before")
    @classmethod
    def clean_code(cls, value):
        return EmployeeInput.clean_code(value)

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value):
        return EmployeeInput.clean_text(value)


class VendorPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=160)
    active: bool

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value):
        return EmployeeInput.clean_text(value)


class BatchInput(ShiftInput):
    request_id: UUID = Field(default_factory=uuid4)
    partner_id: UUID
    work_date: date
    site: str = Field(min_length=2, max_length=120)
    capacity: int = Field(ge=1, le=5000)
    requested_count: int | None = Field(default=None, ge=1, le=5000)

    @field_validator("site", mode="before")
    @classmethod
    def clean_site(cls, value):
        return EmployeeInput.clean_text(value)


class ReasonInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=5, max_length=500)


class BatchTransition(ReasonInput):
    expected_state: Literal["draft", "open", "running", "review", "closed"]
    state: Literal["open", "running", "review", "closed"]


class CapacityInput(ReasonInput):
    expected_capacity: int = Field(ge=1, le=5000)
    capacity: int = Field(ge=1, le=5000)


class BindingInput(ReasonInput):
    batch_id: UUID


def batch_of(db, batch_id):
    row = db.get(PartnerBatch, str(batch_id), populate_existing=True)
    if row is None:
        raise HTTPException(404, "Không tìm thấy đợt chấm công đối tác.")
    return row


def vendor_of(db, partner_id):
    row = db.get(PartnerVendor, str(partner_id), populate_existing=True)
    if row is None:
        raise HTTPException(404, "Không tìm thấy đối tác.")
    return row


def describe_vendor(row):
    return {"id": row.id, "code": row.code, "name": row.name, "active": row.active}


def describe_batch(row):
    return {"id": row.id, "partner_id": row.partner_id, "request_id": row.request_id,
            "name": row.name, "site": row.site, "work_date": row.work_date.isoformat(),
            "timezone": row.timezone, "starts_at": aware(row.starts_at).isoformat(),
            "ends_at": aware(row.ends_at).isoformat(), "admission_from": aware(row.admission_from).isoformat(),
            "checkout_until": aware(row.checkout_until).isoformat(), "rules": row.rules,
            "capacity": row.capacity, "requested_count": row.requested_count, "allocated_numbers": row.next_number, "state": row.state,
            "retention_hours": row.retention_hours, "admission_mode": "automatic",
            "model_id": row.model_id, "policy_id": row.policy_id,
            "threshold": row.threshold, "minimum_margin": row.minimum_margin,
            "group_accuracy_validated": False, "pad_validated": False}


def audit(db, user, action, identity, *, reason=None, **details):
    db.add(AuditLog(action=action, entity_id=identity, reason=reason, details={"admin_id": user.id, **details}))


@router.get("")
def vendors(db: Db, user: Admin):
    return {"items": [describe_vendor(row) for row in db.scalars(select(PartnerVendor).order_by(PartnerVendor.code))]}


@router.post("", status_code=201)
def create_vendor(payload: VendorInput, db: Db, user: MutationAdmin):
    row = PartnerVendor(**payload.model_dump())
    db.add(row)
    try:
        db.flush()
        audit(db, user, "partner_create", row.id, code=row.code)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "Mã đối tác đã tồn tại.") from error
    return describe_vendor(row)


@router.patch("/{partner_id}")
def update_vendor(partner_id: UUID, payload: VendorPatch, db: Db, user: MutationAdmin):
    lock_calendar(db)
    row = vendor_of(db, partner_id)
    if not payload.active and db.scalar(select(PartnerBatch.id).where(
        PartnerBatch.partner_id == row.id, PartnerBatch.state != "closed").limit(1)):
        raise HTTPException(409, "Đối tác còn đợt chưa đóng. Cần xử lý các đợt trước khi ngừng sử dụng.")
    row.name, row.active = payload.name, payload.active
    audit(db, user, "partner_update", row.id, active=row.active)
    db.commit()
    return describe_vendor(row)


@router.get("/batches/list")
def batches(db: Db, user: Admin, date_from: date, date_to: date, partner_id: UUID | None = None,
            offset: int = 0, limit: int = 50, site: str | None = None):
    if not 0 <= (date_to-date_from).days <= 92 or offset < 0 or not 1 <= limit <= 100:
        raise HTTPException(422, "Tra cứu tối đa 93 ngày và 100 đợt mỗi trang.")
    query = select(PartnerBatch).where(PartnerBatch.work_date.between(date_from, date_to))
    if partner_id:
        query = query.where(PartnerBatch.partner_id == str(partner_id))
    if site:
        if len(site) > 120:
            raise HTTPException(422, "Sàn/vị trí tối đa 120 ký tự.")
        query = query.where(PartnerBatch.site.contains(site, autoescape=True))
    rows = db.scalars(query.order_by(PartnerBatch.work_date.desc(), PartnerBatch.created_at.desc(), PartnerBatch.id)
                      .offset(offset).limit(limit+1)).all()
    return {"items": [describe_batch(row) for row in rows[:limit]], "has_more": len(rows) > limit}


@router.post("/batches", status_code=201)
def create_batch(payload: BatchInput, db: Db, user: MutationAdmin):
    lock_calendar(db)
    material = payload.model_dump(mode="json")
    if material["requested_count"] is None:
        material.pop("requested_count")
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    previous = db.scalar(select(PartnerBatch).where(PartnerBatch.request_id == str(payload.request_id)))
    if previous:
        if previous.request_digest != digest:
            raise HTTPException(409, "Mã yêu cầu đã dùng cho dữ liệu khác. Hãy tải lại kết quả trước khi tạo đợt mới.")
        return describe_batch(previous)
    vendor = vendor_of(db, payload.partner_id)
    if not vendor.active:
        raise HTTPException(409, "Đối tác đã ngừng sử dụng.")
    zone = configured_timezone()
    definition = SimpleNamespace(start_minute=minute(payload.start), end_minute=minute(payload.end), timezone=zone)
    try:
        start, end = shift_interval(definition, payload.work_date)
        before = start-timedelta(minutes=payload.capture_before_minutes)
        after = end+timedelta(minutes=payload.capture_after_minutes)
    except (ValueError, OverflowError) as error:
        raise HTTPException(422, "Ngày/giờ đợt không hợp lệ trong múi giờ đã cấu hình.") from error
    row = PartnerBatch(request_id=str(payload.request_id), request_digest=digest, partner_id=vendor.id,
                       name=payload.name, site=payload.site, work_date=payload.work_date, timezone=zone,
                       starts_at=start, ends_at=end, admission_from=before, checkout_until=after,
                       rules=payload.normalized_rules(), capacity=payload.capacity,
                       requested_count=payload.requested_count if payload.requested_count is not None else payload.capacity)
    db.add(row)
    db.flush()
    audit(db, user, "partner_batch_create", row.id, partner_id=vendor.id, capacity=row.capacity)
    db.commit()
    return describe_batch(row)


@router.post("/batches/{batch_id}/state")
def transition_batch(batch_id: UUID, payload: BatchTransition, request: Request, db: Db, user: MutationAdmin):
    if payload.state == "closed":
        raise HTTPException(409, "Mở bảng đối soát, kiểm tra dữ liệu rồi dùng chức năng Chốt đợt để lưu bản chốt bất biến.")
    lock_calendar(db)
    row = batch_of(db, batch_id)
    if row.state == payload.state:
        return describe_batch(row)
    if row.state != payload.expected_state:
        raise HTTPException(409, "Trạng thái đợt đã thay đổi. Hãy tải lại.")
    allowed = {"draft": {"open"}, "open": {"running", "review"}, "running": {"review"}, "review": {"closed"}, "closed": set()}
    if payload.state not in allowed[row.state]:
        raise HTTPException(409, "Không được chuyển trạng thái này hoặc mở lại đợt đã chốt.")
    previous = row.state
    if previous == "draft":
        if not vendor_of(db, row.partner_id).active:
            raise HTTPException(409, "Đối tác đã ngừng sử dụng.")
        engine = getattr(request.app.state, "face_engine", None)
        if engine is None:
            raise HTTPException(503, "Model nhận diện local chưa sẵn sàng.")
        policy = require_policy(db, selected_policy(db, getattr(request.app.state, "attendance_policy_id", None)),
                                engine.model_id, datetime.now(UTC), lock=True, validate_gallery=False)
        row.policy_id, row.model_id = policy.id, policy.model_id
        row.threshold, row.minimum_margin = policy.threshold, policy.minimum_margin
        row.rules = {**row.rules, "recognition_mode": policy.mode,
                     "functional_trial": policy.mode == "functional_trial"}
    row.state = payload.state
    audit(db, user, "partner_batch_state", row.id, reason=payload.reason, before=previous, after=row.state)
    db.commit()
    return describe_batch(row)


@router.post("/batches/{batch_id}/capacity")
def change_capacity(batch_id: UUID, payload: CapacityInput, db: Db, user: MutationAdmin):
    lock_calendar(db)
    row = batch_of(db, batch_id)
    if row.state in {"review", "closed"} or row.capacity != payload.expected_capacity:
        raise HTTPException(409, "Đợt đã ngừng ghi nhận hoặc hạn mức đã thay đổi.")
    if row.state != "draft" and payload.capacity < row.capacity:
        raise HTTPException(409, "Đợt đã mở chỉ được tăng hạn mức; không giảm dưới các chỗ đang tiếp nhận.")
    old = row.capacity
    row.capacity = payload.capacity
    audit(db, user, "partner_batch_capacity", row.id, reason=payload.reason, before=old, after=row.capacity)
    db.commit()
    return describe_batch(row)


@router.get("/devices/list")
def bindings(db: Db, user: Admin):
    rows = db.scalars(select(PartnerDeviceBinding)).all()
    return {"items": [{"device_id": row.device_id, "batch_id": row.batch_id, "active": row.active} for row in rows]}


@router.put("/devices/{device_id}")
def bind_device(device_id: UUID, payload: BindingInput, db: Db, user: MutationAdmin):
    lock_calendar(db)
    batch = batch_of(db, payload.batch_id)
    device = db.get(Device, str(device_id), populate_existing=True)
    if device is None or not device.active:
        raise HTTPException(404, "Không có thiết bị đang hoạt động.")
    if batch.state in {"review", "closed"}:
        raise HTTPException(409, "Đợt đã ngừng nhận lượt mới.")
    row = db.get(PartnerDeviceBinding, device.id, populate_existing=True)
    if row is None:
        row = PartnerDeviceBinding(device_id=device.id, batch_id=batch.id)
        db.add(row)
    else:
        row.batch_id, row.active = batch.id, True
    audit(db, user, "partner_device_bind", device.id, reason=payload.reason, batch_id=batch.id)
    db.commit()
    return {"device_id": device.id, "batch_id": batch.id, "active": True}


@router.post("/devices/{device_id}/unbind")
def unbind_device(device_id: UUID, payload: ReasonInput, db: Db, user: MutationAdmin):
    lock_calendar(db)
    row = db.get(PartnerDeviceBinding, str(device_id))
    if row is None:
        raise HTTPException(404, "Thiết bị chưa gắn đợt đối tác.")
    row.active = False
    audit(db, user, "partner_device_unbind", str(device_id), reason=payload.reason, batch_id=row.batch_id)
    db.commit()
    return {"device_id": str(device_id), "active": False}
