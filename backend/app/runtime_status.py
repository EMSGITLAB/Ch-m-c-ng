"""Report readiness from the configured server policy, never a client flag."""

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from .functional_trial import MODE as TRIAL_MODE
from .functional_trial import trial_gallery
from .gallery import load_gallery
from .models import utcnow
from .policy_selection import PILOT_SCOPE, selected_policy
from .recognition_sequence import require_policy


def attendance_state(db, engine, policy_id):
    policy_id = selected_policy(db, policy_id)
    if engine is None or policy_id is None:
        return {
            "attendance_enabled": False,
            "attendance_mode": None,
            "message": "Camera tự dò mặt để kiểm tra sau khi ghép thiết bị. Chức năng ghi công chưa được bật.",
        }
    try:
        policy = require_policy(db, policy_id, engine.model_id, utcnow(), validate_gallery=False)
        gallery = (trial_gallery(db, policy, engine.dimensions) if policy.mode == TRIAL_MODE
                   else load_gallery(db, engine.model_id, engine.dimensions))
        if len(gallery.samples) < (1 if policy.mode == TRIAL_MODE else 2):
            raise ValueError("insufficient_gallery")
    except (HTTPException, ValueError, SQLAlchemyError):
        return {
            "attendance_enabled": False,
            "attendance_mode": None,
            "message": "Cấu hình hoặc bộ mẫu vận hành chưa sẵn sàng. Chưa bật ghi công.",
        }
    return {
        "attendance_enabled": True,
        "attendance_mode": policy.mode,
        "pilot_people": len(gallery.samples),
        "pilot_scope": policy.evidence.get("scope"),
        "message": (f"Chấm công thử {len(gallery.samples)} người: tự nhận diện và ghi công. Chưa nghiệm thu độ chính xác theo nhóm hoặc chống ảnh giả."
                    if policy.evidence.get("scope") == PILOT_SCOPE else
                    "Thử luồng 1 người: tự nhận diện và ghi công. Chưa nghiệm thu độ chính xác theo nhóm hoặc chống ảnh giả."
                    if policy.mode == TRIAL_MODE else
                    "Kiosk đang ở chế độ đối chiếu: quản trị xác nhận đúng người trước khi ghi công."),
    }
