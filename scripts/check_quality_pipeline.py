"""Exercise actual detection/alignment and rejection on a licensed non-user fixture."""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.face_engine import FaceEngine, FaceInputError  # noqa: E402

engine=FaceEngine(ROOT/"models")
image=cv2.imdecode(np.frombuffer((ROOT/".runtime/fixtures/sface_demo.jpg").read_bytes(),dtype=np.uint8),cv2.IMREAD_COLOR)
faces=engine.detect(image)
assert len(faces)>1


def jpeg(array):
    valid,encoded=cv2.imencode(".jpg",array)
    assert valid
    return encoded.tobytes()


try:
    engine.analyze(jpeg(image))
    raise AssertionError("Multiple faces were accepted")
except FaceInputError as error:
    assert error.code=="multiple_faces"
face=faces[0]
x,y,width,height=face[:4]
crop=image[max(0,int(y-height*.15)):min(image.shape[0],int(y+height*1.15)),max(0,int(x-width*.15)):min(image.shape[1],int(x+width*1.15))]
crop=cv2.resize(crop,(480,480))
vector,metadata=engine.analyze(jpeg(crop))
assert vector.shape==(128,)
assert metadata["quality"]["accepted"]
try:
    engine.analyze(jpeg(np.zeros((480,480,3),dtype=np.uint8)))
    raise AssertionError("Empty image was accepted")
except FaceInputError as error:
    assert error.code=="no_face"
report={"fixture":"OpenCV Zoo SFace demo (Apache-2.0)","single_face_detect_align_embedding":"passed","multiple_face_rejection":"passed","no_face_rejection":"passed","quality":metadata["quality"],"real_camera_calibration":False,"images_saved":False}
(ROOT/"evidence/m1/quality-pipeline.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report))
