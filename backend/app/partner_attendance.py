"""Ordered partner face captures, automatic admission and immutable punches.

Vectors stay in the expiring encrypted local store, never in SQL or receipts.
Every mutation holds calendar_gate before reading bindings/capacity/identities.
"""

import hashlib
import hmac
import math
from datetime import timedelta
from functools import lru_cache
from uuid import uuid4

import numpy as np
from fastapi import HTTPException
from sqlalchemy import func, or_, select

from .attendance import live_device
from .calendar_guard import lock_calendar
from .config import get_settings
from .devices import aware
from .kiosk_scene import face_box
from .matching import Gallery, normalized
from .models import (
    AuditLog,
    PartnerBatch,
    PartnerCapture,
    PartnerCounter,
    PartnerDeviceBinding,
    PartnerEvent,
    PartnerVendor,
    PartnerWorker,
    utcnow,
)
from .partner_face_store import PartnerFaceStore

CAPTURE_TTL = 30
PENDING_TTL = 300
PROOF_TTL = 10
MAX_FRAMES = 12


@lru_cache(maxsize=8)
def _store(runtime, dimensions):
    return PartnerFaceStore(runtime, dimensions)


def store_for(dimensions=128):
    try:
        return _store(str(get_settings().runtime_dir.resolve()), dimensions)
    except (ValueError, OSError, RuntimeError) as error:
        raise HTTPException(503, "Kho mặt tạm chưa sẵn sàng; không tự tạo lại mẫu hoặc ghi công.") from error


def _store_call(method, *args, **kwargs):
    try:
        return method(*args, **kwargs)
    except (ValueError, OSError, RuntimeError) as error:
        raise HTTPException(503, "Kho mẫu mặt tạm chưa đầy đủ hoặc chưa đọc được. Không cấp mã/ghi công mới; cần kiểm tra kho local.") from error


def _batch_context(db, device_id, token_hash, now, *, batch_id=None, direction=None, writable=True, lock=False):
    device = live_device(db, device_id, token_hash, now, lock=lock, workflow="partner")
    binding = db.get(PartnerDeviceBinding, device.id, populate_existing=True)
    if not binding or not binding.active or (batch_id and binding.batch_id != batch_id):
        raise HTTPException(409, "Điểm quét chưa gắn đúng đợt chấm công đối tác.")
    batch = db.get(PartnerBatch, binding.batch_id, populate_existing=True)
    vendor = db.get(PartnerVendor, batch.partner_id, populate_existing=True) if batch else None
    if not batch or not vendor or not vendor.active:
        raise HTTPException(409, "Đợt hoặc đối tác đã ngừng sử dụng.")
    if direction and device.direction != direction:
        raise HTTPException(409, "Chiều Vào/Ra đã đổi. Hãy tạo phiên quét mới.")
    if writable:
        from .recognition_sequence import require_policy
        require_policy(db, batch.policy_id, batch.model_id, now, validate_gallery=False)
        if batch.state not in {"open", "running"}:
            raise HTTPException(409, "Đợt chưa mở hoặc đã ngừng ghi nhận.")
        if device.direction == "in":
            valid = aware(batch.admission_from) <= now < aware(batch.ends_at)
        else:
            valid = aware(batch.starts_at) < now <= aware(batch.checkout_until)
        if not valid:
            raise HTTPException(409, "Ngoài khoảng Vào/Ra được phép của ca đối tác.")
    return device, batch, vendor


def _worker_public(worker, now=None):
    now = now or utcnow()
    pending = worker.state == "pending"
    expired = pending and aware(worker.pending_expires_at) <= now
    return {"id": worker.id, "code": worker.code, "name": worker.declared_name,
            "name_source": worker.name_source, "name_revision": worker.name_revision,
            "state": "expired" if expired else worker.state, "batch_id": worker.batch_id,
            "name_confirmed": worker.name_confirmed_at is not None,
            "admission_approved": worker.approved_at is not None,
            "admission_mode": "automatic",
            "pending_expires_at": aware(worker.pending_expires_at).isoformat(),
            "in_at": aware(worker.admitted_at).isoformat() if worker.admitted_at else None,
            "out_at": aware(worker.checked_out_at).isoformat() if worker.checked_out_at else None}


