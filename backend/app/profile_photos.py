"""Profile portraits are also single-image local recognition references."""

import hashlib
import threading
from uuid import uuid4

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from .auth import Db, MutationAdmin
from .biometric_state import lock_employee
from .calendar_guard import lock_calendar
from .capture_guidance import QUALITY_FEEDBACK
from .collections import read_photo
from .face_engine import FaceInputError
from .matching import SCORING_RULE
from .models import (
    AuditLog,
    CollectionSample,
    Employee,
    FaceCollection,
    FaceTemplate,
    ImportedFacePhoto,
    utcnow,
)
from .pilot_enrollment import current_config, engine_of, membership, publish_pins
from .pilot_gallery import pin
from .policy_selection import PILOT_SCOPE

router = APIRouter(prefix="/api/admin/employees", tags=["profile-photos"])
slots = threading.BoundedSemaphore(1)
PROTOCOL = "profile-photo-v1"


def analyze(engine, content):
    # Decode even rejected portraits before storage; arbitrary bytes are never served as images.
    engine.decode(content)
    try:
        vector, metadata = engine.analyze_reference(content)
        return vector, metadata["quality"] | {"source": PROTOCOL, "model_id": engine.model_id}
    except FaceInputError as error:
        return None, error.details | {"accepted": False, "reason": error.code,
                                     "source": PROTOCOL, "model_id": engine.model_id}


def reference_sample(db, person, photo, vector, quality, engine):
    """Idempotently add a complete one-photo collection, never reuse another person's data."""
    if photo.biometric_revision != person.biometric_revision or photo.model_id != engine.model_id:
        raise HTTPException(409, "Ảnh thuộc phiên dữ liệu khuôn mặt cũ; cần tải ảnh mới.")
    if photo.sample_id:
        return db.get(CollectionSample, photo.sample_id)
    if vector is None:
        photo.quality = quality
        return None
    existing = db.scalar(select(CollectionSample).where(CollectionSample.fingerprint == photo.fingerprint,
                                                        CollectionSample.model_id == engine.model_id))
    if existing:
        collection = db.get(FaceCollection, existing.collection_id)
        if (collection.employee_id != person.id or collection.biometric_revision != person.biometric_revision
                or collection.purpose != "enrollment" or collection.status != "complete"):
            raise HTTPException(409, "Ảnh đã dùng trong bộ dữ liệu khác; hãy chọn ảnh khác.")
        photo.sample_id = existing.id
        return existing
    now = utcnow()
    collection = FaceCollection(employee_id=person.id, model_id=engine.model_id,
        biometric_revision=person.biometric_revision, purpose="enrollment", status="complete",
        guidance_protocol=PROTOCOL, sample_count=1, created_at=now, expires_at=now, completed_at=now)
    db.add(collection)
    db.flush()
    sample = CollectionSample(collection_id=collection.id, position=1, fingerprint=photo.fingerprint,
        model_id=engine.model_id, vector=np.asarray(vector, dtype="<f4").tobytes(),
        dimensions=engine.dimensions, quality=quality)
    db.add(sample)
    db.flush()
    photo.sample_id, photo.quality = sample.id, quality
    return sample


def add_reference_pin(db, person, sample, engine):
    template = db.scalar(select(FaceTemplate).where(FaceTemplate.employee_id == person.id,
        FaceTemplate.biometric_revision == person.biometric_revision, FaceTemplate.model_id == engine.model_id,
        FaceTemplate.quality["source_fingerprint"].as_string() == sample.fingerprint))
    if not template:
        template = FaceTemplate(employee_id=person.id, biometric_revision=person.biometric_revision,
            model_id=engine.model_id, dimensions=engine.dimensions, vector=sample.vector,
            quality={"source_collection_id": sample.collection_id, "source_fingerprint": sample.fingerprint,
                     "scope": PILOT_SCOPE, "profile_photo": True})
        db.add(template)
        db.flush()
    return pin(template)


