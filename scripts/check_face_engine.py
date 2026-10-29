import json
import sys
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.face_engine import FaceEngine  # noqa: E402

started = perf_counter()
engine = FaceEngine(ROOT / "models")
load_ms = (perf_counter()-started)*1000
image = cv2.imdecode(np.frombuffer((ROOT / ".runtime/fixtures/sface_demo.jpg").read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
assert image is not None
faces = engine.detect(image)
assert len(faces) >= 1, "No face in the licensed OpenCV example"
times = []
for _ in range(10):
    started = perf_counter()
    faces = engine.detect(image)
    vector, metadata = engine.extract(image, faces[0])
    times.append((perf_counter()-started)*1000)
assert vector.shape == (128,)
assert abs(float(np.linalg.norm(vector))-1) < 1e-5
repeat, _ = engine.extract(image, faces[0])
assert float(vector @ repeat) > 0.999
report = {"model_id": engine.model_id, "opencv": cv2.__version__, "device": "CPU", "load_and_warmup_ms": round(load_ms,2),
          "fixture_faces": len(faces), "dimensions": 128, "normalized": True, "repeat_consistency": True,
          "technical_smoke_mean_ms": round(float(np.mean(times)),2), "technical_smoke_p95_ms": round(float(np.percentile(times,95)),2),
          "external_inference_api": False, "accuracy_test": "not performed", "threshold_calibrated": False}
(ROOT / "evidence/m1").mkdir(exist_ok=True)
(ROOT / "evidence/m1/face-engine-smoke.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report))
