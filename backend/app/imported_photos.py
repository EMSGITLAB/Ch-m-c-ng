"""Admin-only access and nearest-reference diagnostics for imported test photos."""

import hashlib
import threading

import numpy as np
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from .auth import Admin, Db, MutationAdmin
from .capture_guidance import QUALITY_FEEDBACK
from .collections import read_photo
from .face_engine import FaceInputError
from .matching import normalized
from .models import CollectionSample, Employee, FaceTemplate, ImportedFacePhoto
from .pilot_enrollment import current_config, membership
from .policy_selection import PILOT_SCOPE

router = APIRouter(prefix="/api/admin/imported-face-photos", tags=["imported-test-photos"])
slots = threading.BoundedSemaphore(2)


@router.get("")
def list_photos(request: Request, db: Db, user: Admin, employee_id: str | None = None, offset: int = 0, limit: int = 100):
    if offset < 0 or not 1 <= limit <= 100:
        raise HTTPException(422, "Mỗi trang 1–100 ảnh.")
    policy = current_config(db, request)
    active_fingerprints = set()
    if policy and policy.enabled and policy.evidence.get("scope") == PILOT_SCOPE:
        ids = [item["template_id"] for item in membership(policy)]
        for offset_ids in range(0, len(ids), 1000):
            active_fingerprints.update(template.quality.get("source_fingerprint") for template in db.scalars(
                select(FaceTemplate).where(FaceTemplate.id.in_(ids[offset_ids:offset_ids+1000]))))
    query = select(ImportedFacePhoto, Employee).join(Employee)
    if employee_id:
        query = query.where(Employee.id == employee_id)
    rows = db.execute(
        query.order_by(Employee.code, ImportedFacePhoto.id).offset(offset).limit(limit + 1)
    ).all()
    return {
        "items": [
            {
                "id": photo.id,
                "employee_id": person.id,
                "employee_code": person.code,
                "employee_name": person.name,
                "accepted": bool(photo.sample_id),
                "reason": photo.quality.get("reason"),
                "feedback": "Ảnh hồ sơ đang được dùng làm mẫu nhận diện."
                if photo.fingerprint in active_fingerprints and photo.biometric_revision == person.biometric_revision
                else "Ảnh đạt bộ lọc ban đầu; đã lưu 1 mẫu thử."
                if photo.sample_id
                else f"Vùng mặt trong ảnh nhỏ hơn {photo.quality.get('minimum_face_pixels', 96)} px. Cần ảnh gốc rõ hơn hoặc chụp gần hơn."
                if photo.quality.get("reason") == "face_too_small"
                else QUALITY_FEEDBACK.get(photo.quality.get("reason"), "Ảnh chưa đạt, cần thay ảnh khác."),
                "operational_enrollment": photo.fingerprint in active_fingerprints and photo.biometric_revision == person.biometric_revision,
            }
            for photo, person in rows[:limit]
        ],
        "has_more": len(rows) > limit,
    }


@router.get("/{photo_id}/image")
def image(photo_id: str, db: Db, user: Admin):
    photo = db.get(ImportedFacePhoto, photo_id)
    if not photo:
        raise HTTPException(404, "Không có ảnh này.")
    return Response(content=photo.image, media_type=photo.content_type)


def rank_references(db, engine, vector, fingerprint):
    rows = db.execute(
        select(ImportedFacePhoto, CollectionSample, Employee)
        .join(CollectionSample, CollectionSample.id == ImportedFacePhoto.sample_id)
        .join(Employee, Employee.id == ImportedFacePhoto.employee_id)
        .where(
            Employee.active == True,  # noqa: E712
            ImportedFacePhoto.model_id == engine.model_id,
            ImportedFacePhoto.biometric_revision == Employee.biometric_revision,
        )
        .limit(1001)
    ).all()
    if len(rows) > 1000:
        raise HTTPException(413, "Bộ ảnh thử vượt giới hạn 1.000 mẫu.")
    scores = []
    for photo, sample, person in rows:
        if (
            sample.model_id != engine.model_id
            or sample.dimensions != engine.dimensions
            or len(sample.vector) != engine.dimensions * 4
        ):
            raise HTTPException(503, "Bộ ảnh thử có mẫu không tương thích model.")
        score = float(
            np.clip(normalized(np.frombuffer(sample.vector, dtype="<f4"), engine.dimensions) @ vector, -1, 1)
        )
        scores.append(
            {
                "employee_id": person.id,
                "employee_code": person.code,
                "employee_name": person.name,
                "cosine": round(score, 6),
                "same_reference_file": photo.fingerprint == fingerprint,
            }
        )
    scores.sort(key=lambda row: (-row["cosine"], row["employee_id"]))
    return {
        "mode": "imported_reference_diagnostic",
        "model_id": engine.model_id,
        "reference_count": len(rows),
        "candidates": scores[:3],
        "attendance_recorded": False,
        "identity_confirmed": False,
        "is_accuracy_percentage": False,
        "message": "Chỉ là thứ hạng tương đồng ảnh thử, chưa phải kết luận nhận diện. Dùng lại chính ảnh đăng ký không kiểm chứng được độ chính xác.",
    }


@router.post("/probe")
async def probe(request: Request, db: Db, user: MutationAdmin):
    engine = getattr(request.app.state, "face_engine", None)
    if not engine:
        raise HTTPException(503, "Model local chưa sẵn sàng.")
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Máy chủ đang xử lý ảnh thử khác.")
    try:
        content = await read_photo(request)
        try:
            vector, metadata = await run_in_threadpool(engine.analyze, content)
        except FaceInputError as error:
            return JSONResponse(
                status_code=422,
                content={
                    "detail": QUALITY_FEEDBACK.get(error.code, "Ảnh chưa đạt bộ lọc."),
                    "reason": error.code,
                },
            )
        result = rank_references(db, engine, vector, hashlib.sha256(content).hexdigest())
        return result | {"quality": metadata["quality"]}
    finally:
        slots.release()
