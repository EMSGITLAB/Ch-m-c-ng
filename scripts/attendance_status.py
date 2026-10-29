"""Read-only aggregate state; no identities, tokens or biometric vectors."""
import json
import sys
from pathlib import Path

from sqlalchemy import func, select

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.database import session_factory  # noqa: E402
from app.models import AttendanceEvent, RecognitionPolicy, RecognitionSession  # noqa: E402

with session_factory()() as db:
    report={"policies":db.scalar(select(func.count()).select_from(RecognitionPolicy)),
            "enabled_policies":db.scalar(select(func.count()).select_from(RecognitionPolicy).where(RecognitionPolicy.enabled==True)),  # noqa: E712
            "recognition_sessions":db.scalar(select(func.count()).select_from(RecognitionSession)),
            "attendance_events":db.scalar(select(func.count()).select_from(AttendanceEvent)),
            "identities_exported":False,"vectors_exported":False}
    print(json.dumps(report))
