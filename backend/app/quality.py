"""Image-quality gates. Defaults are provisional until tested on the real cameras."""
from dataclasses import dataclass
from math import atan2, degrees

import cv2
import numpy as np


@dataclass(frozen=True)
class QualityPolicy:
    minimum_face_pixels: int = 96
    minimum_brightness: float = 45
    maximum_brightness: float = 225
    minimum_sharpness: float = 40
    maximum_roll_degrees: float = 25
    maximum_nose_offset: float = 0.45


def assess_quality(image: np.ndarray, faces: np.ndarray, policy: QualityPolicy | None = None) -> dict:
    policy = policy or QualityPolicy()
    if len(faces) == 0:
        return {"accepted": False, "reason": "no_face", "face_count": 0}
    if len(faces) != 1:
        return {"accepted": False, "reason": "multiple_faces", "face_count": len(faces)}
    face = faces[0]
    if not np.isfinite(face).all():
        return {"accepted": False, "reason": "invalid_landmarks", "face_count": 1}
    x, y, width, height = [float(v) for v in face[:4]]
    result = {"accepted": False, "face_count": 1, "frame_width": image.shape[1], "frame_height": image.shape[0],
              "box": [round(v, 1) for v in [x,y,width,height]]}
    if min(width, height) < policy.minimum_face_pixels:
        return result | {"reason": "face_too_small"}
    if x < 0 or y < 0 or x + width > image.shape[1] or y + height > image.shape[0]:
        return result | {"reason": "face_clipped"}
    gray = cv2.cvtColor(image[int(y):int(y+height), int(x):int(x+width)], cv2.COLOR_BGR2GRAY)
    normalized = cv2.resize(gray, (112,112))
    brightness = float(normalized.mean())
    sharpness = float(cv2.Laplacian(normalized, cv2.CV_64F).var())
    result |= {"brightness": round(brightness,2), "sharpness": round(sharpness,2)}
    if brightness < policy.minimum_brightness:
        return result | {"reason": "too_dark"}
    if brightness > policy.maximum_brightness:
        return result | {"reason": "too_bright"}
    if sharpness < policy.minimum_sharpness:
        return result | {"reason": "blurred"}
    eye1, eye2, nose = face[4:6], face[6:8], face[8:10]
    eye_delta = eye2 - eye1
    eye_distance = float(np.linalg.norm(eye_delta))
    if eye_distance < 10:
        return result | {"reason": "invalid_landmarks"}
    roll = abs(degrees(atan2(float(eye_delta[1]), abs(float(eye_delta[0])))))
    nose_offset = abs(float(nose[0] - (eye1[0]+eye2[0])/2)) / eye_distance
    result |= {"roll_degrees": round(roll,2), "nose_offset": round(nose_offset,3)}
    mouth_mid = (face[10:12] + face[12:14]) / 2
    eye_mid = (eye1 + eye2) / 2
    eye_to_mouth = float(mouth_mid[1] - eye_mid[1])
    if eye_to_mouth < 10:
        return result | {"reason": "invalid_landmarks"}
    # Relative landmark ratios, not calibrated head angles or liveness evidence.
    result |= {"yaw_ratio": round(float(nose[0]-eye_mid[0])/eye_distance, 4),
               "pitch_ratio": round(float(nose[1]-eye_mid[1])/eye_to_mouth, 4)}
    if roll > policy.maximum_roll_degrees or nose_offset > policy.maximum_nose_offset:
        return result | {"reason": "look_straight"}
    return result | {"accepted": True, "reason": "accepted"}
