"""Partner work reconciliation. Camera events remain immutable under corrections."""

import copy
import csv
import hashlib
import io
import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import AwareDatetime, Field, NaiveDatetime, field_validator, model_validator
from sqlalchemy import select

from . import partner_attendance as attendance
from .auth import Admin, Db, MutationAdmin
from .calendar_guard import lock_calendar
from .devices import aware
from .employees import EmployeeInput
from .models import (
    AuditLog,
    PartnerEvent,
    PartnerReportAdjustment,
    PartnerReportSnapshot,
    PartnerVendor,
    PartnerWorker,
)
from .partner_admin import ReasonInput, batch_of, describe_batch, describe_vendor
from .shift_rules import local_instant
from .timesheet_exports import csv_text

router = APIRouter(prefix="/api/admin/partners", tags=["partner-reports"])
Filter = Literal["all", "complete", "incomplete", "pending"]
LABELS = {"complete": "Đủ Vào/Ra", "missing_out": "Chưa ghi lượt Ra", "missing_in": "Thiếu lượt Vào",
          "missing_both": "Thiếu Vào/Ra", "pending_name": "Chờ họ tên", "pending_approval": "Đang hoàn tất Vào tự động",
          "expired": "Hết phiên tiếp nhận", "cancelled": "Đã hủy tiếp nhận"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def iso(value):
    return aware(value).isoformat() if value else None


def history(row):
    return {"request_id": row.request_id, "worker_id": row.worker_id, "revision": row.revision,
            "overrides": row.overrides, "reason": row.reason, "admin_id": row.admin_id, "at": iso(row.created_at)}


def effective_row(batch, worker, events, corrections, now):
    raw = {row["direction"]: row["server_time"] for row in events}
    values = {"in_at": raw.get("in"), "out_at": raw.get("out"), "name": worker.declared_name}
    sources = {"in_at": "camera" if raw.get("in") else None, "out_at": "camera" if raw.get("out") else None, "name": "confirmed_name"}
    for correction in corrections:
        for key, value in correction["overrides"].items():
            values[key], sources[key] = value, "manual_adjustment"
    admitted = worker.state in {"active", "completed"} or "in" in raw
    start = datetime.fromisoformat(values["in_at"]) if values["in_at"] else None
    end = datetime.fromisoformat(values["out_at"]) if values["out_at"] else None
    if not admitted:
        status = "cancelled" if worker.state == "cancelled" else "expired" if aware(worker.pending_expires_at) <= now else "pending_name" if not worker.name_confirmed_at else "pending_approval"
    else:
        status = "complete" if start and end and end > start else "missing_out" if start else "missing_in" if end else "missing_both"
    expected = int((aware(batch.ends_at)-aware(batch.starts_at)).total_seconds())
    expected -= sum((row["end_offset"]-row["start_offset"])*60 for row in batch.rules.get("breaks", []) if not row["paid"])
    elapsed = worked = outside = unpaid = None
    if status == "complete":
        elapsed = int((end-start).total_seconds())
        begin, finish = max(start, aware(batch.starts_at)), min(end, aware(batch.ends_at))
        inside = max(0, int((finish-begin).total_seconds()))
        unpaid = 0
        for pause in batch.rules.get("breaks", []):
            if not pause["paid"]:
                left = aware(batch.starts_at)+timedelta(minutes=pause["start_offset"])
                right = aware(batch.starts_at)+timedelta(minutes=pause["end_offset"])
                unpaid += max(0, int((min(finish, right)-max(begin, left)).total_seconds()))
        worked, outside = max(0, inside-unpaid), elapsed-inside
    issues = []
    if admitted and "in" not in raw:
        issues.append("missing_original_camera_in")
    if start and end and end <= start:
        issues.append("invalid_interval")
    return {"worker_id": worker.id, "code": worker.code, "name": values["name"], "name_source": worker.name_source,
            "worker_state": worker.state, "admitted": admitted, "status": status, "status_label": LABELS[status],
            "raw_in_at": raw.get("in"), "raw_out_at": raw.get("out"), **values, "sources": sources,
            "elapsed_seconds": elapsed, "worked_seconds": worked, "unpaid_break_seconds": unpaid,
            "outside_shift_seconds": outside, "expected_seconds": expected, "issues": issues,
            "original_events": events, "adjustment_revision": len(corrections), "adjustments": corrections,
            "biometric_expires_at": iso(worker.biometric_expires_at),
            "biometric_time_expired": aware(worker.biometric_expires_at) <= now}


def build_report(db, batch_id, *, now=None):
    now = now or attendance.utcnow()
    batch = batch_of(db, batch_id)
    if batch.state == "closed":
        saved = db.get(PartnerReportSnapshot, batch.id)
        if saved is None:
            raise HTTPException(503, "Đợt đã đóng nhưng thiếu bản chốt; cần kiểm tra khôi phục, không tự dựng lại chứng từ.")
        if digest(saved.report) != saved.source_hash:
            raise HTTPException(503, "Bản chốt không khớp checksum; chưa xuất dữ liệu.")
        return copy.deepcopy(saved.report)
    vendor = db.get(PartnerVendor, batch.partner_id)
    workers = db.scalars(select(PartnerWorker).where(PartnerWorker.batch_id == batch.id).order_by(PartnerWorker.number).limit(20_001)).all()
    if len(workers) > 20_000:
        raise HTTPException(413, "Đợt vượt 20.000 phiên tiếp nhận; cần tách đợt để đối soát có giới hạn.")
    events = db.scalars(select(PartnerEvent).join(PartnerWorker, PartnerWorker.id == PartnerEvent.worker_id)
        .where(PartnerWorker.batch_id == batch.id).order_by(PartnerEvent.server_time, PartnerEvent.id)).all()
    corrections = db.scalars(select(PartnerReportAdjustment).where(PartnerReportAdjustment.batch_id == batch.id)
        .order_by(PartnerReportAdjustment.worker_id, PartnerReportAdjustment.revision)).all()
    by_worker, amended = defaultdict(list), defaultdict(list)
    for event in events:
        by_worker[event.worker_id].append({"id": event.id, "direction": event.direction,
            "server_time": iso(event.server_time), "device_id": event.device_id, "name": event.declared_name})
    for correction in corrections:
        amended[correction.worker_id].append(history(correction))
    definition = describe_batch(batch)
    rows = [effective_row(batch, worker, by_worker[worker.id], amended[worker.id], now) for worker in workers]
    material = {"schema": 1, "partner": describe_vendor(vendor), "batch": definition,
        "workers": [{"id": worker.id, "code": worker.code, "name": worker.declared_name, "state": worker.state,
            "confirmed_at": iso(worker.name_confirmed_at), "approved_at": iso(worker.approved_at),
            "expires_at": iso(worker.pending_expires_at), "admitted_at": iso(worker.admitted_at),
            "checked_out_at": iso(worker.checked_out_at), "events": by_worker[worker.id], "adjustments": amended[worker.id]} for worker in workers]}
    admitted = sum(row["admitted"] for row in rows)
    complete = sum(row["admitted"] and row["status"] == "complete" for row in rows)
    pending = sum(row["status"] in {"pending_name", "pending_approval"} for row in rows)
    return {"schema": 1, "source_hash": digest(material), "as_of": iso(now), "closed": False,
        "partner": describe_vendor(vendor), "batch": definition, "rows": rows,
        "summary": {"requested": batch.requested_count, "capacity": batch.capacity, "admitted": admitted,
            "complete": complete, "incomplete": admitted-complete, "without_recorded_out": sum(row["admitted"] and not row["raw_out_at"] for row in rows),
            "pending": pending, "cancelled_or_expired": len(rows)-admitted-pending,
            "available_slots": max(0, batch.capacity-admitted-pending),
            "short_of_requested": max(0, batch.requested_count-admitted),
            "total_worked_seconds": sum(row["worked_seconds"] or 0 for row in rows)},
        "note": ("Đợt chạy thử chức năng; chưa nghiệm thu độ chính xác/PAD, không dùng làm chứng từ thanh toán. " if batch.rules.get("functional_trial") else "")
                + "Chỉ tổng hợp cặp đủ Vào/Ra trong ca sau trừ nghỉ không lương. Thiếu Ra không tự tính đủ công. Chưa tính tiền hoặc hệ số ngoài giờ."}


class AdjustmentInput(ReasonInput):
    request_id: UUID
    expected_source: str = Field(pattern=r"^[a-f0-9]{64}$")
    in_at: AwareDatetime | None = None
    out_at: AwareDatetime | None = None
    in_local: NaiveDatetime | None = None
    out_local: NaiveDatetime | None = None
    name: str | None = Field(default=None, max_length=160)

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value):
        return EmployeeInput.clean_text(value) if value is not None else None

    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set & {"in_at", "out_at", "in_local", "out_local", "name"}:
            raise ValueError("Cần chọn dữ liệu điều chỉnh.")
        if any({direction+"_at", direction+"_local"} <= self.model_fields_set for direction in ("in", "out")):
            raise ValueError("Chỉ chọn một cách nhập thời gian cho mỗi chiều.")
        if "name" in self.model_fields_set and not self.name:
            raise ValueError("Không để trống họ tên khi điều chỉnh.")
        return self


