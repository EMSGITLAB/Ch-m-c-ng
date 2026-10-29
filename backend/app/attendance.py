"""Atomic recording after server-side recognition; no client-supplied identity."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select, update

from .biometric_state import lock_employee
from .calendar_guard import assert_event_writable, lock_calendar
from .devices import aware
from .matching import SCORING_RULE
from .models import AttendanceEvent, AuditLog, Device, Employee, RecognitionPolicy, RecognitionSession


def live_device(db, device_id, token_hash, now, lock=False):
    filters = [
        Device.id == device_id,
        Device.active == True,  # noqa: E712
        Device.token_hash == token_hash,
        Device.token_expires_at > now,
    ]
    if lock:
        exists = db.execute(
            update(Device)
            .where(*filters)
            .values(last_seen_at=Device.last_seen_at)
            .returning(Device.id)
            .execution_options(synchronize_session=False)
        ).scalar_one_or_none()
    else:
        exists = db.scalar(select(Device.id).where(*filters))
    if not exists or not token_hash:
        raise HTTPException(401, "Quyền kiosk đã hết hạn, thay đổi hoặc bị thu hồi.")
    return db.scalar(select(Device).where(Device.id == device_id).execution_options(populate_existing=True))


def commit_recognition(
    db,
    request_id,
    device_id,
    token_hash,
    policy_id,
    model_id,
    cooldown_seconds,
    clock=lambda: datetime.now(UTC),
):
    """Lock order: calendar → policy → employee → device → recognition session.

    The recognition pipeline alone may mark a session verified. That pipeline
    is not enabled yet; this service is exercised on isolated test databases.
    """
    if not 1 <= cooldown_seconds <= 3600:
        raise ValueError("invalid_cooldown")
    lock_calendar(db)
    session = db.get(RecognitionSession, request_id)
    if not session or session.device_id != device_id:
        raise HTTPException(404, "Không có yêu cầu của kiosk này.")
    if session.device_token_hash and session.device_token_hash != token_hash:
        raise HTTPException(401, "Phiên nhận diện thuộc quyền kiosk đã bị thay đổi.")
    now = clock()
    live_device(db, device_id, token_hash, now)
    # A lost response may be retrieved after policy retirement/session expiry.
    if session.state == "used":
        return dict(session.receipt)
    if session.state != "verified":
        raise HTTPException(409, "Yêu cầu chưa được máy chủ xác nhận nhận diện hợp lệ.")
    if session.policy_id != policy_id or session.verified_model_id != model_id:
        raise HTTPException(409, "Phiên nhận diện thuộc cấu hình/model cũ.")
    binding = (
        session.employee_id,
        session.biometric_revision,
        session.policy_id,
        session.verified_model_id,
        session.direction,
    )
    valid_policy = db.execute(
        update(RecognitionPolicy)
        .where(
            RecognitionPolicy.id == policy_id,
            RecognitionPolicy.enabled == True,  # noqa: E712
            RecognitionPolicy.model_id == model_id,
            RecognitionPolicy.scoring_rule == SCORING_RULE,
            RecognitionPolicy.validated_at <= now,
            RecognitionPolicy.mode.in_(["supervised", "automatic", "functional_trial"]),
        )
        .values(enabled=RecognitionPolicy.enabled)
        .returning(RecognitionPolicy.id)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    if not valid_policy:
        raise HTTPException(503, "Cấu hình nhận diện chưa được kiểm chứng hoặc đã ngừng sử dụng.")
    lock_employee(db, session.employee_id, expected_revision=session.biometric_revision, active_only=True)
    device = live_device(db, device_id, token_hash, clock(), lock=True)
    session = db.scalar(
        select(RecognitionSession)
        .where(RecognitionSession.request_id == request_id)
        .execution_options(populate_existing=True)
    )
    if session.state == "used":
        result = dict(session.receipt)
        db.commit()
        return result
    now = clock()  # After waiting for locks, never trust a tablet timestamp.
    if binding != (
        session.employee_id,
        session.biometric_revision,
        session.policy_id,
        session.verified_model_id,
        session.direction,
    ):
        raise HTTPException(409, "Quyết định nhận diện đã thay đổi. Cần nhận diện lại.")
    if session.state != "verified" or aware(session.expires_at) <= now:
        raise HTTPException(409, "Phiên nhận diện đã hết hạn hoặc không còn hợp lệ.")
    if session.direction != device.direction:
        raise HTTPException(409, "Chiều Vào/Ra của kiosk đã thay đổi. Cần nhận diện lại.")
    if aware(device.token_expires_at) <= now:
        raise HTTPException(401, "Quyền kiosk đã hết hạn.")
    policy = db.scalar(
        select(RecognitionPolicy).where(RecognitionPolicy.id == policy_id).execution_options(populate_existing=True)
    )
    if policy.mode == "functional_trial":
        from .functional_trial import trial_gallery

        gallery = trial_gallery(db, policy)
        if session.employee_id not in gallery.samples:
            raise HTTPException(409, "Hồ sơ không thuộc cấu hình nhận diện thử đang hoạt động.")
    if policy.mode == "supervised" and (
        not session.supervisor_confirmed_at or aware(session.supervisor_confirmed_at) > now
    ):
        raise HTTPException(409, "Chế độ có giám sát cần xác nhận trực tiếp trước khi ghi công.")
    locked = db.execute(
        update(RecognitionSession)
        .where(
            RecognitionSession.request_id == request_id,
            RecognitionSession.state == "verified",
            RecognitionSession.employee_id == binding[0],
            RecognitionSession.biometric_revision == binding[1],
            RecognitionSession.policy_id == policy_id,
            RecognitionSession.verified_model_id == model_id,
            RecognitionSession.expires_at > now,
        )
        .values(state=RecognitionSession.state)
        .returning(RecognitionSession.request_id)
        .execution_options(synchronize_session=False)
    ).scalar_one_or_none()
    if locked is None:
        raise HTTPException(409, "Phiên nhận diện không còn hợp lệ.")
    employee = db.scalar(
        select(Employee).where(Employee.id == session.employee_id).execution_options(populate_existing=True)
    )
    previous = db.scalar(
        select(AttendanceEvent)
        .where(AttendanceEvent.employee_id == employee.id, AttendanceEvent.direction == session.direction)
        .order_by(AttendanceEvent.server_time.desc(), AttendanceEvent.id.desc())
        .limit(1)
    )
    if previous and aware(previous.server_time) > now:
        raise HTTPException(
            503, "Giờ máy chủ đang lùi so với sự kiện gần nhất. Cần kiểm tra đồng hồ máy chủ."
        )
    duplicate = bool(previous and (now - aware(previous.server_time)).total_seconds() < cooldown_seconds)
    event = (
        previous
        if duplicate
        else AttendanceEvent(
            employee_id=employee.id,
            device_id=device.id,
            request_id=request_id,
            direction=session.direction,
            server_time=now,
            recognition_version=policy_id,
        )
    )
    if not duplicate:
        assert_event_writable(db, employee.id, now)
        db.add(event)
        db.flush()
    original = db.get(RecognitionSession, event.request_id) if duplicate else None
    display = (
        original.receipt
        if original and original.state == "used"
        else {"employee_code": employee.code, "employee_name": employee.name}
    )
    result = {
        "status": "duplicate" if duplicate else "recorded",
        "request_id": request_id,
        "event_id": event.id,
        "employee_code": display["employee_code"],
        "employee_name": display["employee_name"],
        "server_time": aware(event.server_time).isoformat(),
        "direction": event.direction,
        "recognition_version": event.recognition_version,
        "recording_scope": ("local_functional_pilot" if event.recognition_version.startswith("trial-pilot-") else
                            "single_person_functional_trial"
                            if event.recognition_version.startswith("trial-") else "standard"),
    }
    session.state = "used"
    session.receipt = result
    db.add(
        AuditLog(
            action="attendance_duplicate" if duplicate else "attendance_recorded",
            entity_id=event.id,
            details={"request_id": request_id, "device_id": device_id, "policy_id": policy_id},
        )
    )
    db.commit()  # No success is returned before the entire event+receipt commit.
    return dict(result)
