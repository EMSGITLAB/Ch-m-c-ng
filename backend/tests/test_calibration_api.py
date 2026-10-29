from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import numpy as np
from app.main import app
from app.models import CollectionSample, Employee, FaceCollection
from test_admin import setup


def test_calibration_requires_admin_csrf_and_origin(client):
    browser, _ = client
    endpoint = "/api/admin/recognition/calibration"
    assert browser.post(endpoint).status_code == 401
    csrf = setup(browser)
    assert browser.post(endpoint).status_code == 403
    assert browser.post(endpoint, headers={"X-CSRF-Token": csrf, "Origin": "https://outside.invalid"}).status_code == 403


def test_insufficient_data_is_explicit_no_threshold_is_exposed_or_applied(client):
    browser, _ = client
    csrf = setup(browser)
    app.state.face_engine = SimpleNamespace(model_id="m", dimensions=128)
    response = browser.post("/api/admin/recognition/calibration", headers={"X-CSRF-Token": csrf})
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "insufficient_data"
    assert report["candidate"] is None
    assert report["coverage"]["enrolled_people"] == 0
    assert report["operational_enabled"] is False
    assert "vectors" not in report
    assert "people" not in report
    app.state.face_engine = None
    assert browser.post("/api/admin/recognition/calibration", headers={"X-CSRF-Token": csrf}).status_code == 503


def test_coverage_shows_exact_missing_probes_and_never_counts_final_or_old_data(client, monkeypatch):
    browser, factory = client
    endpoint = "/api/admin/recognition/calibration/coverage"
    assert browser.get(endpoint).status_code == 401
    csrf = setup(browser)
    monkeypatch.setitem(app.state._state, "face_engine", SimpleNamespace(model_id="m", dimensions=128))
    monkeypatch.setitem(app.state._state, "pad_engine", None)  # T09 does not depend on PAD.
    with factory() as db:
        people = [Employee(code=code, name=f"Hồ sơ thử {code}", active=code != "D") for code in "ABCD"]
        db.add_all(people)
        db.flush()
        specifications = [(0, "enrollment", 1, "m", 0, "complete"),
                          (0, "calibration", 1, "m", 0, "complete"),
                          (1, "calibration", 5, "m", 0, "complete"),
                          (3, "enrollment", 1, "m", 0, "complete"),
                          (0, "evaluation", 9, "m", 0, "complete"),
                          (0, "calibration", 5, "m", 1, "complete"),
                          (0, "calibration", 5, "old", 0, "complete"),
                          (0, "calibration", 5, "m", 0, "open")]
        for number, (person, purpose, count, model, revision, status) in enumerate(specifications):
            collection = FaceCollection(employee_id=people[person].id, model_id=model, biometric_revision=revision,
                                        purpose=purpose, status=status, sample_count=count,
                                        expires_at=datetime.now(UTC) + timedelta(minutes=10))
            db.add(collection)
            db.flush()
            for position in range(count):
                db.add(CollectionSample(collection_id=collection.id, model_id=model, dimensions=128,
                                        position=position+1, fingerprint=f"coverage-{number}-{position}",
                                        vector=b"unreadable-final" if purpose == "evaluation"
                                        else np.eye(128, dtype="<f4")[0].tobytes(), quality={}))
        db.commit()
    response = browser.get(endpoint + "?limit=2")
    assert response.status_code == 200
    report = response.json()
    assert report["total"] == 3 and len(report["items"]) == 2
    assert report["items"][0]["enrollment_samples"] == 1
    assert report["items"][0]["calibration_samples"] == 1
    assert report["items"][0]["missing_calibration_samples"] == 4
    assert report["items"][1]["role"] == "outside_probe"
    assert report["summary"]["enrolled_people"] == 1
    assert report["summary"]["outside_people_missing"] == 1
    assert report["summary"]["known_probe_samples_missing"] == 4
    assert not report["operational_enabled"] and not report["final_evaluation_used"]
    assert browser.get(endpoint + "?offset=2").json()["items"][0]["role"] == "no_samples"
    assert browser.get(endpoint + "?limit=101").status_code == 422
    assert browser.post("/api/admin/recognition/calibration", headers={"X-CSRF-Token": csrf}).status_code == 200