class CloseInput(ReasonInput):
    request_id: UUID
    expected_source: str = Field(pattern=r"^[a-f0-9]{64}$")
    acknowledge_incomplete: bool = False


@router.get("/batches/{batch_id}/report")
def report(batch_id: UUID, db: Db, user: Admin):
    # Reads take the same short gate as writes to avoid mixing pre/post-punch rows.
    lock_calendar(db)
    result = build_report(db, str(batch_id))
    db.rollback()
    return result


@router.post("/workers/{worker_id}/adjustments")
def adjust(worker_id: UUID, payload: AdjustmentInput, db: Db, user: MutationAdmin):
    lock_calendar(db)
    request_hash = digest({"worker_id": str(worker_id), **payload.model_dump(mode="json", exclude_unset=True)})
    previous = db.get(PartnerReportAdjustment, str(payload.request_id))
    if previous:
        if previous.request_digest != request_hash:
            raise HTTPException(409, "Mã yêu cầu đã dùng cho điều chỉnh khác.")
        return {"adjustment": history(previous), "replayed": True}
    worker = db.get(PartnerWorker, str(worker_id), populate_existing=True)
    if not worker:
        raise HTTPException(404, "Không có lao động đối tác.")
    batch = batch_of(db, worker.batch_id)
    if batch.state != "review" or worker.state not in {"active", "completed"}:
        raise HTTPException(409, "Chỉ điều chỉnh lao động đã Vào khi đợt đang Chờ đối soát và chưa chốt.")
    current = build_report(db, batch.id)
    if current["source_hash"] != payload.expected_source:
        raise HTTPException(409, "Bảng công đã thay đổi. Tải lại trước khi sửa.")
    row = next(row for row in current["rows"] if row["worker_id"] == worker.id)
    overrides = payload.model_dump(mode="json", include=payload.model_fields_set & {"in_at", "out_at", "name"})
    for direction in ("in", "out"):
        field = direction+"_local"
        if field in payload.model_fields_set:
            local = getattr(payload, field)
            try:
                overrides[direction+"_at"] = local_instant(local, ZoneInfo(batch.timezone)).isoformat() if local else None
            except ValueError as error:
                raise HTTPException(422, "Giờ địa phương không xác định duy nhất trong múi giờ của ca.") from error
    effective = {key: overrides.get(key, row[key]) for key in ("in_at", "out_at")}
    now = attendance.utcnow()
    for value in effective.values():
        if value and not aware(batch.admission_from) <= datetime.fromisoformat(value) <= min(now, aware(batch.checkout_until)):
            raise HTTPException(422, "Giờ điều chỉnh phải thuộc cửa sổ ca và không ở tương lai.")
    if all(effective.values()) and datetime.fromisoformat(effective["out_at"]) <= datetime.fromisoformat(effective["in_at"]):
        raise HTTPException(422, "Giờ Ra phải sau giờ Vào.")
    correction = PartnerReportAdjustment(request_id=str(payload.request_id), request_digest=request_hash,
        batch_id=batch.id, worker_id=worker.id, revision=row["adjustment_revision"]+1,
        overrides=overrides, reason=payload.reason, admin_id=user.id, created_at=now)
    db.add(correction)
    db.add(AuditLog(action="partner_report_adjustment", entity_id=worker.id, reason=payload.reason,
                    details={"admin_id": user.id, "request_id": str(payload.request_id), "revision": correction.revision}))
    db.commit()
    return {"adjustment": history(correction), "replayed": False}