def nonce(row, index=None):
    index = index or len(row.frames)+1
    key = get_settings().session_secret
    if len(key) < 32:
        raise HTTPException(503, "Chưa cấu hình khóa thử thách camera.")
    message = f"partner:{row.request_id}:{row.batch_id}:{row.device_id}:{row.token_hash}:{row.direction}:{index}"
    return hmac.new(key.encode(), message.encode(), hashlib.sha256).hexdigest()


def describe_capture(db, row, now=None):
    result = {"request_id": row.request_id, "batch_id": row.batch_id, "state": row.state,
              "direction": row.direction, "stable_frames": row.stable_frames,
              "next_frame_index": len(row.frames)+1, "expires_at": aware(row.expires_at).isoformat(),
              "capture_nonce": nonce(row), "attendance_recorded": False, "anti_spoof_verified": False}
    if row.worker_id:
        worker = db.get(PartnerWorker, row.worker_id, populate_existing=True)
        result["worker"] = _worker_public(worker, now)
        if worker.state == "pending":
            result["action"] = "name_required" if not worker.name_confirmed_at else "record_in"
            result["owned_enrollment"] = worker.device_id == row.device_id and worker.token_hash == row.token_hash
        else:
            result["action"] = "record_"+row.direction
    if row.state == "used":
        result["receipt"] = row.receipt
        result["attendance_recorded"] = row.receipt.get("status") == "recorded"
    return result


def owned_capture(db, request_id, device_id, token_hash, now, *, writable=False):
    row = db.get(PartnerCapture, request_id, populate_existing=True)
    if not row or row.device_id != device_id:
        raise HTTPException(404, "Không có phiên quét đối tác của thiết bị này.")
    if not hmac.compare_digest(row.token_hash, token_hash or ""):
        raise HTTPException(401, "Quyền điểm quét đã thay đổi.")
    # Historical receipts remain recoverable after a batch closes/rebinds.
    live_device(db, device_id, token_hash, now, workflow="partner")
    if row.state == "used" and not writable:
        return row
    _batch_context(db, device_id, token_hash, now, batch_id=row.batch_id, direction=row.direction)
    if aware(row.expires_at) <= now:
        raise HTTPException(410, "Phiên camera đã hết hạn; mẫu/giờ công chưa được tự suy diễn.")
    if now < aware(row.created_at) or (row.last_observed_at and now < aware(row.last_observed_at)):
        raise HTTPException(503, "Đồng hồ máy chủ đang lùi; chưa dùng phiên để ghi nhận mới.")
    return row


def create_capture(db, request_id, device_id, token_hash, model_id, *, expected_worker_id=None):
    lock_calendar(db)
    now = utcnow()
    previous = db.get(PartnerCapture, request_id)
    if previous:
        row = owned_capture(db, request_id, device_id, token_hash, now)
        if expected_worker_id is not None and row.worker_id != expected_worker_id:
            raise HTTPException(409, "Không thay người đang xác nhận trong cùng mã yêu cầu.")
        return describe_capture(db, row, now)
    device, batch, _ = _batch_context(db, device_id, token_hash, now, lock=True)
    if batch.model_id != model_id:
        raise HTTPException(503, "Model của ca khác model đang chạy. Cần cấu hình lại đợt có kiểm soát.")
    pending = db.scalars(select(PartnerCapture).where(PartnerCapture.device_id == device.id,
        PartnerCapture.state.in_(["pending", "verified"]), PartnerCapture.expires_at > now)).all()
    for old in pending:
        if old.direction != device.direction or old.state == "verified":
            # A new live proof can replace a completed proof, never a pending
            # uncertain commit: used requests already have durable receipts.
            old.state = "rejected"
        else:
            raise HTTPException(409, "Thiết bị còn phiên quét đang xử lý. Tra cứu mã yêu cầu đang lưu trước.")
    if expected_worker_id is not None:
        _pending_worker(db, expected_worker_id, device_id, token_hash, now)
    row = PartnerCapture(request_id=request_id, batch_id=batch.id, device_id=device.id, worker_id=expected_worker_id,
        token_hash=token_hash, direction=device.direction, created_at=now, expires_at=now+timedelta(seconds=CAPTURE_TTL))
    db.add(row)
    db.commit()
    return describe_capture(db, row, now)


