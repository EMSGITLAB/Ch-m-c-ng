import pytest
from app.capture_guidance import check_pose, instruction

ANCHOR={"yaw_ratio":0,"pitch_ratio":.5,"roll_degrees":0}


@pytest.mark.parametrize("count,yaw,pitch",[(0,0,.5),(1,.08,.5),(2,-.08,.5),(3,0,.43),(4,0,.57),(5,.01,.51),(9,0,.57)])
def test_expected_pose(count,yaw,pitch):
    assert check_pose(count,ANCHOR | {"yaw_ratio":yaw,"pitch_ratio":pitch},ANCHOR)[0]
    assert instruction(count)["position"]==count+1


@pytest.mark.parametrize("count,yaw,pitch",[(0,.25,.5),(1,0,.5),(1,-.1,.5),(2,.1,.5),(3,0,.6),(4,0,.4),(5,.2,.5)])
def test_wrong_or_unchanged_pose(count,yaw,pitch):
    assert not check_pose(count,ANCHOR | {"yaw_ratio":yaw,"pitch_ratio":pitch},ANCHOR)[0]


def test_person_specific_anchor_and_missing_or_nonfinite_metrics():
    anchor=ANCHOR | {"yaw_ratio":.1,"pitch_ratio":.7}
    assert check_pose(1,anchor | {"yaw_ratio":.18},anchor)[0]
    assert not check_pose(1,ANCHOR,None)[0]
    assert not check_pose(0,{},None)[0]
    assert not check_pose(0,ANCHOR | {"yaw_ratio":float("nan")})[0]
    assert not check_pose(0,ANCHOR | {"roll_degrees":20})[0]
    assert instruction(10) is None
