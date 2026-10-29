import numpy as np
import pytest
from app.config import get_settings
from app.face_engine import FaceInputError
from app.main import app, capture_slots
from fastapi.testclient import TestClient


class TestEngine:
    __test__=False

    def analyze(self,content,max_bytes):
        if content==b"blurred":
            raise FaceInputError("blurred",{"accepted":False,"sharpness":0})
        return np.zeros(128),{"dimensions":128,"quality":{"accepted":True}}


@pytest.fixture
def capture_client():
    with TestClient(app) as browser:
        app.state.face_engine=TestEngine()
        yield browser


def test_capture_requires_explicit_intent_and_allowed_origin(capture_client):
    assert capture_client.post("/api/diagnostics/face",content=b"test").status_code==403
    headers={"X-Local-Capture":"quality-test","Origin":"https://other.invalid"}
    assert capture_client.post("/api/diagnostics/face",content=b"test",headers=headers).status_code==403


def test_capture_response_contains_no_vector_and_never_records_attendance(capture_client):
    response=capture_client.post("/api/diagnostics/face",content=b"test",headers={"X-Local-Capture":"quality-test"})
    assert response.status_code==200
    assert response.json()["stored"] is False
    assert response.json()["attendance_recorded"] is False
    assert "vector" not in response.json()


def test_capture_rejection_and_limits_release_processing_slot(capture_client):
    headers={"X-Local-Capture":"quality-test"}
    assert capture_client.post("/api/diagnostics/face",content=b"blurred",headers=headers).json()["reason"]=="blurred"
    assert capture_client.post("/api/diagnostics/face",content=b"x"*2_000_001,headers=headers).status_code==413
    assert capture_client.post("/api/diagnostics/face",content=b"test",headers=headers).status_code==200
    assert capture_slots.acquire(blocking=False)
    assert capture_slots.acquire(blocking=False)
    try:
        assert capture_client.post("/api/diagnostics/face",content=b"test",headers=headers).status_code==429
    finally:
        capture_slots.release()
        capture_slots.release()


def test_capture_diagnostic_is_not_exposed_in_production(capture_client):
    settings=get_settings()
    previous=settings.environment
    settings.environment="production"
    try:
        assert capture_client.post("/api/diagnostics/face",content=b"test",headers={"X-Local-Capture":"quality-test"}).status_code==403
    finally:
        settings.environment=previous
