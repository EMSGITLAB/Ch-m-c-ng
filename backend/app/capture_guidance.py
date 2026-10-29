"""Provisional capture guidance from 2D landmarks; requires real-camera validation."""
from math import isfinite

PROTOCOL = "relative-pose-v1"
POSES = ["front", "left", "right", "up", "down"] * 2
INSTRUCTIONS = {
    "front": ("Nhìn thẳng", "Nhìn vào camera, giữ đầu thẳng và cằm ngang. Thấy rõ cả hai mắt, mũi và miệng.", "◎"),
    "left": ("Quay nhẹ sang trái của bạn", "Quay mặt nhẹ về bên trái của chính bạn, giống khuôn mặt minh họa trong hình gương. Giữ cằm ngang, vẫn thấy cả hai mắt; không nghiêng đầu sang vai.", "←"),
    "right": ("Quay nhẹ sang phải của bạn", "Quay mặt nhẹ về bên phải của chính bạn, giống khuôn mặt minh họa trong hình gương. Giữ cằm ngang, vẫn thấy cả hai mắt; không nghiêng đầu sang vai.", "→"),
    "up": ("Nâng cằm nhẹ", "Ngẩng cằm lên một chút, mắt vẫn nhìn camera. Không ngửa đầu quá nhiều.", "↑"),
    "down": ("Hạ cằm nhẹ", "Cúi cằm xuống một chút, mắt vẫn nhìn camera. Không cúi quá sâu.", "↓"),
}
QUALITY_FEEDBACK = {
    "no_face": "Chưa thấy khuôn mặt. Đưa mặt vào giữa khung hình.",
    "multiple_faces": "Có nhiều khuôn mặt. Chỉ một người đứng trước camera.",
    "face_too_small": "Khuôn mặt quá nhỏ. Đến gần camera hơn một chút.",
    "face_clipped": "Khuôn mặt bị cắt. Lùi nhẹ và căn toàn bộ mặt vào giữa khung.",
    "too_dark": "Ảnh quá tối. Tăng ánh sáng phía trước khuôn mặt.",
    "too_bright": "Ảnh quá sáng. Tránh ánh sáng chiếu trực tiếp vào mặt.",
    "blurred": "Ảnh bị mờ. Giữ yên và chờ camera lấy nét rồi chụp lại.",
    "look_straight": "Mặt quay hoặc nghiêng quá nhiều. Quay nhẹ hơn, giữ đầu ngay ngắn và thấy rõ hai mắt.",
    "invalid_landmarks": "Chưa thấy rõ mắt, mũi, miệng. Bỏ vật che mặt và nhìn về camera.",
}


def instruction(count):
    if not 0 <= count < len(POSES):
        return None
    pose = POSES[count]
    title, text, arrow = INSTRUCTIONS[pose]
    return {"position": count+1, "pose": pose, "title": title, "text": text, "arrow": arrow}


def check_pose(count, quality, anchor=None):
    """Check signed displacement relative to the first frontal sample."""
    required = instruction(count)
    if required is None:
        return False, "Bộ mẫu đã đủ 10 ảnh."
    values = [quality.get(key) for key in ("yaw_ratio", "pitch_ratio", "roll_degrees")]
    if any(not isinstance(value, (int, float)) or not isfinite(value) for value in values):
        return False, "Chưa đo được hướng mặt. Để thấy rõ hai mắt, mũi và miệng rồi chụp lại."
    yaw, pitch, roll = values
    pose = required["pose"]
    if count == 0:
        accepted = abs(yaw) <= .14 and .2 <= pitch <= .8 and roll <= 12
    elif not anchor or not all(isinstance(anchor.get(key), (int, float)) and isfinite(anchor[key]) for key in ("yaw_ratio", "pitch_ratio")):
        return False, "Thiếu mẫu nhìn thẳng để đối chiếu. Hãy hủy phiên và bắt đầu bộ mẫu mới."
    else:
        dyaw, dpitch = yaw-anchor["yaw_ratio"], pitch-anchor["pitch_ratio"]
        accepted = {
            "front": abs(dyaw) <= .10 and abs(dpitch) <= .10,
            # Preview is mirrored; uploaded pixels are unmirrored.
            "left": dyaw >= .055 and abs(dpitch) <= .15,
            "right": dyaw <= -.055 and abs(dpitch) <= .15,
            "up": dpitch <= -.045 and abs(dyaw) <= .14,
            "down": dpitch >= .045 and abs(dyaw) <= .14,
        }[pose] and roll <= 15
    return accepted, ("Hướng mặt phù hợp theo kiểm tra sơ bộ." if accepted else
                      f"Hướng mặt chưa phù hợp hoặc thay đổi chưa đủ rõ. {required['text']}")