@router.post("/batches/{batch_id}/close")
def close(batch_id: UUID, payload: CloseInput, db: Db, user: MutationAdmin):
    lock_calendar(db)
    batch = batch_of(db, str(batch_id))
    previous = db.get(PartnerReportSnapshot, batch.id)
    other_request = db.scalar(select(PartnerReportSnapshot).where(PartnerReportSnapshot.request_id == str(payload.request_id)))
    if other_request and other_request.batch_id != batch.id:
        raise HTTPException(409, "Mã yêu cầu chốt đã dùng cho đợt khác.")
    if previous:
        if previous.request_id != str(payload.request_id) or previous.report.get("input_source_hash") != payload.expected_source or previous.reason != payload.reason:
            raise HTTPException(409, "Đợt đã chốt bởi yêu cầu khác; dùng bản chốt đã lưu.")
        return build_report(db, batch.id)
    if batch.state != "review":
        raise HTTPException(409, "Chuyển đợt sang Chờ đối soát và kiểm tra trước khi chốt.")
    result = build_report(db, batch.id)
    if result["source_hash"] != payload.expected_source:
        raise HTTPException(409, "Bảng công đã thay đổi; tải lại trước khi chốt.")
    if result["summary"]["incomplete"] and not payload.acknowledge_incomplete:
        raise HTTPException(409, "Đợt còn thiếu Vào/Ra. Kiểm tra và xác nhận rõ việc chốt các dòng thiếu; không tự lấp giờ.")
    now = attendance.utcnow()
    if any(datetime.fromisoformat(event["server_time"]) > now for row in result["rows"] for event in row["original_events"]):
        raise HTTPException(503, "Đồng hồ máy chủ lùi so với lượt gốc; chưa chốt chứng từ.")
    unadmitted = result["summary"]["pending"]
    for row in result["rows"]:
        if row["status"] in {"pending_name", "pending_approval"}:
            row["status"], row["status_label"] = "not_admitted", "Chưa tiếp nhận khi chốt đợt"
    result["summary"].update(pending=0, unadmitted_at_close=unadmitted, available_slots=0)
    result.update(input_source_hash=result["source_hash"], closed=True, closed_at=iso(now), closed_by=user.id, close_reason=payload.reason)
    result["batch"]["state"] = "closed"
    # The report's source hash identifies the reviewed material. The stored
    # checksum separately authenticates the entire immutable report JSON.
    saved = PartnerReportSnapshot(batch_id=batch.id, request_id=str(payload.request_id), source_hash=digest(result),
        report=result, reason=payload.reason, admin_id=user.id, created_at=now)
    batch.state = "closed"
    db.add(saved)
    db.add(AuditLog(action="partner_batch_closed", entity_id=batch.id, reason=payload.reason,
                    details={"admin_id": user.id, "request_id": str(payload.request_id), "source_hash": result["source_hash"],
                             "incomplete_acknowledged": payload.acknowledge_incomplete}))
    db.commit()
    return result


