"""Paired partner kiosk routes. Identity and direction come from server state."""

import hashlib
import hmac
import threading
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from . import partner_attendance as service
from .auth import Admin, Db, same_origin
from .collections import read_photo
from .devices import Kiosk
from .employees import EmployeeInput
from .face_engine import FaceInputError
from .kiosk_scene import check_scene, face_box
from .models import PartnerBatch, PartnerWorker
from .partner_admin import describe_batch, describe_vendor
from .partner_speech import MAX_AUDIO_BYTES, SpeechError

router = APIRouter(prefix="/api/kiosk/partners", tags=["partner-kiosk"])
admin_router = APIRouter(prefix="/api/admin/partners", tags=["partner-admission"])
slots = threading.BoundedSemaphore(2)


class StartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    expected_worker_id: UUID | None = None


class NameInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    source: Literal["manual", "voice", "voice_edited"]
    expected_revision: int = Field(ge=0)
    proof_id: UUID

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value):
        return EmployeeInput.clean_text(value)


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


def context(request, db, device, *, intent=None, writable=True):
    if intent:
        same_origin(request)
        if request.headers.get("x-kiosk-intent") != intent:
            raise HTTPException(403, "Thiếu yêu cầu điểm quét đối tác phù hợp.")
    actor, batch, vendor = service._batch_context(db, device.id, device.token_hash, service.utcnow(), writable=writable)
    engine = getattr(request.app.state, "face_engine", None)
    if writable and (engine is None or engine.model_id != batch.model_id):
        raise HTTPException(503, "Model local chưa sẵn sàng hoặc khác cấu hình ca.")
    return engine, actor, batch, vendor


@router.get("/context")
def kiosk_context(request: Request, db: Db, device: Kiosk):
    engine, actor, batch, vendor = context(request, db, device, writable=False)
    recording_enabled = bool(engine and engine.model_id == batch.model_id)
    message = "Sẵn sàng nhận diện tại đợt đã gán." if recording_enabled else "Bộ nhận diện local chưa sẵn sàng."
    try:
        service._batch_context(db, device.id, device.token_hash, service.utcnow())
    except HTTPException as error:
        recording_enabled, message = False, error.detail
    return {"batch": describe_batch(batch), "partner": describe_vendor(vendor),
            "device_id": actor.id, "direction": actor.direction,
            "recognition_ready": bool(engine and engine.model_id == batch.model_id),
            "recording_enabled": recording_enabled, "message": message,
            "temporary_biometric_cleanup_ready": not bool(getattr(request.app.state, "partner_retention_error", None)),
            "admission_mode": "automatic", "anti_spoof_verified": False}


@router.post("/captures", status_code=201)
def start_capture(payload: StartInput, request: Request, db: Db, device: Kiosk):
    engine, *_ = context(request, db, device, intent="start-partner-capture")
    return service.create_capture(db, str(payload.request_id), device.id, device.token_hash, engine.model_id,
        expected_worker_id=str(payload.expected_worker_id) if payload.expected_worker_id else None)


@router.get("/captures/{request_id}")
def capture_state(request_id: UUID, db: Db, device: Kiosk):
    row = service.owned_capture(db, str(request_id), device.id, device.token_hash, service.utcnow())
    return service.describe_capture(db, row)


def preflight(request, db, device, request_id, index):
    engine, *_ = context(request, db, device, intent="capture-partner-face")
    row = service.owned_capture(db, str(request_id), device.id, device.token_hash, service.utcnow(), writable=True)
    supplied = request.headers.get("x-capture-nonce", "")
    if len(supplied) != 64 or not hmac.compare_digest(service.nonce(row, index), supplied):
        raise HTTPException(403, "Ảnh không gắn với thử thách của phiên hiện tại.")
    return engine


@router.post("/captures/{request_id}/frames/{index}")
async def capture_frame(request_id: UUID, request: Request, db: Db, device: Kiosk,
                        index: int = Path(ge=1, le=12)):
    observed = service.utcnow()
    engine = await run_in_threadpool(preflight, request, db, device, request_id, index)
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Máy chủ đang xử lý camera khác.", headers={"Retry-After": "1"})
    try:
        content = await read_photo(request)
        fingerprint = hashlib.sha256(content).hexdigest()
        try:
            vector, metadata = await run_in_threadpool(engine.analyze, content)
            ready, _ = check_scene(metadata["quality"])
            quality = metadata["quality"]
            if not ready:
                vector = None
        except FaceInputError as error:
            vector, quality = None, {"accepted": False, "reason": error.code, **error.details}
        return await run_in_threadpool(service.append_frame, db, str(request_id), device.id, device.token_hash,
            engine.model_id, engine.dimensions, index, fingerprint, vector, quality, observed)
    finally:
        slots.release()


@router.post("/preview")
async def preview(request: Request, db: Db, device: Kiosk):
    engine, *_ = await run_in_threadpool(context, request, db, device, intent="preview-partner-face")
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Máy chủ đang xử lý camera khác.")
    try:
        content = await read_photo(request)
        try:
            _, _, metadata = await run_in_threadpool(engine.inspect, content)
            ready, feedback = check_scene(metadata["quality"])
            return {"ready": ready, "face_present": True, "face_box": face_box(metadata["quality"]), "feedback": feedback}
        except FaceInputError as error:
            _, feedback = check_scene({**error.details, "accepted": False, "reason": error.code})
            return {"ready": False, "face_present": error.code != "no_face", "face_box": face_box(error.details),
                    "feedback": feedback}
    finally:
        slots.release()


