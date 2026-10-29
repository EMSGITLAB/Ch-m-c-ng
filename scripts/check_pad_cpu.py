"""Run real PAD networks locally; smoke/performance only, no liveness accuracy claim."""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.face_engine import FaceEngine  # noqa: E402
from app.pad_engine import PadEngine  # noqa: E402


def main():
    face = FaceEngine(ROOT / "models")
    engine = PadEngine(ROOT / "models/pad")
    image = face.decode((ROOT / ".runtime/fixtures/sface_demo.jpg").read_bytes())
    boxes = face.detect(image)
    if not len(boxes):
        raise ValueError("Public smoke fixture has no detected face")
    box = max(boxes, key=lambda row: row[2] * row[3])[:4]
    timings, scores = [], []
    for _ in range(20):
        result = engine.score(image, box)
        assert result["decision"] == "not_evaluated" and not result["validated_for_attendance"]
        assert all(abs(sum(item["probabilities"]) - 1) < 1e-6 for item in result["models"])
        timings.append(result["pad_ms"])
        scores.append(result["ensemble_live_score"])
    if max(scores) - min(scores) > 1e-6:
        raise ValueError("PAD inference not repeatable on identical input")
    report = {
        "model_id": engine.model_id, "runtime": "OpenCV DNN CPU", "runs": len(timings),
        "input": "public_OpenCV_Zoo_demo_unlabelled_not_validation_data",
        "timing_scope": "two_PAD_models_and_preprocessing_only_not_full_attendance",
        "median_ms": round(float(np.median(timings)), 2), "p95_ms": round(float(np.percentile(timings, 95)), 2),
        "repeatability_passed": True, "networks_loaded_and_executed": 2,
        "threshold_selected": False, "pad_accuracy_validated": False,
        "attendance_enabled": False, "images_vectors_identities_exported": False,
    }
    (ROOT / "evidence/m1/pad-cpu-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
