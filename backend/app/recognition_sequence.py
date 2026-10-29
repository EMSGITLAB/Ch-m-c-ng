"""Local, ordered recognition frames. This RGB sequence is not liveness/PAD."""

import hashlib
import hmac
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, update

from .attendance import live_device
from .biometric_state import lock_employee
from .calendar_guard import lock_calendar
from .config import get_settings
from .devices import aware
from .functional_trial import MODE as TRIAL_MODE
from .functional_trial import authorize_trial, trial_gallery
from .gallery import load_gallery
from .kiosk_scene import check_scene, face_box
from .matching import SCORING_RULE, decide
from .models import AuditLog, Employee, RecognitionFrame, RecognitionPolicy, RecognitionSession, utcnow

PROTOCOL = "stable-three-v1"
MAX_FRAMES = 12
REQUIRED_FRAMES = 3
TTL_SECONDS = 20


def require_policy(db, policy_id, model_id, now, *, lock=False, validate_gallery=True):
    if not policy_id:
        raise HTTPException(503, "Chưa bật ghi công: cần kiểm chứng cấu hình nhận diện.")
    if lock:
        db.execute(
            update(RecognitionPolicy)
            .where(RecognitionPolicy.id == policy_id)
            .values(enabled=RecognitionPolicy.enabled)
            .execution_options(synchronize_session=False)
        )
    row = db.scalar(
        select(RecognitionPolicy)
        .where(RecognitionPolicy.id == policy_id)
        .execution_options(populate_existing=True)
    )
    if (
        not row
        or not row.enabled
        or row.model_id != model_id
        or row.scoring_rule != SCORING_RULE
        or not row.validated_at
        or aware(row.validated_at) > now
    ):
        raise HTTPException(503, "Cấu hình nhận diện chưa hợp lệ hoặc đã dừng.")
    if row.evidence.get("sequence_protocol") != PROTOCOL:
        raise HTTPException(503, "Cấu hình chưa kiểm chứng cho giao thức chuỗi ảnh này.")
    if row.mode == TRIAL_MODE:
        if validate_gallery:
            trial_gallery(db, row)
        else:
            authorize_trial(db, row)
    elif row.mode != "supervised":
        # No local PAD engine has passed T11 yet. A policy flag alone is not
        # evidence of liveness in this particular camera transaction.
        raise HTTPException(503, "Chưa có bộ kiểm tra giả mạo được kiểm chứng cho ghi công tự động.")
    return row


def owned_session(db, request_id, device_id, token_hash, now):
    live_device(db, device_id, token_hash, now)
    row = db.get(RecognitionSession, request_id, populate_existing=True)
    if not row or row.device_id != device_id:
        raise HTTPException(404, "Không có phiên nhận diện của kiosk này.")
    if not row.device_token_hash or not hmac.compare_digest(row.device_token_hash, token_hash):
        raise HTTPException(401, "Quyền kiosk đã đổi; cần tạo phiên nhận diện mới.")
    if row.state != "used" and aware(row.expires_at) <= now:
        raise HTTPException(410, "Phiên nhận diện hết hạn; chưa có công được ghi cho yêu cầu này.")
    return row


def nonce(row):
    secret = get_settings().session_secret
    if len(secret) < 32:
        raise HTTPException(503, "Chưa cấu hình khóa phiên máy chủ.")
    binding = "|".join(
        [
            PROTOCOL,
            row.request_id,
            row.device_id,
            row.device_token_hash,
            row.policy_id,
            aware(row.expires_at).isoformat(),
        ]
    )
    return hmac.new(secret.encode(), binding.encode(), hashlib.sha256).hexdigest()


def describe(row, policy=None):
    return {
        "request_id": row.request_id,
        "state": row.state,
        "next_frame_index": row.last_frame_index + 1,
        "expires_at": aware(row.expires_at).isoformat(),
        "capture_nonce": nonce(row),
        "required_frames": REQUIRED_FRAMES,
        "maximum_frames": MAX_FRAMES,
        "protocol": PROTOCOL,
        "needs_supervisor": row.state == "verified" and row.supervisor_confirmed_at is None
        and (policy is None or policy.mode != TRIAL_MODE),
        "attendance_recorded": row.state == "used",
        "receipt": row.receipt if row.state == "used" else None,
    }


