"""Local operator status: aggregate diagnostics only, never biometric records."""

import hmac
import json
import shutil
import threading
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, SecretStr
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .auth import Admin, Db, MutationAdmin
from .calendar_guard import lock_calendar
from .config import PROJECT_ROOT, get_settings
from .models import AuditLog
from .recovery_key_files import preserved_key, record_key_export, save_key
from .revocation_ledger import sync_from_audit
from .runtime_status import attendance_state
from .runtime_supervisor import service_status

router = APIRouter(prefix="/api/admin/operations", tags=["operations"])
key_slots = threading.BoundedSemaphore(1)


class KeyExportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: SecretStr
    confirmation: SecretStr


def backup_state(runtime, now):
    for filename, kind in (("last-backup.json", "operational"),
                           ("last-pre-migration-backup.json", "pre_migration")):
        path = runtime / "backups" / filename
        if not path.is_file():
            continue
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
            timestamp = (datetime.fromisoformat(metadata["completed_at"]) if metadata.get("completed_at")
                         else datetime.fromtimestamp(path.stat().st_mtime, UTC))
            if timestamp.tzinfo is None or timestamp > now + timedelta(minutes=1):
                raise ValueError("Invalid backup time")
            return {"available": True, "kind": kind, "encrypted": metadata.get("encrypted") is True,
                    "checksum_verified": metadata.get("checksum_verified") is True,
                    "updated_at": timestamp.isoformat(), "overdue": now - timestamp > timedelta(hours=24)}
        except (OSError, ValueError, KeyError, TypeError):
            return {"available": True, "kind": "invalid_metadata", "encrypted": False,
                    "checksum_verified": False, "updated_at": None, "overdue": True}
    return {"available": False, "kind": None, "encrypted": False, "checksum_verified": False,
            "updated_at": None, "overdue": True}


def database_probe(db):
    try:
        return db.scalar(text("SELECT 1")) == 1
    except SQLAlchemyError:
        db.rollback()
        return False


def snapshot(db, engine, pad_engine, policy_id):
    now = datetime.now(UTC)
    settings = get_settings()
    disk = shutil.disk_usage(settings.runtime_dir if settings.runtime_dir.exists() else PROJECT_ROOT)
    database_ok = database_probe(db)
    attendance = (attendance_state(db, engine, policy_id) if database_ok else
                  {"attendance_enabled": False, "attendance_mode": None})
    service = service_status(settings.runtime_dir / "service")
    backup = backup_state(settings.runtime_dir, now)
    key_preserved = preserved_key(settings.runtime_dir)
    alerts = []
    if disk.free < 2 * 1024 ** 3:
        alerts.append("disk_low")
    if not database_ok:
        alerts.append("database_unavailable")
    if engine is None:
        alerts.append("recognition_unavailable")
    if not attendance["attendance_enabled"]:
        alerts.append("attendance_disabled")
    if not service["running"]:
        alerts.append("supervisor_stopped")
    if not backup["available"]:
        alerts.append("backup_missing")
    else:
        if not backup["checksum_verified"]:
            alerts.append("backup_unverified")
        if not backup["encrypted"]:
            alerts.append("backup_unencrypted")
        if backup["overdue"]:
            alerts.append("backup_overdue")
    if (settings.runtime_dir / "backups/last-backup-error.json").is_file():
        alerts.append("backup_failed")
    if backup["available"] and backup["encrypted"] and not key_preserved:
        alerts.append("recovery_key_not_preserved")
    return {"checked_at": now.isoformat(), "database_ok": database_ok,
            "recognition_ready": engine is not None, "experimental_pad_ready": pad_engine is not None,
            "attendance_enabled": attendance["attendance_enabled"], "attendance_mode": attendance["attendance_mode"],
            "supervisor": {"running": service["running"], "state": service.get("state", "not_started"),
                           "restart_count": service.get("restart_count", 0)},
            "disk": {"free_bytes": disk.free, "total_bytes": disk.total}, "backup": backup,
            "recovery_key_preserved": key_preserved, "alerts": alerts}


@router.get("/status")
def status(request: Request, db: Db, user: Admin):
    return snapshot(db, getattr(request.app.state, "face_engine", None),
                    getattr(request.app.state, "pad_engine", None),
                    getattr(request.app.state, "attendance_policy_id", None))


@router.post("/recovery-key/export")
def export_key(payload: KeyExportInput, db: Db, user: MutationAdmin):
    password = payload.password.get_secret_value()
    if not 12 <= len(password) <= 512:
        raise HTTPException(422, "Mật khẩu khôi phục cần từ 12 đến 512 ký tự.")
    if not hmac.compare_digest(password.encode(), payload.confirmation.get_secret_value().encode()):
        raise HTTPException(422, "Hai lần nhập mật khẩu chưa khớp.")
    settings = get_settings()
    if not settings.backup_directory:
        raise HTTPException(409, "Cần cấu hình thư mục backup riêng trước khi bảo quản khóa.")
    if not key_slots.acquire(blocking=False):
        raise HTTPException(429, "Đang bảo quản khóa. Đợi một lúc rồi thử lại.")
    try:
        try:
            lock_calendar(db)
            sync_from_audit(db, settings.runtime_dir, mirror_directory=settings.backup_directory)
            db.rollback()  # No ledger lock is held during password derivation or USB writes.
            result = save_key(settings.runtime_dir, settings.backup_directory, password, publish=False)
        except (OSError, ValueError, RuntimeError) as error:
            raise HTTPException(503, "Chưa lưu được khóa bảo quản. Kiểm tra ổ backup và khóa máy chủ.") from error
        db.add(AuditLog(action="recovery_key_export", entity_id=str(user.id),
                        details={"password_protected": True, "plaintext_key_exported": False}))
        db.commit()
        try:
            record_key_export(settings.runtime_dir, result.pop("_marker"))
        except OSError as error:
            raise HTTPException(503, "Chưa xác nhận lưu được khóa bảo quản. Vui lòng thử lại.") from error
        return result
    finally:
        key_slots.release()
