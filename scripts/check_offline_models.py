"""Run actual local CPU model inference while the process denies Python egress."""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("offline_probe_guard", ROOT / "backend/tests/network_guard.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
guard = module.NetworkGuard().install()
sys.path.insert(0, str(ROOT / "backend"))
try:
    import cv2
    import numpy as np
    from app.face_engine import FaceEngine
    from app.matching import Gallery
    from app.pad_engine import PadEngine

    fixture = ROOT / ".runtime/fixtures/sface_demo.jpg"
    image = cv2.imdecode(np.frombuffer(fixture.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Licensed local fixture is missing or invalid; no runtime download is allowed")
    engine = FaceEngine(ROOT / "models")
    faces = engine.detect(image)
    assert len(faces) > 0
    vector, _ = engine.extract(image, faces[0])
    assert vector.shape == (128,)
    assert Gallery(engine.model_id, {"technical-fixture": [vector]}).rank(vector, engine.model_id).first_id
    pad = PadEngine(ROOT / "models/pad")
    pad.score(image, faces[0][:4])
    assert guard.denied == 0
    report = {"identity_cpu_inference": True, "local_vector_matching": True, "pad_cpu_inference": True,
              "embedding_dimensions": 128, "nonlocal_network_attempts": guard.denied,
              "licensed_public_fixture": True, "identity_or_pad_accuracy_validation": False,
              "images_vectors_exported": False, "user_network_settings_changed": False}
    (ROOT / "evidence/m5/offline-models-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
finally:
    guard.close()