def create_session(db, request_id, device_id, token_hash, policy_id, model_id):
    lock_calendar(db)
    now = utcnow()
    policy = require_policy(db, policy_id, model_id, now, lock=True)
    device = live_device(db, device_id, token_hash, now, lock=True)
    now = utcnow()
    if aware(device.token_expires_at) <= now:
        raise HTTPException(401, "Quyền kiosk đã hết hạn trong lúc chờ máy chủ.")
    previous = db.get(RecognitionSession, request_id)
    if previous:
        previous = owned_session(db, request_id, device_id, token_hash, now)
        if previous.policy_id != policy_id:
            raise HTTPException(409, "Phiên thuộc cấu hình cũ; cần yêu cầu mới.")
        result = describe(previous, policy)
        db.commit()
        return result
    current = db.scalar(
        select(RecognitionSession.request_id).where(
            RecognitionSession.device_id == device_id,
            RecognitionSession.state.in_(["pending", "verified"]),
            RecognitionSession.expires_at > now,
        )
    )
    if current:
        raise HTTPException(409, "Kiosk còn phiên đang xử lý. Tra cứu kết quả trước khi tạo phiên mới.")
    row = RecognitionSession(
        request_id=request_id,
        device_id=device_id,
        device_token_hash=token_hash,
        policy_id=policy_id,
        direction=device.direction,
        state="pending",
        created_at=now,
        expires_at=now + timedelta(seconds=TTL_SECONDS),
        last_frame_index=0,
    )
    db.add(row)
    db.flush()
    result = describe(row, policy)
    db.commit()
    return result


def append_frame(
    db, request_id, index, device_id, token_hash, policy_id, model_id, fingerprint, vector, quality, received_at=None
):
    # Inference runs before this function, without ledger locks. Every gallery
    # mutation (including employee deactivation/purge) takes this gate first.
    lock_calendar(db)
    now = utcnow()
    # The gallery is loaded once, below, inside the same calendar gate when
    # ranking. Preflight must still authorize the exact active configuration.
    policy = require_policy(db, policy_id, model_id, now, lock=True, validate_gallery=False)
    row = owned_session(db, request_id, device_id, token_hash, now)
    if row.policy_id != policy_id:
        raise HTTPException(409, "Cấu hình nhận diện đã đổi.")
    previous = db.get(RecognitionFrame, (request_id, index))
    if previous:
        if previous.fingerprint != fingerprint:
            raise HTTPException(409, "Vị trí ảnh đã dùng cho ảnh khác. Tra cứu phiên trước khi gửi tiếp.")
        result = dict(previous.response)
        db.commit()
        return result
    if row.state != "pending" or not 1 <= index <= MAX_FRAMES or index != row.last_frame_index + 1:
        raise HTTPException(
            409, "Thứ tự ảnh hoặc trạng thái phiên đã thay đổi. Tra cứu phiên trước khi gửi tiếp."
        )
    if now < aware(row.created_at):
        raise HTTPException(503, "Đồng hồ máy chủ đang lùi; chưa xác nhận chuỗi ảnh.")
    observed = aware(received_at) if received_at is not None else now
    if not aware(row.created_at) <= observed <= now:
        raise HTTPException(503, "Thời điểm máy chủ nhận ảnh chưa hợp lệ; cần thử lại phiên.")
    history = db.scalars(
        select(RecognitionFrame)
        .where(RecognitionFrame.request_id == request_id)
        .order_by(RecognitionFrame.position)
    ).all()
    if history and (observed - aware(history[-1].created_at)).total_seconds() < 0.2:
        raise HTTPException(429, "Các ảnh cần cách nhau ít nhất 0,2 giây.", headers={"Retry-After": "1"})
    accepted, message = False, quality.get("feedback", "Căn mặt vào khung và nhìn thẳng.")
    person = None
    if vector is not None:
        framed, message = check_scene(quality)
        if framed:
            try:
                if policy.mode == TRIAL_MODE:
                    ranking = trial_gallery(db, policy, len(vector)).rank(vector, model_id)
                    decision = (decide(ranking, policy.threshold, policy.minimum_margin)
                                if ranking.second_score is not None else
                                "matched" if ranking.first_score > policy.threshold else "unknown")
                else:
                    ranking = load_gallery(db, model_id, len(vector)).rank(vector, model_id)
                    decision = decide(ranking, policy.threshold, policy.minimum_margin)
            except ValueError as error:
                raise HTTPException(
                    503, "Bộ mẫu vận hành chưa đủ hoặc không tương thích; chưa nhận diện."
                ) from error
            if decision == "matched":
                person = db.get(Employee, ranking.first_id)
                lock_employee(db, person.id, expected_revision=person.biometric_revision, active_only=True)
                accepted = True
                message = "Giữ yên và nhìn thẳng để hoàn tất chuỗi ảnh."
            else:
                message = "Chưa xác định được duy nhất hồ sơ phù hợp. Nhìn thẳng và thử lại."
    device = live_device(db, device_id, token_hash, now, lock=True)
    now = utcnow()
    if aware(row.expires_at) <= now:
        raise HTTPException(410, "Phiên nhận diện đã hết hạn trong lúc chờ khóa dữ liệu.")
    if aware(device.token_expires_at) <= now:
        raise HTTPException(401, "Quyền kiosk đã hết hạn trong lúc xử lý ảnh.")
    if row.direction != device.direction:
        raise HTTPException(409, "Chiều kiosk đã thay đổi; cần phiên nhận diện mới.")
    if now < observed or now < aware(history[-1].created_at if history else row.created_at):
        raise HTTPException(503, "Đồng hồ máy chủ đang lùi; chưa xác nhận chuỗi ảnh.")
    if any(frame.fingerprint == fingerprint for frame in history):
        accepted, message = False, "Ảnh trùng khung hình đã gửi. Cần ảnh camera mới."
    if accepted and any(frame.accepted and frame.employee_id != person.id for frame in history):
        accepted, message = False, "Khuôn mặt thay đổi giữa phiên. Bắt đầu phiên mới."
        row.state = "rejected"
    streak = []
    for frame in reversed(history):
        if (
            not frame.accepted
            or not accepted
            or frame.employee_id != person.id
            or frame.biometric_revision != person.biometric_revision
        ):
            break
        streak.append(frame)
    count = len(streak) + 1 if accepted else 0
    # Stability measures when frames arrived at this server, not variable model
    # or SQL processing latency. Expiry and permissions above still use now.
    stable_seconds = (observed - aware(streak[-1].created_at)).total_seconds() if streak else 0
    if accepted and count >= REQUIRED_FRAMES and stable_seconds >= 0.85:
        row.state, row.employee_id, row.biometric_revision = "verified", person.id, person.biometric_revision
        row.verified_model_id = model_id
        message = ("Chuỗi ảnh đã đạt. Đang ghi công thử."
                   if policy.mode == TRIAL_MODE else "Chuỗi ảnh đã đạt. Đang chờ quản trị đối chiếu đúng người.")
    elif index == MAX_FRAMES:
        row.state, message = "rejected", "Chưa hoàn tất chuỗi ảnh trong phiên. Bắt đầu lại."
    row.last_frame_index = index
    result = {
        "request_id": request_id,
        "state": row.state,
        "frame_accepted": accepted,
        "next_frame_index": index + 1,
        "stable_frames": min(count, REQUIRED_FRAMES),
        "required_frames": REQUIRED_FRAMES,
        "feedback": message,
        "face_box": face_box(quality),
        "needs_supervisor": row.state == "verified" and policy.mode != TRIAL_MODE,
        "attendance_recorded": False,
        "anti_spoof_verified": False,
    }
    db.add(
        RecognitionFrame(
            request_id=request_id,
            position=index,
            fingerprint=fingerprint,
            accepted=accepted,
            employee_id=person.id if accepted else None,
            biometric_revision=person.biometric_revision if accepted else None,
            created_at=observed,
            response=result,
        )
    )
    db.commit()
    return result


