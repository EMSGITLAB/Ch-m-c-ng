import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Unicode,
    UnicodeText,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Unicode(160), nullable=False)
    department: Mapped[str] = mapped_column(Unicode(120), default="")
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    biometric_revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class FaceTemplate(Base):
    __tablename__ = "face_templates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    biometric_revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (CheckConstraint("direction IN ('in', 'out')", name="ck_device_direction"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    direction: Mapped[str] = mapped_column(String(3), default="in")
    token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(default=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AttendanceEvent(Base):
    __tablename__ = "attendance_events"
    __table_args__ = (CheckConstraint("direction IN ('in', 'out')", name="ck_event_direction"),
                      Index("ix_attendance_person_direction_time", "employee_id", "direction", "server_time"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    request_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    server_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    recognition_version: Mapped[str] = mapped_column(String(100), nullable=False)


class Shift(Base):
    __tablename__ = "shifts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    family_id: Mapped[str] = mapped_column(String(36), default=new_id, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Ho_Chi_Minh", server_default="Asia/Ho_Chi_Minh", nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    name: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    start_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    end_minute: Mapped[int] = mapped_column(Integer, nullable=False)
    rules: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (CheckConstraint("start_minute BETWEEN 0 AND 1439 AND end_minute BETWEEN 0 AND 1439", name="ck_shift_minutes"),
                     UniqueConstraint("family_id","revision",name="uq_shift_family_revision"))


class ShiftAssignment(Base):
    __tablename__ = "shift_assignments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    shift_id: Mapped[str] = mapped_column(ForeignKey("shifts.id"))
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    __table_args__ = (Index("uq_active_employee_shift_date","employee_id","shift_id","work_date",unique=True,
                           mssql_where=text("cancelled_at IS NULL"),sqlite_where=text("cancelled_at IS NULL"),
                           postgresql_where=text("cancelled_at IS NULL")),)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str | None] = mapped_column(UnicodeText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AdminUser(Base):
    __tablename__ = "admin_users"
    __table_args__ = (CheckConstraint("id = 1", name="ck_single_admin"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    username: Mapped[str] = mapped_column(Unicode(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("admin_users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DevicePairing(Base):
    __tablename__ = "device_pairings"
    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)


class FaceCollection(Base):
    __tablename__ = "face_collections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True, nullable=False)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    biometric_revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    guidance_protocol: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("purpose IN ('enrollment','calibration','evaluation')",name="ck_collection_purpose"),
        CheckConstraint("status IN ('open','complete','cancelled')",name="ck_collection_status"),
        CheckConstraint("sample_count BETWEEN 0 AND 10",name="ck_collection_count"),
    )


class CollectionSample(Base):
    __tablename__ = "collection_samples"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    collection_id: Mapped[str] = mapped_column(ForeignKey("face_collections.id",ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    vector: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    quality: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        UniqueConstraint("collection_id","position",name="uq_collection_position"),
        UniqueConstraint("model_id","fingerprint",name="uq_model_sample_fingerprint"),
    )


class ImportedFacePhoto(Base):
    __tablename__ = "imported_face_photos"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), nullable=False, index=True)
    sample_id: Mapped[str | None] = mapped_column(ForeignKey("collection_samples.id"), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    batch_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    image: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_type: Mapped[str] = mapped_column(String(30), nullable=False)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    biometric_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    quality: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (Index("uq_imported_photo_sample", "sample_id", unique=True,
        mssql_where=text("sample_id IS NOT NULL"), sqlite_where=text("sample_id IS NOT NULL"),
        postgresql_where=text("sample_id IS NOT NULL")),)


class RecognitionPolicy(Base):
    __tablename__ = "recognition_policies"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    scoring_rule: Mapped[str] = mapped_column(String(50), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    minimum_margin: Mapped[float] = mapped_column(Float, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default="disabled", nullable=False)
    pad_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    __table_args__ = (
        CheckConstraint("threshold BETWEEN -1 AND 1 AND minimum_margin BETWEEN 0 AND 2", name="ck_policy_thresholds"),
        CheckConstraint("mode IN ('disabled','supervised','automatic','functional_trial')", name="ck_policy_mode"),
        CheckConstraint("enabled = 0 OR (validated_at IS NOT NULL AND mode <> 'disabled')", name="ck_policy_validated"),
        CheckConstraint("mode <> 'automatic' OR pad_verified = 1", name="ck_policy_automatic_pad"),
    )


class RecognitionSession(Base):
    __tablename__ = "recognition_sessions"
    request_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False, index=True)
    policy_id: Mapped[str] = mapped_column(ForeignKey("recognition_policies.id"), nullable=False)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    state: Mapped[str] = mapped_column(String(12), default="pending", nullable=False)
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    biometric_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_model_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    supervisor_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    receipt: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    device_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_frame_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    __table_args__ = (
        CheckConstraint("direction IN ('in','out')", name="ck_recognition_direction"),
        CheckConstraint("state IN ('pending','verified','used','rejected')", name="ck_recognition_state"),
        CheckConstraint("state NOT IN ('verified','used') OR (employee_id IS NOT NULL AND biometric_revision IS NOT NULL AND verified_model_id IS NOT NULL)", name="ck_recognition_verified"),
        CheckConstraint("state <> 'used' OR receipt IS NOT NULL", name="ck_recognition_receipt"),
    )


class RecognitionFrame(Base):
    __tablename__ = "recognition_frames"
    request_id: Mapped[str] = mapped_column(ForeignKey("recognition_sessions.request_id"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    accepted: Mapped[bool] = mapped_column(nullable=False)
    employee_id: Mapped[str | None] = mapped_column(ForeignKey("employees.id"), nullable=True)
    biometric_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    response: Mapped[dict] = mapped_column(JSON, nullable=False)
    __table_args__ = (
        CheckConstraint("position BETWEEN 1 AND 12", name="ck_recognition_frame_position"),
        CheckConstraint("accepted = 0 OR (employee_id IS NOT NULL AND biometric_revision IS NOT NULL)", name="ck_recognition_frame_identity"),
    )


class CalendarGate(Base):
    __tablename__ = "calendar_gate"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    __table_args__ = (CheckConstraint("id = 1",name="ck_calendar_gate_singleton"),)


class TimesheetPeriod(Base):
    __tablename__ = "timesheet_periods"
    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    status: Mapped[str] = mapped_column(String(8), default="open", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    protected_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    protected_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        CheckConstraint("status IN ('open','locked') AND revision >= 0",name="ck_period_state"),
        CheckConstraint("status <> 'locked' OR (revision > 0 AND locked_at IS NOT NULL AND protected_from IS NOT NULL AND protected_until IS NOT NULL)",name="ck_period_locked"),
    )


class TimesheetSnapshot(Base):
    __tablename__ = "timesheet_snapshots"
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=new_id)
    month: Mapped[str] = mapped_column(ForeignKey("timesheet_periods.month"),nullable=False)
    revision: Mapped[int] = mapped_column(Integer,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("admin_users.id"),nullable=False)
    reason: Mapped[str] = mapped_column(UnicodeText,nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64),nullable=False)
    calculation_version: Mapped[str] = mapped_column(String(50),nullable=False)
    payload: Mapped[dict] = mapped_column(JSON,nullable=False)
    protection: Mapped[dict] = mapped_column(JSON,nullable=False)
    __table_args__ = (UniqueConstraint("month","revision",name="uq_snapshot_month_revision"),)


class AttendanceAdjustment(Base):
    __tablename__ = "attendance_adjustments"
    id: Mapped[str] = mapped_column(String(36),primary_key=True,default=new_id)
    request_id: Mapped[str] = mapped_column(String(36),unique=True,nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64),nullable=False)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"),nullable=False,index=True)
    kind: Mapped[str] = mapped_column(String(4),nullable=False)
    direction: Mapped[str] = mapped_column(String(3),nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False,index=True)
    target_event_id: Mapped[str | None] = mapped_column(ForeignKey("attendance_events.id"),nullable=True)
    target_adjustment_id: Mapped[str | None] = mapped_column(ForeignKey("attendance_adjustments.id"),nullable=True)
    reason: Mapped[str] = mapped_column(UnicodeText,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("admin_users.id"),nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(UnicodeText,nullable=True)
    __table_args__ = (
        CheckConstraint("kind IN ('add','void') AND direction IN ('in','out')",name="ck_adjustment_kind_direction"),
        CheckConstraint("(kind = 'add' AND target_event_id IS NULL AND target_adjustment_id IS NULL) OR (kind = 'void' AND ((target_event_id IS NOT NULL AND target_adjustment_id IS NULL) OR (target_event_id IS NULL AND target_adjustment_id IS NOT NULL)))",name="ck_adjustment_target"),
        Index("uq_active_void_event","target_event_id",unique=True,
              mssql_where=text("kind = 'void' AND revoked_at IS NULL AND target_event_id IS NOT NULL"),
              sqlite_where=text("kind = 'void' AND revoked_at IS NULL AND target_event_id IS NOT NULL"),
              postgresql_where=text("kind = 'void' AND revoked_at IS NULL AND target_event_id IS NOT NULL")),
        Index("uq_active_void_adjustment","target_adjustment_id",unique=True,
              mssql_where=text("kind = 'void' AND revoked_at IS NULL AND target_adjustment_id IS NOT NULL"),
              sqlite_where=text("kind = 'void' AND revoked_at IS NULL AND target_adjustment_id IS NOT NULL"),
              postgresql_where=text("kind = 'void' AND revoked_at IS NULL AND target_adjustment_id IS NOT NULL")),
    )

