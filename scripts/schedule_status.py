"""Aggregate scheduling state without exporting employee or schedule details."""
import json
import sys
from pathlib import Path

from sqlalchemy import func, select

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.database import session_factory  # noqa: E402
from app.models import Shift, ShiftAssignment  # noqa: E402

with session_factory()() as db:
    report={"shift_versions":db.scalar(select(func.count()).select_from(Shift)),
            "active_shifts":db.scalar(select(func.count()).select_from(Shift).where(Shift.archived_at.is_(None))),
            "assignments":db.scalar(select(func.count()).select_from(ShiftAssignment)),
            "cancelled_assignments":db.scalar(select(func.count()).select_from(ShiftAssignment).where(ShiftAssignment.cancelled_at.is_not(None))),
            "employee_details_exported":False,"schedule_details_exported":False}
    print(json.dumps(report))