def _gallery(db, batch, store, model_id, now):
    workers = db.scalars(select(PartnerWorker).where(PartnerWorker.batch_id == batch.id,
        PartnerWorker.state != "cancelled", PartnerWorker.biometric_expires_at > now,
        or_(PartnerWorker.state != "pending", PartnerWorker.pending_expires_at > now))).all()
    samples = {}
    for worker in workers:
        if not worker.face_reference:
            raise HTTPException(503, "Thiếu mẫu của người đã tiếp nhận; chưa cấp thêm mã hoặc ghi công.")
        samples[worker.id] = _store_call(store.read, worker.face_reference, batch_id=batch.id,
                                       subject_id=worker.id, model_id=model_id, now=now)
    return Gallery(model_id, samples, store.dimensions)


def _classification(gallery, vector, batch):
    if not all(math.isfinite(value) for value in (batch.threshold, batch.minimum_margin)):
        raise HTTPException(503, "Ngưỡng của đợt chưa hợp lệ.")
    rank = gallery.rank(vector, batch.model_id)
    if rank.first_id is None:
        return "new", None
    if rank.first_score <= batch.threshold:
        return ("uncertain", None) if rank.first_score > batch.threshold-batch.minimum_margin else ("new", None)
    if rank.margin is not None and rank.margin <= batch.minimum_margin:
        return "uncertain", None
    return "matched", rank.first_id


def _reserve(db, row, batch, vendor, vectors, store, now):
    if row.direction != "in" or batch.state != "open":
        raise HTTPException(409, "Người chưa có lượt Vào; chiều Ra/đợt đã dừng không cấp mã mới.")
    occupied = db.scalar(select(func.count()).select_from(PartnerWorker).where(PartnerWorker.batch_id == batch.id,
        PartnerWorker.state != "cancelled",
        or_(PartnerWorker.state != "pending", PartnerWorker.pending_expires_at > now)))
    if occupied >= batch.capacity:
        raise HTTPException(409, "Đã đủ hạn mức lao động của đợt, kể cả các chỗ đang chờ họ tên.")
    if batch.serial_number is None:
        counter = db.get(PartnerCounter, 1)
        if counter is None:
            counter = PartnerCounter(id=1, next_batch=0)
            db.add(counter)
        counter.next_batch += 1
        batch.serial_number = counter.next_batch
    batch.next_number += 1
    worker_id, reference = str(uuid4()), str(uuid4())
    expiry = aware(batch.ends_at)+timedelta(hours=batch.retention_hours)
    _store_call(store.write, reference, batch_id=batch.id, subject_id=worker_id, model_id=batch.model_id,
                vectors=vectors[-3:], expires_at=expiry, now=now)
    worker = PartnerWorker(id=worker_id, batch_id=batch.id, number=batch.next_number,
        code=f"{vendor.code}-{batch.work_date:%Y%m%d}-C{batch.serial_number:04d}-{batch.next_number:05d}",
        admission_request_id=row.request_id, device_id=row.device_id, token_hash=row.token_hash,
        reserved_at=now, pending_expires_at=now+timedelta(seconds=PENDING_TTL),
        biometric_expires_at=expiry, face_reference=reference)
    db.add(worker)
    db.flush()
    db.add(AuditLog(action="partner_worker_reserved", entity_id=worker.id,
                    details={"batch_id": batch.id, "capture_id": row.request_id, "number": worker.number}))
    return worker


