"""Camera-scene geometry, independent of enrollment's oval and identity policy."""

from math import isfinite

from .capture_guidance import QUALITY_FEEDBACK


def face_box(quality):
    """Return a clipped normalized box for the unmirrored complete source frame."""
    try:
        width, height = float(quality["frame_width"]), float(quality["frame_height"])
        x, y, face_width, face_height = map(float, quality["box"])
        if not all(map(isfinite, (width, height, x, y, face_width, face_height))):
            return None
        if min(width, height, face_width, face_height) <= 0:
            return None
        left, top = max(0.0, x / width), max(0.0, y / height)
        right, bottom = min(1.0, (x + face_width) / width), min(1.0, (y + face_height) / height)
        if right <= left or bottom <= top:
            return None
        return [left, top, right - left, bottom - top]
    except (KeyError, TypeError, ValueError):
        return None


def check_scene(quality):
    if not quality.get("accepted"):
        return False, QUALITY_FEEDBACK.get(quality.get("reason"), "Khuôn mặt chưa đủ rõ. Nhìn thẳng và giữ yên.")
    if face_box(quality) is None:
        return False, "Chưa xác định được vị trí khuôn mặt trong hình camera."
    return True, "Đã tìm thấy khuôn mặt. Nhìn thẳng và giữ yên."
