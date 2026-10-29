"""Publish versioned multi-person local trial membership from completed reference collections."""

import threading
from uuid import uuid4

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update

from .auth import Admin, Db, MutationAdmin
from .biometric_state import lock_employee
from .calendar_guard import lock_calendar
from .functional_trial import SCOPE as SINGLE_SCOPE
from .matching import SCORING_RULE, decide, normalized
from .models import (
    AuditLog,
    CollectionSample,
    Employee,
    FaceCollection,
    FaceTemplate,
    RecognitionPolicy,
    RecognitionSession,
    utcnow,
)
from .pilot_gallery import gallery_from_pins, pin
from .policy_selection import PILOT_PREFIX, PILOT_SCOPE, selected_policy

router = APIRouter(prefix="/api/admin/recognition/pilot", tags=["pilot-enrollment"])
slots = threading.BoundedSemaphore(1)


class PublishInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    expected_policy_id: str | None = Field(default=None, max_length=64)
    collection_id: str | None = Field(default=None, max_length=36)


def engine_of(request):
    engine = getattr(request.app.state, "face_engine", None)
    if engine is None:
        raise HTTPException(503, "Model local chưa sẵn sàng.")
    return engine


def current_config(db, request):
    identity = selected_policy(db, getattr(request.app.state, "attendance_policy_id", None))
    policy = db.get(RecognitionPolicy, identity, populate_existing=True) if identity else None
    if policy and policy.enabled:
        return policy
    # A stopped pilot retains its tested threshold, but can resume only through an admin mutation.
    for previous in db.scalars(select(RecognitionPolicy).where(RecognitionPolicy.mode == "functional_trial")
            .order_by(RecognitionPolicy.validated_at.desc(), RecognitionPolicy.id.desc())):
        if previous.evidence.get("scope") in {PILOT_SCOPE, SINGLE_SCOPE}:
            return previous
    return policy


def membership(policy):
    if policy.evidence.get("scope") == PILOT_SCOPE:
        return list(policy.evidence.get("templates", []))
    if policy.evidence.get("scope") == SINGLE_SCOPE:
        keys = ("participant_id", "biometric_revision", "template_id", "template_sha256")
        if not all(key in policy.evidence for key in keys):
            raise HTTPException(409, "Cấu hình thử nguồn thiếu thông tin mẫu.")
        return [{key: policy.evidence[key] for key in keys}]
    raise HTTPException(409, "Cấu hình nguồn không phải cấu hình thử local đã kiểm chứng.")


def validate_controls(db, gallery, model, dimensions, threshold, margin):
    checked, tested_people, rejected, reused = 0, set(), 0, 0
    references = {template.quality.get("source_fingerprint") for template in db.scalars(
        select(FaceTemplate).where(FaceTemplate.model_id == model))}
    for sample, _collection, person in db.execute(select(CollectionSample, FaceCollection, Employee)
            .join(FaceCollection, CollectionSample.collection_id == FaceCollection.id)
            .join(Employee, Employee.id == FaceCollection.employee_id)
            .where(Employee.active == True, FaceCollection.purpose == "calibration",  # noqa: E712
                   FaceCollection.status.in_(["open", "complete"]), FaceCollection.model_id == model,
                   FaceCollection.biometric_revision == Employee.biometric_revision)):
        if person.id not in gallery.samples:
            continue
        if sample.fingerprint in references:
            reused += 1
            continue
        if (sample.model_id != model or sample.dimensions != dimensions or len(sample.vector) != dimensions * 4
                or sample.quality.get("accepted") is not True):
            raise HTTPException(409, "Có ảnh hiệu chỉnh không hợp lệ; chưa đổi cấu hình.")
        try:
            ranking = gallery.rank(np.frombuffer(sample.vector, dtype="<f4"), model)
        except ValueError as error:
            raise HTTPException(409, "Vector hiệu chỉnh không hợp lệ; chưa đổi cấu hình.") from error
        decision = (decide(ranking, threshold, margin) if ranking.second_score is not None
                    else "matched" if ranking.first_score > threshold else "unknown")
        checked += 1
        tested_people.add(person.id)
        rejected += decision != "matched" or ranking.first_id != person.id
    if rejected:
        raise HTTPException(409, "Danh sách mới làm ảnh hiệu chỉnh hiện có không còn nhận đúng. Cấu hình cũ được giữ nguyên.")
    # Training-reference separation is a consistency gate, not an accuracy estimate.
    for identity, vectors in gallery.samples.items():
        for vector in vectors:
            ranking = gallery.rank(vector, model)
            if ranking.first_id != identity or (ranking.second_score is not None and ranking.margin <= margin):
                raise HTTPException(409, "Mẫu các hồ sơ quá giống hoặc trùng nhau. Cần kiểm tra lại đúng người trước khi đưa vào chấm công.")
    return {"independent_control_images": checked, "control_people": len(tested_people),
            "people_without_independent_controls": len(gallery.samples)-len(tested_people),
            "reused_controls_excluded": reused, "group_accuracy_validated": False, "pad_validated": False}


