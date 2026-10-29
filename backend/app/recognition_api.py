import hashlib
import hmac
import threading
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from . import recognition_sequence
from .auth import Admin, Db, MutationAdmin, same_origin
from .capture_guidance import QUALITY_FEEDBACK
from .collections import read_photo
from .devices import Kiosk
from .face_engine import FaceInputError
from .kiosk_scene import check_scene, face_box
from .models import Device, Employee, RecognitionPolicy, RecognitionSession, utcnow
from .recognition_sequence import (
    append_frame,
    confirm_session,
    create_session,
    describe,
    nonce,
    owned_session,
    require_policy,
)
from .shifts import ReasonInput

router = APIRouter(prefix="/api/kiosk/recognition", tags=["recognition"])
admin_router = APIRouter(prefix="/api/admin/recognition", tags=["recognition"])
slots = threading.BoundedSemaphore(2)


def database_call(db, function, *args, **kwargs):
    try:
        return function(db, *args, **kwargs)
    except SQLAlchemyError as error:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        raise HTTPException(
            503, "Chưa xác nhận được trạng thái phiên. Tra cứu lại cùng request ID trước khi gửi ảnh tiếp."
        ) from error


class StartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID


class ConfirmInput(ReasonInput):
    confirm_employee_code: str = Field(min_length=1, max_length=40)


def context(request, db):
    same_origin(request)
    engine = getattr(request.app.state, "face_engine", None)
    from .policy_selection import selected_policy

    policy_id = selected_policy(db, getattr(request.app.state, "attendance_policy_id", None))
    if not engine:
        raise HTTPException(503, "Model local chưa sẵn sàng.")
    return engine, policy_id


def intent(request, value):
    if request.headers.get("x-kiosk-intent") != value:
        raise HTTPException(403, "Thiếu yêu cầu kiosk phù hợp.")


def frame_context(request, db, request_id, device):
    # ODBC calls may wait for locks or disk. Keep the complete preflight off
    # the event loop, while using this request's Session sequentially.
    engine, policy = context(request, db)
    intent(request, "capture-recognition")
    row = database_call(db, owned_session, str(request_id), device.id, device.token_hash, utcnow())
    database_call(db, require_policy, policy, engine.model_id, utcnow(), validate_gallery=False)
    supplied = request.headers.get("x-capture-nonce", "")
    if len(supplied) != 64 or not hmac.compare_digest(nonce(row), supplied):
        raise HTTPException(403, "Ảnh không gắn với thử thách của phiên này.")
    return engine, policy


@router.post("/sessions", status_code=201)
def start(payload: StartInput, request: Request, db: Db, device: Kiosk):
    engine, policy = context(request, db)
    intent(request, "start-recognition")
    return database_call(
        db, create_session, str(payload.request_id), device.id, device.token_hash, policy, engine.model_id
    )


@router.get("/sessions/{request_id}")
def state(request_id: UUID, db: Db, device: Kiosk):
    row = database_call(db, owned_session, str(request_id), device.id, device.token_hash, utcnow())
    return describe(row, db.get(RecognitionPolicy, row.policy_id))


@router.post("/preview")
async def preview(request: Request, db: Db, device: Kiosk):
    engine, _ = await run_in_threadpool(context, request, db)
    intent(request, "preview-recognition")
    # Detection previews do not identify anyone or record attendance. They must
    # work before a validated identity/PAD policy has been activated.
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Máy chủ đang xử lý các camera khác.", headers={"Retry-After": "1"})
    try:
        content = await read_photo(request)
        try:
            _, _, metadata = await run_in_threadpool(engine.inspect, content)
            ready, feedback = check_scene(metadata["quality"])
            return {"ready": ready, "face_present": True, "feedback": feedback,
                    "face_box": face_box(metadata["quality"]), "attendance_recorded": False}
        except FaceInputError as error:
            return {
                "ready": False,
                "face_present": error.code != "no_face",
                "feedback": QUALITY_FEEDBACK.get(error.code, "Ảnh chưa đạt chất lượng."),
                "face_box": face_box(error.details),
                "attendance_recorded": False,
            }
    finally:
        slots.release()


@router.post("/sessions/{request_id}/frames/{index}")
async def frame(request_id: UUID, request: Request, db: Db, device: Kiosk, index: int = Path(ge=1, le=12)):
    received_at = recognition_sequence.utcnow()
    engine, policy = await run_in_threadpool(frame_context, request, db, request_id, device)
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Máy chủ đang xử lý các camera khác.", headers={"Retry-After": "1"})
    try:
        content = await read_photo(request)
        fingerprint = hashlib.sha256(content).hexdigest()
        try:
            vector, metadata = await run_in_threadpool(engine.analyze, content)
            quality = metadata["quality"]
        except FaceInputError as error:
            vector, quality = None, {"feedback": QUALITY_FEEDBACK.get(error.code, "Ảnh chưa đạt chất lượng.")}
        return await run_in_threadpool(
            database_call,
            db,
            append_frame,
            str(request_id),
            index,
            device.id,
            device.token_hash,
            policy,
            engine.model_id,
            fingerprint,
            vector,
            quality,
            received_at,
        )
    finally:
        slots.release()


@admin_router.get("/pending")
def pending(request: Request, db: Db, user: Admin):
    _, policy = context(request, db)
    now = utcnow()
    rows = db.execute(
        select(RecognitionSession, Employee, Device)
        .join(Employee, Employee.id == RecognitionSession.employee_id)
        .join(Device, Device.id == RecognitionSession.device_id)
        .join(RecognitionPolicy, RecognitionPolicy.id == RecognitionSession.policy_id)
        .where(
            RecognitionSession.policy_id == policy,
            RecognitionPolicy.mode == "supervised",
            RecognitionSession.state == "verified",
            RecognitionSession.supervisor_confirmed_at.is_(None),
            RecognitionSession.expires_at > now,
            Employee.active == True,  # noqa: E712
            Device.active == True,  # noqa: E712
            RecognitionSession.biometric_revision == Employee.biometric_revision,
            RecognitionSession.device_token_hash == Device.token_hash,
            Device.token_expires_at > now,
        )
        .order_by(RecognitionSession.created_at)
        .limit(101)
    ).all()
    return {
        "items": [
            {
                "request_id": row.request_id,
                "employee_code": person.code,
                "employee_name": person.name,
                "device_name": device.name,
                "direction": row.direction,
                "expires_at": row.expires_at.isoformat(),
            }
            for row, person, device in rows[:100]
        ],
        "has_more": len(rows) > 100,
    }


@admin_router.post("/sessions/{request_id}/confirm")
def confirm(request_id: UUID, payload: ConfirmInput, request: Request, db: Db, user: MutationAdmin):
    engine, policy = context(request, db)
    return database_call(db, confirm_session, str(request_id), payload, user, policy, engine.model_id)