def append_frame(db, request_id, device_id, token_hash, model_id, dimensions, index,
                 fingerprint, vector, quality, observed):
    lock_calendar(db)
    now = utcnow()
    row = owned_capture(db, request_id, device_id, token_hash, now, writable=True)
    _, batch, vendor = _batch_context(db, device_id, token_hash, now, batch_id=row.batch_id, direction=row.direction, lock=True)
    if batch.model_id != model_id:
        raise HTTPException(503, "Model đã thay đổi trong phiên camera.")
    if index <= len(row.frames):
        old = row.frames[index-1]
        if old["fingerprint"] != fingerprint:
            raise HTTPException(409, "Không thay ảnh của vị trí đã gửi. Tra cứu lại phiên.")
        return dict(old["response"])
    if row.state != "pending" or index != len(row.frames)+1 or index > MAX_FRAMES:
        raise HTTPException(409, "Vị trí ảnh hoặc trạng thái phiên không còn hợp lệ.")
    if observed < aware(row.created_at) or (row.last_observed_at and observed < aware(row.last_observed_at)):
        raise HTTPException(503, "Đồng hồ máy chủ lùi; chưa xác nhận phiên.")
    accepted = vector is not None and quality.get("accepted") is True
    feedback = "Nhìn thẳng và giữ yên."
    if any(frame["fingerprint"] == fingerprint for frame in row.frames):
        accepted, feedback = False, "Ảnh trùng khung đã gửi; cần ảnh camera mới."
    if row.last_observed_at and (observed-aware(row.last_observed_at)).total_seconds() < .2:
        accepted, feedback = False, "Giữ yên để lấy khung tiếp theo."
    store = store_for(dimensions)
    values = []
    if accepted and row.feature_reference:
        values = _store_call(store.read, row.feature_reference, batch_id=batch.id,
                             subject_id=row.request_id, model_id=model_id, now=now)
    if accepted and any(float(np.dot(previous, normalized(vector, dimensions))) <= batch.threshold for previous in values):
        row.state, accepted, feedback = "rejected", False, "Người trước camera thay đổi; bắt đầu phiên mới."
    classification, matched = "uncertain", None
    if accepted:
        gallery = _gallery(db, batch, store, model_id, now)
        classification, matched = _classification(gallery, vector, batch)
        if classification == "uncertain":
            accepted, feedback = False, "Kết quả gần giống/chưa rõ; thử lại hoặc nhờ kiểm tra. Không cấp mã mới."
        if row.worker_id is not None and (classification != "matched" or matched != row.worker_id):
            row.state, accepted, feedback = "rejected", False, "Khuôn mặt hiện tại chưa khớp người đang khai tên. Quay lại đúng người; không cấp mã mới."
    if accepted:
        values.append(normalized(vector, dimensions))
        reference = str(uuid4())
        _store_call(store.write, reference, batch_id=batch.id, subject_id=row.request_id, model_id=model_id,
                    vectors=values, expires_at=aware(row.expires_at), now=now)
        row.feature_reference = reference
        row.stable_frames = len(values)
        if row.first_observed_at is None:
            row.first_observed_at = observed
        stable_seconds = (observed-aware(row.first_observed_at)).total_seconds()
        if row.stable_frames >= 3 and stable_seconds >= .85:
            # The calendar lock serializes this fresh gallery/reservation with
            # every other kiosk, including pending and completed workers.
            if classification == "new":
                try:
                    worker = _reserve(db, row, batch, vendor, values, store, now)
                except HTTPException as error:
                    if error.status_code != 409:
                        raise
                    worker, row.state, feedback = None, "rejected", error.detail
            else:
                worker = db.get(PartnerWorker, matched, populate_existing=True)
            if worker:
                row.worker_id, row.state = worker.id, "verified"
                feedback = "Đã xác định mã lao động; tiếp tục theo trạng thái tiếp nhận."
    else:
        row.feature_reference, row.stable_frames, row.first_observed_at = None, 0, None
        if not quality.get("accepted"):
            feedback = "Khuôn mặt chưa đủ chất lượng. Nhìn thẳng, giữ yên và thử lại."
    row.last_observed_at = observed
    if index == MAX_FRAMES and row.state == "pending":
        row.state, feedback = "rejected", "Chưa hoàn tất chuỗi ảnh. Bắt đầu lại."
    # Snapshot the response after SQL defaults are available, before committing.
    db.flush()
    result = describe_capture(db, row, now)
    result.update(next_frame_index=index+1, capture_nonce=nonce(row, index+1),
                  feedback=feedback, face_box=face_box(quality), frame_accepted=accepted)
    row.frames = [*row.frames, {"fingerprint": fingerprint, "observed_at": observed.isoformat(), "response": result}]
    db.commit()
    return result