def publish(db, request, person_id, payload, *, remove=False):
    engine = engine_of(request)
    lock_calendar(db)
    person = db.get(Employee, person_id, populate_existing=True)
    if not person:
        raise HTTPException(404, "Không có hồ sơ nhân viên.")
    lock_employee(db, person.id, expected_revision=payload.expected_revision, active_only=not remove)
    source = current_config(db, request)
    if not source or source.id != payload.expected_policy_id:
        raise HTTPException(409, "Cấu hình đã thay đổi hoặc chưa có ngưỡng thử đã kiểm tra. Hãy tải lại trạng thái.")
    if (source.model_id != engine.model_id or source.mode != "functional_trial" or source.pad_verified
            or source.scoring_rule != SCORING_RULE or not source.validated_at):
        raise HTTPException(409, "Cấu hình nguồn không phù hợp model/chế độ hiện tại.")
    pins = [item for item in membership(source) if item.get("participant_id") != person.id]
    if not remove:
        query = select(FaceCollection).where(FaceCollection.employee_id == person.id,
            FaceCollection.biometric_revision == person.biometric_revision, FaceCollection.model_id == engine.model_id,
            FaceCollection.purpose == "enrollment", FaceCollection.status == "complete")
        if payload.collection_id:
            query = query.where(FaceCollection.id == payload.collection_id)
        collection = db.scalar(query.order_by(FaceCollection.completed_at.desc(), FaceCollection.created_at.desc()))
        if not collection:
            raise HTTPException(409, "Cần bộ mẫu tham chiếu đã hoàn tất của hồ sơ này; không dùng ảnh hiệu chỉnh/đánh giá làm mẫu.")
        samples = db.scalars(select(CollectionSample).where(CollectionSample.collection_id == collection.id)
                             .order_by(CollectionSample.fingerprint)).all()
        if not 1 <= len(samples) <= 10:
            raise HTTPException(409, "Bộ mẫu tham chiếu chưa có dữ liệu hợp lệ.")
        for sample in samples:
            if (sample.model_id != engine.model_id or sample.dimensions != engine.dimensions
                    or len(sample.vector) != engine.dimensions * 4 or sample.quality.get("accepted") is not True):
                raise HTTPException(409, "Bộ mẫu tham chiếu có vector/ảnh không hợp lệ.")
            try:
                vector = normalized(np.frombuffer(sample.vector, dtype="<f4"), engine.dimensions)
            except ValueError as error:
                raise HTTPException(409, "Vector tham chiếu không hợp lệ.") from error
            template = FaceTemplate(employee_id=person.id, biometric_revision=person.biometric_revision,
                model_id=engine.model_id, dimensions=engine.dimensions, vector=np.asarray(vector, dtype="<f4").tobytes(),
                quality={"source_collection_id": collection.id, "source_fingerprint": sample.fingerprint,
                         "scope": PILOT_SCOPE})
            db.add(template)
            db.flush()
            pins.append(pin(template))
    return publish_pins(db, source, pins, engine, person.id, remove=remove)


