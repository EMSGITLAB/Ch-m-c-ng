"""Profile/recognition integration with synthetic vectors, not accuracy evidence."""
import io

import numpy as np
import pytest
from app.face_engine import FaceEngine, FaceInputError
from app.main import app
from app.models import CollectionSample, Employee, FaceTemplate, ImportedFacePhoto, RecognitionPolicy
from PIL import Image
from sqlalchemy import func, select
from test_admin import setup
from test_attendance import attendance as attendance  # noqa: F401
from test_functional_trial import trial as trial  # noqa: F401
from test_recognition_sequence import recognition as recognition  # noqa: F401


def png(color=140):
    stream = io.BytesIO()
    Image.new("RGB", (160, 160), color=(color, color, color)).save(stream, "PNG")
    return stream.getvalue()


def install(monkeypatch, index=1, error=None):
    engine = app.state.face_engine
    monkeypatch.setattr(engine, "decode", FaceEngine.decode, raising=False)

    def analyze(content):
        if error:
            raise FaceInputError(error, {"accepted": False, "reason": error})
        return np.eye(128, dtype="<f4")[index], {"quality": {"accepted": True, "reason": "accepted"}}
    monkeypatch.setattr(engine, "analyze_reference", analyze, raising=False)


def new_person(browser, csrf, code="PORTRAIT"):
    return browser.post("/api/admin/employees", json={"code": code, "name": "Synthetic portrait",
        "department": "Phòng thử"}, headers={"X-CSRF-Token": csrf}).json()["id"]


def test_upload_one_photo_auto_enrolls_and_lists_avatar_without_extra_collection(trial, monkeypatch):
    browser, factory, _, _, _, _ = trial
    csrf = setup(browser)
    identity = new_person(browser, csrf)
    endpoint = f"/api/admin/employees/{identity}/photo"
    install(monkeypatch)
    assert browser.put(endpoint, content=png()).status_code == 403
    response = browser.put(endpoint, content=png(), headers={"X-CSRF-Token": csrf, "Content-Type": "image/png"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["reference_accepted"] and result["recognition"]["enabled"]
    assert result["recognition"]["participants"] == 2
    assert result["recognition"]["threshold_changed"] is False
    assert browser.get(result["profile_photo_url"]).content == png()
    row = browser.get("/api/admin/employees?q=PORTRAIT").json()["items"][0]
    assert row["profile_photo_url"] == result["profile_photo_url"]
    assert row["template_count"] == row["collection_count"] == 1
    assert browser.get("/api/admin/employees/departments").json()["items"] == ["Phòng thử"]
    again = browser.put(endpoint, content=png(), headers={"X-CSRF-Token": csrf})
    assert again.status_code == 200, again.text
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(ImportedFacePhoto)) == 1
        assert db.scalar(select(func.count()).select_from(CollectionSample)) == 1
        assert db.scalar(select(func.count()).select_from(FaceTemplate).where(FaceTemplate.employee_id == identity)) == 1


@pytest.mark.parametrize("reason", ["multiple_faces", "face_too_small", "blurred"])
def test_rejected_portrait_saved_but_not_published_and_corrupt_file_rejected(trial, monkeypatch, reason):
    browser, factory, _, _, _, _ = trial
    csrf = setup(browser)
    identity = new_person(browser, csrf)
    install(monkeypatch, error=reason)
    endpoint = f"/api/admin/employees/{identity}/photo"
    headers = {"X-CSRF-Token": csrf}
    assert browser.put(endpoint, content=b"not an image", headers=headers).status_code == 422
    response = browser.put(endpoint, content=png(), headers=headers)
    assert response.status_code == 200, response.text
    assert not response.json()["reference_accepted"]
    assert not response.json()["recognition"]["enabled"]
    assert reason == response.json()["quality"]["reason"]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(FaceTemplate).where(FaceTemplate.employee_id == identity)) == 0


def test_indistinguishable_people_do_not_replace_policy_and_old_revision_does_not_reappear(trial, monkeypatch):
    browser, factory, ids, _, _, _ = trial
    csrf = setup(browser)
    identity = new_person(browser, csrf)
    install(monkeypatch, index=0)  # Same vector as existing member: must refuse automatic enrollment.
    result = browser.put(f"/api/admin/employees/{identity}/photo", content=png(), headers={"X-CSRF-Token": csrf})
    assert result.status_code == 200, result.text
    assert result.json()["reference_accepted"] and not result.json()["recognition"]["enabled"]
    with factory() as db:
        assert db.get(RecognitionPolicy, "trial-functional-test").enabled
        assert db.scalar(select(func.count()).select_from(FaceTemplate).where(FaceTemplate.employee_id == identity)) == 0
        person = db.get(Employee, identity)
        person.biometric_revision += 1
        db.commit()
    row = browser.get("/api/admin/employees?q=PORTRAIT").json()["items"][0]
    assert row["profile_photo_url"] is None
    assert browser.put(f"/api/admin/employees/{identity}/photo", content=png(),
        headers={"X-CSRF-Token": csrf}).status_code == 409


def test_reference_size_exception_never_changes_live_gate(monkeypatch):
    from test_quality import fixture
    image, face = fixture()
    face[:14] *= 0.45  # 81x90 original pixels; all landmarks retain their geometry.
    engine = FaceEngine.__new__(FaceEngine)
    engine.model_id, engine.dimensions = "synthetic", 128
    monkeypatch.setattr(engine, "decode", lambda *args: image)
    monkeypatch.setattr(engine, "detect", lambda *args: np.array([face]))
    monkeypatch.setattr(engine, "extract", lambda *args: (np.eye(128)[0], {}))
    with pytest.raises(FaceInputError, match="face_too_small"):
        engine.analyze(b"synthetic")
    _, metadata = engine.analyze_reference(b"synthetic")
    assert metadata["quality"]["accepted"] and metadata["quality"]["reference_only"]
    face[2] = 63
    with pytest.raises(FaceInputError, match="face_too_small"):
        engine.analyze_reference(b"synthetic")
