"""Compare OpenCV CPU thread counts on a licensed fixture; no identity accuracy claims."""

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.face_engine import FaceEngine  # noqa: E402

original = cv2.getNumThreads()
engine = FaceEngine(ROOT / "models")
image = cv2.imdecode(np.frombuffer((ROOT / ".runtime/fixtures/sface_demo.jpg").read_bytes(), np.uint8), cv2.IMREAD_COLOR)
x, y, width, height = engine.detect(image)[0][:4]
crop = image[max(0, int(y-height*.15)):min(image.shape[0], int(y+height*1.15)),
             max(0, int(x-width*.15)):min(image.shape[1], int(x+width*1.15))]
valid, encoded = cv2.imencode(".jpg", cv2.resize(crop, (480, 480)))
assert valid
content = encoded.tobytes()
results = []


def once(_):
    start = perf_counter()
    vector, quality = engine.analyze(content)
    assert vector.shape == (128,) and quality["quality"]["accepted"]
    return perf_counter()-start


try:
    vectors = []
    for count in (14, 4):
        cv2.setNumThreads(count)
        vectors.append(engine.analyze(content)[0])
    cosine = float(np.clip(vectors[0] @ vectors[1], -1, 1))
    assert cosine > .99999
    for round_number in range(2):
        for count in dict.fromkeys([original, 1, 2, 4]):
            cv2.setNumThreads(count)
            once(0)
            with ThreadPoolExecutor(max_workers=2) as workers:
                samples = list(workers.map(once, range(20)))
            results.append({"round": round_number+1, "threads": count, "two_workers": True,
                            "samples": len(samples), "mean_ms": round(float(np.mean(samples))*1000, 2),
                            "p95_ms": round(float(np.percentile(samples, 95))*1000, 2)})
finally:
    cv2.setNumThreads(original)
report = {"original_threads": original, "results": results, "licensed_public_fixture": True,
          "embedding_cosine_threads_14_vs_4": cosine,
          "production_configuration_modified": False, "accuracy_or_pad_validation": False}
(ROOT / "evidence/m5/face-cpu-threads.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report))
