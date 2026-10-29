"""Exercise native detection-only preview and stability on a licensed fixture."""
import hashlib
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.auto_capture import StabilityTracker, check_frame  # noqa: E402
from app.capture_guidance import check_pose  # noqa: E402
from app.face_engine import FaceEngine  # noqa: E402

engine=FaceEngine(ROOT/"models")
source=cv2.imdecode(np.frombuffer((ROOT/".runtime/fixtures/sface_demo.jpg").read_bytes(),dtype=np.uint8),cv2.IMREAD_COLOR)
face=engine.detect(source)[0]
x,y,width,height=face[:4]
crop=source[max(0,int(y-height*.15)):min(source.shape[0],int(y+height*1.15)),max(0,int(x-width*.15)):min(source.shape[1],int(x+width*1.15))]
crop=cv2.resize(crop,(360,360))
canvas=np.full((720,960,3),120,dtype=np.uint8)
canvas[180:540,300:660]=crop


def forbidden_extract(*args):
    raise AssertionError("A preview must not extract an embedding")


engine.extract=forbidden_extract
now=[0.]
tracker=StabilityTracker(lambda:now[0])
counts=[]
for index in range(3):
    success,encoded=cv2.imencode(".jpg",cv2.convertScaleAbs(canvas,alpha=1,beta=index))
    assert success
    content=encoded.tobytes()
    _,_,metadata=engine.inspect(content)
    quality=metadata["quality"]
    assert check_frame(quality)[0],quality
    assert check_pose(0,quality)[0],quality
    state=tracker.observe(("licensed-fixture",0,0,engine.model_id),quality,hashlib.sha256(content).hexdigest())
    counts.append(state["stable_frames"])
    assert state["ready"] is (index==2)
    now[0]+=.5
assert tracker.consume(("licensed-fixture",0,0,engine.model_id),hashlib.sha256(content).hexdigest(),state["capture_token"])
report={"fixture":"OpenCV Zoo SFace demo (Apache-2.0)","native_detection_only_preview":"passed",
        "frame_and_front_pose":"passed","stable_frames":counts,"single_use_capture_permission":"passed",
        "images_saved":False,"vectors_saved":False,"real_camera_auto_capture_verified":False,"pad_verified":False}
(ROOT/"evidence/m2/auto-capture-pipeline.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report))
