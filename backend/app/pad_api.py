"""Admin-only ephemeral diagnostics; never activates PAD or attendance policy."""

import threading
from datetime import UTC, datetime

import cv2
from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from .auth import Admin, MutationAdmin, same_origin
from .capture_guidance import QUALITY_FEEDBACK
from .collections import read_photo
from .face_engine import FaceInputError

router = APIRouter(prefix="/api/admin/pad", tags=["pad-diagnostics"])
slots = threading.BoundedSemaphore(1)


@router.get("/status")
def status(request: Request, user: Admin):
    engine = getattr(request.app.state, "pad_engine", None)
    return {"ready": engine is not None and getattr(request.app.state, "face_engine", None) is not None,
            "model_id": engine.model_id if engine else None,
            "validated_for_attendance": False, "threshold": None}


@router.post("/preview")
async def preview(request: Request, user: MutationAdmin):
    same_origin(request)
    if request.headers.get("x-pad-intent") != "experimental-pad-preview":
        raise HTTPException(403, "Thiếu yêu cầu kiểm chứng chống giả mạo.")
    face_engine = getattr(request.app.state, "face_engine", None)
    pad_engine = getattr(request.app.state, "pad_engine", None)
    if face_engine is None or pad_engine is None:
        raise HTTPException(503, "Model kiểm chứng local chưa sẵn sàng.")
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Đang kiểm chứng ảnh khác. Thử lại sau.", headers={"Retry-After": "1"})
    try:
        content = await read_photo(request)
        try:
            image, face, metadata = await run_in_threadpool(face_engine.inspect, content)
            result = await run_in_threadpool(pad_engine.score, image, face[:4])
        except FaceInputError as error:
            return {"quality_accepted": False, "reason": error.code,
                    "feedback": QUALITY_FEEDBACK.get(error.code, "Ảnh chưa đạt chất lượng."),
                    "stored": False, "attendance_recorded": False, "pad": None,
                    "server_time": datetime.now(UTC).isoformat()}
        except (ValueError, RuntimeError, cv2.error) as error:
            raise HTTPException(503, "Chưa đo được điểm chống giả mạo. Chưa có quyết định hợp lệ.") from error
        return {"quality_accepted": True, "quality": metadata["quality"], "pad": result,
                "stored": False, "attendance_recorded": False, "server_time": datetime.now(UTC).isoformat()}
    finally:
        slots.release()
