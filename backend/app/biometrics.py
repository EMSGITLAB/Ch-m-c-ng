from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select

from .auth import Admin, Db, MutationAdmin
from .biometric_state import lock_employee
from .calendar_guard import lock_calendar
from .config import get_settings
from .models import AuditLog, CollectionSample, Employee, FaceCollection, FaceTemplate, ImportedFacePhoto
from .revocation_ledger import merge_ledger

router = APIRouter(prefix="/api/admin/employees", tags=["biometric-data"])


class PurgeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    confirm_employee_code: str
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=5, max_length=500)


@router.get("/{employee_id}/biometrics")
def describe_biometrics(employee_id: str, request: Request, db: Db, user: Admin):
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(404, "Không có hồ sơ nhân viên.")
    templates = db.execute(select(FaceTemplate.model_id, func.count()).where(FaceTemplate.employee_id == employee_id)
                           .group_by(FaceTemplate.model_id)).all()
    collections = db.execute(select(FaceCollection.model_id, func.count(), func.sum(FaceCollection.sample_count))
                             .where(FaceCollection.employee_id == employee_id).group_by(FaceCollection.model_id)).all()
    engine = getattr(request.app.state, "face_engine", None)
    photos = db.scalar(select(func.count()).select_from(ImportedFacePhoto).where(ImportedFacePhoto.employee_id == employee_id))
    return {"employee_id": employee_id, "revision": employee.biometric_revision, "active": employee.active,
            "current_model_id": engine.model_id if engine else None,
            "templates_by_model": [{"model_id": model, "count": count} for model, count in templates],
            "collections_by_model": [{"model_id": model, "collections": count, "samples": samples or 0}
                                     for model, count, samples in collections],
            "images_stored": bool(photos), "imported_photos": photos, "backup_copies_deleted": False}


@router.post("/{employee_id}/biometrics/purge")
def purge_biometrics(employee_id: str, payload: PurgeInput, db: Db, user: MutationAdmin):
    lock_calendar(db)
    employee = db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(404, "Không có hồ sơ nhân viên.")
    if payload.confirm_employee_code != employee.code:
        raise HTTPException(422, "Nhập đúng mã nhân viên để xác nhận xóa dữ liệu khuôn mặt.")
    lock_employee(db, employee_id, expected_revision=payload.expected_revision)
    db.refresh(employee)
    collection_ids = select(FaceCollection.id).where(FaceCollection.employee_id == employee_id)
    photos = db.execute(delete(ImportedFacePhoto).where(ImportedFacePhoto.employee_id == employee_id)
                        .execution_options(synchronize_session=False)).rowcount
    samples = db.execute(delete(CollectionSample).where(CollectionSample.collection_id.in_(collection_ids))
                         .execution_options(synchronize_session=False)).rowcount
    collections = db.execute(delete(FaceCollection).where(FaceCollection.employee_id == employee_id)
                             .execution_options(synchronize_session=False)).rowcount
    templates = db.execute(delete(FaceTemplate).where(FaceTemplate.employee_id == employee_id)
                           .execution_options(synchronize_session=False)).rowcount
    employee.biometric_revision += 1
    counts = {"templates": templates, "collections": collections, "samples": samples}
    db.add(AuditLog(action="biometrics_purge", entity_id=employee_id, reason=payload.reason,
                    details={"deleted": counts, "imported_photos_deleted": photos, "revision": employee.biometric_revision, "backup_copies_deleted": False}))
    db.flush()
    try:
        # Persist the deletion floor before commit. A subsequent commit failure
        # leaves a conservative deletion intent for recovery, never a revival.
        settings = get_settings()
        merge_ledger(settings.runtime_dir, {employee_id: employee.biometric_revision},
                     mirror_directory=settings.backup_directory)
    except (OSError, ValueError, RuntimeError) as error:
        db.rollback()
        raise HTTPException(503, "Chưa lưu được dấu xóa phục vụ khôi phục. Chưa xác nhận xóa mẫu.") from error
    db.commit()
    return {"deleted": counts, "imported_photos_deleted": photos, "revision": employee.biometric_revision, "employee_preserved": True,
            "attendance_preserved": True, "backup_copies_deleted": False,
            "message": "Đã xóa mẫu khuôn mặt trong database đang chạy. Hồ sơ và lịch sử công được giữ lại; bản sao lưu có vòng đời riêng."}
