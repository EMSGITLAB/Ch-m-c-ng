import pytest
from app.auto_capture import check_frame
from app.kiosk_scene import check_scene, face_box


@pytest.mark.parametrize("width,height,box", [
    (1280, 720, [35, 220, 150, 190]),
    (720, 1280, [450, 700, 160, 200]),
    (960, 720, [700, 20, 160, 200]),
])
def test_attendance_accepts_off_centre_faces_in_complete_scene(width, height, box):
    quality = {"accepted": True, "frame_width": width, "frame_height": height, "box": box}
    assert check_scene(quality)[0]
    assert face_box(quality) is not None
    assert not check_frame(quality)[0]  # Enrollment deliberately keeps its oval.


def test_tracking_can_show_quality_feedback_without_accepting_face():
    quality = {"accepted": False, "reason": "blurred", "frame_width": 1000,
               "frame_height": 500, "box": [100, 100, 200, 250]}
    assert not check_scene(quality)[0]
    assert face_box(quality) == pytest.approx([.1, .2, .2, .5])


@pytest.mark.parametrize("quality", [{}, {"box": [0, 0, 100, 100]},
    {"frame_width": 1000, "frame_height": 500, "box": [float("nan"), 0, 100, 100]},
    {"frame_width": 1000, "frame_height": 500, "box": [1100, 0, 100, 100]},
])
def test_invalid_box_never_produces_tracking_or_acceptance(quality):
    assert face_box(quality) is None
    assert not check_scene(quality | {"accepted": True})[0]