def confirm_session(db, request_id, payload, user, policy_id, model_id):
    lock_calendar(db)
    now = utcnow()
    require_policy(db, policy_id, model_id, now, lock=True)
    row = db.get(RecognitionSession, request_id)
    if (
        not row
        or row.policy_id != policy_id
        or row.verified_model_id != model_id
        or row.state != "verified"
        or aware(row.expires_at) <= now
    ):
        raise HTTPException(409, "Phiên đã hết hạn hoặc không còn chờ xác nhận.")
    lock_employee(db, row.employee_id, expected_revision=row.biometric_revision, active_only=True)
    person = db.get(Employee, row.employee_id)
    if payload.confirm_employee_code != person.code:
        raise HTTPException(409, "Mã đối chiếu không khớp hồ sơ máy chủ đã nhận diện.")
    device = live_device(db, row.device_id, row.device_token_hash, now, lock=True)
    now = utcnow()
    if aware(row.expires_at) <= now or aware(device.token_expires_at) <= now or row.direction != device.direction:
        raise HTTPException(409, "Phiên hoặc quyền/chiều kiosk đã thay đổi trong lúc chờ đối chiếu.")
    if row.supervisor_confirmed_at is None:
        row.supervisor_confirmed_at = now
        db.add(
            AuditLog(
                action="recognition_supervisor_confirm",
                entity_id=request_id,
                reason=payload.reason,
                details={
                    "admin_id": user.id,
                    "employee_id": row.employee_id,
                    "biometric_revision": row.biometric_revision,
                },
            )
        )
    result = {"request_id": request_id, "confirmed": True, "attendance_recorded": False}
    db.commit()
    return result
