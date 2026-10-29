import pytest
from app.config import BusinessConfig
from app.main import app
from fastapi.testclient import TestClient
from pydantic import ValidationError


def test_startup_is_not_attendance_success():
    client = TestClient(app)
    response = client.get("/api/system/status")
    assert response.status_code == 200
    assert response.json()["attendance_enabled"] is False
    assert response.json()["recognition_ready"] is False
    assert "database_url" not in response.text
    assert response.headers["Cache-Control"] == "no-store"


def test_business_defaults_are_not_approved_timesheets():
    config = BusinessConfig()
    assert config.capture_retention_days == 0
    assert config.store_enrollment_images is False
    assert config.default_shift.approved_for_real_timesheets is False


@pytest.mark.parametrize("changes", [{"kiosk_direction": "auto"}, {"cooldown_seconds": 0}, {"capture_retention_days": -1}])
def test_reject_invalid_business_settings(changes):
    with pytest.raises(ValidationError):
        BusinessConfig(**changes)

