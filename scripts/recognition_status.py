"""Aggregate runtime checks without images, vectors, credentials or identities."""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from sqlalchemy import func, select, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.database import session_factory  # noqa: E402
from app.models import AttendanceEvent, FaceTemplate, RecognitionFrame, RecognitionPolicy, RecognitionSession  # noqa: E402

with session_factory()() as db:
    report = {"schema_revision": db.scalar(text("SELECT version_num FROM alembic_version")),
        "enabled_policies": db.scalar(select(func.count()).select_from(RecognitionPolicy).where(RecognitionPolicy.enabled == True)),  # noqa: E712
        "operational_templates": db.scalar(select(func.count()).select_from(FaceTemplate)),
        "recognition_sessions": db.scalar(select(func.count()).select_from(RecognitionSession)),
        "recognition_frames": db.scalar(select(func.count()).select_from(RecognitionFrame)),
        "attendance_events": db.scalar(select(func.count()).select_from(AttendanceEvent))}
with urllib.request.urlopen("http://127.0.0.1:8000/api/system/status", timeout=5) as response:
    status = json.load(response)
    report.update(attendance_enabled=status["attendance_enabled"], attendance_mode=status.get("attendance_mode"), recognition_ready=status["recognition_ready"])
    report.update(experimental_pad_ready=status.get("experimental_pad_ready", False),
                  pad_validated_for_attendance=status.get("pad_validated_for_attendance", False))
request = urllib.request.Request("http://127.0.0.1:8000/api/kiosk/recognition/sessions",
    data=b'{"request_id":"00000000-0000-0000-0000-000000000001"}', method="POST",
    headers={"Content-Type":"application/json", "X-Kiosk-Intent":"start-recognition"})
try:
    with urllib.request.urlopen(request, timeout=5) as response:
        report["unauthenticated_start_status"] = response.status
except urllib.error.HTTPError as error:
    report["unauthenticated_start_status"] = error.code
    error.close()
assert report["unauthenticated_start_status"] == 401
report["identities_images_vectors_exported"] = False
(ROOT / "evidence/m3/recognition-runtime-state.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report))
