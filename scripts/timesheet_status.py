"""Aggregate a live preview without exporting employee names or events."""
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"))
from app.config import get_settings  # noqa: E402
from app.database import session_factory  # noqa: E402
from app.timesheets import build_report  # noqa: E402

today=datetime.now(ZoneInfo(get_settings().business().timezone)).date()
with session_factory()() as db:
    report=build_report(db,today.replace(day=1),today)
    print(json.dumps({"calculation_version":report["calculation_version"],"source_digest":report["source_digest"],
                      "summary":report["summary"],"source_events":report["source_event_count"],
                      "source_assignments":report["source_assignment_count"],"finalized":report["finalized"],
                      "identities_exported":False,"events_exported":False}))