def _pending_worker(db, worker_id, device_id, token_hash, now, *, lock=True):
    worker = db.get(PartnerWorker, worker_id, populate_existing=True)
    if not worker:
        raise HTTPException(404, "Không có mã lao động đang tiếp nhận.")
    _batch_context(db, device_id, token_hash, now, batch_id=worker.batch_id, direction="in", lock=lock)
    if worker.device_id != device_id or not hmac.compare_digest(worker.token_hash, token_hash or ""):
        raise HTTPException(409, "Người này đang được tiếp nhận tại điểm khác; dùng lại đúng phiên, không cấp mã mới.")
    if worker.state != "pending" or aware(worker.pending_expires_at) <= now:
        raise HTTPException(410, "Phiên chờ họ tên đã kết thúc hoặc hết hạn.")
    if now < aware(worker.reserved_at) or (worker.name_confirmed_at and now < aware(worker.name_confirmed_at)):
        raise HTTPException(503, "Đồng hồ máy chủ đang lùi; chưa cập nhật phiên tiếp nhận.")
    return worker


def confirm_name(db, worker_id, device_id, token_hash, *, name, source, expected_revision, proof_id):
    lock_calendar(db)
    now = utcnow()
    worker = _pending_worker(db, worker_id, device_id, token_hash, now)
    if worker.name_revision == expected_revision+1 and worker.declared_name == name and worker.name_source == source:
        return _worker_public(worker, now)
    if worker.name_revision != expected_revision:
        raise HTTPException(409, "Họ tên đã thay đổi. Kết quả giọng nói cũ không được ghi đè tên mới.")
    proof = owned_capture(db, proof_id, device_id, token_hash, now, writable=True)
    if (proof.state != "verified" or proof.worker_id != worker.id or proof.direction != "in"
            or not proof.last_observed_at or (now-aware(proof.last_observed_at)).total_seconds() > PROOF_TTL):
        raise HTTPException(409, "Cần quét lại đúng khuôn mặt hiện tại trước khi xác nhận họ tên.")
    worker.declared_name, worker.name_source = name, source
    worker.name_revision += 1
    worker.name_confirmed_at = now
    # The paired kiosk, open batch, capacity and current same-face proof are
    # the admission authority. No administrator approval is required.
    worker.approved_by, worker.approved_at = None, now
    db.add(AuditLog(action="partner_name_confirmed", entity_id=worker.id,
                    details={"revision": worker.name_revision, "source": source, "capture_id": proof_id,
                             "admission_mode": "automatic"}))
    # Retire this proof without creating any attendance event.
    proof.state = "rejected"
    db.commit()
    return _worker_public(worker, now)


