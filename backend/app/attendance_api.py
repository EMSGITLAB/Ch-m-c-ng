import threading
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from .attendance import commit_recognition
from .auth import Db, same_origin
from .config import get_settings
from .devices import Kiosk, aware
from .models import RecognitionSession, utcnow
from .policy_selection import selected_policy

router = APIRouter(prefix="/api/kiosk/attendance", tags=["attendance"])
commit_slots = threading.BoundedSemaphore(4)


class CommitInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@router.post("/{request_id}/commit")
async def commit(request_id: UUID, payload: CommitInput, request: Request, db: Db, device: Kiosk):
    same_origin(request)
    if request.headers.get("x-kiosk-intent") != "record-attendance":
        raise HTTPException(403, "Thiếu yêu cầu ghi công của kiosk.")
    policy_id = await run_in_threadpool(selected_policy, db, getattr(request.app.state, "attendance_policy_id", None))
    engine = getattr(request.app.state, "face_engine", None)
    if not policy_id or not engine:
        raise HTTPException(
            503, "Chưa bật ghi công: cần hoàn tất hiệu chỉnh và kiểm chứng nhận diện/giả mạo."
        )
    if not commit_slots.acquire(blocking=False):
        raise HTTPException(
            429,
            "Máy chủ đang xử lý các lượt ghi công khác. Hãy thử lại cùng request ID.",
            headers={"Retry-After": "1"},
        )
    try:
        return await run_in_threadpool(
            commit_recognition,
            db,
            str(request_id),
            device.id,
            device.token_hash,
            policy_id,
            engine.model_id,
            get_settings().business().cooldown_seconds,
        )
    except SQLAlchemyError as error:
        try:
            await run_in_threadpool(db.rollback)
        except SQLAlchemyError:
            pass
        raise HTTPException(
            503,
            "Chưa xác nhận được kết quả ghi công. Tra cứu lại bằng cùng request ID trước khi nhận diện lại.",
        ) from error
    finally:
        commit_slots.release()


@router.get("/{request_id}")
def receipt(request_id: UUID, db: Db, device: Kiosk):
    session = db.get(RecognitionSession, str(request_id))
    if not session or session.device_id != device.id:
        raise HTTPException(404, "Không có yêu cầu của kiosk này.")
    if session.state == "used":
        return session.receipt
    if aware(session.expires_at) <= utcnow():
        raise HTTPException(410, "Phiên nhận diện đã hết hạn; chưa có công được ghi cho yêu cầu này.")
    if session.state == "rejected":
        return JSONResponse(status_code=422, content={"status": "rejected", "request_id": str(request_id)})
    return JSONResponse(status_code=202, content={"status": "pending", "request_id": str(request_id)})
