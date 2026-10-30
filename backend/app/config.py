import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ShiftDefaults(BaseModel):
    name: str = "Ca mẫu có thể điều chỉnh"
    start: str = "08:00"
    end: str = "17:00"
    break_start: str = "12:00"
    break_end: str = "13:00"
    approved_for_real_timesheets: bool = False


class BusinessConfig(BaseModel):
    timezone: str = "Asia/Ho_Chi_Minh"
    cooldown_seconds: int = Field(default=60, ge=1, le=3600)
    kiosk_direction: str = "in"
    capture_retention_days: int = Field(default=0, ge=0)
    store_enrollment_images: bool = False
    attendance_retention_days: int | None = None
    default_shift: ShiftDefaults = ShiftDefaults()

    @model_validator(mode="after")
    def validate_direction(self):
        if self.kiosk_direction not in {"in", "out"}:
            raise ValueError("kiosk_direction must be in or out")
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", env_prefix="CHAMCONG_", extra="ignore")
    app_name: str = "Chấm công local"
    environment: str = "development"
    database_url: str = "mssql+pyodbc://@localhost/ChamCongFaceLocal?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=yes"
    business_config_path: Path = PROJECT_ROOT / "config" / "business.json"
    models_dir: Path = PROJECT_ROOT / "models"
    runtime_dir: Path = PROJECT_ROOT / ".runtime"
    backup_directory: Path | None = None
    frontend_dist_path: Path = PROJECT_ROOT / "frontend" / "dist"
    serve_frontend: bool = True
    session_secret: str = ""
    max_upload_bytes: int = 2_000_000
    opencv_threads: int = Field(default=4, ge=1, le=32)
    capture_max_edge: int = Field(default=1280, ge=640, le=1600)
    speech_threads: int = Field(default=2, ge=1, le=4)
    speech_timeout_seconds: int = Field(default=30, ge=10, le=60)
    speech_prewarm_enabled: bool = True
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "testserver"]
    allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000", "http://testserver"]
    session_hours: int = Field(default=8, ge=1, le=24)
    functional_trial_enabled: bool = False
    functional_trial_policy_id: str | None = None

    def business(self) -> BusinessConfig:
        return BusinessConfig.model_validate(json.loads(self.business_config_path.read_text(encoding="utf-8")))


@lru_cache
def get_settings() -> Settings:
    return Settings()