def cancel_worker(db, worker_id, device_id, token_hash):
    lock_calendar(db)
    now = utcnow()
    previous = db.get(PartnerWorker, worker_id, populate_existing=True)
    if (previous and previous.state == "cancelled" and previous.device_id == device_id
            and hmac.compare_digest(previous.token_hash, token_hash or "")):
        _batch_context(db, device_id, token_hash, now, batch_id=previous.batch_id, writable=False)
        return _worker_public(previous, now)
    worker = _pending_worker(db, worker_id, device_id, token_hash, now)
    worker.state = "cancelled"
    reference, worker.face_reference = worker.face_reference, None
    db.add(AuditLog(action="partner_admission_cancelled", entity_id=worker.id, details={"device_id": device_id}))
    db.commit()
    if reference:
        _store_call(store_for().remove, reference)
    return _worker_public(worker, now)


def commit_capture(db, request_id, device_id, token_hash):
    lock_calendar(db)
    now = utcnow()
    row = owned_capture(db, request_id, device_id, token_hash, now)
    if row.state == "used":
        return dict(row.receipt)
    if row.state != "verified" or not row.worker_id:
        raise HTTPException(409, "Phiên mặt chưa được xác nhận; chưa ghi công.")
    if not row.last_observed_at or (now-aware(row.last_observed_at)).total_seconds() > PROOF_TTL:
        raise HTTPException(409, "Cần quét lại khuôn mặt hiện tại trước khi ghi Vào/Ra.")
    _, batch, _ = _batch_context(db, device_id, token_hash, now, batch_id=row.batch_id, direction=row.direction, lock=True)
    worker = db.get(PartnerWorker, row.worker_id, populate_existing=True)
    if worker.state == "cancelled":
        raise HTTPException(409, "Lượt tiếp nhận đã hủy.")
    _store_call(store_for().read, worker.face_reference, batch_id=batch.id, subject_id=worker.id,
                model_id=batch.model_id, now=now)
    previous = db.scalar(select(PartnerEvent).where(PartnerEvent.worker_id == worker.id, PartnerEvent.direction == row.direction))
    if previous:
        if aware(previous.server_time) > now:
            raise HTTPException(503, "Giờ máy chủ lùi so với lượt gần nhất.")
        event, status = previous, "duplicate"
    else:
        if row.direction == "in":
            _pending_worker(db, worker.id, device_id, token_hash, now)
            if not worker.name_confirmed_at or not worker.declared_name:
                raise HTTPException(409, "Cần xác nhận họ tên trước khi ghi Vào.")
            # A still-valid named session created by the previous controlled
            # workflow can finish automatically, but only with a fresh proof.
            if not worker.approved_at:
                worker.approved_by, worker.approved_at = None, now
                db.add(AuditLog(action="partner_automatic_admission", entity_id=worker.id,
                                details={"name_revision": worker.name_revision, "capture_id": request_id}))
            worker.state, worker.admitted_at = "active", now
        else:
            if worker.state != "active" or not worker.admitted_at:
                raise HTTPException(409, "Chưa có lượt Vào hợp lệ; không tự tạo lượt hoặc cấp mã ở chiều Ra.")
            if aware(worker.admitted_at) >= now:
                raise HTTPException(409, "Giờ Ra phải sau giờ Vào.")
            worker.state, worker.checked_out_at = "completed", now
        event = PartnerEvent(worker_id=worker.id, capture_id=request_id, device_id=device_id,
                             direction=row.direction, server_time=now, declared_name=worker.declared_name)
        db.add(event)
        db.flush()
        status = "recorded"
    result = {"status": status, "request_id": request_id, "event_id": event.id,
              "worker_id": worker.id, "worker_code": worker.code, "worker_name": event.declared_name,
              "direction": event.direction, "server_time": aware(event.server_time).isoformat(),
              "batch_id": batch.id, "already_completed": worker.state == "completed"}
    row.state, row.receipt = "used", result
    db.add(AuditLog(action="partner_punch_"+status, entity_id=event.id,
                    details={"capture_id": request_id, "device_id": device_id, "batch_id": batch.id}))
    db.commit()
    return dict(result)