@router.put("/workers/{worker_id}/name")
def name(worker_id: UUID, payload: NameInput, request: Request, db: Db, device: Kiosk):
    context(request, db, device, intent="confirm-partner-name")
    return service.confirm_name(db, str(worker_id), device.id, device.token_hash,
        name=payload.name, source=payload.source, expected_revision=payload.expected_revision, proof_id=str(payload.proof_id))


def speech_preflight(request, db, device, worker_id, expected_revision):
    context(request, db, device, intent="transcribe-partner-name")
    worker = service._pending_worker(db, str(worker_id), device.id, device.token_hash, service.utcnow(), lock=False)
    if worker.name_revision != expected_revision:
        raise HTTPException(409, "Tên đã thay đổi; không dùng kết quả giọng nói của phiên cũ.")
    # No SQL transaction/row lock remains held while CPU speech processing runs.
    db.rollback()


@router.post("/workers/{worker_id}/speech")
async def speech(worker_id: UUID, request: Request, db: Db, device: Kiosk,
                 expected_revision: int = Query(ge=0)):
    await run_in_threadpool(speech_preflight, request, db, device, worker_id, expected_revision)
    media = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if media not in {"audio/webm", "audio/mp4", "audio/ogg", "audio/wav", "audio/x-wav"}:
        raise HTTPException(415, "Định dạng micro chưa hỗ trợ; bạn có thể nhập họ tên bằng tay.")
    content = bytearray()
    async for chunk in request.stream():
        if len(content)+len(chunk) > MAX_AUDIO_BYTES:
            raise HTTPException(413, "Đoạn đọc quá lớn; tối đa 8 giây hoặc nhập tay.")
        content.extend(chunk)
    engine = getattr(request.app.state, "partner_speech", None)
    if engine is None:
        raise HTTPException(503, "Bộ đọc tên local chưa sẵn sàng; vui lòng nhập tay.")
    try:
        draft = await run_in_threadpool(engine.transcribe, bytes(content))
    except SpeechError as error:
        messages = {
            "speech_busy": "Micro khác đang xử lý; thử lại hoặc nhập tay.",
            "audio_silent": "Chưa nghe rõ giọng đọc. Kiểm tra micro hoặc nhập tay.",
            "speech_unclear": "Chưa nhận rõ họ tên. Đọc lại hoặc nhập tay.",
            "audio_too_long": "Đoạn đọc quá dài; đọc họ tên trong 8 giây hoặc nhập tay.",
            "audio_too_short": "Đoạn đọc quá ngắn. Đọc đầy đủ họ tên hoặc nhập tay.",
            "audio_invalid": "Không đọc được âm thanh micro; vui lòng thử lại hoặc nhập tay.",
            "speech_timeout": "Xử lý giọng nói quá thời gian; vui lòng nhập tay.",
        }
        code = 429 if str(error) == "speech_busy" else 503
        raise HTTPException(code, messages.get(str(error), "Bộ đọc tên local chưa sẵn sàng; vui lòng nhập tay.")) from error
    finally:
        content.clear()
    await run_in_threadpool(speech_preflight, request, db, device, worker_id, expected_revision)
    return {"draft": draft, "worker_id": str(worker_id), "expected_revision": expected_revision,
            "requires_confirmation": True, "name_saved": False, "audio_stored": False}


@router.get("/workers/{worker_id}")
def worker_state(worker_id: UUID, request: Request, db: Db, device: Kiosk):
    _, _, batch, _ = context(request, db, device)
    worker = db.get(PartnerWorker, str(worker_id), populate_existing=True)
    if not worker or worker.batch_id != batch.id:
        raise HTTPException(404, "Không có người được tiếp nhận tại ca của điểm quét này.")
    if worker.state == "pending" and (worker.device_id != device.id or worker.token_hash != device.token_hash):
        raise HTTPException(409, "Người này đang được tiếp nhận tại điểm khác.")
    return service._worker_public(worker)


@router.post("/workers/{worker_id}/cancel")
def cancel(worker_id: UUID, payload: EmptyInput, request: Request, db: Db, device: Kiosk):
    context(request, db, device, intent="cancel-partner-admission")
    return service.cancel_worker(db, str(worker_id), device.id, device.token_hash)


@router.post("/captures/{request_id}/commit")
def commit(request_id: UUID, payload: EmptyInput, request: Request, db: Db, device: Kiosk):
    same_origin(request)
    if request.headers.get("x-kiosk-intent") != "record-partner-attendance":
        raise HTTPException(403, "Thiếu yêu cầu ghi công đối tác.")
    return service.commit_capture(db, str(request_id), device.id, device.token_hash)


@admin_router.get("/batches/{batch_id}/workers")
def workers(batch_id: UUID, db: Db, user: Admin, offset: int = 0, limit: int = 50):
    if offset < 0 or not 1 <= limit <= 100:
        raise HTTPException(422, "Mỗi trang tối đa 100 lao động.")
    if db.get(PartnerBatch, str(batch_id)) is None:
        raise HTTPException(404, "Không tìm thấy đợt đối tác.")
    rows = db.scalars(select(PartnerWorker).where(PartnerWorker.batch_id == str(batch_id))
        .order_by(PartnerWorker.number).offset(offset).limit(limit+1)).all()
    return {"items": [service._worker_public(row) for row in rows[:limit]], "has_more": len(rows) > limit}