def auto_publish(db, request, additions):
    source = current_config(db, request)
    engine = engine_of(request)
    if (not source or not source.enabled or not source.validated_at or source.model_id != engine.model_id
            or source.mode != "functional_trial" or source.pad_verified or source.scoring_rule != SCORING_RULE):
        return {"enabled": False, "message": "Đã lưu ảnh và mẫu; cần bật cấu hình nhận diện đã kiểm tra trước khi chấm công."}
    pins = membership(source)
    identities = {item["participant_id"] for item in additions}
    pins = [item for item in pins if item["participant_id"] not in identities] + additions
    if pins == membership(source):
        return {"enabled": True, "policy_id": source.id, "threshold_changed": False,
                "message": "Ảnh hồ sơ này đang được dùng làm mẫu nhận diện."}
    result = publish_pins(db, source, pins, engine, "profile-photos", commit=False)
    return result | {"message": "Ảnh hồ sơ đã được dùng làm mẫu nhận diện; không cần thu thêm bộ mẫu."}


def save_photo(db, request, employee_id, content, vector, quality, expected_revision):
    lock_calendar(db)
    person = db.get(Employee, employee_id, populate_existing=True)
    if not person:
        raise HTTPException(404, "Không có hồ sơ nhân viên.")
    lock_employee(db, person.id, expected_revision=expected_revision)
    fingerprint = hashlib.sha256(content).hexdigest()
    photo = db.scalar(select(ImportedFacePhoto).where(ImportedFacePhoto.fingerprint == fingerprint))
    if photo and (photo.employee_id != person.id or photo.biometric_revision != person.biometric_revision):
        raise HTTPException(409, "Ảnh đã thuộc hồ sơ hoặc phiên dữ liệu khác.")
    if not photo:
        photo = ImportedFacePhoto(employee_id=person.id, fingerprint=fingerprint, batch_id=uuid4().hex,
            image=content, content_type="image/png" if content.startswith(b"\x89PNG") else
            "image/jpeg" if content.startswith(b"\xff\xd8") else "image/webp",
            model_id=engine_of(request).model_id, biometric_revision=person.biometric_revision, quality=quality)
        db.add(photo)
        db.flush()
    # Re-selecting an older image explicitly makes it the portrait without deleting history.
    photo.created_at = utcnow()
    sample = reference_sample(db, person, photo, vector, quality, engine_of(request))
    db.flush()
    recognition = {"enabled": False, "message": "Đã lưu ảnh hồ sơ. " +
        QUALITY_FEEDBACK.get(quality.get("reason"), "Ảnh chưa đạt để nhận diện; hãy chọn ảnh rõ hơn.")}
    if sample and not person.active:
        recognition = {"enabled": False, "message": "Đã lưu ảnh và mẫu; hồ sơ đang ngừng hoạt động nên chưa nhận diện chấm công."}
    if sample and person.active:
        try:
            with db.begin_nested():
                recognition = auto_publish(db, request, [add_reference_pin(db, person, sample, engine_of(request))])
        except HTTPException as error:
            recognition = {"enabled": False, "message": "Đã lưu ảnh, chưa đưa vào nhận diện: " + str(error.detail)}
    db.add(AuditLog(action="employee_profile_photo", entity_id=person.id,
        details={"photo_id": photo.id, "reference_accepted": bool(sample),
                 "recognition_enabled": recognition["enabled"], "threshold_changed": False}))
    db.commit()
    return {"profile_photo_url": f"/api/admin/imported-face-photos/{photo.id}/image",
            "reference_accepted": bool(sample), "quality": quality, "recognition": recognition}


@router.put("/{employee_id}/photo")
async def upload_photo(employee_id: str, request: Request, db: Db, user: MutationAdmin):
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Đang lưu ảnh hồ sơ, vui lòng thử lại sau.")
    try:
        person = await run_in_threadpool(db.get, Employee, employee_id)
        if not person:
            raise HTTPException(404, "Không có hồ sơ nhân viên.")
        revision = person.biometric_revision
        content = await read_photo(request)
        try:
            vector, quality = await run_in_threadpool(analyze, engine_of(request), content)
        except FaceInputError as error:
            raise HTTPException(422, "Tệp ảnh không hợp lệ: " + error.code) from error
        return await run_in_threadpool(save_photo, db, request, employee_id, content, vector, quality, revision)
    finally:
        slots.release()