def publish_pins(db, source, pins, engine, entity_id, *, remove=False, commit=True):
    """Caller holds CalendarGate. Publish an entire version once, including batch imports."""
    try:
        gallery = gallery_from_pins(db, pins, engine.model_id, engine.dimensions) if pins else None
    except ValueError as error:
        raise HTTPException(409, "Bộ mẫu hiện tại chưa hợp lệ; chưa đổi cấu hình.") from error
    if gallery and gallery.samples:
        controls = validate_controls(db, gallery, engine.model_id, engine.dimensions, source.threshold, source.minimum_margin)
        pins = [item for item in pins if item.get("participant_id") in gallery.samples]
    else:
        pins, controls = [], {"group_accuracy_validated": False, "pad_validated": False}
    db.execute(update(RecognitionPolicy).where(RecognitionPolicy.enabled == True)  # noqa: E712
               .values(enabled=False).execution_options(synchronize_session=False))
    db.execute(update(RecognitionSession).where(RecognitionSession.state.in_(["pending", "verified"]))
               .values(state="rejected").execution_options(synchronize_session=False))
    policy = RecognitionPolicy(id=PILOT_PREFIX+uuid4().hex, model_id=engine.model_id, scoring_rule=SCORING_RULE,
        threshold=source.threshold, minimum_margin=source.minimum_margin, mode="functional_trial", pad_verified=False,
        enabled=bool(pins), validated_at=utcnow(), evidence={"scope": PILOT_SCOPE, "sequence_protocol": "stable-three-v1",
            "templates": pins, "source_policy_id": source.id, "threshold_changed": False, "metrics": controls})
    db.add(policy)
    db.add(AuditLog(action="pilot_employee_removed" if remove else "pilot_employee_enrolled", entity_id=entity_id,
        details={"policy_id": policy.id, "source_policy_id": source.id, "participants": len(gallery.samples) if gallery else 0,
                 "scope": PILOT_SCOPE, "threshold_changed": False}))
    if commit:
        db.commit()
    else:
        db.flush()
    return {"policy_id": policy.id, "enabled": policy.enabled, "participants": len(gallery.samples) if gallery else 0,
            "threshold": policy.threshold, "minimum_margin": policy.minimum_margin, "threshold_changed": False,
            "metrics": controls, "restart_required": False}


@router.get("/employees/{employee_id}")
def employee_status(employee_id: str, request: Request, db: Db, user: Admin):
    person = db.get(Employee, employee_id)
    if not person:
        raise HTTPException(404, "Không có hồ sơ nhân viên.")
    policy = current_config(db, request)
    engine = engine_of(request)
    pins = membership(policy) if policy else []
    included = False
    participants = 0
    if pins and policy and policy.model_id == engine.model_id:
        try:
            gallery = gallery_from_pins(db, pins, engine.model_id, engine.dimensions)
            included, participants = person.id in gallery.samples, len(gallery.samples)
        except ValueError:
            pass
    return {"revision": person.biometric_revision, "active": person.active,
            "policy_id": policy.id if policy else None, "enabled": bool(policy and policy.enabled),
            "included": included, "participants": participants,
            "threshold": policy.threshold if policy else None,
            "minimum_margin": policy.minimum_margin if policy else None,
            "group_accuracy_validated": False, "pad_validated": False}


@router.post("/employees/{employee_id}/enroll")
def enroll(employee_id: str, payload: PublishInput, request: Request, db: Db, user: MutationAdmin):
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Đang cập nhật danh sách nhận diện. Hãy tải lại sau.")
    try:
        return publish(db, request, employee_id, payload)
    finally:
        slots.release()


@router.post("/employees/{employee_id}/remove")
def remove(employee_id: str, payload: PublishInput, request: Request, db: Db, user: MutationAdmin):
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Đang cập nhật danh sách nhận diện. Hãy tải lại sau.")
    try:
        return publish(db, request, employee_id, payload, remove=True)
    finally:
        slots.release()
