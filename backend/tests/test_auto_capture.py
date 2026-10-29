import numpy as np
import pytest
from app import collections
from app.auto_capture import StabilityTracker, check_frame
from app.face_engine import FaceInputError
from app.main import app
from app.models import CollectionSample, FaceCollection
from sqlalchemy import func, select
from test_collections import SampleEngine, capture, create
from test_collections import collection_client as collection_client

QUALITY={"frame_width":960,"frame_height":720,"box":[336,200,288,320],"yaw_ratio":0,"pitch_ratio":.5,"roll_degrees":0}


def test_stability_requires_time_distinct_frames_and_resets_on_motion():
    now=[0.]
    tracker=StabilityTracker(lambda:now[0])
    signature=("session",0,0,"model")
    assert tracker.observe(signature,QUALITY,"a")["stable_frames"]==1
    now[0]=.1
    assert tracker.observe(signature,QUALITY,"b")["stable_frames"]==1
    now[0]=.5
    assert tracker.observe(signature,QUALITY,"a")["stable_frames"]==1
    assert not tracker.observe(signature,QUALITY,"b")["ready"]
    now[0]=1.
    moved=QUALITY | {"box":[390,200,288,320]}
    assert tracker.observe(signature,moved,"c")["stable_frames"]==1
    now[0]=1.5
    tracker.observe(signature,moved,"d")
    now[0]=2.
    ready=tracker.observe(signature,moved,"e")
    assert ready["ready"]
    assert not tracker.consume(signature,"different-photo",ready["capture_token"])
    assert tracker.consume(signature,"e",ready["capture_token"])
    assert not tracker.consume(signature,"e",ready["capture_token"])


def test_token_expires_and_cannot_cross_collection_or_count():
    now=[0.]
    tracker=StabilityTracker(lambda:now[0])
    key=("session",0,0,"m")
    for number in range(3):
        now[0]=number*.5
        ready=tracker.observe(key,QUALITY,str(number))
    assert not tracker.consume(("other",0,0,"m"),"2",ready["capture_token"])
    assert not tracker.consume(("session",1,0,"m"),"2",ready["capture_token"])
    now[0]=5
    assert not tracker.consume(key,"2",ready["capture_token"])


@pytest.mark.parametrize("changes",[{"box":[0,200,288,320]},{"box":[420,310,80,100]},
                                      {"box":[200,50,560,600]},{"box":[336,400,288,320]},
                                      {"frame_width":1280}])
def test_face_must_fit_visible_frame(changes):
    assert check_frame(QUALITY)[0]
    assert not check_frame(QUALITY | changes)[0]


@pytest.fixture
def automatic_client(collection_client,monkeypatch):
    browser,factory,headers,employee=collection_client
    now=[0.]
    monkeypatch.setattr(collections,"tracker",StabilityTracker(lambda:now[0]))
    class PreviewEngine(SampleEngine):
        embeddings=0
        def inspect(self,content,max_bytes):
            if content==b"no-face":
                raise FaceInputError("no_face")
            _,metadata=SampleEngine.analyze(self,content,max_bytes)
            metadata["quality"]=QUALITY | metadata["quality"]
            if content.startswith(b"outside"):
                metadata["quality"]["box"]=[0,200,288,320]
            return None,None,metadata
        def analyze(self,content,max_bytes):
            self.embeddings+=1
            _,_,metadata=self.inspect(content,max_bytes)
            return np.eye(128,dtype=np.float32)[0],metadata
    app.state.face_engine=PreviewEngine()
    return browser,factory,headers,employee,now


def preview(browser,headers,session,photo):
    return browser.post(f"/api/admin/collections/{session}/preview",content=photo,headers=headers)


def test_preview_never_stores_vectors_and_auto_flow_saves_exactly_one_per_pose(automatic_client):
    browser,factory,headers,employee,now=automatic_client
    session=create(browser,headers,employee)
    for pose in range(5):
        for number in range(3):
            photo=f"pose-{pose}-frame-{number}-{pose}".encode()
            response=preview(browser,headers,session["id"],photo)
            assert response.status_code==200,response.text
            ready=response.json()
            assert ready["ready"] is (number==2)
            now[0]+=.5
        with factory() as db:
            assert db.get(FaceCollection,session["id"]).sample_count==pose
        assert app.state.face_engine.embeddings==pose
        auto_headers=headers | {"X-Capture-Mode":"auto","X-Capture-Token":ready["capture_token"]}
        saved=capture(browser,auto_headers,session["id"],photo)
        assert saved.status_code==201,saved.text
        assert saved.json()["quality"]["capture_mode"]=="auto"
        assert saved.json()["collection"]["sample_count"]==pose+1
        assert capture(browser,auto_headers,session["id"],photo).status_code==409
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(CollectionSample))==5
    assert browser.post(f"/api/admin/collections/{session['id']}/complete",headers=headers).status_code==200


def test_bad_frame_resets_stability_and_wrong_pose_does_not_save(automatic_client):
    browser,factory,headers,employee,now=automatic_client
    session=create(browser,headers,employee)
    assert preview(browser,{},session["id"],b"a-0").status_code==403
    for number in range(2):
        assert not preview(browser,headers,session["id"],f"frame-{number}-0".encode()).json()["ready"]
        now[0]+=.5
    for photo in [b"outside-0",b"no-face"]:
        rejected=preview(browser,headers,session["id"],photo).json()
        assert not rejected["ready"]
        assert rejected["stable_frames"]==0
    assert preview(browser,headers,session["id"],b"retry-0").json()["stable_frames"]==1
    assert capture(browser,headers | {"X-Capture-Mode":"auto"},session["id"],b"retry-0").status_code==409
    assert capture(browser,headers,session["id"],b"manual-front-0").status_code==201
    wrong=preview(browser,headers,session["id"],b"still-front-0").json()
    assert wrong["reason"]=="wrong_pose"
    with factory() as db:
        assert db.get(FaceCollection,session["id"]).sample_count==1
