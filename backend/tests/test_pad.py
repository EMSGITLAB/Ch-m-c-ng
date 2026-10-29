import json
import threading
from pathlib import Path

import numpy as np
import pytest
from app import pad_api
from app.face_engine import FaceInputError
from app.main import app
from app.models import AttendanceEvent, FaceTemplate, ImportedFacePhoto, RecognitionPolicy
from app.pad_engine import PadEngine, prepare, probabilities
from sqlalchemy import func, select
from test_admin import setup


def test_preprocessing_preserves_bgr_raw_values_and_nchw_float32():
    image = np.full((480, 640, 3), [10, 100, 220], dtype=np.uint8)
    tensor, clipped = prepare(image, [240, 160, 120, 120], 2.7)
    assert tensor.shape == (1, 3, 80, 80) and tensor.dtype == np.float32
    assert tensor.flags.c_contiguous
    assert tensor[0, :, 40, 40].tolist() == [10, 100, 220]
    assert not clipped
    assert prepare(image, [1, 1, 120, 120], 4)[1]


@pytest.mark.parametrize("box", [[-1, 0, 120, 120], [600, 0, 120, 120],
                               [1, 1, 0, 120], [float("nan"), 0, 120, 120], [1, 2]])
def test_invalid_geometry_is_never_scored(box):
    with pytest.raises(ValueError):
        prepare(np.zeros((480, 640, 3), dtype=np.uint8), box, 2.7)


def test_softmax_is_stable_and_rejects_invalid_outputs():
    assert probabilities([[1000, 1001, 999]]).sum() == pytest.approx(1)
    assert np.argmax(probabilities([[1000, 1001, 999]])) == 1
    for value in ([[1, 2]], [[1, float("nan"), 2]], [[1, 2, 3], [4, 5, 6]]):
        with pytest.raises(ValueError):
            probabilities(value)


def test_model_checksum_and_path_are_checked_before_network_loading(tmp_path):
    source = Path(__file__).resolve().parents[2] / "models/pad/manifest.json"
    manifest = json.loads(source.read_text(encoding="utf-8"))
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / manifest["models"][0]["filename"]).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        PadEngine(tmp_path)
    manifest["models"][0]["filename"] = "../outside.onnx"
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="path"):
        PadEngine(tmp_path)


def test_ensemble_uses_both_models_and_never_promotes_a_score_to_validation():
    class Network:
        def __init__(self, logits):
            self.logits = logits
        def setInput(self, tensor):
            assert tensor.shape == (1, 3, 80, 80)
        def forward(self):
            return self.logits

    engine = PadEngine.__new__(PadEngine)
    engine.model_id = "synthetic-models"
    engine.lock = threading.Lock()
    engine.networks = [("a", 2.7, Network([[0, 2, 0]])), ("b", 4, Network([[0, -2, 0]]))]
    result = engine.score(np.zeros((480, 640, 3), dtype=np.uint8), [200, 150, 120, 120])
    expected = (probabilities([[0, 2, 0]])[1] + probabilities([[0, -2, 0]])[1]) / 2
    assert result["ensemble_live_score"] == pytest.approx(expected)
    assert len(result["models"]) == 2 and not result["validated_for_attendance"]
    assert result["decision"] == "not_evaluated"


def test_diagnostics_require_admin_and_csrf_and_never_enable_attendance(client, monkeypatch):
    browser, factory = client
    assert browser.get("/api/admin/pad/status").status_code == 401
    assert browser.post("/api/admin/pad/preview", content=b"photo").status_code == 401
    csrf = setup(browser)
    headers = {"X-CSRF-Token": csrf, "X-PAD-Intent": "experimental-pad-preview"}
    assert browser.post("/api/admin/pad/preview", content=b"photo").status_code == 403

    class Face:
        def inspect(self, content):
            if content == b"no-face":
                raise FaceInputError("no_face")
            return np.zeros((480, 640, 3), dtype=np.uint8), np.array([200, 150, 120, 120]), {"quality": {"accepted": True}}

    class Pad:
        model_id = "test-pad"
        def score(self, image, box):
            return {"ensemble_live_score": .99, "validated_for_attendance": False, "decision": "not_evaluated"}

    monkeypatch.setitem(app.state._state, "face_engine", Face())
    monkeypatch.setitem(app.state._state, "pad_engine", Pad())
    assert browser.get("/api/admin/pad/status").json()["threshold"] is None
    readiness = browser.get("/api/system/status").json()
    assert readiness["experimental_pad_ready"] and not readiness["pad_validated_for_attendance"]
    assert not readiness["attendance_enabled"]
    response = browser.post("/api/admin/pad/preview", content=b"photo", headers=headers)
    assert response.status_code == 200
    assert response.json()["pad"]["decision"] == "not_evaluated"
    assert response.json()["stored"] is False and response.json()["attendance_recorded"] is False
    assert app.state.attendance_policy_id is None
    failed = browser.post("/api/admin/pad/preview", content=b"no-face", headers=headers).json()
    assert failed["pad"] is None and not failed["quality_accepted"]
    assert pad_api.slots.acquire(blocking=False)
    try:
        assert browser.post("/api/admin/pad/preview", content=b"photo", headers=headers).status_code == 429
    finally:
        pad_api.slots.release()
    with factory() as db:
        for model in (AttendanceEvent, FaceTemplate, ImportedFacePhoto, RecognitionPolicy):
            assert db.scalar(select(func.count()).select_from(model)) == 0
    monkeypatch.setitem(app.state._state, "pad_engine", None)
    assert not browser.get("/api/system/status").json()["experimental_pad_ready"]
    assert browser.post("/api/admin/pad/preview", content=b"photo", headers=headers).status_code == 503