def filtered_rows(rows, status):
    if status == "all":
        return rows
    return [row for row in rows if (row["status"] == "complete" if status == "complete" else
        row["admitted"] and row["status"] != "complete" if status == "incomplete" else not row["admitted"])]


@router.get("/batches/{batch_id}/export.csv")
def export(batch_id: UUID, db: Db, user: Admin, expected_source: str = Query(pattern=r"^[a-f0-9]{64}$"), status: Filter = "all"):
    lock_calendar(db)
    result = build_report(db, str(batch_id))
    db.rollback()
    if result["source_hash"] != expected_source:
        raise HTTPException(409, "Bảng công khác bản đang xem; tải lại trước khi xuất CSV.")
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Đối tác", "Sàn", "Đợt", "Ngày ca", "Mã tạm", "Họ tên", "Trạng thái", "Vào gốc", "Ra gốc", "Vào đối soát", "Ra đối soát", "Giây ghi nhận", "Giây công trong ca", "Giây nghỉ không lương", "Giây ngoài ca", "Số lần điều chỉnh", "Bản chốt", "Nguồn dữ liệu", "Thời điểm tính", "Phạm vi sử dụng"])
    zone = ZoneInfo(result["batch"]["timezone"])
    def local(value):
        return datetime.fromisoformat(value).astimezone(zone).isoformat() if value else ""
    for row in filtered_rows(result["rows"], status):
        values = [result["partner"]["name"], result["batch"]["site"], result["batch"]["name"], result["batch"]["work_date"],
            row["code"], row["name"], row["status_label"], local(row["raw_in_at"]), local(row["raw_out_at"]),
            local(row["in_at"]), local(row["out_at"]), row["elapsed_seconds"], row["worked_seconds"],
            row["unpaid_break_seconds"], row["outside_shift_seconds"], row["adjustment_revision"],
            "Đã chốt" if result["closed"] else "Chưa chốt", result["source_hash"], result["as_of"],
            "Chạy thử chức năng - không dùng thanh toán" if result["batch"]["rules"].get("functional_trial") else "Đối soát lao động; chưa tính tiền"]
        writer.writerow([csv_text(value) for value in values])
    filename = f"ontime_partner_{result['batch']['work_date']}_{str(batch_id)[:8]}.csv"
    return Response("\ufeff"+output.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})
