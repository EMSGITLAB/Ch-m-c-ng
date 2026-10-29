import numpy as np
import pytest
from app.quality import assess_quality


def fixture():
    rng = np.random.default_rng(42)
    image = rng.integers(70,180,(320,320,3),dtype=np.uint8)
    face = np.array([60,50,180,200,110,110,190,110,150,150,120,195,180,195,.99],dtype=np.float32)
    return image,face


def test_accept_one_clear_face_and_measure_quality():
    image,face=fixture()
    result=assess_quality(image,np.array([face]))
    assert result["accepted"]
    assert result["sharpness"] >=40
    assert result["yaw_ratio"]==0
    assert result["pitch_ratio"]==pytest.approx(40/85,abs=.0001)


@pytest.mark.parametrize("count,reason",[(0,"no_face"),(2,"multiple_faces")])
def test_require_exactly_one_face(count,reason):
    image,face=fixture()
    assert assess_quality(image,np.array([face]*count))["reason"] == reason


@pytest.mark.parametrize("value,reason",[(10,"too_dark"),(250,"too_bright"),(120,"blurred")])
def test_reject_bad_exposure_or_blur(value,reason):
    image,face=fixture()
    image[:]=value
    assert assess_quality(image,np.array([face]))["reason"] == reason


def test_reject_small_clipped_or_turned_faces():
    image,face=fixture()
    small=face.copy()
    small[2]=40
    assert assess_quality(image,np.array([small]))["reason"]=="face_too_small"
    clipped=face.copy()
    clipped[0]=-1
    assert assess_quality(image,np.array([clipped]))["reason"]=="face_clipped"
    turned=face.copy()
    turned[8]=220
    assert assess_quality(image,np.array([turned]))["reason"]=="look_straight"
